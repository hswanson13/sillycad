<div style="font-family: 'Comic Sans MS', 'Comic Sans', 'Comic Neue', 'Chalkboard SE', cursive;">

# SillyCAD Progress

**Where we are:** 🎉 M1–M5, sketching on faces, and U1–U6 are done. U7 holes and partial cosmetic thread support are implemented; comprehensive threading remains in progress. U8 live dimensions, U9 navigation/thread-display fixes and U10 open-guide extrusion are done. The headless suite has 437 passing tests; the native-window integration test passes separately.

**Needs you:** try the U10 workflow below and review the threading limitations before relying on it for a design.

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

## ✅ Extra: Sketch on a face (you asked for this one)

**You'll be able to:** click a flat face of the part and sketch right on it.

- [x] Click a face in 3D (dragging still just orbits), then **New Sketch**: the dialog suggests that face's plane
- [x] Works on any flat face: top, bottom, sides, slanted. Pads grow out of the face; pockets cut into it
- [x] The face's outline shows in the sketch editor as a grey guide, and you can snap to its corners
- [x] **Change plane…** (right-click a sketch) can move a sketch onto a picked face too
- [x] Tests: top/side faces become "XY/XZ/YZ + offset", bottom and slanted faces work, outline found (49 tests total)

**Good to know:** the sketch remembers the face's *plane*, not the face itself (see Decisions). If you later make the part taller, a sketch that was on the old top stays at the old height. Right-click it, choose **Change plane…** with the new top face picked, and it moves up.

## ✅ M5: Save and polish

**You'll be able to:** save, reopen, undo anything, and export with settings.

- [x] Save / Open (`.sillycad` file: readable JSON with a `format_version`)
- [x] File menu: New, Open, Save, Save As (`Ctrl+N` / `Ctrl+O` / `Ctrl+S` / `Ctrl+Shift+S`)
- [x] Window title shows the file name and a `*` when there are unsaved changes; New, Open and Quit offer to save
- [x] STL export dialog (`Ctrl+E`): linear / angular deflection, defaults 0.1 mm / 15°, remembers your last choice
- [x] `python -m sillycad part.sillycad` opens a file directly
- [x] Saving can't leave a half-written file (writes a temp file, then swaps it in)
- [x] Polite errors for files from a newer version, or broken files
- [x] Tests: save, open, recompute gives the same volume, and everything survives the round trip (53 tests total)

## ✅ U1: Inventor-style shell and theme

**You'll be able to:** use the ribbon and Model browser without losing any of the existing modeling tools.

- [x] Light-themed File, 3D Model and View ribbon, original icons, and Quick Access Toolbar
- [x] Extrude menu for Join (Pad) and Cut (Pocket); new solids are named Extrusion and Revolution
- [x] Model browser with Origin, plane picking, visibility eye, nested consumed sketches and failure badges
- [x] Document tab with the file name and unsaved `*`; body volume on the right of the status bar
- [x] Existing separate sketch editor, feature dialogs, live preview, file operations and undo/redo still work
- [x] `E` for Extrude, `F6` for Home view and `Home` for Zoom All; both documented redo shortcuts work in the main window and sketch editor
- [x] Tests for browser nesting, Origin, action shortcuts, save state and sketch redo (58 tests total)

## ✅ U2: Inventor-style viewport

**You'll be able to:** pick a plane or face after starting the sketch command, navigate with the ViewCube, and find common commands in the viewport.

- [x] Light gradient, neutral part with dark edges, translucent work planes, axes, and blue hover / selection
- [x] Native ViewCube, right-edge Pan / Zoom / Orbit / Zoom All / Look At controls, and Home view
- [x] Start 2D Sketch accepts a plane or flat face first or after the command; `Esc` / right-click cancels a pending pick
- [x] **Sketch with Offset…** keeps the explicit plane / offset dialog available; face outlines still appear as snappable guides
- [x] Look At faces a selected browser plane or sketch, or a selected planar face
- [x] Viewport marking menu provides sketch and solid commands, navigation, undo and visibility; right-drag still zooms
- [x] Separate sketch editor, feature dialogs, live preview, save / export and undo / redo remain in place
- [x] Tests cover plane selection, offsets, Look At, command cancellation and ordinary face-owner handling (66 tests total)

