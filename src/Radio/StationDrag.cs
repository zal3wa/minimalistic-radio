using System;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using System.Threading.Tasks;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Input;
using System.Windows.Media;
using System.Windows.Media.Animation;
using System.Windows.Media.Effects;
using System.Windows.Threading;
using static Lang;

// Dragging stations to a new place on the panel's list (docs/superpowers/specs/2026-11-14-drag-to-reorder-design.md):
// hold a station for a moment or move it, and it lifts out of the list while the others slide apart where it will land.
internal sealed partial class Radio
{
    // Where a dragged row lands. heights: each row's height with its spacing, in list order; from: the dragged row;
    // top: the dragged row's top edge, counted from the first row's top. Among the other rows it goes after every
    // row whose middle its top edge has passed.
    internal static int DropIndex(IReadOnlyList<double> heights, int from, double top)
    {
        int target = 0;
        double y = 0;   // the next other row's top, as if the dragged one weren't in the list
        for (int i = 0; i < heights.Count; i++)
        {
            if (i == from) continue;
            if (top <= y + heights[i] / 2) break;
            y += heights[i];
            target++;
        }
        return target;
    }

    private sealed class StationDrag
    {
#if SELFTEST
        // The self-test's synthetic mouse events carry no position (WPF asks the real mouse), so the test puts
        // a pretend pointer here, in the panel's coordinates.
        internal static Point? TestPointer;
#endif

        private const double EdgeZone = 32;   // this close to the list's top or bottom edge it scrolls by itself

        // Moves a station to a place on the list and saves the order; false if nothing changed.
        internal Func<SavedStation, int, bool> Move;

        private readonly ListBox list;
        private readonly DispatcherTimer hold = new DispatcherTimer { Interval = TimeSpan.FromMilliseconds(250) };
        private readonly DispatcherTimer scroll = new DispatcherTimer();
        private readonly Dictionary<ListBoxItem, double> shifts = new Dictionary<ListBoxItem, double>();   // rows moved aside
        // The lifted look, put behind the row's buttons: a card like the panel's, with a shadow.
        private readonly Border card = new Border
        {
            CornerRadius = new CornerRadius(4), BorderThickness = new Thickness(1), IsHitTestVisible = false,
            Effect = new DropShadowEffect { BlurRadius = 12, ShadowDepth = 2, Direction = 270, Opacity = 0.3 }
        };
        private ScrollViewer viewer;
        private Grid pressed;            // held down, not lifted yet
        private bool pressCaptured;      // pressed between the two buttons: the row took the mouse itself
        private Point pressedAt;
        private Grid row;                // the lifted station
        private ListBoxItem container;
        private TranslateTransform lift;
        private int from, target, scrollStep;
        private double grab, pointerY, scrollDelay;   // grab: where the row is held, from its top; pointerY: in the list
        private Action settle;           // lands a station still sliding into its place at once

        internal StationDrag(Window panel, ListBox list)
        {
            this.list = list;
            card.SetResourceReference(Border.BackgroundProperty, "Card");
            card.SetResourceReference(Border.BorderBrushProperty, "Line");
            // The press may have ended unseen (let go over a popup, or the mouse taken away): no lift without the button down.
            hold.Tick += (_, _) =>
            {
                if (ButtonUp()) CancelPress();
                else Lift();
            };
            scroll.Tick += (_, _) => ScrollStep();
            // Escape puts the station back, and only that: the panel's own Escape (back, hide) waits for the next one.
            panel.PreviewKeyDown += (_, e) =>
            {
                if (e.Key != Key.Escape || row == null) return;
                Cancel();
                e.Handled = true;
            };
            list.PreviewKeyDown += (_, e) => MoveByKey(e);
            // The panel hides when it loses focus: the station goes back and the mouse is let go, so nothing
            // holds the panel up.
            panel.Deactivated += (_, _) => Cancel();
            panel.Closed += (_, _) => Cancel();
            list.IsVisibleChanged += (_, _) => { if (!list.IsVisible) Cancel(); };
            // A long list builds only the rows near the visible ones; the lifted row has to stay while its place
            // scrolls far away.
            VirtualizingStackPanel.AddCleanUpVirtualizedItemHandler(list, (_, e) =>
            {
                if (row != null && (e.UIElement == container || e.Value == row)) e.Cancel = true;
            });
        }

