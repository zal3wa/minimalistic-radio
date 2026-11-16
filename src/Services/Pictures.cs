using System;
using System.Collections.Concurrent;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Net;
using System.Net.Http;
using System.Net.Sockets;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using System.Windows.Media;
using System.Windows.Media.Imaging;

// Pictures from outside (station logos, radio-browser favicons, share-link logos, song covers, ICY artwork) and the
// rules every one of them goes through: never fetched from this computer or the local network (first address and every
// redirect, at most 5), at most 1 MB, and at most 4096 pixels wide and tall, read from the header before decoding.
// A refused picture is like one that didn't load: the placeholder stays. Streams aren't affected.
internal static class Pictures
{
    internal const int LargestSide = 4096;
    private const int LargestFile = 1024 * 1024, MostRedirects = 5;
    private static readonly TimeSpan Deadline = TimeSpan.FromSeconds(5);
    // Redirects are followed by hand, so each one's address is checked before it is asked for.
    private static readonly HttpClient client = new HttpClient(new HttpClientHandler { AllowAutoRedirect = false }) { Timeout = Deadline };
    private static readonly string[] LocalSuffixes = { ".localhost", ".local", ".lan", ".home", ".internal", ".home.arpa" };

    // By the name alone: localhost and the home network's names, and every local address written as one.
    internal static bool IsLocalName(string host)
    {
        host = (host ?? "").Trim().TrimStart('[').TrimEnd(']').TrimEnd('.').ToLowerInvariant();
        if (host.Length == 0) return true;
        if (IPAddress.TryParse(host, out IPAddress address)) return IsLocalAddress(address);
        return host == "localhost" || LocalSuffixes.Any(suffix => host.EndsWith(suffix, StringComparison.Ordinal));
    }

    // Loopback, private, link-local, carrier-grade NAT, multicast, unspecified and reserved addresses: IPv4 0/8, 10/8,
    // 100.64/10, 127/8, 169.254/16, 172.16/12, 192.0.0/24, 192.168/16, 198.18/15, 224/4 and 240/4; IPv6 ::, ::1,
    // fc00::/7 and fe80::/10, and the IPv4 ones written as IPv6 (::ffff:a.b.c.d).
    internal static bool IsLocalAddress(IPAddress address)
    {
        if (address.IsIPv4MappedToIPv6) address = address.MapToIPv4();
        byte[] part = address.GetAddressBytes();
        if (address.AddressFamily == AddressFamily.InterNetwork)
            return part[0] == 0 || part[0] == 10 || part[0] == 127 || part[0] >= 224 || (part[0] == 100 && (part[1] & 0xC0) == 64) ||
                (part[0] == 169 && part[1] == 254) || (part[0] == 172 && (part[1] & 0xF0) == 16) || (part[0] == 192 && part[1] == 0 && part[2] == 0) ||
                (part[0] == 192 && part[1] == 168) || (part[0] == 198 && (part[1] & 0xFE) == 18);
        if (address.AddressFamily == AddressFamily.InterNetworkV6)
            return (part.Take(15).All(value => value == 0) && part[15] <= 1) || (part[0] & 0xFE) == 0xFC || (part[0] == 0xFE && (part[1] & 0xC0) == 0x80);
        return true;
    }

    // The name, then every address it resolves to: one local address is enough to refuse it. A name that doesn't resolve
    // in time is refused too.
    internal static async Task<bool> IsLocal(Uri uri, CancellationToken token)
    {
        string host = uri.DnsSafeHost;
        if (IsLocalName(host)) return true;
        if (IPAddress.TryParse(host.TrimStart('[').TrimEnd(']'), out _)) return false;
        Task<IPAddress[]> lookup = Dns.GetHostAddressesAsync(host);
        if (await Task.WhenAny(lookup, Task.Delay(Timeout.Infinite, token)).ConfigureAwait(false) != lookup)
        {
            _ = lookup.ContinueWith(late => late.Exception, TaskContinuationOptions.OnlyOnFaulted);
            return true;
        }
        IPAddress[] addresses = await lookup.ConfigureAwait(false);
        return addresses.Length == 0 || addresses.Any(IsLocalAddress);
    }

