using System;
using System.IO;
using System.Net.Security;
using System.Net.Sockets;
using System.Security.Authentication;
using System.Text;
using System.Threading;
using static Lang;

// The station itself refuses (403, 404, a format that can't be played…): trying again won't help.
internal class StationRefusedException : InvalidOperationException
{
    internal StationRefusedException(string message) : base(message) { }
}

// Opens an internet radio stream over plain HTTP/1.0 (which also accepts the "ICY 200 OK"
// answer of old Shoutcast servers) and strips the in-band ICY metadata, reporting song titles.
internal sealed class RadioStream : Stream
{
    private static readonly Encoding StrictUtf8 = new UTF8Encoding(false, true);
    private readonly TcpClient client;
    private readonly Stream source;
    private readonly int metaInterval;
    private readonly Action<string> titleChanged;
    private int untilMeta;
    private string title;

    private RadioStream(TcpClient client, Stream source, int metaInterval, Action<string> titleChanged)
    {
        this.client = client;
        this.source = source;
        this.metaInterval = metaInterval;
        this.titleChanged = titleChanged;
        untilMeta = metaInterval;
    }

    internal static RadioStream Open(string url, Action<string> titleChanged, CancellationToken cancel)
    {
        var uri = new Uri(url);
        for (int redirects = 0; ; redirects++)
        {
            cancel.ThrowIfCancellationRequested();
            var client = new TcpClient { ReceiveTimeout = 10000, SendTimeout = 10000 };
            try
            {
                Stream network;
                string[] head;
                using (cancel.Register(client.Close))
                {
                    var connect = client.ConnectAsync(uri.DnsSafeHost, uri.Port);
                    if (!connect.Wait(TimeSpan.FromSeconds(10)))
                        throw new IOException("Przekroczono czas połączenia.");
                    network = client.GetStream();
                    if (uri.Scheme == Uri.UriSchemeHttps)
                    {
                        var tls = new SslStream(network, false);
                        tls.AuthenticateAsClient(uri.DnsSafeHost, null, SslProtocols.None, true);
                        network = tls;
                    }
                    byte[] request = Encoding.ASCII.GetBytes(
                        "GET " + uri.PathAndQuery + " HTTP/1.0\r\n" +
                        "Host: " + uri.Authority + "\r\n" +
                        "User-Agent: MinimalisticRadio/2.0\r\n" +
                        "Accept: */*\r\n" +
                        "Icy-MetaData: 1\r\n" +
                        "Connection: close\r\n\r\n");
                    network.Write(request, 0, request.Length);
                    head = ReadHead(network);
                }

                string[] status = head[0].Split(' ');
                int code = status.Length > 1 && int.TryParse(status[1], out int parsed) ? parsed : 0;
                string location = Header(head, "location");
                if (code >= 301 && code <= 308 && location != null && redirects < 5)
                {
                    uri = new Uri(uri, location);
                    client.Close();
                    continue;
                }
                if (code == 403) throw new StationRefusedException(L("The station's server refused access (403)."));
                if (code >= 400 && code < 500) throw new StationRefusedException(L("The station's server returned error {0}.", code));
                if (code != 200) throw new InvalidOperationException(L("The station's server returned error {0}.", code));

                if (string.Equals(Header(head, "transfer-encoding"), "chunked", StringComparison.OrdinalIgnoreCase))
                    network = new ChunkedStream(network);
                int.TryParse(Header(head, "icy-metaint"), out int interval);
                return new RadioStream(client, network, Math.Max(0, interval), titleChanged);
            }
            catch (Exception error)
            {
                client.Close();
                cancel.ThrowIfCancellationRequested();
                if (error is InvalidOperationException) throw;
                throw new InvalidOperationException(L("Couldn't connect to the station. Check your internet connection."), error);
            }
        }
    }

    private static string[] ReadHead(Stream network)
    {
        var line = new StringBuilder();
        var lines = new System.Collections.Generic.List<string>();
        int total = 0;
        while (true)
        {
            int value = network.ReadByte();
            if (value < 0) throw new IOException("Serwer zamknął połączenie.");
            if (++total > 16384) throw new IOException("Zbyt długi nagłówek odpowiedzi.");
            if (value == '\n')
            {
                string text = line.ToString().TrimEnd('\r');
                line.Clear();
                if (text.Length == 0)
                {
                    if (lines.Count == 0) continue;
                    return lines.ToArray();
                }
                lines.Add(text);
            }
            else line.Append((char)value);
        }
    }

    private static string Header(string[] head, string name)
    {
        for (int i = 1; i < head.Length; i++)
        {
            int colon = head[i].IndexOf(':');
            if (colon > 0 && string.Equals(head[i].Substring(0, colon).Trim(), name, StringComparison.OrdinalIgnoreCase))
                return head[i].Substring(colon + 1).Trim();
        }
        return null;
    }

    public override int Read(byte[] buffer, int offset, int count)
    {
        if (metaInterval > 0)
        {
            if (untilMeta == 0)
            {
                if (!ReadMetadata()) return 0;
                untilMeta = metaInterval;
            }
            count = Math.Min(count, untilMeta);
        }
        int read = source.Read(buffer, offset, count);
        if (metaInterval > 0) untilMeta -= read;
        return read;
    }

