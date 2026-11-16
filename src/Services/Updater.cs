using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Net.Http;
using System.Security.Cryptography;
using System.Text;
using System.Threading.Tasks;
using System.Web.Script.Serialization;
using static Lang;

internal sealed class Release
{
    internal Version Version;
    internal string Tag, Page, Notes, Download, Sha256, SignatureDownload;
    internal string Signature;   // the .sig's text, once the download was verified with it
}

// A release whose signature is missing, damaged or wrong: it isn't installed, and the release page is offered instead.
internal sealed class UpdateNotVerifiedException : Exception
{
    internal UpdateNotVerifiedException() : base(L("This update could not be verified. Download it from the release page.")) { }
}

// Updates from the GitHub releases of the project, the way ShareX does it: the radio looks for a newer
// release at most once a day, tells about each version once, and installs it only when asked.
internal static class Updater
{
    internal const string Repository = "zal3wa/minimalistic-radio";
    internal static string Page => "https://github.com/" + Repository;
    private const int LargestProgram = 32 << 20, LargestSignature = 1024;

    internal static Version Current
    {
        get
        {
            Version version = typeof(Updater).Assembly.GetName().Version;
            return new Version(version.Major, version.Minor, Math.Max(0, version.Build));
        }
    }

    internal static Version ParseVersion(string tag) =>
        Version.TryParse((tag ?? "").Trim().TrimStart('v', 'V'), out Version version)
            ? new Version(version.Major, version.Minor, Math.Max(0, version.Build)) : null;

    private static string Exe => System.Reflection.Assembly.GetEntryAssembly().Location;

    // The newest published release, or null when there is none yet.
    internal static async Task<Release> Latest(HttpClient client)
    {
        using (var request = new HttpRequestMessage(HttpMethod.Get, "https://api.github.com/repos/" + Repository + "/releases/latest"))
        {
            request.Headers.UserAgent.ParseAdd("MinimalisticRadio/" + Current.ToString(3));
            request.Headers.Accept.ParseAdd("application/vnd.github+json");
            using (HttpResponseMessage response = await client.SendAsync(request))
            {
                if (response.StatusCode == System.Net.HttpStatusCode.NotFound) return null;
                response.EnsureSuccessStatusCode();
                return ParseRelease(await response.Content.ReadAsStringAsync());
            }
        }
    }

    // The API's answer: the version, the release page and the exe with its digest and signature. Addresses that aren't
    // the project's own on github.com are left out (ProjectAddress).
    internal static Release ParseRelease(string json)
    {
        var root = new JavaScriptSerializer { MaxJsonLength = 4 << 20 }.DeserializeObject(json) as Dictionary<string, object>;
        if (root == null) return null;
        string Text(Dictionary<string, object> data, string key) => data.TryGetValue(key, out object value) ? value as string : null;
        var release = new Release { Tag = Text(root, "tag_name"), Page = ProjectAddress(Text(root, "html_url")), Notes = Text(root, "body") };
        release.Version = ParseVersion(release.Tag);
        if (release.Version == null) return null;
        var assets = (root.TryGetValue("assets", out object list) ? list as object[] : null)?.OfType<Dictionary<string, object>>().ToList()
            ?? new List<Dictionary<string, object>>();
        Dictionary<string, object> program = assets.FirstOrDefault(asset => Text(asset, "name")?.EndsWith(".exe", StringComparison.OrdinalIgnoreCase) == true);
        if (program == null) return release;
        release.Download = ProjectAddress(Text(program, "browser_download_url"));
        string digest = Text(program, "digest");
        if (digest != null && digest.StartsWith("sha256:", StringComparison.OrdinalIgnoreCase))
            release.Sha256 = digest.Substring(7);
        string signatureName = Text(program, "name") + ".sig";
        Dictionary<string, object> signature = assets.FirstOrDefault(asset => string.Equals(Text(asset, "name"), signatureName, StringComparison.OrdinalIgnoreCase));
        if (signature != null) release.SignatureDownload = ProjectAddress(Text(signature, "browser_download_url"));
        return release;
    }

