<div style="font-family: 'Comic Sans MS', 'Comic Sans', 'Comic Neue', 'Chalkboard SE', cursive;">

# SillyCAD Progress

**Where we are:** M4 is done. Waiting for you to try it (see "How to try it" below).

**Needs you:** make a part or two and tell me how it goes. Then I'll start M5 (the last one).

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

## ✅ M4: Solids

**You'll be able to:** turn sketches into real parts.

- [x] Pad (length, reversed, symmetric), Pocket (length or through all, reversed), Revolve (sketch axis or construction line, angle)
- [x] Live 3D preview while you fill in a feature's settings, with any problem shown right in the dialog
- [x] Feature tree: double-click to edit, F2 to rename, Del to delete, right-click to change a sketch's plane
- [x] Recompute from history when anything changes; failed features turn red and the last good body stays
- [x] Rules: the first solid must be a Pad or Revolve, the body stays one piece, and revolve axes can't cross the profile
- [x] Base planes (with labels) and origin axes in 3D, with show/hide
- [x] Toolbar: Fit All, front / top / right / iso views
- [x] Undo / redo for everything in the main window (moved up from M5)
- [x] Body volume in the status bar
- [x] Tests: pad = 8000 mm³, pocket, revolve (annulus, cylinder, half), and the error cases (44 tests total)

## ⬜ M5: Save and polish

**You'll be able to:** save, reopen, undo anything, and export with settings.

- [ ] Save / Open (`.sillycad` file, plain JSON)
- [ ] File menu: New, Open, Save, Save As, and a warning about unsaved changes
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

### M4

```bash
conda activate sillycad
python -m sillycad
```

You'll see the three base planes (blue XY, green XZ, red YZ) and the origin axes.

1. **Pad:** click **New Sketch** (`N`) and pick XY. Draw a rectangle from the origin with dimensions 40 and 20 (like M3), then click **✔ Finish**. Click **Pad** (`P`). The block previews live as you change the length. Use 10 and click OK. The status bar says **Body volume: 8,000.0 mm³**.
2. **Pocket:** New Sketch, XY, offset **10** (the top of the block). Draw a circle on the block and Finish. Click **Pocket** (`O`), tick **Through all**, and click OK. Now there's a hole.
3. **Edit history:** double-click **Sketch1** in the tree, double-click its `40` and make it `60`, then Finish. The block gets longer and the hole is rebuilt in it. (Double-clicking **Pad1** edits its length the same way.)
4. **Revolve:** New Sketch, **XZ**. Draw a rectangle with its left side on the green vertical axis, about 8 wide, from height 10 up to 25, so it sits on the block. Finish. Click **Revolve** (`R`) with "Sketch vertical axis", and a round post appears on the corner.
5. **Errors:** double-click the revolve's sketch and drag the rectangle across the green axis. Finish. **Revolve1** turns red ("The axis crosses the profile") and the body keeps its last good shape. `Ctrl+Z` fixes it.
6. **Tree:** select Pad1 and press `F2` to rename it. Select Sketch2 and press `Del`. It asks before also deleting Pocket1. `Ctrl+Z` brings it back. Right-click a sketch to **Change plane…**
7. **Views:** `1` front, `2` top, `3` right, `0` iso, `F` fit. **Show Planes** and **Show Sketches** toggle.
8. **File → Export STL…** now exports the real body.
9. Run `pytest`. All 44 should pass.

## Decisions

- **Undo/redo:** each command saves a snapshot of the document before and after. Simple and hard to break.
- **Solver:** the planegcs system is rebuilt from scratch on every solve. Sketches are small, so this is fast enough and keeps the code simple.
- **Sketch points:** every line, arc and circle owns its own points, and coincident constraints join them (like FreeCAD). Snapping while drawing will add those coincident constraints automatically.
- **Midpoint** uses planegcs `symmetric_point`, because its `midpoint_on_line` means something different.
- **Dragging:** planegcs has no "soft" drag constraint, so the point is pinned to the mouse first. If that fails, it tries pinning just x, just y, or nothing, and keeps whichever lands closest to the mouse. So a point held by some constraints slides along whatever freedom it has left.
- **Sketch editor:** a separate window. Its canvas is redrawn from the model after every change, and picking uses plain geometry math, which keeps it simple and reliable.
- **Conflicts:** a conflicting constraint stays in the sketch (in red) and the geometry keeps its last good shape, like FreeCAD. Undo or delete fixes it. Duplicates, and Horizontal + Vertical on one line, are refused up front.
- **Recompute** replays the whole feature list from scratch on every change. That's simple and always correct, and fast enough for small parts.
- **One body:** a feature that would leave the body in separate pieces fails with a clear message, instead of silently making two solids.
- **Pocket direction:** by default a pocket cuts against the sketch's normal, into the material (so a sketch on top of a block cuts down). "Reversed" flips it.
- **Plane directions:** XY faces +Z, XZ faces −Y (the front), YZ faces +X (the right), matching the Front/Top/Right views.
- **Main window undo** came early (M4 instead of M5) because the snapshot undo from the sketch editor made it nearly free.
- **File format:** `.sillycad` is plain JSON with a `format_version` field.
- **Wayland:** the app sets `QT_QPA_PLATFORM=xcb` (XWayland), because OCCT's viewer needs an X11 window.
- **Font:** the whole UI uses Comic Sans, falling back to Comic Neue or a cursive font if it isn't installed.

</div>
