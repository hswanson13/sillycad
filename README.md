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
| Leave Pan / Zoom mode | `Esc` or choose Orbit |
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

Use **File** for document commands and the Quick Access Toolbar for common file commands and undo/redo. The **3D Model** ribbon has Start 2D Sketch, Extrude (Join or Cut), Revolve, Hole, and plane visibility; **View** has display, visibility, and navigation controls.

**Extrude and Revolve**

Select a sketch in the browser or start **Extrude** (`E`) or **Revolve** (`R`); the feature's Property Panel replaces the browser while its live preview remains in the viewport. If there is exactly one closed profile, its sketch is chosen automatically unless you explicitly selected another sketch.

- **Extrude** switches between **Join** (Pad) and **Cut** (Pocket). Choose the distance and default, flipped, or (for Join) symmetric direction. Cut also offers **Through All**. `P` and `O` still open the panel with Join or Cut selected.
- **Revolve** uses a sketch axis or construction line and a **Full** or **Angle** extent.
- **OK** (`Ctrl+Enter`) commits and closes; **Cancel** (`Esc`) discards the current preview. **Apply (+)** commits and stays open for another new feature. When editing an existing feature, Apply saves that edit and keeps the same feature open. Cancelling afterward does not undo an earlier Apply.
- Preview errors appear in the panel. As before, accepting a failed feature keeps it in the browser with a red error badge so it can be edited. The last valid body remains visible.

While a Property Panel is open, Undo first cancels the active panel; the next Undo changes document history. Redo closes the panel and redoes the next history step. File and other feature commands are available again after the panel closes.

**Holes and cosmetic threads**

To place a hole directly, create a solid and choose **Hole** on the 3D Model ribbon. Under Placement, choose **Click a face in the viewport**, then click a flat face. Click again to move the preview; the green dot indicates a nearby key point or sketch-line intersection. After picking a face, you can also enter **Center X** and **Center Y** in that face's coordinate system. Double-click the hole in the browser to reposition it later.

Alternatively, choose a sketch under Placement and click a position on its plane, or pick a listed point or the sketch origin. A selected sketch point remains linked to that point when the sketch changes. A clicked free position, line intersection, midpoint or face-outline target is stored as coordinates instead and does **not** follow subsequent changes to that geometry. In direct-face mode, the face's plane is stored rather than a persistent face reference; if the face later moves, the hole does not follow it automatically. If a sketch is selected in the browser when you start Hole, it is selected initially; switch the Placement dropdown to face mode if desired.

Choose the diameter, **Distance** or **Through All**, direction, and a simple, counterbore, spotface, or countersink style. Head dimensions and countersink included angle are entered explicitly. Select a listed ISO 273 fastener size and fine/medium/coarse fit to use its clearance diameter instead of a custom diameter. A clearance hole cannot also be threaded. Preview errors appear in the panel; OK, Cancel, Apply, undo/redo, and browser editing work as for other features.

Check **Cosmetic thread** to record a thread family, size, optional class text, handedness, and full or specified depth. For a recessed hole, the thread depth starts below the counterbore, spotface, or countersink. For example, choose **ISO metric → M6 x 1**, enter a 5 mm hole diameter, and optionally enter `6H` as the class. The diameter is not chosen automatically: use the appropriate bore for your design. To add metadata to an existing circular Cut, double-click the Cut in the browser and enable Cosmetic thread in its panel; its sketch must contain exactly one non-construction circle and no other non-construction curves.

**Important limitations:** this is a partial thread implementation, not comprehensive modern-CAD threading. Thread metadata is shown as illustrative strokes on surviving bore walls in the viewport, including while editing a sketch; it is not helical solid geometry, a thread texture or a dimensional callout. STL contains only the bore. The strokes use bounded sampling and are not an engineering representation of the thread profile. Thread classes are unvalidated text; the diameter check is only a rough compatibility check, not a tolerance or tap-drill calculation. The catalog contains selected sizes, not complete standards: ISO metric M1–M64; selected UNC/UNF/UNEF up to 1 inch; NPT/NPTF 1/16–2 inch; selected BSPP/BSPT 1/16–6 inch; six Tr and three ACME sizes. ISO 273 clearance presets cover M3–M16 selected sizes; inch clearances must be entered manually. A Custom thread stores a name, major diameter, pitch, and diametral taper, but not a full thread profile or multi-start definition. External threads, modeled threads, class-specific tolerances, tap-drill recommendations, and a complete standard catalog are not implemented.

Long or fine-pitch threads show separated representative patches rather than every turn. A shared viewport budget reduces detail when there are many threaded features; exceptionally large numbers of threads may have strokes omitted, with a warning in the application log. These limits affect the illustration only, not thread metadata or the solid. Complex solid recomputations still run synchronously and may take time.

