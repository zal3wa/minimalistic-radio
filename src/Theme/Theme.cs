using System;
using System.IO;
using System.Runtime.InteropServices;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Interop;
using System.Windows.Markup;
using System.Windows.Media;
using System.Windows.Media.Imaging;
using Microsoft.Win32;
using Path = System.Windows.Shapes.Path;

internal static class Theme
{
    internal static bool Dark { get; private set; }

    // The app icon is read from the exe's own Win32 resources (the .ico the exe shows in Explorer),
    // so it is stored in the file only once. 32512 is the resource ID the C# compiler gives it.
    private static readonly IntPtr AppIconId = (IntPtr)32512;

    [DllImport("kernel32.dll", CharSet = CharSet.Unicode)]
    private static extern IntPtr GetModuleHandle(string name);

    [DllImport("comctl32.dll")]
    private static extern int LoadIconMetric(IntPtr instance, IntPtr name, int metric, out IntPtr icon);

    [DllImport("user32.dll")]
    private static extern IntPtr LoadImage(IntPtr instance, IntPtr name, uint type, int width, int height, uint flags);

    [DllImport("user32.dll")]
    internal static extern bool DestroyIcon(IntPtr icon);

    // The small icon for next to the clock, in the size Windows wants at the current display scale.
    internal static IntPtr TrayIconHandle()
    {
        LoadIconMetric(GetModuleHandle(null), AppIconId, 0, out IntPtr handle); // LIM_SMALL
        return handle;
    }

    internal static BitmapSource AppImage(int size)
    {
        IntPtr handle = LoadImage(GetModuleHandle(null), AppIconId, 1, size, size, 0); // IMAGE_ICON
        if (handle == IntPtr.Zero) return null;
        try
        {
            BitmapSource image = Imaging.CreateBitmapSourceFromHIcon(handle, Int32Rect.Empty, BitmapSizeOptions.FromEmptyOptions());
            image.Freeze();
            return image;
        }
        finally { DestroyIcon(handle); }
    }

    internal static void Load(Application app)
    {
        using (Stream xaml = typeof(Theme).Assembly.GetManifestResourceStream("Theme.xaml"))
            app.Resources.MergedDictionaries.Add((ResourceDictionary)XamlReader.Load(xaml));
        Apply(app);
    }

    // Follows the Windows light/dark setting and accent colour; called whenever a menu or the panel opens.
    internal static void Apply(Application app, bool? dark = null)
    {
        Dark = dark ?? Equals(Registry.GetValue(
            @"HKEY_CURRENT_USER\Software\Microsoft\Windows\CurrentVersion\Themes\Personalize", "AppsUseLightTheme", 1), 0);
        Set(app, "Bg", Dark ? "#202020" : "#F9F9F9");
        Set(app, "Card", Dark ? "#2D2D2D" : "#FFFFFF");
        Set(app, "Line", Dark ? "#404040" : "#DADADA");
        Set(app, "Fg", Dark ? "#FFFFFF" : "#1A1A1A");
        Set(app, "Subtle", Dark ? "#B4B4B4" : "#5C5C5C");
        Set(app, "Selected", Dark ? "#2F2F2F" : "#EAEAEA");
        Set(app, "Success", Dark ? "#6CCB5F" : "#0F7B0F");
        Set(app, "SuccessFg", Dark ? "#1C1C1C" : "#FFFFFF");   // the arrow on the green update badge
        Set(app, "Danger", Dark ? "#FF99A4" : "#C42B1C");      // Windows 11's critical text: Quit
        Set(app, "MenuHover", "#09AAFF");
        Set(app, "MenuHoverFg", "#000000");
        Color accent = Accent(Dark);
        double light = (0.2126 * accent.R + 0.7152 * accent.G + 0.0722 * accent.B) / 255;
        app.Resources["Accent"] = Frozen(accent);
        app.Resources["AccentFg"] = Frozen(light > 0.55 ? Colors.Black : Colors.White);
    }

    private static Color Accent(bool dark)
    {
        try
        {
            var settings = new Windows.UI.ViewManagement.UISettings();
            Windows.UI.Color value = settings.GetColorValue(dark
                ? Windows.UI.ViewManagement.UIColorType.AccentLight2
                : Windows.UI.ViewManagement.UIColorType.AccentDark1);
            return Color.FromRgb(value.R, value.G, value.B);
        }
        catch (Exception) { return dark ? Color.FromRgb(0x4C, 0xC2, 0xFF) : Color.FromRgb(0x00, 0x5F, 0xB8); }
    }

    private static void Set(Application app, string key, string hex) =>
        app.Resources[key] = Frozen((Color)ColorConverter.ConvertFromString(hex));

    private static SolidColorBrush Frozen(Color color)
    {
        var brush = new SolidColorBrush(color);
        brush.Freeze();
        return brush;
    }

    // Lucide icon outline (24×24 path data), see Lucide_Icons_license.txt.
    internal static FrameworkElement Glyph(string data, double size = 18, string color = null)
    {
        var path = new Path
        {
            Width = 24, Height = 24, Data = Geometry.Parse(data), Stroke = Brushes.Gray, StrokeThickness = 2,
            StrokeStartLineCap = PenLineCap.Round, StrokeEndLineCap = PenLineCap.Round, StrokeLineJoin = PenLineJoin.Round
        };
        if (color != null) path.SetResourceReference(System.Windows.Shapes.Shape.StrokeProperty, color);
        return new Viewbox { Width = size, Height = size, Child = path };
    }

