"""Tema oscuro azul marino."""

ESTILO = """
QWidget { background: #0f1729; color: #dbe2ef; font-size: 10pt; }
QToolBar { background: #131d33; border: none; padding: 6px; spacing: 6px; }
QToolButton { padding: 6px 10px; border-radius: 6px; }
QToolButton:hover { background: #1f2d4d; }
QLabel#titulo { font-size: 11pt; font-weight: 600; color: #ffffff; }
QLabel#vacio { color: #7a8599; font-size: 12pt; background: #0a1020; }
QLineEdit, QListWidget, QTreeWidget, QGroupBox {
    background: #131d33; border: 1px solid #24334f; border-radius: 6px;
}
QLineEdit { padding: 5px 8px; }
QLineEdit:focus { border-color: #3d7bfd; }
QListWidget::item, QTreeWidget::item { padding: 4px; }
QListWidget::item:selected, QTreeWidget::item:selected { background: #2a4a8c; color: #ffffff; }
QListWidget::item:hover, QTreeWidget::item:hover { background: #1c2a47; }
QHeaderView::section { background: #172340; color: #9fb0cc; border: none; padding: 5px; }
QGroupBox { margin-top: 14px; padding-top: 6px; }
QGroupBox::title { subcontrol-origin: margin; left: 10px; color: #9fb0cc; }
QPushButton {
    background: #1f2d4d; border: 1px solid #2c3f66; border-radius: 6px; padding: 6px 12px;
}
QPushButton:hover { background: #2a3d66; }
QPushButton:pressed { background: #3d7bfd; }
QPushButton:disabled, QWidget:disabled { color: #56627a; }
QSlider::groove:horizontal { height: 6px; background: #24334f; border-radius: 3px; }
QSlider::sub-page:horizontal { background: #3d7bfd; border-radius: 3px; }
QSlider::handle:horizontal {
    background: #ffffff; width: 14px; margin: -5px 0; border-radius: 7px;
}
QSplitter::handle { background: #0b1222; width: 3px; }
QStatusBar { background: #131d33; color: #9fb0cc; }
QScrollBar:vertical { background: #0f1729; width: 10px; }
QScrollBar::handle:vertical { background: #2c3f66; border-radius: 5px; min-height: 30px; }
QScrollBar::add-line, QScrollBar::sub-line { height: 0; }
"""
