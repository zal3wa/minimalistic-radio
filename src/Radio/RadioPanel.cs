using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Net.Http;
using System.Runtime.InteropServices;
using System.Text.RegularExpressions;
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

    // The open panel's way to show a shared station's link: ("shared", the station or null) or ("stations", …).
    private Action<string, SharedStation> showInPanel;

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

    // A date in the language's long format without the weekday ("March 2, 2025", "2 marca 2025", "2. března 2025").
    private static string LongDate(DateTime date)
    {
        CultureInfo culture = Culture;
        return date.ToString(Regex.Replace(culture.DateTimeFormat.LongDatePattern, @"dddd[,.]?\s*", "").Trim(' ', ','), culture);
    }

    // A row's ⋯ menu, opened under the button with its right edge at the button's, so it stays over the panel.
    private static ContextMenu RowMenu(Button button) => new ContextMenu
    {
        PlacementTarget = button, Placement = PlacementMode.Custom,
        CustomPopupPlacementCallback = (popup, target, offset) =>
            new[] { new CustomPopupPlacement(new Point(target.Width - popup.Width, target.Height), PopupPrimaryAxis.Horizontal) }
    };

    // A card for a moment above the player ("Link copied"): a green tick and a line, with a shadow on a layer of its
    // own (sharp ClearType text). It starts hidden.
    private static Grid NewToast(out TextBlock text, out FrameworkElement tick)
    {
        tick = Theme.TickBadge(18);
        tick.VerticalAlignment = VerticalAlignment.Center;
        // Segoe UI sits low in its line: a pixel up puts the words level with the tick.
        text = new TextBlock { FontSize = 14, VerticalAlignment = VerticalAlignment.Center, Margin = new Thickness(10, 0, 0, 2) };
        var line = new StackPanel { Orientation = Orientation.Horizontal };
        line.Children.Add(tick);
        line.Children.Add(text);
        var face = new Border
        {
            Height = 40, CornerRadius = new CornerRadius(6), BorderThickness = new Thickness(1), Padding = new Thickness(12, 0, 16, 0), Child = line
        };
        face.SetResourceReference(Border.BackgroundProperty, "Card");
        face.SetResourceReference(Border.BorderBrushProperty, "Line");
        var toast = new Grid
        {
            Visibility = Visibility.Collapsed, IsHitTestVisible = false, HorizontalAlignment = HorizontalAlignment.Center,
            VerticalAlignment = VerticalAlignment.Bottom, Margin = new Thickness(0, 0, 0, 10), Tag = "toast"
        };
        toast.Children.Add(new Border
        {
            CornerRadius = new CornerRadius(6), Background = Brushes.Black,
            Effect = new DropShadowEffect { BlurRadius = 14, ShadowDepth = 4, Opacity = 0.16, Direction = 270 }
        });
        toast.Children.Add(face);
        return toast;
    }

    // The Play/Stop button's content: a filled triangle or square, then the word.
    private static FrameworkElement PlayLabel(bool play, string text, double size = 0)
    {
        FrameworkElement glyph = Theme.Solid(play ? Theme.PlayIcon : Theme.StopIcon, size > 0 ? size : play ? 16 : 18, "AccentFg");
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
        // A click elsewhere closes the panel, like the Windows flyouts. Its own menus and file dialogs keep it open while
        // they are shown: the menus that are open right now, not a count, so none can be left over. Once the panel has
        // lost the activation and nothing of its own is open any more, it closes: when it is deactivated, when one of its
        // menus closes (a click elsewhere with a menu open deactivates the panel first and closes the menu after), and on
        // every tick of the dismiss timer below.
        var openMenus = new HashSet<ContextMenu>();
        int dialogs = 0;
        bool wasActive = false;
        bool keepOpen = false;
#if SELFTEST
        keepOpen = testMenu && !dismissCheck;   // the self-test keeps its panels open, whatever the mouse does meanwhile
        panelHeld = () => dialogs > 0 || openMenus.Any(menu => menu.IsOpen);
#endif
        bool Held() => keepOpen || dialogs > 0 || openMenus.Any(menu => menu.IsOpen);
        void CloseIfLeft()
        {
            if (playerPanel != panel || !wasActive || panel.IsActive || Held()) return;
            sinceDismiss.Restart();   // a click on the tray icon that took the activation must not open it again
            panel.Close();
        }
        panel.Closed += (_, _) => { if (playerPanel == panel) playerPanel = null; };
        panel.Activated += (_, _) => wasActive = true;
        panel.Deactivated += (_, _) => Post(CloseIfLeft);
        void Hold(ContextMenu menu)
        {
            menu.Opened += (_, _) => openMenus.Add(menu);
            menu.Closed += (_, _) =>
            {
                openMenus.Remove(menu);
                Post(CloseIfLeft);
            };
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

        // "Link copied" after Share: a card centred above the player for two seconds (added over the pages below).
        Grid linkCopied = NewToast(out TextBlock linkCopiedText, out FrameworkElement linkCopiedTick);
        var linkCopiedTimer = new DispatcherTimer { Interval = TimeSpan.FromSeconds(2) };
        linkCopiedTimer.Tick += (_, _) =>
        {
            linkCopiedTimer.Stop();
            linkCopied.Visibility = Visibility.Collapsed;
        };
        panel.Closed += (_, _) => linkCopiedTimer.Stop();
        void ShareStation(SavedStation item)
        {
            bool copied = CopyText(ShareLink.Web(item.Name, item.Url, item.Logo));
            linkCopiedText.Text = copied ? L("Link copied") : L("The clipboard is busy.");
            linkCopiedTick.Visibility = copied ? Visibility.Visible : Visibility.Collapsed;
            linkCopied.Visibility = Visibility.Visible;
            linkCopiedTimer.Stop();
            linkCopiedTimer.Start();
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
        // Song history's own button on the right of its bar: the Statistics page.
        var statisticsButton = NewButton(null, IconText(Theme.ChartIcon, L("Statistics")));
        statisticsButton.Margin = new Thickness(8, 0, 0, 0);
        foreach (Button button in new[] { add, historyButton, statisticsButton })
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
        var pageBar = Columns((backButton, Auto), (pageTitle, Star), (statisticsButton, Auto));
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
        ScrollViewer settingsPane = Pane(), historyPane = Pane(), statisticsPane = Pane(), sharedPane = Pane();
        SharedStation shownShared = null;   // the Shared station page's station (none: the link carried none)
        Action refreshCollected = null;   // Settings › Statistics' "Collected since", again after a clear
        string statisticsFrom = "settings";   // where ← goes back to from Statistics: Settings or Song history

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
            if (ShareLink.TryParse(query, out _))   // a shared station's link typed in and searched for
            {
                OpenShared(query);
                return;
            }
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

        // Pages: "stations", "search" (Add a station), "form" (Add by address, Edit), "history", "settings", "statistics",
        // "shared" (Shared station).
        void SetPage(string target)
        {
            if (target != "form") editing = null;
            if (page == "search" && target != "search") ResetSearch();
            string from = page;
            page = target;
            bool stations = target == "stations";
            Visibility Shown(bool shown) => shown ? Visibility.Visible : Visibility.Collapsed;
            list.Visibility = footer.Visibility = stationsBar.Visibility = Shown(stations);
            pageBar.Visibility = Shown(!stations);
            statisticsButton.Visibility = Shown(target == "history");
            if (target == "statistics" && from != "statistics") statisticsFrom = from == "history" ? "history" : "settings";
            searchPane.Visibility = Shown(target == "search");
            fields.Visibility = Shown(target == "form");
            settingsPane.Visibility = Shown(target == "settings");
            historyPane.Visibility = Shown(target == "history");
            statisticsPane.Visibility = Shown(target == "statistics");
            sharedPane.Visibility = Shown(target == "shared");
            pageTitle.Text = target == "settings" ? L("Settings")
                : target == "history" ? L("Song history")
                : target == "statistics" ? L("Statistics")
                : target == "shared" ? L("Shared station")
                : target == "search" ? L("Add a station")
                : target == "form" ? (editing == null ? L("Add by address") : L("Edit")) : "";
            if (target == "search")
            {
                app.Dispatcher.BeginInvoke(DispatcherPriority.Loaded, new Action(() => searchBox.Focus()));
                ShowSuggestions();
            }
            if (target == "settings")
            {
                refreshCollected?.Invoke();
                if (from != "statistics") settingsPane.ScrollToTop();   // back from Statistics: where it was left
            }
            if (target == "history")
            {
                FillHistory();
                historyPane.ScrollToTop();
            }
            if (target == "statistics")
            {
                FillStatistics(StatisticsPeriod.Month);   // the page opens on this month
                statisticsPane.ScrollToTop();
            }
            if (target == "shared")
            {
                FillShared();
                sharedPane.ScrollToTop();
            }
            if (stations) ShowActiveStationAfterLayout(false);
        }

        // ← and Esc: the station form and Statistics go back to where they were opened from, the rest to the stations.
        void GoBack()
        {
            if (page == "form") CancelForm();
            else if (page == "statistics") SetPage(statisticsFrom);
            else SetPage("stations");
        }

        add.Click += (_, _) => SetPage("search");
        // A shared station's link pasted into the search box or the stream address: its Shared station page (also for
        // systems or browsers where the link doesn't open the radio by itself).
        void TakeLinks(TextBox box) => DataObject.AddPastingHandler(box, (sender, e) =>
        {
            if (!(e.DataObject.GetData(DataFormats.UnicodeText) is string text) || !ShareLink.TryParse(text, out SharedStation _)) return;
            e.CancelCommand();
            Post(() => OpenShared(text));
        });
        TakeLinks(searchBox);
        TakeLinks(url);
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
        statisticsButton.Click += (_, _) => SetPage("statistics");
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
            if (ShareLink.TryParse(address, out _))   // a shared station's link typed in: its page, not a stream
            {
                OpenShared(address);
                return;
            }
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
            ContextMenu options = RowMenu(actions);
            // No Move up / Move down: the station is dragged instead (or moved with Alt+↑/↓).
            options.Items.Add(Item(L("Edit"), null, () => Edit(item)));
            options.Items.Add(Item(L("Share"), null, () => ShareStation(item)));
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
                ContextMenu menu = RowMenu(more);
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
#if SELFTEST
                more.Tag = menu;   // the README pictures read the menu from here
#endif
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

        // Shared station page (a shared station's link): the station, the question, Add and play / Cancel. Nothing is
        // added or played before the click; Cancel, ← and Esc change nothing.
        void FillShared()
        {
            var content = new StackPanel { Margin = new Thickness(Gutter) };
            sharedPane.Content = content;
            SharedStation shared = shownShared;
            if (shared == null)
            {
                TextBlock none = Note(L("This link doesn't contain a station."));
                none.FontSize = 14;
                none.Margin = new Thickness(2, 0, 2, 0);
                content.Children.Add(none);
                return;
            }
            TextBlock Centred(string text, double size) => new TextBlock
            {
                Text = text, FontSize = size, TextWrapping = TextWrapping.Wrap, TextAlignment = TextAlignment.Center
            };
            var card = new StackPanel();
            Grid badge = LogoBadge(shared.Logo, 72);
            badge.HorizontalAlignment = HorizontalAlignment.Center;
            card.Children.Add(badge);
            TextBlock title = Centred(shared.Name, 20);
            title.FontWeight = FontWeights.SemiBold;
            title.Margin = new Thickness(0, 16, 0, 0);
            card.Children.Add(title);
            // The stream address without its http(s)://, in small grey text.
            TextBlock address = Note(Regex.Replace(shared.Url, "^https?://", "", RegexOptions.IgnoreCase));
            address.FontSize = 12;
            address.TextAlignment = TextAlignment.Center;
            address.Margin = new Thickness(0, 4, 0, 0);
            card.Children.Add(address);
            TextBlock question = Centred(L("Add it to your stations and play it now?"), 14);
            question.Margin = new Thickness(0, 16, 0, 0);
            card.Children.Add(question);
            var addAndPlay = NewButton("AccentButton", PlayLabel(true, L("Add and play"), 12));
            addAndPlay.Height = 38;
            addAndPlay.Margin = new Thickness(0, 20, 0, 0);
            var cancel = NewButton(null, L("Cancel"));
            cancel.Height = 32;
            cancel.Padding = new Thickness(12, 0, 12, 0);
            cancel.Margin = new Thickness(0, 8, 0, 0);
            card.Children.Add(addAndPlay);
            card.Children.Add(cancel);
            Border frame = CardFrame(card, new Thickness(20, 28, 20, 20));
            frame.Margin = new Thickness(0);
            content.Children.Add(frame);
            cancel.Click += (_, _) => SetPage("stations");
            // At the end of the list, then it plays (a station that got onto the list meanwhile just plays).
            addAndPlay.Click += (_, _) =>
            {
                int index = Stations.FindIndex(item => Storage.SameStream(item.Url, shared.Url));
                if (index < 0)
                {
                    var added = new SavedStation { Name = shared.Name, Url = shared.Url, Logo = shared.Logo };
                    if (!ApplyStations(Stations.Concat(new[] { added }).ToList())) return;
                    index = Stations.IndexOf(added);
                }
                SelectStation(index);
                if (session == null) StartPlayback();
                SetPage("stations");
                list.SelectedIndex = station;
            };
        }

        // Statistics page (Settings › Statistics › Show): the period switch, then that period's numbers. The counting is
        // in Statistics.cs; here they are only laid out.
        void FillStatistics(StatisticsPeriod period)
        {
            statistics.Tick(DateTime.UtcNow);   // the station playing now counts up to now
            StatisticsSummary summary = statistics.Summarize(period, DateTime.UtcNow, TimeZoneInfo.Local);
            CultureInfo culture = Culture;
            var content = new StackPanel { Margin = new Thickness(Gutter) };

            // All | Year | Month, the chosen one filled with the accent colour.
            var segments = new UniformGrid { Rows = 1 };
            foreach (var (label, value) in new[] { (L("All"), StatisticsPeriod.All), (L("Year"), StatisticsPeriod.Year), (L("Month"), StatisticsPeriod.Month) })
            {
                Button segment = NewButton(value == period ? "AccentButton" : "GhostButton", label);
                segment.Height = 30;
                segment.Padding = new Thickness(4, 0, 4, 0);
                segment.Margin = new Thickness(1, 0, 1, 0);
                if (value == period) segment.FontWeight = FontWeights.SemiBold;
                else segment.Click += (_, _) => FillStatistics(value);
                segments.Children.Add(segment);
            }
            var switcher = new Border
            {
                BorderThickness = new Thickness(1), CornerRadius = new CornerRadius(6), Padding = new Thickness(1, 2, 1, 2), Child = segments
            };
            switcher.SetResourceReference(Border.BackgroundProperty, "Card");
            switcher.SetResourceReference(Border.BorderBrushProperty, "Line");
            content.Children.Add(switcher);
            statisticsPane.Content = content;
            if (!statistics.Collecting)
            {
                TextBlock off = Note(L("Statistics are off. Nothing new is recorded."));
                off.Margin = new Thickness(2, Gutter, 2, 0);
                content.Children.Add(off);
            }
            if (summary.Empty)
            {
                TextBlock nothing = Note(L("Nothing here yet. Listen for a while and come back."));
                nothing.Margin = new Thickness(2, Gutter, 2, 0);
                content.Children.Add(nothing);
                return;
            }

            Border Box(FrameworkElement child, Thickness padding, double top)
            {
                Border box = CardFrame(child, padding);
                box.Margin = new Thickness(0, top, 0, 0);
                return box;
            }
            TextBlock Small(string text, double size = 13)
            {
                TextBlock small = Note(text);
                small.FontSize = size;
                small.TextWrapping = TextWrapping.NoWrap;
                small.VerticalAlignment = VerticalAlignment.Center;
                return small;
            }
            Border Bar(double height, CornerRadius corners)
            {
                var bar = new Border { Height = height, CornerRadius = corners };
                bar.SetResourceReference(Border.BackgroundProperty, "Accent");
                return bar;
            }

            // Listening time: the period on the right, the total in large type, the average per day under it.
            string since = period == StatisticsPeriod.Month ? summary.Since.ToString("Y", culture)
                : period == StatisticsPeriod.Year ? summary.Since.Year.ToString(CultureInfo.InvariantCulture)
                : L("Since {0}", LongDate(summary.Since));
            since = since.Substring(0, 1).ToUpper(culture) + since.Substring(1);   // "listopad 2026" as a label: "Listopad 2026"
            TextBlock periodLabel = Small(since, 12.5);
            periodLabel.Margin = new Thickness(12, 0, 0, 0);
            content.Children.Add(Box(Spaced(Orientation.Vertical, 2,
                Columns((Small(L("Listening time"), 12.5), Star), (periodLabel, Auto)),
                new TextBlock { Text = Statistics.Duration(summary.Total), FontSize = 30, FontWeight = FontWeights.SemiBold },
                Note(L("≈ {0} a day", Statistics.Duration(summary.PerDay)))), new Thickness(16, 14, 16, 14), Gutter));

            // Three tiles: the label on top, the value at the bottom, so the values stay in one row if a label wraps.
            var tiles = new Grid { Margin = new Thickness(0, Gutter, 0, 0) };
            var values = new (string Label, string Value)[]
            {
                (L("Song titles"), summary.Songs.ToString("N0", culture)), (L("Stations"), summary.Stations.ToString("N0", culture)),
                (L("Longest"), Statistics.Duration(summary.Longest))
            };
            for (int i = 0; i < values.Length; i++)
            {
                if (i > 0) tiles.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(8) });
                tiles.ColumnDefinitions.Add(new ColumnDefinition { Width = Star });
                var value = new TextBlock
                {
                    Text = values[i].Value, FontSize = 17, FontWeight = FontWeights.SemiBold, TextWrapping = TextWrapping.Wrap, Margin = new Thickness(0, 2, 0, 0)
                };
                var tile = new DockPanel();
                DockPanel.SetDock(value, Dock.Bottom);
                tile.Children.Add(value);
                tile.Children.Add(Note(values[i].Label));
                Border box = Box(tile, new Thickness(12, 10, 12, 10), 0);
                Grid.SetColumn(box, 2 * i);
                tiles.Children.Add(box);
            }
            content.Children.Add(tiles);

            // Top stations: logo, name, time, and a bar as long as the time next to the first one's.
            content.Children.Add(Group(L("Top stations")));
            var stationRows = new StackPanel();
            foreach (var (stationName, address, time) in summary.TopStations)
            {
                if (stationRows.Children.Count > 0) stationRows.Children.Add(Divider(new Thickness(0)));
                SavedStation known = Stations.FirstOrDefault(item => address != null && Storage.SameStream(item.Url, address))
                    ?? Stations.FirstOrDefault(item => item.Name == stationName);
                Grid badge = LogoBadge(known?.Logo, 24);
                badge.Margin = new Thickness(0, 0, 10, 0);
                TextBlock timeText = Small(Statistics.Duration(time));
                timeText.Margin = new Thickness(8, 0, 0, 0);
                var nameText = new TextBlock { Text = stationName, TextTrimming = TextTrimming.CharacterEllipsis, VerticalAlignment = VerticalAlignment.Center };
                double share = Math.Max(0.03, (double)time.Ticks / summary.TopStations[0].Time.Ticks);
                var bar = new Grid { Margin = new Thickness(34, 6, 0, 0) };
                bar.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(share, GridUnitType.Star) });
                bar.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1 - share, GridUnitType.Star) });
                bar.Children.Add(Bar(6, new CornerRadius(3)));
                var entry = new StackPanel { Margin = new Thickness(0, 10, 0, 10) };
                entry.Children.Add(Columns((badge, Auto), (nameText, Star), (timeText, Auto)));
                entry.Children.Add(bar);
                stationRows.Children.Add(entry);
            }
            content.Children.Add(Box(stationRows, new Thickness(14, 4, 14, 4), 0));

            // Top artists, from the song titles: only when the stations sent titles for at least 20 % of the time.
            TextBlock artistsTitle = Group(L("Top artists"));
            artistsTitle.Margin = new Thickness(2, 18, 0, 2);
            content.Children.Add(artistsTitle);
            TextBlock source = Note(L("From song titles sent by the stations · {0} of listening time", summary.TitlesShare.ToString("P0", culture)));
            source.Margin = new Thickness(2, 0, 2, 8);
            content.Children.Add(source);
            if (summary.EnoughTitles)
            {
                var artistRows = new StackPanel();
                for (int i = 0; i < summary.TopArtists.Count; i++)
                {
                    if (i > 0) artistRows.Children.Add(Divider(new Thickness(0)));
                    TextBlock rank = Small((i + 1).ToString(culture));
                    rank.Width = 16;
                    rank.TextAlignment = TextAlignment.Right;
                    rank.Margin = new Thickness(0, 0, 12, 0);
                    TextBlock plays = Small(Ln("{0} play", "{0} plays", summary.TopArtists[i].Plays));
                    plays.Margin = new Thickness(8, 0, 0, 0);
                    var artist = new TextBlock
                    {
                        Text = summary.TopArtists[i].Name, TextTrimming = TextTrimming.CharacterEllipsis, VerticalAlignment = VerticalAlignment.Center
                    };
                    var row = (Grid)Columns((rank, Auto), (artist, Star), (plays, Auto));
                    row.Height = 40;
                    artistRows.Children.Add(row);
                }
                content.Children.Add(Box(artistRows, new Thickness(14, 2, 14, 2), 0));
            }
            else content.Children.Add(Box(Note(L("Not enough song titles yet")), new Thickness(14, 12, 14, 12), 0));

            // When you listen: the busiest hour, and a bar for each hour of the day.
            content.Children.Add(Group(L("When you listen")));
            string Hour(int hour) => new DateTime(2000, 1, 1, hour % 24, 0, 0).ToString("HH:mm", CultureInfo.InvariantCulture);
            var hours = new Grid { Height = 64 };
            double busiest = summary.Hours.Max();
            for (int hour = 0; hour < 24; hour++)
            {
                hours.ColumnDefinitions.Add(new ColumnDefinition { Width = Star });
                double minutes = summary.Hours[hour];
                // Any listening at all keeps a sliver, so a quiet hour doesn't look like none.
                Border bar = Bar(minutes <= 0 ? 0 : Math.Max(2, Math.Round(minutes / busiest * 60)), new CornerRadius(2, 2, 0, 0));
                bar.VerticalAlignment = VerticalAlignment.Bottom;
                bar.Margin = new Thickness(1, 0, 1, 0);
                Grid.SetColumn(bar, hour);
                hours.Children.Add(bar);
            }
            var axis = new Border { BorderThickness = new Thickness(0, 0, 0, 1), Child = hours };
            axis.SetResourceReference(Border.BorderBrushProperty, "Line");
            var marks = new Grid();
            for (int i = 0; i <= 4; i++)
            {
                if (i > 0) marks.ColumnDefinitions.Add(new ColumnDefinition { Width = Star });
                marks.ColumnDefinitions.Add(new ColumnDefinition { Width = Auto });
                TextBlock mark = Small((i * 6).ToString("00", CultureInfo.InvariantCulture), 11);
                Grid.SetColumn(mark, 2 * i);
                marks.Children.Add(mark);
            }
            content.Children.Add(Box(Spaced(Orientation.Vertical, 6,
                Note(L("Most often {0}", Hour(summary.BusiestHour) + "–" + Hour(summary.BusiestHour + 1))), axis, marks),
                new Thickness(16, 14, 16, 10), 0));

            // Clear statistics, after a question (the history stays).
            var clear = SmallButton("LinkButton", L("Clear statistics"));
            clear.HorizontalAlignment = HorizontalAlignment.Left;
            clear.Margin = new Thickness(-4, 10, 0, 0);
            var confirmClear = RowButton(L("Clear statistics"));
            confirmClear.SetResourceReference(Control.ForegroundProperty, "Danger");
            var keep = RowButton(L("Cancel"));
            keep.Margin = new Thickness(8, 0, 0, 0);
            TextBlock question = Note(L("Clear all statistics? This can't be undone."));
            question.Margin = new Thickness(0, 0, 0, 8);
            var confirmation = new StackPanel { Margin = new Thickness(2, Gutter, 0, 0), Visibility = Visibility.Collapsed };
            confirmation.Children.Add(question);
            confirmation.Children.Add(Columns((confirmClear, Auto), (keep, Auto), (new Border(), Star)));
            clear.Click += (_, _) =>
            {
                clear.Visibility = Visibility.Collapsed;
                confirmation.Visibility = Visibility.Visible;
                confirmation.BringIntoView();
            };
            keep.Click += (_, _) =>
            {
                confirmation.Visibility = Visibility.Collapsed;
                clear.Visibility = Visibility.Visible;
            };
            confirmClear.Click += (_, _) =>
            {
                ClearStatistics();
                FillStatistics(period);
            };
            content.Children.Add(clear);
            content.Children.Add(confirmation);
        }

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
                dialogs++;
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
                finally { dialogs--; }
            };
            import.Click += (_, _) =>
            {
                var dialog = new Microsoft.Win32.OpenFileDialog
                {
                    Filter = L("Station list") + " (*.json)|*.json|" + L("All files") + "|*.*"
                };
                dialogs++;
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
                finally { dialogs--; }
            };
            settings.Children.Add(Group(L("Stations")));
            var transfer = Columns((stationsNote, Star), (export, Auto), (import, Auto));
            transfer.Margin = new Thickness(14, 10, 14, 10);
            settings.Children.Add(SettingsCard(SettingRow(L("Station list"), L("A copy in a file, e.g. for friends"), null), transfer));

            // Statistics: a card of its own, without a group title. The switch, then since when and [Show].
            var showStatistics = RowButton(L("Show"));
            showStatistics.Click += (_, _) => SetPage("statistics");
            TextBlock collected = Note("");
            collected.VerticalAlignment = VerticalAlignment.Center;
            refreshCollected = () => collected.Text = statistics.FirstSession is DateTime first
                ? L("Collected since {0}", LongDate(first.ToLocalTime())) : L("Nothing collected yet");
            refreshCollected();
            var since = Columns((collected, Star), (showStatistics, Auto));
            since.Margin = new Thickness(14, 10, 14, 10);
            Border statisticsCard = SettingsCard(
                SettingRow(L("Statistics"), L("Collected only on this computer, never sent anywhere"),
                    Toggle(statistics.Collecting, SetStatisticsCollecting)),
                since);
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
                SettingRow(L("Automatic updates"), updateDescription, Toggle(checkUpdates, on => { checkUpdates = on; SavePreferences(); })),
                lastCheck));

            // About: the round app icon (as many pixels as the screen shows), the version and a link to the project.
            int iconPixels = (int)Math.Round(32 * VisualTreeHelper.GetDpi(panel).DpiScaleX);
            var appIcon = new Image { Source = Theme.AppImage(iconPixels), Width = 32, Height = 32 };
            RenderOptions.SetBitmapScalingMode(appIcon, BitmapScalingMode.HighQuality);
            settings.Children.Add(Group(L("About")));
            settings.Children.Add(SettingsCard(SettingRow(AppName,
                L("Version {0}", Updater.Current.ToString(3)) + " · MIT · " + L("Lucide icons"), Link("GitHub", Updater.Page), appIcon)));

            // Quitting is rare and stops the music, so it lives here and in the tray menu, not next to Play.
            var quit = RowButton(L("Quit"));
            quit.SetResourceReference(Control.ForegroundProperty, "Danger");
            quit.Click += (_, _) => Shutdown();
            Border quitCard = SettingsCard(SettingRow(L("Quit"), L("Stops the radio and removes it from the tray"), quit));
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
        foreach (FrameworkElement part in new FrameworkElement[] { list, searchPane, fields, settingsPane, historyPane, statisticsPane, sharedPane, linkCopied })
            middle.Children.Add(part);
        // A shared station's link while the panel is open (or right after it opened): this page, or the stations page.
        showInPanel = (target, shared) =>
        {
            shownShared = shared;
            SetPage(target);
            if (target == "stations")
            {
                list.SelectedIndex = station;
                ShowActiveStationAfterLayout(true);
            }
        };
        panel.Closed += (_, _) => { if (playerPanel == null) showInPanel = null; };
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
        // Clicking anywhere outside the panel closes it, like the Windows flyouts, also when it never got the activation
        // (opened from another program). A press shorter than a tick (a touchpad tap) shows in the "pressed since"
        // bit; the first tick only learns the buttons' state, so the click that opened the panel doesn't count.
        bool pointerDown = true;
        var dismiss = new DispatcherTimer { Interval = TimeSpan.FromMilliseconds(40) };
        dismiss.Tick += (_, _) =>
        {
            CloseIfLeft();
            if (playerPanel != panel) return;
            bool down = (GetAsyncKeyState(1) & 0x8001) != 0 | (GetAsyncKeyState(2) & 0x8001) != 0;
            if (down && !pointerDown && !Held())
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
        FrameworkElement placeholder = Theme.Glyph(Theme.RadioIcon, size < 32 ? 16 : size > 48 ? 36 : 18);
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
    private bool dismissCheck;      // VerifyDismiss: this panel isn't kept open by the self-test
    private Func<bool> panelHeld;   // the open panel's menus or dialogs that keep it open right now

    // Self-test of a click elsewhere (--test-menu): another window taking the activation closes the panel, also when one
    // of its menus is open at that moment (2.6.0 then left it open: the menu still held it when the panel was deactivated,
    // and closed only after), and a menu that has closed, even while its page was built again, no longer holds it.
    private async Task VerifyDismiss()
    {
        var elsewhere = new Window
        {
            Width = 160, Height = 60, Left = 0, Top = 0, Topmost = true, ShowInTaskbar = false, Title = AppName + " (self-test)",
            WindowStartupLocation = WindowStartupLocation.Manual
        };
        dismissCheck = true;
        try
        {
            Button Find(Func<Button, bool> match) => Descendants(playerPanel).OfType<Button>().First(match);
            async Task Check(string what, string page, Func<Task> before)
            {
                playerPanel?.Close();
                OpenPlayer(page);
                await Task.Delay(500);
                // Without the activation (a test started in the background) a click elsewhere can't be played here.
                if (playerPanel?.IsActive != true) return;
                await before();
                elsewhere.Show();
                elsewhere.Activate();
                await Task.Delay(500);
                elsewhere.Hide();
                if (playerPanel != null) throw new InvalidOperationException("Panel nie zamyka się po kliknięciu gdzie indziej: " + what);
            }
            await Check("świeżo otwarty", "stations", () => Task.CompletedTask);
            await Check("z otwartym menu wyłącznika czasowego", "stations", async () =>
            {
                Find(button => button.ToolTip as string == L("Sleep timer")).RaiseEvent(new RoutedEventArgs(ButtonBase.ClickEvent));
                await Task.Delay(300);
                if (panelHeld?.Invoke() != true) throw new InvalidOperationException("Otwarte menu nie trzyma panelu.");
            });
            await Check("po menu stacji", "stations", async () =>
            {
                Button options = Descendants(playerPanel).OfType<ListBox>().First(item => item.IsVisible).Items.OfType<Grid>().First()
                    .Children.OfType<Button>().Last();
                options.RaiseEvent(new RoutedEventArgs(ButtonBase.ClickEvent));
                await Task.Delay(300);
                ((ContextMenu)options.Tag).IsOpen = false;
                await Task.Delay(200);
                if (panelHeld?.Invoke() != false || playerPanel?.IsActive != true)
                    throw new InvalidOperationException("Zamknięte menu stacji nadal trzyma panel.");
            });
            await Check("z menu historii otwartym, gdy strona buduje się od nowa", "history", async () =>
            {
                Find(button => button.ToolTip as string == L("More")).RaiseEvent(new RoutedEventArgs(ButtonBase.ClickEvent));
                await Task.Delay(300);
                AddToHistory("Test - Nowy utwór");   // a new song: the page is built again while its menu is open
                await Task.Delay(500);
            });
        }
        finally
        {
            dismissCheck = false;
            elsewhere.Close();
            playerPanel?.Close();
        }
    }

    // Self-test of shared stations' links (--test-menu): a link opens the Shared station page, Cancel changes nothing,
    // Add and play adds the station at the end and plays it, a known station just plays, a link without a station says
    // so, a link pasted into + Station's box opens its page, a second start hands its link over, and Share copies the
    // link and shows "Link copied". Nothing is saved; the stream never answers, so playing it stops at once.
    // With --preview: the Shared station page (shared, shared-invalid), the ⋯ menu (share-menu) and the card (link-copied).
    private async Task VerifyShare(bool preview)
    {
        playerPanel?.Close();
        if (Stations.Count == 0) Stations.Add(new SavedStation { Name = "Stacja testowa", Url = "https://example.com/radio" });
        int count = Stations.Count;
        const string url = "https://example.invalid/shared-test";
        string link = ShareLink.Web("Antyradio Hard", url, ShotStations[2].Logo);
        void Fail(string what) => throw new InvalidOperationException("Udostępnianie stacji: " + what);
        bool Shows(string text)
        {
            playerPanel?.UpdateLayout();
            return playerPanel != null && Descendants(playerPanel).OfType<TextBlock>().Any(block => block.IsVisible && block.Text == text);
        }
        Button ButtonWith(string text)
        {
            playerPanel.UpdateLayout();   // a page just built gets its buttons' insides only now
            return Descendants(playerPanel).OfType<Button>().FirstOrDefault(button => button.IsVisible &&
                (button.Content as string == text || Descendants(button).OfType<TextBlock>().Any(block => block.Text == text)))
                ?? throw new InvalidOperationException("Udostępnianie stacji: brak przycisku " + text);
        }
        void Click(Button button) => button.RaiseEvent(new RoutedEventArgs(ButtonBase.ClickEvent));
        Grid RowOf(int index) => Descendants(playerPanel).OfType<ListBox>().First(box => box.IsVisible).Items.OfType<Grid>().ElementAt(index);
        try
        {
            StopPlayback();
            // The page, and Cancel.
            OpenShared(link);
            if (!Shows(L("Shared station")) || !Shows("Antyradio Hard") || !Shows(L("Add it to your stations and play it now?")) || session != null)
                Fail("nie widać strony udostępnionej stacji.");
            if (preview)
            {
                await Task.Delay(1500);   // the logo comes over the network
                await SavePreview(playerPanel, "shared");
            }
            Click(ButtonWith(L("Cancel")));
            if (Stations.Count != count || session != null || !Shows(L("History"))) Fail("Anuluj coś zmieniło albo nie wrócił do stacji.");
            // Add and play: at the end of the list, and it plays.
            OpenShared(link);
            Click(ButtonWith(L("Add and play")));
            bool added = Stations.Count == count + 1 && Stations[count].Url == url && Stations[count].Name == "Antyradio Hard" &&
                Stations[count].Logo == ShotStations[2].Logo && station == count && session != null && Shows(L("History"));
            StopPlayback();
            if (!added) Fail("Dodaj i odtwórz nie dodało stacji na końcu albo jej nie włączyło.");
            // The same stream again (another name, the radio's own link, a trailing /): already on the list, so it just plays.
            SelectStation(0);
            OpenShared(ShareLink.App("Inna nazwa", url + "/", null));
            bool known = Stations.Count == count + 1 && station == count && session != null && !Shows(L("Shared station"));
            StopPlayback();
            if (!known) Fail("znana stacja nie zagrała od razu.");
            // A link without a station.
            OpenShared(ShareLink.Page + "#n=Bez+adresu");
            if (!Shows(L("This link doesn't contain a station.")) || Shows(L("Add and play"))) Fail("brak komunikatu o złym linku.");
            if (preview) await SavePreview(playerPanel, "shared-invalid");
            // Pasted into the search box of + Station (when the clipboard is free).
            Click(Descendants(playerPanel).OfType<Button>().First(button => button.ToolTip as string == L("Back")));
            Click(ButtonWith(L("Station")));
            string pasted = ShareLink.Web("Wklejona stacja", "https://example.invalid/pasted", null);
            if (CopyText(pasted))
            {
                TextBox box = Descendants(playerPanel).OfType<TextBox>().First(item => item.IsVisible);
                box.Focus();
                ApplicationCommands.Paste.Execute(null, box);
                await Task.Delay(300);
                if (!Shows(L("Shared station")) || !Shows("Wklejona stacja")) Fail("wklejony link nie otworzył strony stacji.");
            }
            // A second start of the radio with --open hands its link to this one.
            playerPanel?.Close();
            string handed = ShareLink.App("Z drugiego startu", "https://example.invalid/second", null);
            using (Process second = Process.Start(new ProcessStartInfo(Exe, "--test-menu --open \"" + handed + "\"") { UseShellExecute = false }))
            {
                for (int wait = 0; wait < 100 && !second.HasExited; wait++) await Task.Delay(100);   // the radio answers meanwhile
                await Task.Delay(300);
                if (!second.HasExited || second.ExitCode != 0 || !Shows("Z drugiego startu")) Fail("drugi start nie przekazał linku.");
            }
            // Share in a station's ⋯ menu: the link on the clipboard and "Link copied".
            playerPanel?.Close();
            OpenPlayer();
            await Task.Delay(500);
            int shared = Math.Max(0, Math.Min(station, Stations.Count - 1));
            Button more = RowOf(shared).Children.OfType<Button>().Last();
            var options = (ContextMenu)more.Tag;
            if (preview)
            {
                Click(more);
                await Task.Delay(500);
                await SaveWithMenu(playerPanel, options, "share-menu");
                options.IsOpen = false;
            }
            options.Items.OfType<MenuItem>().First(item => item.Header as string == L("Share")).RaiseEvent(new RoutedEventArgs(MenuItem.ClickEvent));
            SavedStation sharedStation = Stations[shared];
            string expected = ShareLink.Web(sharedStation.Name, sharedStation.Url, sharedStation.Logo), copied = null;
            try { copied = Clipboard.GetText(); }
            catch (System.Runtime.InteropServices.ExternalException) { /* busy: not the app's fault */ }
            if (copied != null && (copied != expected || !Shows(L("Link copied")))) Fail("Udostępnij nie skopiowało linku: " + copied);
            if (preview) await SavePreview(playerPanel, "link-copied");
        }
        finally
        {
            StopPlayback();
            playerPanel?.Close();
            Stations.RemoveRange(count, Stations.Count - count);   // only in memory: the self-test saves nothing
            station = Math.Min(station, Stations.Count - 1);
        }
    }

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
