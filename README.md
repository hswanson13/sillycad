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
| Orbit | Left-drag |
| Pan | Middle-drag |
| Zoom | Wheel or right-drag |
| Fit all | `F` |
| Wireframe / shaded | `W` / `S` |

**Main window**

| Action | Key |
|---|---|
| New Sketch / Pad / Pocket / Revolve | `N` / `P` / `O` / `R` |
| Undo / Redo | `Ctrl+Z` / `Ctrl+Shift+Z` |
| Front / Top / Right / Iso view | `1` / `2` / `3` / `0` |
| Fit all | `F` |

In the feature tree: double-click to edit (sketches reopen in the sketch editor), `F2` to rename, `Del` to delete, right-click for more. Failed features are red, with the reason shown; the last good body stays on screen.

**Sketch editor**

Click **New Sketch**, pick a plane, and a 2D editor opens. Pick a tool to draw. To constrain, select items and then click a constraint button (or press its key). Every button's tooltip shows its key and what to select. Double-click a dimension to change it.

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

## Layout

- `sillycad/core/` has the document, sketches, solver, features, file I/O and STL export. It has no Qt imports and is fully testable headless.
- `sillycad/gui/` is the PySide6 interface built on top of the core.
- `tests/` holds the headless pytest tests.

Progress is tracked in [progress.md](progress.md).
