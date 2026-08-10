"""Screens: pure functions from state to text and buttons.

Nothing here touches the database or the network, which is what makes the whole interface
testable without Telegram. A handler's job is to change state and then ask for a screen.

Text is HTML-formatted (aiogram's default parse mode here), so anything coming from a user —
a player's name — goes through :func:`esc`.
"""

from __future__ import annotations

from html import escape
from typing import TYPE_CHECKING

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from padel_tour.engine import COMMON_POINT_TARGETS, Format, PairingPattern
from padel_tour.settings import base_url

from .callbacks import (
    Action,
    Screen,
    confirm,
    court,
    plain,
    points,
    setting,
    show,
    toggle,
    winner,
)

if TYPE_CHECKING:
    import uuid
    from collections.abc import Sequence

    from padel_tour.services import (
        PlayerView,
        RoundView,
        TournamentSummary,
        TournamentView,
    )

#: A rendered screen: what to say and what to offer.
type Rendered = tuple[str, InlineKeyboardMarkup]

FORMAT_LABEL = {
    Format.AMERICANO: "Американо",
    Format.MEXICANO: "Мексикано",
}
PATTERN_LABEL = {
    PairingPattern.CROSSOVER: "1+4 против 2+3",
    PairingPattern.SPLIT: "1+3 против 2+4",
    PairingPattern.TOP_HEAVY: "1+2 против 3+4",
}
#: A court holds four; below that there is no tournament to run.
PLAYERS_PER_COURT = 4
#: Names listed on the home screen before it collapses into "…and N more".
HOME_NAME_LIMIT = 12
#: Longest name a monospaced table column can show without wrapping on a phone.
TABLE_NAME_WIDTH = 14
#: How many of the standings fit in a photo caption without crowding the picture.
PODIUM = 3


def esc(text: str) -> str:
    return escape(text, quote=False)


def _nav(*pairs: tuple[str, str]) -> list[InlineKeyboardButton]:
    return [InlineKeyboardButton(text=label, callback_data=data) for label, data in pairs]


# --------------------------------------------------------------------------- home


def home(group_name: str, roster: Sequence[PlayerView]) -> Rendered:
    """What the chat sees when nothing is running."""
    lines = [f"<b>{esc(group_name)}</b>", ""]
    if roster:
        counted = _plural(len(roster), "игрок", "игрока", "игроков")
        lines.append(f"В группе {len(roster)} {counted}")
        lines.append(", ".join(esc(p.name) for p in roster[:HOME_NAME_LIMIT]))
        if len(roster) > HOME_NAME_LIMIT:
            lines.append(f"…и ещё {len(roster) - HOME_NAME_LIMIT}")
    else:
        lines.append("Пока никого. Добавьте игроков: <code>/add Аня, Боря, Вика</code>")

    builder = InlineKeyboardBuilder()
    if len(roster) >= PLAYERS_PER_COURT:
        builder.row(InlineKeyboardButton(text="🎾 Новый турнир", callback_data=show(Screen.ROSTER)))
    builder.row(*_nav(("📜 История", show(Screen.HISTORY))))
    return "\n".join(lines), builder.as_markup()


def _plural(count: int, one: str, few: str, many: str) -> str:
    """Russian noun agreement: 1 игрок, 2 игрока, 5 игроков, and the teens exception."""
    last_two = count % 100
    last = count % 10
    if last == 1 and last_two != 11:  # noqa: PLR2004
        return one
    if 2 <= last <= 4 and not 12 <= last_two <= 14:  # noqa: PLR2004
        return few
    return many


# --------------------------------------------------------------------------- roster


def roster_screen(
    roster: Sequence[PlayerView],
    selected: set[uuid.UUID],
    allowed_counts: Sequence[int],
) -> Rendered:
    """Pick who is playing. 'Дальше' only appears once the count is one we can schedule."""
    chosen = len(selected)
    options = ", ".join(str(value) for value in allowed_counts)

    lines = ["<b>Кто играет?</b>", ""]
    lines.append(f"Выбрано: <b>{chosen}</b>")
    if chosen in allowed_counts:
        lines.append("Можно начинать.")
    else:
        lines.append(f"Нужно {options} — столько влезает в корты по четверо.")

    builder = InlineKeyboardBuilder()
    for player in roster:
        mark = "✅" if player.id in selected else "▫️"
        builder.row(
            InlineKeyboardButton(text=f"{mark} {player.name}", callback_data=toggle(player.id))
        )

    tail = []
    if chosen in allowed_counts:
        tail.append(("Дальше →", show(Screen.SETUP)))
    tail.append(("✖️ Отмена", show(Screen.HOME)))
    builder.row(*_nav(*tail))
    return "\n".join(lines), builder.as_markup()


# --------------------------------------------------------------------------- setup