## ✅ U3: Sketch environment

- [x] Tested native OCCT sketch drawing over a part using 20 lines, 40 endpoints, 21 constraints, a grid and representative constraint / dimension labels. A simulated mouse drag cast rays onto the sketch plane and used the existing live solver.
- [x] With incremental presentation updates, 120 mouse-move handlers took 16.43 ms median and 16.85 ms at the 95th percentile, including redraw; 102 were within 16.67 ms and none exceeded 33.33 ms. The projection also worked after orbiting. This is a prototype measurement, not a complete sketch editor or a guarantee for larger sketches.
- [x] Native OCCT sketch presentations keep the part visible in the main viewport. Camera animation, adaptive grid, reference-outline snapping, orbit and `F5` Look At work on sketch planes.
- [x] Click-and-drag rectangles create ordinary connected lines with horizontal / vertical constraints. Constraint buttons and the constraint list are hidden until opened.
- [x] Smart Dimension and double-click editing use an in-canvas value box. Constraint glyphs can be selected and deleted, with `F8` / `F9` to show / hide them; the sketch marking menu provides drawing and editing commands.
- [x] Local sketch undo / redo, live drag solving, solver and profile feedback, and one main-window undo step on Finish remain available.
- [x] The integrated 20-line drag check recorded 115 live-solve events: 16.63 ms median, 19.16 ms at the 95th percentile, and 23.97 ms maximum; none exceeded 33.33 ms. This includes Qt test-event overhead and is not a guarantee for larger sketches.
- [x] Ruff passes. The headless suite has 83 passed and one opt-in native-window test skipped; that native test passes separately and covers face sketching, navigation, dimension / glyph editing, preview, save / reopen and STL export.
- [x] You chose to defer selecting regions from overlapping circles. Today the profile finder rejects the intersections, and solids use every profile rather than storing a region choice. Supporting that feature requires modeling and file-format changes outside U3's UI-only scope.

## ✅ U4: Property Panels and polish

**You'll be able to:** create or edit an Extrude or Revolve in a docked panel while watching the 3D preview.

- [x] One **Extrude** command opens a Join / Cut panel. Distance, direction, symmetric Join and Through All Cut map to the existing Pad / Pocket data; existing `P` / `O` shortcuts remain.
- [x] Revolve offers sketch axes and construction lines, plus Full / Angle extent. Editing keeps the feature type and identity.
- [x] **OK** commits and closes, **Cancel** discards the current preview, and **Apply (+)** commits while staying open. On a new feature, Apply prepares a fresh feature; when editing, it keeps editing the same one.
- [x] Preview errors are shown in the panel. As before, an accepted failed feature is marked red in the browser; the last good body remains visible.
- [x] Undo cancels an active feature panel first, then undoes history on the next press. Redo, save / reopen, STL export, sketch undo and main-window undo continue to work.
- [x] Browser context menus include Edit, Redefine, Rename, Delete and Origin visibility. Buttons have rich tooltips; the panel and controls use the light-theme colors and Comic Sans fallbacks.
- [x] Ruff passes. The headless suite has 93 passed and one opt-in native-window test skipped; the native test passes separately and covers panel shortcuts, Join / Cut, Apply, Undo, Revolve, sketches, saving and STL export.

**Known limitation:** choosing an individual region from overlapping circles remains deferred; the modeling core and file format are unchanged.

## ✅ U5: Key-point snapping

**You'll be able to:** see a green dot and snap new sketch geometry to important points, including on an extruded face.

- [x] Green dot on the origin, sketch points, line and arc endpoints, circle and arc centers, and line midpoints.
- [x] Face-outline endpoints and straight-edge midpoints snap too; the existing sketch plane and face-outline behavior are unchanged.
- [x] Point and midpoint snaps add the corresponding sketch constraints where the new geometry has a point. Face guides and a circle's radius click are positional, not associative; arc endpoints snap only when the point is on the existing radius.
- [x] Pixel-based picking works at different zoom levels. Markers clear when changing tools, leaving the viewport, or invalidating the target; undo / redo and drawing tools remain available.
- [x] Ruff passes. The headless suite has 99 passed and one native-window test skipped; that native test passes separately and covers rendering the green dot, undo / redo, drawing tools and face sketches.

