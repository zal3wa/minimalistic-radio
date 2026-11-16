# Minimalistic Radio for macOS: test checklist

For testing a beta on a Mac. Write down what you see next to each step (OK, or what went wrong), and the macOS version: Apple menu  → About This Mac.

## Risk checks (betas 1–3)

They check the things the rest of the app depends on. Beta 1 has only the menu next to the clock (a click or a right click on the icon opens it); from beta 2 the radio has its window too (a click opens it, a right click the menu).

1. **Installing.** Download the DMG from the release page and open it. Drag Minimalistic Radio to Applications, then open it from Applications.
   - macOS says it can't check the app: click Done. Open System Settings → Privacy & Security, scroll down to "Minimalistic Radio was blocked…", click **Open Anyway**, and confirm with your password.
   - Expected: the radio's icon appears in the menu bar, next to the clock. No icon in the Dock.
2. **Your stations and song titles.** On Windows: Settings → Station list → Export…, and copy the file to the Mac. On the Mac: the radio's menu → **Import…** (from beta 2 on: the window's Settings → Station list → **Import…**), and choose the file.
   - Play Antyradio Hard, then KIIS FM, Radio 357 and an RMF station (menu → Station).
   - Expected: each one plays, and after a short while the song's title shows in the menu (under the station's name). Note any station whose title never shows.
3. **Keys and Control Center.** While a station plays:
   - the ⏯ key on the keyboard stops and starts it;
   - squeezing an AirPods stem (or tapping it) does the same;
   - Control Center (the switches icon in the menu bar) → Now Playing shows the song and the station; ⏭ and ⏮ switch stations.
4. **Open at login.** Menu → **Open at login** (from beta 2 on: the window's Settings → **Open at login**). If macOS asks to allow it, allow it. Log out and back in.
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

## The whole app (beta 2 and later)

A click on the icon opens the window under the icon; a right click opens the menu.

1. **The window.** It opens under the icon and closes on a click elsewhere, on Esc, or on another click on the icon. The station list shows the logos; a click on a station plays it; dragging a station moves it; ⋯ → Edit and Remove work.
2. **Now playing.** The song and its cover show at the bottom; the copy button turns into "Copied" and the song is in the clipboard. The speaker mutes and unmutes; the slider shows its value while dragged; the moon sets the sleep timer, and the radio stops at the end.
3. **AirPlay.** The AirPlay button lists your HomePod, Apple TV or AirPlay speaker, and the radio plays there.
4. **Search.** + Station: Recommended and Popular in your country show at once. Search for a station, add it with +; it shows a check mark afterwards. Add by address works with a stream address.
5. **History and settings.** History (top left) lists the songs with the station's logo, the station and time; ⋯ → Search on Spotify and YouTube open the browser. Settings (the gear): change the language (the window and the menu change at once), Open at login, Export… and Import…, Check now, the GitHub link.
6. **Statistics.** Settings → Statistics → Show, or Statistics in the history's bar (‹ goes back to where you came from). After listening for a while: the time, the stations and (with stations that send song titles) the artists show for this month; All and Year switch the period. ⋯ (top right) → Clear statistics… asks first: Cancel is the blue button, and Return and Esc both cancel; Clear empties the page, and the song history stays. Settings shows "Collected since" with the day you started. Switch Statistics off: the page says they are off, and listening adds nothing until you switch them on again.
7. **The station card.** Switch stations with ⏭ or the menu: a card shows the station under the icon for a moment. Settings → Show station changes off: no card.
8. **Keys.** In the window: Space plays and stops, ⌘F opens the search, ⌘, the settings, ⌘W closes it, ⌘Q quits the radio.
9. **Updating from the disk image (beta 4 and later, when the next version is out).** Open the radio straight from the DMG (not from Applications) and click **Download update**.
   - Expected: after a moment a Finder window shows the new Minimalistic Radio and the card says to quit and drag it to Applications. Dragging it there works, and the new version opens from Applications.
   - Note if no Finder window opens, or if the card says the update couldn't be verified.
10. **Sharing a station (beta 5 and later).** ⋯ → Share on a station ("Link copied" shows), then remove that station. Open the link in the browser and press Open in Minimalistic Radio: the window shows "Shared station" with **+ Add** and a checked **Play automatically** under it.
    - Uncheck it and press Add: the station is added at the end, the list scrolls to it, and whatever was playing keeps playing.
    - Open the link again: the list shows the station with "Already on your list", and nothing starts.
    - Remove the station, open the link, check the box and press Add: the station is added and plays. Opening the link again just plays it.

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
| 8 | | |
| 9 | | |
| 10 | | |
