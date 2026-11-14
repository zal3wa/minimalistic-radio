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

// The first README pictures show the app where it lives: the corner of a Windows 11 taskbar with the tray
// icon, and what a right click (the menu) or a left click (the panel) opens above it. The menu and the panel
// are the app's real ones; the desktop and the taskbar around them are drawn.
internal sealed partial class Radio
{
    private const double SceneHeight = 682, TaskbarHeight = 48;
    // The notification area from the right edge: show desktop strip, clock, network/volume/battery, our icon.
    private const double ShowDesktopWidth = 8, ClockWidth = 76, QuickSettingsWidth = 92, TrayButtonWidth = 32;
    private const double TrayIconFromRight = ShowDesktopWidth + ClockWidth + QuickSettingsWidth + TrayButtonWidth / 2;
    private const double MenuShadow = 6;   // the menu's template leaves room for its shadow on the right and bottom

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

    private async Task SaveTrayShot(FrameworkElement opened, string name, bool panel)
    {
        foreach (bool dark in new[] { false, true })
        {
            Theme.Apply(app, dark);
            await Task.Delay(400);
            double scale = VisualTreeHelper.GetDpi(opened).DpiScaleX;
            FrameworkElement scene = TrayScene(Snapshot(opened, scale), scale, panel, dark);
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

    private static FrameworkElement TrayScene(BitmapSource opened, double scale, bool panel, bool dark)
    {
        double Snap(double value) => Math.Round(value * scale) / scale;   // whole pixels keep the real UI sharp
        double openedWidth = opened.PixelWidth / scale, openedHeight = opened.PixelHeight / scale;
        double width, left, top;
        if (panel)
        {
            // The panel's card sits 12 px from the screen edge and the taskbar, inside a transparent shadow margin.
            double card = openedWidth - 2 * ShadowMargin;
            width = Snap(card + 24);
            left = 12 - ShadowMargin;
            top = SceneHeight - TaskbarHeight - 12 + ShadowMargin - openedHeight;
        }
        else
        {
            // The menu opens to the left of the pointer, just above the taskbar.
            double menu = openedWidth - MenuShadow;
            width = Snap(24 + menu + TrayIconFromRight);
            left = 24;
            top = SceneHeight - TaskbarHeight - 8 - (openedHeight - MenuShadow);
        }

        Brush Solid(long argb) => new SolidColorBrush(Color.FromArgb((byte)(argb >> 24), (byte)(argb >> 16), (byte)(argb >> 8), (byte)argb));
        Brush text = Solid(dark ? 0xFFFFFFFF : 0xFF1A1A1A);
        var scene = new Canvas
        {
            Width = width, Height = SceneHeight,
            Background = new LinearGradientBrush(
                ((SolidColorBrush)Solid(dark ? 0xFF0E1A31 : 0xFFBFD5F2)).Color,
                ((SolidColorBrush)Solid(dark ? 0xFF261D3D : 0xFFEDE3F5)).Color, 45),
            Clip = new RectangleGeometry(new Rect(0, 0, width, SceneHeight), 8, 8)
        };
        var bloom = new RadialGradientBrush(((SolidColorBrush)Solid(dark ? 0x664A6FD0 : 0xAAFFFFFF)).Color,
            ((SolidColorBrush)Solid(dark ? 0x004A6FD0 : 0x00FFFFFF)).Color)
        { Center = new Point(0.25, 0.3), GradientOrigin = new Point(0.25, 0.3), RadiusX = 0.8, RadiusY = 0.6 };
        scene.Children.Add(new Rectangle { Width = width, Height = SceneHeight, Fill = bloom });

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
        Canvas.SetTop(taskbar, SceneHeight - TaskbarHeight);
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
        Canvas.SetTop(pointer, Snap(SceneHeight - TaskbarHeight / 2 + 5));
        scene.Children.Add(pointer);

        scene.Measure(new Size(width, SceneHeight));
        scene.Arrange(new Rect(0, 0, width, SceneHeight));
        scene.UpdateLayout();
        return scene;
    }
}
