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

_BTN_STYLE = (
    "QPushButton { font-size: 11px; color: #ccc; background: #444; border: none; border-radius: 3px; }"
    "QPushButton:hover { background: #666; }"
)
_TOGGLE_STYLE = (
    "QPushButton { font-size: 11px; font-weight: bold; border-radius: 3px; padding: 2px 10px; border: none; }"
    "QPushButton:checked { background: #1976D2; color: white; }"
    "QPushButton:!checked { background: #444; color: #aaa; }"
)


class CardItem(QFrame):
    def __init__(self, path, char_idx, readonly=False, parent=None):
        super().__init__(parent)
        self.path = path
        self.char_idx = char_idx
        self._readonly = readonly
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

        if not self._readonly:
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
                b.setStyleSheet(_BTN_STYLE)
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
        self._back_paths = []      # mirrored back-sheet paths
        self._back_mode = False
        self._saved_front_data = []  # snapshot taken when entering back mode
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

        # Front / Back toggle (hidden until a back sheet exists)
        self._front_btn = QPushButton("Front")
        self._front_btn.setCheckable(True)
        self._front_btn.setChecked(True)
        self._front_btn.setFixedHeight(24)
        self._front_btn.setStyleSheet(_TOGGLE_STYLE)
        self._front_btn.clicked.connect(self._show_front)

        self._back_btn = QPushButton("Back")
        self._back_btn.setCheckable(True)
        self._back_btn.setChecked(False)
        self._back_btn.setFixedHeight(24)
        self._back_btn.setStyleSheet(_TOGGLE_STYLE)
        self._back_btn.clicked.connect(self._show_back)

        self._toggle_widget = QWidget()
        tw_layout = QHBoxLayout(self._toggle_widget)
        tw_layout.setContentsMargins(0, 0, 8, 0)
        tw_layout.setSpacing(3)
        tw_layout.addWidget(self._front_btn)
        tw_layout.addWidget(self._back_btn)
        self._toggle_widget.hide()
        tl.addWidget(self._toggle_widget)

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
        self._back_mode = False
        self._back_paths = getattr(result, 'back_image_paths', [])
        card_data = []

        for i, cr in enumerate(result.characters):
            used = set(cr.image_paths)
            self._pools[i] = [p for p in cr.candidate_paths if p not in used]
            for path in cr.image_paths:
                card_data.append((path, i))

        self._rebuild(card_data)
        self._info.setText(f"{len(card_data)} cards  —  hover for options")
        self._save_btn.setEnabled(True)

        if self._back_paths:
            self._front_btn.setChecked(True)
            self._back_btn.setChecked(False)
            self._toggle_widget.show()
        else:
            self._toggle_widget.hide()

    def _rebuild(self, card_data):
        while self._grid.count():
            item = self._grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._cards = []
        cols = self._options.cols if self._options else 5
        for idx, (path, char_idx) in enumerate(card_data):
            card = CardItem(path, char_idx, readonly=self._back_mode, parent=self._container)
            self._grid.addWidget(card, idx // cols, idx % cols)
            self._cards.append(card)

    def _reflow(self):
        cols = self._options.cols if self._options else 5
        for i, card in enumerate(self._cards):
            self._grid.addWidget(card, i // cols, i % cols)
        count = len(self._cards)
        self._info.setText(f"{count} cards  —  hover for options" if not self._back_mode
                           else f"{count} cards  —  back sheet preview")

    # ===== SHEET TOGGLE =====
    def _show_front(self):
        if not self._back_mode:
            return
        self._back_mode = False
        self._front_btn.setChecked(True)
        self._back_btn.setChecked(False)
        self._rebuild(self._saved_front_data)
        self._info.setText(f"{len(self._cards)} cards  —  hover for options")

    def _show_back(self):
        if self._back_mode or not self._back_paths:
            return
        self._saved_front_data = [(c.path, c.char_idx) for c in self._cards]
        self._back_mode = True
        self._front_btn.setChecked(False)
        self._back_btn.setChecked(True)
        self._rebuild([(p, -1) for p in self._back_paths])
        self._info.setText(f"{len(self._cards)} cards  —  back sheet (columns mirrored)")

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
        from pipeline import create_doc, make_sheet_filename
        opts = self._options
        rows = opts.rows if opts else 5
        cols = opts.cols if opts else 5
        paper = opts.paper_size if opts else "B4"
        paths = [c.path for c in self._cards]
        downloads = os.path.join(os.path.expanduser("~"), "Downloads")
        prompts = [cr.prompt for cr in self._result.characters] if self._result else []
        name = make_sheet_filename(prompts, datetime.now().strftime('%Y%m%d_%H%M%S'))
        out = os.path.join(downloads, name)
        try:
            create_doc(paths, out, rows, cols, paper)
            self._info.setText(f"Saved: {name}")
        except Exception as e:
            QMessageBox.critical(self, "Save Error", str(e))