        // Every station's row: the whole row can be grabbed, except its ⋯ button.
        internal void Attach(Grid stationRow, Button options)
        {
            stationRow.Background = Brushes.Transparent;   // so the gap between the two buttons can be grabbed too
            stationRow.PreviewMouseLeftButtonDown += (_, e) => Press(stationRow, options, e);
            stationRow.MouseLeftButtonDown += (_, e) =>
            {
                // Pressed between the buttons, where nothing takes the mouse: the row does, and the list doesn't select it.
                if (pressed != stationRow || e.OriginalSource != stationRow || !stationRow.CaptureMouse()) return;
                pressCaptured = true;
                e.Handled = true;
            };
            stationRow.PreviewMouseMove += (_, e) => Moved(stationRow, e);
            stationRow.PreviewMouseLeftButtonUp += (_, e) => Released(stationRow, e);
            stationRow.LostMouseCapture += (_, e) =>
            {
                if (e.OriginalSource != stationRow) return;   // e.g. the station button handing the mouse over to the row
                if (stationRow == row) Cancel();
                else if (stationRow == pressed) CancelPress();
            };
        }

        private void Press(Grid stationRow, Button options, MouseButtonEventArgs e)
        {
            settle?.Invoke();
            if (row != null || Stations.Count < 2 || Within(e.OriginalSource, options)) return;   // one station: nothing to drag
            if (viewer == null)
            {
                viewer = Descendants(list).OfType<ScrollViewer>().FirstOrDefault();
                if (viewer == null) return;
                viewer.ScrollChanged += (_, _) => Follow();   // scrolled (by itself or the wheel): the gap moves along
            }
            if (!(list.ItemContainerGenerator.ContainerFromItem(stationRow) is ListBoxItem place)) return;
            CancelPress();
            pressed = stationRow;
            pressedAt = Pointer(e, viewer);
            pointerY = pressedAt.Y;
            grab = pressedAt.Y - SlotTop(place);
            hold.Start();
        }

        private void Moved(Grid stationRow, MouseEventArgs e)
        {
            if (stationRow == row)
            {
                pointerY = Pointer(e, viewer).Y;
                Follow();
                AutoScroll();
                return;
            }
            if (stationRow != pressed) return;
            if (ButtonUp())
            {
                CancelPress();
                return;
            }
            Point at = Pointer(e, viewer), inRow = Pointer(e, stationRow);
            pointerY = at.Y;
            if (Math.Abs(at.Y - pressedAt.Y) >= SystemParameters.MinimumVerticalDragDistance) Lift();
            // Left the row before the hold was up: an ordinary press of the button.
            else if (inRow.X < 0 || inRow.Y < 0 || inRow.X > stationRow.ActualWidth || inRow.Y > stationRow.ActualHeight) CancelPress();
        }

        private void Released(Grid stationRow, MouseButtonEventArgs e)
        {
            if (stationRow == row)
            {
                e.Handled = true;
                Drop(Pointer(e, viewer));
            }
            // Let go before the hold was up: a click, and the station button plays the station as before.
            else if (stationRow == pressed) CancelPress();
        }

        // The list is about to be built again and these rows go away: forget a press or a lift at once (no slide back)
        // and let the mouse go, so no row that is no longer shown keeps it.
        internal void Abandon()
        {
            if (pressed != null) CancelPress();
            if (row != null) Finish();
            container = null;
            lift = null;
        }

        private void CancelPress()
        {
            hold.Stop();
            Grid stationRow = pressed;
            bool captured = pressCaptured;
            pressed = null;
            pressCaptured = false;
            if (captured && stationRow.IsMouseCaptured) stationRow.ReleaseMouseCapture();
        }

        // Held for 250 ms, or moved past the drag threshold: the station lifts out of the list.
        private void Lift()
        {
            hold.Stop();
            Grid lifted = pressed;
            bool captured = pressCaptured;
            pressed = null;
            pressCaptured = false;
            if (lifted == null) return;
            container = list.ItemContainerGenerator.ContainerFromItem(lifted) as ListBoxItem;
            from = Stations.IndexOf(lifted.Tag as SavedStation);
            // The row takes the mouse from the station button, so the release that ends the drag isn't a click.
            if (container == null || from < 0 || !lifted.CaptureMouse())
            {
                if (captured) lifted.ReleaseMouseCapture();
                container = null;
                return;
            }
            row = lifted;
            target = from;
            container.RenderTransform = lift = new TranslateTransform();
            Raise(container, row, true);
            shifts.Clear();
            if (VisualTreeHelper.GetParent(container) is Panel host)
                foreach (ListBoxItem other in host.Children.OfType<ListBoxItem>())
                    if (other != container) shifts[other] = 0;
            Follow();
        }