    // An address from the GitHub API is used only when it is https on github.com, under the project
    // (https://github.com/zal3wa/minimalistic-radio/…), written plainly: no port, user, query, %-codes or dot segments.
    // Anything else gives null, and the radio falls back to its own constant page.
    internal static string ProjectAddress(string address)
    {
        if (!Uri.TryCreate(address, UriKind.Absolute, out Uri uri) || uri.Scheme != Uri.UriSchemeHttps || uri.Host != "github.com" ||
            !uri.IsDefaultPort || uri.UserInfo.Length > 0 || uri.Query.Length > 0 || uri.Fragment.Length > 0)
            return null;
        string path = uri.AbsolutePath;
        bool plain = path.All(letter => letter < 128 && (char.IsLetterOrDigit(letter) || "/-._~".IndexOf(letter) >= 0)) &&
            !path.Split('/').Any(part => part == "." || part == "..");
        return plain && path.StartsWith("/" + Repository + "/", StringComparison.Ordinal) ? uri.AbsoluteUri : null;
    }

    // Downloads the release's exe and its signature, and checks them: the SHA-256 published by GitHub (when there is
    // one) and the project's signature (always). Only a verified exe is saved, for Install.
    internal static async Task<string> Download(Release release, Action<int> progress)
    {
        if (release.Download == null)
            throw new InvalidOperationException(L("The release has no program file."));
        byte[] exe;
        string signature = null;
        using (var client = new HttpClient { Timeout = TimeSpan.FromMinutes(2) })
        {
            client.DefaultRequestHeaders.UserAgent.ParseAdd("MinimalisticRadio/" + Current.ToString(3));
            exe = await Fetch(client, release.Download, LargestProgram, progress, true);
            if (exe == null || (release.Sha256 != null && !string.Equals(Sha256(exe), release.Sha256, StringComparison.OrdinalIgnoreCase)))
                throw new InvalidDataException(L("The downloaded file is damaged."));
            if (release.SignatureDownload != null)
            {
                byte[] text = await Fetch(client, release.SignatureDownload, LargestSignature, null, false);
                if (text != null) signature = Encoding.ASCII.GetString(text);
            }
        }
        if (!Signed(release.Version.ToString(3), exe, signature)) throw new UpdateNotVerifiedException();
        release.Signature = signature;
        string file = Path.Combine(Path.GetTempPath(), "Minimalistic Radio " + release.Version.ToString(3) + ".exe");
        File.WriteAllBytes(file, exe);
        return file;
    }

    // The file's bytes; null when it is bigger than longest, or (unless required) when the server doesn't have it.
    private static async Task<byte[]> Fetch(HttpClient client, string address, int longest, Action<int> progress, bool required)
    {
        using (HttpResponseMessage response = await client.GetAsync(address, HttpCompletionOption.ResponseHeadersRead))
        {
            if (!required && !response.IsSuccessStatusCode) return null;
            response.EnsureSuccessStatusCode();
            long total = response.Content.Headers.ContentLength ?? 0;
            using (Stream source = await response.Content.ReadAsStreamAsync())
            using (var target = new MemoryStream())
            {
                var buffer = new byte[1 << 16];
                int read;
                while ((read = await source.ReadAsync(buffer, 0, buffer.Length)) > 0)
                {
                    if (target.Length + read > longest) return null;
                    target.Write(buffer, 0, read);
                    if (total > 0) progress?.Invoke((int)Math.Min(100, target.Length * 100 / total));
                }
                return target.ToArray();
            }
        }
    }

    private static string Sha256(byte[] data)
    {
        using (SHA256 hash = SHA256.Create())
            return string.Concat(hash.ComputeHash(data).Select(part => part.ToString("x2")));
    }

    // The release job signs "Minimalistic Radio for Windows <x.y.z> <the exe's SHA-256, lowercase hex>" with the project's
    // ECDSA P-256 key (SHA-256); Minimalistic-Radio.exe.sig is the 64-byte r‖s signature in base64. This is the check:
    // the exe's own hash, for exactly this version, against the public key built into the radio. The release job calls
    // it too, on the exe it built (.github/workflows/build.yml), so keep its name and parameters.
    internal static bool Signed(string version, byte[] exe, string signature)
    {
        if (version == null || exe == null || signature == null) return false;
        byte[] value;
        try { value = Convert.FromBase64String(signature.Trim()); }
        catch (FormatException) { return false; }
        return SignatureMatches(version, Sha256(exe), value);
    }

    internal static bool SignatureMatches(string version, string sha256, byte[] signature)
    {
        if (version == null || sha256 == null || signature == null || signature.Length != 64) return false;
        byte[] message = Encoding.UTF8.GetBytes("Minimalistic Radio for Windows " + version + " " + sha256);
        try
        {
            using (ECDsa key = ECDsa.Create(PublicKey()))
                return key.VerifyData(message, signature, HashAlgorithmName.SHA256);
        }
        catch (CryptographicException error)
        {
            Debug.WriteLine(error);
            return false;
        }
    }

