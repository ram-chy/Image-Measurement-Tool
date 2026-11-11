"""
SQLite database layer — date-aware version.

When frozen, the DB is stored in a per-user writable folder
(%LOCALAPPDATA%\\ImageMeasurementTool) so the app works when installed
into Program Files (which is read-only for normal users).
When run from source, it stays next to main.py.
"""

import hashlib
import hmac
import json
import os
import secrets
import shutil
import sqlite3
import sys
from pathlib import Path
from datetime import datetime, date
from image_analyzer.core.analyzer import ImageInfo


def _data_dir() -> Path:
    if getattr(sys, "frozen", False):
        root = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(root) / "ImageMeasurementTool"
    return Path(__file__).resolve().parents[2]


def _db_path() -> str:
    base = _data_dir()
    base.mkdir(parents=True, exist_ok=True)
    db_file = base / "image_reports.db"

    # One-time migration from the old "DB next to the exe" location
    if not db_file.exists():
        legacy = Path(sys.executable).parent / "image_reports.db" \
            if getattr(sys, "frozen", False) else None
        if legacy and legacy.exists() and legacy.resolve() != db_file.resolve():
            try:
                shutil.copy2(legacy, db_file)
            except OSError:
                pass

    return str(db_file)


def get_connection() -> sqlite3.Connection:
    con = sqlite3.connect(_db_path())
    con.row_factory = sqlite3.Row
    return con


def _column_exists(con, table: str, column: str) -> bool:
    rows = con.execute(f"PRAGMA table_info({table})").fetchall()
    return any(r["name"] == column for r in rows)


def init_db():
    """Create tables and migrate existing DB if needed."""
    with get_connection() as con:
        # sessions table
        con.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                analysis_date TEXT    NOT NULL,
                created_at    TEXT    NOT NULL,
                total_files   INTEGER NOT NULL DEFAULT 0,
                ok_files      INTEGER NOT NULL DEFAULT 0
            )
        """)
        # image_records table
        con.execute("""
            CREATE TABLE IF NOT EXISTS image_records (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id       INTEGER NOT NULL REFERENCES sessions(id),
                analysis_date    TEXT    NOT NULL,
                analysed_at      TEXT    NOT NULL,
                file_name        TEXT,
                file_format      TEXT,
                file_path        TEXT,
                dpi_x            REAL,
                dpi_y            REAL,
                color_mode       TEXT,
                color_mode_label TEXT,
                width_px         INTEGER,
                height_px        INTEGER,
                width_inch       REAL,
                height_inch      REAL,
                width_feet       REAL,
                height_feet      REAL,
                file_size_kb     REAL,
                status           TEXT,
                moved_to         TEXT,
                original_name    TEXT
            )
        """)

        # ── Migrations: add new columns to existing DBs ───────────────────────
        if not _column_exists(con, "sessions", "analysis_date"):
            con.execute("ALTER TABLE sessions ADD COLUMN analysis_date TEXT NOT NULL DEFAULT ''")
            # Back-fill from created_at
            con.execute("UPDATE sessions SET analysis_date = substr(created_at, 1, 10) WHERE analysis_date = ''")

        if not _column_exists(con, "image_records", "analysis_date"):
            con.execute("ALTER TABLE image_records ADD COLUMN analysis_date TEXT NOT NULL DEFAULT ''")
            con.execute("""
                UPDATE image_records SET analysis_date = substr(analysed_at, 1, 10)
                WHERE analysis_date = ''
            """)

        # Original file path (needed to re-check whether a file was moved)
        if not _column_exists(con, "image_records", "file_path"):
            con.execute("ALTER TABLE image_records ADD COLUMN file_path TEXT")

        # Name of the file before the Item prefix was applied on move
        if not _column_exists(con, "image_records", "original_name"):
            con.execute("ALTER TABLE image_records ADD COLUMN original_name TEXT")

        # Indexes for fast date searches
        con.execute("""
            CREATE INDEX IF NOT EXISTS idx_sessions_date ON sessions (analysis_date)
        """)
        con.execute("""
            CREATE INDEX IF NOT EXISTS idx_records_date ON image_records (analysis_date)
        """)

        # ── User accounts (login) ─────────────────────────────────────────────
        con.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                username      TEXT NOT NULL UNIQUE COLLATE NOCASE,
                display_name  TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                salt          TEXT NOT NULL,
                is_admin      INTEGER NOT NULL DEFAULT 0,
                created_at    TEXT NOT NULL
            )
        """)

        # ── Customers ─────────────────────────────────────────────────────────
        con.execute("""
            CREATE TABLE IF NOT EXISTS customers (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                name       TEXT NOT NULL,
                mobile     TEXT NOT NULL UNIQUE,
                item       TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            )
        """)
        if not _column_exists(con, "customers", "item"):
            con.execute("ALTER TABLE customers ADD COLUMN item TEXT NOT NULL DEFAULT ''")

        # ── Token slips ───────────────────────────────────────────────────────
        con.execute("""
            CREATE TABLE IF NOT EXISTS tokens (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                token_no        TEXT NOT NULL UNIQUE,
                session_id      INTEGER,
                customer_id     INTEGER,
                customer_name   TEXT NOT NULL,
                customer_mobile TEXT NOT NULL,
                created_by_id   INTEGER,
                created_by_name TEXT NOT NULL,
                created_at      TEXT NOT NULL,
                file_count      INTEGER NOT NULL DEFAULT 0,
                files_json      TEXT NOT NULL DEFAULT '[]',
                item            TEXT NOT NULL DEFAULT ''
            )
        """)
        if not _column_exists(con, "tokens", "item"):
            con.execute("ALTER TABLE tokens ADD COLUMN item TEXT NOT NULL DEFAULT ''")
        con.execute("""
            CREATE INDEX IF NOT EXISTS idx_tokens_created ON tokens (created_at)
        """)
        con.commit()


