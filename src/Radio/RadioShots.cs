#if SELFTEST
// Only in a build made with -p:SelfTest=true (docs/BUILDING.md): the README pictures and the --preview ones.
using System;
using System.Globalization;
using System.IO;
using System.Threading.Tasks;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
using System.Windows.Media.Effects;
using System.Windows.Media.Imaging;
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

    private async Task SavePreview(Visual visual, string name)
    {
        foreach (bool dark in new[] { false, true })
        {
            Theme.Apply(app, dark);
            await Task.Delay(400);
            SavePng(Snapshot((FrameworkElement)visual, VisualTreeHelper.GetDpi(visual).DpiScaleX), name, dark);
        }
        Theme.Apply(app);
    }

    // The panel with one of its menus open over it (a menu is a window of its own, so it is drawn on where it is).
    private async Task SaveWithMenu(Window window, ContextMenu menu, string name)
    {
        foreach (bool dark in new[] { false, true })
        {
            Theme.Apply(app, dark);
            await Task.Delay(400);
            double scale = VisualTreeHelper.GetDpi(window).DpiScaleX;
            Point origin = window.PointToScreen(new Point()), at = menu.PointToScreen(new Point());
            double x = (at.X - origin.X) / scale, y = (at.Y - origin.Y) / scale;
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
            double scale = VisualTreeHelper.GetDpi(opened).DpiScaleX;
            FrameworkElement scene = TrayScene(Snapshot(opened, scale), scale, dark);
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
