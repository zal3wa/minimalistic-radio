# Shared station: Add + "Play automatically"; Statistics: "Clear statistics…" in a ⋯ menu

Windows 2.8.0, Linux 1.0.0 beta 9 and macOS 1.0.0 beta 5. The designs are on the canvas
https://claude.ai/artifact/NFX2ooYExjbBGHosDHH6Uo, in the sections "Udostępnianie stacji" (boards "… opened from a
link") and "Propozycja: czyszczenie statystyk". The owner approved both on 2026-11-16.

## Why

1. A shared link used to offer only "Add and play". Someone listening to a programme who opened a link from a friend
   could add the station only by stopping what was playing.
2. "Clear statistics" was a plain link at the bottom of the Statistics page. It looked risky to press, and on Windows
   the question didn't say what would be deleted or that the song history stays.

## 1. The shared-station page

From top to bottom:
- the logo, the name and the address, as today;
- the question **"Add it to your stations?"** (it replaces "Add it to your stations and play it now?");
- the primary button **"+ Add"**: a plus icon and the label "Add";
- under the button, a checkbox **"Play automatically"**, centred, in the system's own checkbox style;
- the button **"Cancel"**.

How it behaves:
- **The checkbox's state.** It is checked the first time. After that it keeps the user's last choice, saved in the
  preferences file with the other preferences when **Add** is pressed. Cancel doesn't save it.
- **Add, checked.** Adds the station at the end of the list and plays it, exactly as "Add and play" did.
- **Add, unchecked.** Adds the station at the end of the list and changes nothing about playback: what was playing
  keeps playing, and nothing starts if nothing was playing. The panel goes back to the station list, scrolled so the
  new station shows.
- **A station already on the list.**
  - With the saved choice checked, the radio plays it without asking, as today.
  - With it unchecked, the panel shows the station list scrolled to that station, plus the existing short message
    "Already on your list". Playback doesn't change.
- **Keyboard.** Enter = Add; Space toggles the checkbox when it has focus; Esc / ← = Cancel. The checkbox is a real,
  focusable checkbox with its label.

## 2. Statistics: "Clear statistics…"

- The "Clear statistics" link or button at the bottom of the Statistics page goes away.
- The Statistics page's header bar gets a **⋯** button at its right end. On Linux it sits left of ✕. Its accessible
  name and tooltip are "More".
- ⋯ opens the system's own menu or popover with one item, **"Clear statistics…"**. The ellipsis says a question
  comes next.
- The question uses the system's own dialog:
  - Windows: a modal dialog inside the panel that dims the page behind it.
  - macOS: an `NSAlert` sheet on the panel.
  - Linux: an `Adw.AlertDialog`.
- What the dialog shows:
  - title **"Clear statistics?"**;
  - body **"Your listening statistics will be permanently deleted. Your song history will remain."**;
  - a second paragraph, on its own line: **"This can't be undone."**;
  - the buttons **"Cancel"** and **"Clear"**.
- **Cancel is the default.** Enter and Esc both cancel. "Clear" is the destructive one:
  - Windows: red text;
  - macOS: `hasDestructiveAction`;
  - Linux: `ADW_RESPONSE_DESTRUCTIVE`.
- **Button order:**
  - Windows: [Clear] [Cancel], with Cancel as the accent button;
  - macOS: Cancel as the default (blue) button, Clear destructive;
  - Linux: [Cancel] [Clear].
- **Clear** deletes the statistics exactly as today. The song history stays.

## 3. Texts (written by the owner for the dialog; use them verbatim)

