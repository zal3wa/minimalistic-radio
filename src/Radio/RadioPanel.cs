using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Net.Http;
using System.Runtime.InteropServices;
using System.Threading;
using System.Threading.Tasks;
using System.Windows;
using System.Windows.Automation;
using System.Windows.Controls;
using System.Windows.Controls.Primitives;
using System.Windows.Input;
using System.Windows.Interop;
using System.Windows.Media;
using System.Windows.Media.Effects;
using System.Windows.Media.Imaging;
using System.Windows.Threading;
using Forms = System.Windows.Forms;
using static Lang;

// The player panel that opens next to the notification area: stations, history and settings.
internal sealed partial class Radio
{
    private const double ShadowMargin = 10;
    private readonly Stopwatch sinceDismiss = new Stopwatch();

    [StructLayout(LayoutKind.Sequential)]
    private struct Rect32 { public int Left, Top, Right, Bottom; }

    [DllImport("user32.dll")]
    private static extern bool GetWindowRect(IntPtr window, out Rect32 rect);

    [DllImport("user32.dll")]
    private static extern bool SetWindowPos(IntPtr window, IntPtr after, int x, int y, int width, int height, uint flags);

    [DllImport("user32.dll")]
    private static extern short GetAsyncKeyState(int key);

    [StructLayout(LayoutKind.Sequential)]
    private struct AppBarData
    {
        public int Size;
        public IntPtr Window;
        public uint CallbackMessage;
        public uint Edge;
        public Rect32 Bounds;
        public IntPtr Param;
    }

    [DllImport("shell32.dll")]
    private static extern IntPtr SHAppBarMessage(uint message, ref AppBarData data);

    // Where Windows 11 opens its own flyouts: the corner of the taskbar's screen next to the
    // notification area (bottom right, or top right / bottom left for a taskbar on another edge).
    private static (System.Drawing.Rectangle area, uint edge) TrayCorner()
    {
        var data = new AppBarData { Size = Marshal.SizeOf(typeof(AppBarData)) };
        if (SHAppBarMessage(5, ref data) != IntPtr.Zero) // ABM_GETTASKBARPOS
        {
            var bar = System.Drawing.Rectangle.FromLTRB(data.Bounds.Left, data.Bounds.Top, data.Bounds.Right, data.Bounds.Bottom);
            System.Drawing.Rectangle area = Forms.Screen.FromRectangle(bar).WorkingArea;
            // An auto-hiding taskbar is left inside the work area: keep clear of where it slides in.
            area = data.Edge switch
            {
                0 => System.Drawing.Rectangle.FromLTRB(Math.Max(area.Left, bar.Right), area.Top, area.Right, area.Bottom),
                1 => System.Drawing.Rectangle.FromLTRB(area.Left, Math.Max(area.Top, bar.Bottom), area.Right, area.Bottom),
                2 => System.Drawing.Rectangle.FromLTRB(area.Left, area.Top, Math.Min(area.Right, bar.Left), area.Bottom),
                _ => System.Drawing.Rectangle.FromLTRB(area.Left, area.Top, area.Right, Math.Min(area.Bottom, bar.Top))
            };
            return (area, data.Edge);
        }
        return (Forms.Screen.PrimaryScreen.WorkingArea, 3);
    }

    private void ShowPlayer()
    {
        if (playerPanel != null) playerPanel.Close();
        // The click on the tray icon has just closed the panel (click outside): don't reopen it.
        else if (!sinceDismiss.IsRunning || sinceDismiss.ElapsedMilliseconds > 400) OpenPlayer();
    }

    // ---- Small building blocks ----

    private static readonly GridLength Auto = GridLength.Auto;
    private static readonly GridLength Star = new GridLength(1, GridUnitType.Star);
    private const double Gutter = 12;   // the panel's padding: around the bar, at the sides of every page, under Play

    // A page that scrolls; its content keeps the gutter on both sides and the scroll bar floats over the right one.
    private ScrollViewer Pane()
    {
        var pane = new ScrollViewer
        {
            VerticalScrollBarVisibility = ScrollBarVisibility.Auto, HorizontalScrollBarVisibility = ScrollBarVisibility.Disabled,
            Visibility = Visibility.Collapsed, Focusable = false
        };
        pane.SetResourceReference(FrameworkElement.StyleProperty, "OverlayScroll");
        return pane;
    }

    // The same for a list: its rows keep the gutter on both sides (the list's own border adds the last pixel).
    private void OverlayScroll(ListBox box)
    {
        box.Resources[typeof(ScrollViewer)] = app.FindResource("OverlayScroll");
        box.Padding = new Thickness(Gutter - 1, 0, Gutter - 1, 0);
    }

    // The Play/Stop button's content: a filled triangle or square, then the word.
    private static FrameworkElement PlayLabel(bool play, string text)
    {
        FrameworkElement glyph = Theme.Solid(play ? Theme.PlayIcon : Theme.StopIcon, play ? 16 : 18, "AccentFg");
        glyph.VerticalAlignment = VerticalAlignment.Center;
        // Segoe UI sits low in its line: a pixel up puts the word level with the glyph.
        var label = new StackPanel { Orientation = Orientation.Horizontal };
        label.Children.Add(glyph);
        label.Children.Add(new TextBlock { Text = text, VerticalAlignment = VerticalAlignment.Center, Margin = new Thickness(10, 0, 0, 2) });
        return label;
    }

    private static FrameworkElement Spaced(Orientation orientation, double spacing, params FrameworkElement[] children)
    {
        var panel = new StackPanel { Orientation = orientation };
        for (int i = 0; i < children.Length; i++)
        {
            if (i > 0)
                children[i].Margin = orientation == Orientation.Vertical
                    ? new Thickness(0, spacing, 0, 0) : new Thickness(spacing, 0, 0, 0);
            panel.Children.Add(children[i]);
        }
        return panel;
    }

    private static FrameworkElement IconText(string glyph, string text, string color = null) => Spaced(Orientation.Horizontal, 8,
        Theme.Glyph(glyph, 18, color), new TextBlock { Text = text, VerticalAlignment = VerticalAlignment.Center });

    private static Button NewButton(string style, object content, string tip = null)
    {
        var button = new Button { Content = content, ToolTip = tip };
        if (style != null) button.SetResourceReference(FrameworkElement.StyleProperty, style);
        return button;
    }

    private static Button SmallButton(string style, string text)
    {
        Button button = NewButton(style, text);
        button.Padding = new Thickness(12, 4, 12, 4);
        button.FontSize = 13;
        return button;
    }

    private static FrameworkElement Columns(params (FrameworkElement element, GridLength width)[] cells)
    {
        var grid = new Grid();
        for (int i = 0; i < cells.Length; i++)
        {
            grid.ColumnDefinitions.Add(new ColumnDefinition { Width = cells[i].width });
            Grid.SetColumn(cells[i].element, i);
            grid.Children.Add(cells[i].element);
        }
        return grid;
    }

    private static TextBlock Note(string text)
    {
        var note = new TextBlock { Text = text, TextWrapping = TextWrapping.Wrap, FontSize = 12.5 };
        note.SetResourceReference(TextBlock.ForegroundProperty, "Subtle");
        return note;
    }

    private static Border Divider(Thickness margin)
    {
        var divider = new Border { Height = 1, Margin = margin };
        divider.SetResourceReference(Border.BackgroundProperty, "Line");
        return divider;
    }

    private static Border CardFrame(FrameworkElement child, Thickness padding)
    {
        var card = new Border
        {
            CornerRadius = new CornerRadius(6), BorderThickness = new Thickness(1),
            Padding = padding, Margin = new Thickness(0, 0, 0, 4), Child = child
        };
        card.SetResourceReference(Border.BackgroundProperty, "Card");
        card.SetResourceReference(Border.BorderBrushProperty, "Line");
        return card;
    }

    private static void OpenWebPage(string address)
    {
        try { Process.Start(new ProcessStartInfo(address) { UseShellExecute = true })?.Dispose(); }
        catch (Win32Exception error) { Debug.WriteLine(error); }
    }

    // A settings row: an optional icon, the title with a grey description under it, the control on the right.
    private static FrameworkElement SettingRow(string title, object description, FrameworkElement control, FrameworkElement icon = null)
    {
        var text = new StackPanel { VerticalAlignment = VerticalAlignment.Center };
        text.Children.Add(new TextBlock { Text = title, FontSize = 14, TextWrapping = TextWrapping.Wrap });
        if (description != null)
        {
            TextBlock note = description as TextBlock ?? Note(description.ToString());
            note.Margin = new Thickness(0, 1, 0, 0);
            text.Children.Add(note);
        }
        var row = new Grid { MinHeight = 40, Margin = new Thickness(14, 12, 14, 12) };
        row.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
        row.ColumnDefinitions.Add(new ColumnDefinition { Width = Star });
        row.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
        if (icon != null)
        {
            icon.VerticalAlignment = VerticalAlignment.Center;
            icon.Margin = new Thickness(0, 0, 12, 0);
            row.Children.Add(icon);
        }
        Grid.SetColumn(text, 1);
        row.Children.Add(text);
        if (control != null)
        {
            control.Margin = new Thickness(12, 0, 0, 0);
            control.VerticalAlignment = VerticalAlignment.Center;
            Grid.SetColumn(control, 2);
            row.Children.Add(control);
        }
        return row;
    }

