using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Net.Http;
using System.Net.NetworkInformation;
using System.Runtime.ExceptionServices;
using System.Runtime.InteropServices;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading;
using System.Threading.Tasks;
using System.Web.Script.Serialization;
using System.Windows;
using System.Windows.Automation;
using System.Windows.Controls;
using System.Windows.Controls.Primitives;
using System.Windows.Media;
using System.Windows.Threading;
using Microsoft.Win32;
using Forms = System.Windows.Forms;
using static Lang;

// Tray icon, tray menu, playback, the Windows media controls (Win+A), history, sleep timer and updates.
// The player panel is in RadioPanel.cs.
internal sealed partial class Radio
{
    internal const string AppName = "Minimalistic Radio";
    private static string NoTrack => L("The station doesn't send song titles");
    private static string Ready => L("Ready to play");
    private static string Connecting => L("Connecting to the station…");
    private static readonly List<SavedStation> Stations = new List<SavedStation>();
    private static Storage.SuggestionList suggestions;   // the station search's empty page, loaded once per run
    private static readonly HttpClient metadataClient = new HttpClient { Timeout = TimeSpan.FromSeconds(8) };

    private readonly Application app;
    private readonly EventWaitHandle panelRequest;
    private readonly bool autostart, updated;
#if SELFTEST
    // The self-test and the README pictures are only in a build made with -p:SelfTest=true (docs/BUILDING.md).
    private readonly bool testMenu;   // --test-menu: VerifyMenu, or TakeScreenshots with --screenshot
    private readonly bool preview = Environment.GetCommandLineArgs().Contains("--preview");
#endif
    private Window playerPanel;
    private RegisteredWaitHandle panelListener;
    private Windows.Media.Playback.MediaPlayer mediaSession;
    private MenuItem statusItem;
    private MenuItem trackItem;
    private Canvas trackViewport;
    private TextBlock trackLabel;
    private readonly DispatcherTimer trackTimer = new DispatcherTimer { Interval = TimeSpan.FromMilliseconds(25) };
    private readonly Stopwatch trackClock = new Stopwatch();
    private string track;
    private int station = -1;
    private string lastPlayed;
    private string artworkUrl;
    private string shownThumbnail;
    private int volume = 30;
    private int unmuteVolume = 30, volumeBefore = 30;   // see ChangeVolume and ToggleMute
    private readonly Stopwatch sinceVolumeChange = new Stopwatch();
    private bool playing;
    private string status = Ready;
    private CancellationTokenSource session;
    private Task audio = Task.CompletedTask;
    private Forms.NotifyIcon tray;
    private System.Drawing.Icon icon;
    private IntPtr iconHandle;
    private Window anchor;
    private ContextMenu popup;

    // Sleep timer: the last 30 seconds fade out.
    private DateTime? sleepAt;
    private int sleepMinutes;
    private int fade = 100;
    private readonly DispatcherTimer sleepTimer = new DispatcherTimer { Interval = TimeSpan.FromSeconds(1) };

    // Network changes (see OnNetworkChanged).
    // Playback stopped after running out of retries: start again if the network is back within 10 minutes,
    // not hours later somewhere else (a laptop opened in a meeting).
    private DateTime? lostConnectionAt;
    private static readonly TimeSpan LostConnectionWindow = TimeSpan.FromMinutes(10);
    private bool networkWasDown;
    private readonly DispatcherTimer networkSettle = new DispatcherTimer { Interval = TimeSpan.FromSeconds(2) };

    // Songs played, newest first.
    private readonly List<HistoryEntry> history = new List<HistoryEntry>();
    private int historyVersion;

    // Updates (see Updater.cs).
    private bool checkUpdates = true;
    private DateTime? lastUpdateCheck;
    private Release readyUpdate;   // downloaded and checked, waiting for a click
    private string readyFile;
    private bool installing, checking;
    private string updateStatus;
    private int updateVersion;
    private readonly DispatcherTimer updateTimer = new DispatcherTimer { Interval = TimeSpan.FromHours(1) };

    internal Radio(Application app, EventWaitHandle panelRequest, bool autostart, bool updated)
    {
        this.app = app;
        this.panelRequest = panelRequest;
        this.autostart = autostart;
        this.updated = updated;
    }

#if SELFTEST
    internal Radio(Application app, EventWaitHandle panelRequest, bool testMenu, bool autostart, bool updated)
        : this(app, panelRequest, autostart, updated) => this.testMenu = testMenu;
#endif

    private void Post(Action action) => app.Dispatcher.BeginInvoke(action);

    private static string Exe => System.Reflection.Assembly.GetEntryAssembly().Location;

    internal void Start()
    {
        iconHandle = Theme.TrayIconHandle();
        icon = iconHandle != IntPtr.Zero ? System.Drawing.Icon.FromHandle(iconHandle) : System.Drawing.Icon.ExtractAssociatedIcon(Exe);
        tray = new Forms.NotifyIcon { Icon = icon, Text = AppName, Visible = true };
        tray.MouseUp += (_, e) => { if (e.Button == Forms.MouseButtons.Right) Post(ShowMenu); };
        tray.MouseClick += (_, e) => { if (e.Button == Forms.MouseButtons.Left) Post(ShowPlayer); };
        tray.BalloonTipClicked += (_, _) => Post(() => OpenPlayer());
#if SELFTEST
        if (!testMenu)
#endif
        {
            LoadStations();
            LoadPreferences();
            LoadHistory();
            StartMenu.Register(Exe);
            Autostart.Refresh(Exe);
            Updater.CleanUp();
            Storage.RemoveOldFFmpeg();
            AttachMediaSession();
            SystemEvents.PowerModeChanged += OnPowerModeChanged;
            NetworkChange.NetworkAvailabilityChanged += OnNetworkChanged;
            NetworkChange.NetworkAddressChanged += OnNetworkChanged;
            networkSettle.Tick += (_, _) => NetworkSettled();
            // Updates: first look 20 s after start, then hourly; CheckForUpdates itself keeps it to every 6 hours.
            updateTimer.Tick += (_, _) => CheckForUpdates(false);
            updateTimer.Start();
            var firstCheck = new DispatcherTimer { Interval = TimeSpan.FromSeconds(20) };
            firstCheck.Tick += (_, _) => { firstCheck.Stop(); CheckForUpdates(false); };
            firstCheck.Start();
            if (updated)
                tray.ShowBalloonTip(4000, AppName, L("Updated to version {0}", Updater.Current.ToString(3)), Forms.ToolTipIcon.Info);
        }
        panelListener = ThreadPool.RegisterWaitForSingleObject(panelRequest,
            (_, _) => Post(() => OpenPlayer()), null, Timeout.Infinite, false);
        trackTimer.Tick += (_, _) => ScrollTrack();
        sleepTimer.Tick += (_, _) => SleepTick();
#if SELFTEST
        if (testMenu) Post(Environment.GetCommandLineArgs().Contains("--screenshot") ? (Action)TakeScreenshots : VerifyMenu);
        else
#endif
        if (station >= 0 && !autostart) Post(StartPlayback);
    }