def setup_screen(
    fmt: Format,
    points_per_match: int,
    pattern: PairingPattern,
    rounds: int,
    player_count: int,
) -> Rendered:
    """Tournament options. Every value is one tap away from changing."""
    lines = [
        "<b>Настройки турнира</b>",
        "",
        f"Игроков: <b>{player_count}</b>, кортов: <b>{player_count // PLAYERS_PER_COURT}</b>",
    ]
    if fmt is Format.AMERICANO:
        lines.append(
            f"Американо: {player_count - 1} "
            + _plural(player_count - 1, "раунд", "раунда", "раундов")
            + ", каждый с каждым в паре."
        )
    else:
        lines.append("Мексикано: пары по таблице после каждого раунда.")

    builder = InlineKeyboardBuilder()
    builder.row(
        *[
            InlineKeyboardButton(
                text=("• " if value is fmt else "") + FORMAT_LABEL[value],
                callback_data=setting("fmt", value.value),
            )
            for value in Format
        ]
    )
    builder.row(
        *[
            InlineKeyboardButton(
                text=("• " if value == points_per_match else "") + f"до {value}",
                callback_data=setting("pts", str(value)),
            )
            for value in COMMON_POINT_TARGETS
        ]
    )
    if fmt is Format.MEXICANO:
        for value in PairingPattern:
            builder.row(
                InlineKeyboardButton(
                    text=("• " if value is pattern else "") + PATTERN_LABEL[value],
                    callback_data=setting("pat", value.value),
                )
            )
        builder.row(
            InlineKeyboardButton(text="−1 раунд", callback_data=setting("rnd", "-1")),
            InlineKeyboardButton(text=f"{rounds} раундов", callback_data=setting("rnd", "0")),
            InlineKeyboardButton(text="+1 раунд", callback_data=setting("rnd", "+1")),
        )

    builder.row(*_nav(("🎲 Жеребьёвка", plain(Action.BEGIN)), ("←", show(Screen.ROSTER))))
    return "\n".join(lines), builder.as_markup()


# --------------------------------------------------------------------------- draw


def draw_screen(view: TournamentView) -> Rendered:
    """The draw, before a single point is played."""
    lines = [f"<b>Жеребьёвка — {FORMAT_LABEL[view.format]}</b>", ""]
    if view.format is Format.AMERICANO:
        for rnd in view.rounds:
            lines.append(f"<b>Раунд {rnd.number}</b>")
            lines.extend(_match_lines(rnd))
            lines.append("")
    else:
        lines.append(f"Раундов: {view.total_rounds}")
        lines.append("")
        first = view.rounds[0]
        lines.extend(_match_lines(first))

    builder = InlineKeyboardBuilder()
    builder.row(*_nav(("🎲 Пересдать", plain(Action.REROLL)), ("▶️ Поехали", show(Screen.ROUND))))
    return "\n".join(lines), builder.as_markup()


def _match_lines(rnd: RoundView) -> list[str]:
    lines = []
    for match in rnd.matches:
        left = " + ".join(esc(name) for name in match.team_a)
        right = " + ".join(esc(name) for name in match.team_b)
        score = f"  <b>{match.score_a}:{match.score_b}</b>" if match.played else ""
        lines.append(f"Корт {match.court}: {left} — {right}{score}")
    return lines


# --------------------------------------------------------------------------- round


def round_screen(view: TournamentView) -> Rendered:
    """The live screen: what is being played and where to put the scores."""
    rnd = view.next_unfinished_round or view.current_round
    if rnd is None:
        return table_screen(view)

    lines = [
        f"<b>Раунд {rnd.number} из {view.total_rounds}</b>",
        f"<i>матч до {view.points_per_match} очков</i>",
        "",
        *_match_lines(rnd),
    ]

    builder = InlineKeyboardBuilder()
    for match in rnd.matches:
        if match.played:
            continue
        builder.row(
            InlineKeyboardButton(
                text=f"✍️ Счёт — корт {match.court}", callback_data=court(match.court)
            )
        )
    builder.row(*_nav(("📊 Таблица", show(Screen.TABLE)), ("📈 График", show(Screen.CHART))))
    return "\n".join(lines), builder.as_markup()


def winner_screen(view: TournamentView, rnd: RoundView, court_no: int) -> Rendered:
    """Step one of entering a score: who won."""
    match = next(m for m in rnd.matches if m.court == court_no)
    left = " + ".join(esc(name) for name in match.team_a)
    right = " + ".join(esc(name) for name in match.team_b)

    lines = [
        f"<b>Корт {court_no}, раунд {rnd.number}</b>",
        "",
        f"{left}",
        f"{right}",
        "",
        "Кто выиграл?",
    ]

    builder = InlineKeyboardBuilder()
    for side, team in (("a", match.team_a), ("b", match.team_b)):
        builder.row(InlineKeyboardButton(text=f"🏆 {' + '.join(team)}", callback_data=winner(side)))
    # An odd target cannot be split evenly, so a draw is arithmetically impossible.
    if view.points_per_match % 2 == 0:
        builder.row(InlineKeyboardButton(text="🤝 Ничья", callback_data=winner("draw")))
    builder.row(*_nav(("← Назад", plain(Action.CANCEL))))
    return "\n".join(lines), builder.as_markup()


