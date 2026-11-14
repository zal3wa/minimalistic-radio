using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Diagnostics;
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

// The player panel that opens above the tray icon, with the station list, search and settings.
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

    // A Windows 11 settings card: icon, title and description on the left, a control on the right,
    // optional extra rows below a divider (like the expanders in the Settings app).
    private static FrameworkElement Card(FrameworkElement icon, string title, string description,
        FrameworkElement control, params FrameworkElement[] rows)
    {
        var text = new StackPanel { VerticalAlignment = VerticalAlignment.Center };
        text.Children.Add(new TextBlock { Text = title, FontSize = 14, TextWrapping = TextWrapping.Wrap });
        if (description != null)
        {
            TextBlock note = Note(description);
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
            var divider = new Border { Height = 1, Margin = new Thickness(-14, 12, -14, 12) };
            divider.SetResourceReference(Border.BackgroundProperty, "Line");
            body.Children.Add(divider);
            row.Margin = new Thickness(34, 0, 0, 0);
            body.Children.Add(row);
        }
        var card = new Border
        {
            CornerRadius = new CornerRadius(6), BorderThickness = new Thickness(1),
            Padding = new Thickness(14, 12, 14, 12), Margin = new Thickness(0, 0, 0, 4), Child = body
        };
        card.SetResourceReference(Border.BackgroundProperty, "Card");
        card.SetResourceReference(Border.BorderBrushProperty, "Line");
        return card;
    }

    private static TextBlock Group(string text, bool first = false) => new TextBlock
    {
        Text = text, FontSize = 14, FontWeight = FontWeights.SemiBold, Margin = new Thickness(2, first ? 0 : 18, 0, 8)
    };

    // Status badge: a coloured dot and a short label.
    private static FrameworkElement Pill(string text, bool ok)
    {
        var dot = new System.Windows.Shapes.Ellipse { Width = 8, Height = 8, VerticalAlignment = VerticalAlignment.Center, Margin = new Thickness(0, 0, 6, 0) };
        dot.SetResourceReference(System.Windows.Shapes.Shape.FillProperty, ok ? "Success" : "Subtle");
        var row = new StackPanel { Orientation = Orientation.Horizontal };
        row.Children.Add(dot);
        row.Children.Add(new TextBlock { Text = text, FontSize = 12, VerticalAlignment = VerticalAlignment.Center });
        var pill = new Border { CornerRadius = new CornerRadius(11), Padding = new Thickness(8, 3, 10, 4), Child = row };
        pill.SetResourceReference(Border.BackgroundProperty, "Selected");
        return pill;
    }

    // A numbered step; a finished one shows a green tick instead of its number.
    private static FrameworkElement Step(int number, string text, FrameworkElement action = null, bool done = false)
    {
        var badge = new Grid { Width = 20, Height = 20, VerticalAlignment = VerticalAlignment.Top, Margin = new Thickness(0, 0, 10, 0) };
        var circle = new System.Windows.Shapes.Ellipse { StrokeThickness = 1 };
        circle.SetResourceReference(System.Windows.Shapes.Shape.FillProperty, done ? "Success" : "Selected");
        circle.SetResourceReference(System.Windows.Shapes.Shape.StrokeProperty, done ? "Success" : "Line");
        badge.Children.Add(circle);
        FrameworkElement mark = done ? Theme.Glyph(Theme.CheckSmallIcon, 11, "Bg")
            : new TextBlock { Text = number.ToString(), FontSize = 11, FontWeight = FontWeights.SemiBold };
        mark.HorizontalAlignment = HorizontalAlignment.Center;
        mark.VerticalAlignment = VerticalAlignment.Center;
        badge.Children.Add(mark);
        var label = new TextBlock { Text = text, FontSize = 13, TextWrapping = TextWrapping.Wrap, VerticalAlignment = VerticalAlignment.Center };
        var grid = new Grid();
        grid.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
        grid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
        grid.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
        grid.Children.Add(badge);
        Grid.SetColumn(label, 1);
        grid.Children.Add(label);
        if (action != null)
        {
            action.Margin = new Thickness(8, -4, -8, -4);
            Grid.SetColumn(action, 2);
            grid.Children.Add(action);
        }
        return grid;
    }

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

    private void ShowPlayer()
    {
        if (playerPanel != null) playerPanel.Close();
        // The click on the tray icon has just closed the panel (click outside): don't reopen it.
        else if (!sinceDismiss.IsRunning || sinceDismiss.ElapsedMilliseconds > 400) OpenPlayer();
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

    private static void OpenWebPage(string address)
    {
        try { Process.Start(new ProcessStartInfo(address) { UseShellExecute = true })?.Dispose(); }
        catch (Win32Exception error) { Debug.WriteLine(error); }
    }

    private static bool WindhawkInstalled()
    {
        Process[] running = Process.GetProcessesByName("windhawk");
        foreach (Process process in running) process.Dispose();
        if (running.Length > 0) return true;
        return new[] { Environment.SpecialFolder.ProgramFiles, Environment.SpecialFolder.ProgramFilesX86 }
            .Any(folder => File.Exists(Path.Combine(Environment.GetFolderPath(folder), "Windhawk", "windhawk.exe")));
    }

    private static readonly GridLength Auto = GridLength.Auto;
    private static readonly GridLength Star = new GridLength(1, GridUnitType.Star);

    private void OpenPlayer(bool showSettings = false)
    {
        if (playerPanel != null) { playerPanel.Activate(); return; }
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
        bool optionsOpen = false;
        panel.Closed += (_, _) => { if (playerPanel == panel) playerPanel = null; };
        panel.Deactivated += (_, _) => Post(() =>
        {
            if (playerPanel == panel && !panel.IsActive && !optionsOpen && !testMenu) panel.Close();
        });

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
        var manual = NewButton(null, T("Dodaj z adresu", "Add by address"));
        manual.HorizontalAlignment = HorizontalAlignment.Left;
        manual.Visibility = Visibility.Collapsed;
        var results = new ListBox();
        var searchStatus = new TextBlock { TextWrapping = TextWrapping.Wrap };
        var searchHeader = Spaced(Orientation.Vertical, 8, Columns((searchBox, Star), (searchButton, Auto)), searchStatus);
        searchHeader.Margin = new Thickness(0, 0, 0, 8);
        var searchPane = new DockPanel { Visibility = Visibility.Collapsed };
        DockPanel.SetDock(searchHeader, Dock.Top);
        searchPane.Children.Add(searchHeader);
        searchPane.Children.Add(results);
        CancellationTokenSource activeSearch = null;
        panel.Closed += (_, _) => activeSearch?.Cancel();

        var settingsButton = NewButton("GhostButton", Theme.Glyph(Theme.SettingsIcon), T("Ustawienia", "Settings"));
        settingsButton.Padding = new Thickness(8, 6, 8, 6);
        settingsButton.VerticalAlignment = VerticalAlignment.Center;
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

        // Keeps the playing station on screen. Centred when the panel opens; otherwise scrolled only as far as needed.
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

        void FillList()
        {
            list.Items.Clear();
            foreach (SavedStation item in Stations) list.Items.Add(StationRow(item));
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
            Stations.Clear();
            Stations.AddRange(updated);
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

        void SetSearchVisible(bool visible)
        {
            searchPane.Visibility = visible ? Visibility.Visible : Visibility.Collapsed;
            list.Visibility = visible ? Visibility.Collapsed : Visibility.Visible;
            manual.Visibility = visible ? Visibility.Visible : Visibility.Collapsed;
            add.Content = visible ? (object)T("Anuluj", "Cancel") : IconText(Theme.PlusIcon, T("Stacja", "Station"));
            if (!visible)
            {
                activeSearch?.Cancel();
                activeSearch = null;
                searchButton.IsEnabled = true;
                results.Items.Clear();
                searchStatus.Text = "";
                ShowActiveStationAfterLayout(false);
            }
        }

        void SetSettingsVisible(bool visible)
        {
            if (visible)
            {
                SetSearchVisible(false);
                fields.Visibility = Visibility.Collapsed;
                editing = null;
            }
            settingsPane.Visibility = visible ? Visibility.Visible : Visibility.Collapsed;
            list.Visibility = visible ? Visibility.Collapsed : Visibility.Visible;
            add.Visibility = visible ? Visibility.Collapsed : Visibility.Visible;
            sectionLabel.Text = visible ? T("Ustawienia", "Settings") : T("Stacje", "Stations");
            backButton.Visibility = visible ? Visibility.Visible : Visibility.Collapsed;
            settingsButton.Visibility = visible ? Visibility.Hidden : Visibility.Visible;
            if (visible) settingsPane.ScrollToTop();
            else ShowActiveStationAfterLayout(false);
        }

        add.Click += (_, _) =>
        {
            SetSearchVisible(searchPane.Visibility != Visibility.Visible);
            fields.Visibility = Visibility.Collapsed;
            if (searchPane.Visibility == Visibility.Visible) searchBox.Focus();
        };
        searchButton.Click += (_, _) => Search();
        searchBox.KeyDown += (_, e) => { if (e.Key == Key.Enter) Search(); };
        manual.Click += (_, _) => { SetSearchVisible(false); Edit(null); };
        settingsButton.Click += (_, _) => SetSettingsVisible(true);
        backButton.Click += (_, _) => SetSettingsVisible(false);

        void CancelForm()
        {
            bool adding = editing == null;
            editing = null;
            fields.Visibility = Visibility.Collapsed;
            if (adding)
            {
                SetSearchVisible(true);
                searchBox.Focus();
            }
        }
        cancelForm.Click += (_, _) => CancelForm();

        void AddSearchResult(DirectoryStation item)
        {
            string address = Storage.IsWebUrl(item.ResolvedUrl) ? item.ResolvedUrl : item.Url;
            if (Stations.Any(entry => entry.Url == address))
            {
                searchStatus.Text = T("Ta stacja jest już na liście.", "This station is already on the list.");
                return;
            }
            var added = new SavedStation { Name = item.Name.Trim(), Url = address, Logo = Storage.IsWebUrl(item.Logo) ? item.Logo : null };
            if (!ApplyStations(Stations.Concat(new[] { added }).ToList())) return;
            if (station < 0) SelectStation(Stations.IndexOf(added));
            list.SelectedIndex = station;
            SetSearchVisible(false);
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
            if (Stations.Any(item => item != editing && item.Url == address))
            {
                message.Text = T("Ten adres jest już na liście.", "This address is already on the list.");
                return;
            }

            var entry = new SavedStation { Name = label, Url = address, Logo = string.IsNullOrEmpty(logoAddress) ? null : logoAddress };
            bool wasSelected = station >= 0 && Stations[station] == editing;
            var updated = editing == null ? Stations.Concat(new[] { entry }).ToList()
                : Stations.Select(item => item == editing ? entry : item).ToList();
            if (!ApplyStations(updated)) return;
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
            if (index < 0 || !ApplyStations(Stations.Where(entry => entry != item).ToList())) return;
            if (index == station)
            {
                station = -1;
                StopPlayback();
                SetTrayText(AppName);
            }
            else if (index < station) station--;
            list.SelectedIndex = station;
            if (lastPlayed == item.Url)
            {
                lastPlayed = null;
                SavePreferences();
            }
            if (editing == item) fields.Visibility = Visibility.Collapsed;
        }

        FrameworkElement ResultRow(DirectoryStation item)
        {
            var button = NewButton("GhostButton", new TextBlock
            {
                Text = string.IsNullOrWhiteSpace(item.Country) ? item.Name : item.Name + " · " + item.Country,
                TextWrapping = TextWrapping.Wrap
            });
            button.HorizontalContentAlignment = HorizontalAlignment.Left;
            button.Padding = new Thickness(10, 8, 10, 8);
            button.Click += (_, _) => AddSearchResult(item);
            return button;
        }

        FrameworkElement StationRow(SavedStation item)
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
                int index = Stations.IndexOf(item);
                if (index < 0) return;
                SelectStation(index);
                if (session == null) StartPlayback();
                list.SelectedIndex = station;
            };
            var actions = NewButton("GhostButton", Theme.Glyph(Theme.MoreIcon), T("Opcje stacji", "Station options"));
            actions.Padding = new Thickness(8, 6, 8, 6);
            actions.Margin = new Thickness(4, 0, 0, 0);
            var options = new ContextMenu { PlacementTarget = actions, Placement = PlacementMode.Bottom };
            options.Items.Add(Item(T("Edytuj", "Edit"), null, () => Edit(item)));
            options.Items.Add(Item(T("Usuń", "Remove"), null, () => Remove(item)));
            options.Opened += (_, _) => optionsOpen = true;
            options.Closed += (_, _) => optionsOpen = false;
            actions.Click += (_, _) => options.IsOpen = true;
            var row = Columns((stationButton, Star), (actions, Auto));
            row.MinHeight = 47;
            return row;
        }

        BitmapSource titleIcon;
        using (Stream resource = typeof(Radio).Assembly.GetManifestResourceStream("radio.ico"))
            titleIcon = new IconBitmapDecoder(resource, BitmapCreateOptions.None, BitmapCacheOption.OnLoad)
                .Frames.OrderByDescending(frame => frame.PixelWidth).First();

        // Settings page, laid out like the Windows 11 Settings app: groups of cards.
        FrameworkElement BuildSettings()
        {
            var page = new StackPanel { Margin = new Thickness(0, 0, 0, 4) };

            // General: language
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
                    OpenPlayer(true);
                });
            };
            page.Children.Add(Group(T("Ogólne", "General"), true));
            page.Children.Add(Card(Theme.Glyph(Theme.GlobeIcon, 20), T("Język", "Language"),
                T("W Windows: ", "In Windows: ") + (SystemPolish ? T("polski", "Polish") : T("angielski", "English")),
                language));

            // Sound: decoder and FFmpeg
            string[] modes = { "auto", "windows", "ffmpeg" };
            var decoding = new ComboBox { MinWidth = 136 };
            decoding.Items.Add(T("Automatycznie", "Automatic"));
            decoding.Items.Add(T("Tylko Windows", "Windows only"));
            decoding.Items.Add(T("Zawsze FFmpeg", "Always FFmpeg"));
            decoding.SelectedIndex = Math.Max(0, Array.IndexOf(modes, decoder));
            string Explain(string mode) =>
                mode == "windows" ? T("Nic nie jest pobierane. Stacje w formatach innych niż MP3 i AAC nie zagrają.",
                                      "Nothing is downloaded. Stations in formats other than MP3 and AAC won't play.")
                : mode == "ffmpeg" ? T("Każda stacja gra przez FFmpeg, pobierany raz (ok. 110 MB).",
                                       "Every station plays through FFmpeg, downloaded once (about 110 MB).")
                : T("MP3 i AAC gra sam Windows. FFmpeg pobiera się tylko dla stacji w innych formatach.",
                    "Windows plays MP3 and AAC itself. FFmpeg is downloaded only for stations in other formats.");
            var explanation = Note(Explain(decoder));

            var ffmpegState = Note("");
            var removeFfmpeg = NewButton(null, T("Usuń", "Remove"));
            removeFfmpeg.Padding = new Thickness(12, 4, 12, 4);
            removeFfmpeg.FontSize = 13;
            var ffmpegLabel = new TextBlock { Text = "FFmpeg", FontSize = 13 };
            var ffmpegRow = Columns((Spaced(Orientation.Vertical, 1, ffmpegLabel, ffmpegState), Star), (removeFfmpeg, Auto));
            removeFfmpeg.Margin = new Thickness(8, 0, 0, 0);
            removeFfmpeg.VerticalAlignment = VerticalAlignment.Center;
            void RefreshFfmpeg()
            {
                string path = FFmpeg.Locate();
                bool downloaded = File.Exists(Path.Combine(FFmpeg.Folder, "ffmpeg.exe"));
                ffmpegState.Text = path == null ? T("Nie pobrano", "Not downloaded")
                    : downloaded && path.StartsWith(FFmpeg.Folder, StringComparison.OrdinalIgnoreCase)
                        ? T("Pobrany przez radio · 100 MB", "Downloaded by the radio · 100 MB")
                        : path;
                removeFfmpeg.Visibility = downloaded ? Visibility.Visible : Visibility.Collapsed;
            }
            removeFfmpeg.Click += (_, _) =>
            {
                try { Directory.Delete(FFmpeg.Folder, true); }
                catch (Exception error) when (error is IOException || error is UnauthorizedAccessException)
                {
                    ffmpegState.Text = T("Teraz w użyciu. Zatrzymaj radio i spróbuj ponownie.", "In use right now. Stop the radio and try again.");
                    return;
                }
                RefreshFfmpeg();
            };
            RefreshFfmpeg();
            decoding.SelectionChanged += (_, _) =>
            {
                string value = modes[decoding.SelectedIndex];
                explanation.Text = Explain(value);
                if (decoder == value) return;
                decoder = value;
                SavePreferences();
                RefreshFfmpeg();
                if (session != null) StartPlayback();
            };
            page.Children.Add(Group(T("Dźwięk", "Sound")));
            page.Children.Add(Card(Theme.Glyph(Theme.WaveIcon, 20), T("Dekodowanie", "Decoding"),
                T("Czym odtwarzane są stacje", "What plays the stations"), decoding, explanation, ffmpegRow));

            // Taskbar: the Windhawk player
            bool windows11 = Environment.OSVersion.Version.Build >= 22000;
            bool windhawk = windows11 && WindhawkInstalled();
            FrameworkElement status = Pill(!windows11 ? T("Tylko Windows 11", "Windows 11 only")
                : windhawk ? T("Windhawk jest", "Windhawk found") : T("Brak Windhawk", "No Windhawk"), windhawk);
            var steps = !windows11 ? new FrameworkElement[0] : new[]
            {
                Step(1, windhawk ? T("Windhawk jest zainstalowany", "Windhawk is installed") : T("Zainstaluj darmowy Windhawk", "Install the free Windhawk"),
                    windhawk ? null : Link(T("Pobierz", "Download"), "https://windhawk.net"), windhawk),
                Step(2, T("Zainstaluj w nim mod Taskbar Fluent Media Player", "In it, install the Taskbar Fluent Media Player mod"),
                    Link(T("Otwórz", "Open"), "https://windhawk.net/mods/taskbar-fluent-media-player")),
                Step(3, T("Prawy klik na odtwarzaczu → Settings → kliknięcie: „Open media app”. Otworzy ten panel.",
                          "Right-click the player → Settings → click action: “Open media app”. It opens this panel."))
            };
            page.Children.Add(Group(T("Pasek zadań", "Taskbar")));
            page.Children.Add(Card(Theme.Glyph(Theme.TaskbarIcon, 20), T("Odtwarzacz na pasku zadań", "Taskbar player"),
                T("Tytuł i przyciski radia na pasku", "Song title and buttons on the taskbar"),
                status, steps));

            // About
            page.Children.Add(Group(T("O aplikacji", "About")));
            page.Children.Add(Card(new Image { Source = titleIcon, Width = 20, Height = 20 }, AppName,
                T("Wersja ", "Version ") + typeof(Radio).Assembly.GetName().Version.ToString(3) + T(" · ikony Lucide", " · Lucide icons"),
                null));
            return page;
        }
        settingsPane.Content = BuildSettings();

        volumeSlider.ValueChanged += (_, e) => ChangeVolume((int)Math.Round(e.NewValue));
        play.Click += (_, _) => TogglePlayback();
        var copy = NewButton("GhostButton", Theme.Glyph(Theme.CopyIcon), T("Kopiuj tytuł", "Copy title"));
        copy.Padding = new Thickness(8);
        copy.VerticalAlignment = VerticalAlignment.Center;
        copy.Click += (_, _) =>
        {
            if (track != null && !CopyText(track)) message.Text = T("Schowek jest zajęty.", "The clipboard is busy.");
        };
        var quit = NewButton("GhostButton", T("Zakończ", "Quit"));
        quit.Margin = new Thickness(12, 0, 0, 0);
        quit.Click += (_, _) => Shutdown();

        var cover = new Image { Width = 42, Height = 42, Stretch = Stretch.Uniform };
        var fallback = Theme.Glyph(Theme.MusicIcon);
        var coverBox = new Grid { Width = 42, Height = 42 };
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
            (settingsButton, Auto));
        var header = Spaced(Orientation.Vertical, 12, titleRow, add, manual, fields, sectionRow);
        header.Margin = new Thickness(0, 0, 0, 8);
        var volumeRow = Columns((volumeText, Auto), (volumeSlider, Star));
        play.HorizontalAlignment = HorizontalAlignment.Stretch;
        var transport = Columns((play, Star), (quit, Auto));
        var footer = Spaced(Orientation.Vertical, 10, trackCard, volumeRow, transport);
        footer.Margin = new Thickness(0, 10, 0, 0);

        var middle = new Grid();
        middle.Children.Add(list);
        middle.Children.Add(searchPane);
        middle.Children.Add(settingsPane);
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
        SetSettingsVisible(showSettings);

        panel.KeyDown += (_, e) =>
        {
            if (e.Key != Key.Escape) return;
            if (settingsPane.Visibility == Visibility.Visible) SetSettingsVisible(false);
            else if (fields.Visibility == Visibility.Visible) CancelForm();
            else if (searchPane.Visibility == Visibility.Visible) SetSearchVisible(false);
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

        void RefreshPanel()
        {
            if (displayedArtwork != artworkUrl)
            {
                displayedArtwork = artworkUrl;
                RefreshArtwork(displayedArtwork);
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
        }

        var timer = new DispatcherTimer { Interval = TimeSpan.FromMilliseconds(250) };
        timer.Tick += (_, _) => RefreshPanel();
        // Clicking anywhere outside the panel closes it, like the Windows flyouts.
        bool pointerDown = true;
        var dismiss = new DispatcherTimer { Interval = TimeSpan.FromMilliseconds(40) };
        dismiss.Tick += (_, _) =>
        {
            bool down = GetAsyncKeyState(1) < 0 || GetAsyncKeyState(2) < 0;
            if (down && !pointerDown && !optionsOpen && !testMenu)
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
        panel.ContentRendered += (_, _) => ShowActiveStation(true);
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
                image.DecodePixelWidth = 80;
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