    // After sleep or hibernation the old connection is dead: start the station again.
    private void OnPowerModeChanged(object sender, PowerModeChangedEventArgs e)
    {
        if (e.Mode == PowerModes.Resume) Post(() => { if (session != null) StartPlayback(); });
    }

    // When the network comes back, connect at once instead of waiting out the retry delays (up to 30 s),
    // or start again if the retries ran out meanwhile. Switching Wi-Fi often changes only the address, not
    // "available", so address changes count too. They come in bursts, so act once they settle.
    private void OnNetworkChanged(object sender, EventArgs e) => Post(() =>
    {
        if ((e as NetworkAvailabilityEventArgs)?.IsAvailable == false) networkWasDown = true;
        networkSettle.Stop();
        networkSettle.Start();
    });

    private void NetworkSettled()
    {
        networkSettle.Stop();
        if (!NetworkInterface.GetIsNetworkAvailable())
        {
            networkWasDown = true;
            return;
        }
        // A station that is still playing kept its connection, unless the network was down in between.
        bool restart = session != null ? !playing || networkWasDown
            : lostConnectionAt != null && DateTime.UtcNow - lostConnectionAt.Value < LostConnectionWindow;
        networkWasDown = false;
        if (restart) StartPlayback();
    }

#if SELFTEST
    // "--test-menu": builds the menu and the panel without playing anything, exit code 0 = OK.
    // With "--preview" it also saves pictures of them (light and dark) to %TEMP%\MinimalisticRadio-*.png.
    private async void VerifyMenu()
    {
        try
        {
            Lang.Verify();   // the catalogs: all there, nothing missing, English for an unknown text
            if (ParseTrack("Sienna Spiro - text=\"Great Expectation\" song_spot=\"M\"", 0) != "Sienna Spiro – Great Expectation" ||
                ParseTrack("title=\"The Way\",artist=\"ARIANA GRANDE / MAC MILLER\",url=\"song_spot=\\\"F\\\"\"", 0) != "ARIANA GRANDE / MAC MILLER – The Way" ||
                ParseTrack("title=\"\",artist=\"\",url=\"\"", 0) != null ||
                ParseTrack("Radio 357 - Najlepszy radiowy adres na świecie!", 3) != null ||
                ParseTrack("The Streets - Blinded by the Lights", 4) != "The Streets - Blinded by the Lights" ||
                ParseTrack("Promo - text=\"Reklama\" song_spot=\"A\"", 0) != null ||
                ParseTrack("- text=\"Spot Block End\" amgTrackId=\"9876543\" length=\"00:00:00\"", 0) != null)
                throw new InvalidOperationException("Błędne metadane.");
            if (iconHandle == IntPtr.Zero || Theme.AppImage(64)?.PixelWidth != 64)
                throw new InvalidOperationException("Brak ikony w zasobach programu.");
            Covers.Split("Leonard Cohen - Everybody Knows", out string artist, out string song);
            Covers.Split("Dżingiel", out string noArtist, out string onlyTitle);
            if (artist != "Leonard Cohen" || song != "Everybody Knows" || noArtist != null || onlyTitle != "Dżingiel" ||
                Updater.ParseVersion("v2.10.0") <= Updater.ParseVersion("v2.9.1") || Updater.ParseVersion("v2.1") != new Version(2, 1, 0))
                throw new InvalidOperationException("Błędny podział tytułu lub numer wersji.");
            // Search shows only what Windows can play: MP3, AAC, AAC+ and unknown codecs, no HLS.
            if (!Storage.Playable("MP3", false) || !Storage.Playable("aac+", false) || !Storage.Playable("UNKNOWN", false) ||
                Storage.Playable("AAC", true) || Storage.Playable("OGG", false) || Storage.Playable("FLAC", false))
                throw new InvalidOperationException("Błędny filtr formatów stacji.");
            if (!new[] { "-- # TOP 100 CHARTS ---", "0R - LO-FI || LoFi, Chill, Study, Hip Hop, Relax", "a,b,c,d,e",
                "*Chill", "Lofi || Chill", "Hits #1", "Top ***", "a, b, c, d, e" }.All(Storage.LooksLikeSpam) ||
                new[] { "RMF FM", "102.7 KIIS FM Los Angeles", "Radio ZET Chilli", "Rock, Pop, Jazz, Blues" }.Any(Storage.LooksLikeSpam))
                throw new InvalidOperationException("Błędne rozpoznawanie śmieciowych nazw stacji.");
            DirectoryStation Sample(string name, string url, string codec = "MP3", bool hls = false) =>
                new DirectoryStation { Name = name, Url = url, Codec = codec, Hls = hls };
            var picked = new[] { Sample("Polecana", "https://a.example/live") };
            DirectoryStation[] popular = Storage.CleanPopular(new[]
            {
                Sample("Pierwsza", "https://one.example/stream"),
                Sample(" pierwsza ", "https://other.example/stream"),    // same name
                Sample("Druga", "http://ONE.example/stream/"),           // same stream
                Sample("Polecana", "https://b.example/live"),            // recommended by name
                Sample("Trzecia", "http://a.example/live"),              // recommended by stream
                Sample("Ogg", "https://c.example/ogg", "OGG"),
                Sample("Hls", "https://d.example/hls", "AAC", true),
                Sample("Czwarta", "https://e.example/stream", "AAC+")
            }, picked);
            if (string.Join("|", popular.Select(item => item.Name)) != "Pierwsza|Czwarta")
                throw new InvalidOperationException("Błędne czyszczenie listy popularnych stacji: " + string.Join("|", popular.Select(item => item.Name)));
            if (string.Join("|", Storage.CleanPopular(new[] { "RMF FM", "Radio RMF FM", "Radio ZET", "Radio ZET Chilli" }
                .Select(name => Sample(name, "https://" + name.Replace(' ', '-') + ".example/s")), new DirectoryStation[0]).Select(item => item.Name)) != "RMF FM|Radio ZET|Radio ZET Chilli")
                throw new InvalidOperationException("Błędne porównywanie nazw stacji.");
            if (Storage.CleanPopular(new[] { Sample("Radio", "https://r1.example/s"), Sample("Radio", "https://r2.example/s") }, new DirectoryStation[0]).Length != 2)
                throw new InvalidOperationException("Dwie stacje o nazwie Radio powinny zostać obie.");
            // "Popular in your country" follows the radio's language (design: languages and country, section 1).
            foreach (var (language, system, expected) in new (string, string, string)[] { ("pl", "US", "PL"), ("pl", null, "PL"), ("es", "MX", "MX"), ("es", "US", "ES"),
                ("en", "US", "US"), ("en", null, null), ("de", "AT", "AT"), ("pt", "BR", "BR") })
                if (Storage.CountryFor(language, system) != expected)
                    throw new InvalidOperationException($"Błędny kraj popularnych stacji: ({language}, {system}) → {Storage.CountryFor(language, system)}.");
            if (Storage.RecommendedIds.Length != 10 ||Storage.CleanPopular(Enumerable.Range(1, 30).Select(n => Sample("S" + n, "https://x.example/" + n)), picked).Length != 15)
                throw new InvalidOperationException("Błędna liczba stacji polecanych lub popularnych.");
            // Where a dragged station lands: after a row once its top edge passes that row's middle (49 px apart, as on the panel).
            double[] rows = { 49, 49, 49, 49, 49 }, mixed = { 30, 60, 30 };
            if (DropIndex(rows, 0, 0) != 0 || DropIndex(rows, 0, 24) != 0 || DropIndex(rows, 0, 25) != 1 || DropIndex(rows, 0, 49 * 2.2) != 2 ||
                DropIndex(rows, 0, 1000) != 4 || DropIndex(rows, 4, 49 * 4) != 4 || DropIndex(rows, 4, 49 * 4 - 24) != 4 ||
                DropIndex(rows, 4, 49 * 4 - 25) != 3 || DropIndex(rows, 4, -1000) != 0 || DropIndex(rows, 2, 49 * 2) != 2 ||
                DropIndex(mixed, 0, 29) != 0 || DropIndex(mixed, 0, 31) != 1 || DropIndex(mixed, 2, 16) != 1 || DropIndex(mixed, 2, 14) != 0)
                throw new InvalidOperationException("Błędne miejsce upuszczenia przeciąganej stacji.");
            using (var testSession = new CancellationTokenSource())
            {
                session = testSession;
                Stations.Add(new SavedStation { Name = "Stacja testowa", Url = "https://example.com/radio" });
                station = 0;
                SetStatus(Stations[0].Name);
                track = string.Concat(Enumerable.Repeat("Wykonawca – Długi tytuł utworu ", 5));
                ShowMenu();
                if (!trackItem.IsEnabled || !trackTimer.IsEnabled || statusItem.Header as string != Stations[0].Name)
                    throw new InvalidOperationException("Błędny wiersz utworu.");
                track = "Krótki tytuł";
                RefreshTrack();
                if (trackTimer.IsEnabled || trackLabel.Text != track)
                    throw new InvalidOperationException("Krótki tytuł nie powinien się przewijać.");
                track = null;
                RefreshTrack();
                if (trackItem.IsEnabled || trackLabel.Text != NoTrack)
                    throw new InvalidOperationException("Brak tytułu powinien wyłączyć kopiowanie.");
                var stations = (MenuItem)popup.Items[1];
                var levels = (MenuItem)popup.Items[2];
                var sleep = (MenuItem)popup.Items[3];
                if (!popup.IsOpen || stations.Items.Count != 1 || levels.Items.Count != 8 || sleep.Items.Count != 7)
                    throw new InvalidOperationException("Nie udało się otworzyć menu radia.");
                if (preview)
                {
                    track = "LEONARD COHEN - EVERYBODY KNOWS";
                    RefreshTrack();
                    await SavePreview(popup, "menu");
                }
                session = null;
                if (preview)
                {
                    Stations.Clear();
                    LoadStations();
                    // A long list (in memory only) with the playing station far down: the list has to scroll to show it.
                    for (int n = 1; Stations.Count < 25; n++)
                        Stations.Insert(0, new SavedStation { Name = "Stacja testowa " + n, Url = "https://example.com/" + n });
                    station = 17;
                    session = testSession;
                    status = StationName;
                    sleepAt = DateTime.Now.AddMinutes(30);
                    readyUpdate = new Release { Version = new Version(9, 9, 9), Tag = "v9.9.9" };
                    foreach (string played in new[] { "Leonard Cohen - Everybody Knows", "Queen - A Kind Of Magic", "Daughtry - What About Now" })
                        AddToHistory(played);
                }
                ShowPlayer();
                if (playerPanel?.IsVisible != true || !Storage.IsWebUrl("https://example.com/live") || Storage.IsWebUrl("file:///tmp/test"))
                    throw new InvalidOperationException("Błędny panel lub walidacja adresu.");
                // Pressing the volume bar next to the knob has to start a drag, not only jump there. The press goes
                // in the way Windows delivers it: PreviewMouseDown tunnels down to the bar.
                var slider = Descendants(playerPanel).OfType<Slider>().First();
                var bar = Descendants(slider).OfType<RepeatButton>().First();
                void Press(RoutedEvent pressEvent) => bar.RaiseEvent(new System.Windows.Input.MouseButtonEventArgs(
                    System.Windows.Input.Mouse.PrimaryDevice, Environment.TickCount, System.Windows.Input.MouseButton.Left) { RoutedEvent = pressEvent });
                Press(System.Windows.Input.Mouse.PreviewMouseDownEvent);
                bool dragging = slider.IsMouseCaptured;
                Press(System.Windows.Input.Mouse.PreviewMouseUpEvent);
                if (!dragging || slider.IsMouseCaptured)
                    throw new InvalidOperationException("Głośności nie da się przeciągać z dowolnego miejsca paska.");
                if (preview)
                {
                    await Task.Delay(3000);
                    var stationList = Descendants(playerPanel).OfType<ListBox>().First(item => item.IsVisible);
                    var row = (FrameworkElement)stationList.ItemContainerGenerator.ContainerFromIndex(station);
                    var viewer = Descendants(stationList).OfType<ScrollViewer>().First();
                    double top = row?.TranslatePoint(new Point(0, 0), viewer).Y ?? -1;
                    if (row == null || top < 0 || top + row.ActualHeight > viewer.ActualHeight + 0.5)
                        throw new InvalidOperationException($"Aktywna stacja poza widokiem (top={top}, wysokość listy={viewer.ActualHeight}).");
                    await SavePreview(playerPanel, "panel");
                    session = null;
                }
                foreach (string page in new[] { "settings", "history" })
                {
                    playerPanel.Close();
                    OpenPlayer(page);
                    if (playerPanel?.IsVisible != true)
                        throw new InvalidOperationException("Nie udało się otworzyć strony: " + page);
                    if (preview)
                    {
                        await Task.Delay(1000);
                        await SavePreview(playerPanel, page);
                        var scroller = Descendants(playerPanel).OfType<ScrollViewer>().First(item => item.IsVisible && item.Content is StackPanel);
                        await SavePreview((Visual)scroller.Content, page + "-all");
                    }
                }
                playerPanel.Close();
                ShowStationPopup();
                if (osd?.IsVisible != true || osdTitle.Text != StationName)
                    throw new InvalidOperationException("Nie pokazała się karta zmiany stacji.");
                if (preview)
                {
                    await Task.Delay(1000);
                    await SavePreview(osd, "osd");
                }
                osd.Hide();
                AttachMediaSession();
                if (mediaSession?.SystemMediaTransportControls.IsNextEnabled != true)
                    throw new InvalidOperationException("Brak systemowego sterowania multimediami.");
                CloseMenu();
                await VerifyStationDrag();
                await VerifyVolumeRow();
                await VerifyCopyFeedback(preview);
            }
        }
        catch (Exception error)
        {
            Environment.ExitCode = 1;
            try { File.WriteAllText(Path.Combine(Path.GetTempPath(), "MinimalisticRadio-test.log"), error.ToString()); }
            catch (IOException) { }
        }
        finally
        {
            session = null;
            Shutdown();
        }
    }

