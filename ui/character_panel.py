from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox,
    QCheckBox, QLineEdit, QPlainTextEdit,
    QLabel, QPushButton, QProgressBar, QComboBox
)
from PySide6.QtCore import Qt, Signal, QTimer
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pipeline import PipelineOptions


class CharacterPanel(QWidget):
    characterSelected = Signal(str)
    generate_requested = Signal(list, object)
    cancel_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.setInterval(500)
        self._preview_timer.timeout.connect(self._on_cursor_settled)

        self._text_edit.textChanged.connect(self._preview_timer.start)
        self._text_edit.cursorPositionChanged.connect(self._preview_timer.start)

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        header = QLabel("Characters")
        header.setStyleSheet("font-weight: bold; font-size: 13px;")
        layout.addWidget(header)

        self._text_edit = QPlainTextEdit()
        self._text_edit.setPlaceholderText(
            "Enter character names, comma or newline separated...\n\nMove cursor to a name to preview it."
        )
        layout.addWidget(self._text_edit, stretch=1)

        options_group = QGroupBox("Options")
        options_layout = QVBoxLayout(options_group)
        options_layout.setSpacing(6)

        self._pdf_check = QCheckBox("Export PDF (requires OpenOffice/LibreOffice)")
        self._claude_check = QCheckBox("Filter with Claude Vision")
        self._randomize_check = QCheckBox("Randomize results")
        options_layout.addWidget(self._pdf_check)
        options_layout.addWidget(self._claude_check)
        options_layout.addWidget(self._randomize_check)

        self._engine_combo = QComboBox()
        self._engine_combo.addItems(["Google (SerpAPI)", "Brave", "DuckDuckGo (free)"])
        self._engine_combo.setCurrentIndex(0)
        options_layout.addWidget(self._engine_combo)

        layout_row = QHBoxLayout()
        self._layout_combo = QComboBox()
        self._layout_combo.addItems(["5×5 (25)", "4×4 (16)", "3×3 (9)", "2×2 (4)"])
        self._paper_combo = QComboBox()
        self._paper_combo.addItems(["B4", "A4", "Letter", "A3"])
        layout_row.addWidget(self._layout_combo)
        layout_row.addWidget(self._paper_combo)
        options_layout.addLayout(layout_row)

        self._email_edit = QLineEdit()
        self._email_edit.setPlaceholderText("Send to email (optional)")
        options_layout.addWidget(self._email_edit)

        layout.addWidget(options_group)

        self._gen_button = QPushButton("Generate")
        self._gen_button.setFixedHeight(44)
        self._gen_button.setStyleSheet(
            "QPushButton { font-size: 15px; font-weight: bold; background: #1976D2; color: white; border-radius: 6px; }"
            "QPushButton:hover { background: #1565C0; }"
            "QPushButton:disabled { background: #90CAF9; color: #e0e0e0; }"
        )
        self._gen_button.clicked.connect(self._on_generate_clicked)

        self._cancel_button = QPushButton("Cancel")
        self._cancel_button.setFixedHeight(44)
        self._cancel_button.setStyleSheet(
            "QPushButton { font-size: 13px; font-weight: bold; background: #c62828; color: white; border-radius: 6px; }"
            "QPushButton:hover { background: #b71c1c; }"
        )
        self._cancel_button.clicked.connect(self.cancel_requested.emit)
        self._cancel_button.hide()

        btn_row = QHBoxLayout()
        btn_row.addWidget(self._gen_button)
        btn_row.addWidget(self._cancel_button)
        layout.addLayout(btn_row)

        self._status_label = QLabel("Ready")
        self._status_label.setWordWrap(True)
        self._status_label.setAlignment(Qt.AlignCenter)
        self._status_label.setStyleSheet("color: #333; font-size: 12px;")
        layout.addWidget(self._status_label)

        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 0)
        self._progress_bar.setFixedHeight(6)
        self._progress_bar.setTextVisible(False)
        self._progress_bar.hide()
        layout.addWidget(self._progress_bar)

    def _on_cursor_settled(self):
        name = self._current_line()
        if name:
            self.characterSelected.emit(name)

    def _on_generate_clicked(self):
        self.generate_requested.emit(self.get_prompts(), self.get_options())

    def _current_line(self) -> str:
        return self._text_edit.textCursor().block().text().strip().strip(",")

    def get_prompts(self) -> list:
        text = self._text_edit.toPlainText()
        parts = [p.strip() for p in text.replace(",", "\n").splitlines() if p.strip()]
        return parts[:25]

    def get_options(self) -> PipelineOptions:
        engine = ["serpapi", "brave", "ddg"][self._engine_combo.currentIndex()]
        rows, cols = [(5,5),(4,4),(3,3),(2,2)][self._layout_combo.currentIndex()]
        paper = ["B4", "A4", "Letter", "A3"][self._paper_combo.currentIndex()]
        return PipelineOptions(
            use_claude=self._claude_check.isChecked(),
            export_pdf=self._pdf_check.isChecked(),
            randomize=self._randomize_check.isChecked(),
            search_engine=engine,
            send_email_to=self._email_edit.text().strip(),
            rows=rows,
            cols=cols,
            paper_size=paper,
        )

    def set_generating(self, active: bool):
        self._gen_button.setEnabled(not active)
        self._pdf_check.setEnabled(not active)
        self._claude_check.setEnabled(not active)
        self._randomize_check.setEnabled(not active)
        self._engine_combo.setEnabled(not active)
        self._layout_combo.setEnabled(not active)
        self._paper_combo.setEnabled(not active)
        self._email_edit.setEnabled(not active)
        self._text_edit.setEnabled(not active)
        if active:
            self._cancel_button.show()
            self._progress_bar.show()
        else:
            self._cancel_button.hide()
            self._progress_bar.hide()

    def set_status(self, message: str):
        self._status_label.setText(message)

    def selected_character(self) -> str:
        return self._current_line()