## ✅ U6: Straight-line inference

**You'll be able to:** draw horizontal and vertical lines with green alignment feedback, including on an extruded face.

- [x] A line drawn within 5° of a sketch axis snaps horizontal or vertical. The preview turns green and the committed line receives the matching solver constraint.
- [x] Hold `Ctrl` while drawing to temporarily turn off line alignment; key-point snaps still work. A snapped key point takes precedence and does not add an extra orientation constraint.
- [x] The same inference follows sketch axes on face sketches, including after orbiting. Undo / redo cancels an unfinished chain so it cannot retain a deleted endpoint.
- [x] Ruff passes. The headless suite has 104 passed and one native-window test skipped; that native test passes separately and covers preview rendering, constraints, key-point precedence, undo / redo and sketches on top and side faces.

## 🔨 U7: Holes and threads

**You can now:** place and reposition holes by clicking planar faces or sketches and record cosmetic internal-thread metadata. Versions 1–3 still load; current saves use version 4.

- [x] Simple blind/through holes, counterbore, spotface, and countersink; selected ISO 273 metric clearance presets.
- [x] Cosmetic metadata for selected ISO metric, UNC/UNF/UNEF, NPT/NPTF, BSPP/BSPT, Tr and ACME sizes, plus custom size/pitch/taper; class text, handedness and depth persist through save, undo and edit.
- [x] Tapered simple bores are geometric cones; a cylindrical Pocket cannot be marked as a tapered thread. Existing single-circle Cuts can carry parallel-thread metadata with a rough diameter check.
- [x] Live preview, Property Panel, ribbon and marking menu, browser, undo/redo, and version-1 loading. Headless volume, invalid-input, migration and GUI tests plus an opt-in native-window test.
- [x] Click to place or move a face hole, without a separate placement sketch. Alternatively choose a sketch and click a position or a named point. A linked sketch point follows the sketch; free coordinates, intersections and face-outline targets do not. A stored face plane does not follow the original face if it moves.
- [x] Green key-point dots now appear in Select mode as well as while drawing and placing holes. Interior sketch-line intersections can be snapped; drawing there adds two point-on-line constraints.
- [x] Repositioning, Cancel, Apply, undo/redo, save/reopen, old-file migration, invalid placement, side faces, curved-face errors, and viewport navigation have regression coverage.
- [x] Ruff passes. The full headless suite has 140 passed and one native test skipped; the expanded native-window test passes separately.
- [x] Threaded Holes and circular Cuts display illustrative, non-selectable strokes on surviving bore walls, including in live previews and sketch mode. They do not change the body or STL.
- [ ] Comprehensive standards coverage, validated class-specific tolerances and fits, other clearance standards, external threads, multi-start/profile definitions, and viewport thread callouts.

**Engineering limitation:** metadata is not helical geometry and does not appear in STL. Catalogs are selected subsets; class text, pipe entrance diameter, gauge, engagement, tap drills, and manufacturing fit are not validated. Verify dimensions against the governing standards. See README's **Holes and cosmetic threads** section for exact ranges and tapered-bore limitations.

## ✅ U8: Dimension entry while drawing

- [x] Rectangle supports click–move–click as well as dragging; live width and height fields appear in the preview.
- [x] Line offers length and angle, circle offers radius, and arc offers radius followed by sweep. Type immediately, use Tab to switch fields, Enter to confirm, or click the next point; Escape cancels. Typed values create editable constraints; unedited values do not.
- [x] Arc sweep is an editable dimension in the solver and sketch UI. Format version 4 stores it; versions 1–3 still load.
- [x] Ruff passes. The headless suite has 144 passed and one native test skipped; the expanded native-window test passes separately.

## ✅ U9: Navigation recovery and thread-display stress