    // "--test-menu --screenshot": pictures for the README (%TEMP%\MinimalisticRadio-shot-*.png), in English,
    // with the saved station list, a real song and its cover, light and dark. Nothing is saved or played.
    private async void TakeScreenshots()
    {
        try
        {
            Lang.Setting = "en";
            LoadStations();
            station = Math.Min(2, Stations.Count - 1);
            using (var shot = new CancellationTokenSource())
            {
                session = shot;
                playing = true;
                status = StationName;
                string[] played = { "Daughtry - What About Now", "Dawid Podsiadło - Małomiasteczkowy", "Queen - A Kind Of Magic",
                    "Editors - Shadow", "Leonard Cohen - Everybody Knows" };
                int chosen = station;
                for (int i = 0; i < played.Length; i++)
                {
                    station = (chosen + played.Length - 1 - i) % Stations.Count;
                    AddToHistory(played[i]);
                }
                station = chosen;
                track = played.Last();
                artworkUrl = await Covers.Find(metadataClient, track);

                ShowMenu();
                await SaveTrayShot(popup, "shot-tray-menu", false);
                CloseMenu();
                foreach (var (page, name) in new[] { ("stations", "tray-panel"), ("search:jazz", "search"), ("history", "history"), ("settings", "settings") })
                {
                    OpenPlayer(page);
                    await Task.Delay(page.StartsWith("search") ? 6000 : 3000);   // results, logos and the cover arrive over the network
                    if (page == "stations") await SaveTrayShot(playerPanel, "shot-" + name, true);
                    else await SavePreview(playerPanel, "shot-" + name);
                    playerPanel.Close();
                }
                ShowStationPopup();
                await Task.Delay(2000);
                await SavePreview(osd, "shot-card");
                osd.Hide();
            }
        }
        catch (Exception error)
        {
            Environment.ExitCode = 1;
            try { File.WriteAllText(Path.Combine(Path.GetTempPath(), "MinimalisticRadio-test.log"), error.ToString()); }
            catch (IOException) { }
        }
        finally
        {
            session = null;
            Shutdown();
        }
    }
#endif

