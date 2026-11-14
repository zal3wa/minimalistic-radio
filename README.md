# Minimalistic Radio — only 185 KB

Małe radio internetowe dla Windows 10 i 11, które mieszka obok zegara. Jeden plik `.exe`, bez instalatora i bez dodatkowych bibliotek.

*A tiny internet radio for Windows 10/11 that lives in the notification area. One exe, no installer, nothing else to install. English UI included.*

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/screenshots/stations-dark.png">
    <img src="docs/screenshots/stations-light.png" width="380" alt="Minimalistic Radio: station list, now playing with cover art, volume">
  </picture>
</p>

<table>
  <tr>
    <td align="center">
      <picture>
        <source media="(prefers-color-scheme: dark)" srcset="docs/screenshots/history-dark.png">
        <img src="docs/screenshots/history-light.png" width="270" alt="Song history">
      </picture>
      <br>Historia utworów · <i>Song history</i>
    </td>
    <td align="center">
      <picture>
        <source media="(prefers-color-scheme: dark)" srcset="docs/screenshots/settings-dark.png">
        <img src="docs/screenshots/settings-light.png" width="270" alt="Settings">
      </picture>
      <br>Ustawienia · <i>Settings</i>
    </td>
    <td align="center">
      <picture>
        <source media="(prefers-color-scheme: dark)" srcset="docs/screenshots/menu-dark.png">
        <img src="docs/screenshots/menu-light.png" width="270" alt="Tray menu">
      </picture>
      <br>Menu obok zegara · <i>Tray menu</i>
    </td>
  </tr>
</table>

## Co potrafi

- **Ikona obok zegara**: kliknięcie otwiera panel w rogu ekranu (jak systemowe okienka Windows 11), prawy przycisk — szybkie menu.
- **Twoje stacje** z logo; wyszukiwarka w katalogu [radio-browser.info](https://www.radio-browser.info) albo dodawanie z adresu; zmiana kolejności, eksport i import listy (np. dla znajomych).
- **Win+A, klawisze multimedialne, ekran blokady**: tytuł, wykonawca i okładka utworu (albo logo stacji), poprzednia/następna stacja.
- **Historia utworów** z kopiowaniem i wyszukiwaniem w Spotify lub YouTube.
- **Wyłącznik czasowy** (15–90 min, z łagodnym wyciszeniem na koniec).
- **Samo się wznawia** po zerwaniu internetu i po wybudzeniu komputera.
- **Uruchamianie z Windows** (opcjonalnie), **polski i angielski** (jak w Windows albo do wyboru), jasny i ciemny motyw.
- **Aktualizacje** jak w ShareX: najwyżej raz dziennie sprawdza, czy jest nowa wersja, informuje o niej raz i instaluje dopiero na życzenie.

## Pobieranie

Najnowsza wersja: **[Releases → Minimalistic-Radio.exe](https://github.com/zal3wa/minimalistic-radio/releases/latest)**. Wystarczy uruchomić.
Plik nie jest podpisany cyfrowo, więc Windows SmartScreen może zapytać: *Więcej informacji → Uruchom mimo to*.

## Jak to działa

- Interfejs: WPF na **.NET Framework 4.8**, który jest częścią każdego Windows 10 i 11 — dlatego plik jest tak mały.
- Dźwięk MP3 i AAC (w tym HE-AAC/AAC+) dekoduje **sam Windows** (Media Foundation). Dla innych formatów (Ogg/Opus, FLAC, HLS) radio jednorazowo pobiera [FFmpeg](https://ffmpeg.org) (kompilacja [gyan.dev](https://www.gyan.dev/ffmpeg/builds/), sprawdzana sumą SHA-256). W ustawieniach można wybrać: automatycznie / tylko Windows / zawsze FFmpeg.
- Odtwarzacz na pasku zadań Windows 11 jest możliwy przez darmowy [Windhawk](https://windhawk.net) i mod [Taskbar Fluent Media Player](https://windhawk.net/mods/taskbar-fluent-media-player) — szczegóły w ustawieniach radia. Samo radio niczego w systemie nie modyfikuje.

## Prywatność

Radio nie zbiera żadnych danych. Łączy się tylko z:
- serwerami stacji, których słuchasz,
- `radio-browser.info` — gdy wyszukujesz stacje,
- `itunes.apple.com` — wyszukiwanie okładki po wykonawcy i tytule granego utworu,
- `api.github.com` — sprawdzanie aktualizacji (raz dziennie, można wyłączyć),
- `github.com` — pobieranie FFmpeg lub nowej wersji, tylko gdy są potrzebne,
- `stream.radio357.pl` — tytuły utworów Radia 357.

Ustawienia, lista stacji i historia są w `%LOCALAPPDATA%\Minimalistic Radio`.

## Budowanie

Potrzebne: [.NET SDK](https://dotnet.microsoft.com/download) 8 lub nowszy i Windows 10/11 SDK (instalowany z Visual Studio albo [osobno](https://developer.microsoft.com/windows/downloads/windows-sdk/)).

```
dotnet build src/MinimalisticRadio.csproj -c Release -o out
```

`out\Minimalistic Radio.exe --test-menu` uruchamia autotest (kod wyjścia 0 = OK), a `--test-menu --screenshot` tworzy zrzuty do tego README w `%TEMP%\MinimalisticRadio-shot-*.png`. Wypchnięcie tagu `v*` buduje i publikuje wydanie przez GitHub Actions.

## Licencja

[MIT](LICENSE). Ikony: [Lucide](https://lucide.dev) (ISC, zob. `src/Assets/Lucide_Icons_license.txt`).

## Struktura

```
src/
  Program.cs            start, jedna kopia programu
  Radio/                ikona obok zegara, menu, odtwarzanie (RadioApp) i panel (RadioPanel)
  Audio/                połączenie ze stacją, dekodowanie przez Windows, FFmpeg jako zapas
  Services/             okładki, aktualizacje, zapis ustawień, integracja z Windows, język
  Theme/                kolory i wygląd kontrolek (Windows 11)
  Assets/               ikona i licencja ikon
```
