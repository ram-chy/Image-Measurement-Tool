"""
Worker thread — runs image analysis without blocking the UI.
"""

from PyQt6.QtCore import QThread, pyqtSignal
from image_analyzer.core.analyzer import analyze_image, ImageInfo


class AnalysisWorker(QThread):
    """
    Runs image analysis in a background thread.

    Signals
    -------
    progress(int, int, str)   : current index, total, current filename
    result(ImageInfo)         : emitted after each file is processed
    finished_all(list)        : emitted when all files are done
    error(str)                : emitted on unexpected crash
    """
    progress     = pyqtSignal(int, int, str)
    result       = pyqtSignal(object)
    finished_all = pyqtSignal(list)
    error        = pyqtSignal(str)

    def __init__(self, file_paths: list[str], parent=None):
        super().__init__(parent)
        self.file_paths = file_paths
        self._results: list[ImageInfo] = []
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        try:
            total = len(self.file_paths)
            for idx, path in enumerate(self.file_paths):
                if self._cancelled:
                    break
                self.progress.emit(idx + 1, total, path)
                info = analyze_image(path)
                self._results.append(info)
                self.result.emit(info)
            self.finished_all.emit(self._results)
        except Exception as exc:
            self.error.emit(str(exc))
