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

    internal const string PlayIcon = "M5 3 L19 12 L5 21 Z";
    internal const string StopIcon = "M6 6 H18 V18 H6 Z";
    internal const string RadioIcon = "M3 10 L3 6 A2 2 0 0 1 5 4 H19 A2 2 0 0 1 21 6 V18 A2 2 0 0 1 19 20 H5 A2 2 0 0 1 3 18 Z M3 10 H21 M7 15 H7.01 M11 15 H17";
    internal const string CheckIcon = "M20 6 L9 17 L4 12";
    internal const string VolumeIcon = "M11 5 L6 9 H3 V15 H6 L11 19 Z M15 9 A4 4 0 0 1 15 15 M18 6 A8 8 0 0 1 18 18";
    internal const string PlusIcon = "M12 5 V19 M5 12 H19";
    internal const string MinusIcon = "M5 12 H19";
    internal const string QuitIcon = "M10 17 L15 12 L10 7 M15 12 H3 M15 3 H19 A2 2 0 0 1 21 5 V19 A2 2 0 0 1 19 21 H15";
    internal const string MoreIcon = "M5 12 H5.1 M12 12 H12.1 M19 12 H19.1";
    internal const string MusicIcon = "M9 18V5l12-2v13 M9 18a3 2 0 1 1-6 0a3 2 0 1 1 6 0 M21 16a3 2 0 1 1-6 0a3 2 0 1 1 6 0";
    internal const string CopyIcon = "M8 8h12v12H8z M16 8V4H4v12h4";
    internal const string SettingsIcon = "M21 4H14 M10 4H3 M21 12H12 M8 12H3 M21 20H16 M12 20H3 M14 2V6 M8 10V14 M16 18V22";
    internal const string BackIcon = "M19 12 H5 M12 19 L5 12 L12 5";
    internal const string CloseIcon = "M18 6 L6 18 M6 6 L18 18";
    internal const string GlobeIcon = "M2 12 A10 10 0 1 0 22 12 A10 10 0 1 0 2 12 Z M12 2 A14.5 14.5 0 0 0 12 22 A14.5 14.5 0 0 0 12 2 M2 12 H22";
    internal const string WaveIcon = "M2 10 V13 M6 6 V17 M10 3 V21 M14 8 V15 M18 5 V18 M22 10 V13";
    internal const string TaskbarIcon = "M3 5 A2 2 0 0 1 5 3 H19 A2 2 0 0 1 21 5 V19 A2 2 0 0 1 19 21 H5 A2 2 0 0 1 3 19 Z M3 15 H21 M15 18 H18";
    internal const string ExternalIcon = "M15 3 H21 V9 M10 14 L21 3 M18 13 V19 A2 2 0 0 1 16 21 H5 A2 2 0 0 1 3 19 V8 A2 2 0 0 1 5 6 H11";
    internal const string CheckSmallIcon = "M20 6 L9 17 L4 12";
    internal const string HistoryIcon = "M2 12 A10 10 0 1 0 22 12 A10 10 0 1 0 2 12 Z M12 6 V12 L16 14";
    internal const string MoonIcon = "M12 3 A6 6 0 0 0 21 12 A9 9 0 1 1 12 3 Z";
    internal const string UpdateIcon = "M21 12 A9 9 0 1 1 18.36 5.64 M21 3 V9 H15";
    internal const string DownloadIcon = "M21 15 V19 A2 2 0 0 1 19 21 H5 A2 2 0 0 1 3 19 V15 M7 10 L12 15 L17 10 M12 15 V3";
    internal const string PowerIcon = "M12 2 V12 M18.4 6.6 A9 9 0 1 1 5.63 6.64";
    internal const string ListIcon = "M8 6 H21 M8 12 H21 M8 18 H21 M3 6 H3.01 M3 12 H3.01 M3 18 H3.01";
}
