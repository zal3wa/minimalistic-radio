"""The Statistics page (from Settings): listening time, songs, stations, top stations and artists, and the hours
of the day, for this month, this year or everything. The counting is in core/statistics.py; the data never leaves
the computer."""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import TYPE_CHECKING, Callable

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk, Pango  # noqa: E402

from ..controller import Change, RadioController  # noqa: E402
from ..core.statistics import (  # noqa: E402
    Period, Summary, count, enough_titles, find_logo, format_count, format_duration, format_hours, period_label,
    plays_text, since_label,
)
from ..i18n import C_, N_  # noqa: E402
from .bars import subpage_bar  # noqa: E402
from .logos import LogoCache, LogoImage  # noqa: E402

if TYPE_CHECKING:
    from .window import RadioWindow

LOGO_SIZE = 32
CHART_HEIGHT = 64


def _label(text: str = "", *classes: str, **props) -> Gtk.Label:
    props.setdefault("xalign", 0)
    return Gtk.Label(label=text, css_classes=list(classes), **props)


def _card(child: Gtk.Widget, *classes: str) -> Gtk.Widget:
    box = Gtk.Box(css_classes=["card", *classes])
    box.append(child)
    return box


class PeriodSwitch(Gtk.Box):
    """All | Year | Month, in equal parts: libadwaita's toggle group where there is one (1.7), else linked buttons."""

    def __init__(self, labels: list[tuple[Period, str]], chosen: Callable[[Period], None]) -> None:
        super().__init__(hexpand=True)
        self._chosen = chosen
        self._setting = False
        self.group = None
        self.buttons: dict[Period, Gtk.ToggleButton] = {}
        if hasattr(Adw, "ToggleGroup"):
            self.group = Adw.ToggleGroup(homogeneous=True, hexpand=True)
            for period, label in labels:
                self.group.add(Adw.Toggle(label=label, name=period.value))
            self.group.connect("notify::active-name", self._group_changed)
            self.append(self.group)
        else:
            box = Gtk.Box(homogeneous=True, hexpand=True, css_classes=["linked"])
            first = None
            for period, label in labels:
                button = Gtk.ToggleButton(label=label, group=first)
                first = first or button
                button.connect("toggled", self._button_toggled, period)
                self.buttons[period] = button
                box.append(button)
            self.append(box)

    def select(self, period: Period) -> None:
        self._setting = True
        try:
            if self.group is not None:
                self.group.set_active_name(period.value)
            else:
                self.buttons[period].set_active(True)
        finally:
            self._setting = False

    def _group_changed(self, group, _param) -> None:
        if not self._setting and group.get_active_name():
            self._chosen(Period(group.get_active_name()))

    def _button_toggled(self, button: Gtk.ToggleButton, period: Period) -> None:
        if not self._setting and button.get_active():
            self._chosen(period)


