using System;
using System.Linq;
using System.Runtime.InteropServices;
using System.Threading;
using System.Windows;
using Forms = System.Windows.Forms;

internal static class Program
{
    [DllImport("shell32.dll", CharSet = CharSet.Unicode)]
    private static extern int SetCurrentProcessExplicitAppUserModelID(string appId);

    [STAThread]
    private static void Main(string[] args)
    {
        SetCurrentProcessExplicitAppUserModelID(Radio.AppName);
        Lang.Setting = Storage.Read<Preferences>(Storage.PreferencesFile)?.Language ?? "auto";
        bool testMenu = args.Contains("--test-menu");
        // Same names as earlier versions, so an old copy and the Windhawk taskbar mod keep working with this one.
        using (var instance = new Mutex(true, testMenu ? @"Local\MinimalisticRadio.Test" : @"Local\RadioNaZywo", out bool first))
        using (var request = new EventWaitHandle(false, EventResetMode.AutoReset,
            testMenu ? @"Local\MinimalisticRadio.TestPanel" : @"Local\MinimalisticRadio.Panel"))
        {
            bool openPanel = args.Length == 0 || args.Contains("--open-panel");
            if (!first)
            {
                if (openPanel) { request.Set(); return; }
                if (testMenu) { Environment.ExitCode = 2; return; }
                Forms.MessageBox.Show(Lang.T("Radio jest już uruchomione. Poszukaj ikony obok zegara.",
                    "The radio is already running. Look for its icon next to the clock."), Radio.AppName);
                return;
            }
            if (openPanel) request.Set();

            var app = new Application { ShutdownMode = ShutdownMode.OnExplicitShutdown };
            Theme.Load(app);
            var radio = new Radio(app, request, testMenu);
            app.Dispatcher.BeginInvoke(new Action(radio.Start));
            app.Run();
        }
    }
}