    private static IEnumerable<DependencyObject> Descendants(DependencyObject parent)
    {
        for (int i = 0; i < VisualTreeHelper.GetChildrenCount(parent); i++)
        {
            DependencyObject child = VisualTreeHelper.GetChild(parent, i);
            yield return child;
            foreach (DependencyObject inner in Descendants(child)) yield return inner;
        }
    }

    // ---- Tray menu ----

    private void ShowMenu()
    {
        if (anchor != null)
        {
            CloseMenu();
            return;
        }
        Theme.Apply(app);
        // An invisible window owns the menu, so it closes like a normal menu when clicking elsewhere.
        anchor = new Window
        {
            Width = 1, Height = 1, Left = -100, Top = -100, WindowStyle = WindowStyle.None,
            AllowsTransparency = true, Background = Brushes.Transparent, ShowInTaskbar = false,
            Topmost = true, ResizeMode = ResizeMode.NoResize, WindowStartupLocation = WindowStartupLocation.Manual
        };
        popup = BuildMenu();
        popup.PlacementTarget = anchor;
        popup.Placement = PlacementMode.MousePoint;
        popup.Closed += (_, _) => CloseMenu();
        anchor.Deactivated += (_, _) => Post(() =>
        {
            if (popup != null && !popup.IsOpen) CloseMenu();
        });
        anchor.Show();
        anchor.Activate();
        popup.IsOpen = true;
        RefreshTrack();
    }

