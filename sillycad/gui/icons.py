"""Small original line icons for the ribbon and model browser."""

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtSvg import QSvgRenderer

from sillycad.gui import theme

_SHAPES = {
    "new": '<path d="M7 3h12l6 6v20H7z M19 3v6h6 M12 18h8 M16 14v8"/>',
    "open": '<path d="M3 9h10l3 3h13l-4 14H3z M3 9V6h10l3 3"/>',
    "save": '<path d="M5 4h20l3 3v21H5z M10 4v9h12V4 M10 28V18h13v10"/>',
    "undo": '<path d="M12 9 5 15l7 6 M6 15h13c6 0 8 3 8 8"/>',
    "redo": '<path d="m20 9 7 6-7 6 M26 15H13c-6 0-8 3-8 8"/>',
    "export": '<path d="M5 18v9h22v-9 M16 4v16 M10 14l6 6 6-6"/>',
    "sketch": '<path d="M5 6h22v20H5z M8 22 21 9l4 4-13 13-5 1z M19 11l4 4"/>',
    "pad": '<path d="m6 11 11-6 10 5-11 6z M6 11v12l10 5 11-6V10 M16 16v12"/>',
    "pocket": (
        '<path d="m5 10 11-5 11 5v13l-11 5-11-5z M5 10l11 5 11-5 M16 15v13 M12 9l4-2 4 2-4 2z"/>'
    ),
    "revolve": (
        '<path d="M16 3v26 M11 7h8v18h-8z M5 17c0-5 5-8 11-8s11 3 11 8 '
        'M23 14l4 3 2-4 M27 21c-3 4-7 5-11 5-5 0-9-2-11-5"/>'
    ),
    "planes": '<path d="M4 23 19 14l9 5-15 9z M4 17 19 8l9 5-15 9z M4 11 19 2l9 5-15 9z"/>',
    "sketches": (
        '<path d="M4 16c3-5 7-8 12-8s9 3 12 8c-3 5-7 8-12 8S7 21 4 16z '
        'M16 12a4 4 0 1 0 0 8 4 4 0 0 0 0-8z"/>'
    ),
    "hidden": '<path d="M4 16c3-5 7-8 12-8s9 3 12 8c-3 5-7 8-12 8S7 21 4 16z M5 5l22 22"/>',
    "fit": '<path d="M4 11V4h7 M21 4h7v7 M28 21v7h-7 M11 28H4v-7 M10 10h12v12H10z"/>',
    "front": '<path d="M6 6h20v20H6z M10 10h12v12H10z"/>',
    "top": '<path d="m5 11 11-6 11 6-11 6z M5 11v10l11 6 11-6V11 M16 17v10"/>',
    "right": '<path d="m5 10 11-5 11 5v12l-11 5-11-5z M16 5v22 M16 15l11-5"/>',
    "iso": '<path d="m5 10 11-6 11 6v12l-11 6-11-6z M5 10l11 6 11-6 M16 16v12"/>',
    "shaded": '<path d="m5 10 11-6 11 6v12l-11 6-11-6z M5 10l11 6 11-6 M16 16v12"/>',
    "wireframe": (
        '<path d="m5 10 11-6 11 6v12l-11 6-11-6z M5 10l11 6 11-6 M16 16v12 M5 22l11-6 11 6"/>'
    ),
    "document": '<path d="M7 3h12l6 6v20H7z M19 3v6h6 M11 15h10 M11 19h10 M11 23h7"/>',
    "origin": '<path d="M7 25h18 M7 25V7 M7 25l12-12 M22 11l-3 2 1-4"/>',
    "plane": '<path d="m4 12 13-7 11 6-13 7z M4 12v8l11 7 13-8v-8 M15 18v9"/>',
    "axis": '<path d="M5 25 25 5 M19 5h6v6"/>',
    "point": '<circle cx="16" cy="16" r="4"/>',
    "pan": (
        '<path d="M12 16V7a2 2 0 0 1 4 0v7-9a2 2 0 0 1 4 0v9-7a2 2 0 0 1 4 0'
        'v9-4a2 2 0 0 1 4 0v8c0 5-3 9-9 9h-3c-3 0-5-2-7-5l-4-6a2 2 0 0 1 3-2l4 4"/>'
    ),
    "zoom": '<circle cx="13" cy="13" r="8"/><path d="m19 19 8 8 M9 13h8 M13 9v8"/>',
    "orbit": (
        '<circle cx="16" cy="16" r="8"/><path d="M5 11c3-4 9-6 15-5 M23 4l3 3-4 2 '
        'M27 21c-3 4-9 6-15 5 M9 28l-3-3 4-2"/>'
    ),
    "look_at": (
        '<path d="M3 16c3-5 8-8 13-8s10 3 13 8c-3 5-8 8-13 8S6 21 3 16z '
        'M16 12a4 4 0 1 0 0 8 4 4 0 0 0 0-8z"/>'
    ),
    "select": '<path d="M6 3v23l6-6 4 9 4-2-4-9 9-1z"/>',
    "line": '<path d="M5 25 27 7"/><circle cx="5" cy="25" r="2"/><circle cx="27" cy="7" r="2"/>',
    "circle": '<circle cx="16" cy="16" r="11"/><circle cx="16" cy="16" r="1"/>',
    "arc": '<path d="M5 20A11 11 0 0 1 26 10 M16 20h9 M16 20V9"/><circle cx="16" cy="20" r="1"/>',
    "rectangle": (
        '<path d="M5 7h22v18H5z"/><circle cx="5" cy="7" r="2"/><circle cx="27" cy="25" r="2"/>'
    ),
    "dimension": '<path d="M6 8v16 M26 8v16 M6 16h20 M10 13l-4 3 4 3 M22 13l4 3-4 3"/>',
    "constraint": '<path d="M5 10h22 M5 22h22 M12 6v20 M20 6v20"/>',
    "construction": '<path d="M4 25 11 18 M15 14l4-4 M23 6l5-4"/>',
    "finish": '<path d="m5 17 7 7L27 7"/>',
    "delete": '<path d="M7 9h18 M12 9V5h8v4 M9 9l2 18h10l2-18 M14 13v10 M18 13v10"/>',
}


def icon(name: str, *, error: bool = False) -> QIcon:
    """Render an original icon, optionally with a failure badge."""
    stroke = theme.SUCCESS if name == "finish" else theme.ACCENT_HOVER
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32" '
        f'fill="none" stroke="{stroke}" stroke-width="2" '
        f'stroke-linecap="round" stroke-linejoin="round">{_SHAPES[name]}</svg>'
    )
    pixmap = QPixmap(32, 32)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    QSvgRenderer(QByteArray(svg.encode())).render(painter)
    if error:
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(theme.ERROR))
        painter.drawEllipse(19, 19, 13, 13)
        painter.setPen(QPen(QColor(theme.WHITE), 2))
        painter.drawLine(25, 22, 25, 26)
        painter.drawPoint(25, 29)
    painter.end()
    return QIcon(pixmap)