    // A settings card, like a group in the Settings app: its rows in one box, with thin lines between them.
    private static Border SettingsCard(params FrameworkElement[] rows)
    {
        var body = new StackPanel();
        foreach (FrameworkElement row in rows)
        {
            if (body.Children.Count > 0) body.Children.Add(Divider(new Thickness(0)));
            body.Children.Add(row);
        }
        Border card = CardFrame(body, new Thickness(0));
        card.Margin = new Thickness(0);
        return card;
    }

    // A button in a settings row, as tall as the language list.
    private static Button RowButton(string text)
    {
        Button button = NewButton(null, text);
        button.MinHeight = 32;
        button.Padding = new Thickness(14, 0, 14, 0);
        button.VerticalAlignment = VerticalAlignment.Center;
        return button;
    }

    private static TextBlock Group(string text, bool first = false) => new TextBlock
    {
        Text = text, FontSize = 14, FontWeight = FontWeights.SemiBold, Margin = new Thickness(2, first ? 0 : 18, 0, 8)
    };

    private static Button Link(string text, string address)
    {
        var content = new StackPanel { Orientation = Orientation.Horizontal };
        content.Children.Add(new TextBlock { Text = text, VerticalAlignment = VerticalAlignment.Center });
        FrameworkElement arrow = Theme.Glyph(Theme.ExternalIcon, 13, "Accent");
        arrow.Margin = new Thickness(6, 0, 0, 0);
        content.Children.Add(arrow);
        Button button = NewButton("LinkButton", content);
        button.Padding = new Thickness(8, 5, 0, 5);   // the arrow ends where the row's controls end
        button.VerticalAlignment = VerticalAlignment.Center;
        button.Click += (_, _) => OpenWebPage(address);
        return button;
    }

    // Windows 11 on/off switch with its "On"/"Off" label.
    private static CheckBox Toggle(bool on, Action<bool> changed)
    {
        var toggle = new CheckBox { IsChecked = on };
        toggle.SetResourceReference(FrameworkElement.StyleProperty, "ToggleSwitch");
        void Label() => toggle.Content = toggle.IsChecked == true ? Lc("switch", "On") : Lc("switch", "Off");
        Label();
        toggle.Checked += (_, _) => { Label(); changed(true); };
        toggle.Unchecked += (_, _) => { Label(); changed(false); };
        return toggle;
    }

    // ---- The panel ----