    private ContextMenu BuildMenu()
    {
        var menu = new ContextMenu();
        menu.Items.Add(session == null
            ? Item(L("Play"), Theme.PlayIcon, StartPlayback, Stations.Count > 0)
            : Item(L("Stop"), Theme.StopIcon, () => StopPlayback()));
        var stations = Item(L("Station"), Theme.RadioIcon);
        for (int index = 0; index < Stations.Count; index++)
        {
            int selected = index;
            stations.Items.Add(Item(Stations[index].Name,
                index == station ? Theme.CheckIcon : null, () =>
                {
                    SelectStation(selected);
                    ShowStationPopup();
                }));
        }

        var levels = Item(L("Volume") + $" ({volume}%)", Theme.VolumeIcon);
        levels.Items.Add(Item(L("Up 5%"), Theme.PlusIcon, () => ChangeVolume(volume + 5), volume < 100));
        levels.Items.Add(Item(L("Down 5%"), Theme.MinusIcon, () => ChangeVolume(volume - 5), volume > 0));
        levels.Items.Add(new Separator());
        foreach (int preset in new[] { 0, 25, 50, 75, 100 })
            levels.Items.Add(Item(preset == 0 ? L("Mute") : $"{preset}%",
                volume == preset ? Theme.CheckIcon : null, () => ChangeVolume(preset)));

        var sleep = Item(sleepAt == null ? L("Sleep timer") : SleepLabel, Theme.MoonIcon);
        FillSleepMenu(sleep);

        menu.Items.Add(stations);
        menu.Items.Add(levels);
        menu.Items.Add(sleep);
        menu.Items.Add(new Separator());
        statusItem = Item(status, null, null, false);
        menu.Items.Add(statusItem);
        if (session != null)
        {
            trackLabel = new TextBlock { TextWrapping = TextWrapping.NoWrap, FontSize = 13 };
            trackViewport = new Canvas { Width = 300, ClipToBounds = true };
            trackViewport.Children.Add(trackLabel);
            trackItem = Item("", null, CopyTrackFromMenu, false);
            trackItem.Header = trackViewport;
            menu.Items.Add(trackItem);
        }
        menu.Items.Add(new Separator());
        if (readyUpdate != null)
            menu.Items.Add(Item(L("Update to {0}", readyUpdate.Version.ToString(3)), Theme.UpdateReadyIcon, InstallUpdate));
        menu.Items.Add(Item(L("Settings"), Theme.SettingsIcon, () =>
        {
            playerPanel?.Close();
            OpenPlayer("settings");
        }));
        menu.Items.Add(Item(L("Quit"), Theme.QuitIcon, Shutdown));
        return menu;
    }

    private static MenuItem Item(string text, string glyph, Action action = null, bool enabled = true)
    {
        var item = new MenuItem { Header = text, IsEnabled = enabled };
        if (glyph != null) item.Icon = Theme.Glyph(glyph, 16);
        if (action != null) item.Click += (_, _) => action();
        return item;
    }

    // The menu closes on the click, so success is answered with the station card instead of a mark in the menu.
    private void CopyTrackFromMenu()
    {
        string title = track;
        if (title == null) return;
        if (CopyText(title)) ShowCopiedCard(title);
        else tray.ShowBalloonTip(2500, AppName, L("Couldn't copy the title."), Forms.ToolTipIcon.Warning);
    }

    private static bool CopyText(string text)
    {
        try
        {
            Clipboard.SetText(text);
            return true;
        }
        catch (ExternalException error)
        {
            Debug.WriteLine(error);
            return false;
        }
    }

    private void CloseMenu()
    {
        Window window = anchor;
        ContextMenu menu = popup;
        anchor = null;
        popup = null;
        trackTimer.Stop();
        trackClock.Reset();
        statusItem = null;
        trackItem = null;
        trackViewport = null;
        trackLabel = null;
        if (menu?.IsOpen == true) menu.IsOpen = false;
        window?.Close();
    }

    private void SetTrayText(string text) =>
        tray.Text = text.Length <= 63 ? text : text.Substring(0, 62) + "…";

    // ---- Sleep timer ----

    private string SleepLabel => L("Stops at {0}", sleepAt?.ToString("HH:mm"));

    private void FillSleepMenu(ItemsControl target)
    {
        foreach (int minutes in new[] { 15, 30, 45, 60, 90 })
            target.Items.Add(Item(L("{0} min", minutes), sleepAt != null && sleepMinutes == minutes ? Theme.CheckIcon : null,
                () => SetSleepTimer(minutes)));
        target.Items.Add(new Separator());
        target.Items.Add(Item(L("Off"), sleepAt == null ? Theme.CheckIcon : null, () => SetSleepTimer(null)));
    }

    private void SetSleepTimer(int? minutes)
    {
        sleepMinutes = minutes ?? 0;
        sleepAt = minutes == null ? (DateTime?)null : DateTime.Now.AddMinutes(minutes.Value);
        Volatile.Write(ref fade, 100);
        if (sleepAt == null) sleepTimer.Stop();
        else sleepTimer.Start();
    }

    private void SleepTick()
    {
        if (sleepAt == null) { sleepTimer.Stop(); return; }
        double left = (sleepAt.Value - DateTime.Now).TotalSeconds;
        if (left <= 0)
        {
            SetSleepTimer(null);
            if (session != null) StopPlayback(L("Stopped by the sleep timer"));
            else lostConnectionAt = null;   // the radio had already lost the station: don't bring it back later
        }
        else Volatile.Write(ref fade, left >= 30 ? 100 : (int)(left * 100 / 30));
    }

    // What the players use: the chosen volume, lowered while the sleep timer fades out.
    private int EffectiveVolume() => Volatile.Read(ref volume) * Volatile.Read(ref fade) / 100;

    // ---- Playback ----

    private void SelectStation(int index)
    {
        if (station == index || index < 0 || index >= Stations.Count) return;
        station = index;
        SetTrayText(AppName + " · " + Stations[index].Name);
        if (session != null) StartPlayback();
        else
        {
            lostConnectionAt = null;   // another station chosen: don't bring back the lost one
            SetStatus(Ready);
            UpdateMediaSession();
        }
    }

    private void ChangeVolume(int value)
    {
        value = Clamp(value, 0, 100);
        if (value == volume) return;
        // Changes less than a second apart (a drag, the wheel, the arrow keys) count as one: turned down to 0 that way,
        // unmuting brings back the level from before them, not the 1% passed last.
        if (!sinceVolumeChange.IsRunning || sinceVolumeChange.ElapsedMilliseconds > 1000) volumeBefore = volume;
        sinceVolumeChange.Restart();
        if (value == 0 && volumeBefore > 0) unmuteVolume = volumeBefore;
        Volatile.Write(ref volume, value);
        SavePreferences();
        UpdateMediaSession();
    }

    // The panel's speaker button: mutes, and unmutes back to the level from before (30 if there was none). Through
    // ChangeVolume like any change, so the tray menu, the media controls and the saved volume follow.
    private void ToggleMute()
    {
        int before = volume;
        ChangeVolume(before > 0 ? 0 : unmuteVolume);
        if (before > 0) unmuteVolume = before;
    }

    // The speaker for a level, like Windows 11: muted, or one to three waves.
    internal static string VolumeGlyph(int level) =>
        level <= 0 ? Theme.VolumeMutedIcon : level <= 33 ? Theme.Volume1Icon : level <= 66 ? Theme.Volume2Icon : Theme.Volume3Icon;

    private void TogglePlayback()
    {
        if (session == null) StartPlayback();
        else StopPlayback();
    }

