# Linux beta test checklist

Thank you for testing. You need one Linux computer, about 30 minutes, and a few stations. Install the radio once, as below, then go through the checks. Tick what works and note what does not.

**Install:** open [minimalistic-radio.flatpakref](https://zal3wa.github.io/minimalistic-radio/minimalistic-radio.flatpakref) and click Install in GNOME Software, Discover or your software manager. If the link does not open there, run this in a terminal:

```
flatpak install https://zal3wa.github.io/minimalistic-radio/minimalistic-radio.flatpakref
```

You install it once: every later beta arrives as an update.

| System | Notes |
| --- | --- |
| Ubuntu (24.04 or newer) | Enable Flatpak first: [flathub.org/setup/Ubuntu](https://flathub.org/setup/Ubuntu). The `.snap` on the [releases page](https://github.com/zal3wa/minimalistic-radio/releases) is for testing the Snap only (`sudo snap install --dangerous ./minimalistic-radio_*.snap`): it does not update, and it plays MP3, AAC, Ogg/Opus, FLAC and HLS but not rare formats such as WMA. |
| Fedora Workstation (GNOME) | GNOME shows no tray icon by default. Check that the window, the media keys and the clock-menu player still work. |
| Fedora KDE or Kubuntu | KDE has a tray. |
| Linux Mint (Cinnamon) | Cinnamon has a tray too. |

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
23. Update: when the next beta is out (it shows on the [releases page](https://github.com/zal3wa/minimalistic-radio/releases)), it arrives as an update without a new download: the radio shows a green arrow, or GNOME Software or Discover lists it under Updates. Install it there (or run `flatpak update`), restart the radio, and check that your stations and settings are still there.
24. Close button: the window's bar has only a close button on the right (no minimize or maximize, whatever your desktop's button layout). It hides the window and the radio keeps playing; the first time, a notification says so, also when there is a tray icon.
25. Statistics: play two stations for a few minutes each, then open Settings and press Show next to Statistics. The listening time and the stations appear, and for a station that sends song titles, the artists. All, Year and Month switch the period. Quit and start the radio again: the numbers are still there. "Clear statistics" asks first, then empties the page; the song history stays.

## How to report

Open a [new GitHub issue](https://github.com/zal3wa/minimalistic-radio/issues/new) and write:

- your system and desktop (for example "Fedora 43 KDE, Wayland"), and Flatpak or Snap,
- the number of the check that failed and what you saw instead,
- a screenshot if it helps.

If everything worked, a short "all ok on <your system>" is just as useful.