    // startPage: "stations", "history", "settings", or "search:<query>" to open the station search with results.
    private void OpenPlayer(string startPage = "stations")
    {
        if (playerPanel != null) { playerPanel.Activate(); return; }
        string startSearch = null;
        if (startPage.StartsWith("search:", StringComparison.Ordinal))
        {
            startSearch = startPage.Substring(7);
            startPage = "stations";
        }
        CloseMenu();
        Theme.Apply(app);
        var panel = new Window
        {
            Title = AppName, Width = 412 + 2 * ShadowMargin, Height = 602 + 2 * ShadowMargin,
            ResizeMode = ResizeMode.NoResize, ShowInTaskbar = false, Topmost = true,
            WindowStyle = WindowStyle.None, AllowsTransparency = true, Background = Brushes.Transparent,
            WindowStartupLocation = WindowStartupLocation.Manual, Left = -32000, Top = -32000,
            FontSize = 14, UseLayoutRounding = true
        };
        panel.SetResourceReference(Control.ForegroundProperty, "Fg");
        TextOptions.SetTextFormattingMode(panel, TextFormattingMode.Display);
        playerPanel = panel;
        // Menus and file dialogs opened from the panel keep it open while they are shown.
        int holdOpen = 0;
#if SELFTEST
        if (testMenu) holdOpen = 1;   // the self-test keeps the panel open, as if a menu were shown
#endif
        panel.Closed += (_, _) => { if (playerPanel == panel) playerPanel = null; };
        panel.Deactivated += (_, _) => Post(() =>
        {
            if (playerPanel == panel && !panel.IsActive && holdOpen == 0) panel.Close();
        });
        void Hold(ContextMenu menu)
        {
            menu.Opened += (_, _) => holdOpen++;
            menu.Closed += (_, _) => holdOpen--;
        }

        // The list starts 12 px under the bar, like its sides (its border and the rows' margin add a pixel each).
        var list = new ListBox { Margin = new Thickness(0, Gutter - 2, 0, 0) };
        OverlayScroll(list);
        // The playing station's row shows a play triangle before its ⋯ button.
        var playingMarks = new Dictionary<SavedStation, FrameworkElement>();
        // Stations are dragged to a new place, or moved with Alt+↑/↓ (StationDrag.cs); MoveStation below makes the move.
        var drag = new StationDrag(panel, list);
        var now = new TextBlock
        {
            TextWrapping = TextWrapping.Wrap, TextTrimming = TextTrimming.CharacterEllipsis, FontSize = 15,
            FontWeight = FontWeights.SemiBold, LineHeight = 20, LineStackingStrategy = LineStackingStrategy.BlockLineHeight,
            MaxHeight = 40, VerticalAlignment = VerticalAlignment.Center
        };
        var play = NewButton("AccentButton", null);
        play.MinHeight = 38;
        var volumeSlider = new Slider
        {
            Minimum = 0, Maximum = 100, Value = volume, IsSnapToTickEnabled = true, TickFrequency = 1,
            SmallChange = 1, LargeChange = 5, IsMoveToPointEnabled = true, VerticalAlignment = VerticalAlignment.Center
        };
        var name = new TextBox { Tag = L("Station name"), MaxLength = 100 };
        var url = new TextBox { Tag = L("Stream address (HTTP or HTTPS)"), MaxLength = 2048 };
        var logo = new TextBox { Tag = L("Logo address (optional)"), MaxLength = 2048 };
        SavedStation editing = null;
        var message = new TextBlock { TextWrapping = TextWrapping.Wrap };
        // The "Copied" bubble: one layer over the whole panel, so it can sit above any button (the copy button, a
        // history row's more button), with the same bubble as the volume's. It goes after 1.5 s, and the copy
        // button's check mark with it.
        Grid notice = NewBubble(out TextBlock noticeText);
        var noticeLayer = new Canvas { IsHitTestVisible = false, Tag = "notice" };
        noticeLayer.Children.Add(notice);
        var noticeTimer = new DispatcherTimer { Interval = TimeSpan.FromMilliseconds(1500) };
        Action noticeEnd = null;
        void EndNotice()
        {
            noticeTimer.Stop();
            notice.Visibility = Visibility.Collapsed;
            Action end = noticeEnd;
            noticeEnd = null;
            end?.Invoke();
        }
        noticeTimer.Tick += (_, _) => EndNotice();
        panel.Closed += (_, _) => noticeTimer.Stop();
        void ShowNotice(FrameworkElement anchor, Action end = null)
        {
            EndNotice();
            noticeEnd = end;
            noticeText.Text = L("Copied");
            notice.Visibility = Visibility.Visible;
            noticeLayer.UpdateLayout();
            Point top = anchor.TranslatePoint(new Point(anchor.ActualWidth / 2, 0), noticeLayer);
            double left = Math.Round(top.X - notice.ActualWidth / 2);
            // Inside the panel's edges; the bubble would be cut off at its right otherwise.
            left = Math.Max(ShadowMargin, Math.Min(left, noticeLayer.ActualWidth - ShadowMargin - notice.ActualWidth));
            Canvas.SetLeft(notice, left);
            Canvas.SetTop(notice, Math.Round(Math.Max(ShadowMargin, top.Y - notice.ActualHeight - 4)));
            noticeTimer.Start();
        }

        // The station form (Add by address, Edit) is a page of its own.
        var save = NewButton("AccentButton", L("Save"));
        var cancelForm = NewButton(null, L("Cancel"));
        var fields = Spaced(Orientation.Vertical, 8, name, url, logo,
            Spaced(Orientation.Horizontal, 8, save, cancelForm), message);
        fields.Margin = new Thickness(Gutter);
        fields.Visibility = Visibility.Collapsed;

        var searchBox = new TextBox { Tag = L("Type a station name"), MaxLength = 100 };
        var searchButton = NewButton(null, L("Search"));
        searchButton.Margin = new Thickness(8, 0, 0, 0);
        // The search page: box and button, then one line with the status (or a hint) and "Add by address".
        string searchHint = L("Search the radio-browser.info directory");
        var manual = SmallButton("LinkButton", L("Add by address"));
        manual.VerticalAlignment = VerticalAlignment.Center;
        manual.Margin = new Thickness(8, 0, -8, 0);
        var results = new ListBox();
        OverlayScroll(results);
        TextBlock searchStatus = Note(searchHint);
        searchStatus.VerticalAlignment = VerticalAlignment.Center;
        var searchHeader = Spaced(Orientation.Vertical, 4, Columns((searchBox, Star), (searchButton, Auto)),
            Columns((searchStatus, Star), (manual, Auto)));
        searchHeader.Margin = new Thickness(Gutter, Gutter, Gutter, 6);
        var searchPane = new DockPanel { Visibility = Visibility.Collapsed };
        DockPanel.SetDock(searchHeader, Dock.Top);
        searchPane.Children.Add(searchHeader);
        searchPane.Children.Add(results);
        CancellationTokenSource activeSearch = null;
        var loadingSuggestions = new CancellationTokenSource();
        bool loadingNow = false, resetting = false;
        string page = "stations";
        panel.Closed += (_, _) => { activeSearch?.Cancel(); loadingSuggestions.Cancel(); };

        // The bar on top. On the stations page: [+ Station] [History], and on the right the update arrow (when one is
        // ready) and Settings. On the other pages: ← and the page's title. There is no hide button: the panel hides when
        // it loses focus, on Esc and on a click on the tray icon. Its space above, below and left is the same 12 px.
        var add = NewButton(null, IconText(Theme.PlusIcon, L("Station")));
        var historyButton = NewButton(null, IconText(Theme.HistoryIcon, L("History")));
        historyButton.Margin = new Thickness(4, 0, 0, 0);
        foreach (Button button in new[] { add, historyButton })
        {
            button.Height = 32;
            button.Padding = new Thickness(10, 0, 12, 0);
        }
        var settingsButton = NewButton("GhostButton", Theme.Glyph(Theme.SettingsIcon), L("Settings"));
        settingsButton.Margin = new Thickness(4, 0, 0, 0);
        // Like Discord: a green arrow appears once a new version is downloaded; a click installs it.
        var updateButton = NewButton("GhostButton", Theme.UpdateBadge(18), L("Update Ready!"));
        updateButton.Visibility = Visibility.Collapsed;
        updateButton.Click += (_, _) => InstallUpdate();
        var backButton = NewButton("GhostButton", Theme.Glyph(Theme.BackIcon), L("Back"));
        foreach (Button button in new[] { updateButton, settingsButton, backButton })
        {
            button.Width = button.Height = 32;
            button.Padding = new Thickness(0);
        }
        // Segoe UI sits low in its line: 2 px less below lifts the title by one, level with the arrow.
        var pageTitle = new TextBlock
        {
            FontSize = 14, FontWeight = FontWeights.SemiBold, TextTrimming = TextTrimming.CharacterEllipsis,
            VerticalAlignment = VerticalAlignment.Center, Margin = new Thickness(4, 0, 0, 2)
        };
        var stationsBar = Columns((add, Auto), (historyButton, Auto), (new Border(), Star), (updateButton, Auto), (settingsButton, Auto));
        var pageBar = Columns((backButton, Auto), (pageTitle, Star));
        var bar = new Grid { Margin = new Thickness(Gutter) };
        bar.Children.Add(stationsBar);
        bar.Children.Add(pageBar);
        // Under the bar, across the whole panel: the text colour at 10 %.
        var barLine = new Border { Height = 1, Opacity = 0.1 };
        barLine.SetResourceReference(Border.BackgroundProperty, "Fg");
        var header = new StackPanel();
        header.Children.Add(bar);
        header.Children.Add(barLine);
        // The player (now playing, volume, Play/Stop) is only on the stations page; it is filled in further down.
        var footer = new Border { Margin = new Thickness(Gutter, 10, Gutter, Gutter) };
        ScrollViewer settingsPane = Pane(), historyPane = Pane(), statisticsPane = Pane();

        int shownStation = station;
        void ShowActiveStation(bool centre)
        {
            if (station < 0 || station >= list.Items.Count || list.Visibility != Visibility.Visible) return;
            list.ScrollIntoView(list.Items[station]);
            ScrollViewer viewer = Descendants(list).OfType<ScrollViewer>().FirstOrDefault();
            // The list scrolls by whole stations, so offsets and the viewport are counted in stations.
            if (centre && viewer != null && viewer.CanContentScroll && viewer.ViewportHeight > 0)
                viewer.ScrollToVerticalOffset(Math.Max(0, station - (viewer.ViewportHeight - 1) / 2));
        }
        void ShowActiveStationAfterLayout(bool centre) =>
            app.Dispatcher.BeginInvoke(DispatcherPriority.Loaded, new Action(() => ShowActiveStation(centre)));

        void Edit(SavedStation item)
        {
            editing = item;
            name.Text = item?.Name ?? "";
            url.Text = item?.Url ?? "";
            logo.Text = item?.Logo ?? "";
            message.Text = "";
            SetPage("form");
            app.Dispatcher.BeginInvoke(DispatcherPriority.Loaded, new Action(() => name.Focus()));
        }

        void FillList()
        {
            drag.Abandon();   // a press or a drag on the old rows ends here
            list.Items.Clear();
            playingMarks.Clear();
            foreach (SavedStation item in Stations) list.Items.Add(StationRow(item));
            list.SelectedIndex = station;
            shownStation = station;
            ShowActiveStationAfterLayout(false);
        }

        bool SaveStations(List<SavedStation> updated)
        {
#if SELFTEST
            if (testMenu) return true;   // the self-test changes stations in memory only: the saved list stays as it was
#endif
            try
            {
                Storage.Write(Storage.StationFile, updated);
                return true;
            }
            catch (Exception error) when (error is IOException || error is UnauthorizedAccessException)
            {
                Forms.MessageBox.Show(L("Couldn't save the station list."), AppName);
                return false;
            }
        }

        bool ApplyStations(List<SavedStation> updated)
        {
            if (!SaveStations(updated)) return false;
            SavedStation active = station >= 0 && station < Stations.Count ? Stations[station] : null;
            Stations.Clear();
            Stations.AddRange(updated);
            if (active != null) station = Stations.IndexOf(active);
            FillList();
            return true;
        }

        async void Search()
        {
            string query = searchBox.Text?.Trim();
            if (string.IsNullOrEmpty(query) || !searchButton.IsEnabled) return;
            using (var request = new CancellationTokenSource())
            {
                activeSearch = request;
                CancellationToken searchToken = request.Token;
                searchButton.IsEnabled = false;
                results.Items.Clear();
                searchStatus.Text = L("Searching…");
                try
                {
                    DirectoryStation[] found = await Storage.Search(metadataClient, query, searchToken);
                    if (searchToken.IsCancellationRequested) return;
                    foreach (DirectoryStation item in found) results.Items.Add(ResultRow(item));
                    searchStatus.Text = found.Length == 0 ? L("No results.") : "";
                }
                catch (OperationCanceledException) when (searchToken.IsCancellationRequested) { }
                catch (Exception error) when (error is HttpRequestException || error is OperationCanceledException)
                {
                    searchStatus.Text = L("The station directory is unavailable right now. Try again.");
                }
                finally
                {
                    if (activeSearch == request)
                    {
                        activeSearch = null;
                        searchButton.IsEnabled = true;
                    }
                }
            }
        }

        // A section title in the list (not selectable).
        FrameworkElement Heading(string text)
        {
            var title = new TextBlock { Text = text, FontSize = 13, FontWeight = FontWeights.SemiBold, Margin = new Thickness(10, 8, 0, 2) };
            title.SetResourceReference(TextBlock.ForegroundProperty, "Subtle");
            return new ListBoxItem { Content = title, IsHitTestVisible = false, Focusable = false };
        }

        bool ShowingSuggestions() => page == "search" && activeSearch == null && string.IsNullOrWhiteSpace(searchBox.Text);

        // With the search box empty: our recommended stations, then the popular ones. Loaded once per run, kept in memory.
        async void ShowSuggestions()
        {
            if (!ShowingSuggestions()) return;
            string loadingText = L("Loading suggestions…");
            string unavailable = L("The station directory is unavailable right now. Try again.");
            // A change of language can change the country (Storage.CurrentCountry): then they load again.
            Storage.SuggestionList shown = suggestions?.Country == Storage.CurrentCountry() ? suggestions : null;
            if (shown == null)
            {
                results.Items.Clear();
                searchStatus.Text = loadingText;
                if (loadingNow) return;
                loadingNow = true;
                try
                {
                    shown = await Storage.Suggestions(metadataClient, loadingSuggestions.Token);
                    if (shown.Complete) suggestions = shown;   // kept for the run only when nothing failed
                }
                catch (Exception error) when (error is HttpRequestException || error is OperationCanceledException)
                {
                    if (!loadingSuggestions.IsCancellationRequested && ShowingSuggestions()) searchStatus.Text = unavailable;
                }
                finally { loadingNow = false; }
                if (!ShowingSuggestions())
                {
                    // The user typed, searched or left meanwhile: do not leave the loading text behind.
                    if (activeSearch == null && searchStatus.Text == loadingText) searchStatus.Text = searchHint;
                    return;
                }
                if (shown == null) return;
            }
            results.Items.Clear();
            searchStatus.Text = shown.Complete ? searchHint : unavailable;
            if (shown.Recommended.Length > 0)
            {
                results.Items.Add(Heading(L("Recommended")));
                foreach (DirectoryStation item in shown.Recommended) results.Items.Add(ResultRow(item));
            }
            if (shown.Popular.Length > 0)
            {
                results.Items.Add(Heading(shown.Country != null ? L("Popular in your country")
                    : L("Popular worldwide")));
                foreach (DirectoryStation item in shown.Popular) results.Items.Add(ResultRow(item));
            }
        }

        // Leaving the search page: no results kept, no request left running.
        void ResetSearch()
        {
            activeSearch?.Cancel();
            activeSearch = null;
            searchButton.IsEnabled = true;
            results.Items.Clear();
            searchStatus.Text = searchHint;
            resetting = true;   // clearing the box must not start the suggestions again
            searchBox.Text = "";
            resetting = false;
        }

        // Pages: "stations", "search" (Add a station), "form" (Add by address, Edit), "history", "settings", "statistics".
        void SetPage(string target)
        {
            if (target != "form") editing = null;
            if (page == "search" && target != "search") ResetSearch();
            page = target;
            bool stations = target == "stations";
            Visibility Shown(bool shown) => shown ? Visibility.Visible : Visibility.Collapsed;
            list.Visibility = footer.Visibility = stationsBar.Visibility = Shown(stations);
            pageBar.Visibility = Shown(!stations);
            searchPane.Visibility = Shown(target == "search");
            fields.Visibility = Shown(target == "form");
            settingsPane.Visibility = Shown(target == "settings");
            historyPane.Visibility = Shown(target == "history");
            statisticsPane.Visibility = Shown(target == "statistics");
            pageTitle.Text = target == "settings" ? L("Settings")
                : target == "history" ? L("Song history")
                : target == "statistics" ? L("Statistics")
                : target == "search" ? L("Add a station")
                : target == "form" ? (editing == null ? L("Add by address") : L("Edit")) : "";
            if (target == "search")
            {
                app.Dispatcher.BeginInvoke(DispatcherPriority.Loaded, new Action(() => searchBox.Focus()));
                ShowSuggestions();
            }
            if (target == "settings") settingsPane.ScrollToTop();
            if (target == "history")
            {
                FillHistory();
                historyPane.ScrollToTop();
            }
            if (target == "statistics")
            {
                FillStatistics();
                statisticsPane.ScrollToTop();
            }
            if (stations) ShowActiveStationAfterLayout(false);
        }

        // ← and Esc: the station form goes back to where it came from, Statistics to Settings, the rest to the stations.
        void GoBack()
        {
            if (page == "form") CancelForm();
            else if (page == "statistics") SetPage("settings");
            else SetPage("stations");
        }

        add.Click += (_, _) => SetPage("search");
        searchButton.Click += (_, _) => Search();
        searchBox.KeyDown += (_, e) => { if (e.Key == Key.Enter) Search(); };
        // Clearing the box drops the results (and a running search) and brings the suggestions back.
        searchBox.TextChanged += (_, _) =>
        {
            if (resetting || page != "search" || !string.IsNullOrWhiteSpace(searchBox.Text)) return;
            activeSearch?.Cancel();
            activeSearch = null;
            searchButton.IsEnabled = true;
            results.Items.Clear();
            searchStatus.Text = searchHint;
            ShowSuggestions();
        };
        manual.Click += (_, _) => Edit(null);
        settingsButton.Click += (_, _) => SetPage("settings");
        historyButton.Click += (_, _) => SetPage("history");
        backButton.Click += (_, _) => GoBack();

        // Adding goes back to the search, editing to the stations.
        void CancelForm() => SetPage(editing == null ? "search" : "stations");
        cancelForm.Click += (_, _) => CancelForm();

        void AddSearchResult(DirectoryStation item)
        {
            string address = Storage.IsWebUrl(item.ResolvedUrl) ? item.ResolvedUrl : item.Url;
            if (Stations.Any(entry => Storage.SameStream(entry.Url, address)))
            {
                searchStatus.Text = L("This station is already on the list.");
                return;
            }
            var added = new SavedStation { Name = item.Name.Trim(), Url = address, Logo = Storage.IsWebUrl(item.Logo) ? item.Logo : null };
            if (!ApplyStations(Stations.Concat(new[] { added }).ToList())) return;
            if (station < 0) SelectStation(Stations.IndexOf(added));
            list.SelectedIndex = station;
            SetPage("stations");
        }

        save.Click += (_, _) =>
        {
            string label = name.Text?.Trim();
            string address = url.Text?.Trim();
            string logoAddress = logo.Text?.Trim();
            if (string.IsNullOrEmpty(label) || !Storage.IsWebUrl(address) ||
                (!string.IsNullOrEmpty(logoAddress) && !Storage.IsWebUrl(logoAddress)))
            {
                message.Text = L("Enter a name and a valid stream address. The logo is optional.");
                return;
            }
            if (Stations.Any(item => item != editing && Storage.SameStream(item.Url, address)))
            {
                message.Text = L("This address is already on the list.");
                return;
            }

            var entry = new SavedStation { Name = label, Url = address, Logo = string.IsNullOrEmpty(logoAddress) ? null : logoAddress };
            int editedIndex = editing == null ? -1 : Stations.IndexOf(editing);
            bool wasSelected = editedIndex >= 0 && editedIndex == station;
            var updated = editing == null ? Stations.Concat(new[] { entry }).ToList()
                : Stations.Select(item => item == editing ? entry : item).ToList();
            if (!ApplyStations(updated)) return;
            if (wasSelected) station = editedIndex;
            list.SelectedIndex = station;
            if (lastPlayed != null && lastPlayed == editing?.Url)
            {
                lastPlayed = address;
                SavePreferences();
            }
            if (wasSelected && session != null && editing.Url != address) StartPlayback();
            else if (wasSelected && session != null && status == editing.Name) SetStatus(entry.Name);
            if (station < 0) SelectStation(Stations.IndexOf(entry));
            SetPage("stations");
        };

        void Remove(SavedStation item)
        {
            int index = Stations.IndexOf(item);
            bool active = index == station;
            if (index < 0 || !ApplyStations(Stations.Where(entry => entry != item).ToList())) return;
            if (active)
            {
                station = -1;
                StopPlayback();
                SetTrayText(AppName);
            }
            list.SelectedIndex = station;
            if (lastPlayed == item.Url)
            {
                lastPlayed = null;
                SavePreferences();
            }
            if (editing == item && page == "form") SetPage("stations");
        }

        // Puts a station in another place on the list (dragged there, or Alt+↑/↓) and saves the order like any other
        // change; the current station follows by identity and keeps playing. Only its row moves: the list isn't built
        // again, so the other rows keep their logos and nothing flickers.
        bool MoveStation(SavedStation item, int target)
        {
            int index = Stations.IndexOf(item);
            var row = list.Items.OfType<FrameworkElement>().FirstOrDefault(entry => entry.Tag == item);
            if (index < 0 || target < 0 || target >= Stations.Count || target == index || row == null) return false;
            var updated = Stations.ToList();
            updated.RemoveAt(index);
            updated.Insert(target, item);
            if (!SaveStations(updated)) return false;
            SavedStation active = station >= 0 && station < Stations.Count ? Stations[station] : null;
            Stations.RemoveAt(index);
            Stations.Insert(target, item);
            if (active != null) station = Stations.IndexOf(active);
            // The list scrolls by whole stations; it keeps the same offset, so the rows stay where the drop showed them.
            ScrollViewer viewer = Descendants(list).OfType<ScrollViewer>().FirstOrDefault();
            double offset = viewer?.VerticalOffset ?? 0;
            list.Items.Remove(row);
            list.Items.Insert(target, row);
            list.SelectedIndex = station;
            shownStation = station;
            list.UpdateLayout();
            viewer?.ScrollToVerticalOffset(offset);
            list.UpdateLayout();
            return true;
        }
        drag.Move = MoveStation;

        // A search result: logo, name, then country · format · genres, and + (or a tick when it's already on the list).
        FrameworkElement ResultRow(DirectoryStation item)
        {
            Grid badge = LogoBadge(item.Logo, 32);
            var details = new List<string>();
            if (!string.IsNullOrWhiteSpace(item.Country)) details.Add(item.Country.Trim());
            string format = (item.Codec ?? "").Trim().ToUpperInvariant();
            if (format == "UNKNOWN") format = "";
            if (item.Bitrate > 0) format = (format + " " + item.Bitrate + " kbps").Trim();
            if (format.Length > 0) details.Add(format);
            string genres = string.Join(", ", (item.Tags ?? "").Split(',').Select(tag => tag.Trim()).Where(tag => tag.Length > 0).Take(2));
            if (genres.Length > 0) details.Add(genres);
            var name = new TextBlock { Text = item.Name.Trim(), FontSize = 15, TextTrimming = TextTrimming.CharacterEllipsis };
            TextBlock info = Note(string.Join(" · ", details));
            info.TextWrapping = TextWrapping.NoWrap;
            info.TextTrimming = TextTrimming.CharacterEllipsis;
            var text = Spaced(Orientation.Vertical, 1, name, info);
            text.Margin = new Thickness(12, 0, 8, 0);
            text.VerticalAlignment = VerticalAlignment.Center;
            string address = Storage.IsWebUrl(item.ResolvedUrl) ? item.ResolvedUrl : item.Url;
            bool known = Stations.Any(entry => Storage.SameStream(entry.Url, address));
            FrameworkElement mark = Theme.Glyph(known ? Theme.CheckIcon : Theme.PlusIcon, 18, known ? "Success" : null);
            mark.VerticalAlignment = VerticalAlignment.Center;
            var button = NewButton("GhostButton", Columns((badge, Auto), (text, Star), (mark, Auto)),
                known ? L("Already on your list") : L("Add to your stations"));
            button.HorizontalContentAlignment = HorizontalAlignment.Stretch;
            button.Padding = new Thickness(10, 6, 10, 6);
            button.Click += (_, _) => AddSearchResult(item);
            return button;
        }

        FrameworkElement StationRow(SavedStation item)
        {
            Grid badge = LogoBadge(item.Logo, 32);
            var text = new TextBlock
            {
                Text = item.Name, TextTrimming = TextTrimming.CharacterEllipsis,
                VerticalAlignment = VerticalAlignment.Center, Margin = new Thickness(12, 0, 0, 0)
            };
            // Shown while this station plays (RefreshPanel), like the Linux and Mac lists.
            FrameworkElement playing = Theme.Solid(Theme.PlayIcon, 14, "Accent");
            playing.VerticalAlignment = VerticalAlignment.Center;
            playing.Margin = new Thickness(8, 0, 4, 0);
            playing.Visibility = Visibility.Collapsed;
            playingMarks[item] = playing;
            var stationButton = NewButton("GhostButton", Columns((badge, Auto), (text, Star), (playing, Auto)));
            stationButton.HorizontalContentAlignment = HorizontalAlignment.Stretch;
            stationButton.Padding = new Thickness(10, 6, 8, 6);
            stationButton.FontSize = 16;
            stationButton.Click += (_, _) =>
            {
                int position = Stations.IndexOf(item);
                if (position < 0) return;
                SelectStation(position);
                if (session == null) StartPlayback();
                list.SelectedIndex = station;
            };
            var actions = NewButton("GhostButton", Theme.Glyph(Theme.MoreIcon), L("Station options"));
            actions.Padding = new Thickness(8, 6, 8, 6);
            actions.Margin = new Thickness(4, 0, 0, 0);
            var options = new ContextMenu { PlacementTarget = actions, Placement = PlacementMode.Bottom };
            // No Move up / Move down: the station is dragged instead (or moved with Alt+↑/↓).
            options.Items.Add(Item(L("Edit"), null, () => Edit(item)));
            options.Items.Add(new Separator());
            options.Items.Add(Item(L("Remove"), null, () => Remove(item)));
            Hold(options);
            actions.Click += (_, _) => options.IsOpen = true;
#if SELFTEST
            actions.Tag = options;   // the self-test reads the menu from here
#endif
            var row = (Grid)Columns((stationButton, Star), (actions, Auto));
            row.MinHeight = 47;
            row.Tag = item;
            drag.Attach(row, actions);
            return row;
        }

        // History page: the songs the radio played, newest first, each with its station's logo (found by the station's
        // name, as the history keeps it; the radio icon for a station without one or no longer on the list).
        int shownHistory = -1;
        void FillHistory()
        {
            shownHistory = historyVersion;
            var content = new StackPanel { Margin = new Thickness(Gutter) };
            if (history.Count == 0)
            {
                content.Children.Add(Note(L("Songs the radio plays will show up here.")));
                historyPane.Content = content;
                return;
            }
            CultureInfo culture = Culture;
            var rows = new StackPanel();
            foreach (HistoryEntry entry in history)
            {
                if (rows.Children.Count > 0) rows.Children.Add(Divider(new Thickness(0)));
                DateTime time = entry.Time.ToLocalTime();
                Grid badge = LogoBadge(Stations.FirstOrDefault(item => item.Name == entry.Station)?.Logo, 32);
                badge.Margin = new Thickness(0, 0, 12, 0);
                var text = new StackPanel { VerticalAlignment = VerticalAlignment.Center, Margin = new Thickness(0, 7, 4, 7), ToolTip = entry.Title };
                text.Children.Add(new TextBlock { Text = entry.Title, FontSize = 14, TextTrimming = TextTrimming.CharacterEllipsis });
                TextBlock where = Note(entry.Station + " · " + time.ToString(time.Date == DateTime.Today ? "HH:mm" : "d MMM, HH:mm", culture));
                where.TextWrapping = TextWrapping.NoWrap;
                where.TextTrimming = TextTrimming.CharacterEllipsis;
                text.Children.Add(where);
                var more = NewButton("GhostButton", Theme.Glyph(Theme.MoreIcon), L("More"));
                more.Padding = new Thickness(8, 6, 8, 6);
                more.VerticalAlignment = VerticalAlignment.Center;
                string query = Uri.EscapeDataString(entry.Title.Replace(" – ", " ").Replace(" - ", " "));
                var menu = new ContextMenu { PlacementTarget = more, Placement = PlacementMode.Bottom };
                menu.Items.Add(Item(L("Copy"), Theme.CopyIcon, () =>
                {
                    if (CopyText(entry.Title)) ShowNotice(more);
                    else message.Text = L("The clipboard is busy.");
                }));
                menu.Items.Add(Item(L("Search on Spotify"), null,
                    () => OpenWebPage("https://open.spotify.com/search/" + query)));
                menu.Items.Add(Item(L("Search on YouTube"), null,
                    () => OpenWebPage("https://www.youtube.com/results?search_query=" + query)));
                Hold(menu);
                more.Click += (_, _) => menu.IsOpen = true;
                var row = (Grid)Columns((badge, Auto), (text, Star), (more, Auto));
                row.MinHeight = 50;
                row.Margin = new Thickness(10, 0, 4, 0);
                rows.Children.Add(row);
            }
            content.Children.Add(CardFrame(rows, new Thickness(0)));
            var clear = SmallButton("LinkButton", L("Clear history"));
            clear.HorizontalAlignment = HorizontalAlignment.Left;
            clear.Margin = new Thickness(-4, 6, 0, 0);
            clear.Click += (_, _) => { ClearHistory(); FillHistory(); };
            content.Children.Add(clear);
            historyPane.Content = content;
        }

        void FillStatistics() { }

        // Settings page, laid out like the Windows 11 Settings app (and like the Linux and Mac apps): General, Stations,
        // Statistics, Updates, About and Quit, each one card of rows.
        Action refreshUpdates = null;
        FrameworkElement BuildSettings()
        {
            var settings = new StackPanel { Margin = new Thickness(Gutter) };

            // General: language, start with Windows
            var language = new ComboBox { MinWidth = 136 };
            language.Items.Add(L("Same as Windows"));
            foreach (var (_, ownName) in Languages) language.Items.Add(ownName);   // each language by its own name
            string[] languages = new[] { "auto" }.Concat(Languages.Select(item => item.Code)).ToArray();
            language.SelectedIndex = Math.Max(0, Array.IndexOf(languages, Lang.Setting));
            language.SelectionChanged += (_, _) =>
            {
                string value = languages[language.SelectedIndex];
                if (Lang.Setting == value) return;
                Lang.Setting = value;
                SavePreferences();
                if (session == null) SetStatus(Ready);
                // Every label is created in the chosen language: build the panel again, still on this page.
                Post(() =>
                {
                    panel.Close();
                    OpenPlayer("settings");
                });
            };
            settings.Children.Add(Group(L("General"), true));
            settings.Children.Add(SettingsCard(
                SettingRow(L("Language"), L("In Windows: {0}", LanguageName(SystemLanguage)), language),
                SettingRow(L("Start with Windows"), L("Waits by the clock, doesn't play by itself"),
                    Toggle(Autostart.Enabled, on => Autostart.Set(on, Exe))),
                SettingRow(L("Show station changes"), L("A card at the bottom after a media key or menu switch"),
                    Toggle(showStationPopup, on => { showStationPopup = on; SavePreferences(); }))));

            // Stations: export / import (e.g. to give someone your list); what happened shows left of the buttons.
            var stationsNote = Note("");
            stationsNote.VerticalAlignment = VerticalAlignment.Center;
            void Report(string text) => stationsNote.Text = text;
            var export = RowButton(L("Export…"));
            var import = RowButton(L("Import…"));
            import.Margin = new Thickness(8, 0, 0, 0);
            export.Click += (_, _) =>
            {
                var dialog = new Microsoft.Win32.SaveFileDialog
                {
                    FileName = AppName + " - " + L("stations") + ".json", DefaultExt = ".json",
                    Filter = L("Station list") + " (*.json)|*.json"
                };
                holdOpen++;
                try
                {
                    if (dialog.ShowDialog(panel) != true) return;
                    Storage.Write(dialog.FileName, Stations);
                    Report(L("Stations saved: {0}.", Stations.Count));
                }
                catch (Exception error) when (error is IOException || error is UnauthorizedAccessException)
                {
                    Report(L("Couldn't save the file."));
                }
                finally { holdOpen--; }
            };
            import.Click += (_, _) =>
            {
                var dialog = new Microsoft.Win32.OpenFileDialog
                {
                    Filter = L("Station list") + " (*.json)|*.json|" + L("All files") + "|*.*"
                };
                holdOpen++;
                try
                {
                    if (dialog.ShowDialog(panel) != true) return;
                    List<SavedStation> loaded = Storage.Read<List<SavedStation>>(dialog.FileName);
                    if (loaded == null)
                    {
                        Report(L("This isn't a Minimalistic Radio station list."));
                        return;
                    }
                    var fresh = loaded
                        .Where(item => item != null && !string.IsNullOrWhiteSpace(item.Name) && Storage.IsWebUrl(item.Url) &&
                            !Stations.Any(known => Storage.SameStream(known.Url, item.Url)))
                        .GroupBy(item => Storage.StreamKey(item.Url)).Select(same => same.First())
                        .Select(item => new SavedStation { Name = item.Name.Trim(), Url = item.Url, Logo = Storage.IsWebUrl(item.Logo) ? item.Logo : null })
                        .ToList();
                    if (fresh.Count == 0) Report(L("All stations from this file are already on the list."));
                    else if (ApplyStations(Stations.Concat(fresh).ToList())) Report(L("Stations added: {0}.", fresh.Count));
                }
                finally { holdOpen--; }
            };
            settings.Children.Add(Group(L("Stations")));
            var transfer = Columns((stationsNote, Star), (export, Auto), (import, Auto));
            transfer.Margin = new Thickness(14, 10, 14, 10);
            settings.Children.Add(SettingsCard(SettingRow(L("Station list"), L("A copy in a file, e.g. for friends"), null), transfer));

            // Statistics: a card of its own, without a group title.
            var showStatistics = RowButton(L("Show"));
            showStatistics.Click += (_, _) => SetPage("statistics");
            Border statisticsCard = SettingsCard(SettingRow(L("Statistics"), L("Collected only on this computer, never sent anywhere"), showStatistics));
            statisticsCard.Margin = new Thickness(0, 18, 0, 0);
            settings.Children.Add(statisticsCard);

            // Updates
            var updateNote = Note("");
            updateNote.VerticalAlignment = VerticalAlignment.Center;
            var updateDescription = Note("");
            var checkNow = RowButton("");
            checkNow.Margin = new Thickness(8, 0, 0, 0);
            checkNow.Click += (_, _) =>
            {
                if (readyUpdate != null && !installing) InstallUpdate();
                else CheckForUpdates(true);
            };
            refreshUpdates = () =>
            {
                CultureInfo culture = Culture;
                DateTime? checkedAt = lastUpdateCheck?.ToLocalTime();
                updateDescription.Text = readyUpdate != null
                    ? L("Version {0} is ready to install", readyUpdate.Version.ToString(3))
                    : L("Looks for a new version every few hours");
                updateNote.Text = updateStatus ?? (checkedAt == null ? L("Not checked yet.")
                    : L("Last checked: {0}",
                      checkedAt.Value.ToString(checkedAt.Value.Date == DateTime.Today ? "HH:mm" : "d MMM, HH:mm", culture)));
                checkNow.Content = readyUpdate != null ? L("Update") : L("Check now");
                checkNow.SetResourceReference(FrameworkElement.StyleProperty, readyUpdate != null ? "AccentButton" : (object)typeof(Button));
                checkNow.IsEnabled = !installing && !checking;
            };
            refreshUpdates();
            settings.Children.Add(Group(L("Updates")));
            var lastCheck = Columns((updateNote, Star), (checkNow, Auto));
            lastCheck.Margin = new Thickness(14, 10, 14, 10);
            settings.Children.Add(SettingsCard(
                SettingRow(L("Updates"), updateDescription, Toggle(checkUpdates, on => { checkUpdates = on; SavePreferences(); })),
                lastCheck));

            // About: the round app icon (as many pixels as the screen shows), the version and a link to the project.
            int iconPixels = (int)Math.Round(32 * VisualTreeHelper.GetDpi(panel).DpiScaleX);
            var appIcon = new Image { Source = Theme.AppImage(iconPixels), Width = 32, Height = 32 };
            RenderOptions.SetBitmapScalingMode(appIcon, BitmapScalingMode.HighQuality);
            settings.Children.Add(Group(L("About")));
            settings.Children.Add(SettingsCard(SettingRow(AppName,
                L("Version {0}", Updater.Current.ToString(3)) + " · MIT · " + L("Lucide icons"), Link("GitHub", Updater.Page), appIcon)));

            // Quitting is rare and stops the music, so it lives here and in the tray menu, not next to Play.
            var quit = RowButton(L("Quit Minimalistic Radio"));
            quit.SetResourceReference(Control.ForegroundProperty, "Danger");
            quit.HorizontalAlignment = HorizontalAlignment.Left;
            quit.Margin = new Thickness(14, 12, 14, 12);
            quit.Click += (_, _) => Shutdown();
            Border quitCard = SettingsCard(quit);
            quitCard.Margin = new Thickness(0, 18, 0, 0);
            settings.Children.Add(quitCard);
            return settings;
        }
        settingsPane.Content = BuildSettings();

        // Footer: now playing, volume with the sleep timer, play/stop.
        // The volume row is like Windows 11's: a speaker button that shows the level and mutes, the slider, and the
        // number in a bubble above the knob while the volume changes by hand. With no label, the slider is named.
        AutomationProperties.SetName(volumeSlider, L("Volume"));
        var muteButton = NewButton("GhostButton", null);
        muteButton.Padding = new Thickness(8, 6, 8, 6);
        muteButton.Margin = new Thickness(-4, 0, 6, 0);
        muteButton.VerticalAlignment = VerticalAlignment.Center;
        void ShowVolume()
        {
            string glyph = VolumeGlyph(volume);
            if (Equals(muteButton.Tag, glyph)) return;
            muteButton.Tag = glyph;
            muteButton.Content = Theme.Glyph(glyph);
            string tip = volume == 0 ? L("Unmute") : L("Mute");
            muteButton.ToolTip = tip;
            AutomationProperties.SetName(muteButton, tip);
        }
        muteButton.Click += (_, _) =>
        {
            ToggleMute();
            volumeSlider.Value = volume;
            ShowVolume();
        };
        // The bubble lives in the panel (a layer over the slider that may draw above it), not in a popup window, so it
        // needs no window of its own, follows the theme like the rest, and shows in the self-test's pictures. It goes
        // a second after the last wheel turn or key, or when a drag lets go.
        Grid bubble = NewBubble(out TextBlock bubbleText);
        var bubbleLayer = new Canvas { IsHitTestVisible = false };
        bubbleLayer.Children.Add(bubble);
        var sliderCell = new Grid();
        sliderCell.Children.Add(volumeSlider);
        sliderCell.Children.Add(bubbleLayer);
        var bubbleTimer = new DispatcherTimer { Interval = TimeSpan.FromSeconds(1) };
        void HideBubble()
        {
            bubbleTimer.Stop();
            bubble.Visibility = Visibility.Collapsed;
        }
        bubbleTimer.Tick += (_, _) => HideBubble();
        panel.Closed += (_, _) => bubbleTimer.Stop();
        void ShowBubble(bool untilRelease)
        {
            if (!(volumeSlider.Template?.FindName("PART_Track", volumeSlider) is Track track) || track.Thumb == null) return;
            bubbleText.Text = ((int)Math.Round(volumeSlider.Value)).ToString(CultureInfo.InvariantCulture);
            bubble.Visibility = Visibility.Visible;
            sliderCell.UpdateLayout();   // the knob where the new value puts it, the bubble at its new width
            Point knob = track.Thumb.TranslatePoint(new Point(track.Thumb.ActualWidth / 2, 0), bubbleLayer);
            Canvas.SetLeft(bubble, Math.Round(knob.X - bubble.ActualWidth / 2));
            Canvas.SetTop(bubble, Math.Round(knob.Y - bubble.ActualHeight - 4));
            bubbleTimer.Stop();
            if (!untilRelease) bubbleTimer.Start();
        }
        volumeSlider.ValueChanged += (_, e) =>
        {
            ChangeVolume((int)Math.Round(e.NewValue));
            ShowVolume();
        };
        // Like the Windows 11 volume slider: press anywhere on it and drag (WPF on its own only jumps
        // there and drags just the knob), and the mouse wheel changes the volume by 2%.
        void SlideTo(MouseEventArgs e)
        {
            if (volumeSlider.Template?.FindName("PART_Track", volumeSlider) is Track track)
                volumeSlider.Value = Math.Round(Math.Max(0, Math.Min(100, track.ValueFromPoint(e.GetPosition(track)))));
            ShowBubble(true);
        }
        // handledEventsToo: with IsMoveToPointEnabled the Slider itself marks a press next to the knob as
        // handled (it only jumps there), and a plain += handler would never see it.
        volumeSlider.AddHandler(UIElement.PreviewMouseLeftButtonDownEvent, new MouseButtonEventHandler((_, e) =>
        {
            volumeSlider.Focus();
            SlideTo(e);
            volumeSlider.CaptureMouse();
            e.Handled = true;
        }), true);
        volumeSlider.PreviewMouseMove += (_, e) =>
        {
            if (volumeSlider.IsMouseCaptured && e.LeftButton == MouseButtonState.Pressed) SlideTo(e);
        };
        volumeSlider.PreviewMouseLeftButtonUp += (_, e) =>
        {
            if (!volumeSlider.IsMouseCaptured) return;
            volumeSlider.ReleaseMouseCapture();
            e.Handled = true;
        };
        volumeSlider.LostMouseCapture += (_, _) => HideBubble();
        volumeSlider.MouseWheel += (_, e) =>
        {
            volumeSlider.Value = Clamp((int)volumeSlider.Value + (e.Delta > 0 ? 2 : -2), 0, 100);
            ShowBubble(false);
            e.Handled = true;
        };
        // handledEventsToo: the Slider handles its keys itself; this runs after, with the new value.
        volumeSlider.AddHandler(UIElement.KeyDownEvent, new KeyEventHandler((_, e) =>
        {
            if (e.Key == Key.Left || e.Key == Key.Right || e.Key == Key.Up || e.Key == Key.Down ||
                e.Key == Key.PageUp || e.Key == Key.PageDown || e.Key == Key.Home || e.Key == Key.End)
                ShowBubble(false);
        }), true);
        play.Click += (_, _) => TogglePlayback();
        var copy = NewButton("GhostButton", Theme.Glyph(Theme.CopyIcon), L("Copy title"));
        copy.Padding = new Thickness(8);
        copy.VerticalAlignment = VerticalAlignment.Center;
        copy.Click += (_, _) =>
        {
            if (track == null) return;
            if (!CopyText(track))
            {
                message.Text = L("The clipboard is busy.");
                return;
            }
            copy.Content = Theme.Glyph(Theme.CheckIcon);
            ShowNotice(copy, () => copy.Content = Theme.Glyph(Theme.CopyIcon));
        };

        var sleepButton = NewButton("GhostButton", null, L("Sleep timer"));
        sleepButton.Padding = new Thickness(8, 6, 8, 6);
        sleepButton.Margin = new Thickness(6, 0, -4, 0);
        sleepButton.Click += (_, _) =>
        {
            var menu = new ContextMenu { PlacementTarget = sleepButton, Placement = PlacementMode.Top };
            FillSleepMenu(menu);
            Hold(menu);
            menu.IsOpen = true;
        };
        var sleepText = Note("");
        sleepText.VerticalAlignment = VerticalAlignment.Center;
        var cancelSleep = SmallButton("LinkButton", L("Cancel"));
        cancelSleep.Click += (_, _) => SetSleepTimer(null);
        var sleepRow = Columns((sleepText, Star), (cancelSleep, Auto));
        bool? shownSleep = null;

        var cover = new Image { Width = 42, Height = 42, Stretch = Stretch.Uniform };
        var fallback = Theme.Glyph(Theme.MusicIcon);
        var coverBox = new Grid { Width = 42, Height = 42, ClipToBounds = true };
        coverBox.Children.Add(fallback);
        coverBox.Children.Add(cover);
        string displayedArtwork = null;
        var caption = new TextBlock { Text = L("Now playing"), FontSize = 11, Opacity = 0.75 };
        var trackInfo = Spaced(Orientation.Vertical, 2, caption, now);
        trackInfo.VerticalAlignment = VerticalAlignment.Center;
        trackInfo.Margin = new Thickness(10, 0, 10, 0);
        var trackCard = new Border
        {
            CornerRadius = new CornerRadius(6), Padding = new Thickness(10, 6, 6, 6),
            Child = Columns((coverBox, Auto), (trackInfo, Star), (copy, Auto))
        };
        trackCard.SetResourceReference(Border.BackgroundProperty, "Card");

        var volumeRow = Columns((muteButton, Auto), (sliderCell, Star), (sleepButton, Auto));
        play.HorizontalAlignment = HorizontalAlignment.Stretch;
        footer.Child = Spaced(Orientation.Vertical, 10, trackCard, volumeRow, sleepRow, play);

        var middle = new Grid();
        foreach (FrameworkElement part in new FrameworkElement[] { list, searchPane, fields, settingsPane, historyPane, statisticsPane })
            middle.Children.Add(part);
        var content = new DockPanel { LastChildFill = true };
        DockPanel.SetDock(header, Dock.Top);
        DockPanel.SetDock(footer, Dock.Bottom);
        content.Children.Add(header);
        content.Children.Add(footer);
        content.Children.Add(middle);

        // No padding: the bar's line goes from edge to edge; each part keeps its own 12 px from the sides.
        var frame = new Border
        {
            BorderThickness = new Thickness(1), CornerRadius = new CornerRadius(8), Child = content
        };
        frame.SetResourceReference(Border.BackgroundProperty, "Bg");
        frame.SetResourceReference(Border.BorderBrushProperty, "Line");
        // The shadow sits on its own layer so the text above it keeps sharp ClearType rendering.
        var shadow = new Border
        {
            CornerRadius = new CornerRadius(8), Background = Brushes.Black,
            Effect = new DropShadowEffect { BlurRadius = 14, ShadowDepth = 2, Opacity = 0.3, Direction = 270 }
        };
        var root = new Grid { Margin = new Thickness(ShadowMargin) };
        root.Children.Add(shadow);
        root.Children.Add(frame);
        root.Children.Add(noticeLayer);
        panel.Content = root;
        FillList();
        SetPage(startPage);
        if (startSearch != null)
        {
            searchBox.Text = startSearch;
            searchBox.CaretIndex = startSearch.Length;
            SetPage("search");
            Search();
        }

        panel.KeyDown += (_, e) =>
        {
            if (e.Key != Key.Escape) return;
            if (page != "stations") GoBack();
            else panel.Close();
            e.Handled = true;
        };

        async void RefreshArtwork(string address)
        {
            cover.Source = null;
            fallback.Visibility = Visibility.Visible;
            ImageSource source = await LoadImage(address);
            if (source == null || displayedArtwork != address || playerPanel != panel) return;
            cover.Source = source;
            fallback.Visibility = Visibility.Hidden;
        }

        int shownUpdate = -1;
        void RefreshPanel()
        {
            string picture = CoverUrl;
            if (displayedArtwork != picture)
            {
                displayedArtwork = picture;
                RefreshArtwork(picture);
            }
            play.IsEnabled = Stations.Count > 0;
            list.SelectedIndex = station;
            if (station != shownStation)
            {
                // The station changed (media keys, tray menu, taskbar players…): bring it into view, but leave
                // the list alone otherwise, so scrolling through it by hand isn't undone.
                shownStation = station;
                ShowActiveStation(false);
            }
            string playText = session == null ? L("Play") : L("Stop");
            if (!Equals(play.Tag, playText))
            {
                play.Tag = playText;
                play.Content = PlayLabel(session == null, playText);
            }
            SavedStation playing = session != null && station >= 0 && station < Stations.Count ? Stations[station] : null;
            foreach (KeyValuePair<SavedStation, FrameworkElement> mark in playingMarks)
                mark.Value.Visibility = mark.Key == playing ? Visibility.Visible : Visibility.Collapsed;
            copy.IsEnabled = track != null;
            now.Text = track ?? (session != null && status == StationName ? NoTrack : status);
            now.ToolTip = track;
            volumeSlider.Value = volume;
            ShowVolume();
            bool sleeping = sleepAt != null;
            if (shownSleep != sleeping)
            {
                shownSleep = sleeping;
                sleepButton.Content = Theme.Glyph(Theme.MoonIcon, 18, sleeping ? "Accent" : null);
                sleepRow.Visibility = sleeping ? Visibility.Visible : Visibility.Collapsed;
            }
            if (sleeping) sleepText.Text = SleepLabel;
            if (shownUpdate != updateVersion)
            {
                shownUpdate = updateVersion;
                updateButton.Visibility = readyUpdate != null && !installing ? Visibility.Visible : Visibility.Collapsed;
                refreshUpdates?.Invoke();
            }
            if (page == "history" && shownHistory != historyVersion) FillHistory();
        }

        var timer = new DispatcherTimer { Interval = TimeSpan.FromMilliseconds(250) };
        timer.Tick += (_, _) => RefreshPanel();
        // Clicking anywhere outside the panel closes it, like the Windows flyouts.
        bool pointerDown = true;
        var dismiss = new DispatcherTimer { Interval = TimeSpan.FromMilliseconds(40) };
        dismiss.Tick += (_, _) =>
        {
            bool down = GetAsyncKeyState(1) < 0 || GetAsyncKeyState(2) < 0;
            if (down && !pointerDown && holdOpen == 0)
            {
                IntPtr handle = new WindowInteropHelper(panel).Handle;
                System.Drawing.Point point = Forms.Cursor.Position;
                if (handle != IntPtr.Zero && GetWindowRect(handle, out Rect32 bounds) &&
                    (point.X < bounds.Left || point.X >= bounds.Right || point.Y < bounds.Top || point.Y >= bounds.Bottom))
                {
                    sinceDismiss.Restart();
                    panel.Close();
                }
            }
            pointerDown = down;
        };
        panel.Closed += (_, _) => { dismiss.Stop(); timer.Stop(); };
        RefreshPanel();

        // Always in the corner next to the notification area, 12 px from the screen edge and the taskbar,
        // like the Windows 11 flyouts — wherever the panel was opened from (tray, a taskbar player, Start menu).
        void PositionPanel()
        {
            IntPtr handle = new WindowInteropHelper(panel).Handle;
            if (handle == IntPtr.Zero || playerPanel != panel || !GetWindowRect(handle, out Rect32 bounds)) return;
            var (area, edge) = TrayCorner();
            const double Gap = 12;
            double scale = VisualTreeHelper.GetDpi(panel).DpiScaleY;
            double fit = area.Height / scale + 2 * (ShadowMargin - Gap);
            if (panel.Height > fit) { panel.Height = Math.Max(200, fit); return; }
            int width = bounds.Right - bounds.Left, height = bounds.Bottom - bounds.Top;
            int inset = (int)Math.Round((Gap - ShadowMargin) * scale); // the shadow margin around the panel is transparent
            int x = edge == 0 ? area.Left + inset : area.Right - width - inset;   // taskbar on the left: left corner
            int y = edge == 1 ? area.Top + inset : area.Bottom - height - inset;   // taskbar at the top: top corner
            SetWindowPos(handle, IntPtr.Zero, x, y, 0, 0, 0x0001 | 0x0004 | 0x0010); // NOSIZE | NOZORDER | NOACTIVATE
        }
        panel.SourceInitialized += (_, _) => PositionPanel();
        panel.SizeChanged += (_, _) => Post(PositionPanel);
        panel.ContentRendered += (_, _) => { if (page == "stations") ShowActiveStation(true); };
        panel.Show();
        panel.Activate();
        Post(PositionPanel);
        timer.Start();
        dismiss.Start();
    }