        // Puts the lifted row under the pointer, inside the list, and opens the gap where it would land.
        private void Follow()
        {
            if (row == null) return;
            if (!(VisualTreeHelper.GetParent(container) is Panel host))
            {
                Cancel();
                return;
            }
            ItemContainerGenerator generator = list.ItemContainerGenerator;
            double pitch = Pitch(container);
            var heights = new double[list.Items.Count];
            for (int i = 0; i < heights.Length; i++) heights[i] = pitch;   // rows not built yet (far down a long list) are as tall
            List<ListBoxItem> built = host.Children.OfType<ListBoxItem>().ToList();
            foreach (ListBoxItem other in built)
            {
                int i = generator.IndexFromContainer(other);
                if (i >= 0) heights[i] = Pitch(other);
            }
            // Where the first row's top is, worked out from the first visible row (the list scrolls by whole stations).
            int first = viewer.CanContentScroll ? Math.Max(0, Math.Min(heights.Length - 1, (int)viewer.VerticalOffset)) : from;
            if (!(generator.ContainerFromIndex(first) is ListBoxItem anchor))
            {
                anchor = container;
                first = from;
            }
            double start = SlotTop(anchor) - heights.Take(first).Sum(), end = start + heights.Sum();
            // It follows the pointer up and down but stays inside the list and its visible part.
            double top = Math.Max(Math.Max(0, start), Math.Min(Math.Min(viewer.ActualHeight, end) - pitch, pointerY - grab));
            lift.Y = top - SlotTop(container);
            target = DropIndex(heights, from, top - start);
            foreach (ListBoxItem other in built)
            {
                int i = generator.IndexFromContainer(other);
                if (other != container && i >= 0) Shift(other, from < i && i <= target ? -pitch : target <= i && i < from ? pitch : 0);
            }
        }

        // Slides a row aside for the gap, or puts it there at once if it was only just built while scrolling.
        private void Shift(ListBoxItem other, double offset)
        {
            bool known = shifts.TryGetValue(other, out double current);
            if (known && current == offset) return;
            shifts[other] = offset;
            if (!(other.RenderTransform is TranslateTransform move)) other.RenderTransform = move = new TranslateTransform();
            if (known) move.BeginAnimation(TranslateTransform.YProperty, Slide(offset));
            else
            {
                move.BeginAnimation(TranslateTransform.YProperty, null);
                move.Y = offset;
            }
        }

        // Near the top or bottom edge of the visible list it scrolls by itself: a station every 300 ms at the inner
        // edge of the zone, faster closer to the list's edge, every 60 ms at the edge and beyond.
        private void AutoScroll()
        {
            double bottom = viewer.ActualHeight - EdgeZone;
            scrollStep = pointerY < EdgeZone && viewer.VerticalOffset > 0 ? -1
                : pointerY > bottom && viewer.VerticalOffset < viewer.ScrollableHeight ? 1 : 0;
            if (scrollStep == 0)
            {
                scroll.Stop();
                return;
            }
            scrollDelay = 300 - 240 * Math.Min(1, (scrollStep < 0 ? EdgeZone - pointerY : pointerY - bottom) / EdgeZone);
            if (scroll.IsEnabled) return;   // setting the interval restarts the timer, so the next tick sets it
            scroll.Interval = TimeSpan.FromMilliseconds(scrollDelay);
            scroll.Start();
        }

        private void ScrollStep()
        {
            if (row == null)
            {
                scroll.Stop();
                return;
            }
            AutoScroll();   // still at an edge, and not at the end yet?
            if (scrollStep == 0) return;
            // A line is one station here (the list scrolls by whole stations); ScrollChanged then moves the gap.
            if (scrollStep < 0) viewer.LineUp();
            else viewer.LineDown();
            scroll.Interval = TimeSpan.FromMilliseconds(scrollDelay);
        }

