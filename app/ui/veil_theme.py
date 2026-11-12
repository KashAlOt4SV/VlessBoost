"""VEIL's opaque native desktop palette. No full-window effects or web view."""
BG = "#0b0f14"
PANEL = "#111821"
BLUE = "#82baff"
MUTED = "#8190a4"
GREEN = "#6ee7bd"

STYLE = """
QMainWindow, QDialog { background: #0b0f14; }
QWidget { color: #e9eff8; font-family: 'Segoe UI'; font-size: 13px; }
QLabel { background: transparent; }
QLabel[kind='eyebrow'] { color: #82baff; font-size: 10px; font-weight: 600; letter-spacing: 2px; }
QLabel[kind='muted'] { color: #8190a4; font-size: 12px; }
QLabel[kind='title'] { font-size: 27px; font-weight: 600; letter-spacing: -0.6px; }
QLabel[kind='section'] { font-size: 14px; font-weight: 600; }
QLabel[kind='metric'] { font-size: 30px; font-weight: 500; }
QLabel[kind='badge'] { color: #9ac8ff; background: #192b40; border: 1px solid #25405c; border-radius: 5px; padding: 5px 9px; font-size: 10px; }
QFrame#sidebar { background: #0e141b; border-right: 1px solid #202a36; }
QFrame#topbar { background: #0e141b; border-bottom: 1px solid #202a36; }
QFrame#card { background: #111821; border: 1px solid #23303e; border-radius: 12px; }
QFrame#engine { background: #111c25; border: 1px solid #284337; border-radius: 10px; }
QPushButton { background: #192331; border: 1px solid #2a3b50; border-radius: 7px; padding: 9px 15px; font-weight: 500; }
QPushButton:hover { background: #22354b; border-color: #52789d; }
QPushButton:pressed { background: #152131; border-color: #82baff; }
QPushButton:focus-visible { border: 1px solid #82baff; }
QPushButton:disabled { color: #657186; background: #131c26; border-color: #23303e; }
QPushButton[primary='true'] { color: #091522; background: #82baff; border: 1px solid #a4cdff; }
QPushButton[primary='true']:hover { background: #a1cdff; }
QPushButton[primary='true']:pressed { background: #65a5f1; }
QPushButton[primary='true']:disabled { background: #304968; border-color: #304968; color: #8b9caf; }
QPushButton[nav='true'] { text-align: left; padding: 12px 16px; background: transparent; border: 1px solid transparent; color: #91a0b4; }
QPushButton[nav='true']:hover { background: #151f2b; color: #e9eff8; }
QPushButton[nav='true']:checked { color: #acd2ff; background: #17283b; border-color: #29415b; }
QLineEdit, QPlainTextEdit { background: #0b1118; border: 1px solid #283748; border-radius: 7px; padding: 10px; selection-background-color: #284e78; }
QLineEdit:focus, QPlainTextEdit:focus { border-color: #6ca7eb; }
QScrollArea { background: transparent; border: none; }
QScrollArea > QWidget > QWidget { background: transparent; }
QScrollBar:vertical { background: transparent; width: 7px; margin: 3px 0; }
QScrollBar::handle:vertical { background: #2b3c50; border-radius: 3px; min-height: 30px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
QTableWidget { background: #111821; alternate-background-color: #131d28; border: 1px solid #23303e; border-radius: 10px; gridline-color: #23303e; selection-background-color: #1d3047; }
QTableWidget::item { padding: 8px 14px; border: none; }
QHeaderView::section { background: #111821; color: #8190a4; border: none; border-bottom: 1px solid #23303e; padding: 12px 14px; text-align: left; font-size: 11px; }
QComboBox { background: #192331; border: 1px solid #2a3b50; border-radius: 6px; padding: 8px 14px; }
QComboBox QAbstractItemView { background: #192331; selection-background-color: #284e78; }
QToolTip { color: #e9eff8; background: #1b2939; border: 1px solid #39516c; padding: 5px; }
QMenu { background: #111821; border: 1px solid #30435a; padding: 5px; }
QMenu::item { padding: 8px 24px; }
QMenu::item:selected { background: #22354b; }
"""