    // .github/update-signing.pub.pem, built into the exe: a P-256 SubjectPublicKeyInfo, whose last 64 bytes are the
    // point's X and Y (.NET Framework can't read the format itself).
    private static ECParameters PublicKey()
    {
        string pem;
        using (Stream stream = typeof(Updater).Assembly.GetManifestResourceStream("update-signing.pub.pem"))
        {
            if (stream == null) throw new CryptographicException("No public key.");
            using (var reader = new StreamReader(stream)) pem = reader.ReadToEnd();
        }
        byte[] key;
        try
        {
            key = Convert.FromBase64String(string.Concat(pem.Split('\n').Select(line => line.Trim()).Where(line => !line.StartsWith("-----"))));
        }
        catch (FormatException) { throw new CryptographicException("A damaged public key."); }
        byte[] header = { 0x30, 0x59, 0x30, 0x13, 0x06, 0x07, 0x2A, 0x86, 0x48, 0xCE, 0x3D, 0x02, 0x01, 0x06, 0x08, 0x2A, 0x86, 0x48, 0xCE, 0x3D,
            0x03, 0x01, 0x07, 0x03, 0x42, 0x00, 0x04 };
        if (key.Length != header.Length + 64 || !key.Take(header.Length).SequenceEqual(header)) throw new CryptographicException("Not a P-256 public key.");
        return new ECParameters
        {
            Curve = ECCurve.NamedCurves.nistP256,
            Q = new ECPoint { X = key.Skip(header.Length).Take(32).ToArray(), Y = key.Skip(header.Length + 32).ToArray() }
        };
    }

    // A running exe can't be overwritten, but it can be renamed: the old one steps aside as *.old,
    // the new one takes its place and is started; the old copy is removed on the next start. The downloaded file is
    // read and verified once more first, and what was verified is what gets written.
    internal static void Install(Release release, string downloaded)
    {
        byte[] exe = File.ReadAllBytes(downloaded);
        if (!Signed(release.Version.ToString(3), exe, release.Signature))
        {
            try { File.Delete(downloaded); }
            catch (Exception error) when (error is IOException || error is UnauthorizedAccessException) { Debug.WriteLine(error); }
            throw new UpdateNotVerifiedException();
        }
        string target = Exe, old = target + ".old";
        if (File.Exists(old)) File.Delete(old);
        File.Move(target, old);
        try { File.WriteAllBytes(target, exe); }
        catch
        {
            if (File.Exists(target)) File.Delete(target);
            File.Move(old, target);
            throw;
        }
        try { File.Delete(downloaded); }
        catch (Exception error) when (error is IOException || error is UnauthorizedAccessException) { Debug.WriteLine(error); }
        Process.Start(new ProcessStartInfo(target, "--updated") { UseShellExecute = false })?.Dispose();
    }

