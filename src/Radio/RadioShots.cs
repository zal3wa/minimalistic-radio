#if SELFTEST
// Only in a build made with -p:SelfTest=true (docs/BUILDING.md): the README pictures and the --preview ones.
using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Threading.Tasks;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Controls.Primitives;
using System.Windows.Media;
using System.Windows.Media.Effects;
using System.Windows.Media.Imaging;
using static Lang;
using Path = System.Windows.Shapes.Path;
using Rectangle = System.Windows.Shapes.Rectangle;

// The first README picture shows the app where it lives: the corner of a Windows 11 taskbar with the tray
// icon and the menu a right click opens above it, as wide as the Linux one beside the clock. The menu is the
// app's real one; the desktop and the taskbar around it are drawn.
internal sealed partial class Radio
{
    // The README pictures' stations and songs, as in the Linux ones (linux/minimalistic_radio/selftest.py).
    private static readonly SavedStation[] ShotStations =
    {
        new SavedStation { Name = "102.7 KIIS FM Los Angeles", Url = "http://stream.revma.ihrhls.com/zc185",
            Logo = "https://i.iheart.com/v3/re/assets.brands/61d4a04fc786e58c38995162?ops=gravity(%22center%22),contain(360,360)&quality=80" },
        new SavedStation { Name = "Radio Nowy Świat", Url = "https://stream.nowyswiat.online/mp3",
            Logo = "https://dabplus.live/logo/ea4141ebdcca43ef81e6f8e7351b4309.png" },
        new SavedStation { Name = "Antyradio Hard", Url = "https://an05.cdn.eurozet.pl/ANTHAR.mp3",
            Logo = "https://gfx-player.radiozet.pl/var/player/storage/images/player-antyradio/kanaly-muzyczne/antyradio-hard/710016-10-pol-PL/Antyradio-Hard_size-228x228.jpg" },
        new SavedStation { Name = "Radio 357", Url = "https://stream.radio357.pl/",
            Logo = "https://radio357.pl/wp-content/uploads/2022/04/c5399c0d-1b8e-43d5-b23b-e5cef1857856.png" },
        new SavedStation { Name = "RMF Classic", Url = "http://31.192.216.8/RMFCLASSIC48" },
        new SavedStation { Name = "RMF Classic Rock", Url = "https://rs201-krk.rmfstream.pl/rmf_classic_rock",
            Logo = "https://www.rmfon.pl/assets/images/favicon/apple-touch-icon.png" },
        new SavedStation { Name = "Polskie Radio Jedynka AAC", Url = "http://stream3.polskieradio.pl:8950/;.mp3" },
        new SavedStation { Name = "Polskie Radio - Czwórka (Program 4) (AAC+)", Url = "http://stream3.polskieradio.pl:8956/;" },
    };
    private static readonly (string Song, int Station)[] ShotSongs =   // the oldest first; the last one is playing
    {
        ("Daughtry - What About Now", 7), ("Dawid Podsiadło - Małomiasteczkowy", 5), ("Queen - A Kind Of Magic", 4),
        ("Editors - Shadow", 3), ("Leonard Cohen - Everybody Knows", 2),
    };

    private const double SceneWidth = 778;     // the Linux tray picture's width in the README
    private const double TaskbarHeight = 48, MenuGap = 8, DesktopAboveMenu = 24;
    // The notification area from the right edge: show desktop strip, clock, network/volume/battery, our icon.
    private const double ShowDesktopWidth = 8, ClockWidth = 76, QuickSettingsWidth = 92, TrayButtonWidth = 32;
    private const double TrayIconFromRight = ShowDesktopWidth + ClockWidth + QuickSettingsWidth + TrayButtonWidth / 2;
    private const double MenuShadow = 6;   // the menu's template leaves room for its shadow on the right and bottom

