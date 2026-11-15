<p align="center"><img src="docs/icon.png" width="96" alt="Minimalistic Radio icon"></p>

<h1 align="center">Minimalistic Radio - only 219 KB</h1>

<p align="center">A tiny open-source internet radio for Windows 10 and 11 that lives next to the clock.<br>One <code>.exe</code>, no installer, nothing else to install. <a href="#linux">Also for Linux.</a></p>

<p align="center">
  <a href="https://github.com/zal3wa/minimalistic-radio/releases/latest/download/Minimalistic-Radio.exe"><img src="docs/download-windows.svg" height="56" alt="Download for Windows"></a>
  <a href="#linux"><img src="docs/download-linux.svg" height="56" alt="Download for Linux"></a>
</p>

<p align="center"><sub>Not signed yet: if Windows SmartScreen asks, choose <i>More info</i> → <i>Run anyway</i>.</sub></p>

<table align="center">
  <tr>
    <td align="center" valign="top">
      <a href="docs/screenshots/README.md#right-click-the-menu"><picture>
        <source media="(prefers-color-scheme: dark)" srcset="docs/screenshots/tray-menu-dark.png">
        <img src="docs/screenshots/tray-menu-light.png" width="454" alt="Right click on the tray icon opens the menu">
      </picture></a>
      <br><b>Right click</b> on the icon: the menu
    </td>
    <td align="center" valign="top">
      <a href="docs/screenshots/README.md#left-click-the-player"><picture>
        <source media="(prefers-color-scheme: dark)" srcset="docs/screenshots/tray-panel-dark.png">
        <img src="docs/screenshots/tray-panel-light.png" width="346" alt="Left click on the tray icon opens the player">
      </picture></a>
      <br><b>Left click</b>: the player
    </td>
  </tr>
</table>

<table align="center">
  <tr>
    <td align="center" valign="top">
      <a href="docs/screenshots/README.md#station-search"><picture>
        <source media="(prefers-color-scheme: dark)" srcset="docs/screenshots/search-dark.png">
        <img src="docs/screenshots/search-light.png" width="400" alt="Station search with logos, country, codec and bitrate">
      </picture></a>
      <br>Station search: thousands of stations from radio-browser.info
    </td>
    <td align="center" valign="top">
      <a href="docs/screenshots/README.md#song-history"><picture>
        <source media="(prefers-color-scheme: dark)" srcset="docs/screenshots/history-dark.png">
        <img src="docs/screenshots/history-light.png" width="400" alt="Song history">
      </picture></a>
      <br>Song history
    </td>
  </tr>
  <tr>
    <td align="center" valign="top">
      <a href="docs/screenshots/README.md#settings"><picture>
        <source media="(prefers-color-scheme: dark)" srcset="docs/screenshots/settings-dark.png">
        <img src="docs/screenshots/settings-light.png" width="400" alt="Settings">
      </picture></a>
      <br>Settings
    </td>
    <td align="center" valign="middle">
      <a href="docs/screenshots/README.md#station-change-card"><picture>
        <source media="(prefers-color-scheme: dark)" srcset="docs/screenshots/card-dark.png">
        <img src="docs/screenshots/card-light.png" width="400" alt="Station change card">
      </picture></a>
      <br>Station change card (media keys)
    </td>
  </tr>
</table>

## Linux

The same radio for Linux, made with GTK and libadwaita: a tray icon (where the desktop has one), media keys, the sleep timer, station search, song history and the Windows station list (export it there, import it here). It runs as a Flatpak or a Snap.

<!-- When Flathub is live, remove these comment marks:
<a href="https://flathub.org/apps/io.github.zal3wa.minimalistic-radio"><img src="https://flathub.org/api/badge?locale=en" height="56" alt="Get it on Flathub"></a>
-->
<!-- When the Snap Store page is live, remove these comment marks:
<a href="https://snapcraft.io/minimalistic-radio"><img src="https://snapcraft.io/static/images/badges/en/snap-store-black.svg" height="56" alt="Get it from the Snap Store"></a>
-->