NPT, NPTF, BSPT and tapered custom threads require a **simple Hole** with an explicit thread depth and user-specified entrance diameter. The bore tapers by the selected diametral taper for that depth and continues cylindrically at the smaller diameter. Pipe nominal sizes are not bore diameters; pipe entrance diameter and gauge-plane, engagement, sealing, and class requirements are **not verified**. A tapered thread cannot be attached to a cylindrical Cut. Through-all thread depth is checked against the cutter length, not measured material thickness. Verify all thread and clearance choices against the current governing standards and manufacturing requirements.

Reference data: [ISO 261 metric size table](https://www.radii.com.mx/en/tools/reference-tables/iso-261-metric-threads), [UNC/UNF table](https://www.engineeringtoolbox.com/unified-screw-threads-unc-unf-d_1809.html), [UNEF table](https://threadspec.org/unef/), [NPT dimensions](https://amesweb.info/Screws/NPT-Thread-Chart.aspx), [NPTF sizes](https://pipingtechs.com/nptf-thread-size-chart-dimensions-tpi-thread-guide/), [BSP dimensions](https://www.raipurhydraulics.com/resources/bsp-thread-chart), [Tr dimensions](https://www.roymech.co.uk/Useful_Tables/Screws/Trapezoidal.html), [ACME dimensions](https://www.radii.com.mx/en/tools/reference-tables/acme-threads), and [ISO 273 clearance examples](https://isocnc.com/resources/clearance-hole-chart/).

Click **Start 2D Sketch**, then pick a visible base plane or flat face in the viewport, or a plane under **Origin** in the Model browser. Alternatively, select the plane or face first, then start the sketch. The sketch opens in the main viewport with the part behind it; a face outline appears as a snappable guide. To specify an offset, use **Sketch with Offset…** from the Start 2D Sketch dropdown or a browser plane's context menu. The Origin eye hides or shows the planes and axes.

Select a plane, flat face, or sketch and use **Look At** on the View ribbon, navigation bar, or viewport marking menu to face it directly. While a sketch plane is being requested, `Esc` or right-click cancels the command.

Consumed sketches are nested under their features; other sketches remain at the top level. Double-click to edit, `F2` to rename, `Del` to delete, or right-click for **Edit**, **Redefine (Change plane)**, **Rename**, or **Delete**. Failed features are red with the reason in a tooltip; the last good body stays on screen. The document tab and window title show `*` for unsaved changes.

**Sketch environment**

The camera turns toward the sketch plane and the contextual **Sketch** ribbon appears. Use **Rectangle** and click opposite corners, or drag between them, to make four connected, horizontal/vertical lines. Lines chain by clicking successive points; right-click ends the chain. Scroll or right-drag to zoom, middle-drag to pan, and Shift+middle-drag to orbit; `F5` looks back at the sketch plane.

While drawing, small fields show live dimensions. Type a value immediately and use `Tab` / `Shift+Tab` to switch fields; `Enter` confirms, `Esc` cancels the unfinished geometry, and clicking the next point still works. For a rectangle the fields are width then height; move the pointer to choose the quadrant. Lines offer length and angle in degrees, circles offer radius, and arcs offer radius at the start point followed by counter-clockwise sweep in degrees at the end point. Typed values become editable sketch constraints; unedited fields remain measurements and do not constrain the shape. The fields pass mouse clicks through to the drawing canvas, so use Tab rather than clicking a field.

In Select mode and while drawing, a green dot marks a nearby key point: the origin, sketch points, line and arc endpoints, circle and arc centers, line midpoints, and interior intersections of sketch line segments. Face-outline endpoints and straight-edge midpoints are also available. Drawing geometry with a point at a sketch key point adds a coincident or midpoint constraint, or two point-on-line constraints at a line intersection. Face-outline snaps are positional only, not linked to the body; a circle's radius click is also positional only. An arc endpoint can snap only to a point on its existing radius.

Lines within 5° of the sketch's horizontal or vertical axis snap to that axis: the preview turns green and the new line receives a horizontal or vertical constraint. Hold `Ctrl` while drawing to temporarily suppress this inference for a free-angle line; key-point snapping still works. A key-point snap takes precedence over alignment, so the endpoint stays exactly on that target without adding a potentially redundant orientation constraint. Undo or redo cancels an unfinished line chain.

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

Parts are saved as `.sillycad` files: readable JSON with a `format_version`, holding the feature list (sketches with their geometry and constraints, pads, pockets, revolves, holes, and cosmetic thread metadata). Version 4 adds editable arc-sweep dimensions; versions 1–3 still load. Older SillyCAD versions cannot read version 4. Units are millimetres and degrees. The 3D shape isn't stored; it's rebuilt when the file opens. STL is export-only (binary).

## Layout

- `sillycad/core/` has the document, sketches, solver, features, file I/O and STL export. It has no Qt imports and is fully testable headless.
- `sillycad/gui/` is the PySide6 interface built on top of the core.
- `tests/` holds the headless pytest tests and an opt-in native-window integration test.

Progress is tracked in [progress.md](progress.md).
