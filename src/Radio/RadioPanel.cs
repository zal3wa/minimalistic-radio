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

    // A Windows 11 settings card: icon, title and description on the left, a control on the right,
    // optional extra rows below a divider (like the expanders in the Settings app).
    private static FrameworkElement Card(FrameworkElement icon, string title, object description,
        FrameworkElement control, params FrameworkElement[] rows)
    {
        var text = new StackPanel { VerticalAlignment = VerticalAlignment.Center };
        text.Children.Add(new TextBlock { Text = title, FontSize = 14, TextWrapping = TextWrapping.Wrap });
        if (description != null)
        {
            TextBlock note = description as TextBlock ?? Note(description.ToString());
            note.Margin = new Thickness(0, 1, 0, 0);
            text.Children.Add(note);
        }
        icon.VerticalAlignment = VerticalAlignment.Center;
        icon.Margin = new Thickness(0, 0, 14, 0);
        var head = new Grid { MinHeight = 40 };
        head.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
        head.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
        head.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
        head.Children.Add(icon);
        Grid.SetColumn(text, 1);
        head.Children.Add(text);
        if (control != null)
        {
            control.Margin = new Thickness(12, 0, 0, 0);
            control.VerticalAlignment = VerticalAlignment.Center;
            Grid.SetColumn(control, 2);
            head.Children.Add(control);
        }
        var body = new StackPanel();
        body.Children.Add(head);
        foreach (FrameworkElement row in rows)
        {
            body.Children.Add(Divider(new Thickness(-14, 12, -14, 12)));
            row.Margin = new Thickness(34, 0, 0, 0);
            body.Children.Add(row);
        }
        return CardFrame(body, new Thickness(14, 12, 14, 12));
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
        button.VerticalAlignment = VerticalAlignment.Center;
        button.Click += (_, _) => OpenWebPage(address);
        return button;
    }

    // Windows 11 on/off switch with its "On"/"Off" label.
    private static CheckBox Toggle(bool on, Action<bool> changed)
    {
        var toggle = new CheckBox { IsChecked = on };
        toggle.SetResourceReference(FrameworkElement.StyleProperty, "ToggleSwitch");
        void Label() => toggle.Content = toggle.IsChecked == true ? T("Wł.", "On") : T("Wył.", "Off");
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
        panel.Closed += (_, _) => { if (playerPanel == panel) playerPanel = null; };
        panel.Deactivated += (_, _) => Post(() =>
        {
            if (playerPanel == panel && !panel.IsActive && holdOpen == 0 && !testMenu) panel.Close();
        });
        void Hold(ContextMenu menu)
        {
            menu.Opened += (_, _) => holdOpen++;
            menu.Closed += (_, _) => holdOpen--;
        }

        var list = new ListBox();
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
        var volumeText = new TextBlock { VerticalAlignment = VerticalAlignment.Center, MinWidth = 104 };
        var name = new TextBox { Tag = T("Nazwa stacji", "Station name"), MaxLength = 100 };
        var url = new TextBox { Tag = T("Adres strumienia HTTP lub HTTPS", "Stream address (HTTP or HTTPS)"), MaxLength = 2048 };
        var logo = new TextBox { Tag = T("Adres logotypu (opcjonalnie)", "Logo address (optional)"), MaxLength = 2048 };
        SavedStation editing = null;
        var message = new TextBlock { TextWrapping = TextWrapping.Wrap };
        var add = NewButton(null, IconText(Theme.PlusIcon, T("Stacja", "Station")));
        add.HorizontalAlignment = HorizontalAlignment.Left;
        var save = NewButton("AccentButton", T("Zapisz", "Save"));
        var cancelForm = NewButton(null, T("Anuluj", "Cancel"));
        var fields = Spaced(Orientation.Vertical, 8, name, url, logo,
            Spaced(Orientation.Horizontal, 8, save, cancelForm), message);
        fields.Visibility = Visibility.Collapsed;

        var searchBox = new TextBox { Tag = T("Wpisz nazwę stacji", "Type a station name"), MaxLength = 100 };
        var searchButton = NewButton(null, T("Szukaj", "Search"));
        searchButton.Margin = new Thickness(8, 0, 0, 0);
        // The search page: box and button, then one line with the status (or a hint) and "Add by address".
        string searchHint = T("Szukaj w katalogu radio-browser.info", "Search the radio-browser.info directory");
        var manual = SmallButton("LinkButton", T("Dodaj z adresu", "Add by address"));
        manual.VerticalAlignment = VerticalAlignment.Center;
        manual.Margin = new Thickness(8, 0, -8, 0);
        var results = new ListBox();
        TextBlock searchStatus = Note(searchHint);
        searchStatus.VerticalAlignment = VerticalAlignment.Center;
        var searchHeader = Spaced(Orientation.Vertical, 4, Columns((searchBox, Star), (searchButton, Auto)),
            Columns((searchStatus, Star), (manual, Auto)));
        searchHeader.Margin = new Thickness(0, 0, 0, 6);
        var searchPane = new DockPanel { Visibility = Visibility.Collapsed };
        DockPanel.SetDock(searchHeader, Dock.Top);
        searchPane.Children.Add(searchHeader);
        searchPane.Children.Add(results);
        CancellationTokenSource activeSearch = null;
        var loadingSuggestions = new CancellationTokenSource();
        bool loadingNow = false;
        string page = "stations";
        panel.Closed += (_, _) => { activeSearch?.Cancel(); loadingSuggestions.Cancel(); };

        // Header: title with Update (when ready), History, Settings and Hide; the page title with a back arrow.
        var historyButton = NewButton("GhostButton", Theme.Glyph(Theme.HistoryIcon), T("Historia utworów", "Song history"));
        var settingsButton = NewButton("GhostButton", Theme.Glyph(Theme.SettingsIcon), T("Ustawienia", "Settings"));
        // Hides the panel (like the X of Windows 11 flyouts); the radio keeps playing next to the clock.
        var closeButton = NewButton("GhostButton", Theme.Glyph(Theme.CloseIcon), T("Ukryj panel (radio gra dalej)", "Hide the panel (the radio keeps playing)"));
        closeButton.Click += (_, _) => panel.Close();
        // Like Discord: a green arrow appears once a new version is downloaded; a click installs it.
        var updateButton = NewButton("GhostButton", Theme.Glyph(Theme.UpdateReadyIcon, 18, "Success"), T("Aktualizacja gotowa!", "Update Ready!"));
        updateButton.Visibility = Visibility.Collapsed;
        updateButton.Click += (_, _) => InstallUpdate();
        foreach (Button button in new[] { updateButton, historyButton, settingsButton, closeButton })
        {
            button.Padding = new Thickness(8, 6, 8, 6);
            button.VerticalAlignment = VerticalAlignment.Center;
        }
        var sectionLabel = new TextBlock
        {
            Text = T("Stacje", "Stations"), FontSize = 20, FontWeight = FontWeights.SemiBold, VerticalAlignment = VerticalAlignment.Center
        };
        var backButton = NewButton("GhostButton", Theme.Glyph(Theme.BackIcon), T("Wstecz", "Back"));
        backButton.Padding = new Thickness(6);
        backButton.Margin = new Thickness(-6, 0, 6, 0);
        backButton.VerticalAlignment = VerticalAlignment.Center;
        var sectionRow = Columns((backButton, Auto), (sectionLabel, Star));
        var settingsPane = new ScrollViewer
        {
            VerticalScrollBarVisibility = ScrollBarVisibility.Auto, HorizontalScrollBarVisibility = ScrollBarVisibility.Disabled,
            Visibility = Visibility.Collapsed, Padding = new Thickness(0, 0, 8, 0), Focusable = false
        };
        var historyPane = new ScrollViewer
        {
            VerticalScrollBarVisibility = ScrollBarVisibility.Auto, HorizontalScrollBarVisibility = ScrollBarVisibility.Disabled,
            Visibility = Visibility.Collapsed, Padding = new Thickness(0, 0, 8, 0), Focusable = false
        };

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
            fields.Visibility = Visibility.Visible;
            name.Focus();
        }

        void FillList()
        {
            list.Items.Clear();
            for (int index = 0; index < Stations.Count; index++) list.Items.Add(StationRow(Stations[index], index));
            list.SelectedIndex = station;
            shownStation = station;
            ShowActiveStationAfterLayout(false);
        }

        bool ApplyStations(List<SavedStation> updated)
        {
            try { Storage.Write(Storage.StationFile, updated); }
            catch (Exception error) when (error is IOException || error is UnauthorizedAccessException)
            {
                Forms.MessageBox.Show(T("Nie udało się zapisać listy stacji.", "Couldn't save the station list."), AppName);
                return false;
            }
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
                searchStatus.Text = T("Szukam…", "Searching…");
                try
                {
                    DirectoryStation[] found = await Storage.Search(metadataClient, query, searchToken);
                    if (searchToken.IsCancellationRequested) return;
                    foreach (DirectoryStation item in found) results.Items.Add(ResultRow(item));
                    searchStatus.Text = found.Length == 0 ? T("Brak wyników.", "No results.") : "";
                }
                catch (OperationCanceledException) when (searchToken.IsCancellationRequested) { }
                catch (Exception error) when (error is HttpRequestException || error is OperationCanceledException)
                {
                    searchStatus.Text = T("Katalog chwilowo niedostępny. Spróbuj ponownie.",
                        "The station directory is unavailable right now. Try again.");
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
            if (suggestions == null)
            {
                if (loadingNow) return;
                loadingNow = true;
                results.Items.Clear();
                searchStatus.Text = T("Wczytuję propozycje…", "Loading suggestions…");
                try { suggestions = await Storage.Suggestions(metadataClient, loadingSuggestions.Token); }
                catch (Exception error) when (error is HttpRequestException || error is OperationCanceledException)
                {
                    if (!loadingSuggestions.IsCancellationRequested && ShowingSuggestions())
                        searchStatus.Text = T("Nie udało się połączyć z katalogiem stacji. Spróbuj ponownie.",
                            "Couldn't reach the station directory. Try again.");
                }
                finally { loadingNow = false; }
                if (suggestions == null) return;
            }
            if (!ShowingSuggestions()) return;
            results.Items.Clear();
            searchStatus.Text = searchHint;
            if (suggestions.Recommended.Length > 0)
            {
                results.Items.Add(Heading(T("Polecane", "Recommended")));
                foreach (DirectoryStation item in suggestions.Recommended) results.Items.Add(ResultRow(item));
            }
            if (suggestions.Popular.Length > 0)
            {
                results.Items.Add(Heading(suggestions.Country != null ? T("Popularne w Twoim kraju", "Popular in your country")
                    : T("Popularne na świecie", "Popular worldwide")));
                foreach (DirectoryStation item in suggestions.Popular) results.Items.Add(ResultRow(item));
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
        }

        void SetPage(string target)
        {
            if (target != "stations")
            {
                fields.Visibility = Visibility.Collapsed;
                editing = null;
            }
            if (page == "search" && target != "search") ResetSearch();
            page = target;
            bool stations = target == "stations";
            list.Visibility = stations ? Visibility.Visible : Visibility.Collapsed;
            searchPane.Visibility = target == "search" ? Visibility.Visible : Visibility.Collapsed;
            settingsPane.Visibility = target == "settings" ? Visibility.Visible : Visibility.Collapsed;
            historyPane.Visibility = target == "history" ? Visibility.Visible : Visibility.Collapsed;
            add.Visibility = stations ? Visibility.Visible : Visibility.Collapsed;
            sectionLabel.Text = target == "settings" ? T("Ustawienia", "Settings")
                : target == "history" ? T("Historia", "History")
                : target == "search" ? T("Dodaj stację", "Add a station") : T("Stacje", "Stations");
            if (target == "search")
            {
                app.Dispatcher.BeginInvoke(DispatcherPriority.Loaded, new Action(() => searchBox.Focus()));
                ShowSuggestions();
            }
            backButton.Visibility = stations ? Visibility.Collapsed : Visibility.Visible;
            // Off the stations page these two go away entirely, so the rest moves up to the X on the right.
            historyButton.Visibility = settingsButton.Visibility = stations ? Visibility.Visible : Visibility.Collapsed;
            if (target == "settings") settingsPane.ScrollToTop();
            if (target == "history")
            {
                FillHistory();
                historyPane.ScrollToTop();
            }
            if (stations) ShowActiveStationAfterLayout(false);
        }

        add.Click += (_, _) => SetPage("search");
        searchButton.Click += (_, _) => Search();
        searchBox.KeyDown += (_, e) => { if (e.Key == Key.Enter) Search(); };
        // Clearing the box drops the results (and a running search) and brings the suggestions back.
        searchBox.TextChanged += (_, _) =>
        {
            if (page != "search" || !string.IsNullOrWhiteSpace(searchBox.Text)) return;
            activeSearch?.Cancel();
            activeSearch = null;
            searchButton.IsEnabled = true;
            results.Items.Clear();
            searchStatus.Text = searchHint;
            ShowSuggestions();
        };
        manual.Click += (_, _) => { SetPage("stations"); Edit(null); };
        settingsButton.Click += (_, _) => SetPage("settings");
        historyButton.Click += (_, _) => SetPage("history");
        backButton.Click += (_, _) => SetPage("stations");

        void CancelForm()
        {
            bool adding = editing == null;
            editing = null;
            fields.Visibility = Visibility.Collapsed;
            if (adding) SetPage("search");
        }
        cancelForm.Click += (_, _) => CancelForm();

        void AddSearchResult(DirectoryStation item)
        {
            string address = Storage.IsWebUrl(item.ResolvedUrl) ? item.ResolvedUrl : item.Url;
            if (Stations.Any(entry => Storage.SameStream(entry.Url, address)))
            {
                searchStatus.Text = T("Ta stacja jest już na liście.", "This station is already on the list.");
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
                message.Text = T("Podaj nazwę i poprawny adres strumienia. Logo jest opcjonalne.",
                    "Enter a name and a valid stream address. The logo is optional.");
                return;
            }
            if (Stations.Any(item => item != editing && Storage.SameStream(item.Url, address)))
            {
                message.Text = T("Ten adres jest już na liście.", "This address is already on the list.");
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
            fields.Visibility = Visibility.Collapsed;
            editing = null;
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
            if (editing == item) fields.Visibility = Visibility.Collapsed;
        }

        void Move(SavedStation item, int delta)
        {
            int index = Stations.IndexOf(item), target = index + delta;
            if (index < 0 || target < 0 || target >= Stations.Count) return;
            var updated = Stations.ToList();
            updated.RemoveAt(index);
            updated.Insert(target, item);
            ApplyStations(updated);
        }

        // A search result: logo, name, then country · format · genres, and + (or a tick when it's already on the list).
        FrameworkElement ResultRow(DirectoryStation item)
        {
            var image = new Image { Width = 32, Height = 32, Stretch = Stretch.Uniform };
            var placeholder = Theme.Glyph(Theme.RadioIcon);
            var badge = new Grid { Width = 32, Height = 32, VerticalAlignment = VerticalAlignment.Center };
            badge.Children.Add(placeholder);
            badge.Children.Add(image);
            image.Loaded += async (_, _) =>
            {
                if (image.Source != null) return;
                ImageSource source = await LoadImage(item.Logo);
                if (source == null) return;
                image.Source = source;
                placeholder.Visibility = Visibility.Hidden;
            };
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
                known ? T("Już jest na twojej liście", "Already on your list") : T("Dodaj do stacji", "Add to your stations"));
            button.HorizontalContentAlignment = HorizontalAlignment.Stretch;
            button.Padding = new Thickness(10, 6, 10, 6);
            button.Click += (_, _) => AddSearchResult(item);
            return button;
        }

        FrameworkElement StationRow(SavedStation item, int index)
        {
            var image = new Image { Width = 32, Height = 32, Stretch = Stretch.Uniform };
            var placeholder = Theme.Glyph(Theme.RadioIcon);
            var badge = new Grid { Width = 32, Height = 32 };
            badge.Children.Add(placeholder);
            badge.Children.Add(image);
            image.Loaded += async (_, _) =>
            {
                if (image.Source != null) return;
                ImageSource source = await LoadImage(item.Logo);
                if (source == null) return;
                image.Source = source;
                placeholder.Visibility = Visibility.Hidden;
            };
            var text = new TextBlock
            {
                Text = item.Name, TextTrimming = TextTrimming.CharacterEllipsis,
                VerticalAlignment = VerticalAlignment.Center, Margin = new Thickness(12, 0, 0, 0)
            };
            var stationButton = NewButton("GhostButton", Columns((badge, Auto), (text, Star)));
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
            var actions = NewButton("GhostButton", Theme.Glyph(Theme.MoreIcon), T("Opcje stacji", "Station options"));
            actions.Padding = new Thickness(8, 6, 8, 6);
            actions.Margin = new Thickness(4, 0, 0, 0);
            var options = new ContextMenu { PlacementTarget = actions, Placement = PlacementMode.Bottom };
            options.Items.Add(Item(T("Edytuj", "Edit"), null, () => Edit(item)));
            options.Items.Add(Item(T("Przesuń wyżej", "Move up"), null, () => Move(item, -1), index > 0));
            options.Items.Add(Item(T("Przesuń niżej", "Move down"), null, () => Move(item, 1), index < Stations.Count - 1));
            options.Items.Add(new Separator());
            options.Items.Add(Item(T("Usuń", "Remove"), null, () => Remove(item)));
            Hold(options);
            actions.Click += (_, _) => options.IsOpen = true;
            var row = Columns((stationButton, Star), (actions, Auto));
            row.MinHeight = 47;
            return row;
        }

        // History page: the songs the radio played, newest first.
        int shownHistory = -1;
        void FillHistory()
        {
            shownHistory = historyVersion;
            var content = new StackPanel();
            if (history.Count == 0)
            {
                content.Children.Add(Note(T("Tu pojawią się utwory, które zagra radio.", "Songs the radio plays will show up here.")));
                historyPane.Content = content;
                return;
            }
            var culture = new CultureInfo(Polish ? "pl-PL" : "en-US");
            var rows = new StackPanel();
            foreach (HistoryEntry entry in history)
            {
                if (rows.Children.Count > 0) rows.Children.Add(Divider(new Thickness(-12, 0, -4, 0)));
                DateTime time = entry.Time.ToLocalTime();
                var text = new StackPanel { VerticalAlignment = VerticalAlignment.Center, Margin = new Thickness(0, 7, 0, 7) };
                text.Children.Add(new TextBlock { Text = entry.Title, FontSize = 14, TextWrapping = TextWrapping.Wrap });
                text.Children.Add(Note(entry.Station + " · " + time.ToString(time.Date == DateTime.Today ? "HH:mm" : "d MMM, HH:mm", culture)));
                var more = NewButton("GhostButton", Theme.Glyph(Theme.MoreIcon), T("Więcej", "More"));
                more.Padding = new Thickness(8, 6, 8, 6);
                more.VerticalAlignment = VerticalAlignment.Center;
                string query = Uri.EscapeDataString(entry.Title.Replace(" – ", " ").Replace(" - ", " "));
                var menu = new ContextMenu { PlacementTarget = more, Placement = PlacementMode.Bottom };
                menu.Items.Add(Item(T("Kopiuj", "Copy"), Theme.CopyIcon, () => CopyText(entry.Title)));
                menu.Items.Add(Item(T("Szukaj w Spotify", "Search on Spotify"), null,
                    () => OpenWebPage("https://open.spotify.com/search/" + query)));
                menu.Items.Add(Item(T("Szukaj w YouTube", "Search on YouTube"), null,
                    () => OpenWebPage("https://www.youtube.com/results?search_query=" + query)));
                Hold(menu);
                more.Click += (_, _) => menu.IsOpen = true;
                rows.Children.Add(Columns((text, Star), (more, Auto)));
            }
            content.Children.Add(CardFrame(rows, new Thickness(12, 2, 4, 2)));
            var clear = SmallButton("LinkButton", T("Wyczyść historię", "Clear history"));
            clear.HorizontalAlignment = HorizontalAlignment.Left;
            clear.Margin = new Thickness(-8, 6, 0, 0);
            clear.Click += (_, _) => { ClearHistory(); FillHistory(); };
            content.Children.Add(clear);
            historyPane.Content = content;
        }

        BitmapSource titleIcon = Theme.AppImage(64);

        // Settings page, laid out like the Windows 11 Settings app: groups of cards.
        Action refreshUpdates = null;
        FrameworkElement BuildSettings()
        {
            var settings = new StackPanel { Margin = new Thickness(0, 0, 0, 4) };

            // General: language, start with Windows
            var language = new ComboBox { MinWidth = 136 };
            language.Items.Add(T("Jak w Windows", "Same as Windows"));
            language.Items.Add("Polski");
            language.Items.Add("English");
            string[] languages = { "auto", "pl", "en" };
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
            settings.Children.Add(Group(T("Ogólne", "General"), true));
            settings.Children.Add(Card(Theme.Glyph(Theme.GlobeIcon, 20), T("Język", "Language"),
                T("W Windows: ", "In Windows: ") + (SystemPolish ? T("polski", "Polish") : T("angielski", "English")), language));
            settings.Children.Add(Card(Theme.Glyph(Theme.PowerIcon, 20), T("Uruchamiaj z Windows", "Start with Windows"),
                T("Czeka obok zegara, nie gra samo", "Waits by the clock, doesn't play by itself"),
                Toggle(Autostart.Enabled, on => Autostart.Set(on, Exe))));
            settings.Children.Add(Card(Theme.Glyph(Theme.PopupIcon, 20), T("Pokazuj zmianę stacji", "Show station changes"),
                T("Karta na dole ekranu po zmianie klawiszem lub z menu", "A card at the bottom after a media key or menu switch"),
                Toggle(showStationPopup, on => { showStationPopup = on; SavePreferences(); })));

            // Stations: export / import (e.g. to give someone your list)
            var stationsNote = Note("");
            stationsNote.Visibility = Visibility.Collapsed;
            void Report(string text)
            {
                stationsNote.Text = text;
                stationsNote.Visibility = Visibility.Visible;
            }
            var export = SmallButton(null, T("Eksportuj…", "Export…"));
            var import = SmallButton(null, T("Importuj…", "Import…"));
            export.Click += (_, _) =>
            {
                var dialog = new Microsoft.Win32.SaveFileDialog
                {
                    FileName = AppName + " - " + T("stacje", "stations") + ".json", DefaultExt = ".json",
                    Filter = T("Lista stacji", "Station list") + " (*.json)|*.json"
                };
                holdOpen++;
                try
                {
                    if (dialog.ShowDialog(panel) != true) return;
                    Storage.Write(dialog.FileName, Stations);
                    Report(T("Zapisano stacje: ", "Stations saved: ") + Stations.Count + ".");
                }
                catch (Exception error) when (error is IOException || error is UnauthorizedAccessException)
                {
                    Report(T("Nie udało się zapisać pliku.", "Couldn't save the file."));
                }
                finally { holdOpen--; }
            };
            import.Click += (_, _) =>
            {
                var dialog = new Microsoft.Win32.OpenFileDialog
                {
                    Filter = T("Lista stacji", "Station list") + " (*.json)|*.json|" + T("Wszystkie pliki", "All files") + "|*.*"
                };
                holdOpen++;
                try
                {
                    if (dialog.ShowDialog(panel) != true) return;
                    List<SavedStation> loaded = Storage.Read<List<SavedStation>>(dialog.FileName);
                    if (loaded == null)
                    {
                        Report(T("To nie jest lista stacji Minimalistic Radio.", "This isn't a Minimalistic Radio station list."));
                        return;
                    }
                    var fresh = loaded
                        .Where(item => item != null && !string.IsNullOrWhiteSpace(item.Name) && Storage.IsWebUrl(item.Url) &&
                            !Stations.Any(known => Storage.SameStream(known.Url, item.Url)))
                        .GroupBy(item => Storage.StreamKey(item.Url)).Select(same => same.First())
                        .Select(item => new SavedStation { Name = item.Name.Trim(), Url = item.Url, Logo = Storage.IsWebUrl(item.Logo) ? item.Logo : null })
                        .ToList();
                    if (fresh.Count == 0) Report(T("Wszystkie stacje z tego pliku już są na liście.", "All stations from this file are already on the list."));
                    else if (ApplyStations(Stations.Concat(fresh).ToList())) Report(T("Dodano stacje: ", "Stations added: ") + fresh.Count + ".");
                }
                finally { holdOpen--; }
            };
            settings.Children.Add(Group(T("Stacje", "Stations")));
            settings.Children.Add(Card(Theme.Glyph(Theme.ListIcon, 20), T("Lista stacji", "Station list"),
                T("Kopia w pliku, np. dla znajomych", "A copy in a file, e.g. for friends"), null,
                Spaced(Orientation.Vertical, 8, Spaced(Orientation.Horizontal, 8, export, import), stationsNote)));

            // About and updates
            var updateNote = Note("");
            var updateDescription = Note("");
            var checkNow = SmallButton(null, "");
            checkNow.VerticalAlignment = VerticalAlignment.Center;
            checkNow.Margin = new Thickness(8, 0, 0, 0);
            checkNow.Click += (_, _) =>
            {
                if (readyUpdate != null && !installing) InstallUpdate();
                else CheckForUpdates(true);
            };
            refreshUpdates = () =>
            {
                CultureInfo culture = new CultureInfo(Polish ? "pl-PL" : "en-US");
                DateTime? checkedAt = lastUpdateCheck?.ToLocalTime();
                updateDescription.Text = readyUpdate != null
                    ? T("Wersja ", "Version ") + readyUpdate.Version.ToString(3) + T(" jest gotowa do instalacji", " is ready to install")
                    : T("Co kilka godzin sprawdza, czy jest nowa wersja", "Looks for a new version every few hours");
                updateNote.Text = updateStatus ?? (checkedAt == null ? T("Jeszcze nie sprawdzano.", "Not checked yet.")
                    : T("Ostatnio sprawdzono: ", "Last checked: ") +
                      checkedAt.Value.ToString(checkedAt.Value.Date == DateTime.Today ? "HH:mm" : "d MMM, HH:mm", culture));
                checkNow.Content = readyUpdate != null ? T("Zaktualizuj", "Update") : T("Sprawdź teraz", "Check now");
                checkNow.SetResourceReference(FrameworkElement.StyleProperty, readyUpdate != null ? "AccentButton" : (object)typeof(Button));
                checkNow.IsEnabled = !installing && !checking;
            };
            refreshUpdates();
            settings.Children.Add(Group(T("O aplikacji", "About")));
            settings.Children.Add(Card(new Image { Source = titleIcon, Width = 20, Height = 20 }, AppName,
                T("Wersja ", "Version ") + Updater.Current.ToString(3) + " · MIT · " + T("ikony Lucide", "Lucide icons"),
                Link("GitHub", Updater.Page)));
            settings.Children.Add(Card(Theme.Glyph(Theme.UpdateIcon, 20), T("Aktualizacje", "Updates"), updateDescription,
                Toggle(checkUpdates, on => { checkUpdates = on; SavePreferences(); }),
                Columns((updateNote, Star), (checkNow, Auto))));
            // Quitting is rare and stops the music, so it lives here and in the tray menu, not next to Play.
            var quit = SmallButton(null, T("Zakończ", "Quit"));
            quit.Click += (_, _) => Shutdown();
            settings.Children.Add(Card(Theme.Glyph(Theme.QuitIcon, 20), T("Zakończ Minimalistic Radio", "Quit Minimalistic Radio"),
                T("Wyłącza radio i usuwa ikonę obok zegara", "Stops the radio and removes it from next to the clock"), quit));
            return settings;
        }
        settingsPane.Content = BuildSettings();

        // Footer: now playing, volume with the sleep timer, play/stop.
        volumeSlider.ValueChanged += (_, e) => ChangeVolume((int)Math.Round(e.NewValue));
        // Like the Windows 11 volume slider: press anywhere on it and drag (WPF on its own only jumps
        // there and drags just the knob), and the mouse wheel changes the volume by 2%.
        void SlideTo(MouseEventArgs e)
        {
            if (volumeSlider.Template?.FindName("PART_Track", volumeSlider) is Track track)
                volumeSlider.Value = Math.Round(Math.Max(0, Math.Min(100, track.ValueFromPoint(e.GetPosition(track)))));
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
        volumeSlider.MouseWheel += (_, e) =>
        {
            volumeSlider.Value = Clamp((int)volumeSlider.Value + (e.Delta > 0 ? 2 : -2), 0, 100);
            e.Handled = true;
        };
        play.Click += (_, _) => TogglePlayback();
        var copy = NewButton("GhostButton", Theme.Glyph(Theme.CopyIcon), T("Kopiuj tytuł", "Copy title"));
        copy.Padding = new Thickness(8);
        copy.VerticalAlignment = VerticalAlignment.Center;
        copy.Click += (_, _) =>
        {
            if (track != null && !CopyText(track)) message.Text = T("Schowek jest zajęty.", "The clipboard is busy.");
        };

        var sleepButton = NewButton("GhostButton", null, T("Wyłącznik czasowy", "Sleep timer"));
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
        var cancelSleep = SmallButton("LinkButton", T("Anuluj", "Cancel"));
        cancelSleep.Click += (_, _) => SetSleepTimer(null);
        var sleepRow = Columns((sleepText, Star), (cancelSleep, Auto));
        bool? shownSleep = null;

        var cover = new Image { Width = 42, Height = 42, Stretch = Stretch.Uniform };
        var fallback = Theme.Glyph(Theme.MusicIcon);
        var coverBox = new Grid { Width = 42, Height = 42, ClipToBounds = true };
        coverBox.Children.Add(fallback);
        coverBox.Children.Add(cover);
        string displayedArtwork = null;
        var caption = new TextBlock { Text = T("Teraz gra", "Now playing"), FontSize = 11, Opacity = 0.75 };
        var trackInfo = Spaced(Orientation.Vertical, 2, caption, now);
        trackInfo.VerticalAlignment = VerticalAlignment.Center;
        trackInfo.Margin = new Thickness(10, 0, 10, 0);
        var trackCard = new Border
        {
            CornerRadius = new CornerRadius(6), Padding = new Thickness(10, 6, 6, 6),
            Child = Columns((coverBox, Auto), (trackInfo, Star), (copy, Auto))
        };
        trackCard.SetResourceReference(Border.BackgroundProperty, "Card");

        var titleRow = Columns(
            (Spaced(Orientation.Horizontal, 10,
                new Image { Source = titleIcon, Width = 20, Height = 20 },
                new TextBlock { Text = AppName, FontSize = 16, VerticalAlignment = VerticalAlignment.Center }), Star),
            (updateButton, Auto), (historyButton, Auto), (settingsButton, Auto), (closeButton, Auto));
        var header = Spaced(Orientation.Vertical, 12, titleRow, add, fields, sectionRow);
        header.Margin = new Thickness(0, 0, 0, 8);
        var volumeRow = Columns((volumeText, Auto), (volumeSlider, Star), (sleepButton, Auto));
        play.HorizontalAlignment = HorizontalAlignment.Stretch;
        var footer = Spaced(Orientation.Vertical, 10, trackCard, volumeRow, sleepRow, play);
        footer.Margin = new Thickness(0, 10, 0, 0);

        var middle = new Grid();
        middle.Children.Add(list);
        middle.Children.Add(searchPane);
        middle.Children.Add(settingsPane);
        middle.Children.Add(historyPane);
        var content = new DockPanel { LastChildFill = true };
        DockPanel.SetDock(header, Dock.Top);
        DockPanel.SetDock(footer, Dock.Bottom);
        content.Children.Add(header);
        content.Children.Add(footer);
        content.Children.Add(middle);

        var frame = new Border
        {
            BorderThickness = new Thickness(1), CornerRadius = new CornerRadius(8),
            Padding = new Thickness(12), Child = content
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
            if (page != "stations") SetPage("stations");
            else if (fields.Visibility == Visibility.Visible) CancelForm();
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
                // The station changed (media keys, tray menu, Windhawk…): bring it into view, but leave
                // the list alone otherwise, so scrolling through it by hand isn't undone.
                shownStation = station;
                ShowActiveStation(false);
            }
            string playText = session == null ? T("Odtwórz", "Play") : T("Zatrzymaj", "Stop");
            if (!Equals(play.Tag, playText))
            {
                play.Tag = playText;
                play.Content = IconText(session == null ? Theme.PlayIcon : Theme.StopIcon, playText, "AccentFg");
            }
            copy.IsEnabled = track != null;
            now.Text = track ?? (session != null && status == StationName ? NoTrack : status);
            now.ToolTip = track;
            volumeText.Text = T("Głośność ", "Volume ") + volume + "%";
            volumeSlider.Value = volume;
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
            if (down && !pointerDown && holdOpen == 0 && !testMenu)
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
        // like the Windows 11 flyouts — wherever the panel was opened from (tray, Windhawk, Start menu).
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
}
