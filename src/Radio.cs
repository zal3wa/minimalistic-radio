using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Net.Http;
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
using Forms = System.Windows.Forms;
using static Lang;

// Tray icon, tray menu, playback and the Windows media controls. The player panel is in Panel.cs.
internal sealed partial class Radio
{
    internal const string AppName = "Minimalistic Radio";
    private static string NoTrack => T("Stacja nie podaje tytułu", "The station doesn't send song titles");
    private static string Ready => T("Gotowe do odtwarzania", "Ready to play");
    private static readonly List<SavedStation> Stations = new List<SavedStation>();
    private static readonly HttpClient metadataClient = new HttpClient { Timeout = TimeSpan.FromSeconds(5) };

    private readonly Application app;
    private readonly EventWaitHandle panelRequest;
    private readonly bool testMenu;
    private readonly bool preview = Environment.GetCommandLineArgs().Contains("--preview");
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
    private int volume = 30;
    private string decoder = "auto";   // "auto": Windows, FFmpeg when needed; "windows"; "ffmpeg"
    private string status = Ready;
    private CancellationTokenSource session;
    private Task audio = Task.CompletedTask;
    private Forms.NotifyIcon tray;
    private System.Drawing.Icon icon;
    private Window anchor;
    private ContextMenu popup;

    internal Radio(Application app, EventWaitHandle panelRequest, bool testMenu)
    {
        this.app = app;
        this.panelRequest = panelRequest;
        this.testMenu = testMenu;
    }

    private void Post(Action action) => app.Dispatcher.BeginInvoke(action);

    internal void Start()
    {
        using (Stream resource = typeof(Radio).Assembly.GetManifestResourceStream("radio.ico"))
            icon = new System.Drawing.Icon(resource);
        tray = new Forms.NotifyIcon { Icon = icon, Text = AppName, Visible = true };
        tray.MouseUp += (_, e) => { if (e.Button == Forms.MouseButtons.Right) Post(ShowMenu); };
        tray.MouseClick += (_, e) => { if (e.Button == Forms.MouseButtons.Left) Post(ShowPlayer); };
        if (!testMenu)
        {
            LoadStations();
            LoadPreferences();
            StartMenu.Register(System.Reflection.Assembly.GetEntryAssembly().Location);
            AttachMediaSession();
        }
        panelListener = ThreadPool.RegisterWaitForSingleObject(panelRequest,
            (_, _) => Post(() => OpenPlayer()), null, Timeout.Infinite, false);
        trackTimer.Tick += (_, _) => ScrollTrack();
        if (testMenu) Post(VerifyMenu);
        else if (station >= 0) Post(StartPlayback);
    }

