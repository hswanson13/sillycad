<div style="font-family: 'Comic Sans MS', 'Comic Sans', 'Comic Neue', 'Chalkboard SE', cursive;">

# SillyCAD Progress

**Where we are:** M2 is done. Waiting for you to try it (see "How to try it" below).

**Needs you:** run the M2 tests and tell me they pass. Then I'll start M3.

Legend: ✅ done · 🔨 in progress · ⬜ not started

---

## ✅ M1: It runs

**You'll be able to:** open the app, spin a test box around in 3D, and export it to STL.

- [x] `environment.yml`, `pyproject.toml` (ruff + pytest), README
- [x] Main window with the 3D viewer showing a box (UI in Comic Sans)
- [x] Export STL
- [x] Test: STL file is non-empty with a plausible triangle count

## ✅ M2: Sketch brain (no GUI yet)

**You'll be able to:** run `pytest` and watch the solver work.

- [x] Sketch model: point, line, arc, circle, construction flag, stable IDs
- [x] All constraints and dimensions from the spec, with friendly "you picked the wrong things" messages
- [x] Solver wrapper (planegcs): solve, degrees of freedom, conflicts, redundancies
- [x] A failed solve leaves the geometry untouched (last good state)
- [x] Tests: a rectangle solves to the right coordinates, and a conflict gets caught (15 tests total)

## ⬜ M3: Sketch editor

**You'll be able to:** draw and constrain a sketch with the mouse.

- [ ] 2D editor with grid, zoom/pan and snapping
- [ ] Draw lines, arcs, circles and points, with a construction toggle
- [ ] Constraint buttons + keyboard shortcuts
- [ ] Dimension labels (double-click to edit)
- [ ] Live solve while dragging, DOF in the status bar
- [ ] Colors: normal = free, green = fully constrained, red = conflict
- [ ] Clear messages for open or self-intersecting profiles

## ⬜ M4: Solids

**You'll be able to:** turn sketches into real parts.

- [ ] Pad, Pocket, Revolve
- [ ] Feature tree: edit, rename, delete, errors shown
- [ ] Recompute from history when anything changes
- [ ] Base planes, origin axes, sketch wires (show/hide)
- [ ] Toolbar: Fit All, front / top / right / iso views
- [ ] Tests: pad = 8000 mm³, pocket and revolve volumes

## ⬜ M5: Save and polish

**You'll be able to:** save, reopen, undo anything, and export with settings.

- [ ] Save / Open (`.sillycad` file, plain JSON)
- [ ] Undo / redo for every edit
- [ ] STL export dialog (quality settings with good defaults)
- [ ] Test: save, open, recompute gives the same volume

---

## How to try it

### M1

```bash
conda activate sillycad
cd ~/repos/sillycad
python -m sillycad
```

If `conda` isn't found, run `eval "$(~/miniforge3/bin/conda shell.bash hook)"` first. You can also skip activating and run `~/miniforge3/envs/sillycad/bin/python -m sillycad`.

1. A brown 40 × 20 × 10 box should appear.
2. Left-drag to orbit, middle-drag to pan, scroll to zoom. Press `F` to fit the box in view again.
3. Press `W` for wireframe and `S` for shaded.
4. Choose **File → Export STL…** and save it. The status bar shows the triangle count (12 for a box).
5. Open the STL in any viewer or slicer. It should be a 40 × 20 × 10 mm box.
6. Run `pytest`. It should show 2 passed.

### M2

There's no GUI change in this milestone. It's the solver behind the sketcher.

1. Run `pytest -v`. All 15 should pass. The names say what each one checks (rectangle, conflict, tangent, and so on).
2. Optional: play with it in Python:

```python
from sillycad.core.sketch import Sketch, ORIGIN
from sillycad.core.solver import solve

s = Sketch()
line = s.add_line(1, 1, 30, 8)
s.add_constraint("coincident", [s.geo[line].p1, ORIGIN])
s.add_constraint("horizontal", [line])
print(solve(s).message)  # 1 degree of freedom left
s.add_constraint("distance", [line], 40)
print(solve(s).message)  # Fully constrained
print(s.line_points(line))  # ((0, 0), (40, 0))
s.add_constraint("parallel", [line])  # wrong selection
# ValueError: Parallel needs two lines.
```

## Decisions

- **Undo/redo:** each command saves a snapshot of the document before and after. Simple and hard to break.
- **Solver:** the planegcs system is rebuilt from scratch on every solve. Sketches are small, so this is fast enough and keeps the code simple.
- **Sketch points:** every line, arc and circle owns its own points, and coincident constraints join them (like FreeCAD). Snapping while drawing will add those coincident constraints automatically.
- **Midpoint** uses planegcs `symmetric_point`, because its `midpoint_on_line` means something different.
- **Dragging** (for M3): planegcs has no "soft" drag constraint, so I'll pin the point to the mouse and, if that fails, let the point slide as far as its constraints allow.
- **File format:** `.sillycad` is plain JSON with a `format_version` field.
- **Wayland:** the app sets `QT_QPA_PLATFORM=xcb` (XWayland), because OCCT's viewer needs an X11 window.
- **Font:** the whole UI uses Comic Sans, falling back to Comic Neue or a cursive font if it isn't installed.

</div>
