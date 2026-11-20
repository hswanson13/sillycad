"""Ribbon and quick access controls, backed by the main window's actions."""

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QSizePolicy,
    QStackedWidget,
    QTabBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)


class Ribbon(QWidget):
    """File menu, Quick Access Toolbar and the part-environment ribbon."""

    def __init__(self, actions: dict[str, QAction], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("ribbon")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        quick = QWidget()
        quick.setObjectName("quickAccess")
        quick_layout = QHBoxLayout(quick)
        quick_layout.setContentsMargins(4, 1, 4, 1)
        quick_layout.setSpacing(1)
        for key in ("new", "open", "save", "undo", "redo", "export"):
            quick_layout.addWidget(_button(actions[key], icon_only=True))
        name = QLabel("SillyCAD")
        name.setObjectName("applicationName")
        quick_layout.addWidget(name)
        quick_layout.addStretch()
        layout.addWidget(quick)

        tabs_row = QHBoxLayout()
        tabs_row.setContentsMargins(0, 0, 0, 0)
        tabs_row.setSpacing(0)
        file_button = QToolButton()
        file_button.setObjectName("fileButton")
        file_button.setText("File")
        file_button.setToolTip("<b>File</b><br>Create, open, save or export a part.")
        file_menu = QMenu(file_button)
        file_menu.addActions([actions[key] for key in ("new", "open", "save", "save_as")])
        file_menu.addSeparator()
        export_menu = file_menu.addMenu("Export")
        export_stl = export_menu.addAction("STL…")
        export_stl.setIcon(actions["export"].icon())
        export_stl.setToolTip(actions["export"].toolTip())
        export_stl.triggered.connect(actions["export"].trigger)
        file_menu.addSeparator()
        file_menu.addAction(actions["quit"])
        file_button.setMenu(file_menu)
        file_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        tabs_row.addWidget(file_button)

        self.tabs = QTabBar()
        self.tabs.setObjectName("ribbonTabs")
        self.tabs.addTab("3D Model")
        self.tabs.addTab("View")
        tabs_row.addWidget(self.tabs)
        tabs_row.addStretch()
        layout.addLayout(tabs_row)

        self.pages = QStackedWidget()
        sketch_button = _button(actions["new_sketch"], large=True)
        sketch_menu = QMenu(sketch_button)
        sketch_menu.addAction(actions["sketch_offset"])
        sketch_button.setMenu(sketch_menu)
        sketch_button.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)
        self.extrude_button = _button(actions["extrude"], large=True)
        extrude_menu = QMenu(self.extrude_button)
        extrude_menu.addActions([actions["pad"], actions["pocket"]])
        self.extrude_button.setMenu(extrude_menu)
        self.extrude_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.pages.addWidget(
            _page(
                [
                    ("Sketch", [sketch_button]),
                    ("Create", [self.extrude_button, _button(actions["revolve"], large=True)]),
                    ("Work Features", [_button(actions["planes"], large=True)]),
                ]
            )
        )
        self.pages.addWidget(
            _page(
                [
                    ("Appearance", [_column(actions["shaded"], actions["wireframe"])]),
                    ("Visibility", [_column(actions["sketches"], actions["planes"])]),
                    (
                        "Navigate",
                        [
                            _button(actions["fit"], large=True),
                            _column(actions["front"], actions["top"]),
                            _column(actions["right"], actions["iso"]),
                            _column(actions["orbit"], actions["pan"], actions["zoom"]),
                            _button(actions["look_at"], large=True),
                        ],
                    ),
                ]
            )
        )
        self.tabs.currentChanged.connect(self.pages.setCurrentIndex)
        layout.addWidget(self.pages)

    def show_extrude_menu(self) -> None:
        """Open the Join/Cut menu for the Extrude keyboard shortcut."""
        self.tabs.setCurrentIndex(0)
        self.extrude_button.showMenu()


def _button(action: QAction, *, large: bool = False, icon_only: bool = False) -> QToolButton:
    button = QToolButton()
    button.setDefaultAction(action)
    button.setAutoRaise(True)
    button.setIconSize(QSize(32, 32) if large else QSize(20, 20))
    if icon_only:
        style = Qt.ToolButtonStyle.ToolButtonIconOnly
    elif large:
        style = Qt.ToolButtonStyle.ToolButtonTextUnderIcon
    else:
        style = Qt.ToolButtonStyle.ToolButtonTextBesideIcon
    button.setToolButtonStyle(style)
    if large:
        button.setMinimumHeight(72)
    return button


def _column(*actions: QAction) -> QWidget:
    widget = QWidget()
    layout = QVBoxLayout(widget)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(0)
    for action in actions:
        layout.addWidget(_button(action))
    layout.addStretch()
    return widget


def _page(panels: list[tuple[str, list[QWidget]]]) -> QWidget:
    page = QWidget()
    page.setObjectName("ribbonPage")
    layout = QHBoxLayout(page)
    layout.setContentsMargins(4, 3, 4, 2)
    layout.setSpacing(0)
    for title, widgets in panels:
        panel = QWidget()
        panel.setObjectName("ribbonPanel")
        panel.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Preferred)
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(2, 0, 2, 0)
        panel_layout.setSpacing(0)
        controls = QHBoxLayout()
        controls.setContentsMargins(2, 0, 2, 0)
        controls.setSpacing(2)
        for widget in widgets:
            controls.addWidget(widget)
        controls.addStretch()
        panel_layout.addLayout(controls, 1)
        caption = QLabel(title)
        caption.setObjectName("panelCaption")
        caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
        panel_layout.addWidget(caption)
        layout.addWidget(panel)
        separator = QFrame()
        separator.setObjectName("panelSeparator")
        separator.setFrameShape(QFrame.Shape.VLine)
        layout.addWidget(separator)
    layout.addStretch()
    return page
