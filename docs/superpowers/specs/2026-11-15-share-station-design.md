# Share a station — design

Approved by the owner on 2026-11-15 ("o to mi właśnie chodziło"). The pictures are the source of truth for the look:
the "Udostępnianie stacji" section of the top bar canvas, https://claude.ai/artifact/NFX2ooYExjbBGHosDHH6Uo
(owner-only link; read it with the Artifact tool, files `project/ShareWeb.dc.html`, `project/Windows.dc.html`,
`project/Linux.dc.html`, `project/Mac.dc.html`, props `overlay` = menu / copied and `page` = shared).

## Why

The owner and a few friends swap stations by hand today (Export/Import of a whole list, or typing a stream address).
A link that you paste into Messenger or an e-mail, and that adds the station to your friend's radio with one click,
is the whole feature. It must feel safe: nothing is added or played without the person agreeing, the link carries
nothing about the sender, and the page behind it is on a GitHub address.

## The flow

1. **Sending.** A station's ⋯ menu gets **Share** between Edit and Remove (Windows and macOS keep their separator
   before Remove). Share copies the link to the clipboard and shows **"Link copied"** for about two seconds:
   - Windows: a small card centred above the player (card colours, 1 px card border, a green circle with a tick).
   - macOS: a pill above the player (menu colours, a green circle with a tick).
   - Linux: an `Adw.Toast` ("Link copied", no icon).
2. **The page.** The link opens `https://minimalistic-radio.github.io/#…` (a static page, see below). It shows the
   station's logo and name, an **Open in Minimalistic Radio** button and, below, **Download from GitHub** for people
   who don't have the radio. On a phone the radio can't run, so the page says so and offers **Copy link** instead.
3. **The radio.** "Open in Minimalistic Radio" opens `minimalistic-radio://add?…`. The radio (started if it isn't
   running) opens its panel/window on a new subpage **Shared station**: ← / ‹ and the title in the bar (Linux also ✕),
   a card with the 72 px logo, the name, the stream address in small grey text, the question
   **"Add it to your stations and play it now?"**, a primary **Add and play** button and **Cancel**. No player on this
   page, like the other subpages.
   - **Add and play** appends the station at the end of the list, plays it and returns to the stations page.
   - **Cancel**, ← and Esc return to the stations page and change nothing.
   - **Already on the list** (same stream address, see Matching): no question; the radio plays that station and shows
     the stations page.
   - **Invalid link**: the Shared station page shows only "This link doesn't contain a station." and ←.

## The link

- Web link: `https://minimalistic-radio.github.io/#` + a form-encoded query string (`application/x-www-form-urlencoded`,
  as `URLSearchParams` writes it; spaces become `+`).
- App link: `minimalistic-radio://add?` + the same query string.
- Keys: `n` = station name (required), `u` = stream address (required), `l` = logo address (optional, only when the
  station has one). Unknown keys are ignored, so later versions can add keys.
- Example: `https://minimalistic-radio.github.io/#n=Antyradio+Hard&u=https%3A%2F%2Fan05.cdn.eurozet.pl%2FANTHAR.mp3`
- The part after `#` never reaches a server, so GitHub doesn't see which station was shared.
- **Pasting also works:** the add-station field (+ Station search box / address field) accepts a pasted web link or
  app link and opens the Shared station page for it. This covers browsers or systems where the app link doesn't open.

## Validation (the same in the apps and on the page)

- `u`: an absolute `http` or `https` address, at most 2048 characters. Anything else → invalid link.
- `n`: trimmed, control characters removed, cut to 100 characters; empty → invalid link.
- `l`: kept only if it is an absolute `https` address of at most 2048 characters; otherwise dropped silently.
- The app never plays or adds anything from a link without the Add and play click, except the already-on-the-list
  case, which only plays a station the person added themselves.

## Matching ("already on the list")

Same stream address after trimming, comparing the scheme and host case-insensitively and the rest exactly, and
ignoring one trailing `/`. Each app has (or gets) one helper for this, with unit tests.

## Opening the app from a link, per system

- **Windows.** At every start, write the per-user URL handler (no admin rights, `HKCU\Software\Classes\minimalistic-radio`):
  default value `URL:Minimalistic Radio`, an empty `URL Protocol` value, `DefaultIcon` = the exe, and
  `shell\open\command` = `"<exe path>" --open "%1"`. Rewrite it only when it differs (the exe may have moved).
  A second instance started with `--open <link>` hands the link to the running one (today it only signals
  "open the panel" through an `EventWaitHandle`; add a channel that carries text, limited to the same user session,
  e.g. a named pipe or `WM_COPYDATA`) and exits. A first instance started with `--open` starts normally and then shows
  the page. The test build must not register the handler (it would point links at `out-test`).
- **macOS.** `CFBundleURLTypes` with the scheme `minimalistic-radio` in Info.plist; handle it in the app delegate
  (`application(_:open:)`), opening the panel on the Shared station page.
- **Linux.** The desktop file gets `MimeType=x-scheme-handler/minimalistic-radio;` and `Exec=… %u`; the existing
  `HANDLES_COMMAND_LINE` handler receives the link from a second launch over D-Bus. Works the same in Flatpak (the
  desktop file is exported) and Snap.

## The page

- Its own repository, `minimalistic-radio/minimalistic-radio.github.io` (the owner's new organization), served by
  GitHub Pages at the root. The main repository stays at `zal3wa/minimalistic-radio`: moving it would break the
  Flatpak remote `zal3wa.github.io/minimalistic-radio`, because Pages addresses are not redirected.
- One static `index.html` plus the app icon; no build step, no scripts or fonts from other servers, no analytics,
  no cookies. The only outside request is the station's own logo (`l`).
- Looks like the canvas: light and dark by `prefers-color-scheme`; desktop (centred 440 px column) and phone layouts.
- Texts in English plus the radio's languages (cs, de, es, fr, it, pl, pt, uk), chosen from `navigator.languages`.
- Phone = `navigator.userAgentData.mobile`, or a phone/tablet user agent where that isn't available.
- **Open in Minimalistic Radio** is a plain link to the app link. **Download from GitHub** goes to
  `https://github.com/zal3wa/minimalistic-radio`. **Copy link** copies the page's own address.
- No `#` or an invalid one: the page shows the radio's name, one line about it and Download from GitHub.
- Open Graph tags for chat previews are static (the `#` part isn't visible to chat apps): title
  "A radio station for you", description "Open it in Minimalistic Radio, a tiny free radio for Windows, macOS and
  Linux.", image = the app icon.

## Texts (English source; all eight catalogues on every system)

Share · Link copied · Shared station · Add it to your stations and play it now? · Add and play · Cancel (existing) ·
This link doesn't contain a station.

## Out of scope (for now)

The macOS system Share menu (AirDrop, Messages) instead of copying — the owner may want it later; sharing from Song
history; sharing several stations at once; listening on the page itself.

## Tests

- Unit tests for building and parsing links (round trip, `+` and `%20`, missing keys, bad `u`, long `n`, bad `l`,
  unknown keys) and for matching, on every system.
- The self-test / integration tests open a shared link into a running app: the page appears, Add and play adds and
  plays, Cancel changes nothing, a known station just plays, an invalid link shows the message.
- Screenshot modes get the Shared station page (light and dark) and the Share menu.

## Releases

Nothing ships until all three systems and the page are done. The page goes live first, so the apps never hand out
links that don't open. Then, with the owner's OK: Windows 2.7.0, linux-v1.0.0-beta.7, macOS beta 3.
