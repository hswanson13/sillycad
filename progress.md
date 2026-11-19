<div style="font-family: 'Comic Sans MS', 'Comic Sans', 'Comic Neue', 'Chalkboard SE', cursive;">

# SillyCAD Progress

**Where we are:** M1 is done. Waiting for you to try it (see "How to try it" below).

**Needs you:** try M1 and tell me it works. Then I'll start M2.

Legend: ✅ done · 🔨 in progress · ⬜ not started

---

## ✅ M1: It runs

**You'll be able to:** open the app, spin a test box around in 3D, and export it to STL.

- [x] `environment.yml`, `pyproject.toml` (ruff + pytest), README
- [x] Main window with the 3D viewer showing a box (UI in Comic Sans)
- [x] Export STL
- [x] Test: STL file is non-empty with a plausible triangle count

## ⬜ M2: Sketch brain (no GUI yet)

**You'll be able to:** run `pytest` and watch the solver work.

- [ ] Sketch model: point, line, arc, circle, construction flag, stable IDs
- [ ] Solver wrapper (planegcs): solve, degrees of freedom, conflicts
- [ ] Tests: a rectangle solves to the right coordinates, and a conflict gets caught

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
conda activate sillycad   # or: ~/miniforge3/bin/conda activate sillycad
cd ~/repos/sillycad
python -m sillycad
```

1. A brown 40 × 20 × 10 box should appear.
2. Left-drag to orbit, middle-drag to pan, scroll to zoom. Press `F` to fit the box in view again.
3. Press `W` for wireframe and `S` for shaded.
4. Choose **File → Export STL…** and save it. The status bar shows the triangle count (12 for a box).
5. Open the STL in any viewer or slicer. It should be a 40 × 20 × 10 mm box.
6. Run `pytest`. It should show 2 passed.

## Decisions

- **Undo/redo:** each command saves a snapshot of the document before and after. Simple and hard to break.
- **Solver:** the planegcs system is rebuilt from scratch on every solve. Sketches are small, so this is fast enough and keeps the code simple.
- **File format:** `.sillycad` is plain JSON with a `format_version` field.
- **Wayland:** the app sets `QT_QPA_PLATFORM=xcb` (XWayland), because OCCT's viewer needs an X11 window.
- **Font:** the whole UI uses Comic Sans, falling back to Comic Neue or a cursive font if it isn't installed.

</div>