class StatisticsPage(Adw.NavigationPage):
    def __init__(self, window: RadioWindow, controller: RadioController, logos: LogoCache,
                 _: Callable[[str], str]) -> None:
        super().__init__(tag="statistics", title=_("Statistics"))
        self.window = window
        self.controller = controller
        self.logos = logos
        self._ = _
        self.period = Period.MONTH
        self.summary: Summary | None = None

        self.switch = PeriodSwitch([(Period.ALL, _("All")), (Period.YEAR, _("Year")), (Period.MONTH, _("Month"))],
                                   self._period_chosen)
        self.switch.select(self.period)

        self.off = _label(_("Statistics are off. Nothing new is recorded."), "dim-label", wrap=True,
                          margin_start=4, margin_end=4, visible=not controller.prefs.collect_statistics)
        self.empty = _label(_("Nothing here yet. Listen for a while and come back."), "dim-label", wrap=True,
                            margin_top=12, margin_start=4, margin_end=4)

        # Listening time: the period on the right, the total, the average a day.
        self.period_label = _label("", "caption", "dim-label", xalign=1, ellipsize=Pango.EllipsizeMode.END)
        top = Gtk.Box(spacing=12)
        top.append(_label(_("Listening time"), "caption", "dim-label", hexpand=True))
        top.append(self.period_label)
        self.total_label = _label("", "title-1", "numeric")
        self.per_day_label = _label("", "caption", "dim-label")
        listening = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, hexpand=True,
                            margin_top=14, margin_bottom=14, margin_start=16, margin_end=16)
        for widget in (top, self.total_label, self.per_day_label):
            listening.append(widget)

        # Three tiles: the label at the top, the value at the bottom (in one row even if a label wraps). A value
        # wraps too rather than widen the window ("4 Std. 50 Min." in German, wide fonts).
        tiles = Gtk.Box(spacing=8, homogeneous=True)
        self.tile_values: list[Gtk.Label] = []
        for text in (_("Song titles"), _("Stations"), _("Longest")):
            value = _label("", "title-4", "numeric", valign=Gtk.Align.END, wrap=True)
            tile = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, margin_top=10, margin_bottom=10,
                           margin_start=12, margin_end=12)
            tile.append(_label(text, "caption", "dim-label", wrap=True, vexpand=True, valign=Gtk.Align.START))
            tile.append(value)
            tiles.append(_card(tile, "stat-tile"))
            self.tile_values.append(value)

        self.stations_list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE, css_classes=["boxed-list"])

        self.share_label = _label("", "caption", "dim-label", wrap=True, margin_start=4, margin_end=4)
        self.artists_list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE, css_classes=["boxed-list"])
        self.too_few = _label(_("Not enough song titles yet"), "dim-label", wrap=True, margin_start=4)

        # When you listen: the busiest hour and a bar for each hour of the day.
        self.peak_label = _label("", "caption", "dim-label")
        self.chart = Gtk.Box(spacing=2, homogeneous=True, css_classes=["stat-chart"])
        self.chart.set_size_request(-1, CHART_HEIGHT)
        self.bars: list[Gtk.Box] = []
        for _hour in range(24):
            bar = Gtk.Box(valign=Gtk.Align.END, css_classes=["stat-hour"])
            self.bars.append(bar)
            self.chart.append(bar)
        axis = Gtk.Box(homogeneous=True)
        for index, text in enumerate(("00", "06", "12", "18")):
            cell = Gtk.Box()
            cell.append(_label(text, "caption", "dim-label", hexpand=True))
            if index == 3:
                cell.append(_label("24", "caption", "dim-label", xalign=1))
            axis.append(cell)
        hours = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, hexpand=True,
                        margin_top=14, margin_bottom=10, margin_start=16, margin_end=16)
        for widget in (self.peak_label, self.chart, axis):
            hours.append(widget)

        self.clear_button = Gtk.Button(label=_("Clear statistics"), halign=Gtk.Align.START, css_classes=["link"])
        self.clear_button.connect("clicked", lambda _button: self.ask_to_clear())

        self.data = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.data.append(_card(listening))
        self.data.append(tiles)
        self.data.append(self._section(_("Top stations"), self.stations_list))
        self.data.append(self._section(_("Top artists"), self.share_label, self.artists_list, self.too_few))
        self.data.append(self._section(_("When you listen"), _card(hours)))
        self.data.append(self.clear_button)

        # The empty line or the numbers. Not a Gtk.Stack: one that isn't homogeneous both ways measures a wrapping
        # label at one line, so a long translation of the empty line would widen the window.
        self.data.set_visible(False)
        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, margin_top=12, margin_bottom=16,
                       margin_start=12, margin_end=12)
        for widget in (self.switch, self.off, self.empty, self.data):
            body.append(widget)
        self.scroller = Gtk.ScrolledWindow(child=Adw.Clamp(child=body, maximum_size=600), vexpand=True,
                                           hscrollbar_policy=Gtk.PolicyType.NEVER)
        toolbar = Adw.ToolbarView(content=self.scroller)
        toolbar.add_top_bar(subpage_bar(self.get_title(), _))
        self.set_child(toolbar)
        self.connect("showing", lambda _page: self._opened())
        self.connect("map", lambda _page: self.update())

    @staticmethod
    def _section(title: str, *widgets: Gtk.Widget) -> Gtk.Box:
        """A heading above its content, as libadwaita's preference groups have them."""
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, margin_top=6)
        box.append(_label(title, "heading", margin_start=4, margin_bottom=4))
        for widget in widgets:
            box.append(widget)
        return box

    # ---- From the controller and the user ----

    def refresh(self, change: Change) -> None:
        if change & Change.PREFERENCES:
            self.off.set_visible(not self.controller.prefs.collect_statistics)
        if change & (Change.STATISTICS | Change.STATIONS) and self.get_mapped():
            self.update()

    def _opened(self) -> None:
        """Opening the page shows this month."""
        self.period = Period.MONTH
        self.switch.select(self.period)
        self.update()

    def _period_chosen(self, period: Period) -> None:
        self.period = period
        self.update()

    def ask_to_clear(self) -> Adw.AlertDialog:
        _ = self._
        dialog = Adw.AlertDialog(heading=_("Clear statistics?"),
                                 body=_("The listening time and the songs counted so far are deleted. "
                                        "The song history stays."))
        dialog.add_response("cancel", _("Cancel"))
        dialog.add_response("clear", _("Clear"))
        dialog.set_response_appearance("clear", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_default_response("cancel")
        dialog.set_close_response("cancel")
        dialog.connect("response", self._clear_answered)
        dialog.present(self.window)
        return dialog

    def _clear_answered(self, _dialog: Adw.AlertDialog, response: str) -> None:
        if response == "clear":
            self.controller.clear_statistics()

    # ---- Showing the numbers ----

    @property
    def shown(self) -> str:
        """"empty" (nothing in the period) or "data"."""
        return "data" if self.data.get_visible() else "empty"

    def update(self, now: datetime | None = None) -> None:
        """Counts the chosen period again, as of `now` (the tests and the screenshots pass a time)."""
        _ = self._
        if now is None:
            self.controller.refresh_statistics()   # the running session up to now
            now = datetime.now(timezone.utc)
        summary = count(self.controller.statistics, self.period, now)
        self.summary = summary
        self.empty.set_visible(summary.empty)
        self.data.set_visible(not summary.empty)
        if summary.empty:
            return
        today = now.astimezone().date()
        if self.period is Period.ALL:
            first: date = summary.since.astimezone().date()
            self.period_label.set_text(since_label(first, _, C_))
        else:
            self.period_label.set_text(period_label(self.period, today, _, C_))
        self.total_label.set_text(format_duration(summary.total, _))
        self.per_day_label.set_text(_("≈ {time} a day").format(time=format_duration(summary.per_day, _)))
        for label, text in zip(self.tile_values, (format_count(summary.songs), format_count(summary.stations),
                                                  format_duration(summary.longest, _))):
            label.set_text(text)
        self._show_stations(summary)
        self._show_artists(summary)
        self._show_hours(summary)

    def _show_stations(self, summary: Summary) -> None:
        self.stations_list.remove_all()
        most = summary.top_stations[0].seconds if summary.top_stations else 1
        for top in summary.top_stations:
            logo = LogoImage(self.logos, LOGO_SIZE)
            logo.show_logo(find_logo(self.controller.stations, top.url, top.name))
            line = Gtk.Box(spacing=12)
            line.append(logo)
            line.append(_label(top.name, hexpand=True, ellipsize=Pango.EllipsizeMode.END))
            line.append(_label(format_duration(top.seconds, self._), "caption", "dim-label", "numeric"))
            bar = Gtk.ProgressBar(fraction=max(0.03, top.seconds / most), margin_start=LOGO_SIZE + 12,
                                  css_classes=["stat-bar"])
            row = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, margin_top=10, margin_bottom=10,
                          margin_start=14, margin_end=14)
            row.append(line)
            row.append(bar)
            self.stations_list.append(Gtk.ListBoxRow(child=row, activatable=False))

    def _show_artists(self, summary: Summary) -> None:
        _ = self._
        share = round(summary.titles_share * 100)
        self.share_label.set_text(
            _("From song titles sent by the stations · {share} of listening time").format(share=f"{share}%"))
        enough = enough_titles(summary)
        self.artists_list.set_visible(enough)
        self.too_few.set_visible(not enough)
        self.artists_list.remove_all()
        if not enough:
            return
        for rank, (artist, plays) in enumerate(summary.top_artists, 1):
            row = Gtk.Box(spacing=12, margin_top=12, margin_bottom=12, margin_start=14, margin_end=14)
            row.append(_label(str(rank), "caption", "dim-label", "numeric", xalign=1, width_chars=2))
            row.append(_label(artist, hexpand=True, ellipsize=Pango.EllipsizeMode.END))
            row.append(_label(plays_text(plays, N_), "caption", "dim-label"))
            self.artists_list.append(Gtk.ListBoxRow(child=row, activatable=False))

    def _show_hours(self, summary: Summary) -> None:
        self.peak_label.set_text(self._("Most often {hours}").format(hours=format_hours(summary.peak_hour)))
        busiest = max(summary.hours) or 1
        for hour, (bar, seconds) in enumerate(zip(self.bars, summary.hours)):
            bar.set_size_request(-1, round(seconds / busiest * (CHART_HEIGHT - 4)))
            bar.set_tooltip_text(f"{format_hours(hour)} · {format_duration(seconds, self._)}")
