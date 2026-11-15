using System;
using System.Diagnostics;
using System.IO;
using System.Runtime.InteropServices;
using System.Runtime.InteropServices.ComTypes;
using System.Text;
using static Lang;

// A Start menu shortcut carrying the app's ID ("Minimalistic Radio"). With it Windows knows the app:
// its name and icon show in the media controls, and "shell:AppsFolder\Minimalistic Radio" starts it,
// which is what taskbar media players do to open the app.
internal static class StartMenu
{
    internal static string LinkPath => Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.Programs), Radio.AppName + ".lnk");

    internal static void Register(string exe)
    {
        try
        {
            var link = (IShellLinkW)new ShellLink();
            if (File.Exists(LinkPath))
            {
                ((IPersistFile)link).Load(LinkPath, 0);
                var target = new StringBuilder(1024);
                link.GetPath(target, target.Capacity, IntPtr.Zero, 0);
                if (string.Equals(target.ToString(), exe, StringComparison.OrdinalIgnoreCase)) return;
            }
            link.SetPath(exe);
            link.SetWorkingDirectory(Path.GetDirectoryName(exe));
            link.SetIconLocation(exe, 0);
            link.SetDescription(L("Internet radio"));
            var key = new PropertyKey { Format = new Guid("9F4C2855-9F79-4B39-A8D0-E1D42DE1D5F3"), Id = 5 }; // PKEY_AppUserModel_ID
            var value = new PropVariant { Type = 31, Pointer = Marshal.StringToCoTaskMemUni(Radio.AppName) };   // VT_LPWSTR
            try
            {
                var store = (IPropertyStore)link;
                store.SetValue(ref key, ref value);
                store.Commit();
            }
            finally { Marshal.FreeCoTaskMem(value.Pointer); }
            ((IPersistFile)link).Save(LinkPath, true);
        }
        catch (Exception error) when (error is COMException || error is IOException || error is UnauthorizedAccessException)
        {
            Debug.WriteLine(error);
        }
    }

    [ComImport, Guid("00021401-0000-0000-C000-000000000046")]
    private class ShellLink { }

    [ComImport, Guid("000214F9-0000-0000-C000-000000000046"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    private interface IShellLinkW
    {
        void GetPath([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder file, int max, IntPtr findData, uint flags);
        void GetIDList(out IntPtr list);
        void SetIDList(IntPtr list);
        void GetDescription([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder name, int max);
        void SetDescription([MarshalAs(UnmanagedType.LPWStr)] string name);
        void GetWorkingDirectory([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder dir, int max);
        void SetWorkingDirectory([MarshalAs(UnmanagedType.LPWStr)] string dir);
        void GetArguments([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder args, int max);
        void SetArguments([MarshalAs(UnmanagedType.LPWStr)] string args);
        void GetHotkey(out short hotkey);
        void SetHotkey(short hotkey);
        void GetShowCmd(out int command);
        void SetShowCmd(int command);
        void GetIconLocation([Out, MarshalAs(UnmanagedType.LPWStr)] StringBuilder path, int max, out int index);
        void SetIconLocation([MarshalAs(UnmanagedType.LPWStr)] string path, int index);
        void SetRelativePath([MarshalAs(UnmanagedType.LPWStr)] string path, uint reserved);
        void Resolve(IntPtr window, uint flags);
        void SetPath([MarshalAs(UnmanagedType.LPWStr)] string file);
    }

    [ComImport, Guid("886D8EEB-8CF2-4446-8D02-CDBA1DBDCF99"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    private interface IPropertyStore
    {
        void GetCount(out uint count);
        void GetAt(uint index, out PropertyKey key);
        void GetValue(ref PropertyKey key, out PropVariant value);
        void SetValue(ref PropertyKey key, ref PropVariant value);
        void Commit();
    }

    [StructLayout(LayoutKind.Sequential, Pack = 4)]
    private struct PropertyKey
    {
        public Guid Format;
        public uint Id;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct PropVariant
    {
        public ushort Type;
        public ushort Reserved1, Reserved2, Reserved3;
        public IntPtr Pointer;
        public IntPtr Padding;
    }
}

// minimalistic-radio:// links (a shared station's "Open in Minimalistic Radio" on its page) start this exe with
// --open "<link>". Registered for the current user only (no administrator rights needed), at every start, and written
// again only when it differs (the exe may have moved). The test build doesn't register it.
internal static class LinkHandler
{
    private const string Key = @"Software\Classes\" + ShareLink.Scheme;

    internal static void Register(string exe)
    {
        string name = "URL:" + Radio.AppName, icon = "\"" + exe + "\",0", command = "\"" + exe + "\" --open \"%1\"";
        try
        {
            using (Microsoft.Win32.RegistryKey root = Microsoft.Win32.Registry.CurrentUser.OpenSubKey(Key))
            {
                string Value(string path) => (root?.OpenSubKey(path)?.GetValue("") as string);
                if (root?.GetValue("") as string == name && root.GetValue("URL Protocol") is string &&
                    Value("DefaultIcon") == icon && Value(@"shell\open\command") == command)
                    return;
            }
            using (Microsoft.Win32.RegistryKey root = Microsoft.Win32.Registry.CurrentUser.CreateSubKey(Key))
            {
                root.SetValue("", name);
                root.SetValue("URL Protocol", "");
                using (Microsoft.Win32.RegistryKey key = root.CreateSubKey("DefaultIcon")) key.SetValue("", icon);
                using (Microsoft.Win32.RegistryKey key = root.CreateSubKey(@"shell\open\command")) key.SetValue("", command);
            }
        }
        catch (Exception error) when (error is UnauthorizedAccessException || error is System.Security.SecurityException || error is IOException)
        {
            Debug.WriteLine(error);
        }
    }
}

// A link given to a second start of the radio (--open, from a minimalistic-radio:// link) goes to the running one:
// WM_COPYDATA to a message-only window of the running radio. Only programs on the same desktop, so in the same user
// session, can find that window. The plain "open the panel" keeps its EventWaitHandle.
internal sealed class LinkChannel : System.Windows.Forms.NativeWindow, IDisposable
{
    private const int CopyData = 0x004A, MessageOnly = -3, LongestLink = 16384;
    private static readonly IntPtr Marker = (IntPtr)0x4D524C4B;   // "MRLK": a link for the radio, nothing else

    [StructLayout(LayoutKind.Sequential)]
    private struct CopyDataStruct
    {
        public IntPtr Marker;
        public int Size;
        public IntPtr Data;
    }

    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    private static extern IntPtr FindWindowEx(IntPtr parent, IntPtr after, string className, string title);

    [DllImport("user32.dll")]
    private static extern IntPtr SendMessageTimeout(IntPtr window, int message, IntPtr wParam, ref CopyDataStruct data,
        int flags, int timeout, out IntPtr result);

    [DllImport("user32.dll")]
    private static extern int GetWindowThreadProcessId(IntPtr window, out int process);

    [DllImport("user32.dll")]
    private static extern bool AllowSetForegroundWindow(int process);

    // The test build listens under a name of its own, so a test never takes the real radio's links.
    internal static string WindowName(bool test) => Radio.AppName + (test ? " links (self-test)" : " links");

    private readonly Action<string> received;

    internal LinkChannel(string name, Action<string> received)
    {
        this.received = received;
        CreateHandle(new System.Windows.Forms.CreateParams { Caption = name, Parent = (IntPtr)MessageOnly });
    }

    protected override void WndProc(ref System.Windows.Forms.Message message)
    {
        if (message.Msg == CopyData)
        {
            var data = (CopyDataStruct)Marshal.PtrToStructure(message.LParam, typeof(CopyDataStruct));
            if (data.Marker == Marker && data.Size > 0 && data.Size <= LongestLink * 2 && data.Size % 2 == 0 && data.Data != IntPtr.Zero)
            {
                string link = Marshal.PtrToStringUni(data.Data, data.Size / 2);
                // The sender waits for the answer: the link is handled after it, on the radio's own time.
                System.Windows.Application.Current?.Dispatcher.BeginInvoke(new Action(() => received(link)));
                message.Result = (IntPtr)1;
                return;
            }
        }
        base.WndProc(ref message);
    }

    // From the second start: gives the link to the running radio (which may still be starting: up to 5 s) and lets it
    // bring its panel to the front. False if no running radio took it.
    internal static bool Send(string name, string link)
    {
        if (string.IsNullOrEmpty(link) || link.Length > LongestLink) return false;
        for (int attempt = 0; attempt < 50; attempt++)
        {
            IntPtr target = FindWindowEx((IntPtr)MessageOnly, IntPtr.Zero, null, name);
            if (target != IntPtr.Zero)
            {
                GetWindowThreadProcessId(target, out int process);
                AllowSetForegroundWindow(process);   // this start came from a click, so it may pass the front on
                IntPtr text = Marshal.StringToHGlobalUni(link);
                try
                {
                    var data = new CopyDataStruct { Marker = Marker, Size = link.Length * 2, Data = text };
                    return SendMessageTimeout(target, CopyData, IntPtr.Zero, ref data, 0x0002, 5000, out IntPtr result) != IntPtr.Zero &&
                        result == (IntPtr)1;   // SMTO_ABORTIFHUNG
                }
                finally { Marshal.FreeHGlobal(text); }
            }
            System.Threading.Thread.Sleep(100);
        }
        return false;
    }

    public void Dispose() => DestroyHandle();
}

// "Start with Windows": the current user's Run key, so no administrator rights are needed and the entry
// also shows in Settings → Apps → Startup. "--autostart" starts the radio quietly next to the clock.
internal static class Autostart
{
    private const string Key = @"Software\Microsoft\Windows\CurrentVersion\Run";

    internal static bool Enabled
    {
        get
        {
            using (Microsoft.Win32.RegistryKey key = Microsoft.Win32.Registry.CurrentUser.OpenSubKey(Key))
                return key?.GetValue(Radio.AppName) != null;
        }
    }

    internal static void Set(bool enabled, string exe)
    {
        try
        {
            using (Microsoft.Win32.RegistryKey key = Microsoft.Win32.Registry.CurrentUser.CreateSubKey(Key))
            {
                if (enabled) key.SetValue(Radio.AppName, "\"" + exe + "\" --autostart");
                else key.DeleteValue(Radio.AppName, false);
            }
        }
        catch (Exception error) when (error is UnauthorizedAccessException || error is System.Security.SecurityException || error is IOException)
        {
            Debug.WriteLine(error);
        }
    }

    // Keeps the entry pointing at this exe if it was moved.
    internal static void Refresh(string exe)
    {
        if (Enabled) Set(true, exe);
    }
}