    // The same outline, filled: the play triangle and the stop square.
    internal static FrameworkElement Solid(string data, double size, string color)
    {
        var glyph = (Viewbox)Glyph(data, size, color);
        ((Path)glyph.Child).SetResourceReference(System.Windows.Shapes.Shape.FillProperty, color);
        return glyph;
    }

    // "Update ready": a green disc with an arrow down.
    internal static FrameworkElement UpdateBadge(double size)
    {
        var disc = new System.Windows.Shapes.Ellipse { Width = 20, Height = 20, Margin = new Thickness(2) };
        disc.SetResourceReference(System.Windows.Shapes.Shape.FillProperty, "Success");
        var arrow = new Path
        {
            Data = Geometry.Parse("M12 7 V16 M8 12.5 L12 16.5 L16 12.5"), StrokeThickness = 2,
            StrokeStartLineCap = PenLineCap.Round, StrokeEndLineCap = PenLineCap.Round, StrokeLineJoin = PenLineJoin.Round
        };
        arrow.SetResourceReference(System.Windows.Shapes.Shape.StrokeProperty, "SuccessFg");
        var badge = new Grid { Width = 24, Height = 24 };
        badge.Children.Add(disc);
        badge.Children.Add(arrow);
        return new Viewbox { Width = size, Height = size, Child = badge };
    }

    internal const string PlayIcon = "M5 3 L19 12 L5 21 Z";
    internal const string StopIcon = "M6 6 H18 V18 H6 Z";
    internal const string RadioIcon = "M3 10 L3 6 A2 2 0 0 1 5 4 H19 A2 2 0 0 1 21 6 V18 A2 2 0 0 1 19 20 H5 A2 2 0 0 1 3 18 Z M3 10 H21 M7 15 H7.01 M11 15 H17";
    internal const string CheckIcon = "M20 6 L9 17 L4 12";
    internal const string VolumeIcon = "M11 5 L6 9 H3 V15 H6 L11 19 Z M15 9 A4 4 0 0 1 15 15 M18 6 A8 8 0 0 1 18 18";
    // The panel's speaker button, like Windows 11: muted, then one to three waves. One speaker for all four, a little
    // left of VolumeIcon's so that the third wave fits.
    internal const string VolumeMutedIcon = "M10 5 L5 9 H2 V15 H5 L10 19 Z M15 9 L21 15 M21 9 L15 15";
    internal const string Volume1Icon = "M10 5 L5 9 H2 V15 H5 L10 19 Z M13.5 9.5 A3.5 3.5 0 0 1 13.5 14.5";
    internal const string Volume2Icon = Volume1Icon + " M16.5 7 A7 7 0 0 1 16.5 17";
    internal const string Volume3Icon = Volume2Icon + " M19.5 4.5 A10.5 10.5 0 0 1 19.5 19.5";
    internal const string PlusIcon = "M12 5 V19 M5 12 H19";
    internal const string MinusIcon = "M5 12 H19";
    internal const string QuitIcon = "M10 17 L15 12 L10 7 M15 12 H3 M15 3 H19 A2 2 0 0 1 21 5 V19 A2 2 0 0 1 19 21 H15";
    internal const string MoreIcon = "M5 12 H5.1 M12 12 H12.1 M19 12 H19.1";
    internal const string MusicIcon = "M9 18V5l12-2v13 M9 18a3 2 0 1 1-6 0a3 2 0 1 1 6 0 M21 16a3 2 0 1 1-6 0a3 2 0 1 1 6 0";
    internal const string CopyIcon = "M8 8h12v12H8z M16 8V4H4v12h4";
    internal const string SettingsIcon = "M21 4H14 M10 4H3 M21 12H12 M8 12H3 M21 20H16 M12 20H3 M14 2V6 M8 10V14 M16 18V22";
    internal const string BackIcon = "M19 12 H5 M12 19 L5 12 L12 5";
    internal const string ExternalIcon = "M15 3 H21 V9 M10 14 L21 3 M18 13 V19 A2 2 0 0 1 16 21 H5 A2 2 0 0 1 3 19 V8 A2 2 0 0 1 5 6 H11";
    internal const string UpdateReadyIcon ="M12 3 V15 M6 9 L12 15 L18 9 M5 20 H19";   // arrow down to a line, like Discord's
    internal const string HistoryIcon = "M3 12 A9 9 0 1 0 12 3 A9.75 9.75 0 0 0 5.26 5.74 L3 8 M3 3 V8 H8 M12 7 V12 L16 14";   // Lucide history
    internal const string MoonIcon = "M12 3 A6 6 0 0 0 21 12 A9 9 0 1 1 12 3 Z";
    internal const string DownloadIcon = "M21 15 V19 A2 2 0 0 1 19 21 H5 A2 2 0 0 1 3 19 V15 M7 10 L12 15 L17 10 M12 15 V3";
}