    // The picture's bytes, or null: refused (a local address, more than 5 redirects, not an image, over 1 MB) or failed.
    // At most 5 seconds in all.
    internal static Task<byte[]> Download(string address) => Download(address, IsLocal);

    internal static async Task<byte[]> Download(string address, Func<Uri, CancellationToken, Task<bool>> refused)
    {
        try
        {
            using (var timeout = new CancellationTokenSource(Deadline))
                for (int redirects = 0; ; redirects++)
                {
                    if (!Storage.IsWebUrl(address) || !Uri.TryCreate(address, UriKind.Absolute, out Uri uri) || await refused(uri, timeout.Token))
                        return null;
                    using (HttpResponseMessage response = await client.GetAsync(uri, HttpCompletionOption.ResponseHeadersRead, timeout.Token))
                    {
                        int code = (int)response.StatusCode;
                        if (code >= 300 && code < 400)
                        {
                            Uri next = response.Headers.Location;
                            if (next == null || redirects >= MostRedirects) return null;
                            address = (next.IsAbsoluteUri ? next : new Uri(uri, next)).AbsoluteUri;
                            continue;
                        }
                        if (!response.IsSuccessStatusCode || response.Content.Headers.ContentType?.MediaType?.StartsWith("image/") != true)
                            return null;
                        var data = new MemoryStream();
                        using (Stream input = await response.Content.ReadAsStreamAsync())
                        {
                            var buffer = new byte[8192];
                            int count;
                            while ((count = await input.ReadAsync(buffer, 0, buffer.Length, timeout.Token)) > 0)
                            {
                                if (data.Length + count > LargestFile) return null;
                                data.Write(buffer, 0, count);
                            }
                        }
                        return data.ToArray();
                    }
                }
        }
        catch (Exception error)
        {
            Debug.WriteLine(error);
            return null;
        }
    }

    // The declared width and height of every frame (an icon can carry several), from the header through WIC, without
    // decoding the pixels: at most 4096 each. A picture whose size can't be read is refused. Call it on a thread with a
    // Dispatcher (the UI's).
    internal static bool Fits(byte[] data)
    {
        if (data == null || data.Length == 0) return false;
        try
        {
            using (var stream = new MemoryStream(data, false))
            {
                BitmapDecoder decoder = BitmapDecoder.Create(stream, BitmapCreateOptions.DelayCreation | BitmapCreateOptions.IgnoreColorProfile,
                    BitmapCacheOption.None);
                return decoder.Frames.Count > 0 && decoder.Frames.All(frame => frame.PixelWidth <= LargestSide && frame.PixelHeight <= LargestSide);
            }
        }
        catch (Exception error)
        {
            Debug.WriteLine(error);
            return false;
        }
    }