    // "--test-menu": builds the menu and the panel without playing anything, exit code 0 = OK.
    // With "--preview" it also saves pictures of them (light and dark) to %TEMP%\MinimalisticRadio-*.png.
    private async void VerifyMenu()
    {
        try
        {
            if (ParseTrack("Sienna Spiro - text=\"Great Expectation\" song_spot=\"M\"", 0) != "Sienna Spiro – Great Expectation" ||
                ParseTrack("title=\"The Way\",artist=\"ARIANA GRANDE / MAC MILLER\",url=\"song_spot=\\\"F\\\"\"", 0) != "ARIANA GRANDE / MAC MILLER – The Way" ||
                ParseTrack("title=\"\",artist=\"\",url=\"\"", 0) != null ||
                ParseTrack("Radio 357 - Najlepszy radiowy adres na świecie!", 3) != null ||
                ParseTrack("The Streets - Blinded by the Lights", 4) != "The Streets - Blinded by the Lights" ||
                ParseTrack("Promo - text=\"Reklama\" song_spot=\"A\"", 0) != null ||
                ParseTrack("- text=\"Spot Block End\" amgTrackId=\"9876543\" length=\"00:00:00\"", 0) != null)
                throw new InvalidOperationException("Błędne metadane.");
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
                if (!popup.IsOpen || stations.Items.Count != 1 || levels.Items.Count != 8)
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
                }
                ShowPlayer();
                if (playerPanel?.IsVisible != true || !Storage.IsWebUrl("https://example.com/live") || Storage.IsWebUrl("file:///tmp/test"))
                    throw new InvalidOperationException("Błędny panel lub walidacja adresu.");
                if (preview)
                {
                    await Task.Delay(3000);
                    var stationList = Descendants(playerPanel).OfType<ListBox>().First(item => item.IsVisible);
                    var row = (FrameworkElement)stationList.ItemContainerGenerator.ContainerFromIndex(station);
                    var viewer = Descendants(stationList).OfType<ScrollViewer>().First();
                    double top = row?.TranslatePoint(new Point(0, 0), viewer).Y ?? -1;
                    if (row == null || top < 0 || top + row.ActualHeight > viewer.ActualHeight + 0.5)
                        throw new InvalidOperationException($"Aktywna stacja poza widokiem (top={top}, wysokość listy={viewer.ActualHeight}).");
                    File.WriteAllText(Path.Combine(Path.GetTempPath(), "MinimalisticRadio-scroll.txt"),
                        $"aktywna stacja {station + 1}/{Stations.Count}: od {top:F0} do {top + row.ActualHeight:F0} px, lista ma {viewer.ActualHeight:F0} px");
                    await SavePreview((Visual)playerPanel.Content, "panel");
                    session = null;
                }
                playerPanel.Close();
                OpenPlayer(true);
                if (playerPanel?.IsVisible != true)
                    throw new InvalidOperationException("Nie udało się otworzyć ustawień.");
                if (preview)
                {
                    await Task.Delay(1000);
                    await SavePreview((Visual)playerPanel.Content, "settings");
                    var scroller = Descendants(playerPanel).OfType<ScrollViewer>().First(item => item.IsVisible && item.Content is StackPanel);
                    await SavePreview((Visual)scroller.Content, "settings-all");
                }
                playerPanel.Close();
                AttachMediaSession();
                if (mediaSession?.SystemMediaTransportControls.IsNextEnabled != true)
                    throw new InvalidOperationException("Brak systemowego sterowania multimediami.");
                CloseMenu();
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

    private static IEnumerable<DependencyObject> Descendants(DependencyObject parent)
    {
        for (int i = 0; i < VisualTreeHelper.GetChildrenCount(parent); i++)
        {
            DependencyObject child = VisualTreeHelper.GetChild(parent, i);
            yield return child;
            foreach (DependencyObject inner in Descendants(child)) yield return inner;
        }
    }

    private async Task SavePreview(Visual visual, string name)
    {
        foreach (bool dark in new[] { false, true })
        {
            Theme.Apply(app, dark);
            await Task.Delay(400);
            var element = (FrameworkElement)visual;
            double scale = VisualTreeHelper.GetDpi(visual).DpiScaleX;
            var bitmap = new System.Windows.Media.Imaging.RenderTargetBitmap(
                (int)Math.Ceiling(element.ActualWidth * scale), (int)Math.Ceiling(element.ActualHeight * scale),
                96 * scale, 96 * scale, PixelFormats.Pbgra32);
            bitmap.Render(visual);
            var encoder = new System.Windows.Media.Imaging.PngBitmapEncoder();
            encoder.Frames.Add(System.Windows.Media.Imaging.BitmapFrame.Create(bitmap));
            using (FileStream file = File.Create(Path.Combine(Path.GetTempPath(),
                "MinimalisticRadio-" + name + (dark ? "-dark" : "-light") + ".png")))
                encoder.Save(file);
        }
        Theme.Apply(app);
    }

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
            ? Item(T("Odtwórz", "Play"), Theme.PlayIcon, StartPlayback, Stations.Count > 0)
            : Item(T("Zatrzymaj", "Stop"), Theme.StopIcon, () => StopPlayback()));
        var stations = Item(T("Stacja", "Station"), Theme.RadioIcon);
        for (int index = 0; index < Stations.Count; index++)
        {
            int selected = index;
            stations.Items.Add(Item(Stations[index].Name,
                index == station ? Theme.CheckIcon : null, () => SelectStation(selected)));
        }

