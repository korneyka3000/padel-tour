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
from padel_tour.settings import mini_app_url

from .callbacks import (
    Action,
    Screen,
    claim,
    confirm,
    court,
    drop,
    plain,
    points,
    release,
    setting,
    show,
    toggle,
    winner,
)
from .wording import FORMAT_LABEL, PATTERN_LABEL
from .wording import plural as _plural

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


#: A court holds four; below that there is no tournament to run.
PLAYERS_PER_COURT = 4
#: Names listed on the home screen before it collapses into "…and N more".
HOME_NAME_LIMIT = 12
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
        lines.append(f"<b>{len(roster)}</b> {counted}")
        lines.append("")
        # One per line. Comma-joined, eight names are a paragraph nobody reads and nobody
        # can point at; stacked, the roster is something you can check at a glance.
        lines.extend(f"· {esc(player.name)}" for player in roster[:HOME_NAME_LIMIT])
        if len(roster) > HOME_NAME_LIMIT:
            rest = len(roster) - HOME_NAME_LIMIT
            lines.append(f"<i>…и ещё {rest}</i>")
    else:
        lines.append("Пока никого. Добавьте игроков: <code>/add Аня, Боря, Вика</code>")

    builder = InlineKeyboardBuilder()
    if len(roster) >= PLAYERS_PER_COURT:
        builder.row(InlineKeyboardButton(text="🎾 Новый турнир", callback_data=show(Screen.ROSTER)))
    builder.row(*_nav(("👥 Состав", show(Screen.SQUAD)), ("📜 История", show(Screen.HISTORY))))
    return "\n".join(lines), builder.as_markup()


def squad_screen(roster: Sequence[PlayerView], mine: uuid.UUID | None = None) -> Rendered:
    """The group's roster, and the three things done to it.

    Removing hides rather than deletes — the row carries every match that person played —
    and ``/add`` with the same name brings them back, which is why one tap is enough and
    there is no confirmation standing in the way.

    Saying which of these names is you is the other tap, and it is the one that makes a
    personal history exist at all: matches are recorded against a player, so until an
    account holds one, "my statistics" has nothing to point at.
    """
    lines = ["<b>Состав группы</b>", ""]
    if not roster:
        lines.append("Пока никого.")
    elif mine is None:
        lines.append("Отметьте себя — тогда бот запомнит вашу статистику.")
    lines.append("")
    lines.append("Добавить: <code>/add Аня, Боря</code>")
    lines.append("Переименовать: <code>/rename Аня = Анна</code>")

    builder = InlineKeyboardBuilder()
    for player in roster:
        row = [InlineKeyboardButton(text=f"✕ {player.name}", callback_data=drop(player.id))]
        if player.id == mine:
            row.append(InlineKeyboardButton(text="это я ✓", callback_data=release(player.id)))
        elif mine is None:
            row.append(InlineKeyboardButton(text="это я", callback_data=claim(player.id)))
        builder.row(*row)
    builder.row(*_nav(("🏠 В начало", show(Screen.HOME))))
    return "\n".join(lines), builder.as_markup()


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
    lines.append("Все отмечены — снимите тех, кого сегодня нет.")
    lines.append("")
    lines.append(f"Выбрано: <b>{chosen}</b> из {len(roster)}")
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
    """The live screen: what is being played and where to put the scores.

    A Mexicano that has played its last planned round lands here with nothing left to draw
    and no automatic ending — the count was the organiser's plan, not the format's rule —
    so this is where "one more?" gets asked.
    """
    rnd = view.next_unfinished_round or view.current_round
    if rnd is None:
        return table_screen(view)

    if _plan_used_up(view):
        return _plan_done_screen(view)

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


def _plan_used_up(view: TournamentView) -> bool:
    """Every planned round drawn and played, and the tournament still open."""
    return (
        view.format is Format.MEXICANO
        and not view.finished
        and len(view.rounds) >= view.total_rounds
        and all(rnd.complete for rnd in view.rounds)
    )


def _plan_done_screen(view: TournamentView) -> Rendered:
    """The fork at the end of a Mexicano: one more, or that is the evening."""
    leader = view.standings[0]
    lines = [
        f"<b>Сыграно {view.total_rounds} из {view.total_rounds}</b>",
        "",
        f"Впереди <b>{esc(leader.name)}</b> — {leader.points_for}.",
        "Играем ещё раунд или заканчиваем?",
    ]

    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="➕ Ещё раунд", callback_data=plain(Action.EXTEND)))
    builder.row(*_nav(("📊 Таблица", show(Screen.TABLE)), ("🏁 Завершить", confirm(Action.FINISH))))
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


MEDALS = {1: "🥇", 2: "🥈", 3: "🥉"}

#: Longest name the table shows in full. Wider and the columns stop fitting a phone.
NAME_WIDTH = 11


