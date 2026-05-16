import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtWidgets import QMainWindow, QSplitter, QStackedWidget
from PySide6.QtCore import Qt

from ui.character_panel import CharacterPanel
from ui.browser_panel import BrowserPanel
from ui.card_grid_panel import CardGridPanel


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Image Sheet Generator")
        self.resize(1100, 750)
        self.setMinimumSize(700, 500)

        self.character_panel = CharacterPanel()
        self.browser_panel   = BrowserPanel()
        self.card_panel      = CardGridPanel()

        self._right = QStackedWidget()
        self._right.addWidget(self.browser_panel)  # 0 — search preview
        self._right.addWidget(self.card_panel)     # 1 — generated cards

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self.character_panel)
        splitter.addWidget(self._right)
        splitter.setSizes([340, 760])
        splitter.setChildrenCollapsible(False)
        self.setCentralWidget(splitter)

        self.character_panel.characterSelected.connect(self._on_char_selected)
        self.character_panel.generate_requested.connect(self._on_generate)
        self.character_panel.cancel_requested.connect(self._on_cancel)

        self._worker = None
        self._current_options = None

    def _on_char_selected(self, name):
        self._right.setCurrentIndex(0)
        self.browser_panel.load_character(name)

    def _on_generate(self, prompts, options):
        if not prompts:
            self.character_panel.set_status("Error: Enter at least one character name.")
            return
        self._current_options = options
        self._right.setCurrentIndex(0)  # show browser while running
        self.character_panel.set_generating(True)
        self.character_panel.set_status("Starting...")

        from workers.pipeline_worker import PipelineWorker
        self._worker = PipelineWorker(prompts, options)
        self._worker.progress.connect(self.character_panel.set_status)
        self._worker.finished_ok.connect(self._on_done)
        self._worker.failed.connect(self._on_failed)
        self._worker.cancelled_partial.connect(self._on_cancelled_partial)
        self._worker.start()

    def _on_done(self, result):
        self.character_panel.set_generating(False)
        self.card_panel.load_result(result, self._current_options)
        self._right.setCurrentIndex(1)
        self.character_panel.set_status("Done! Click Save .docx in the preview panel.")

    def _on_cancel(self):
        if self._worker:
            self._worker.cancel()
            self.character_panel.set_status("Cancelling...")

    def _on_failed(self, err):
        self.character_panel.set_generating(False)
        self.character_panel.set_status("Cancelled." if err == "Cancelled." else f"Error: {err}")

    def _on_cancelled_partial(self, partial_images, character_results):
        self.character_panel.set_generating(False)
        if not partial_images:
            self.character_panel.set_status("Cancelled.")
            return
        from PySide6.QtWidgets import QMessageBox
        reply = QMessageBox.question(
            self,
            "Build partial sheet?",
            f"{len(partial_images)} image(s) collected before cancel.\n\n"
            "Build a sheet now, filling remaining slots with spread duplicates?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._build_partial(character_results)
        else:
            self.character_panel.set_status("Cancelled.")

    def _build_partial(self, character_results):
        from datetime import datetime
        from pipeline import fill_to_count_spread, create_doc, PipelineResult
        opts = self._current_options
        rows  = opts.rows       if opts else 5
        cols  = opts.cols       if opts else 5
        paper = opts.paper_size if opts else "B4"
        filled = fill_to_count_spread(character_results, rows * cols)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        downloads = os.path.join(os.path.expanduser("~"), "Downloads")
        out = os.path.join(downloads, f"output_{timestamp}.docx")
        try:
            create_doc(filled, out, rows, cols, paper)
            # Show partial result in card panel
            from pipeline import CharacterResult as CR
            fake_result = PipelineResult(
                output_docx=out, output_pdf=None,
                characters=[CR(prompt="partial", image_paths=filled, candidate_paths=[])]
            )
            self.card_panel.load_result(fake_result, opts)
            self._right.setCurrentIndex(1)
            self.character_panel.set_status(f"Partial sheet ready — {len(filled)} cards.")
        except Exception as e:
            self.character_panel.set_status(f"Error: {e}")
