using System;
using System.Collections.Generic;
using System.IO;
using System.Windows;
using System.Windows.Media;
using System.Windows.Media.Imaging;

// Draws the Minimalistic Radio icon (a black disc with four level bars) at any size and writes
// a multi-size .ico (PNG frames) plus PNGs. Geometry on a 32×32 grid, the same as docs/icon.svg.
static class Program
{
    // Bars as (x, top, height) with their width. On the 32 grid the design is scaled; the small sizes
    // are fitted by hand to whole pixels so the bars stay sharp and apart.
    static (double width, (double x, double y, double h)[] bars) Layout(int size)
    {
        switch (size)
        {
            case 16: return (1, new[] { (3.0, 6.0, 4.0), (6, 4, 8), (9, 3, 10), (12, 5, 6) });
            case 20: return (2, new[] { (3.0, 7.0, 6.0), (7, 5, 10), (11, 4, 12), (15, 6, 8) });
            case 24: return (2, new[] { (5.0, 9.0, 6.0), (9, 6, 12), (13, 5, 14), (17, 7, 10) });
            case 40: return (4, new[] { (9.0, 15.0, 10.0), (15, 10, 20), (21, 8, 24), (27, 13, 14) });
            case 48: return (4, new[] { (10.0, 18.0, 12.0), (18, 12, 24), (26, 9, 30), (34, 15, 18) });
        }
        double k = size / 32.0;
        return (3 * k, new[] { (7 * k, 12 * k, 8 * k), (12 * k, 8 * k, 16 * k), (17 * k, 6 * k, 20 * k), (22 * k, 10 * k, 12 * k) });
    }

    static byte[] Png(int size)
    {
        var visual = new DrawingVisual();
        using (DrawingContext dc = visual.RenderOpen())
        {
            dc.DrawEllipse(Brushes.Black, null, new Point(size / 2.0, size / 2.0), size / 2.0 - 0.5 * size / 32.0, size / 2.0 - 0.5 * size / 32.0);
            var bar = new SolidColorBrush(Color.FromRgb(0xC8, 0xC8, 0xC8));
            var (width, bars) = Layout(size);
            foreach (var (x, y, h) in bars)
                dc.DrawRoundedRectangle(bar, null, new Rect(x, y, width, h), width / 2, width / 2);
        }
        var bitmap = new RenderTargetBitmap(size, size, 96, 96, PixelFormats.Pbgra32);
        bitmap.Render(visual);
        var encoder = new PngBitmapEncoder();
        encoder.Frames.Add(BitmapFrame.Create(bitmap));
        using (var stream = new MemoryStream()) { encoder.Save(stream); return stream.ToArray(); }
    }

    [STAThread]
    static void Main(string[] args)
    {
        string folder = args[0];
        int[] sizes = { 16, 20, 24, 32, 40, 48, 64, 256 };
        var frames = new List<byte[]>();
        foreach (int size in sizes) frames.Add(Png(size));
        using (var ico = new BinaryWriter(File.Create(Path.Combine(folder, "radio.ico"))))
        {
            ico.Write((ushort)0); ico.Write((ushort)1); ico.Write((ushort)sizes.Length);
            int offset = 6 + 16 * sizes.Length;
            for (int i = 0; i < sizes.Length; i++)
            {
                ico.Write((byte)(sizes[i] >= 256 ? 0 : sizes[i])); ico.Write((byte)(sizes[i] >= 256 ? 0 : sizes[i]));
                ico.Write((byte)0); ico.Write((byte)0); ico.Write((ushort)1); ico.Write((ushort)32);
                ico.Write(frames[i].Length); ico.Write(offset);
                offset += frames[i].Length;
            }
            foreach (byte[] frame in frames) ico.Write(frame);
        }
        File.WriteAllBytes(Path.Combine(folder, "icon-256.png"), frames[sizes.Length - 1]);
        foreach (int size in new[] { 16, 24, 32 }) File.WriteAllBytes(Path.Combine(folder, "icon-" + size + ".png"), frames[Array.IndexOf(sizes, size)]);
        Console.WriteLine("radio.ico: " + new FileInfo(Path.Combine(folder, "radio.ico")).Length + " B, " + sizes.Length + " rozmiarow");
    }
}