    private bool ReadMetadata()
    {
        int length = source.ReadByte();
        if (length < 0) return false;
        if (length == 0) return true;
        var data = new byte[length * 16];
        for (int done = 0; done < data.Length;)
        {
            int read = source.Read(data, done, data.Length - done);
            if (read == 0) return false;
            done += read;
        }

        string text;
        try { text = StrictUtf8.GetString(data); }
        catch (DecoderFallbackException) { text = Encoding.GetEncoding(1250).GetString(data); }
        const string key = "StreamTitle='";
        int start = text.IndexOf(key, StringComparison.Ordinal);
        if (start < 0) return true;
        start += key.Length;
        int end = text.IndexOf("';", start, StringComparison.Ordinal);
        if (end < 0) end = text.TrimEnd('\0').Length;
        string value = text.Substring(start, Math.Max(0, end - start)).Trim('﻿', ' ', '\0');
        if (value != title)
        {
            title = value;
            titleChanged?.Invoke(value);
        }
        return true;
    }

    protected override void Dispose(bool disposing)
    {
        if (disposing)
        {
            try { source.Dispose(); } catch (IOException) { }
            client.Close();
        }
        base.Dispose(disposing);
    }

    public override bool CanRead => true;
    public override bool CanSeek => false;
    public override bool CanWrite => false;
    public override long Length => throw new NotSupportedException();
    public override long Position { get => throw new NotSupportedException(); set => throw new NotSupportedException(); }
    public override void Flush() { }
    public override long Seek(long offset, SeekOrigin origin) => throw new NotSupportedException();
    public override void SetLength(long value) => throw new NotSupportedException();
    public override void Write(byte[] buffer, int offset, int count) => throw new NotSupportedException();

    // Some servers answer with Transfer-Encoding: chunked even to HTTP/1.0 requests.
    internal sealed class ChunkedStream : Stream
    {
        private const int LongestLine = 1024;   // a chunk's size line, without its line feed
        private readonly Stream source;
        private int left;
        private bool finished;

        internal ChunkedStream(Stream source) => this.source = source;

        public override int Read(byte[] buffer, int offset, int count)
        {
            if (finished) return 0;
            if (left == 0)
            {
                string line = ReadLine();
                if (line.Length == 0) line = ReadLine();
                int semicolon = line.IndexOf(';');
                if (semicolon >= 0) line = line.Substring(0, semicolon);
                left = Convert.ToInt32(line.Trim(), 16);
                if (left == 0) { finished = true; return 0; }
            }
            int read = source.Read(buffer, offset, Math.Min(count, left));
            if (read == 0) { finished = true; return 0; }
            left -= read;
            return read;
        }

        // A longer line ends the stream with an error, like any broken stream.
        private string ReadLine()
        {
            var line = new StringBuilder();
            int value, length = 0;
            while ((value = source.ReadByte()) >= 0 && value != '\n')
            {
                if (++length > LongestLine) throw new IOException("Zbyt długi wiersz rozmiaru fragmentu.");
                if (value != '\r') line.Append((char)value);
            }
            if (value < 0) throw new IOException("Serwer zamknął połączenie.");
            return line.ToString();
        }

        protected override void Dispose(bool disposing)
        {
            if (disposing) source.Dispose();
            base.Dispose(disposing);
        }

        public override bool CanRead => true;
        public override bool CanSeek => false;
        public override bool CanWrite => false;
        public override long Length => throw new NotSupportedException();
        public override long Position { get => throw new NotSupportedException(); set => throw new NotSupportedException(); }
        public override void Flush() { }
        public override long Seek(long offset, SeekOrigin origin) => throw new NotSupportedException();
        public override void SetLength(long value) => throw new NotSupportedException();
        public override void Write(byte[] buffer, int offset, int count) => throw new NotSupportedException();
    }

#if SELFTEST
    // Self-test (--test-menu): chunked transfer, and a chunk's size line of more than 1024 bytes ends the stream with an
    // error, like any broken stream.
    internal static void Verify()
    {
        void Check(bool ok, string what)
        {
            if (!ok) throw new InvalidOperationException("Strumień: " + what);
        }
        string Read(string body)
        {
            using (var chunked = new ChunkedStream(new MemoryStream(Encoding.ASCII.GetBytes(body))))
            using (var reader = new StreamReader(chunked, Encoding.ASCII))
                return reader.ReadToEnd();
        }
        Check(Read("4\r\nWiki\r\n5;name=value\r\npedia\r\n0\r\n\r\n") == "Wikipedia", "fragmenty.");
        Check(Read("4;" + new string('x', 1021) + "\r\nabcd\r\n0\r\n\r\n") == "abcd", "wiersz rozmiaru o długości 1024 bajtów.");
        foreach (string line in new[] { "4;" + new string('x', 1022) + "\r", new string('0', 100000), new string('\r', 100000) })
        {
            bool broken = false;
            try { Read(line + "\nabcd\r\n0\r\n\r\n"); }
            catch (IOException) { broken = true; }
            Check(broken, "przyjęty wiersz rozmiaru o długości " + line.Length + " bajtów.");
        }
    }
#endif
}
