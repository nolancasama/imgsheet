import os
from PySide6.QtWidgets import (
    QWidget, QScrollArea, QGridLayout, QLabel, QPushButton,
    QVBoxLayout, QHBoxLayout, QFrame, QFileDialog,
    QMessageBox, QSizePolicy
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap

CARD_W = 120
CARD_H = 171  # 7:10 ratio


class CardItem(QFrame):
    def __init__(self, path, char_idx, parent=None):
        super().__init__(parent)
        self.path = path
        self.char_idx = char_idx
        self.setFrameShape(QFrame.StyledPanel)
        self.setStyleSheet("QFrame { background: #2a2a3e; border-radius: 4px; }")
        self._setup()

    def _setup(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(3, 3, 3, 3)
        layout.setSpacing(3)

        self._img_label = QLabel()
        self._img_label.setFixedSize(CARD_W, CARD_H)
        self._img_label.setAlignment(Qt.AlignCenter)
        self._img_label.setStyleSheet("background: #111; border-radius: 3px;")
        self._load(self.path)
        layout.addWidget(self._img_label)

        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(0, 0, 0, 0)
        btn_row.setSpacing(2)
        for text, tip, slot in [
            ("⟳", "Swap with next candidate", self._on_swap),
            ("✕", "Remove card",              self._on_delete),
            ("↑", "Upload custom image",      self._on_upload),
        ]:
            b = QPushButton(text)
            b.setToolTip(tip)
            b.setFixedHeight(20)
            b.setStyleSheet("QPushButton { font-size: 11px; color: #ccc; background: #444; border: none; border-radius: 3px; }"
                            "QPushButton:hover { background: #666; }")
            b.clicked.connect(slot)
            btn_row.addWidget(b)
        layout.addLayout(btn_row)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

    def _load(self, path):
        px = QPixmap(path)
        if not px.isNull():
            px = px.scaled(CARD_W, CARD_H, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self._img_label.setPixmap(px)
        self.path = path

    def update_path(self, path):
        self._load(path)

    # --- slots wired by CardGridPanel via lambda ---
    def _on_swap(self):
        grid = self._find_grid()
        if grid:
            grid.swap_card(self)

    def _on_delete(self):
        grid = self._find_grid()
        if grid:
            grid.delete_card(self)

    def _on_upload(self):
        grid = self._find_grid()
        if grid:
            grid.upload_card(self)

    def _find_grid(self):
        p = self.parent()
        while p:
            if isinstance(p, CardGridPanel):
                return p
            p = p.parent()
        return None


class CardGridPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._options = None
        self._result = None
        self._pools = {}
        self._cards = []
        self._setup_ui()

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Top bar
        top = QWidget()
        top.setFixedHeight(38)
        top.setStyleSheet("background: #1e1e2e; border-bottom: 1px solid #333;")
        tl = QHBoxLayout(top)
        tl.setContentsMargins(10, 4, 10, 4)
        self._info = QLabel("No sheet generated yet")
        self._info.setStyleSheet("color: #ccc; font-size: 12px;")
        tl.addWidget(self._info)
        tl.addStretch()
        self._save_btn = QPushButton("Save .docx")
        self._save_btn.setEnabled(False)
        self._save_btn.clicked.connect(self._on_save)
        tl.addWidget(self._save_btn)
        root.addWidget(top)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { background: #1a1a2e; border: none; }")
        self._container = QWidget()
        self._container.setStyleSheet("background: #1a1a2e;")
        self._grid = QGridLayout(self._container)
        self._grid.setSpacing(8)
        self._grid.setContentsMargins(10, 10, 10, 10)
        self._grid.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        scroll.setWidget(self._container)
        root.addWidget(scroll, stretch=1)

    def load_result(self, result, options):
        self._result = result
        self._options = options
        self._pools = {}
        card_data = []

        for i, cr in enumerate(result.characters):
            used = set(cr.image_paths)
            self._pools[i] = [p for p in cr.candidate_paths if p not in used]
            for path in cr.image_paths:
                card_data.append((path, i))

        self._rebuild(card_data)
        self._info.setText(f"{len(card_data)} cards  —  hover for options")
        self._save_btn.setEnabled(True)

    def _rebuild(self, card_data):
        while self._grid.count():
            item = self._grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._cards = []
        cols = self._options.cols if self._options else 5
        for idx, (path, char_idx) in enumerate(card_data):
            card = CardItem(path, char_idx, parent=self._container)
            self._grid.addWidget(card, idx // cols, idx % cols)
            self._cards.append(card)

    def _reflow(self):
        cols = self._options.cols if self._options else 5
        for i, card in enumerate(self._cards):
            self._grid.addWidget(card, i // cols, i % cols)
        self._info.setText(f"{len(self._cards)} cards")

    # ===== CARD OPERATIONS =====
    def swap_card(self, card):
        pool = self._pools.get(card.char_idx, [])
        if not pool:
            QMessageBox.information(self, "No more candidates",
                                    "All candidate images for this character have been used.")
            return
        old = card.path
        new = pool.pop(0)
        pool.append(old)
        card.update_path(new)

    def delete_card(self, card):
        if card not in self._cards:
            return
        self._cards.remove(card)
        if card.char_idx >= 0:
            self._pools.setdefault(card.char_idx, []).insert(0, card.path)
        self._grid.removeWidget(card)
        card.deleteLater()
        self._reflow()

    def upload_card(self, card):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Image", "",
            "Images (*.jpg *.jpeg *.png *.webp *.bmp)"
        )
        if path:
            card.update_path(path)
            card.char_idx = -1

    def _on_save(self):
        if not self._cards:
            return
        from datetime import datetime
        from pipeline import create_doc
        opts = self._options
        rows = opts.rows if opts else 5
        cols = opts.cols if opts else 5
        paper = opts.paper_size if opts else "B4"
        paths = [c.path for c in self._cards]
        downloads = os.path.join(os.path.expanduser("~"), "Downloads")
        name = f"output_{datetime.now().strftime('%Y%m%d_%H%M%S')}.docx"
        out = os.path.join(downloads, name)
        try:
            create_doc(paths, out, rows, cols, paper)
            self._info.setText(f"Saved: {name}")
        except Exception as e:
            QMessageBox.critical(self, "Save Error", str(e))
