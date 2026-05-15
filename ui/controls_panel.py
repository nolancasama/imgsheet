from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton, QProgressBar
from PySide6.QtCore import Qt, Signal


class ControlsPanel(QWidget):
    generate_requested = Signal(list, object)

    def __init__(self, get_prompts, get_options, parent=None):
        super().__init__(parent)
        self._get_prompts = get_prompts
        self._get_options = get_options
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        self._gen_button = QPushButton("Generate")
        self._gen_button.setFixedHeight(44)
        self._gen_button.setStyleSheet(
            "QPushButton { font-size: 15px; font-weight: bold; background: #1976D2; color: white; border-radius: 6px; }"
            "QPushButton:hover { background: #1565C0; }"
            "QPushButton:disabled { background: #90CAF9; color: #e0e0e0; }"
        )
        self._gen_button.clicked.connect(self._on_generate_clicked)
        layout.addWidget(self._gen_button)

        self._status_label = QLabel("Ready")
        self._status_label.setWordWrap(True)
        self._status_label.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self._status_label.setStyleSheet("color: #333; font-size: 12px;")
        layout.addWidget(self._status_label)

        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 0)
        self._progress_bar.setFixedHeight(6)
        self._progress_bar.setTextVisible(False)
        self._progress_bar.hide()
        layout.addWidget(self._progress_bar)

        layout.addStretch(1)

    def _on_generate_clicked(self):
        prompts = self._get_prompts()
        options = self._get_options()
        self.generate_requested.emit(prompts, options)

    def set_generating(self, active: bool):
        self._gen_button.setEnabled(not active)
        if active:
            self._progress_bar.show()
        else:
            self._progress_bar.hide()

    def set_status(self, message: str):
        self._status_label.setText(message)
