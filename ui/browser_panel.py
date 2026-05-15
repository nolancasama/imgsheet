from urllib.parse import quote
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLineEdit, QComboBox, QLabel
)
from PySide6.QtCore import QTimer

try:
    from PySide6.QtWebEngineWidgets import QWebEngineView
    _WEB_ENGINE_AVAILABLE = True
except ImportError:
    _WEB_ENGINE_AVAILABLE = False


class BrowserPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._pending_name = None
        self._load_timer = QTimer(self)
        self._load_timer.setSingleShot(True)
        self._load_timer.setInterval(500)
        self._load_timer.timeout.connect(self._do_load)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Top bar
        top_bar = QWidget()
        top_bar.setFixedHeight(36)
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(6, 4, 6, 4)
        top_layout.setSpacing(6)

        self._url_display = QLineEdit()
        self._url_display.setReadOnly(True)
        self._url_display.setPlaceholderText("Select a character to preview...")
        self._url_display.setStyleSheet("background: #f0f0f0; color: #555;")
        top_layout.addWidget(self._url_display, stretch=1)

        self._engine_combo = QComboBox()
        self._engine_combo.addItems(["DuckDuckGo", "Google", "Bing"])
        self._engine_combo.setFixedWidth(110)
        self._engine_combo.currentIndexChanged.connect(self._on_engine_changed)
        top_layout.addWidget(self._engine_combo)

        layout.addWidget(top_bar)

        if _WEB_ENGINE_AVAILABLE:
            self._view = QWebEngineView()
            layout.addWidget(self._view, stretch=1)
        else:
            fallback = QLabel(
                "Install PySide6-Addons for browser preview:\n"
                "pip install PySide6-Addons"
            )
            fallback.setAlignment(__import__("PySide6.QtCore", fromlist=["Qt"]).Qt.AlignCenter)
            fallback.setStyleSheet(
                "background: #fff8e1; color: #555; font-size: 13px; padding: 20px;"
            )
            layout.addWidget(fallback, stretch=1)
            self._view = None

    def _build_url(self, name: str) -> str:
        engine = self._engine_combo.currentText()
        encoded = quote(name)
        if engine == "Google":
            return f"https://www.google.com/search?q={encoded}&tbm=isch"
        elif engine == "Bing":
            return f"https://www.bing.com/images/search?q={encoded}"
        else:  # DuckDuckGo default
            return f"https://duckduckgo.com/?q={encoded}&ia=images&iax=images"

    def load_character(self, name: str):
        self._pending_name = name
        self._load_timer.start()

    def _do_load(self):
        if not self._pending_name:
            return
        name = self._pending_name
        url = self._build_url(name)
        self._url_display.setText(url)
        if self._view is not None:
            from PySide6.QtCore import QUrl
            self._view.load(QUrl(url))

    def _on_engine_changed(self):
        if self._pending_name:
            self._do_load()