    // --preview: over a year of listening, in memory only (nothing is saved), so that the Statistics page shows each
    // period differently. The stations are the last ones of the list (the saved ones, with their logos).
    private void FillSampleStatistics()
    {
        statistics.Clear(DateTime.UtcNow);
        if (Stations.Count == 0) return;
        var random = new Random(7);
        string[] songs =
        {
            "Leonard Cohen - Everybody Knows", "Editors - Shadow", "Queen - A Kind Of Magic", "Dawid Podsiadło - Małomiasteczkowy",
            "Daughtry - What About Now", "Metallica - One", "Queen - Radio Ga Ga", "Leonard Cohen - Hallelujah", "Editors - Papillon", "Dżingiel"
        };
        int[] hours = { 7, 8, 12, 16, 17, 18, 19, 19, 20, 20, 20, 21, 21, 22, 23 };   // mostly in the evening
        DateTime now = DateTime.UtcNow;
        for (int day = 420; day >= 0; day--)
            for (int count = random.Next(3); count > 0; count--)
            {
                int pick = Stations.Count - 1 - random.Next(Math.Min(6, Stations.Count));
                SavedStation played = Stations[pick];
                DateTime start = DateTime.Today.AddDays(-day).AddHours(hours[random.Next(hours.Length)]).AddMinutes(random.Next(60)).ToUniversalTime();
                if (start >= now) continue;
                DateTime end = start.AddMinutes(15 + random.Next(150));
                if (end > now) end = now;
                bool titles = pick % 3 != 0;   // some stations send no song titles
                statistics.Sessions.Add(new ListeningSession { Station = played.Name, Url = played.Url, Start = start, End = end, Titles = titles });
                if (titles)
                    for (DateTime time = start.AddMinutes(2); time < end; time = time.AddMinutes(4))
                        statistics.Songs.Add(new PlayedSong { Station = played.Name, Title = songs[random.Next(songs.Length)], Time = time });
            }
    }

    // The README pictures (--screenshot) are drawn at 2× (192 DPI) whatever the screen's scaling, sharp on high-density
    // screens; the --preview ones at the screen's own. 0: the screen's.
    private double shotScale;

    private double ScaleOf(Visual visual) => shotScale > 0 ? shotScale : VisualTreeHelper.GetDpi(visual).DpiScaleX;

    // Physical pixels per point where the window really is (for positions on the screen).
    private static double ScreenScale(Visual visual) => PresentationSource.FromVisual(visual)?.CompositionTarget?.TransformToDevice.M11 ?? 1;

    // Before drawing at another scale than the screen's: the window (or a menu's popup, or a drawn scene) lays itself out
    // for that scale, so its lines and text fall on whole pixels of the picture instead of being stretched.
    private void LayOutFor(Visual visual)
    {
        if (shotScale <= 0) return;
        DependencyObject root = visual;
        for (DependencyObject parent; (parent = VisualTreeHelper.GetParent(root)) != null;) root = parent;
        if (root is Visual top && VisualTreeHelper.GetDpi(top).DpiScaleX != shotScale)
        {
            VisualTreeHelper.SetRootDpi(top, new DpiScale(shotScale, shotScale));
            // Only some elements lay themselves out and draw again on a new DPI: every one does, so all edges are rounded
            // anew (a border drawn for the old rounding lets the shadow under it show through as a thin line).
            foreach (UIElement element in new[] { top }.Concat(Descendants(top)).OfType<UIElement>())
            {
                element.InvalidateMeasure();
                element.InvalidateArrange();
                element.InvalidateVisual();
            }
        }
        (root as UIElement)?.UpdateLayout();
    }

    private async Task SavePreview(Visual visual, string name)
    {
        foreach (bool dark in new[] { false, true })
        {
            Theme.Apply(app, dark);
            await Task.Delay(400);
            LayOutFor(visual);
            SavePng(Snapshot((FrameworkElement)visual, ScaleOf(visual)), name, dark);
        }
        Theme.Apply(app);
    }