    // Station logos (the list's and the search's), decoded, for the whole run: a list built again (language, add,
    // edit, remove, suggestions) shows them at once instead of fetching them again. A logo that didn't load stays
    // the radio icon until the next start. Kept as tasks, so rows asking for one still loading share the download.
    private const int LogoCacheSize = 200;
    private static readonly Dictionary<string, Task<ImageSource>> logos = new Dictionary<string, Task<ImageSource>>();
    private static readonly Queue<string> logoOrder = new Queue<string>();

    // A station's logo, or the radio icon while it loads and when there is none.
    private static Grid LogoBadge(string address, double size)
    {
        var image = new Image { Width = size, Height = size, Stretch = Stretch.Uniform };
        FrameworkElement placeholder = Theme.Glyph(Theme.RadioIcon, size < 32 ? 16 : 18);
        var badge = new Grid { Width = size, Height = size, VerticalAlignment = VerticalAlignment.Center };
        badge.Children.Add(placeholder);
        badge.Children.Add(image);
        image.Loaded += async (_, _) =>
        {
            if (image.Source != null) return;
            ImageSource source = await LoadLogo(address);
            if (source == null) return;
            image.Source = source;
            placeholder.Visibility = Visibility.Hidden;
        };
        return badge;
    }

    private static Task<ImageSource> LoadLogo(string address)
    {
        if (!Storage.IsWebUrl(address)) return Task.FromResult<ImageSource>(null);
        if (!logos.TryGetValue(address, out Task<ImageSource> logo)) CacheLogo(address, logo = LoadImage(address));
        return logo;
    }