- [x] Lost sketch mouse releases no longer leave zoom, orbit or other drags following the pointer; navigation cursors no longer accumulate application-wide overrides. Wheel events with no vertical movement no longer zoom, and small trackpad movements zoom proportionally.
- [x] Escape leaves explicit Pan or Zoom mode in the 3D view. Existing sketch cancellation, navigation, previews and drawing remain available.
- [x] Cosmetic thread linework has a per-feature and shared segment budget, clipped to body bounds and sampled in representative patches along long bores. Only viewport illustration changes; thread metadata, model geometry and STL do not.
- [x] All 229 catalog entries, 32 combinations of hole style, extent, direction and handedness, later cuts, and the shared linework budget have regression coverage. The native test repeatedly switches thread families, including invalid and tapered choices, edits a 500 mm fine-pitch hole among twelve threaded holes, and exercises cancel, undo and redo.
- [x] On the test machine, rendering linework for twelve 500 mm threaded holes fell from 4.2 s to about 0.3 s; ten native live-preview changes had a 0.411 s median. These are measurements, not performance guarantees. Complex Boolean recomputations can still take time.
- [x] Ruff passes. The full headless suite has 429 passed and one native test skipped; the native-window test passes separately.

## ✅ U10: Closed profiles with open guides

- [x] An independent open curve no longer prevents a closed profile from being extruded or revolved. The sketch and feature panel warn that it is excluded; its geometry and constraints are retained.
- [x] Crossings or touches (except adjacent endpoints), branching and an open-only sketch still produce profile errors. There is no individual-region selection yet; all eligible closed profiles are used.
- [x] Threaded circular Cuts use the same profile rules and retain their cosmetic strokes. The existing unique-profile/default-sketch selection now recognizes a closed circle alongside an open guide.
- [x] Tested a 100 mm radius circle centered on an open line by a midpoint constraint on the side of a holed block. Extrusion volume, radius edits, solver state, undo/redo and threaded Cuts have headless and native regression coverage.
- [x] The user's saved part was loaded without writing to it: its circle selected the correct sketch, the 10 mm Join added 314,159.265 mm³, and both existing constraints remained unchanged.
- [x] Ruff passes. The full headless suite has 437 passed and one native test skipped; the native-window test passes separately.

---

## How to try it

### U10

1. Restart SillyCAD and open the saved part. Select **Sketch2** if necessary, choose **Extrude** (`E`), and use **Join** with the desired distance. The 100 mm radius circle can extend past the supporting face as long as the result is connected.
2. The warning notes that the open guide line is not included in the solid. To remove the warning, edit the sketch, select the line and press `G` for Construction; the midpoint and radius constraints remain. Use Finish Sketch, then extrude again.
3. Double-click the circle's radius dimension to change it, then use undo/redo. The guide and circle may still move unless separately constrained; face-outline snaps are positional rather than linked to the body.

### U9

1. Save any open work, restart the application, and open a part. Try wheel zoom, right-drag zoom and middle-drag pan in the 3D view and while sketching. Choose Zoom on the navigation bar, then press `Esc` to return to Orbit (in a sketch, `Esc` returns to Select).
2. Make a long hole, enable **Cosmetic thread**, and change the size or family. Long or fine-pitch bores show representative thread patches rather than every turn. Try an invalid or tapered choice and check the Property Panel for its error or required settings.
3. Use Cancel, reopen the hole, then try OK and undo/redo. A tapered pipe thread needs a simple hole, an appropriate entrance diameter and an explicit thread depth. Threading remains cosmetic and only partially covers modern standards.

### U8

1. Start a sketch, choose **Rectangle**, click the first corner and move the mouse. Type a width, press `Tab`, type a height, then press `Enter` or click the second corner. The two dimensions can be double-clicked and edited after creation. You can also draw by two clicks or by dragging without typing.
2. Try **Line**: type length, Tab to angle in degrees, and press Enter. Try **Circle**: type its radius. For **Arc**, click the center, type the radius and press Enter, then move toward the end, type its counter-clockwise sweep and press Enter.
3. Use undo/redo, change tools, and press Escape to cancel an unfinished shape. Hold Ctrl while drawing a line to temporarily suppress horizontal/vertical inference. Fields pass mouse clicks to the canvas; use Tab to select them.
4. Open a part with a cosmetic threaded Hole or circular Cut: the bore should show thread strokes in the 3D view and while sketching. The strokes are illustrative only; the exported STL is unchanged.

### U7 (in progress)