        // Let go: the station moves into the gap and the order is saved. Outside the list, or where it was, it goes back.
        private void Drop(Point at)
        {
            pointerY = at.Y;
            Follow();
            if (row == null) return;
            if (at.X < 0 || at.Y < 0 || at.X > viewer.ActualWidth || at.Y > viewer.ActualHeight || target == from)
            {
                Cancel();
                return;
            }
            var item = (SavedStation)row.Tag;
            Grid lifted = row;
            ListBoxItem place = container;
            double offset = lift.Y, landed = SlotTop(container) + lift.Y;
            int to = target;
            List<ListBoxItem> others = Finish();
            if (Move == null || !Move(item, to))
            {
                SlideBack(lifted, place, offset, others);   // not saved: the list stays as it was
                return;
            }
            // Only the station's row moved: the rows that made room for it now stand there for real, so their slide
            // ends at once (before anything is drawn), and the station slides from where it was let go into its place.
            foreach (ListBoxItem other in others)
                if (other.RenderTransform is TranslateTransform move)
                {
                    move.BeginAnimation(TranslateTransform.YProperty, null);
                    move.Y = 0;
                }
            list.UpdateLayout();
            if (list.ItemContainerGenerator.ContainerFromItem(lifted) is ListBoxItem slot)
                Settle(slot, lifted, landed - SlotTop(slot));
        }

        // Escape, the mouse lost, the panel hiding, or let go outside the list: everything slides back into place.
        private void Cancel()
        {
            if (row == null)
            {
                if (pressed != null) CancelPress();
                return;
            }
            Grid lifted = row;
            ListBoxItem place = container;
            double offset = lift.Y;
            SlideBack(lifted, place, offset, Finish());
        }

        // Ends the drag and lets the mouse go; returns the rows that had moved aside.
        private List<ListBoxItem> Finish()
        {
            Grid lifted = row;
            row = null;   // before letting go: the row's LostMouseCapture then finds no drag
            scrollStep = 0;
            scroll.Stop();
            List<ListBoxItem> others = shifts.Keys.ToList();
            shifts.Clear();
            if (lifted.IsMouseCaptured) lifted.ReleaseMouseCapture();
            return others;
        }

        private void SlideBack(Grid lifted, ListBoxItem place, double offset, List<ListBoxItem> others)
        {
            foreach (ListBoxItem other in others)
                if (other.RenderTransform is TranslateTransform move) move.BeginAnimation(TranslateTransform.YProperty, Slide(0));
            Settle(place, lifted, offset);
        }

        // The station slides into its place from `offset` away, then loses the lifted look.
        private void Settle(ListBoxItem place, Grid stationRow, double offset)
        {
            settle?.Invoke();
            var move = new TranslateTransform(0, offset);
            place.RenderTransform = move;
            Raise(place, stationRow, true);
            Action done = null;
            done = () =>
            {
                if (settle != done) return;
                settle = null;
                place.ClearValue(UIElement.RenderTransformProperty);
                Raise(place, stationRow, false);
            };
            settle = done;
            DoubleAnimation slide = Slide(0);
            slide.Completed += (_, _) => done();
            move.BeginAnimation(TranslateTransform.YProperty, slide);
        }

        // The lifted look: above the other rows, slightly see-through, on a card with a shadow.
        private void Raise(ListBoxItem place, Grid stationRow, bool lifted)
        {
            if (lifted)
            {
                Panel.SetZIndex(place, 1);
                place.Opacity = 0.9;
                if (card.Parent == stationRow) return;
                (card.Parent as Panel)?.Children.Remove(card);
                Grid.SetColumnSpan(card, Math.Max(1, stationRow.ColumnDefinitions.Count));
                stationRow.Children.Insert(0, card);
            }
            else
            {
                place.ClearValue(Panel.ZIndexProperty);
                place.ClearValue(UIElement.OpacityProperty);
                if (card.Parent == stationRow) stationRow.Children.Remove(card);
            }
        }

        // Alt+↑ / Alt+↓ moves the focused station (or the selected one) one place; the focus stays on it.
        private void MoveByKey(KeyEventArgs e)
        {
            // With Alt held, Windows reports the arrow as a system key.
            if (row != null || e.Key != Key.System || (e.SystemKey != Key.Up && e.SystemKey != Key.Down)) return;
            var source = e.OriginalSource as DependencyObject;
            Grid stationRow = (source == null ? null : ItemsControl.ContainerFromElement(list, source) as ListBoxItem)?.Content as Grid
                ?? list.SelectedItem as Grid;
            if (!(stationRow?.Tag is SavedStation item)) return;
            e.Handled = true;
            // The station button or its ⋯ button: the same one gets the focus in the moved row.
            int part = Math.Max(0, Descendants(stationRow).OfType<Button>().ToList().IndexOf(source as Button));
            int to = Stations.IndexOf(item) + (e.SystemKey == Key.Up ? -1 : 1);
            if (Move == null || !Move(item, to)) return;
            Grid moved = list.Items.OfType<Grid>().FirstOrDefault(other => other.Tag == item);
            if (moved == null) return;
            list.ScrollIntoView(moved);
            list.UpdateLayout();
            Descendants(moved).OfType<Button>().ElementAtOrDefault(part)?.Focus();
        }