def save_session(results: list[ImageInfo]) -> int:
    """Insert a new session + all image records. Returns session id."""
    init_db()
    now      = datetime.now()
    today    = now.date().isoformat()          # YYYY-MM-DD
    now_str  = now.isoformat(sep=" ", timespec="seconds")
    ok_count = sum(1 for r in results if r.status == "OK")

    with get_connection() as con:
        cur = con.execute(
            "INSERT INTO sessions (analysis_date, created_at, total_files, ok_files) "
            "VALUES (?, ?, ?, ?)",
            (today, now_str, len(results), ok_count),
        )
        session_id = cur.lastrowid

        rows = [
            (
                session_id, today, now_str,
                info.file_name, info.format,
                info.file_path,
                info.dpi_x, info.dpi_y,
                info.color_mode, info.color_mode_label,
                info.width_px, info.height_px,
                info.width_inch, info.height_inch,
                round(info.width_inch  / 12, 4) if info.width_inch  else 0.0,
                round(info.height_inch / 12, 4) if info.height_inch else 0.0,
                info.file_size_kb,
                info.status,
                None,
            )
            for info in results
        ]
        con.executemany("""
            INSERT INTO image_records
                (session_id, analysis_date, analysed_at,
                 file_name, file_format, file_path,
                 dpi_x, dpi_y, color_mode, color_mode_label,
                 width_px, height_px, width_inch, height_inch,
                 width_feet, height_feet, file_size_kb, status, moved_to)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, rows)
        con.commit()

    return session_id


def update_moved_to(session_id: int, file_name: str, moved_to: str,
                    new_name: str | None = None, orig_path: str | None = None):
    """
    Record destination when a file is moved.

    When ``new_name`` is given (the Item-prefixed file name), the record's
    ``file_name`` is updated too and the original name is preserved in
    ``original_name``.  ``orig_path`` (the file's path before the move)
    pinpoints the exact record, so two files that share a name within one
    session are both updated correctly.
    """
    with get_connection() as con:
        match = "session_id=? AND file_name=?"
        params: list = [session_id, file_name]
        if orig_path:
            match += " AND file_path=?"
            params.append(orig_path)
        if new_name and new_name != file_name:
            con.execute(
                "UPDATE image_records SET moved_to=?, status='Moved', "
                "file_name=?, original_name=COALESCE(original_name, ?) "
                f"WHERE {match}",
                (moved_to, new_name, file_name, *params),
            )
        else:
            con.execute(
                "UPDATE image_records SET moved_to=?, status='Moved' "
                f"WHERE {match}",
                (moved_to, *params),
            )
        con.commit()


def refresh_record_locations(records: list[dict]) -> int:
    """
    Re-check each record's original file path (and move destination) on disk.

    - File exists at its original path  -> status stays OK (moved_to cleared)
    - File exists at its moved_to path  -> status 'Moved'
    - File no longer found              -> status 'Moved'

    Only records that have a stored file_path (or moved_to) can be checked.
    Returns the number of records whose status changed.
    """
    updates: list[tuple[str, str | None, int]] = []

    for rec in records:
        file_path = rec.get("file_path")
        moved_to = rec.get("moved_to")
        old_status = rec.get("status") or ""

        if file_path and Path(file_path).exists():
            # Keep an ERROR (bad/unreadable image) as-is, otherwise it is present
            new_status = old_status if old_status == "ERROR" else "OK"
            new_moved = None
        elif moved_to and Path(moved_to).exists():
            new_status, new_moved = "Moved", moved_to
        elif file_path or moved_to:
            # Recorded somewhere, but no longer there -> treat as moved
            new_status, new_moved = "Moved", moved_to
        else:
            continue  # legacy record without a stored path — cannot check

        if new_status != old_status or (new_moved or None) != (moved_to or None):
            updates.append((new_status, new_moved, rec["id"]))

    if updates:
        with get_connection() as con:
            con.executemany(
                "UPDATE image_records SET status=?, moved_to=? WHERE id=?",
                updates,
            )
            con.commit()

    return len(updates)


# ── Query helpers ─────────────────────────────────────────────────────────────

def fetch_available_dates() -> list[str]:
    """Return distinct analysis dates (YYYY-MM-DD), newest first."""
    init_db()
    with get_connection() as con:
        rows = con.execute(
            "SELECT DISTINCT analysis_date FROM sessions ORDER BY analysis_date DESC"
        ).fetchall()
    return [r["analysis_date"] for r in rows]


def fetch_sessions_by_date(analysis_date: str | None = None) -> list[dict]:
    """
    Return sessions for a given date string ('YYYY-MM-DD').
    Pass None to get ALL sessions, newest first.
    """
    init_db()
    with get_connection() as con:
        if analysis_date:
            rows = con.execute(
                "SELECT * FROM sessions WHERE analysis_date=? ORDER BY id DESC",
                (analysis_date,),
            ).fetchall()
        else:
            rows = con.execute(
                "SELECT * FROM sessions ORDER BY id DESC"
            ).fetchall()
    return [dict(r) for r in rows]


def fetch_records_for_session(session_id: int) -> list[dict]:
    with get_connection() as con:
        rows = con.execute(
            "SELECT * FROM image_records WHERE session_id=? ORDER BY id",
            (session_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def fetch_records_by_date(analysis_date: str) -> list[dict]:
    """Return ALL image records for a given date (across all sessions that day)."""
    with get_connection() as con:
        rows = con.execute(
            "SELECT * FROM image_records WHERE analysis_date=? ORDER BY id",
            (analysis_date,),
        ).fetchall()
    return [dict(r) for r in rows]


# ═══════════════════════════════════════════════════════════════════════════════
#  Users / authentication
# ═══════════════════════════════════════════════════════════════════════════════

_PBKDF2_ITERATIONS = 200_000


def _hash_password(password: str, salt_hex: str | None = None) -> tuple[str, str]:
    """Return (hash_hex, salt_hex) using PBKDF2-HMAC-SHA256."""
    salt = bytes.fromhex(salt_hex) if salt_hex else secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, _PBKDF2_ITERATIONS
    )
    return digest.hex(), salt.hex()


def count_users() -> int:
    init_db()
    with get_connection() as con:
        return con.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"]


def count_admins() -> int:
    with get_connection() as con:
        return con.execute(
            "SELECT COUNT(*) AS n FROM users WHERE is_admin=1"
        ).fetchone()["n"]


def create_user(username: str, display_name: str, password: str,
                is_admin: bool = False) -> int:
    """Create a user. Raises ValueError when the username is already taken."""
    init_db()
    username = username.strip()
    display_name = display_name.strip()
    if not username or not display_name:
        raise ValueError("Username and display name are required.")
    if len(password) < 4:
        raise ValueError("Password must be at least 4 characters.")

    password_hash, salt = _hash_password(password)
    now = datetime.now().isoformat(sep=" ", timespec="seconds")
    try:
        with get_connection() as con:
            cur = con.execute(
                "INSERT INTO users "
                "(username, display_name, password_hash, salt, is_admin, created_at) "
                "VALUES (?,?,?,?,?,?)",
                (username, display_name, password_hash, salt,
                 1 if is_admin else 0, now),
            )
            con.commit()
            return cur.lastrowid
    except sqlite3.IntegrityError:
        raise ValueError("That username is already taken.")


def authenticate(username: str, password: str) -> dict | None:
    """Return the matching user (without secrets) or None."""
    init_db()
    with get_connection() as con:
        row = con.execute(
            "SELECT * FROM users WHERE username=? COLLATE NOCASE",
            (username.strip(),),
        ).fetchone()
    if not row:
        return None
    digest, _ = _hash_password(password, row["salt"])
    if not hmac.compare_digest(digest, row["password_hash"]):
        return None
    return {
        "id": row["id"],
        "username": row["username"],
        "display_name": row["display_name"],
        "is_admin": bool(row["is_admin"]),
    }


def list_users() -> list[dict]:
    init_db()
    with get_connection() as con:
        rows = con.execute(
            "SELECT id, username, display_name, is_admin, created_at "
            "FROM users ORDER BY display_name COLLATE NOCASE"
        ).fetchall()
    return [dict(r) for r in rows]


def delete_user(user_id: int):
    init_db()
    with get_connection() as con:
        con.execute("DELETE FROM users WHERE id=?", (user_id,))
        con.commit()


def update_user_password(user_id: int, password: str):
    init_db()
    if len(password) < 4:
        raise ValueError("Password must be at least 4 characters.")
    password_hash, salt = _hash_password(password)
    with get_connection() as con:
        con.execute(
            "UPDATE users SET password_hash=?, salt=? WHERE id=?",
            (password_hash, salt, user_id),
        )
        con.commit()


# ═══════════════════════════════════════════════════════════════════════════════
#  Customers + token slips
# ═══════════════════════════════════════════════════════════════════════════════

def fetch_customers() -> list[dict]:
    init_db()
    with get_connection() as con:
        rows = con.execute(
            "SELECT * FROM customers ORDER BY name COLLATE NOCASE"
        ).fetchall()
    return [dict(r) for r in rows]


def _upsert_customer(con, name: str, mobile: str, item: str = "") -> int:
    now = datetime.now().isoformat(sep=" ", timespec="seconds")
    row = con.execute(
        "SELECT id, item FROM customers WHERE mobile=?", (mobile,)
    ).fetchone()
    if row:
        # Remember the latest item for this customer, but never wipe it when
        # the current token does not specify one.
        new_item = item or (row["item"] or "")
        con.execute(
            "UPDATE customers SET name=?, item=? WHERE id=?",
            (name, new_item, row["id"]),
        )
        return row["id"]
    cur = con.execute(
        "INSERT INTO customers (name, mobile, item, created_at) VALUES (?,?,?,?)",
        (name, mobile, item or "", now),
    )
    return cur.lastrowid


def upsert_customer(name: str, mobile: str, item: str = "") -> int:
    with get_connection() as con:
        customer_id = _upsert_customer(
            con, name.strip(), mobile.strip(), item.strip()
        )
        con.commit()
        return customer_id


def _next_token_no(con) -> str:
    prefix = datetime.now().strftime("%y%m%d") + "-"
    row = con.execute(
        "SELECT token_no FROM tokens WHERE token_no LIKE ? "
        "ORDER BY id DESC LIMIT 1",
        (prefix + "%",),
    ).fetchone()
    seq = int(row["token_no"].rsplit("-", 1)[1]) + 1 if row else 1
    return f"{prefix}{seq:03d}"


def create_token(session_id: int | None, customer_name: str, customer_mobile: str,
                 created_by_id: int | None, created_by_name: str,
                 files: list[dict], item: str = "") -> dict:
    """
    Save a token slip and return its full snapshot.

    `files` is a list of {"file_name": ..., "color_mode": ...} dicts.
    `item` is the job/item name that prefixes the moved file names.
    """
    init_db()
    now = datetime.now().isoformat(sep=" ", timespec="seconds")
    files_json = json.dumps(files, ensure_ascii=False)
    item = (item or "").strip()

    with get_connection() as con:
        customer_id = _upsert_customer(con, customer_name.strip(),
                                       customer_mobile.strip(), item)
        token_no = _next_token_no(con)
        cur = con.execute(
            "INSERT INTO tokens "
            "(token_no, session_id, customer_id, customer_name, customer_mobile, "
            " created_by_id, created_by_name, created_at, file_count, files_json, "
            " item) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (token_no, session_id, customer_id, customer_name.strip(),
             customer_mobile.strip(), created_by_id, created_by_name,
             now, len(files), files_json, item),
        )
        con.commit()
        token_id = cur.lastrowid

    return {
        "id": token_id,
        "token_no": token_no,
        "session_id": session_id,
        "customer_id": customer_id,
        "customer_name": customer_name.strip(),
        "customer_mobile": customer_mobile.strip(),
        "created_by_id": created_by_id,
        "created_by_name": created_by_name,
        "created_at": now,
        "file_count": len(files),
        "files": files,
        "item": item,
    }


def fetch_tokens(limit: int = 200) -> list[dict]:
    """Newest tokens first, with their file snapshots decoded."""
    init_db()
    with get_connection() as con:
        rows = con.execute(
            "SELECT * FROM tokens ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    tokens = []
    for r in rows:
        d = dict(r)
        try:
            d["files"] = json.loads(d.pop("files_json") or "[]")
        except (TypeError, ValueError):
            d["files"] = []
        tokens.append(d)
    return tokens

