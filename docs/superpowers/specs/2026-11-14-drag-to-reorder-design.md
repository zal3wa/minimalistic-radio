# Drag to reorder stations: design

Date: 2026-11-14. Status: approved by the owner. Applies to Windows (released together with station suggestions as 2.4.0) and Linux (stations page, Task 9 of the Linux plan).

## Intent

"Move up / Move down" in the station menu is tedious. The owner wants to grab a station with the mouse, drag it, and see the list open up where it will land.

## Behaviour

- **Grab the whole row.** The station lifts as soon as either happens with the left button down: it is **held for about 250 ms** even without moving (the owner's wish: holding shows at once that it can be dragged), or the pointer moves past the system drag threshold.
  - A quick click, released before 250 ms without moving, still plays the station, as today.
  - Releasing a lifted station without having moved puts it back in place. It does not play.
  - The ⋯ menu button never starts a drag.
- **While dragging:**
  - The dragged station lifts out of the list: a shadow and slight transparency. It follows the pointer vertically, keeps its horizontal position, and stays within the list.
  - The other stations slide apart smoothly (about 150 ms) to open a gap the height of one row where it would drop. The gap moves as the pointer moves.
  - Near the top or bottom edge of the list's visible area, the list scrolls by itself, faster the closer the pointer is.
- **Drop:** releasing the button moves the station into the gap and saves the order, with the same storage and rules as the old move. The playing station keeps playing; the current station follows its identity. Dropping in the original place changes nothing.
- **Cancel:** Escape, losing mouse capture, or releasing outside the list returns the station to its place, with animation, and nothing is saved.
- **Menu:** the ⋯ menu loses "Move up" and "Move down"; "Edit" and "Remove" stay.
- **Keyboard:** Alt+↑ / Alt+↓ on the focused or selected station moves it one place, so reordering stays possible without a mouse. Focus stays on the moved station.
- **One station or none:** nothing to drag.

## Platform notes

- **Windows (WPF):** implement it in the panel's station list with pointer capture and a `TranslateTransform` per row for the slide animation, plus an adorner or popup for the lifted row. Don't use OLE `DragDrop.DoDragDrop`: it gives no live gap and a "copy" cursor. Respect `SystemParameters.MinimumVerticalDragDistance`.
- **Linux (GTK 4):** the same experience with `Gtk.GestureDrag` on the rows: the lifted row is drawn as a translated snapshot, and the other rows get animated margins or transforms (`Adw.TimedAnimation`). Use the GTK drag threshold. Respect "reduce animation" (`gtk-enable-animations`): when animations are off, the gap jumps instead of sliding.

## Not doing

Dragging stations between windows or into other apps, multi-select, sorting by name.