    // Beyond the limit the oldest logos go first.
    private static void CacheLogo(string address, Task<ImageSource> logo)
    {
        if (!logos.ContainsKey(address)) logoOrder.Enqueue(address);
        logos[address] = logo;
        while (logos.Count > LogoCacheSize) logos.Remove(logoOrder.Dequeue());
    }

    private static async Task<ImageSource> LoadImage(string address)
    {
        if (!Storage.IsWebUrl(address)) return null;
        try
        {
            using (var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(5)))
            using (HttpResponseMessage response = await metadataClient.GetAsync(address, HttpCompletionOption.ResponseHeadersRead, timeout.Token))
            {
                if (!response.IsSuccessStatusCode || response.Content.Headers.ContentType?.MediaType?.StartsWith("image/") != true)
                    return null;
                var data = new MemoryStream();
                using (Stream input = await response.Content.ReadAsStreamAsync())
                {
                    var buffer = new byte[8192];
                    int count;
                    while ((count = await input.ReadAsync(buffer, 0, buffer.Length, timeout.Token)) > 0)
                    {
                        if (data.Length + count > 1024 * 1024) return null;
                        data.Write(buffer, 0, count);
                    }
                }
                data.Position = 0;
                var image = new BitmapImage();
                image.BeginInit();
                image.CacheOption = BitmapCacheOption.OnLoad;
                image.DecodePixelWidth = 120;
                image.StreamSource = data;
                image.EndInit();
                image.Freeze();
                return image;
            }
        }
        catch (Exception error)
        {
            Debug.WriteLine(error);
            return null;
        }
    }

    // The small bubble with a shadow, used by the volume value and by "Copied". It starts hidden; the caller places it.
    // The shadow is on a layer of its own, so the text keeps sharp ClearType rendering (like the panel's shadow).
    private static Grid NewBubble(out TextBlock text)
    {
        text = new TextBlock { FontSize = 12 };
        var face = new Border
        {
            CornerRadius = new CornerRadius(4), BorderThickness = new Thickness(1), Padding = new Thickness(8, 3, 8, 4), Child = text
        };
        face.SetResourceReference(Border.BackgroundProperty, "Bg");
        face.SetResourceReference(Border.BorderBrushProperty, "Line");
        var bubble = new Grid { Visibility = Visibility.Collapsed };
        bubble.Children.Add(new Border
        {
            CornerRadius = new CornerRadius(4), Background = Brushes.Black,
            Effect = new DropShadowEffect { BlurRadius = 8, ShadowDepth = 1, Opacity = 0.25, Direction = 270 }
        });
        bubble.Children.Add(face);
        return bubble;
    }