| | Dialog title | Body | Second paragraph | Cancel | Clear |
|---|---|---|---|---|---|
| en | Clear statistics? | Your listening statistics will be permanently deleted. Your song history will remain. | This can't be undone. | Cancel | Clear |
| pl | Wyczyścić statystyki? | Wszystkie statystyki słuchania zostaną trwale usunięte. Historia utworów pozostanie bez zmian. | Tej operacji nie można cofnąć. | Anuluj | Wyczyść |
| de | Statistiken löschen? | Deine Hörstatistiken werden dauerhaft gelöscht. Dein Titelverlauf bleibt erhalten. | Das lässt sich nicht rückgängig machen. | Abbrechen | Löschen |
| fr | Effacer les statistiques ? | Vos statistiques d'écoute seront définitivement supprimées. Votre historique des titres sera conservé. | Cette action est irréversible. | Annuler | Effacer |
| es | ¿Borrar las estadísticas? | Tus estadísticas de escucha se eliminarán permanentemente. El historial de canciones se conservará. | Esta acción no se puede deshacer. | Cancelar | Borrar |
| it | Cancellare le statistiche? | Le statistiche di ascolto verranno eliminate definitivamente. La cronologia dei brani rimarrà invariata. | Questa operazione non può essere annullata. | Annulla | Cancella |
| pt | Limpar as estatísticas? | As suas estatísticas de audição serão eliminadas permanentemente. O histórico de músicas será mantido. | Esta ação não pode ser anulada. | Cancelar | Limpar |
| cs | Smazat statistiky? | Vaše statistiky poslechu budou trvale smazány. Historie skladeb zůstane zachována. | Tuto akci nelze vrátit zpět. | Zrušit | Smazat |
| uk | Очистити статистику? | Вашу статистику прослуховування буде остаточно видалено. Історія композицій залишиться без змін. | Цю дію неможливо скасувати. | Скасувати | Очистити |

The French title keeps its space before "?". Write it as a no-break space (U+00A0) in the catalogs.

"Cancel" may already be in the catalogs. If its translation there differs from the table, use the table's word only
where the two are the same word; otherwise keep the catalog's established "Cancel". "Clear" (the dialog button) is
a new entry wherever the catalog has no plain "Clear" with this meaning.

These texts aren't from the owner, so they are written natively here (not word for word):

| | Menu item | ⋯ button name | Checkbox | Question on the shared page | Button |
|---|---|---|---|---|---|
| en | Clear statistics… | More | Play automatically | Add it to your stations? | Add |
| pl | Wyczyść statystyki… | Więcej | Odtwarzaj automatycznie | Dodać tę stację do listy? | Dodaj |
| de | Statistiken löschen… | Mehr | Automatisch abspielen | Zu deinen Sendern hinzufügen? | Hinzufügen |
| fr | Effacer les statistiques… | Plus | Lire automatiquement | L’ajouter à vos stations ? | Ajouter |
| es | Borrar las estadísticas… | Más | Reproducir automáticamente | ¿Añadirla a tus emisoras? | Añadir |
| it | Cancella le statistiche… | Altro | Riproduci automaticamente | Aggiungerla alle tue stazioni? | Aggiungi |
| pt | Limpar as estatísticas… | Mais | Reproduzir automaticamente | Adicioná-la às suas estações? | Adicionar |
| cs | Smazat statistiky… | Další | Přehrávat automaticky | Přidat ji mezi vaše stanice? | Přidat |
| uk | Очистити статистику… | Більше | Відтворювати автоматично | Додати її до ваших станцій? | Додати |

If a catalog already has "More" or "Add" for a ⋯ button or an add button elsewhere in the app, reuse that entry (one
msgid, one translation). Remove the catalog entries that are no longer used:
- "Add and play";
- "Add it to your stations and play it now?";
- the old clear-statistics question and its body texts.

## 4. Pictures and versions

- **Pictures.** The README and landing-page pictures come from each app's screenshot mode, never from mockups. Every
  picture that shows the shared-station page or the Statistics page is taken again in light and dark, at 2×, the
  same way as the current ones: `docs/screenshots/` and `docs/screenshots/demo/`. The Statistics picture now shows ⋯
  in the header and no link at the bottom.
- **Versions.**
  - Windows: `<Version>2.8.0</Version>`;
  - Linux: beta 9, the same way beta 8 was done (a metainfo development release entry);
  - macOS: beta 5, which lives in the tag only.

  Nothing is tagged or released until the owner says so.

## Left to the builder

Names of preferences keys, helpers and tests, and the exact pixel spacing (follow the canvas). Each app keeps its
structure, style and test approach.