    internal static void CleanUp()
    {
        try
        {
            string old = Exe + ".old";
            if (File.Exists(old)) File.Delete(old);
        }
        catch (Exception error) when (error is IOException || error is UnauthorizedAccessException) { Debug.WriteLine(error); }
    }

#if SELFTEST
    // Self-test (--test-menu): the signature check against a message signed with the project's real key, and which
    // addresses from the GitHub API are used.
    internal static void Verify()
    {
        void Check(bool ok, string what)
        {
            if (!ok) throw new InvalidOperationException("Aktualizacje: " + what);
        }
        const string empty = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855";   // SHA-256 of nothing
        const string signed = "tQA3ijFKDn5OCtDQd6ef1k9XiFM+c9J7/Q6detkKVsAVqIvdPsCJpQ+FbfWCYYiEq+Y0oRelhvsqY4IEsZp3uw==";
        byte[] signature = Convert.FromBase64String(signed);
        Check(SignatureMatches("0.0.1", empty, signature), "podpis z prawdziwego klucza się nie zgadza.");
        Check(Signed("0.0.1", new byte[0], signed) && Signed("0.0.1", new byte[0], " " + signed + "\n"), "podpis pliku (skrót liczony z pliku).");
        Check(!SignatureMatches("0.0.2", empty, signature) && !Signed("0.0.2", new byte[0], signed), "podpis przyjęty dla innej wersji.");
        Check(!SignatureMatches("0.0.1", "f" + empty.Substring(1), signature) && !Signed("0.0.1", new byte[1], signed), "podpis przyjęty dla innego pliku.");
        Check(!SignatureMatches("0.0.1", empty.ToUpperInvariant(), signature), "skrót wielkimi literami to inna wiadomość.");
        for (int index = 0; index < signature.Length; index += 21)
        {
            byte[] changed = (byte[])signature.Clone();
            changed[index] ^= 1;
            Check(!SignatureMatches("0.0.1", empty, changed), "przyjęty zmieniony bajt podpisu nr " + index + ".");
        }
        Check(!SignatureMatches("0.0.1", empty, signature.Take(63).ToArray()) && !SignatureMatches("0.0.1", empty, null) &&
            !Signed("0.0.1", new byte[0], null) && !Signed("0.0.1", new byte[0], "") && !Signed("0.0.1", new byte[0], "not base64!") &&
            !Signed(null, new byte[0], signed), "brakujący albo uszkodzony podpis.");

        // Release addresses: only https on github.com, under the project, written plainly.
        foreach (string good in new[] { "https://github.com/zal3wa/minimalistic-radio/releases/tag/v2.7.2",
            "https://github.com/zal3wa/minimalistic-radio/releases/download/v2.7.2/Minimalistic-Radio.exe",
            "https://GitHub.com/zal3wa/minimalistic-radio/releases/download/v2.7.2/Minimalistic-Radio.exe.sig" })
            Check(ProjectAddress(good) != null, "dobry adres wydania odrzucony: " + good);
        foreach (string bad in new[] { null, "", "javascript:alert(1)", "http://github.com/zal3wa/minimalistic-radio/releases/tag/v2.7.2",
            "https://github.com.evil.example/zal3wa/minimalistic-radio/releases", "https://evil.example/zal3wa/minimalistic-radio/releases",
            "https://github.com/zal3wa/minimalistic-radio", "https://github.com/zal3wa/minimalistic-radio-evil/releases",
            "https://github.com/someone/minimalistic-radio/releases", "https://user@github.com/zal3wa/minimalistic-radio/releases",
            "https://github.com:8443/zal3wa/minimalistic-radio/releases", "https://github.com/zal3wa/minimalistic-radio/../../evil/releases",
            "https://github.com/zal3wa/minimalistic-radio/%2e%2e/%2e%2e/evil", "https://github.com/zal3wa/minimalistic-radio/releases?x=1",
            "https://github.com/zal3wa/minimalistic-radio/releases#x", "file:///C:/zal3wa/minimalistic-radio/x.exe",
            "https://github.com/zal3wa/minimalistic-radio/releases\\..\\..\\evil", "https://github.com/zal3wa/minimalistic-radio/x\u0000" })
            Check(ProjectAddress(bad) == null, "zły adres wydania przyjęty: " + bad);
        string Json(string page, string download, string signatureDownload) => "{\"tag_name\":\"v2.7.2\",\"html_url\":\"" + page + "\",\"assets\":[" +
            "{\"name\":\"Minimalistic-Radio.exe.sig\",\"browser_download_url\":\"" + signatureDownload + "\"}," +
            "{\"name\":\"Minimalistic-Radio.exe\",\"browser_download_url\":\"" + download + "\",\"digest\":\"sha256:" + empty + "\"}]}";
        const string project = "https://github.com/zal3wa/minimalistic-radio/releases/";
        Release release = ParseRelease(Json(project + "tag/v2.7.2", project + "download/v2.7.2/Minimalistic-Radio.exe",
            project + "download/v2.7.2/Minimalistic-Radio.exe.sig"));
        Check(release?.Version == new Version(2, 7, 2) && release.Page == project + "tag/v2.7.2" && release.Download == project + "download/v2.7.2/Minimalistic-Radio.exe" &&
            release.SignatureDownload == project + "download/v2.7.2/Minimalistic-Radio.exe.sig" && release.Sha256 == empty, "odczyt wydania z GitHuba.");
        release = ParseRelease(Json("https://evil.example/zal3wa/minimalistic-radio/", "https://evil.example/x.exe", "https://evil.example/x.exe.sig"));
        Check(release != null && release.Page == null && release.Download == null && release.SignatureDownload == null, "obce adresy w wydaniu.");
    }
#endif
}
