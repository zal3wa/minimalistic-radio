using System;
using System.Runtime.InteropServices;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Interop;
using System.Windows.Media;
using System.Windows.Media.Animation;
using System.Windows.Media.Effects;
using System.Windows.Threading;
using static Lang;

// A small card like the Windows 11 media flyout, shown for a few seconds when the station changes from
// outside the panel (media keys, Win+A, the tray menu, the Windhawk taskbar player). Windows has no API
// that lets an app show its own flyout, so this stands in for it. It never takes focus or clicks.
internal sealed partial class Radio
{
    private Window osd;
    private Image osdCover;
    private FrameworkElement osdFallback;
    private TextBlock osdTitle, osdText;
    private string osdPicture, osdCopied;
    private DateTime osdUntil, osdShownAt;
    private bool osdSawPlaying;
    private bool showStationPopup = true;
    private readonly DispatcherTimer osdTimer = new DispatcherTimer { Interval = TimeSpan.FromMilliseconds(200) };

    [DllImport("user32.dll")]
    private static extern int GetWindowLong(IntPtr window, int index);

    [DllImport("user32.dll")]
    private static extern int SetWindowLong(IntPtr window, int index, int value);

    private void ShowStationPopup()
    {
        if (!showStationPopup || playerPanel != null || station < 0) return;
        ShowOsd(null);
    }

    // The same card for "the song title was copied": the title on the first line, the confirmation on the second.
    // It ignores the "Show station changes" setting, because it answers the user's own click.
    private void ShowCopiedCard(string copied)
    {
        if (station < 0) return;
        ShowOsd(copied);
    }

    private void ShowOsd(string copied)
    {
        osdCopied = copied;
        Theme.Apply(app);
        if (osd == null) BuildOsd();
        osdShownAt = DateTime.Now;
        osdUntil = osdShownAt.AddSeconds(3);
        osdSawPlaying = copied != null;   // nothing to wait for: it stays its usual 3 s
        RefreshOsd();
        if (!osd.IsVisible)
        {
            osd.Opacity = 0;
            osd.Show();
        }
        // Also cancels a fade-out in progress when stations are switched quickly one after another.
        osd.BeginAnimation(UIElement.OpacityProperty, new DoubleAnimation(1, TimeSpan.FromMilliseconds(150)));
        Post(PositionOsd);
        osdTimer.Start();
    }

    private void BuildOsd()
    {
        osd = new Window
        {
            WindowStyle = WindowStyle.None, AllowsTransparency = true, Background = Brushes.Transparent,
            ShowInTaskbar = false, Topmost = true, ShowActivated = false, Focusable = false, ResizeMode = ResizeMode.NoResize,
            SizeToContent = SizeToContent.WidthAndHeight, WindowStartupLocation = WindowStartupLocation.Manual,
            Left = -32000, Top = -32000, FontSize = 14, UseLayoutRounding = true
        };
        osd.SetResourceReference(Control.ForegroundProperty, "Fg");
        TextOptions.SetTextFormattingMode(osd, TextFormattingMode.Display);
        osd.SourceInitialized += (_, _) =>
        {
            // No activation, clicks pass through, not in Alt+Tab.
            IntPtr handle = new WindowInteropHelper(osd).Handle;
            SetWindowLong(handle, -20, GetWindowLong(handle, -20) | 0x08000000 | 0x20 | 0x80);
        };
        osd.SizeChanged += (_, _) => Post(PositionOsd);
        osdTimer.Tick += (_, _) => OsdTick();

        osdCover = new Image { Width = 44, Height = 44, Stretch = Stretch.UniformToFill };
        osdFallback = Theme.Glyph(Theme.RadioIcon, 26);
        var picture = new Grid { Width = 44, Height = 44, ClipToBounds = true, Margin = new Thickness(0, 0, 12, 0) };
        picture.Children.Add(osdFallback);
        picture.Children.Add(osdCover);
        osdTitle = new TextBlock { FontSize = 15, FontWeight = FontWeights.SemiBold, TextTrimming = TextTrimming.CharacterEllipsis };
        osdText = Note("");
        osdText.FontSize = 13;
        osdText.TextWrapping = TextWrapping.NoWrap;
        osdText.TextTrimming = TextTrimming.CharacterEllipsis;
        var text = Spaced(Orientation.Vertical, 2, osdTitle, osdText);
        text.VerticalAlignment = VerticalAlignment.Center;
        var card = new Border
        {
            CornerRadius = new CornerRadius(8), BorderThickness = new Thickness(1), Padding = new Thickness(12, 10, 16, 10),
            MinWidth = 260, MaxWidth = 380, Child = Columns((picture, Auto), (text, Star))
        };
        card.SetResourceReference(Border.BackgroundProperty, "Bg");
        card.SetResourceReference(Border.BorderBrushProperty, "Line");
        var shadow = new Border
        {
            CornerRadius = new CornerRadius(8), Background = Brushes.Black,
            Effect = new DropShadowEffect { BlurRadius = 14, ShadowDepth = 2, Opacity = 0.3, Direction = 270 }
        };
        var root = new Grid { Margin = new Thickness(ShadowMargin) };
        root.Children.Add(shadow);
        root.Children.Add(card);
        osd.Content = root;
    }