    // The landing page's animated demo (minimalistic-radio.github.io), made only of real pictures: the stations page
    // playing → History → a song's ⋯ menu with "Search on Spotify" under the pointer → Statistics → ← back. Each frame
    // is a shot-demo-*.png like the other README pictures (light and dark, the same size and shadow margin), and
    // MinimalisticRadio-shot-demo-hotspots.json says where the pointer clicks in each: the centre of the element, in
    // that picture's own pixels, measured on the element itself.
    private async Task TakeDemoShots()
    {
        var frames = new List<string>();
        double scale = 1;
        Point Centre(FrameworkElement element, Point offset = default)
        {
            Point centre = element.TranslatePoint(new Point(element.ActualWidth / 2, element.ActualHeight / 2), element is MenuItem ? (UIElement)ItemsControl.ItemsControlFromItemContainer(element) : playerPanel);
            return new Point(Math.Round((centre.X + offset.X) * scale), Math.Round((centre.Y + offset.Y) * scale));
        }
        string Spot(string name, Point at) => string.Format(CultureInfo.InvariantCulture, "\"{0}\": [{1}, {2}]", name, at.X, at.Y);
        void Frame(string name, params string[] spots) => frames.Add(string.Format(CultureInfo.InvariantCulture,
            "    \"{0}\": {{ \"file\": \"MinimalisticRadio-shot-demo-{0}-light.png\", \"width\": {1}, \"height\": {2}, {3} }}", name,
            Math.Ceiling(playerPanel.ActualWidth * scale), Math.Ceiling(playerPanel.ActualHeight * scale), string.Join(", ", spots)));
        Button Find(Func<Button, bool> match)
        {
            playerPanel.UpdateLayout();
            return Descendants(playerPanel).OfType<Button>().First(button => button.IsVisible && match(button));
        }
        bool Says(Button button, string text) => Descendants(button).OfType<TextBlock>().Any(block => block.Text == text);
        void Click(Button button) => button.RaiseEvent(new RoutedEventArgs(ButtonBase.ClickEvent));

        FillSampleStatistics();   // a year of listening, in memory only, so the Statistics frame has something to show
        OpenPlayer();
        await Task.Delay(3000);   // logos and the cover arrive over the network
        LayOutFor(playerPanel);
        scale = ScaleOf(playerPanel);   // the pictures' pixels per point (2 for --screenshot)

        // The stations page, playing; the pointer goes to [History].
        Button history = Find(button => Says(button, L("History")));
        await SavePreview(playerPanel, "shot-demo-stations");
        Frame("stations", Spot("history", Centre(history)));

        // Song history; the pointer goes to the first song's ⋯, and later to [Statistics].
        Click(history);
        await Task.Delay(2000);
        Button more = Find(button => button.ToolTip as string == L("More"));
        Button statistics = Find(button => Says(button, L("Statistics")));
        await SavePreview(playerPanel, "shot-demo-history");
        Frame("history", Spot("more", Centre(more)), Spot("statistics", Centre(statistics)));

        // Its menu open, "Search on Spotify" highlighted as under the pointer; the menu has to be inside the picture.
        var menu = (ContextMenu)more.Tag;
        Click(more);
        await Task.Delay(500);
        var spotify = menu.Items.OfType<MenuItem>().First(item => item.Header as string == L("Search on Spotify"));
        spotify.Focus();
        if (!spotify.IsHighlighted)
            typeof(MenuItem).GetProperty("IsHighlighted").SetValue(spotify, true);   // as the pointer would
        await Task.Delay(300);
        LayOutFor(menu);
        Point origin = playerPanel.PointToScreen(new Point()), at = menu.PointToScreen(new Point());
        double screen = ScreenScale(playerPanel);   // the menu's place, from screen pixels to points
        var offset = new Point((at.X - origin.X) / screen, (at.Y - origin.Y) / screen);
        if (offset.X < 0 || offset.Y < 0 || offset.X + menu.ActualWidth > playerPanel.ActualWidth || offset.Y + menu.ActualHeight > playerPanel.ActualHeight)
            throw new InvalidOperationException("Menu utworu wychodzi poza obrazek demo.");
        await SaveWithMenu(playerPanel, menu, "shot-demo-history-menu");
        Frame("history-menu", Spot("spotify", Centre(spotify, offset)));
        menu.IsOpen = false;
        await Task.Delay(300);

        // Statistics (this month); the pointer goes to ←, which leads back to Song history and from there to the stations.
        Click(statistics);
        await Task.Delay(2000);
        Button back = Find(button => button.ToolTip as string == L("Back"));
        await SavePreview(playerPanel, "shot-demo-statistics");
        Frame("statistics", Spot("back", Centre(back)));
        playerPanel.Close();

        File.WriteAllText(System.IO.Path.Combine(System.IO.Path.GetTempPath(), "MinimalisticRadio-shot-demo-hotspots.json"),
            "{\n  \"scale\": " + scale.ToString(CultureInfo.InvariantCulture) + ",\n  \"frames\": {\n" + string.Join(",\n", frames) + "\n  }\n}\n");
    }