def _standing_lines(view: TournamentView) -> list[str]:
    """The table, in columns that actually line up.

    Three attempts, and the reasons for the last one are the reasons the first two failed.

    ``<pre>`` aligns, because it is monospaced — but Telegram renders it as a code listing
    with a "copy" header bolted on, and wraps it once a line passes the chat width, which
    folded every row of an eight-player table in half on a phone.

    Proportional text has no header and no wrapping problem, and no alignment either: it
    turned the table into a list of sentences, which is what it looked like and not what it
    is. A table whose numbers do not stack is a table you cannot read down.

    So: inline ``<code>``, one span per row. Monospaced, therefore aligned, and without the
    block chrome — Telegram only draws the copy header for ``<pre>``. The medals sit
    *outside* the span, at the end of the line, because an emoji is double-width and one in
    the middle of a monospaced row throws every column after it out by a character.
    """
    lines = []
    for row in view.standings:
        name = row.name if len(row.name) <= NAME_WIDTH else row.name[: NAME_WIDTH - 1] + "…"
        cells = f"{row.rank:>2}  {name:<{NAME_WIDTH}} {row.points_for:>4} {row.diff:>+5}"
        medal = f" {MEDALS[row.rank]}" if row.rank in MEDALS else ""
        lines.append(f"<code>{esc(cells)}</code>{medal}")
    return lines


def _table_header() -> str:
    """Column names, in the same monospaced grid as the rows underneath them."""
    return f"<code>{'':>2}  {'игрок':<{NAME_WIDTH}} {'очки':>4} {'разн':>5}</code>"


def table_screen(view: TournamentView) -> Rendered:
    """The leaderboard while play is going on."""
    if view.finished:
        return finish_screen(view)

    played = sum(1 for rnd in view.rounds if rnd.complete)
    lines = [
        f"<b>Таблица</b> · сыграно {played} из {view.total_rounds}",
        "",
        _table_header(),
        *_standing_lines(view),
    ]

    builder = InlineKeyboardBuilder()
    builder.row(*_nav(("🎾 К раунду", show(Screen.ROUND)), ("📈 График", show(Screen.CHART))))
    builder.row(*_nav(("🏁 Завершить", confirm(Action.FINISH))))
    return "\n".join(lines), builder.as_markup()


def finish_screen(view: TournamentView) -> Rendered:
    """The ending, and it should feel like one.

    A tournament that stops by quietly greying out its buttons is an anticlimax after two
    hours on court. So: the winner is named on their own line, the podium is called out, and
    everybody else is still listed — seven of the eight also turned up.
    """
    table = view.standings
    lines = ["🏆 <b>Турнир завершён</b>", ""]

    if table:
        champion = table[0]
        lines.append(f"Победитель — <b>{esc(champion.name)}</b>, {champion.points_for} очков")
        lines.append("")

    lines.append(_table_header())
    lines.extend(_standing_lines(view))

    if len(table) > PODIUM:
        # The people who did not make the podium are the reason there was a tournament.
        lines.append("")
        lines.append(f"<i>Сыграли все {len(table)}. Спасибо каждому.</i>")

    builder = InlineKeyboardBuilder()
    builder.row(*_nav(("📈 График", show(Screen.CHART)), ("📜 История", show(Screen.HISTORY))))
    builder.row(*_nav(("🏠 В начало", show(Screen.HOME))))
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
    builder.row(InlineKeyboardButton(text="📊 Открыть график", url=mini_app_url(f"t_{view.id}")))
    if view.finished:
        builder.row(*_nav(("📊 Таблица", show(Screen.TABLE)), ("🏠 В начало", show(Screen.HOME))))
    else:
        builder.row(*_nav(("🎾 К раунду", show(Screen.ROUND)), ("📊 Таблица", show(Screen.TABLE))))
    return "\n".join(lines), builder.as_markup()


# --------------------------------------------------------------------------- history


def history_screen(entries: Sequence[TournamentSummary]) -> Rendered:
    """What the group has played.

    Each line used to name the winner and nobody else, which turned a record of eight
    people into a record of one. The podium goes in, and the rest are counted rather than
    reduced to a number with no faces attached.
    """
    lines = ["<b>Прошедшие турниры</b>", ""]
    if not entries:
        lines.append("Пока ни одного.")

    for entry in entries:
        when = entry.created_at.strftime("%d.%m")
        status = " <i>(идёт)</i>" if not entry.finished else ""
        lines.append(f"<b>{when}</b> · {FORMAT_LABEL[entry.format]}{status}")

        podium = entry.placings[:PODIUM]
        if podium:
            lines.append(
                "  "
                + " · ".join(f"{MEDALS[place]} {esc(name)}" for place, name in enumerate(podium, 1))
            )
            rest = entry.player_count - len(podium)
            if rest > 0:
                lines.append(f"  <i>и ещё {rest} {_plural(rest, 'игрок', 'игрока', 'игроков')}</i>")
        else:
            lines.append("  <i>ещё не сыграно ни одного раунда</i>")
        lines.append("")

    builder = InlineKeyboardBuilder()
    builder.row(*_nav(("🏠 В начало", show(Screen.HOME))))
    return "\n".join(lines), builder.as_markup()
