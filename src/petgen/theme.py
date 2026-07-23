from __future__ import annotations

from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import QApplication, QWidget

# Color Tokens
COLOR_PRIMARY = "#6366f1"
COLOR_PRIMARY_HOVER = "#4f46e5"
COLOR_PRIMARY_LIGHT = "#eeef2ff"
COLOR_TEXT_MAIN = "#0f172a"
COLOR_TEXT_MUTED = "#64748b"
COLOR_BG_CARD = "#ffffff"
COLOR_BG_APP = "#f8fafc"
COLOR_BORDER = "#e2e8f0"
COLOR_BORDER_FOCUS = "#818cf8"
COLOR_DANGER = "#ef4444"
COLOR_DANGER_BG = "#fef2f2"

MAIN_STYLESHEET = """
QWidget {
    font-family: -apple-system, "SF Pro Display", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
    font-size: 13px;
    color: #0f172a;
}

QDialog {
    background-color: #f8fafc;
}

/* Tabs */
QTabWidget::pane {
    border: 1px solid #e2e8f0;
    border-radius: 12px;
    background-color: #ffffff;
    top: -1px;
}

QTabBar::tab {
    background-color: #f1f5f9;
    color: #64748b;
    border: 1px solid #e2e8f0;
    border-bottom: none;
    border-top-left-radius: 8px;
    border-top-right-radius: 8px;
    padding: 8px 16px;
    margin-right: 4px;
    font-weight: 500;
}

QTabBar::tab:selected {
    background-color: #ffffff;
    color: #4f46e5;
    border-color: #cbd5e1;
    border-bottom: 2px solid #6366f1;
    font-weight: 600;
}

QTabBar::tab:hover:!selected {
    background-color: #e2e8f0;
    color: #334155;
}

/* LineEdit, TextEdit, SpinBox, ComboBox */
QLineEdit, QTextEdit, QSpinBox, QDoubleSpinBox, QComboBox {
    background-color: #ffffff;
    border: 1px solid #cbd5e1;
    border-radius: 8px;
    padding: 6px 10px;
    color: #0f172a;
    selection-background-color: #818cf8;
}

QLineEdit:focus, QTextEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {
    border: 2px solid #6366f1;
    padding: 5px 9px;
}

QLineEdit:hover, QTextEdit:hover, QSpinBox:hover, QDoubleSpinBox:hover, QComboBox:hover {
    border-color: #94a3b8;
}

QComboBox::drop-down {
    border: none;
    width: 24px;
}

QComboBox::down-arrow {
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid #64748b;
    margin-right: 8px;
}

/* Buttons */
QPushButton {
    background-color: #f1f5f9;
    color: #1e293b;
    border: 1px solid #cbd5e1;
    border-radius: 8px;
    padding: 6px 14px;
    font-weight: 500;
}

QPushButton:hover {
    background-color: #e2e8f0;
    border-color: #94a3b8;
    color: #0f172a;
}

QPushButton:pressed {
    background-color: #cbd5e1;
}

QPushButton:disabled {
    background-color: #f8fafc;
    color: #94a3b8;
    border-color: #e2e8f0;
}

/* Primary Action Button */
QPushButton[accent="primary"] {
    background-color: #4f46e5;
    color: #ffffff;
    border: none;
    font-weight: 600;
}

QPushButton[accent="primary"]:hover {
    background-color: #4338ca;
}

QPushButton[accent="primary"]:pressed {
    background-color: #3730a3;
}

/* Danger Action Button */
QPushButton[accent="danger"] {
    background-color: #fef2f2;
    color: #dc2626;
    border: 1px solid #fca5a5;
}

QPushButton[accent="danger"]:hover {
    background-color: #fee2e2;
    color: #b91c1c;
    border-color: #f87171;
}

/* CheckBox */
QCheckBox {
    spacing: 8px;
    color: #1e293b;
}

QCheckBox::indicator {
    width: 18px;
    height: 18px;
    border-radius: 4px;
    border: 1px solid #cbd5e1;
    background-color: #ffffff;
}

QCheckBox::indicator:hover {
    border-color: #6366f1;
}

QCheckBox::indicator:checked {
    background-color: #4f46e5;
    border-color: #4f46e5;
}

/* Scroll Area & ScrollBars */
QScrollArea {
    border: 1px solid #e2e8f0;
    border-radius: 10px;
    background-color: #f8fafc;
}

QScrollBar:vertical {
    border: none;
    background: #f1f5f9;
    width: 8px;
    border-radius: 4px;
    margin: 2px;
}

QScrollBar::handle:vertical {
    background: #cbd5e1;
    border-radius: 4px;
    min-height: 20px;
}

QScrollBar::handle:vertical:hover {
    background: #94a3b8;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}

/* QMenu (Tray / Context Menu) */
QMenu {
    background-color: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 10px;
    padding: 6px;
}

QMenu::item {
    padding: 6px 20px;
    border-radius: 6px;
    color: #1e293b;
}

QMenu::item:selected {
    background-color: #eef2ff;
    color: #4f46e5;
}

QMenu::separator {
    height: 1px;
    background: #e2e8f0;
    margin: 4px 8px;
}
"""


def apply_theme(target: QWidget | QApplication) -> None:
    """Apply global theme QSS to a widget or application instance."""
    target.setStyleSheet(MAIN_STYLESHEET)
