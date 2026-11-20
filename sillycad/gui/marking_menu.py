"""Viewport marking menu backed by the same actions as the ribbon."""

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QGridLayout,
    QLabel,
    QMenu,
    QToolButton,
    QWidget,
    QWidgetAction,
)


class MarkingMenu(QMenu):
    """Offer the main 3D commands around the pointer and additional commands below."""

    def __init__(
        self, actions: dict[str, QAction], parent: QWidget | None = None, *, sketch: bool = False
    ) -> None:
        super().__init__(parent)
        controls = QWidget()
        controls.setObjectName("markingControls")
        grid = QGridLayout(controls)
        grid.setContentsMargins(4, 4, 4, 4)
        grid.setSpacing(1)
        positions = (
            (
                ("line", 0, 1),
                ("circle", 0, 2),
                ("arc", 1, 2),
                ("smart_dimension", 2, 2),
                ("construction", 2, 1),
                ("finish", 2, 0),
                ("undo", 1, 0),
                ("delete", 0, 0),
            )
            if sketch
            else (
                ("new_sketch", 0, 1),
                ("extrude", 0, 2),
                ("revolve", 1, 2),
                ("fit", 2, 2),
                ("iso", 2, 1),
                ("look_at", 2, 0),
                ("undo", 1, 0),
                ("planes", 0, 0),
            )
        )
        for key, row, column in positions:
            action = actions[key]
            button = QToolButton()
            button.setIcon(action.icon())
            button.setText(action.text())
            button.setToolTip(action.toolTip())
            button.setIconSize(QSize(24, 24))
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
            button.setCheckable(action.isCheckable())
            button.setChecked(action.isChecked())
            button.setEnabled(action.isEnabled())
            button.clicked.connect(self.close)
            button.clicked.connect(action.trigger)
            grid.addWidget(button, row, column)
        center = QLabel("SillyCAD")
        center.setAlignment(Qt.AlignmentFlag.AlignCenter)
        grid.addWidget(center, 1, 1)
        group = QWidgetAction(self)
        group.setDefaultWidget(controls)
        self.addAction(group)
        self.addSeparator()
        if sketch:
            for key in (
                "select",
                "rectangle",
                "point",
                "show_constraints",
                "cancel",
                "coincident",
                "horizontal",
                "vertical",
                "parallel",
                "perpendicular",
                "equal",
                "point_on_line",
                "tangent",
                "midpoint",
                "fix",
                "distance",
                "distance_x",
                "distance_y",
                "angle",
                "radius",
                "diameter",
            ):
                self.addAction(actions[key])
            return
        for key in (
            "sketch_offset",
            "pad",
            "pocket",
            "sketches",
            "shaded",
            "wireframe",
            "front",
            "top",
            "right",
        ):
            self.addAction(actions[key])
        file_menu = self.addMenu("File")
        file_menu.addActions(
            [actions[key] for key in ("new", "open", "save", "save_as", "export", "quit")]
        )