        var levels = Item(T("Głośność", "Volume") + $" ({volume}%)", Theme.VolumeIcon);
        levels.Items.Add(Item(T("Zwiększ o 5%", "Up 5%"), Theme.PlusIcon, () => ChangeVolume(volume + 5), volume < 100));
        levels.Items.Add(Item(T("Zmniejsz o 5%", "Down 5%"), Theme.MinusIcon, () => ChangeVolume(volume - 5), volume > 0));
        levels.Items.Add(new Separator());
        foreach (int preset in new[] { 0, 25, 50, 75, 100 })
            levels.Items.Add(Item(preset == 0 ? T("Wycisz", "Mute") : $"{preset}%",
                volume == preset ? Theme.CheckIcon : null, () => ChangeVolume(preset)));

        menu.Items.Add(stations);
        menu.Items.Add(levels);
        menu.Items.Add(new Separator());
        statusItem = Item(status, null, null, false);
        menu.Items.Add(statusItem);
        if (session != null)
        {
            trackLabel = new TextBlock { TextWrapping = TextWrapping.NoWrap, FontSize = 13 };
            trackViewport = new Canvas { Width = 300, ClipToBounds = true };
            trackViewport.Children.Add(trackLabel);
            trackItem = Item("", null, () =>
            {
                string title = track;
                if (title != null && !CopyText(title))
                    tray.ShowBalloonTip(2500, AppName, T("Nie udało się skopiować tytułu.", "Couldn't copy the title."), Forms.ToolTipIcon.Warning);
            }, false);
            trackItem.Header = trackViewport;
            menu.Items.Add(trackItem);
        }
        menu.Items.Add(new Separator());
        menu.Items.Add(Item(T("Ustawienia", "Settings"), Theme.SettingsIcon, () =>
        {
            playerPanel?.Close();
            OpenPlayer(true);
        }));
        menu.Items.Add(Item(T("Zakończ", "Quit"), Theme.QuitIcon, Shutdown));
        return menu;
    }

    private static MenuItem Item(string text, string glyph, Action action = null, bool enabled = true)
    {
        var item = new MenuItem { Header = text, IsEnabled = enabled };
        if (glyph != null) item.Icon = Theme.Glyph(glyph, 16);
        if (action != null) item.Click += (_, _) => action();
        return item;
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

    private void SelectStation(int index)
    {
        if (station == index || index < 0 || index >= Stations.Count) return;
        station = index;
        SetTrayText(AppName + " · " + Stations[index].Name);
        if (session != null) StartPlayback();
        else SetStatus(Ready);
    }

    private void ChangeVolume(int value)
    {
        value = Clamp(value, 0, 100);
        if (value == volume) return;
        Volatile.Write(ref volume, value);
        SavePreferences();
        UpdateMediaSession();
    }

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
            string stream = Stations[station].Url;
            int playingStation = new Uri(stream).Host switch
            {
                "stream.revma.ihrhls.com" => 0,
                "stream.radio357.pl" => 3,
                _ => -1
            };
            SetStatus(Connecting);
            string mode = decoder;
            Task previous = audio;
            audio = Task.Run(async () =>
            {
                try { await previous.ConfigureAwait(false); }
                catch (Exception) { /* The previous request reports its own error. */ }
                Action started = () => Post(() =>
                {
                    if (session != request) return;
                    lastPlayed = stream;
                    SavePreferences();
                    SetStatus(StationName);
                    if (playingStation == 3) _ = PollRadio357(request);
                });
                Action<string> titleChanged = value =>
                {
                    if (playingStation != 3) UpdateTrack(request, value, playingStation);
                };
                if (mode != "ffmpeg")
                {
                    try
                    {
                        // MP3 and AAC: Windows' own decoders, nothing to download.
                        StreamPlayer.Play(stream, request.Token, () => Volatile.Read(ref volume), started, titleChanged);
                        return;
                    }
                    catch (UnsupportedFormatException) when (mode == "windows")
                    {
                        throw new InvalidOperationException(T(
                            "Ta stacja nadaje w formacie, którego Windows nie obsługuje. Włącz FFmpeg w ustawieniach.",
                            "This station uses a format Windows can't play. Turn on FFmpeg in the settings."));
                    }
                    catch (UnsupportedFormatException) { }
                }
                // Anything else (Ogg/Opus, FLAC, HLS…) or FFmpeg chosen in the settings:
                // FFmpeg, downloaded the first time it is needed.
                Task<string> ffmpeg = EnsureFFmpeg(request.Token);
                if (!ffmpeg.IsCompleted)
                {
                    await ffmpeg.ConfigureAwait(false);
                    Post(() => { if (session == request) SetStatus(Connecting); });
                }
                FfmpegPlayer.Play(await ffmpeg.ConfigureAwait(false), stream, request.Token,
                    () => Volatile.Read(ref volume), started, titleChanged);
            });
            try
            {
                await audio;
                if (session == request) StopPlayback(T("Transmisja zakończyła się", "The broadcast has ended"));
            }
            catch (Exception error)
            {
                if (session == request) StopPlayback(error.Message);
            }
        }
    }

    private static string Connecting => T("Łączenie ze stacją…", "Connecting to the station…");

    private Task<string> EnsureFFmpeg(CancellationToken cancel) =>
        FFmpeg.EnsureAsync(percent => Post(() => SetStatus(percent < 100
            ? T("Pobieranie FFmpeg (jednorazowo)… ", "Downloading FFmpeg (one time)… ") + percent + "%"
            : T("Instalowanie FFmpeg…", "Installing FFmpeg…"))), cancel);

    private void StopPlayback(string message = null)
    {
        CancellationTokenSource current = session;
        session = null;
        current?.Cancel();
        track = null;
        artworkUrl = null;
        RefreshTrack();
        SetStatus(message ?? T("Zatrzymano", "Stopped"));
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

        trackItem.ToolTip = track != null ? T("Kliknij, aby skopiować utwór", "Click to copy the song") : null;
        AutomationProperties.SetName(trackItem, track != null ? T("Skopiuj utwór: ", "Copy song: ") + track : NoTrack);
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
        string cover = title != null && match.Success ? match.Groups[1].Value : null;
        Post(() =>
        {
            if (session != request) return;
            if (track == title && artworkUrl == cover) return;
            track = title;
            artworkUrl = cover;
            RefreshTrack();
            UpdateMediaSession();
        });
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

    // A muted, looping silent clip keeps "Minimalistic Radio" in the Windows media controls
    // (and the Windhawk taskbar player) even while the radio is stopped.
    private void AttachMediaSession()
    {
        try
        {
            mediaSession?.Dispose();
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
                        if (Stations.Count > 0) SelectStation((station + 1) % Stations.Count);
                        break;
                    case Windows.Media.SystemMediaTransportControlsButton.Previous:
                        if (Stations.Count > 0) SelectStation((station + Stations.Count - 1) % Stations.Count);
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

    private void UpdateMediaSession()
    {
        if (mediaSession == null) return;
        try
        {
            var controls = mediaSession.SystemMediaTransportControls;
            controls.PlaybackStatus = session == null ? Windows.Media.MediaPlaybackStatus.Paused : Windows.Media.MediaPlaybackStatus.Playing;
            var display = controls.DisplayUpdater;
            display.Type = Windows.Media.MediaPlaybackType.Music;
            display.MusicProperties.Title = track ?? StationName;
            display.MusicProperties.Artist = track == null ? AppName : StationName;
            display.Update();
        }
        catch (Exception error) { Debug.WriteLine(error); }
    }

    private string StationName => station >= 0 && station < Stations.Count ? Stations[station].Name : AppName;

    private void LoadPreferences()
    {
        Preferences saved = Storage.Read<Preferences>(Storage.PreferencesFile);
        if (saved == null) return;
        volume = Clamp(saved.Volume, 0, 100);
        lastPlayed = saved.LastPlayed;
        decoder = saved.Decoder == "windows" || saved.Decoder == "ffmpeg" ? saved.Decoder : "auto";
        Lang.Setting = saved.Language == "pl" || saved.Language == "en" ? saved.Language : "auto";
        station = Stations.FindIndex(item => item.Url == lastPlayed);
        if (station >= 0) SetTrayText(AppName + " · " + Stations[station].Name);
    }

    private void SavePreferences()
    {
        if (testMenu) return;
        try
        {
            Storage.Write(Storage.PreferencesFile, new Preferences
                { Volume = volume, LastPlayed = lastPlayed, Language = Lang.Setting, Decoder = decoder });
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
        StopPlayback();
        CloseMenu();
        panelListener?.Unregister(null);
        playerPanel?.Close();
        mediaSession?.Dispose();
        tray?.Dispose();
        icon?.Dispose();
        app.Shutdown();
    }
}