1. Make or open a block and choose **Hole**. In Placement choose **Click a face in the viewport**, then click anywhere on its flat top face; click again elsewhere to move the preview. Hover a corner, edge midpoint, sketch point, or sketch-line intersection for a green dot. Adjust Center X/Y after choosing the face.
2. Set diameter, depth and style; choose **OK**. Double-click the hole in the browser, click a new location, and use OK, undo and redo. Use Cancel to discard an uncommitted move. **Apply (+)** keeps the panel open to place another hole.
3. To associate a center with a sketch point, select that sketch under Placement and click the point or select it from the Center list. A free click or intersection is positional only. In an open sketch, hover in Select mode to see green points; use Point at the crossing of two sketch lines to add a constrained intersection.
4. Optionally enable **Cosmetic thread**; for M6 x 1, use a 5 mm bore as an example. To try clearance, turn the thread off and choose ISO 273 M6 / Medium (6.6 mm). For a Cut made from one circle, double-click the Cut and enable the cosmetic thread controls. Thread support remains partial; see the engineering limitation above.
5. Run `ruff check .`, `ruff format --check .`, and `pytest`; on X11 / XWayland, also run `SILLYCAD_NATIVE_GUI_TESTS=1 QT_QPA_PLATFORM=xcb pytest -q tests/test_sketch_native.py`.

**Panel keys:** `Ctrl+Enter` OK · `Esc` Cancel · `Ctrl+Z` cancel panel / undo · `Ctrl+Shift+Z` or `Ctrl+Y` redo.

### U6

```bash
conda activate sillycad
python -m sillycad
```

1. Start a sketch and choose **Line** (`L`). Click a starting point and move almost horizontally, then almost vertically: the preview should turn green and lock to the nearest sketch axis. Click to create each line and check the horizontal or vertical constraint glyph.
2. Move outside the 5° range to draw a diagonal. Move back into the green range and hold `Ctrl`: the preview returns to blue and clicking creates a free-angle line. Release `Ctrl` to restore inference.
3. Hover over an existing point: its green dot wins over alignment, and the endpoint remains exactly on the point. Undo or redo an unfinished chain, then draw again.
4. Finish a separate closed rectangle and use **Extrude** (`E`) → **Join** to make a block. Start a sketch on its top or side face and repeat. Orbit with Shift+middle-drag and verify that alignment still follows the sketch axes.
5. Run `ruff check .`, `ruff format --check .`, and `pytest`; on X11 / XWayland, also run `SILLYCAD_NATIVE_GUI_TESTS=1 QT_QPA_PLATFORM=xcb pytest -q tests/test_sketch_native.py`.

**Sketch keys:** `L` Line · hold `Ctrl` while drawing to suppress line alignment · `Esc` cancel / Select · `Ctrl+Z` undo · `Ctrl+Shift+Z` or `Ctrl+Y` redo · `Ctrl+Enter` Finish · `F5` Look At sketch.

### U5

```bash
conda activate sillycad
python -m sillycad
```

1. Start a sketch and draw a line. Choose **Point** (`P`) and move near an endpoint, the line's midpoint, and the origin: a green dot should appear. Click the midpoint, then drag or dimension the line to check that the point remains at its midpoint.
2. Try **Line** (`L`), **Rectangle**, **Circle** (`C`) and **Arc** (`A`) near sketch endpoints and centers. Use `Ctrl+Z` and `Ctrl+Shift+Z` to undo / redo, and switch to Select or move away to hide the dot.
3. Finish the sketch, create a separate closed rectangle sketch, and make a block from it with **Extrude** (`E`) and **Join**. Start another sketch on the block's flat face. Move a drawing tool near an outline corner or the midpoint of a straight edge: the dot should appear there too. These face-guide snaps set the initial position but do not follow later body changes.
4. Zoom in and out and try the same key points. Run `ruff check .`, `ruff format --check .`, and `pytest`; on X11 / XWayland, also run `SILLYCAD_NATIVE_GUI_TESTS=1 QT_QPA_PLATFORM=xcb pytest -q tests/test_sketch_native.py`.

**Sketch keys:** `L` Line · `C` Circle · `A` Arc · `P` Point · `Esc` cancel / Select · `Ctrl+Z` undo · `Ctrl+Shift+Z` or `Ctrl+Y` redo · `Ctrl+Enter` Finish · `F5` Look At sketch.

### U4

```bash
conda activate sillycad
python -m sillycad
```

