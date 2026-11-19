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
