"""
Database backup helpers.

The live database is a single SQLite file.  This module keeps one rotated
backup copy in a user-selected folder.  Backups are made with SQLite's online
backup API, so they are consistent even while the app is running.

Only the latest backup is kept: the previous backup file is replaced
atomically after the new copy has been verified.
"""

import json
import os
import sqlite3
from datetime import date
from pathlib import Path

from image_analyzer.core.database import _data_dir, _db_path

SETTINGS_FILE    = "settings.json"
BACKUP_FILENAME  = "ImageMeasurementTool_Data_Backup.db"
OLD_BACKUP_GLOB  = "ImageMeasurementTool_Data_Backup_*.db"


def _settings_path() -> Path:
    return _data_dir() / SETTINGS_FILE


def load_settings() -> dict:
    """Read settings.json; return an empty dict when it does not exist."""
    try:
        with open(_settings_path(), "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_settings(settings: dict) -> None:
    """Write settings.json atomically."""
    path = _settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(settings, fh, indent=2)
    os.replace(tmp, path)


def get_backup_settings() -> dict:
    settings = load_settings()
    return {
        "backup_dir":       str(settings.get("backup_dir") or "").strip(),
        "auto_backup":      bool(settings.get("auto_backup", False)),
        "last_backup_date": str(settings.get("last_backup_date") or ""),
    }


def set_backup_settings(backup_dir: str, auto_backup: bool) -> dict:
    """Save the backup folder / switch.  A folder change triggers a new backup."""
    settings = load_settings()
    new_dir = str(backup_dir or "").strip()
    old_dir = str(settings.get("backup_dir") or "").strip()
    if new_dir != old_dir:
        settings.pop("last_backup_date", None)
    settings["backup_dir"] = new_dir
    settings["auto_backup"] = bool(auto_backup)
    save_settings(settings)
    return get_backup_settings()


def backup_path(backup_dir: str | Path) -> Path:
    return Path(backup_dir).expanduser() / BACKUP_FILENAME


def create_backup(backup_dir: str | Path | None = None) -> Path:
    """
    Create a verified, consistent backup and replace the previous backup.

    Raises ValueError if no folder was given, or RuntimeError if verification
    fails.  The old backup is left untouched when anything goes wrong.
    """
    if backup_dir is None:
        backup_dir = get_backup_settings()["backup_dir"]
    folder_text = str(backup_dir or "").strip()
    if not folder_text:
        raise ValueError("Please choose a backup folder first.")

    folder = Path(folder_text).expanduser()
    folder.mkdir(parents=True, exist_ok=True)

    final_path = folder / BACKUP_FILENAME
    temp_path  = folder / (BACKUP_FILENAME + ".tmp")

    try:
        temp_path.unlink(missing_ok=True)

        # SQLite's backup API produces a consistent copy while the app is open.
        source = sqlite3.connect(_db_path())
        try:
            target = sqlite3.connect(str(temp_path))
            try:
                with target:
                    source.backup(target)
            finally:
                target.close()
        finally:
            source.close()

        check = sqlite3.connect(str(temp_path))
        try:
            result = check.execute("PRAGMA integrity_check").fetchone()
        finally:
            check.close()
        if not result or str(result[0]).lower() != "ok":
            raise RuntimeError("The backup copy did not pass its integrity check.")

        # Replace the previous backup atomically.
        os.replace(temp_path, final_path)

        # Clean up any date-stamped backups from older versions.
        for old in folder.glob(OLD_BACKUP_GLOB):
            try:
                old.unlink()
            except OSError:
                pass

        settings = load_settings()
        settings["backup_dir"] = str(folder)
        settings.setdefault("auto_backup", True)
        settings["last_backup_date"] = date.today().isoformat()
        save_settings(settings)
        return final_path

    except Exception:
        try:
            temp_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def maybe_run_daily_backup() -> Path | None:
    """Run one backup per day when automatic backups are enabled."""
    settings = get_backup_settings()
    if not settings["auto_backup"] or not settings["backup_dir"]:
        return None
    target = backup_path(settings["backup_dir"])
    if (settings["last_backup_date"] == date.today().isoformat()
            and target.exists()):
        return None
    return create_backup(settings["backup_dir"])
