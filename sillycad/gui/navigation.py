"""Compact viewport navigation controls."""

from PySide6.QtCore import QSize
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QToolButton, QVBoxLayout, QWidget


class NavigationBar(QWidget):
    """Keep the viewport's navigation actions beside the native OCCT window."""

    def __init__(self, actions: dict[str, QAction], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("navigationBar")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(3, 3, 3, 3)
        layout.setSpacing(2)
        for key in ("iso", "orbit", "pan", "zoom", "fit", "look_at"):
            button = QToolButton()
            button.setDefaultAction(actions[key])
            button.setIconSize(QSize(22, 22))
            button.setAutoRaise(True)
            layout.addWidget(button)
        layout.addStretch()
