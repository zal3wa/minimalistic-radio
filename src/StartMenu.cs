using System;
using System.Diagnostics;
using System.IO;
using System.Runtime.InteropServices;
using System.Runtime.InteropServices.ComTypes;
using System.Text;

// A Start menu shortcut carrying the app's ID ("Minimalistic Radio"). With it Windows knows the app:
// its name and icon show in the media controls, and "shell:AppsFolder\Minimalistic Radio" starts it,
// which is what the Windhawk taskbar player's "Open media app" click does.
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
            link.SetDescription(Lang.T("Radio internetowe", "Internet radio"));
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
