# SillyCAD

A minimal parametric 3D CAD app in Python. It uses pythonocc-core for geometry, PySide6 for the UI and planegcs to solve sketch constraints.

## Setup

You need conda. [Miniforge](https://github.com/conda-forge/miniforge) is recommended.

```bash
conda env create -f environment.yml
conda activate sillycad
```

To update the environment after `environment.yml` changes:

```bash
conda env update -f environment.yml --prune
```

## Run

```bash
python -m sillycad
```

**3D view controls**

| Action | Mouse / key |
|---|---|
| Orbit | Left-drag, or choose Orbit on the navigation bar |
| Pan | Middle-drag, or choose Pan and left-drag |
| Zoom | Wheel / right-drag, or choose Zoom and left-drag |
| Fit all | `F` / `Home` |
| Home view (isometric + fit) | `0` / `F6` |
| Wireframe / shaded | `W` / `S` |

Click the ViewCube for standard orientations. Right-click the viewport for the marking menu; press `Esc` or click outside it to dismiss it.

Open a file directly with `python -m sillycad part.sillycad`.

**Main window**

| Action | Key |
|---|---|
| New / Open / Save / Save As | `Ctrl+N` / `Ctrl+O` / `Ctrl+S` / `Ctrl+Shift+S` |
| Export STL (asks for quality) | `Ctrl+E` |
| Start 2D Sketch / Extrude / Revolve | `N` / `E` / `R` |
| Join (Pad) / Cut (Pocket) | `P` / `O` |
| Undo / Redo | `Ctrl+Z` / `Ctrl+Shift+Z` or `Ctrl+Y` |
| Front / Top / Right / Home view | `1` / `2` / `3` / `0` or `F6` |
| Zoom All | `F` / `Home` |

Use **File** for document commands and the Quick Access Toolbar for common file commands and undo/redo. The **3D Model** ribbon has Start 2D Sketch, Extrude (Join or Cut), Revolve, and plane visibility; **View** has display, visibility, and navigation controls.

Click **Start 2D Sketch**, then pick a visible base plane or flat face in the viewport, or a plane under **Origin** in the Model browser. Alternatively, select the plane or face first, then start the sketch. The sketch opens in the main viewport with the part behind it; a face outline appears as a snappable guide. To specify an offset, use **Sketch with Offset…** from the Start 2D Sketch dropdown or a browser plane's context menu. The Origin eye hides or shows the planes and axes.

Select a plane, flat face, or sketch and use **Look At** on the View ribbon, navigation bar, or viewport marking menu to face it directly. While a sketch plane is being requested, `Esc` or right-click cancels the command.

Consumed sketches are nested under their features; other sketches remain at the top level. Double-click to edit, `F2` to rename, `Del` to delete, or right-click for more. Failed features are red with the reason in a tooltip; the last good body stays on screen. The document tab and window title show `*` for unsaved changes.

**Sketch environment**

The camera turns toward the sketch plane and the contextual **Sketch** ribbon appears. Use **Rectangle** and drag between opposite corners to make four connected, horizontal/vertical lines. Lines chain by clicking successive points; right-click ends the chain. Scroll or right-drag to zoom, middle-drag to pan, and Shift+middle-drag to orbit; `F5` looks back at the sketch plane.

Select geometry, then click **Dimension** or press `D` to infer a suitable dimension and enter its value at the label. Double-click a dimension to edit it. Explicit dimensions remain in the Dimension dropdown. The constraint-button grid is hidden initially; click **Constraints** in the ribbon to show it. Click **Constraints** in the sketch-status panel to open the constraint list. Constraint glyphs can also be clicked and deleted; `F8` shows them and `F9` hides them. Right-click for the sketch marking menu when not drawing.

Undo and redo work locally while sketching. **Finish Sketch** commits the complete edit as one main-window undo step; Cancel Sketch is in the marking menu. Colors: dark = still free, green = fully constrained, red = conflicting or redundant constraints. Red rings mark profile problems such as loose ends.

| Draw | Key | Constrain | Key | Dimension | Key |
|---|---|---|---|---|---|
| Select / cancel | `Esc` | Coincident | `I` | Smart Dimension | `D` |
| Point | `P` | Horizontal | `H` | Horizontal distance | `Shift+H` |
| Line | `L` | Vertical | `V` | Vertical distance | `Shift+V` |
| Arc | `A` | Parallel | `Shift+P` | Angle | `Shift+A` |
| Circle | `C` | Perpendicular | `N` | Radius | `R` |
| Construction | `G` | Equal | `E` | Diameter | `Shift+D` |
| Delete | `Del` | Point on line | `O` | | |
| Undo / Redo | `Ctrl+Z` / `Ctrl+Shift+Z` or `Ctrl+Y` | Tangent | `T` | | |
| Fit view | `Home` | Midpoint | `M` | | |
| Finish | `Ctrl+Enter` | Fix | `F` | Look at sketch | `F5` |
| Show / hide glyphs | `F8` / `F9` | | | | |

Overlapping circles currently produce an intersecting-profile error. Choosing an individual overlapping region to extrude is deferred: it needs modeling and file-format changes.

## Test and lint

```bash
pytest
ruff check .
ruff format --check .
```

The native-window integration test is opt-in and needs an active X11/XWayland display:

```bash
SILLYCAD_NATIVE_GUI_TESTS=1 QT_QPA_PLATFORM=xcb pytest -q tests/test_sketch_native.py
```

## Files

Parts are saved as `.sillycad` files: readable JSON with a `format_version`, holding the feature list (sketches with their geometry and constraints, pads, pockets, revolves). Units are millimetres and degrees. The 3D shape isn't stored; it's rebuilt when the file opens. STL is export-only (binary).

## Layout

- `sillycad/core/` has the document, sketches, solver, features, file I/O and STL export. It has no Qt imports and is fully testable headless.
- `sillycad/gui/` is the PySide6 interface built on top of the core.
- `tests/` holds the headless pytest tests and an opt-in native-window integration test.

Progress is tracked in [progress.md](progress.md).
