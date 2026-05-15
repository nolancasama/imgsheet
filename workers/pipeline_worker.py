import threading
from PySide6.QtCore import QThread, Signal


class PipelineWorker(QThread):
    progress = Signal(str)
    finished_ok = Signal(object)
    failed = Signal(str)
    cancelled_partial = Signal(list, list)

    def __init__(self, prompts, options):
        super().__init__()
        self.prompts = prompts
        self.options = options
        self._cancel_event = threading.Event()

    def cancel(self):
        self._cancel_event.set()

    def run(self):
        try:
            from pipeline import run_pipeline, PipelineCancelled
            result = run_pipeline(self.prompts, self.options, self.progress.emit, self._cancel_event)
            self.finished_ok.emit(result)
        except PipelineCancelled as e:
            self.cancelled_partial.emit(e.partial_images, e.character_results)
        except Exception as e:
            self.failed.emit(str(e))