    // The picture, width pixels wide, once it Fits; null otherwise.
    internal static BitmapImage Decode(byte[] data, int width)
    {
        if (!Fits(data)) return null;
        try
        {
            var image = new BitmapImage();
            image.BeginInit();
            image.CacheOption = BitmapCacheOption.OnLoad;
            image.DecodePixelWidth = width;
            image.StreamSource = new MemoryStream(data, false);
            image.EndInit();
            image.Freeze();
            return image;
        }
        catch (Exception error)
        {
            Debug.WriteLine(error);
            return null;
        }
    }

#if SELFTEST
    // Self-test (--test-menu): which hosts count as local, the size rule, and that a local address is never asked for,
    // not even after a redirect.
    internal static async Task Verify()
    {
        void Check(bool ok, string what)
        {
            if (!ok) throw new InvalidOperationException("Obrazki: " + what);
        }
        foreach (string host in new[] { "localhost", "LocalHost.", "radio.localhost", "printer.local", "router.lan", "nas.home", "db.internal", "box.home.arpa",
            "127.0.0.1", "127.1.2.3", "0.0.0.0", "10.0.0.1", "10.255.255.255", "100.64.0.1", "100.127.255.255", "169.254.169.254", "172.16.0.1",
            "172.31.255.255", "192.0.0.1", "192.168.1.1", "198.18.0.1", "198.19.255.255", "224.0.0.1", "239.255.255.250", "240.0.0.1", "255.255.255.255",
            "::", "::1", "[::1]", "fe80::1", "febf::1", "fc00::1", "fd12:3456::1", "::ffff:192.168.1.1", "::ffff:127.0.0.1", "[::ffff:10.0.0.1]", "" })
            Check(IsLocalName(host), "adres lokalny przepuszczony: " + host);
        foreach (string host in new[] { "example.com", "radio.example", "local.example.com", "lan.example.com", "mylocal", "home", "8.8.8.8", "1.1.1.1",
            "11.0.0.1", "100.63.255.255", "100.128.0.1", "172.15.255.255", "172.32.0.1", "192.0.1.1", "192.169.0.1", "198.17.255.255", "198.20.0.1",
            "223.255.255.255", "2606:4700:4700::1111", "[2a00:1450:4001:80b::200e]", "fbff::1", "fe7f::1", "::ffff:8.8.8.8" })
            Check(!IsLocalName(host), "adres publiczny odrzucony: " + host);
        Check(await IsLocal(new Uri("http://[::1]:8000/logo.png"), CancellationToken.None) &&
            await IsLocal(new Uri("http://" + Environment.MachineName + "/logo.png"), CancellationToken.None) &&
            !await IsLocal(new Uri("https://8.8.8.8/logo.png"), CancellationToken.None), "adres po rozwiązaniu nazwy.");

        // The size: read from the header, at most 4096 pixels each way, a picture that can't be read is refused.
        byte[] Png(int width, int height)
        {
            var encoder = new PngBitmapEncoder();
            encoder.Frames.Add(BitmapFrame.Create(BitmapSource.Create(width, height, 96, 96, PixelFormats.Gray8, null, new byte[width * height], width)));
            using (var stream = new MemoryStream())
            {
                encoder.Save(stream);
                return stream.ToArray();
            }
        }
        // Only a PNG's header declaring a size, and an empty IDAT: there are no pixels at all, so a check that read them
        // would fail even for 10×10.
        byte[] Header(int width, int height)
        {
            var png = new MemoryStream();
            png.Write(new byte[] { 0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A }, 0, 8);
            void Chunk(string type, byte[] data)
            {
                byte[] body = Encoding.ASCII.GetBytes(type).Concat(data).ToArray();
                uint crc = 0xFFFFFFFF;
                foreach (byte part in body)
                {
                    crc ^= part;
                    for (int bit = 0; bit < 8; bit++) crc = (crc >> 1) ^ (0xEDB88320 & (uint)-(int)(crc & 1));
                }
                byte[] Big(uint value) => new[] { (byte)(value >> 24), (byte)(value >> 16), (byte)(value >> 8), (byte)value };
                png.Write(Big((uint)data.Length), 0, 4);
                png.Write(body, 0, body.Length);
                png.Write(Big(~crc), 0, 4);
            }
            Chunk("IHDR", new[] { (byte)(width >> 24), (byte)(width >> 16), (byte)(width >> 8), (byte)width,
                (byte)(height >> 24), (byte)(height >> 16), (byte)(height >> 8), (byte)height, (byte)8, (byte)0, (byte)0, (byte)0, (byte)0 });
            Chunk("IDAT", new byte[] { 0x78, 0x9C, 0x03, 0x00, 0x00, 0x00, 0x00, 0x01 });   // zlib of nothing
            Chunk("IEND", new byte[0]);
            return png.ToArray();
        }
        Check(Fits(Header(10, 10)) && !Fits(Header(5000, 10)) && !Fits(Header(10, 5000)), "rozmiar z samego nagłówka PNG (5000×10).");
        Check(Decode(Png(16, 16), 120) != null && Fits(Png(LargestSide, 1)) && Fits(Png(1, LargestSide)), "obrazek do 4096 pikseli odrzucony.");
        Check(!Fits(Png(LargestSide + 1, 1)) && !Fits(Png(1, LargestSide + 1)) && Decode(Png(5000, 10), 120) == null, "obrazek ponad 4096 pikseli przyjęty.");
        Check(!Fits(new byte[0]) && !Fits(Encoding.ASCII.GetBytes("<html>not a picture</html>")) && Decode(null, 120) == null, "nie obrazek przyjęty.");

        // Nothing is asked of this computer: test servers on loopback ports. In the test, 0 and 2 count as public; 1 is
        // local as it really is, and must never hear from the radio, not even through a redirect.
        var servers = Enumerable.Range(0, 3).Select(_ => new TcpListener(IPAddress.Loopback, 0)).ToArray();
        var requests = new ConcurrentQueue<string>();
        foreach (TcpListener server in servers) server.Start();
        try
        {
            int Port(int server) => ((IPEndPoint)servers[server].LocalEndpoint).Port;
            string At(int server, string path) => "http://127.0.0.1:" + Port(server) + path;
            byte[] Answer(string status, string headers, byte[] body) => Encoding.ASCII.GetBytes("HTTP/1.1 " + status + "\r\n" + headers +
                "Content-Length: " + body.Length + "\r\nConnection: close\r\n\r\n").Concat(body).ToArray();
            byte[] Redirect(string to) => Answer("302 Found", "Location: " + to + "\r\n", new byte[0]);
            byte[] logo = Png(16, 16);
            for (int server = 0; server < servers.Length; server++)
            {
                int number = server;
                _ = Task.Run(() => Serve(servers[number], path =>
                {
                    requests.Enqueue(number + path);
                    if (path == "/to-local") return Redirect(At(1, "/logo.png"));
                    if (path == "/to-public") return Redirect(At(2, "/logo.png"));
                    if (path.StartsWith("/hop/")) return Redirect(At(0, "/hop/" + (int.Parse(path.Substring(5)) + 1)));
                    if (path == "/text") return Answer("200 OK", "Content-Type: text/plain\r\n", Encoding.ASCII.GetBytes("text"));
                    return Answer("200 OK", "Content-Type: image/png\r\n", logo);
                }));
            }
            Func<Uri, CancellationToken, Task<bool>> rule = (uri, token) =>
                uri.Port == Port(0) || uri.Port == Port(2) ? Task.FromResult(false) : IsLocal(uri, token);
            Check(await Download(At(1, "/logo.png")) == null && await Download("http://localhost:" + Port(1) + "/logo.png") == null,
                "obrazek pobrany z tego komputera.");
            Check(await Download(At(0, "/to-local"), rule) == null, "przekierowanie do sieci lokalnej przepuszczone.");
            byte[] fetched = await Download(At(0, "/to-public"), rule);
            Check(fetched != null && fetched.SequenceEqual(logo) && Decode(fetched, 120) != null, "przekierowanie do dozwolonego adresu nie działa.");
            Check(await Download(At(0, "/hop/0"), rule) == null && requests.Count(path => path.StartsWith("0/hop/")) == 1 + MostRedirects,
                "więcej niż 5 przekierowań: " + requests.Count(path => path.StartsWith("0/hop/")));
            Check(await Download(At(2, "/text"), rule) == null, "nie obrazek pobrany jako obrazek.");
            Check(!requests.Any(path => path.StartsWith("1")), "serwer lokalny dostał zapytanie: " + string.Join(", ", requests));
        }
        finally
        {
            foreach (TcpListener server in servers) server.Stop();
        }
    }

    // A tiny HTTP server for the test: each request's path gets answer(path), then the connection closes.
    private static async Task Serve(TcpListener server, Func<string, byte[]> answer)
    {
        while (true)
        {
            TcpClient client;
            try { client = await server.AcceptTcpClientAsync().ConfigureAwait(false); }
            catch (Exception) { return; }   // stopped
            using (client)
            using (NetworkStream stream = client.GetStream())
            {
                var reader = new StreamReader(stream, Encoding.ASCII, false, 1024, true);
                string request = await reader.ReadLineAsync().ConfigureAwait(false);
                while (!string.IsNullOrEmpty(await reader.ReadLineAsync().ConfigureAwait(false))) { }
                byte[] response = answer(request?.Split(' ').ElementAtOrDefault(1) ?? "");
                await stream.WriteAsync(response, 0, response.Length).ConfigureAwait(false);
            }
        }
    }
#endif
}