def points_screen(view: TournamentView, court_no: int) -> Rendered:
    """Step two: how many points the winner took.

    Only scores that actually win are offered — below half the target the 'winner' lost.
    """
    target = view.points_per_match
    lowest = target // 2 + 1

    lines = [
        f"<b>Корт {court_no}</b>",
        "",
        f"Сколько очков у победителей? Матч до {target}.",
    ]

    builder = InlineKeyboardBuilder()
    for value in range(lowest, target + 1):
        builder.button(text=str(value), callback_data=points(value))
    builder.adjust(4)
    builder.row(*_nav(("← Назад", plain(Action.CANCEL))))
    return "\n".join(lines), builder.as_markup()


# --------------------------------------------------------------------------- table


def table_screen(view: TournamentView) -> Rendered:
    """The leaderboard."""
    medals = {1: "🥇", 2: "🥈", 3: "🥉"}
    lines = ["<b>Таблица</b>", "", "<pre>"]
    lines.append(f"{'#':>2} {'игрок':<14}{'очки':>6}{'разн':>6}")
    for row in view.standings:
        mark = medals.get(row.rank, f"{row.rank:>2}")
        name = f"{row.name[:TABLE_NAME_WIDTH]:<{TABLE_NAME_WIDTH}}"
        lines.append(f"{mark:>2} {name}{row.points_for:>6}{row.diff:>+6}")
    lines.append("</pre>")

    if view.finished:
        lines.append("")
        lines.append(f"🏆 Победитель — <b>{esc(view.standings[0].name)}</b>")

    builder = InlineKeyboardBuilder()
    if view.finished:
        builder.row(*_nav(("📈 График", show(Screen.CHART)), ("🏠 В начало", show(Screen.HOME))))
    else:
        builder.row(*_nav(("🎾 К раунду", show(Screen.ROUND)), ("📈 График", show(Screen.CHART))))
        builder.row(
            *_nav(
                ("🏁 Завершить", confirm(Action.FINISH)),
            )
        )
    return "\n".join(lines), builder.as_markup()


def confirm_finish(view: TournamentView) -> Rendered:
    """Ending a tournament early is fine, but it should not happen by a stray tap."""
    played = sum(1 for rnd in view.rounds if rnd.complete)
    lines = [
        "<b>Завершить турнир?</b>",
        "",
        f"Сыграно {played} из {view.total_rounds}. Таблица останется как есть.",
    ]
    builder = InlineKeyboardBuilder()
    builder.row(*_nav(("🏁 Да, завершить", plain(Action.FINISH)), ("← Нет", show(Screen.TABLE))))
    return "\n".join(lines), builder.as_markup()


# --------------------------------------------------------------------------- chart


def chart_caption(view: TournamentView) -> Rendered:
    """What goes under the picture.

    Short on purpose. A caption is capped at 1024 characters, which an eight-player table
    fits inside and a twenty-four-player one does not — so rather than have the screen work
    for small groups and silently truncate for large ones, it always shows the top three and
    points at the full table, which is one button away.
    """
    medals = {1: "🥇", 2: "🥈", 3: "🥉"}
    lines = ["<b>Ход турнира</b>", "", "Места по раундам.", ""]
    lines.extend(
        f"{medals.get(row.rank, row.rank)} {esc(row.name)} — {row.points_for}"
        for row in view.standings[:PODIUM]
    )

    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🌐 Открыть в вебе", url=f"{base_url()}/t/{view.id}"))
    if view.finished:
        builder.row(*_nav(("📊 Таблица", show(Screen.TABLE)), ("🏠 В начало", show(Screen.HOME))))
    else:
        builder.row(*_nav(("🎾 К раунду", show(Screen.ROUND)), ("📊 Таблица", show(Screen.TABLE))))
    return "\n".join(lines), builder.as_markup()


# --------------------------------------------------------------------------- history


def history_screen(entries: Sequence[TournamentSummary]) -> Rendered:
    lines = ["<b>Прошедшие турниры</b>", ""]
    if not entries:
        lines.append("Пока ни одного.")
    for entry in entries:
        when = entry.created_at.strftime("%d.%m")
        winner_name = esc(entry.winner_name) if entry.winner_name else "—"
        status = "" if entry.finished else " <i>(идёт)</i>"
        lines.append(
            f"{when} · {FORMAT_LABEL[entry.format]} · {entry.player_count} чел. · "
            f"🏆 {winner_name}{status}"
        )

    builder = InlineKeyboardBuilder()
    builder.row(*_nav(("🏠 В начало", show(Screen.HOME))))
    return "\n".join(lines), builder.as_markup()