1. Make a closed rectangle sketch and finish it. Press `E`: the **Extrude** panel replaces the Model browser, and a Join preview appears. Change **Distance**, try **Flipped** and **Symmetric**, then click **OK**.
2. Sketch a circle on the block's top face and finish. Press `E`, choose **Cut**, and try **Distance** and **Through All**. The preview should update as you change the inputs. Click **Apply (+)**: the cut is added and the panel stays open with a new feature name. Click **Cancel** to leave that next preview without removing the applied cut.
3. Double-click the extrusion in the browser. Edit its settings, click **Apply**, change another value and then **Cancel**: the applied edit remains. `Ctrl+Z` undoes the applied edit. While a panel is open, the first `Ctrl+Z` cancels the panel instead.
4. In a new part, draw a rectangle to one side of a sketch axis and finish. Press `R`, try **Full** and **Angle**, and choose a sketch axis or a construction line. Check the live preview, then commit with `Ctrl+Enter`.
5. Right-click a sketch for **Redefine (Change plane)**; try **Edit**, `F2` rename, `Del`, and the Origin eye. Hover over ribbon and panel controls for their tooltips. Save, reopen and export STL.
6. Run `ruff check .`, `ruff format --check .`, and `pytest`. On X11 / XWayland, run the extra real-window check with `SILLYCAD_NATIVE_GUI_TESTS=1 QT_QPA_PLATFORM=xcb pytest -q tests/test_sketch_native.py`.

**Panel keys:** `E` Extrude · `P` Join · `O` Cut · `R` Revolve · `Ctrl+Enter` OK · `Esc` Cancel · `Ctrl+Z` cancel panel / undo · `Ctrl+Shift+Z` or `Ctrl+Y` redo.

### U3

```bash
conda activate sillycad
python -m sillycad
```

1. Click **Start 2D Sketch**, select XY, and drag **Rectangle** between opposite corners. The right panel should report one closed profile. Select an edge, press `D`, enter a length, and double-click the label to change it.
2. Click **Constraints** in the ribbon to reveal the normally hidden buttons. Open **Constraints** in the sketch-status panel to see the list. Click a glyph and press `Del`; `Ctrl+Z` restores it. Try `F9` and `F8` to hide and show glyphs.
3. Draw a line chain with `L`, then right-click to stop it. Try the sketch marking menu, construction toggle, local undo / redo, and a stray line or overlapping circles to see profile feedback.
4. Finish (`Ctrl+Enter`), choose **Extrude** and **Join** in the Property Panel, and make a block. Start a new sketch on its flat face: the part should stay visible behind the sketch and the face outline should snap at its corners.
5. Orbit with Shift+middle-drag, pan with middle-drag, and zoom with the wheel or right-drag. Press `F5` to face the sketch again. Finish, then undo / redo once in the main window; save, reopen, and export STL.
6. Run `ruff check .`, `ruff format --check .`, and `pytest`. To run the extra native-window check on X11 / XWayland, use `SILLYCAD_NATIVE_GUI_TESTS=1 QT_QPA_PLATFORM=xcb pytest -q tests/test_sketch_native.py`.

### U2

```bash
conda activate sillycad
python -m sillycad
```

1. Click **Start 2D Sketch** (`N`), then select a highlighted base plane in the viewport or a plane under **Origin**. Alternatively, select a plane first and start the command. The sketch opens immediately, without a plane dialog. Try `Esc` and right-click to cancel while waiting for a plane.
2. Draw a closed rectangle with the Line tool, finish the sketch, and use **Extrude** (`E`) with **Join** in the Property Panel. Change the length and check the live preview, then click OK. The browser should show **Extrusion1** with **Sketch1** nested underneath.
3. Click **Start 2D Sketch** and then a flat face of the solid. Its outline should appear as a snappable guide in the sketch editor. Cancel that sketch; try selecting the face before starting a sketch as well.
4. Open the **Start 2D Sketch** dropdown → **Sketch with Offset…**, choose a base plane and enter an offset. Alternatively, right-click a browser plane and choose **Sketch with Offset…**.
5. Click different ViewCube faces and corners; use `F6` to return to the isometric Home view. Try each navigation-bar mode, middle-drag pan, right-drag zoom, the wheel, and `Home` for Zoom All. Select a plane, planar face, or browser sketch and choose **Look At**.
6. Right-click the viewport to try the marking menu. Hide and show Origin, switch Shaded / Wireframe, and check that the ViewCube still works after the model changes.
7. Save the part, make an edit, and check the `*` in the title and document tab. Undo / redo, reopen the part, and export STL; the status bar reports its triangle count.
8. Run `ruff check .`, `ruff format --check .` and `pytest`.

