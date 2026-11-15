# Minimalistic Radio for macOS: test checklist

For testing a beta on a Mac. Write down what you see next to each step (OK, or what went wrong), and the macOS version: Apple menu  → About This Mac.

## Risk checks (betas 1–3)

The first betas have only the menu next to the clock (a click or a right click on the icon opens it), no window yet. They check the things the rest of the app depends on.

1. **Installing.** Download the DMG from the release page and open it. Drag Minimalistic Radio to Applications, then open it from Applications.
   - macOS says it can't check the app: click Done. Open System Settings → Privacy & Security, scroll down to "Minimalistic Radio was blocked…", click **Open Anyway**, and confirm with your password.
   - Expected: the radio's icon appears in the menu bar, next to the clock. No icon in the Dock.
2. **Your stations and song titles.** On Windows: Settings → Station list → Export…, and copy the file to the Mac. On the Mac: the radio's menu → **Import…**, and choose the file.
   - Play Antyradio Hard, then KIIS FM, Radio 357 and an RMF station (menu → Station).
   - Expected: each one plays, and after a short while the song's title shows in the menu (under the station's name). Note any station whose title never shows.
3. **Keys and Control Center.** While a station plays:
   - the ⏯ key on the keyboard stops and starts it;
   - squeezing an AirPods stem (or tapping it) does the same;
   - Control Center (the switches icon in the menu bar) → Now Playing shows the song and the station; ⏭ and ⏮ switch stations.
4. **Open at login.** Menu → **Open at login** (it gets a check mark). If macOS asks to allow it, allow it. Log out and back in.
   - Expected: the icon is back next to the clock, and nothing plays by itself.
5. **Shortcuts and Siri.** Open the Shortcuts app and search for "Minimalistic Radio".
   - Expected: actions such as Play, Play Station, Stop, Next Station and Set Volume are listed. Try one.
   - On macOS 26: open Spotlight (⌘ Space) and type "Play Minimalistic Radio".
   - If you use Siri in English: "Play Minimalistic Radio".
6. **The first update (when beta 2 is out).** Keep beta 1 running. Within a few hours (or at once after quitting and opening it again), the menu shows **Update**. Click it.
   - Note exactly what macOS asks, if anything (a permission, your password).
   - Expected: the radio restarts by itself, playing the same station if it was playing.
7. **The second update (when beta 3 is out).** Update again the same way.
   - Expected: nothing is asked this time.

## Results

| Step | macOS version, date | Result |
|------|---------------------|--------|
| 1 | | |
| 2 | | |
| 3 | | |
| 4 | | |
| 5 | | |
| 6 | | |
| 7 | | |