        private static bool ButtonUp()
        {
#if SELFTEST
            if (TestPointer != null) return false;   // the self-test's synthetic presses leave the real button up
#endif
            return Mouse.LeftButton != MouseButtonState.Pressed;
        }

        private static Point Pointer(MouseEventArgs e, UIElement relativeTo)
        {
#if SELFTEST
            if (TestPointer is Point fake) return Window.GetWindow(relativeTo).TranslatePoint(fake, relativeTo);
#endif
            return e.GetPosition(relativeTo);
        }

        // A row's place in the list's visible area (the top of its spacing), not counting its slide.
        private double SlotTop(ListBoxItem place) => VisualTreeHelper.GetParent(place) is UIElement host
            ? VisualTreeHelper.GetOffset(place).Y - place.Margin.Top + host.TranslatePoint(new Point(), viewer).Y : 0;

        private static double Pitch(ListBoxItem place) => place.ActualHeight + place.Margin.Top + place.Margin.Bottom;

        private static DoubleAnimation Slide(double to) =>
            new DoubleAnimation(to, TimeSpan.FromMilliseconds(150)) { EasingFunction = new CubicEase { EasingMode = EasingMode.EaseOut } };

        private static bool Within(object source, DependencyObject ancestor)
        {
            for (var node = source as DependencyObject; node != null;
                 node = node is Visual ? VisualTreeHelper.GetParent(node) : LogicalTreeHelper.GetParent(node))
                if (node == ancestor) return true;
            return false;
        }
    }

#if SELFTEST
    // Self-test (--test-menu, from VerifyMenu), on a list in memory: nothing is saved and nothing plays. The ⋯ menu
    // without Move up / Move down, logos from the cache, a quick press that stays a press, a hold that lifts, the gap
    // and the drop (moving only the station's row: the other rows and their logos stay), Escape, Alt+↓ / Alt+↑ with
    // the focus kept, and a long list scrolling by itself at its edges.
    private async Task VerifyStationDrag()
    {
        try
        {
            // Logos come from the cache, put there by the test (nothing is downloaded): A–D have one, E's didn't load.
            string[] letters = { "A", "B", "C", "D", "E" };
            var pictures = new Dictionary<string, ImageSource>();
            Stations.Clear();
            foreach (string letter in letters)
            {
                string logo = "https://example.com/logo/" + letter;
                pictures[letter] = letter == "E" ? null : Theme.AppImage(32);
                CacheLogo(logo, Task.FromResult(pictures[letter]));
                Stations.Add(new SavedStation { Name = "Stacja " + letter, Url = "https://example.com/" + letter, Logo = logo });
            }
            Task<ImageSource> failed = LoadLogo("https://example.com/logo/E");
            SavedStation current = Stations[1];
            station = 1;
            session = null;
            playerPanel?.Close();
            OpenPlayer();
            await Task.Delay(800);
            ListBox list = Descendants(playerPanel).OfType<ListBox>().First(item => item.IsVisible);
            string Order() => string.Concat(Stations.Select(item => item.Name.Substring(7)));
            string Shown() => string.Concat(list.Items.OfType<Grid>().Select(row => ((SavedStation)row.Tag).Name.Substring(7)));
            bool Current() => station >= 0 && station < Stations.Count && Stations[station] == current && session == null;
            Grid Row(string letter) => list.Items.OfType<Grid>().First(row => ((SavedStation)row.Tag).Name == "Stacja " + letter);
            ListBoxItem Box(Grid row) => (ListBoxItem)list.ItemContainerGenerator.ContainerFromItem(row);
            Button Play(Grid row) => Descendants(row).OfType<Button>().First();
            Image Picture(Grid row) => Descendants(row).OfType<Image>().First();
            // Every row still the same row, with the same Image showing the same picture: nothing built or loaded again.
            Dictionary<string, (Grid row, Image image)> Rows() => letters.ToDictionary(letter => letter, letter => (Row(letter), Picture(Row(letter))));
            bool Kept(Dictionary<string, (Grid row, Image image)> before) => letters.All(letter =>
                Row(letter) == before[letter].row && Picture(Row(letter)) == before[letter].image && before[letter].image.Source == pictures[letter]);
            double Shifted(string letter) => (Box(Row(letter)).RenderTransform as TranslateTransform)?.Y ?? 0;
            Point Middle(FrameworkElement element) =>
                element.TranslatePoint(new Point(element.ActualWidth / 2, element.ActualHeight / 2), playerPanel);
            // Like Windows: the preview event tunnels down to the target, then the same event bubbles up from it.
            void Send(UIElement target, RoutedEvent preview, RoutedEvent bubble)
            {
                MouseEventArgs args = preview == Mouse.PreviewMouseMoveEvent
                    ? new MouseEventArgs(Mouse.PrimaryDevice, Environment.TickCount)
                    : new MouseButtonEventArgs(Mouse.PrimaryDevice, Environment.TickCount, MouseButton.Left);
                args.RoutedEvent = preview;
                target.RaiseEvent(args);
                if (bubble == null) return;
                args.RoutedEvent = bubble;
                target.RaiseEvent(args);
            }
            void Down(UIElement target, Point at)
            {
                StationDrag.TestPointer = at;
                Send(target, Mouse.PreviewMouseDownEvent, Mouse.MouseDownEvent);
            }
            void MoveTo(UIElement target, Point at)
            {
                StationDrag.TestPointer = at;
                Send(target, Mouse.PreviewMouseMoveEvent, Mouse.MouseMoveEvent);
            }
            void Up(UIElement target, bool bubble = true) => Send(target, Mouse.PreviewMouseUpEvent, bubble ? Mouse.MouseUpEvent : null);
            void Press(UIElement target, Key key, bool alt = false)
            {
                var args = new KeyEventArgs(Keyboard.PrimaryDevice, PresentationSource.FromVisual(playerPanel), Environment.TickCount, key)
                    { RoutedEvent = Keyboard.PreviewKeyDownEvent };
                // With Alt held Windows marks the key as a system key; the test marks it the same way.
                if (alt) typeof(KeyEventArgs).GetMethod("MarkSystem", BindingFlags.Instance | BindingFlags.NonPublic).Invoke(args, null);
                target.RaiseEvent(args);
                args.RoutedEvent = Keyboard.KeyDownEvent;
                target.RaiseEvent(args);
            }

            // The ⋯ menu keeps Edit and Remove; Move up / Move down went away with dragging.
            List<string> labels = ((Descendants(Row("A")).OfType<Button>().Last().Tag as ContextMenu)?.Items.OfType<MenuItem>()
                .Select(item => item.Header as string) ?? Enumerable.Empty<string>()).ToList();
            if (!labels.Contains(T("Edytuj", "Edit")) || !labels.Contains(T("Usuń", "Remove")) ||
                labels.Contains(T("Przesuń wyżej", "Move up")) || labels.Contains(T("Przesuń niżej", "Move down")))
                throw new InvalidOperationException("Błędne menu stacji: " + string.Join(", ", labels));

            // The logos show from the cache; the one that didn't load stays the radio icon and isn't fetched again.
            if (letters.Any(letter => Picture(Row(letter)).Source != pictures[letter]) || !ReferenceEquals(LoadLogo("https://example.com/logo/E"), failed))
                throw new InvalidOperationException("Logo stacji nie z pamięci podręcznej.");

            // Let go before the hold is up: no lift (the button's own click, which plays the station, isn't sent here).
            Grid rowA = Row("A");
            Point start = Middle(Play(rowA));
            double pitch = Middle(Row("B")).Y - Middle(rowA).Y;
            Down(Play(rowA), start);
            Up(Play(rowA), false);
            await Task.Delay(400);
            if (rowA.IsMouseCaptured || Panel.GetZIndex(Box(rowA)) != 0 || !Current())
                throw new InvalidOperationException("Krótkie kliknięcie podniosło stację.");

            // Held for 250 ms without moving: it lifts above the others.
            Down(Play(rowA), start);
            await Task.Delay(400);
            if (!rowA.IsMouseCaptured || Panel.GetZIndex(Box(rowA)) != 1 || Box(rowA).Opacity >= 1)
                throw new InvalidOperationException("Przytrzymana stacja się nie podniosła.");

            // Two rows down: B and C slide up to open the gap; let go there, A lands third, B stays the current
            // station and nothing plays.
            MoveTo(rowA, start + new Vector(0, pitch * 2.2));
            await Task.Delay(400);
            if (Math.Abs(Shifted("B") + pitch) > 1 || Math.Abs(Shifted("C") + pitch) > 1 || Math.Abs(Shifted("D")) > 1)
                throw new InvalidOperationException($"Stacje się nie rozsunęły: B {Shifted("B")}, C {Shifted("C")}, D {Shifted("D")}, wiersz {pitch}.");
            if (preview) await SavePreview(playerPanel, "drag");
            Dictionary<string, (Grid row, Image image)> beforeDrop = Rows();
            Up(rowA);
            if (Order() != "BCADE" || Shown() != "BCADE" || !Current() || rowA.IsMouseCaptured || !Kept(beforeDrop))
                throw new InvalidOperationException("Upuszczenie: " + Order() + " / " + Shown() + ", " + StationName +
                    (session != null ? ", gra" : "") + (Kept(beforeDrop) ? "" : ", wiersze lub logo zbudowane od nowa"));

            // Moved past the drag threshold it lifts at once; Escape puts it back, and the panel stays open.
            rowA = Row("A");
            start = Middle(Play(rowA));
            Down(Play(rowA), start);
            MoveTo(Play(rowA), start + new Vector(0, pitch * 1.4));
            bool lifted = rowA.IsMouseCaptured;
            await Task.Delay(300);
            bool gap = Math.Abs(Shifted("D") + pitch) < 1;
            Press(Play(rowA), Key.Escape);
            await Task.Delay(400);
            if (!lifted || !gap || rowA.IsMouseCaptured || Order() != "BCADE" || playerPanel?.IsVisible != true ||
                Panel.GetZIndex(Box(rowA)) != 0 || Math.Abs(Shifted("A")) > 1 || Math.Abs(Shifted("D")) > 1)
                throw new InvalidOperationException($"Escape nie odłożył stacji (podniesiona {lifted}, przerwa {gap}, kolejność {Order()}).");

            // Alt+↓ on a focused station moves it one place down, Alt+↑ back up; the focus stays on it.
            Dictionary<string, (Grid row, Image image)> beforeKeys = Rows();
            Play(Row("A")).Focus();
            Press(Play(Row("A")), Key.Down, true);
            string afterDown = Order();
            bool focusKept = !playerPanel.IsActive || Row("A").IsKeyboardFocusWithin;
            Press(Play(Row("A")), Key.Up, true);
            if (afterDown != "BCDAE" || Order() != "BCADE" || Shown() != "BCADE" || !focusKept || !Current() || !Kept(beforeKeys))
                throw new InvalidOperationException("Alt+strzałki: " + afterDown + ", potem " + Order() + (focusKept ? "" : ", bez fokusu") +
                    (Kept(beforeKeys) ? "" : ", wiersze lub logo zbudowane od nowa"));

            // A long list, both ways: held at an edge it scrolls by itself while the lifted station's own place
            // scrolls far out of view; then, held in the middle, the visible rows must still lie one after another
            // from the list's top edge, the gap must be where the lifted row is, and let go there the station must
            // land in that gap, with the list staying where it was.
            for (int n = Stations.Count + 1; Stations.Count < 40; n++)
                Stations.Add(new SavedStation { Name = "Stacja " + n, Url = "https://example.com/" + n });
            playerPanel.Close();
            OpenPlayer();
            await Task.Delay(800);
            list = Descendants(playerPanel).OfType<ListBox>().First(item => item.IsVisible);
            // The list was built anew: the logos are the same pictures from the cache, not downloaded again.
            if (letters.Any(letter => Picture(Row(letter)).Source != pictures[letter]))
                throw new InvalidOperationException("Po przebudowie listy logo nie z pamięci podręcznej.");
            ScrollViewer viewer = Descendants(list).OfType<ScrollViewer>().First();
            ItemContainerGenerator generator = list.ItemContainerGenerator;
            // Rows snap to whole device pixels at display scaling (125%, 150%…), so places can be off by a pixel or so;
            // a row in the wrong slot would be off by a whole row.
            const double Px = 2;
            double Slid(ListBoxItem box) => (box.RenderTransform as TranslateTransform)?.Y ?? 0;
            double Place(ListBoxItem box) => box.TranslatePoint(new Point(), viewer).Y - Slid(box) - box.Margin.Top;   // without its slide
            Point InList(double y) => viewer.TranslatePoint(new Point(viewer.ActualWidth / 2, y), playerPanel);
            async Task DragFar(string name, bool down)
            {
                Grid dragged = Row(name);
                Point at = Middle(Play(dragged));
                double before = viewer.VerticalOffset;
                Down(Play(dragged), at);
                MoveTo(Play(dragged), at + new Vector(0, down ? 10 : -10));
                MoveTo(dragged, InList(down ? viewer.ActualHeight - 4 : 4));
                await Task.Delay(1500);
                double scrolled = viewer.VerticalOffset;
                MoveTo(dragged, InList(viewer.ActualHeight / 2));   // out of the edge zone: scrolling stops
                await Task.Delay(400);
                ListBoxItem liftedBox = Box(dragged);
                List<ListBoxItem> seen = ((Panel)VisualTreeHelper.GetParent(liftedBox)).Children.OfType<ListBoxItem>()
                    .Where(box => Place(box) > Px - pitch && Place(box) < viewer.ActualHeight - Px).OrderBy(Place).ToList();
                int[] indices = seen.Select(generator.IndexFromContainer).ToArray();
                string layout = string.Join(" ", seen.Select(box => generator.IndexFromContainer(box) + "@" + Math.Round(Place(box)) +
                    (Math.Abs(Slid(box)) > Px ? "/" + Math.Round(Slid(box)) : "")));
                // Laid out one after another from the top edge, in order, and the lifted station's far place not among them.
                bool contiguous = seen.Count > 2 && Math.Abs(Place(seen[0])) < Px && indices[0] == (int)viewer.VerticalOffset &&
                    !seen.Contains(liftedBox) && Enumerable.Range(1, seen.Count - 1)
                        .All(k => indices[k] == indices[k - 1] + 1 && Math.Abs(Place(seen[k]) - Place(seen[k - 1]) - pitch) < Px);
                // Rows between its place and the gap moved one row toward its place, the others not at all.
                double toward = down ? -pitch : pitch;
                bool slides = seen.All(box => Math.Abs(Slid(box)) < Px || Math.Abs(Slid(box) - toward) < Px);
                int[] moved = seen.Where(box => Math.Abs(Slid(box) - toward) < Px).Select(generator.IndexFromContainer).ToArray();
                int gapRow = moved.Length == 0 ? -1 : down ? moved.Max() : moved.Min();
                bool split = gapRow >= 0 && seen.Where(box => Math.Abs(Slid(box)) < Px)
                    .All(box => down ? generator.IndexFromContainer(box) > gapRow : generator.IndexFromContainer(box) < gapRow);
                double gapTop = split ? Place(seen.First(box => generator.IndexFromContainer(box) == gapRow)) : double.NaN;
                double liftedTop = liftedBox.TranslatePoint(new Point(), viewer).Y - liftedBox.Margin.Top, pointer = viewer.ActualHeight / 2;
                bool over = Math.Abs(liftedTop - gapTop) <= pitch / 2 + Px && pointer >= liftedTop && pointer <= liftedTop + pitch;
                bool kept = dragged.IsMouseCaptured;
                if (preview) await SavePreview(playerPanel, "drag-far-" + (down ? "down" : "up"));
                double dropped = viewer.VerticalOffset;
                Up(dragged);
                await Task.Delay(400);
                int landed = Stations.FindIndex(item => item.Name == "Stacja " + name);
                bool inGap = landed == gapRow && ((Grid)list.Items[gapRow]).Tag == dragged.Tag &&
                    Math.Abs(Place(Box((Grid)list.Items[gapRow])) - gapTop) < Px;
                if (Math.Abs(scrolled - before) < 5 || !contiguous || !slides || !split || !over || !kept || !inGap ||
                    Math.Abs(viewer.VerticalOffset - dropped) > 0.5 || !Current())
                    throw new InvalidOperationException($"Długa lista ({(down ? "w dół" : "w górę")}) [{contiguous} {slides} {split} {over} {inGap}]: przewinięto {before}→{scrolled}, " +
                        $"wiersze {layout}; przerwa {gapRow}@{gapTop}, podniesiona @{liftedTop}, trzymana {kept}, " +
                        $"wylądowała {landed}, przewinięcie {dropped}→{viewer.VerticalOffset}, aktualna {StationName}.");
            }
            await DragFar("A", true);
            viewer.ScrollToEnd();
            list.UpdateLayout();
            await Task.Delay(300);
            await DragFar("40", false);
            playerPanel.Close();

            // The logo cache stays small: past its limit the oldest logos go first.
            for (int n = 0; n < LogoCacheSize + 50; n++) CacheLogo("https://example.com/many/" + n, Task.FromResult<ImageSource>(null));
            if (logos.Count != LogoCacheSize || logos.ContainsKey("https://example.com/logo/A") ||
                !logos.ContainsKey("https://example.com/many/" + (LogoCacheSize + 49)))
                throw new InvalidOperationException("Pamięć logo bez limitu: " + logos.Count);
        }
        finally { StationDrag.TestPointer = null; }
    }
#endif
}
