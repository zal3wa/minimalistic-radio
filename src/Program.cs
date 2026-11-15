using System;
using System.Linq;
using System.Runtime.InteropServices;
using System.Threading;
using System.Windows;
using Forms = System.Windows.Forms;
using static Lang;

internal static class Program
{
    [DllImport("shell32.dll", CharSet = CharSet.Unicode)]
    private static extern int SetCurrentProcessExplicitAppUserModelID(string appId);

    [STAThread]
    private static void Main(string[] args)
    {
#if !SELFTEST
        // The self-test is only in a build made with -p:SelfTest=true (docs/BUILDING.md); this one says so and stops,
        // instead of starting the radio for a script that waits for a test.
        if (args.Contains("--test-menu"))
        {
            Environment.ExitCode = 3;
            return;
        }
#endif
        SetCurrentProcessExplicitAppUserModelID(Radio.AppName);
        Lang.Setting = Storage.Read<Preferences>(Storage.PreferencesFile)?.Language ?? "auto";
#if SELFTEST
        // "--lang de": the self-test and its pictures in that language, whatever the settings say.
        int chosen = Array.IndexOf(args, "--lang");
        if (chosen >= 0 && chosen + 1 < args.Length) Lang.Setting = args[chosen + 1];
#endif
        bool updated = args.Contains("--updated");
        // Same names as earlier versions, so an old copy and the Windhawk taskbar mod keep working with this one.
        string instanceName = @"Local\RadioNaZywo", panelName = @"Local\MinimalisticRadio.Panel";
#if SELFTEST
        // The self-test runs beside the radio, under names of its own.
        bool testMenu = args.Contains("--test-menu");
        if (testMenu)
        {
            instanceName = @"Local\MinimalisticRadio.Test";
            panelName = @"Local\MinimalisticRadio.TestPanel";
        }
#endif
        using (var instance = new Mutex(true, instanceName, out bool first))
        using (var request = new EventWaitHandle(false, EventResetMode.AutoReset, panelName))
        {
            // Started by an update: the previous version is still closing, wait for it.
            if (!first && updated)
            {
                try { first = instance.WaitOne(TimeSpan.FromSeconds(20)); }
                catch (AbandonedMutexException) { first = true; }
            }
            bool openPanel = args.Length == 0 || args.Contains("--open-panel");
            if (!first)
            {
                if (openPanel) { request.Set(); return; }
#if SELFTEST
                if (testMenu) { Environment.ExitCode = 2; return; }
#endif
                if (args.Contains("--autostart")) return;
                Forms.MessageBox.Show(L("The radio is already running. Look for its icon next to the clock."), Radio.AppName);
                return;
            }
            if (openPanel) request.Set();

            var app = new Application { ShutdownMode = ShutdownMode.OnExplicitShutdown };
            Theme.Load(app);
#if SELFTEST
            var radio = new Radio(app, request, testMenu, args.Contains("--autostart"), updated);
#else
            var radio = new Radio(app, request, args.Contains("--autostart"), updated);
#endif
            app.Dispatcher.BeginInvoke(new Action(radio.Start));
            app.Run();
        }
    }
}
