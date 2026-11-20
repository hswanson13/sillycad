"""The application's light-theme colors and stylesheet."""

ACCENT = "#0696d7"
ACCENT_HOVER = "#087db4"
ACCENT_LIGHT = "#dceff9"
WHITE = "#ffffff"
RIBBON = "#f5f5f5"
PANEL_LABEL = "#e6e6e6"
FRAME = "#d9d9d9"
BORDER = "#c4c4c4"
TEXT = "#2e2e2e"
MUTED = "#6b6b6b"
ERROR = "#d62828"
SUCCESS = "#268b43"

SKETCH_BACKGROUND = "#fbfcfe"
SKETCH_GRID_MINOR = "#edf0f5"
SKETCH_GRID_MAJOR = "#d5dbe5"
SKETCH_AXIS_X = "#e06666"
SKETCH_AXIS_Y = "#6aa84f"
SKETCH_FREE = "#1f2d3d"
SKETCH_SELECTED = "#ff7f00"
SKETCH_HOVER = "#2f80ed"
SKETCH_REFERENCE = "#9aa3b2"
SKETCH_DIMENSION_BACKGROUND = "#e6ffffff"

VIEW_SKETCH = (0.1, 0.3, 1.0)
VIEW_PLANES = {
    "XY": (0.25, 0.45, 0.95),
    "XZ": (0.25, 0.7, 0.3),
    "YZ": (0.9, 0.3, 0.3),
}

STYLESHEET = f"""
QMainWindow, QDockWidget {{
    background: {FRAME};
    color: {TEXT};
}}
QWidget#ribbon, QWidget#ribbonPage, QWidget#ribbonPanel {{
    background: {RIBBON};
}}
QWidget#quickAccess {{
    background: {PANEL_LABEL};
    border-bottom: 1px solid {BORDER};
}}
QLabel#applicationName {{
    color: {MUTED};
    padding-left: 8px;
}}
QToolButton {{
    color: {TEXT};
    background: transparent;
    border: 1px solid transparent;
    border-radius: 2px;
    padding: 3px;
}}
QToolButton:hover, QToolButton:checked {{
    background: {ACCENT_LIGHT};
    border-color: {ACCENT};
}}
QToolButton:pressed {{
    background: {PANEL_LABEL};
}}
QToolButton#fileButton {{
    background: {ACCENT};
    border: 0;
    color: {WHITE};
    font-weight: bold;
    min-width: 62px;
    padding: 6px 12px;
}}
QToolButton#fileButton:hover {{
    background: {ACCENT_HOVER};
}}
QToolButton#fileButton::menu-indicator {{
    image: none;
}}
QTabBar#ribbonTabs::tab {{
    background: {RIBBON};
    color: {TEXT};
    padding: 6px 16px;
    border: 1px solid transparent;
}}
QTabBar#ribbonTabs::tab:selected {{
    background: {WHITE};
    border-color: {BORDER};
    border-bottom-color: {WHITE};
}}
QLabel#panelCaption {{
    background: {PANEL_LABEL};
    color: {MUTED};
    padding: 2px 6px;
}}
QFrame#panelSeparator {{
    color: {BORDER};
}}
QDockWidget::title {{
    background: {PANEL_LABEL};
    color: {TEXT};
    padding: 5px 8px;
    border: 1px solid {BORDER};
    font-weight: bold;
}}
QTreeWidget, QListWidget {{
    background: {WHITE};
    color: {TEXT};
    border: 1px solid {BORDER};
    outline: none;
}}
QTreeWidget::item {{
    padding: 3px 0;
}}
QTreeWidget::item:selected, QListWidget::item:selected {{
    background: {ACCENT_LIGHT};
    color: {TEXT};
}}
QLabel#hintLabel {{
    color: {MUTED};
}}
QLabel#errorLabel, QLabel[sketchState="error"] {{
    color: {ERROR};
}}
QLabel[sketchState="done"] {{
    color: {SUCCESS};
}}
QLabel#sketchStatus {{
    font-weight: bold;
}}
QTabBar#documentTabs::tab {{
    background: {PANEL_LABEL};
    color: {TEXT};
    border: 1px solid {BORDER};
    padding: 4px 16px;
}}
QTabBar#documentTabs::tab:selected {{
    background: {WHITE};
    border-top: 2px solid {ACCENT};
}}
QStatusBar {{
    background: {RIBBON};
    color: {TEXT};
    border-top: 1px solid {BORDER};
}}
QMenu {{
    background: {WHITE};
    color: {TEXT};
    border: 1px solid {BORDER};
    padding: 4px;
}}
QMenu::item {{
    padding: 5px 24px 5px 8px;
}}
QMenu::item:selected {{
    background: {ACCENT_LIGHT};
}}
QToolTip {{
    background: {WHITE};
    color: {TEXT};
    border: 1px solid {BORDER};
    padding: 6px;
}}
"""
