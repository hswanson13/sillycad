"""Feature history panel. It only shows and asks; the main window does the work."""

from PySide6.QtCore import QPoint, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QKeyEvent
from PySide6.QtWidgets import QAbstractItemView, QHeaderView, QMenu, QTreeWidget, QTreeWidgetItem

from sillycad.core.document import Document
from sillycad.core.features import Feature, Pad, Pocket, Revolve, SketchFeature

ERROR_COLOR = QColor("#d62828")


class FeatureTree(QTreeWidget):
    """One row per feature: name (editable) and a short description."""

    edit_requested = Signal(str)
    rename_requested = Signal(str, str)
    delete_requested = Signal(str)
    plane_requested = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.setColumnCount(2)
        self.setHeaderHidden(True)
        self.setRootIsDecorated(False)
        self.header().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.setEditTriggers(QAbstractItemView.EditTrigger.EditKeyPressed)  # F2 renames
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._menu)
        self.itemDoubleClicked.connect(lambda item, _col: self.edit_requested.emit(_id(item)))
        self.itemChanged.connect(self._renamed)

    def fill(self, doc: Document, errors: dict[str, str]) -> None:
        """Show the document's features, marking failed ones in red."""
        current = self.current_id()
        self.blockSignals(True)
        self.clear()
        names = {f.id: f.name for f in doc.features}
        for f in doc.features:
            item = QTreeWidgetItem([f.name, _describe(f, names)])
            item.setData(0, Qt.ItemDataRole.UserRole, f.id)
            item.setData(1, Qt.ItemDataRole.UserRole, isinstance(f, SketchFeature))
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
            tip = "Double-click to edit. F2 renames, Del deletes."
            if f.id in errors:
                item.setText(1, f"⚠ {errors[f.id]}")
                tip = errors[f.id]
                for column in (0, 1):
                    item.setForeground(column, ERROR_COLOR)
            for column in (0, 1):
                item.setToolTip(column, tip)
            self.addTopLevelItem(item)
            if f.id == current:
                self.setCurrentItem(item)
        self.blockSignals(False)

    def select(self, fid: str) -> None:
        for row in range(self.topLevelItemCount()):
            if _id(self.topLevelItem(row)) == fid:
                self.setCurrentItem(self.topLevelItem(row))

    def current_id(self) -> str | None:
        item = self.currentItem()
        return _id(item) if item else None

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace) and self.currentItem():
            self.delete_requested.emit(_id(self.currentItem()))
        else:
            super().keyPressEvent(event)

    def _renamed(self, item: QTreeWidgetItem, column: int) -> None:
        if column == 0:
            fid, name = _id(item), item.text(0).strip()
            # Defer: the main window rebuilds the tree, which can't happen inside this signal.
            QTimer.singleShot(0, lambda: self.rename_requested.emit(fid, name))

    def _menu(self, pos: QPoint) -> None:
        item = self.itemAt(pos)
        if item is None:
            return
        fid = _id(item)
        menu = QMenu(self)
        menu.addAction("Edit…", lambda: self.edit_requested.emit(fid))
        menu.addAction("Rename", lambda: self.editItem(item, 0))
        if item.data(1, Qt.ItemDataRole.UserRole):  # it's a sketch
            menu.addAction("Change plane…", lambda: self.plane_requested.emit(fid))
        menu.addSeparator()
        menu.addAction("Delete", lambda: self.delete_requested.emit(fid))
        menu.exec(self.viewport().mapToGlobal(pos))


def _id(item: QTreeWidgetItem) -> str:
    return item.data(0, Qt.ItemDataRole.UserRole)


def _describe(f: Feature, names: dict[str, str]) -> str:
    if isinstance(f, SketchFeature):
        offset = f", offset {f.offset:g} mm" if f.offset else ""
        return f"sketch on {f.plane}{offset}"
    source = f" · {names.get(f.sketch_id, '?')}"
    if isinstance(f, Pad):
        extra = ", symmetric" if f.symmetric else ", reversed" if f.reversed else ""
        return f"pad {f.length:g} mm{extra}{source}"
    if isinstance(f, Pocket):
        depth = "through all" if f.through_all else f"{f.length:g} mm"
        return f"pocket {depth}{', reversed' if f.reversed else ''}{source}"
    if isinstance(f, Revolve):
        return f"revolve {f.angle:g}°{source}"
    return ""