#if SELFTEST
    // Self-test of the copy feedback: the panel's bubble says "Copied" after the copy button, and the tray's card
    // reads "Copied to clipboard" on its second line. A busy clipboard is not a failure of the app, so it is skipped.
    private async Task VerifyCopyFeedback(bool preview)
    {
        track = "Test Artist - Test Song";
        playerPanel?.Close();
        OpenPlayer();
        await Task.Delay(500);
        string copied = L("Copied");
        Button copyButton = Descendants(playerPanel).OfType<Button>().First(button => button.ToolTip as string == L("Copy title"));
        copyButton.RaiseEvent(new RoutedEventArgs(ButtonBase.ClickEvent));
        var notice = (FrameworkElement)Descendants(playerPanel).OfType<Canvas>().First(layer => layer.Tag as string == "notice").Children[0];
        if (notice.IsVisible && Descendants(notice).OfType<TextBlock>().First().Text != copied)
            throw new InvalidOperationException("Dymek kopiowania ma zły tekst.");
        if (preview) await SavePreview(playerPanel, "copied");
        playerPanel.Close();
        CopyTrackFromMenu();
        if (osd?.IsVisible == true && osdText.Text != L("Copied to clipboard"))
            throw new InvalidOperationException("Karta kopiowania ma zły drugi wiersz.");
        osd?.Hide();
    }

    // Self-test of the volume row (--test-menu, from VerifyMenu): the speaker for 0, 20, 50 and 90%, mute and unmute,
    // and the number in the bubble on a wheel turn.
    private async Task VerifyVolumeRow()
    {
        playerPanel?.Close();
        OpenPlayer();
        await Task.Delay(500);
        var slider = Descendants(playerPanel).OfType<Slider>().First();
        string[] speakers = { Theme.VolumeMutedIcon, Theme.Volume1Icon, Theme.Volume2Icon, Theme.Volume3Icon };
        Button speaker = Descendants(playerPanel).OfType<Button>().First(button => speakers.Contains(button.Tag as string));
        for (int i = 0; i < 4; i++)
        {
            ChangeVolume(new[] { 0, 20, 50, 90 }[i]);
            await Task.Delay(300);   // the panel refreshes every 250 ms
            if (speaker.Tag as string != speakers[i]) throw new InvalidOperationException("Błędna ikona głośności przy " + volume + "%.");
        }
        speaker.RaiseEvent(new RoutedEventArgs(ButtonBase.ClickEvent));
        int muted = volume;
        speaker.RaiseEvent(new RoutedEventArgs(ButtonBase.ClickEvent));
        if (muted != 0 || volume != 90) throw new InvalidOperationException($"Wyciszanie: {muted}%, potem {volume}%.");
        slider.RaiseEvent(new MouseWheelEventArgs(Mouse.PrimaryDevice, Environment.TickCount, 120) { RoutedEvent = Mouse.MouseWheelEvent });
        var bubble = (FrameworkElement)((Panel)VisualTreeHelper.GetParent(slider)).Children.OfType<Canvas>().First().Children[0];
        if (volume != 92 || !bubble.IsVisible || Descendants(bubble).OfType<TextBlock>().First().Text != "92")
            throw new InvalidOperationException("Dymek głośności nie pokazuje wartości.");
        playerPanel.Close();
    }
#endif
}
