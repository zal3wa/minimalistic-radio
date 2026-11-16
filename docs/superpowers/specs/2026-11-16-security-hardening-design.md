# Security hardening (Windows 2.7.2, Linux beta 8, macOS beta 4)

## Why

The owner asked whether a shared-station link, or anything else from outside, could harm someone's computer through
the radio. A read-only review of all three apps found no way to run code. Every address from outside must be http or
https, nothing is added before "Add and play", outside texts are shown as plain text, and nothing calls a shell.
The review did find weaker spots. This change fixes all of them. The owner approved every item, including signing
the Windows updates with a new key stored as the GitHub secret `UPDATE_SIGNING_KEY`.

Goals: the same protections on all three systems, with the same limits. Non-goals: no new features and no visible
changes, except the error shown when an update can't be verified. Anti-goals: no legitimate station may stop playing,
the app must not get bigger in any way people would notice, and nothing about the network or the user may be logged.

## 1. Signed updates

**Windows.** The release job signs every release exe with the ECDSA P-256 key in the GitHub secret
`UPDATE_SIGNING_KEY` (PKCS#8 PEM).
- The signed message is the UTF-8 text `Minimalistic Radio for Windows <version> <sha256>`:
  - `<version>` is the release version as `x.y.z`, e.g. `2.7.2`;
  - `<sha256>` is the lowercase hex SHA-256 of the exe;
  - single spaces between the parts and no trailing newline.
- The signature is the 64-byte IEEE P1363 form (r‖s), which is what .NET's `ECDsa.SignData` gives. It is published
  base64-encoded as the release asset `Minimalistic-Radio.exe.sig`.
- The app embeds the public key. Its PEM, the single source of truth, is in
  `.github/update-signing.pub.pem`:

  ```
  -----BEGIN PUBLIC KEY-----
  MFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAEr+RjoGb4ysfxC2MStP94N1Fld0i9
  wKrcUa56O7L857+btlGlpDtcHDECQECZKjTVq8H3titw7jCYHdrLTmCEGg==
  -----END PUBLIC KEY-----
  ```
- Before it installs anything, the app downloads the exe and the `.sig` and computes the SHA-256 itself. It installs
  only when the signature verifies against the embedded key, for this exact version and hash.
- Fail closed. A missing, damaged or wrong signature means no install. The app then shows the message
  "This update could not be verified. Download it from the release page." and offers the release page. The GitHub
  digest, when present, is still compared as well.
- Right before `Install` swaps the files, the app hashes and verifies the downloaded file once more.
- The release job fails, and publishes nothing, when the secret is missing, when the secret's public key differs
  from `.github/update-signing.pub.pem`, or when the signature does not verify. That last check runs the built app's
  own verification code: Windows PowerShell 5.1 loads the exe and calls the method through reflection.
- `workflow_dispatch` with `dry_run` builds, signs and verifies exactly as a release would, then uploads the exe and
  the `.sig` as an artifact and publishes nothing.
- Older versions (2.7.1 and before) don't know about the signature. They still update to 2.7.2 through the GitHub
  digest, as today.

**macOS.** Zip updates are already verified against the running app's designated requirement, which pins the
certificate. The disk-image path, used when the app can't replace itself, must verify too:
- mount the downloaded DMG read-only and hidden (`hdiutil attach -nobrowse -readonly -noautoopen` with a private
  mount point);
- check the app inside with the same `signedLikeThisApp` check, including the release tag;
- only then open the mounted volume in Finder;
- when the check fails, detach the DMG, delete it and open the release page.

**Both.** The release page URL (`html_url`) and the download URLs from the GitHub API are used only when they are
https on `github.com` and the page is under `https://github.com/zal3wa/minimalistic-radio/`. Otherwise the app falls
back to the constant project page.

**Linux.** Nothing to change: Flatpak's repository is GPG-signed and the app downloads no code.

## 2. Pictures can't exhaust memory (all three)

Every downloaded picture (station logos, radio-browser favicons, share-link logos, song covers, ICY artwork) has its
declared width and height read from the file header before it is decoded. A picture wider or taller than 4096 pixels
is refused as if it had failed to load, and the placeholder is shown. This applies to every decode path that sees
outside bytes, including cover files read back from the cache.
- Windows: read the dimensions with the WIC/WPF frame metadata, without decoding the pixels.
- macOS: read them with `CGImageSourceCopyPropertiesAtIndex`.
- Linux: read them with a header parser for PNG, JPEG, GIF, WebP, BMP and ICO, or with `GdkPixbuf.PixbufLoader`'s
  `size-prepared` signal. A format whose dimensions can't be read is refused.

The byte limits that exist today stay.

## 3. No picture requests to the local network (all three)

Pictures are never fetched from these hosts:
- `localhost`, and names ending in `.localhost`, `.local`, `.lan`, `.home`, `.internal` or `.home.arpa`;
- any host that resolves to a loopback, private, link-local, carrier-grade NAT, multicast, unspecified or reserved
  address:
  - IPv4 0/8, 10/8, 100.64/10, 127/8, 169.254/16, 172.16/12, 192.0.0/24, 192.168/16, 198.18/15, 224/4 and 240/4;
  - IPv6 ::, ::1, fc00::/7 and fe80::/10, plus IPv4-mapped forms of the IPv4 ranges.

The check covers the first address and every redirect hop (at most 5). A refused picture behaves like a failed one.
Streams are not affected: a station on the home network still plays.

## 4. A flood of song titles can't slow the radio down (all three)

- Title changes from a stream are applied at most once every 5 seconds. The first title after starting a station is
  applied at once. When several titles arrive within 5 seconds, the newest one is applied when the 5 seconds have
  passed, so the shown title is never stale.
- Everything that follows a title (history, statistics, covers, notifications, Now Playing) sees only applied titles.
- The statistics keep at most 100 000 song plays; when there are more, the oldest are dropped.
- The song history keeps its current limit (100 where there is none yet).
- Windows: the chunked-transfer size line is capped at 1024 bytes; a longer line ends the stream with an error, like
  any broken stream.
- Linux: every download (pictures, covers, JSON) gets an overall deadline of 30 seconds, not only a per-read timeout.

## 5. Small items

**Names (all three).** Names from every source get the same cleanup that share links use today: share links,
radio-browser, the manual form, import, and the station file on load.
- Remove control characters and the bidirectional formatting characters U+061C, U+200E, U+200F, U+202A–U+202E and
  U+2066–U+2069.
- Keep the zero-width joiners and the variation selectors, so emoji still work.
- Trim, and cut to 100 characters.
- Song titles get the same character cleanup and keep their 240-character limit.

**Linux.**
- `<` and `>` in notification texts become `‹` and `›`.
- The tray tooltip title is escaped the way its body already is.
- urllib follows redirects only to http/https.
- The iTunes artwork address must be http/https.

**Windows.**
- `--open` is honoured only as the last argument and only with a value starting with `minimalistic-radio:`.
- The SELFTEST build must not register the protocol handler. Fix the code or the comment at
  `WindowsIntegration.cs:105` so the two agree; the build must not register it.

**macOS.**
- Hardened runtime on: `ENABLE_HARDENED_RUNTIME: YES` and `codesign --options runtime` in CI. No entitlements are
  added unless a test proves one is needed.
- Covers are decoded through the same size-limited decoder as logos, and `downloadCover` accepts only http/https.

**Logo cache (macOS, Linux).** Logo cache files are pruned the way covers already are.

## Releases

- Windows: version `2.7.2`, tag `v2.7.2`.
- Linux: `linux-v1.0.0-beta.8`.
- macOS: the next beta tag.

Each tag message lists the fixes in plain words. Tags are pushed only after the owner's final OK.

## Left to the builder

Names of helpers and files, how the tests are written, and the exact error-message wording on macOS (it follows the
Windows message above). Each app keeps its existing structure, style and test approach. New user-facing strings go
into every language catalog, written natively for each language, not translated word for word.