    private void RefreshOsd()
    {
        osdTitle.Text = osdCopied ?? StationName;
        osdText.Text = osdCopied != null ? L("Copied to clipboard") : track ?? (session == null ? status : playing ? L("Now playing") : status);
        string picture = CoverUrl;
        if (picture == osdPicture) return;
        osdPicture = picture;
        osdCover.Source = null;
        osdFallback.Visibility = Visibility.Visible;
        LoadOsdPicture(picture);
    }

    private async void LoadOsdPicture(string address)
    {
        ImageSource source = await LoadImage(address);
        if (source == null || address != osdPicture) return;
        osdCover.Source = source;
        osdFallback.Visibility = Visibility.Hidden;
    }

    private void OsdTick()
    {
        if (osd == null || !osd.IsVisible) { osdTimer.Stop(); return; }
        RefreshOsd();
        // Once the sound starts, stay 2 s more (at most 6 s in all), so the card ends on what is playing.
        if (playing && !osdSawPlaying)
        {
            osdSawPlaying = true;
            DateTime later = DateTime.Now.AddSeconds(2), latest = osdShownAt.AddSeconds(6);
            if (later > osdUntil) osdUntil = later < latest ? later : latest;
        }
        if (DateTime.Now < osdUntil) return;
        osdTimer.Stop();
        var fade = new DoubleAnimation(0, TimeSpan.FromMilliseconds(300));
        fade.Completed += (_, _) => { if (DateTime.Now >= osdUntil) osd?.Hide(); };
        osd.BeginAnimation(UIElement.OpacityProperty, fade);
    }

    // Centred above the taskbar, where Windows 11 shows its volume and media flyout.
    private void PositionOsd()
    {
        if (osd == null || !osd.IsVisible) return;
        IntPtr handle = new WindowInteropHelper(osd).Handle;
        if (handle == IntPtr.Zero || !GetWindowRect(handle, out Rect32 bounds)) return;
        var (area, edge) = TrayCorner();
        double scale = VisualTreeHelper.GetDpi(osd).DpiScaleY;
        int width = bounds.Right - bounds.Left, height = bounds.Bottom - bounds.Top;
        int inset = (int)Math.Round((24 - ShadowMargin) * scale);
        int x = area.Left + (area.Width - width) / 2;
        int y = edge == 1 ? area.Top + inset : area.Bottom - height - inset;
        SetWindowPos(handle, IntPtr.Zero, x, y, 0, 0, 0x0001 | 0x0004 | 0x0010); // NOSIZE | NOZORDER | NOACTIVATE
    }
}
