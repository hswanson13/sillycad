<div style="font-family: 'Comic Sans MS', 'Comic Sans', 'Comic Neue', 'Chalkboard SE', cursive;">

# SillyCAD Progress

**Where we are:** M3 is done. Waiting for you to try it (see "How to try it" below).

**Needs you:** play with the sketch editor and tell me how it feels. Then I'll start M4.

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

## ✅ M3: Sketch editor

**You'll be able to:** draw and constrain a sketch with the mouse.

- [x] 2D editor with grid, zoom/pan and snapping to points
- [x] Draw lines (they chain), arcs, circles and points, with a construction toggle
- [x] Constraint buttons + keyboard shortcuts, with a hint when the selection is wrong
- [x] Dimension labels (double-click to edit); new dimensions ask for a value right away
- [x] Live solve while dragging, DOF in the status bar
- [x] Colors: normal = free, green = fully constrained, red = conflict
- [x] Clear messages for open or self-intersecting profiles, with red rings on the trouble spots
- [x] Undo / redo inside the sketch editor
- [x] Finished sketches show as blue wires in 3D, with a Show Sketches toggle

## ⬜ M4: Solids

**You'll be able to:** turn sketches into real parts.

- [ ] Pad, Pocket, Revolve
- [ ] Feature tree: edit, rename, delete, errors shown
- [ ] Recompute from history when anything changes
- [ ] Base planes and origin axes in 3D
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

### M3

```bash
conda activate sillycad
python -m sillycad
```

1. Click **New Sketch**, keep **XY**, and click OK. The sketch editor opens.
2. Press `L`. Click the **origin** (the big dot where the red and green axes cross), then 3 more corners of a rectangle, then the origin again to close it. Snapping to a point (a blue ring shows) joins the ends for you.
3. Watch the right panel: it should say **1 closed profile**.
4. Press `Esc`. Click the bottom line and press `H`, then click the right line and press `V`. Do the same for the other two sides.
5. Click the bottom line and press `D`. Type `40` and press Enter. Click the right line, press `D` and enter `20`. Everything turns **green**: fully constrained.
6. Double-click the `40` label and change it to `60`. The rectangle stretches.
7. Try a conflict: click the bottom line, press `Shift+H`, and enter `10`. It turns **red** and the panel lists the conflict. Press `Ctrl+Z` to undo.
8. Delete a dimension (click its label, press `Del`), then drag a corner. It slides live as far as the constraints allow.
9. Draw a circle (`C`) inside the rectangle. It's still 1 profile, now with a hole. Draw a stray line (`L`, two clicks, then `Esc`). Red rings mark its loose ends.
10. Click **✔ Finish**. The sketch appears in 3D as blue wires. The placeholder box turns see-through so you can see it. **Show Sketches** hides it again.
11. Run `pytest`. All 32 should pass.

**Sketch editor keys**

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

Mouse: scroll to zoom, middle-drag to pan, right-click to stop drawing. Shift- or Ctrl-click selects more than one item.

## Decisions

- **Undo/redo:** each command saves a snapshot of the document before and after. Simple and hard to break.
- **Solver:** the planegcs system is rebuilt from scratch on every solve. Sketches are small, so this is fast enough and keeps the code simple.
- **Sketch points:** every line, arc and circle owns its own points, and coincident constraints join them (like FreeCAD). Snapping while drawing will add those coincident constraints automatically.
- **Midpoint** uses planegcs `symmetric_point`, because its `midpoint_on_line` means something different.
- **Dragging:** planegcs has no "soft" drag constraint, so the point is pinned to the mouse first. If that fails, it tries pinning just x, just y, or nothing, and keeps whichever lands closest to the mouse. So a point held by some constraints slides along whatever freedom it has left.
- **Sketch editor:** a separate window. Its canvas is redrawn from the model after every change, and picking uses plain geometry math, which keeps it simple and reliable.
- **Conflicts:** a conflicting constraint stays in the sketch (in red) and the geometry keeps its last good shape, like FreeCAD. Undo or delete fixes it. Duplicates, and Horizontal + Vertical on one line, are refused up front.
- **Test box:** the M1 box is still there as a placeholder and turns see-through when sketches exist. M4 replaces it with real solids.
- **File format:** `.sillycad` is plain JSON with a `format_version` field.
- **Wayland:** the app sets `QT_QPA_PLATFORM=xcb` (XWayland), because OCCT's viewer needs an X11 window.
- **Font:** the whole UI uses Comic Sans, falling back to Comic Neue or a cursive font if it isn't installed.

</div>