Until the stores are live: open the [releases page](https://github.com/zal3wa/minimalistic-radio/releases) and take the `.flatpak` or the `.snap` from the newest `linux-v...` release. Double-click it to open it in GNOME Software, Discover or App Center. For the `.snap` you can also run `sudo snap install --dangerous ./minimalistic-radio_*.snap`.

The Flatpak plays every format. The Snap is smaller (0.7 MB) and plays MP3, AAC and HE-AAC, Ogg/Opus and FLAC, including HLS streams; rare formats such as WMA play only in the Flatpak.

Linux beta testers are welcome: see the [test checklist](docs/LINUX-TEST-CHECKLIST.md).

<table align="center">
  <tr>
    <td align="center" valign="top">
      <picture>
        <source media="(prefers-color-scheme: dark)" srcset="docs/screenshots/linux-stations-dark.png">
        <img src="docs/screenshots/linux-stations-light.png" width="400" alt="The station list on Linux">
      </picture>
      <br>Stations
    </td>
    <td align="center" valign="top">
      <picture>
        <source media="(prefers-color-scheme: dark)" srcset="docs/screenshots/linux-search-dark.png">
        <img src="docs/screenshots/linux-search-light.png" width="400" alt="Station search on Linux">
      </picture>
      <br>Station search
    </td>
  </tr>
  <tr>
    <td align="center" valign="top">
      <picture>
        <source media="(prefers-color-scheme: dark)" srcset="docs/screenshots/linux-history-dark.png">
        <img src="docs/screenshots/linux-history-light.png" width="400" alt="Song history on Linux">
      </picture>
      <br>Song history
    </td>
    <td align="center" valign="top">
      <picture>
        <source media="(prefers-color-scheme: dark)" srcset="docs/screenshots/linux-settings-dark.png">
        <img src="docs/screenshots/linux-settings-light.png" width="400" alt="Settings on Linux">
      </picture>
      <br>Settings
    </td>
  </tr>
</table>

<!-- The tray menu is drawn by the desktop, so its picture has to come from a real desktop (a beta tester).
Add it here, with the same light/dark <picture> pattern as above:
docs/screenshots/linux-tray-menu-light.png and linux-tray-menu-dark.png -->

## Languages

English, Polish, German, Ukrainian, Czech, Spanish, French, Italian and Portuguese (Settings → Language). Native speakers: if a translation sounds wrong, please fix it in [`src/Lang/*.po`](src/Lang) (Windows) or [`linux/po/*.po`](linux/po) (Linux) and send a pull request.

Some stations are never shown in search or suggestions; the list is in [`data/banned-stations.json`](data/banned-stations.json).

## Privacy

The radio collects no personal data: no accounts, no telemetry, no ads. It only connects to:
- the servers of the stations you listen to,
- the websites the station logos come from, for your list and for search results,
- `radio-browser.info`: when you open the station search or search for stations, it gets your country code and what you typed,
- `itunes.apple.com`: the artist and title of the song that's playing, to find its cover art ([Apple's privacy policy](https://www.apple.com/legal/privacy/)),
- `api.github.com`: to check for updates, every few hours; can be turned off in Settings → Updates ([GitHub's privacy statement](https://docs.github.com/site-policy/privacy-policies/github-general-privacy-statement)),
- `github.com`: to download a new version, only when there is one,
- `stream.radio357.pl`: song titles, only while Radio 357 is playing.

Nothing else is sent. Like any internet connection, these servers see your IP address.

The Linux version contacts the same servers, except GitHub: it never contacts GitHub for updates. Updates come from Flathub or the Snap Store, through your system's software center (the Flatpak also shows an update arrow, asked of Flatpak itself).

Settings, the station list and the history are stored in `%LOCALAPPDATA%\Minimalistic Radio` on Windows, and in your user folders on Linux (inside the app's own folder for a Flatpak or a Snap).

## Uninstall

**Windows.** 
There's no installer. The radio adds a Start menu shortcut, so Windows shows its name and icon in the media controls, and an entry in Startup apps only if you turn on *Start with Windows*. To remove everything:

1. Settings → turn off *Start with Windows*, then *Quit*.
2. Delete `Minimalistic-Radio.exe`, the folder `%LOCALAPPDATA%\Minimalistic Radio` and the shortcut `%APPDATA%\Microsoft\Windows\Start Menu\Programs\Minimalistic Radio.lnk`.

**Linux.** Remove it in GNOME Software, Discover or App Center. The Flatpak asks whether to delete its data too (settings, station list, history); tick it to remove everything.

## License

[MIT](LICENSE). Icons: [Lucide](https://lucide.dev) (ISC). Building from source: [docs/BUILDING.md](docs/BUILDING.md).