**Main-window keys**

| Action | Key | Action | Key |
|---|---|---|---|
| New / Open | `Ctrl+N` / `Ctrl+O` | Save / Save As | `Ctrl+S` / `Ctrl+Shift+S` |
| Export STL | `Ctrl+E` | Undo / Redo | `Ctrl+Z` / `Ctrl+Shift+Z` or `Ctrl+Y` |
| Start 2D Sketch | `N` | Extrude | `E` |
| Join (Pad) / Cut (Pocket) | `P` / `O` | Revolve | `R` |
| Zoom All | `F` / `Home` | Home view | `0` / `F6` |
| Front / Top / Right | `1` / `2` / `3` | Shaded / Wireframe | `S` / `W` |
| Cancel plane selection / leave Pan or Zoom | `Esc` (plane pick also right-click) | Marking menu | right-click viewport |

For current sketch controls, see the table in the README. The M1–M5 walkthroughs below describe the historical UI and are superseded by U4 where they differ.

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

### Sketch on a face

1. Make the 40 × 20 × 10 block from M4 (or open your own part).
2. Turn off **Show Planes** so they're out of the way. **Click the top face**: it lights up, and the status bar says "Face picked".
3. Click **New Sketch** (`N`). The dialog already says **XY, offset 10**. Click OK.
4. The face's outline is drawn in grey. Draw a circle inside it (click near a corner of the outline and it snaps there). Finish.
5. **Pocket** it: the hole starts at the top face.
6. Now click the **front face**, then New Sketch. You get **XZ** (the front plane). Draw a rectangle on the face and **Pad** it 5 mm: it sticks out of the front.
7. Try the **bottom face** (orbit underneath, or press `0` then drag the view): the dialog says **Picked face**. A Pad there grows downward, out of the part.

### M5

```bash
conda activate sillycad
python -m sillycad
```

1. Make any part (or the M4 block with a hole). The title says **Untitled \*** because it isn't saved yet.
2. `Ctrl+S` and save it as `bracket`. It becomes `bracket.sillycad` and the `*` goes away.
3. Change something (double-click Pad1, new length). The `*` comes back. `Ctrl+N`: it asks to save first. Choose **Discard**.
4. `Ctrl+O` and open `bracket.sillycad`. Everything is back, sketches and constraints included. Double-click a sketch: the dimensions are still there and still editable.
5. Close the window with unsaved changes. It asks first; **Cancel** keeps you working.
6. `Ctrl+E` (File → Export STL…). Try the defaults, then again with 0.01 mm / 5°: smoother circles, more triangles (the status bar shows the count).
7. From a terminal: `python -m sillycad bracket.sillycad` opens it straight away.
8. Peek inside `bracket.sillycad` with any text editor: it's readable JSON.
9. Run `pytest`. All 53 should pass.

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
- **Sketch on a face:** the spec ruled this out to avoid the topological naming problem (a reference to "face #7" breaks when the part changes). So picking a face only *reads* its plane once. A plane parallel to a base plane is stored as base plane + offset; any other (slanted, or facing down/back) is stored as its own plane. No sketch ever points at a face, so nothing can break. The trade-off: a sketch doesn't follow its face if that face moves later.
- **Main window undo** came early (M4 instead of M5) because the snapshot undo from the sketch editor made it nearly free.
- **File format:** `.sillycad` is readable JSON with a `format_version` field. Every object has a `type` (`sketch`, `pad`, `line`, …). The 3D shape is never saved; it's rebuilt from the features on open. Unknown fields are refused (rather than silently dropped), and a file from a newer version is refused with a clear message.
- **Wayland:** the app sets `QT_QPA_PLATFORM=xcb` (XWayland), because OCCT's viewer needs an X11 window.
- **Font:** the whole UI uses Comic Sans, falling back to Comic Neue or a cursive font if it isn't installed.

</div>
