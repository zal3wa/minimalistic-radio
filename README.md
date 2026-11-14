<p align="center"><img src="docs/icon.png" width="96" alt="Minimalistic Radio icon"></p>

<h1 align="center">Minimalistic Radio - only 197 KB</h1>

<p align="center">A tiny internet radio for Windows 10 and 11 that lives next to the clock.<br>One <code>.exe</code>, no installer, nothing else to install.</p>

<p align="center">
  <a href="https://github.com/zal3wa/minimalistic-radio/releases/latest/download/Minimalistic-Radio.exe"><img src="docs/download-windows.svg" height="56" alt="Download for Windows"></a>
</p>

<p align="center"><sub>Not signed yet: if Windows SmartScreen asks, choose <i>More info</i> → <i>Run anyway</i>.</sub></p>

<table align="center">
  <tr>
    <td align="center" valign="top">
      <picture>
        <source media="(prefers-color-scheme: dark)" srcset="docs/screenshots/stations-dark.png">
        <img src="docs/screenshots/stations-light.png" width="400" alt="Station list, now playing with cover art, volume">
      </picture>
      <br>Stations and now playing
    </td>
    <td align="center" valign="top">
      <picture>
        <source media="(prefers-color-scheme: dark)" srcset="docs/screenshots/history-dark.png">
        <img src="docs/screenshots/history-light.png" width="400" alt="Song history">
      </picture>
      <br>Song history
    </td>
  </tr>
  <tr>
    <td align="center" valign="top">
      <picture>
        <source media="(prefers-color-scheme: dark)" srcset="docs/screenshots/settings-dark.png">
        <img src="docs/screenshots/settings-light.png" width="400" alt="Settings">
      </picture>
      <br>Settings
    </td>
    <td align="center" valign="top">
      <picture>
        <source media="(prefers-color-scheme: dark)" srcset="docs/screenshots/menu-dark.png">
        <img src="docs/screenshots/menu-light.png" width="400" alt="Tray menu">
      </picture>
      <br>Tray menu
    </td>
  </tr>
</table>

## Privacy

The radio collects no data. It only connects to:
- the servers of the stations you listen to,
- `radio-browser.info`: when you search for stations,
- `itunes.apple.com`: to find the cover art of the song that's playing, by artist and title,
- `api.github.com`: to check for updates (every few hours, can be turned off),
- `github.com`: to download FFmpeg or a new version, only when needed,
- `stream.radio357.pl`: song titles of Radio 357.

Settings, the station list and the history are stored in `%LOCALAPPDATA%\Minimalistic Radio`.

## License

[MIT](LICENSE). Icons: [Lucide](https://lucide.dev) (ISC). Building from source: [docs/BUILDING.md](docs/BUILDING.md).
