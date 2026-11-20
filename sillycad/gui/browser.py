"""Model browser: document, origin and the feature history."""

from collections.abc import Iterator

from PySide6.QtCore import QPoint, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QKeyEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QMenu,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
)

from sillycad.core.document import Document
from sillycad.core.features import Feature, Pad, Pocket, Revolve, SketchFeature
from sillycad.gui import theme
from sillycad.gui.icons import icon

_KIND = Qt.ItemDataRole.UserRole + 1
_KEY = Qt.ItemDataRole.UserRole + 2


class ModelBrowser(QTreeWidget):
    """Display the history while keeping all commands keyed by feature ID."""

    edit_requested = Signal(str)
    rename_requested = Signal(str, str)
    delete_requested = Signal(str)
    plane_requested = Signal(str)
    plane_selected = Signal(object)
    start_sketch_requested = Signal(str)
    offset_sketch_requested = Signal(str)
    planes_visibility_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._document_name = "Untitled"
        self._planes_visible = True
        self._origin_eye: QToolButton | None = None
        self.setColumnCount(2)
        self.setHeaderHidden(True)
        self.header().setStretchLastSection(False)
        self.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.header().setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self.setColumnWidth(1, 30)
        self.setEditTriggers(QAbstractItemView.EditTrigger.EditKeyPressed)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._menu)
        self.itemClicked.connect(self._clicked)
        self.itemDoubleClicked.connect(self._double_clicked)
        self.itemChanged.connect(self._renamed)

    def fill(self, doc: Document, errors: dict[str, str]) -> None:
        """Rebuild the browser, preserving expansion and selection where possible."""
        old_items = list(self._items())
        expanded = {item.data(0, _KEY) for item in old_items if item.isExpanded()}
        old_keys = {item.data(0, _KEY) for item in old_items}
        current = self.currentItem()
        selected_key = current.data(0, _KEY) if current else None
        self.blockSignals(True)
        self.clear()

        root = self._item(None, self._document_name, "document", "document", "document")
        origin = self._item(root, "Origin", "origin", "origin", "origin")
        origin.setToolTip(0, "Base planes, axes and the center point.")
        for plane in ("XY", "XZ", "YZ"):
            item = self._item(origin, f"{plane} Plane", "plane", f"plane:{plane}", "plane")
            item.setData(0, Qt.ItemDataRole.UserRole, plane)
            item.setToolTip(0, f"<b>{plane} Plane</b><br>Select it for Start 2D Sketch.")
        for axis in ("X", "Y", "Z"):
            self._item(origin, f"{axis} Axis", "axis", f"axis:{axis}", "axis")
        self._item(origin, "Center Point", "point", "origin:point", "point")

        self._origin_eye = QToolButton(self)
        self._origin_eye.setAutoRaise(True)
        self._origin_eye.clicked.connect(self.planes_visibility_requested.emit)
        self.setItemWidget(origin, 1, self._origin_eye)
        self._update_eye()

        names = {feature.id: feature.name for feature in doc.features}
        for feature in doc.features:
            if isinstance(feature, SketchFeature) and doc.users(feature.id):
                continue
            item = self._feature_item(root, feature, names, errors, f"feature:{feature.id}")
            if not isinstance(feature, SketchFeature):
                sketch = doc.find(feature.sketch_id)
                if isinstance(sketch, SketchFeature):
                    self._feature_item(
                        item, sketch, names, errors, f"feature:{feature.id}:sketch:{sketch.id}"
                    )

        for item in self._items():
            key = item.data(0, _KEY)
            if key in old_keys:
                item.setExpanded(key in expanded)
            else:
                item.setExpanded(item.childCount() > 0)
            if key == selected_key:
                self.setCurrentItem(item)
        self.blockSignals(False)

    def _item(
        self,
        parent: QTreeWidgetItem | None,
        text: str,
        kind: str,
        key: str,
        icon_name: str,
        *,
        error: bool = False,
    ) -> QTreeWidgetItem:
        item = QTreeWidgetItem([text, ""])
        item.setData(0, _KIND, kind)
        item.setData(0, _KEY, key)
        item.setIcon(0, icon(icon_name, error=error))
        if parent is None:
            self.addTopLevelItem(item)
        else:
            parent.addChild(item)
        return item

    def _feature_item(
        self,
        parent: QTreeWidgetItem,
        feature: Feature,
        names: dict[str, str],
        errors: dict[str, str],
        key: str,
    ) -> QTreeWidgetItem:
        icon_name = {
            SketchFeature: "sketch",
            Pad: "pad",
            Pocket: "pocket",
            Revolve: "revolve",
        }[type(feature)]
        kind = "sketch" if isinstance(feature, SketchFeature) else "feature"
        item = self._item(parent, feature.name, kind, key, icon_name, error=feature.id in errors)
        item.setData(0, Qt.ItemDataRole.UserRole, feature.id)
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
        description = _describe(feature, names)
        message = errors.get(feature.id)
        tip = f"{description}\nDouble-click to edit; F2 renames; Del deletes."
        item.setToolTip(0, message or tip)
        if message:
            item.setForeground(0, QColor(theme.ERROR))
        return item

    def _items(self) -> Iterator[QTreeWidgetItem]:
        def walk(item: QTreeWidgetItem) -> Iterator[QTreeWidgetItem]:
            yield item
            for index in range(item.childCount()):
                yield from walk(item.child(index))

        for index in range(self.topLevelItemCount()):
            yield from walk(self.topLevelItem(index))

    def set_document_name(self, name: str) -> None:
        """Update the document root without rebuilding the tree."""
        self._document_name = name
        if self.topLevelItemCount():
            self.topLevelItem(0).setText(0, name)

    def set_planes_visible(self, visible: bool) -> None:
        """Keep the Origin eye in sync with the shared visibility action."""
        self._planes_visible = visible
        self._update_eye()

    def _update_eye(self) -> None:
        if self._origin_eye is not None:
            action = "Hide" if self._planes_visible else "Show"
            self._origin_eye.setIcon(icon("sketches" if self._planes_visible else "hidden"))
            self._origin_eye.setToolTip(f"<b>{action} Origin</b><br>{action} planes and axes.")

    def select(self, fid: str) -> None:
        """Select a feature by its stable ID."""
        for item in self._items():
            if item.data(0, _KIND) in ("feature", "sketch") and _id(item) == fid:
                self.setCurrentItem(item)
                return

    def current_id(self) -> str | None:
        """Return the selected feature's ID, not an origin item's ID."""
        item = self.currentItem()
        if item and item.data(0, _KIND) in ("feature", "sketch"):
            return _id(item)
        return None

    def current_plane(self) -> str | None:
        """Return the selected base-plane name, if any."""
        item = self.currentItem()
        return _id(item) if item and item.data(0, _KIND) == "plane" else None

    def keyPressEvent(self, event: QKeyEvent) -> None:
        fid = self.current_id()
        if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace) and fid:
            self.delete_requested.emit(fid)
        else:
            super().keyPressEvent(event)

    def _clicked(self, item: QTreeWidgetItem, _column: int) -> None:
        plane = _id(item) if item.data(0, _KIND) == "plane" else None
        self.plane_selected.emit(plane)

    def _double_clicked(self, item: QTreeWidgetItem, _column: int) -> None:
        if item.data(0, _KIND) in ("feature", "sketch"):
            self.edit_requested.emit(_id(item))

    def _renamed(self, item: QTreeWidgetItem, column: int) -> None:
        if column == 0 and item.data(0, _KIND) in ("feature", "sketch"):
            fid, name = _id(item), item.text(0).strip()
            QTimer.singleShot(0, lambda: self.rename_requested.emit(fid, name))

    def _menu(self, pos: QPoint) -> None:
        item = self.itemAt(pos)
        if item is None:
            return
        self.setCurrentItem(item)
        kind = item.data(0, _KIND)
        menu = QMenu(self)
        if kind == "origin":
            action = "Hide" if self._planes_visible else "Show"
            menu.addAction(f"{action} Planes and Origin", self.planes_visibility_requested.emit)
        elif kind == "plane":

            def start_sketch() -> None:
                self.start_sketch_requested.emit(_id(item))

            menu.addAction("Start 2D Sketch", start_sketch)
            menu.addAction(
                "Start Sketch with Offset…", lambda: self.offset_sketch_requested.emit(_id(item))
            )
        elif kind in ("feature", "sketch"):
            fid = _id(item)
            menu.addAction(
                "Edit Sketch" if kind == "sketch" else "Edit Feature",
                lambda: self.edit_requested.emit(fid),
            )
            if kind == "sketch":
                menu.addAction("Change plane…", lambda: self.plane_requested.emit(fid))
            menu.addAction("Rename", lambda: self.editItem(item, 0))
            menu.addSeparator()
            menu.addAction("Delete", lambda: self.delete_requested.emit(fid))
        else:
            return
        menu.exec(self.viewport().mapToGlobal(pos))


def _id(item: QTreeWidgetItem) -> str:
    return item.data(0, Qt.ItemDataRole.UserRole)


def _describe(feature: Feature, names: dict[str, str]) -> str:
    if isinstance(feature, SketchFeature):
        offset = f", offset {feature.offset:g} mm" if feature.offset else ""
        where = "a picked face" if feature.plane == "Face" else feature.plane
        return f"Sketch on {where}{offset}"
    source = f" · {names.get(feature.sketch_id, '?')}"
    if isinstance(feature, Pad):
        extra = ", symmetric" if feature.symmetric else ", reversed" if feature.reversed else ""
        return f"Pad {feature.length:g} mm{extra}{source}"
    if isinstance(feature, Pocket):
        depth = "through all" if feature.through_all else f"{feature.length:g} mm"
        return f"Pocket {depth}{', reversed' if feature.reversed else ''}{source}"
    return f"Revolve {feature.angle:g}°{source}"