    private async void StartPlayback()
    {
        if (Stations.Count == 0) return;
        if (station < 0) station = 0;
        StopPlayback();
        using (var request = new CancellationTokenSource())
        {
            session = request;
            CancellationToken token = request.Token;
            string stream = Stations[station].Url;
            int playingStation = new Uri(stream).Host switch
            {
                "stream.revma.ihrhls.com" => 0,
                "stream.radio357.pl" => 3,
                _ => -1
            };
            SetStatus(Connecting);
            bool everPlayed = false, polling = false;
            Task previous = audio;
            audio = Task.Run(async () =>
            {
                try { await previous.ConfigureAwait(false); }
                catch (Exception) { /* The previous request reports its own error. */ }
                Action started = () =>
                {
                    everPlayed = true;
                    Post(() =>
                    {
                        if (session != request) return;
                        playing = true;
                        lastPlayed = stream;
                        SavePreferences();
                        SetStatus(StationName);
                        if (playingStation == 3 && !polling)
                        {
                            polling = true;
                            _ = PollRadio357(request);
                        }
                    });
                };
                Action<string> titleChanged = value =>
                {
                    if (playingStation != 3) UpdateTrack(request, value, playingStation);
                };
                // Internet radio drops now and then (Wi-Fi, sleep, server restarts): connect again, waiting
                // a bit longer each time. A station that never started gets only two retries.
                int attempt = 0;
                while (true)
                {
                    var clock = Stopwatch.StartNew();
                    ExceptionDispatchInfo failure = null;
                    try
                    {
                        // MP3 and AAC, decoded by Windows itself.
                        StreamPlayer.Play(stream, token, EffectiveVolume, started, titleChanged);
                    }
                    catch (OperationCanceledException) when (token.IsCancellationRequested) { throw; }
                    catch (StationRefusedException) { throw; }   // also a format Windows can't play
                    catch (Exception error) { failure = ExceptionDispatchInfo.Capture(error); }
                    token.ThrowIfCancellationRequested();
                    if (clock.Elapsed > TimeSpan.FromMinutes(1)) attempt = 0;
                    if (attempt >= (everPlayed ? 10 : 2))
                    {
                        failure?.Throw();
                        return;   // the station keeps ending its broadcast
                    }
                    int delay = new[] { 2, 3, 5, 10, 15, 30 }[Math.Min(attempt, 5)];
                    attempt++;
                    Post(() =>
                    {
                        if (session != request) return;
                        playing = false;
                        track = null;
                        artworkUrl = null;
                        RefreshTrack();
                        SetStatus(L("Connection lost. Retrying in {0} s…", delay));
                    });
                    await Task.Delay(TimeSpan.FromSeconds(delay), token).ConfigureAwait(false);
                    Post(() => { if (session == request) SetStatus(Connecting); });
                }
            });
            try
            {
                await audio;
                if (session == request) StopPlayback(L("The broadcast has ended"));
            }
            catch (Exception error)
            {
                if (session == request)
                {
                    StopPlayback(error.Message);
                    // Not refused by the station: the connection was lost and the retries ran out.
                    if (!(error is StationRefusedException)) lostConnectionAt = DateTime.UtcNow;
                }
            }
        }
    }

    private void StopPlayback(string message = null)
    {
        CancellationTokenSource current = session;
        session = null;
        playing = false;
        lostConnectionAt = null;
        current?.Cancel();
        track = null;
        artworkUrl = null;
        RefreshTrack();
        SetStatus(message ?? L("Stopped"));
    }

    private void SetStatus(string message)
    {
        status = message;
        if (statusItem != null) statusItem.Header = message;
        UpdateMediaSession();
    }

    private void RefreshTrack()
    {
        if (trackItem == null) return;
        trackItem.IsEnabled = track != null;
        trackLabel.Text = track ?? NoTrack;
        trackLabel.Measure(new Size(double.PositiveInfinity, double.PositiveInfinity));
        trackViewport.Height = trackLabel.DesiredSize.Height;
        Canvas.SetLeft(trackLabel, 0);
        trackClock.Restart();
        if (trackLabel.DesiredSize.Width > trackViewport.Width) trackTimer.Start();
        else trackTimer.Stop();

        trackItem.ToolTip = track != null ? L("Click to copy the song") : null;
        AutomationProperties.SetName(trackItem, track != null ? L("Copy song: {0}", track) : NoTrack);
    }

    private void ScrollTrack()
    {
        if (trackLabel == null) return;
        double distance = trackLabel.DesiredSize.Width - trackViewport.Width;
        const double speed = 36;
        double travelTime = Math.Max(0, distance) / speed;
        double time = trackClock.Elapsed.TotalSeconds % (travelTime + 2.5);
        Canvas.SetLeft(trackLabel, -Math.Max(0, Math.Min((time - 1.2) * speed, Math.Max(0, distance))));
    }

    private void UpdateTrack(CancellationTokenSource request, string raw, int playingStation)
    {
        string title = ParseTrack(raw, playingStation);
        Match match = Regex.Match(raw ?? "", "amgArtworkURL=\"([^\"]+)\"");
        string cover = title != null && match.Success && Storage.IsWebUrl(match.Groups[1].Value) ? match.Groups[1].Value : null;
        Post(() =>
        {
            if (session != request || track == title) return;
            track = title;
            artworkUrl = cover;
            RefreshTrack();
            UpdateMediaSession();
            if (title == null) return;
            AddToHistory(title);
            if (cover == null) FindCover(request, title);
        });
    }

    private async void FindCover(CancellationTokenSource request, string title)
    {
        string found = await Covers.Find(metadataClient, title);
        if (found == null || session != request || track != title) return;
        artworkUrl = found;
        UpdateMediaSession();
    }

    private static bool Has(string text, string part) => text.IndexOf(part, StringComparison.OrdinalIgnoreCase) >= 0;

