# Linux beta test checklist

Thank you for testing. You need one Linux computer, about 30 minutes, and a few stations. Pick the row that matches your system, install the radio as shown, then go through the checks. Tick what works and note what does not.

| System | Install | Notes |
| --- | --- | --- |
| Ubuntu (24.04 or newer) | the `.snap` from the newest `linux-v...` [release](https://github.com/zal3wa/minimalistic-radio/releases): `sudo snap install --dangerous ./minimalistic-radio_*.snap` (or open it in App Center) | The Snap plays MP3, AAC, Ogg/Opus, FLAC and HLS. Rare formats such as WMA play only in the Flatpak. |
| Fedora Workstation (GNOME) | the `.flatpak` from the same release, opened in GNOME Software | GNOME shows no tray icon by default. Check that the window, the media keys and the clock-menu player still work. |
| Fedora KDE or Kubuntu | the `.flatpak`, opened in Discover | KDE has a tray. |
| Linux Mint (Cinnamon) | the `.flatpak`, opened in Software Manager | Cinnamon has a tray too. |

If a double click does nothing, run `flatpak install --user ./minimalistic-radio.flatpak` in a terminal.

## Checks

Do each on your system. Write "ok", "broken" or "not applicable".

1. Install: the app appears in the application menu with its icon, and starts.
2. Tray icon and menu: the icon shows next to the clock (not on GNOME without an extension); the menu lists your stations and the other items.
3. Left click on the icon opens the player.
4. Scroll volume: mouse wheel up on the tray icon makes it louder, wheel down quieter. Check the direction on every desktop you have.
5. Media keys (play/pause, next, previous) work, and the player in the clock menu (GNOME) or the media widget (KDE) shows the station and controls it.
6. Station change: a notification shows the new station and the song when you change station.
7. KDE: after you change the station, the station submenus in the tray menu refresh and show the right current station.
8. AAC+ station: add Polskie Radio Czworka AAC+ (search for it). It sounds stereo and full, not thin or mono.
9. HLS: play Polskie Radio Czworka (the HLS stream, listed as HLS in the search). It starts and keeps playing for a few minutes.
10. Sleep timer: set one for 1 minute; the music stops and the radio does not start again by itself.
11. Autostart: turn on "Start with the system", log out and in again: the radio is running.
12. Idle suspend: set automatic suspend to the shortest delay (on GNOME: Settings, Power, Automatic Suspend). Play a station and do not touch the computer for longer than that delay: it must not suspend while playing. After you stop the music it may suspend again. (Closing the lid always suspends, with any app: that is not a failure.)
13. Wi-Fi: turn Wi-Fi off for a few seconds and on again. The radio reconnects by itself.
14. Mixer name: open the sound settings while playing. The stream is named "Minimalistic Radio" (not "python" or an ID).
15. Language: change the language in Settings (for example to Polish and back). Texts change at once or after a restart, and nothing is cut off.
16. Windows export and Linux import: on Windows, export your stations (Settings, Export). Copy the file to the Linux computer and import it (Settings, Import). All stations, with their logos, appear.
17. KDE only: there is one tray entry, not two (a known Plasma 6.7 bug can show a duplicate).
18. Resume: while a station plays, close the lid (or choose Suspend), wait a minute, and wake the computer. The radio reconnects by itself within a few seconds. This one matters most in the Flatpak.
19. No tray (GNOME without a tray extension, for example Fedora): close the window while a station plays. The radio keeps playing, and the first time a notification says so. The radio is listed under Background Apps in the menu at the top right, and quitting it there stops it.
20. Second launch: with the radio running and its window closed, start it again from the application menu. The same window comes back, and no second radio starts (only one tray icon, only one stream in the sound settings).
21. Copy the song from the tray: while a song title shows, click it in the tray menu. The window opens; paste somewhere: you get the title. On Wayland the window may say "Press Copy to copy the song" instead: press Copy, then paste. Report it if the window says "Copied" but the paste is wrong or empty.
22. MP3 and Ogg/Opus: in the search, add one station listed as MP3 and one listed as OGG or OPUS. Both play, with song titles if the station sends them.

## How to report

Open a [new GitHub issue](https://github.com/zal3wa/minimalistic-radio/issues/new) and write:

- your system and desktop (for example "Fedora 43 KDE, Wayland"), and Flatpak or Snap,
- the number of the check that failed and what you saw instead,
- a screenshot if it helps. A screenshot of the tray menu on your desktop is welcome too: it will go into the README.

If everything worked, a short "all ok on <your system>" is just as useful.