    // The panel with one of its menus open over it (a menu is a window of its own, so it is drawn on where it is).
    private async Task SaveWithMenu(Window window, ContextMenu menu, string name)
    {
        foreach (bool dark in new[] { false, true })
        {
            Theme.Apply(app, dark);
            await Task.Delay(400);
            LayOutFor(window);
            LayOutFor(menu);
            double scale = ScaleOf(window), screen = ScreenScale(window);
            Point origin = window.PointToScreen(new Point()), at = menu.PointToScreen(new Point());
            double x = (at.X - origin.X) / screen, y = (at.Y - origin.Y) / screen;
            double width = Math.Max(window.ActualWidth, x + menu.ActualWidth), height = Math.Max(window.ActualHeight, y + menu.ActualHeight);
            var drawing = new DrawingVisual();
            using (DrawingContext context = drawing.RenderOpen())
            {
                context.DrawImage(Snapshot(window, scale), new Rect(0, 0, window.ActualWidth, window.ActualHeight));
                context.DrawImage(Snapshot(menu, scale), new Rect(x, y, menu.ActualWidth, menu.ActualHeight));
            }
            var picture = new RenderTargetBitmap((int)Math.Ceiling(width * scale), (int)Math.Ceiling(height * scale), 96 * scale, 96 * scale, PixelFormats.Pbgra32);
            picture.Render(drawing);
            SavePng(picture, name, dark);
        }
        Theme.Apply(app);
    }

    private async Task SaveTrayShot(FrameworkElement opened, string name)
    {
        foreach (bool dark in new[] { false, true })
        {
            Theme.Apply(app, dark);
            await Task.Delay(400);
            LayOutFor(opened);
            double scale = ScaleOf(opened);
            FrameworkElement scene = TrayScene(Snapshot(opened, scale), scale, dark);
            LayOutFor(scene);
            SavePng(Snapshot(scene, scale), name, dark);
        }
        Theme.Apply(app);
    }

    private static BitmapSource Snapshot(FrameworkElement element, double scale)
    {
        var bitmap = new RenderTargetBitmap((int)Math.Ceiling(element.ActualWidth * scale),
            (int)Math.Ceiling(element.ActualHeight * scale), 96 * scale, 96 * scale, PixelFormats.Pbgra32);
        bitmap.Render(element);
        return bitmap;
    }

    private static void SavePng(BitmapSource image, string name, bool dark)
    {
        var encoder = new PngBitmapEncoder();
        encoder.Frames.Add(BitmapFrame.Create(image));
        using (FileStream file = File.Create(System.IO.Path.Combine(System.IO.Path.GetTempPath(),
            "MinimalisticRadio-" + name + (dark ? "-dark" : "-light") + ".png")))
            encoder.Save(file);
    }