    private static string ParseTrack(string raw, int playingStation)
    {
        if (string.IsNullOrWhiteSpace(raw)) return null;
        string value = System.Net.WebUtility.HtmlDecode(raw).Trim();
        if (playingStation == 0)
        {
            // iHeart (KIIS) sends songs either as: title="…",artist="…",url="…"
            Match rich = Regex.Match(value, "^title=\"(?<title>[^\"]*)\",artist=\"(?<artist>[^\"]*)\"");
            if (rich.Success)
            {
                string title = rich.Groups["title"].Value.Trim(), artist = rich.Groups["artist"].Value.Trim();
                if (title.Length == 0 || artist.Length == 0) return null;
                value = artist + " – " + title;
            }
            // …or as: Artist - text="Title" song_spot="M" … (ads use other song_spot values)
            else if (Has(value, "song_spot=") || Has(value, "text=\""))
            {
                const string titleField = " - text=\"";
                int separator = value.IndexOf(titleField, StringComparison.OrdinalIgnoreCase);
                if (separator <= 0 || !Has(value, "song_spot=\"M\"")) return null;
                int start = separator + titleField.Length;
                int end = value.IndexOf("\" song_spot=", start, StringComparison.OrdinalIgnoreCase);
                if (end <= start) return null;
                value = value.Substring(0, separator) + " – " + value.Substring(start, end - start);
            }
        }
        if (value.StartsWith("Radio 357", StringComparison.OrdinalIgnoreCase) ||
            value.StartsWith("Radio Nowy Świat - Pion i poziom", StringComparison.OrdinalIgnoreCase) ||
            !value.Any(char.IsLetterOrDigit))
            return null;
        return value.Length > 240 ? value.Substring(0, 240) + "…" : value;
    }

    private async Task PollRadio357(CancellationTokenSource request)
    {
        CancellationToken token = request.Token;
        while (!token.IsCancellationRequested)
        {
            try
            {
                using (HttpResponseMessage response = await metadataClient.GetAsync("https://stream.radio357.pl/now/playing.json", token))
                {
                    response.EnsureSuccessStatusCode();
                    var root = new JavaScriptSerializer().DeserializeObject(await response.Content.ReadAsStringAsync()) as Dictionary<string, object>;
                    string song = root != null && root.TryGetValue("s", out object value) ? value as string : null;
                    UpdateTrack(request, song, 3);
                }
            }
            catch (OperationCanceledException) when (token.IsCancellationRequested) { return; }
            catch (Exception error) when (error is HttpRequestException || error is ArgumentException ||
                error is InvalidOperationException || error is OperationCanceledException)
            {
                UpdateTrack(request, null, 3);
            }

            try { await Task.Delay(TimeSpan.FromSeconds(10), token); }
            catch (OperationCanceledException) { return; }
        }
    }

    // ---- Windows media controls (Win+A, media keys, lock screen) ----

    // A muted, looping silent clip keeps "Minimalistic Radio" in the Windows media controls
    // (and the Windhawk taskbar player) even while the radio is stopped.
    private void AttachMediaSession()
    {
        try
        {
            mediaSession?.Dispose();
            shownThumbnail = null;
            mediaSession = new Windows.Media.Playback.MediaPlayer();
            mediaSession.CommandManager.IsEnabled = false;
            mediaSession.IsMuted = true;
            mediaSession.Source = Windows.Media.Core.MediaSource.CreateFromStream(CreateSilentMedia(), "audio/wav");
            mediaSession.IsLoopingEnabled = true;
            mediaSession.Play();
            var controls = mediaSession.SystemMediaTransportControls;
            controls.IsEnabled = true;
            controls.IsPlayEnabled = controls.IsPauseEnabled = controls.IsNextEnabled = controls.IsPreviousEnabled = true;
            controls.ButtonPressed += (_, args) => Post(() =>
            {
                switch (args.Button)
                {
                    case Windows.Media.SystemMediaTransportControlsButton.Play:
                        if (session == null) StartPlayback();
                        break;
                    case Windows.Media.SystemMediaTransportControlsButton.Pause:
                        StopPlayback();
                        break;
                    case Windows.Media.SystemMediaTransportControlsButton.Next:
                        if (Stations.Count == 0) break;
                        SelectStation((station + 1) % Stations.Count);
                        ShowStationPopup();
                        break;
                    case Windows.Media.SystemMediaTransportControlsButton.Previous:
                        if (Stations.Count == 0) break;
                        SelectStation((station + Stations.Count - 1) % Stations.Count);
                        ShowStationPopup();
                        break;
                }
            });
            UpdateMediaSession();
        }
        catch (Exception error)
        {
            Debug.WriteLine(error);
            mediaSession?.Dispose();
            mediaSession = null;
        }
    }

    private static Windows.Storage.Streams.InMemoryRandomAccessStream CreateSilentMedia()
    {
        var stream = new Windows.Storage.Streams.InMemoryRandomAccessStream();
        using (var writer = new Windows.Storage.Streams.DataWriter(stream))
        {
            writer.ByteOrder = Windows.Storage.Streams.ByteOrder.LittleEndian;
            writer.WriteBytes(Encoding.ASCII.GetBytes("RIFF"));
            writer.WriteUInt32(16036);
            writer.WriteBytes(Encoding.ASCII.GetBytes("WAVEfmt "));
            writer.WriteUInt32(16);
            writer.WriteUInt16(1);
            writer.WriteUInt16(1);
            writer.WriteUInt32(8000);
            writer.WriteUInt32(16000);
            writer.WriteUInt16(2);
            writer.WriteUInt16(16);
            writer.WriteBytes(Encoding.ASCII.GetBytes("data"));
            writer.WriteUInt32(16000);
            writer.WriteBytes(new byte[16000]);
            writer.StoreAsync().AsTask().GetAwaiter().GetResult();
            writer.DetachStream();
        }
        stream.Seek(0);
        return stream;
    }

    // The song's cover when known, otherwise the station's logo.
    private string CoverUrl => artworkUrl ??
        (station >= 0 && station < Stations.Count && Storage.IsWebUrl(Stations[station].Logo) ? Stations[station].Logo : null);

    private void UpdateMediaSession()
    {
        if (mediaSession == null) return;
        try
        {
            var controls = mediaSession.SystemMediaTransportControls;
            controls.PlaybackStatus = session == null ? Windows.Media.MediaPlaybackStatus.Paused
                : playing ? Windows.Media.MediaPlaybackStatus.Playing : Windows.Media.MediaPlaybackStatus.Changing;
            var display = controls.DisplayUpdater;
            display.Type = Windows.Media.MediaPlaybackType.Music;
            Covers.Split(track, out string artist, out string song);
            display.MusicProperties.Title = track == null ? StationName : song;
            display.MusicProperties.Artist = track == null ? AppName : artist ?? StationName;
            display.MusicProperties.AlbumTitle = StationName;
            string picture = CoverUrl;
            if (picture != shownThumbnail)
            {
                shownThumbnail = picture;
                display.Thumbnail = picture == null ? null
                    : Windows.Storage.Streams.RandomAccessStreamReference.CreateFromUri(new Uri(picture));
            }
            display.Update();
        }
        catch (Exception error) { Debug.WriteLine(error); }
    }

    // ---- History ----

