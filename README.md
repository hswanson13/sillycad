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

Click **Start 2D Sketch**, then pick a visible base plane or flat face in the viewport, or a plane under **Origin** in the Model browser. Alternatively, select the plane or face first, then start the sketch. Its editor opens directly; a face outline appears as a snappable guide. To specify an offset, use **Sketch with Offset…** from the Start 2D Sketch dropdown or a browser plane's context menu. The Origin eye hides or shows the planes and axes.

Select a plane, flat face, or sketch and use **Look At** on the View ribbon, navigation bar, or viewport marking menu to face it directly. While a sketch plane is being requested, `Esc` or right-click cancels the command.

Consumed sketches are nested under their features; other sketches remain at the top level. Double-click to edit, `F2` to rename, `Del` to delete, or right-click for more. Failed features are red with the reason in a tooltip; the last good body stays on screen. The document tab and window title show `*` for unsaved changes.

**Sketch editor**

After choosing a sketch plane, the separate 2D editor opens. Pick a tool to draw. To constrain, select items and then click a constraint button (or press its key). Every button's tooltip shows its key and what to select. Double-click a dimension to change it.

| Draw | Key | Constrain | Key | Dimension | Key |
|---|---|---|---|---|---|
| Select / cancel | `Esc` | Coincident | `I` | Distance | `D` |
| Point | `P` | Horizontal | `H` | Horizontal distance | `Shift+H` |
| Line | `L` | Vertical | `V` | Vertical distance | `Shift+V` |
| Arc | `A` | Parallel | `Shift+P` | Angle | `Shift+A` |
| Circle | `C` | Perpendicular | `N` | Radius | `R` |
| Construction | `G` | Equal | `E` | Diameter | `Shift+D` |
| Delete | `Del` | Point on line | `O` | | |
| Undo / Redo | `Ctrl+Z` / `Ctrl+Shift+Z` | Tangent | `T` | | |
| Fit view | `Home` | Midpoint | `M` | | |
| Finish | `Ctrl+Enter` | Fix | `F` | | |

Colors: dark = still free, green = fully constrained, red = conflicting or redundant constraints. Red rings mark profile problems such as loose ends.

## Test and lint

```bash
pytest
ruff check .
ruff format .
```

## Files

Parts are saved as `.sillycad` files: readable JSON with a `format_version`, holding the feature list (sketches with their geometry and constraints, pads, pockets, revolves). Units are millimetres and degrees. The 3D shape isn't stored; it's rebuilt when the file opens. STL is export-only (binary).

## Layout

- `sillycad/core/` has the document, sketches, solver, features, file I/O and STL export. It has no Qt imports and is fully testable headless.
- `sillycad/gui/` is the PySide6 interface built on top of the core.
- `tests/` holds the headless pytest tests.

Progress is tracked in [progress.md](progress.md).