    private static FrameworkElement TrayScene(BitmapSource opened, double scale, bool dark)
    {
        double Snap(double value) => Math.Round(value * scale) / scale;   // whole pixels keep the real UI sharp
        double openedWidth = opened.PixelWidth / scale, openedHeight = opened.PixelHeight / scale;
        // The menu opens to the left of the pointer, just above the taskbar.
        double menuWidth = openedWidth - MenuShadow, menuHeight = openedHeight - MenuShadow;
        double width = Snap(SceneWidth), height = Snap(DesktopAboveMenu + menuHeight + MenuGap + TaskbarHeight);
        double left = width - TrayIconFromRight - menuWidth, top = DesktopAboveMenu;

        Brush Solid(long argb) => new SolidColorBrush(Color.FromArgb((byte)(argb >> 24), (byte)(argb >> 16), (byte)(argb >> 8), (byte)argb));
        Brush text = Solid(dark ? 0xFFFFFFFF : 0xFF1A1A1A);
        var scene = new Canvas
        {
            Width = width, Height = height,
            Background = new LinearGradientBrush(
                ((SolidColorBrush)Solid(dark ? 0xFF0E1A31 : 0xFFBFD5F2)).Color,
                ((SolidColorBrush)Solid(dark ? 0xFF261D3D : 0xFFEDE3F5)).Color, 45),
            Clip = new RectangleGeometry(new Rect(0, 0, width, height), 8, 8)
        };
        var bloom = new RadialGradientBrush(((SolidColorBrush)Solid(dark ? 0x664A6FD0 : 0xAAFFFFFF)).Color,
            ((SolidColorBrush)Solid(dark ? 0x004A6FD0 : 0x00FFFFFF)).Color)
        { Center = new Point(0.25, 0.3), GradientOrigin = new Point(0.25, 0.3), RadiusX = 0.8, RadiusY = 0.6 };
        scene.Children.Add(new Rectangle { Width = width, Height = height, Fill = bloom });

        TextBlock Glyph(string glyph, double size) => new TextBlock
        {
            Text = glyph, FontSize = size, Foreground = text, FontFamily = new FontFamily("Segoe Fluent Icons, Segoe MDL2 Assets"),
            HorizontalAlignment = HorizontalAlignment.Center, VerticalAlignment = VerticalAlignment.Center, Margin = new Thickness(4, 0, 4, 0)
        };
        Border Slot(double slotWidth, UIElement child, Brush fill = null) => new Border
        {
            Width = slotWidth, Height = 40, CornerRadius = new CornerRadius(4), Background = fill ?? Brushes.Transparent, Child = child
        };

        var icon = new Image { Source = Theme.AppImage((int)Math.Round(16 * scale)), Width = 16, Height = 16 };
        RenderOptions.SetBitmapScalingMode(icon, BitmapScalingMode.HighQuality);
        var quick = new StackPanel { Orientation = Orientation.Horizontal, HorizontalAlignment = HorizontalAlignment.Center };
        foreach (string glyph in new[] { "", "", "" })   // Wi-Fi, volume, battery
            quick.Children.Add(Glyph(glyph, 15));
        var culture = CultureInfo.GetCultureInfo("en-US");
        var clock = new StackPanel { HorizontalAlignment = HorizontalAlignment.Right, VerticalAlignment = VerticalAlignment.Center, Margin = new Thickness(0, 0, 8, 0) };
        foreach (string line in new[] { DateTime.Now.ToString("h:mm tt", culture), DateTime.Now.ToString("M/d/yyyy", culture) })
            clock.Children.Add(new TextBlock { Text = line, FontSize = 12, Foreground = text, HorizontalAlignment = HorizontalAlignment.Right });

        var tray = new StackPanel { Orientation = Orientation.Horizontal, HorizontalAlignment = HorizontalAlignment.Right, VerticalAlignment = VerticalAlignment.Center };
        tray.Children.Add(Slot(TrayButtonWidth, Glyph("", 12)));                                    // hidden icons
        tray.Children.Add(Slot(TrayButtonWidth, icon, Solid(dark ? 0x15FFFFFF : 0x0F000000)));         // ours, under the pointer
        tray.Children.Add(Slot(QuickSettingsWidth, quick));
        tray.Children.Add(Slot(ClockWidth, clock));
        tray.Children.Add(new Border { Width = ShowDesktopWidth });
        var taskbar = new Border
        {
            Width = width, Height = TaskbarHeight, Child = tray,
            Background = Solid(dark ? 0xF01C1C1C : 0xF0F3F3F3),
            BorderBrush = Solid(dark ? 0x26FFFFFF : 0x1A000000), BorderThickness = new Thickness(0, 1, 0, 0)
        };
        Canvas.SetTop(taskbar, height - TaskbarHeight);
        scene.Children.Add(taskbar);

        var picture = new Image { Source = opened, Width = openedWidth, Height = openedHeight, Stretch = Stretch.Fill };
        RenderOptions.SetBitmapScalingMode(picture, BitmapScalingMode.NearestNeighbor);
        Canvas.SetLeft(picture, Snap(left));
        Canvas.SetTop(picture, Snap(top));
        scene.Children.Add(picture);

        // The mouse pointer on our icon.
        var pointer = new Path
        {
            Data = Geometry.Parse("M0,0 L0,17 L4.2,13.2 L6.9,19.4 L9.4,18.3 L6.8,12.2 L12.2,12.2 Z"),
            Fill = Brushes.White, Stroke = Brushes.Black, StrokeThickness = 1, StrokeLineJoin = PenLineJoin.Round,
            Effect = new DropShadowEffect { BlurRadius = 4, ShadowDepth = 1, Opacity = 0.35, Direction = 300 }
        };
        Canvas.SetLeft(pointer, Snap(width - TrayIconFromRight + 5));
        Canvas.SetTop(pointer, Snap(height - TaskbarHeight / 2 + 5));
        scene.Children.Add(pointer);

        scene.Measure(new Size(width, height));
        scene.Arrange(new Rect(0, 0, width, height));
        scene.UpdateLayout();
        return scene;
    }
}
#endif