    private void AddToHistory(string title)
    {
        if (history.Count > 0 && history[0].Title == title && history[0].Station == StationName) return;
        history.Insert(0, new HistoryEntry { Title = title, Station = StationName, Time = DateTime.Now });
        if (history.Count > 100) history.RemoveRange(100, history.Count - 100);
        historyVersion++;
        SaveHistory();
    }

    private void ClearHistory()
    {
        history.Clear();
        historyVersion++;
        SaveHistory();
    }

    private void SaveHistory()
    {
#if SELFTEST
        if (testMenu) return;
#endif
        try { Storage.Write(Storage.HistoryFile, history); }
        catch (Exception error) when (error is IOException || error is UnauthorizedAccessException) { Debug.WriteLine(error); }
    }

    private void LoadHistory()
    {
        var saved = Storage.Read<List<HistoryEntry>>(Storage.HistoryFile);
        if (saved != null) history.AddRange(saved.Where(entry => !string.IsNullOrEmpty(entry?.Title)).Take(100));
    }

    // ---- Updates ----
    // Like Discord: every few hours the radio looks for a newer release and quietly downloads it
    // (checked against GitHub's SHA-256). A green arrow in the panel then says "Update Ready!",
    // and a click swaps the exe and restarts into the new version. No pop-ups.

    private static readonly TimeSpan UpdateInterval = TimeSpan.FromHours(6);

    private async void CheckForUpdates(bool manual)
    {
#if SELFTEST
        if (testMenu) return;
#endif
        if (installing || checking) return;
        if (!manual && (!checkUpdates || (lastUpdateCheck != null &&
            DateTime.UtcNow - lastUpdateCheck.Value.ToUniversalTime() < UpdateInterval)))
            return;
        checking = true;
        lastUpdateCheck = DateTime.UtcNow;
        SavePreferences();
        if (manual)
        {
            updateStatus = L("Checking…");
            updateVersion++;
        }
        try
        {
            Release latest = await Updater.Latest(metadataClient);
            if (latest == null || latest.Version <= Updater.Current)
                updateStatus = manual ? L("You have the latest version.") : null;
            else if (readyUpdate?.Tag != latest.Tag || !File.Exists(readyFile))
            {
                if (manual)
                {
                    updateStatus = L("Downloading version {0}…", latest.Version.ToString(3));
                    updateVersion++;
                }
                string file = await Updater.Download(latest, null);
                if (readyFile != null && readyFile != file)
                {
                    try { File.Delete(readyFile); }
                    catch (Exception error) when (error is IOException || error is UnauthorizedAccessException) { Debug.WriteLine(error); }
                }
                readyUpdate = latest;
                readyFile = file;
                updateStatus = null;
            }
            else updateStatus = null;
        }
        catch (Exception error) when (error is HttpRequestException || error is IOException || error is InvalidDataException ||
            error is OperationCanceledException || error is ArgumentException || error is InvalidOperationException ||
            error is UnauthorizedAccessException)
        {
            Debug.WriteLine(error);
            if (manual) updateStatus = L("Couldn't check for updates.");
        }
        finally { checking = false; }
        updateVersion++;
    }

    private void InstallUpdate()
    {
        Release release = readyUpdate;
        if (release == null || installing) return;
        if (!File.Exists(readyFile))
        {
            // The downloaded file was cleaned from the temporary folder: get it again.
            readyUpdate = null;
            readyFile = null;
            updateVersion++;
            CheckForUpdates(true);
            return;
        }
        installing = true;
        try
        {
            Updater.Install(readyFile);   // swaps the exe and starts the new version
            Shutdown();
        }
        catch (Exception error) when (error is IOException || error is UnauthorizedAccessException ||
            error is System.ComponentModel.Win32Exception || error is ArgumentException)
        {
            Debug.WriteLine(error);
            installing = false;
            readyUpdate = null;
            readyFile = null;
            updateStatus = L("Couldn't install it. Opening the page with the new version.");
            updateVersion++;
            OpenWebPage(release.Page ?? Updater.Page + "/releases/latest");
        }
    }

    // ---- Stored settings ----

    private string StationName => station >= 0 && station < Stations.Count ? Stations[station].Name : AppName;

    private void LoadPreferences()
    {
        Preferences saved = Storage.Read<Preferences>(Storage.PreferencesFile);
        if (saved == null) return;
        volume = Clamp(saved.Volume, 0, 100);
        lastPlayed = saved.LastPlayed;
        Lang.Setting = IsSupported(saved.Language) ? saved.Language : "auto";
        checkUpdates = saved.CheckUpdates ?? true;
        lastUpdateCheck = saved.LastUpdateCheck;
        showStationPopup = saved.ShowStationPopup ?? true;
        station = Stations.FindIndex(item => item.Url == lastPlayed);
        if (station >= 0) SetTrayText(AppName + " · " + Stations[station].Name);
    }

    private void SavePreferences()
    {
#if SELFTEST
        if (testMenu) return;
#endif
        try
        {
            Storage.Write(Storage.PreferencesFile, new Preferences
            {
                Volume = volume, LastPlayed = lastPlayed, Language = Lang.Setting,
                CheckUpdates = checkUpdates, LastUpdateCheck = lastUpdateCheck, ShowStationPopup = showStationPopup
            });
        }
        catch (Exception error) when (error is IOException || error is UnauthorizedAccessException)
        { Debug.WriteLine(error); }
    }

    private void LoadStations()
    {
        var saved = Storage.Read<List<SavedStation>>(Storage.StationFile);
        foreach (var item in saved ?? new List<SavedStation>())
            if (item != null && !string.IsNullOrWhiteSpace(item.Name) && Storage.IsWebUrl(item.Url))
                Stations.Add(item);
    }

    private static int Clamp(int value, int min, int max) => Math.Max(min, Math.Min(max, value));

    private void Shutdown()
    {
        SystemEvents.PowerModeChanged -= OnPowerModeChanged;
        NetworkChange.NetworkAvailabilityChanged -= OnNetworkChanged;
        NetworkChange.NetworkAddressChanged -= OnNetworkChanged;
        networkSettle.Stop();
        updateTimer.Stop();
        sleepTimer.Stop();
        StopPlayback();
        CloseMenu();
        panelListener?.Unregister(null);
        playerPanel?.Close();
        osdTimer.Stop();
        osd?.Close();
        mediaSession?.Dispose();
        tray?.Dispose();
        icon?.Dispose();
        if (iconHandle != IntPtr.Zero) Theme.DestroyIcon(iconHandle);
        app.Shutdown();
    }
}
