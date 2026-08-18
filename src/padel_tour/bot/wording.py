"""Saying a refusal in the language the chat speaks.

Errors carry an English sentence and a machine code (see :mod:`padel_tour.faults`). The
English is for the log. This turns the code into Russian, which is what the people pressing
these buttons read.

Unknown codes fall through to the English sentence rather than to something vague. A phrase
nobody wrote is still better than "что-то пошло не так": it says *what* happened, and a
screenshot of it is a bug report somebody can act on.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from padel_tour.engine import Format, PairingPattern

if TYPE_CHECKING:
    from padel_tour.faults import CodedError

FORMAT_LABEL = {
    Format.AMERICANO: "Американо",
    Format.MEXICANO: "Мексикано",
}

PATTERN_LABEL = {
    PairingPattern.CROSSOVER: "1+4 против 2+3",
    PairingPattern.SPLIT: "1+3 против 2+4",
    PairingPattern.TOP_HEAVY: "1+2 против 3+4",
}


def plural(count: int, one: str, few: str, many: str) -> str:
    """Russian noun agreement: 1 игрок, 2 игрока, 5 игроков, and the teens exception."""
    last_two = count % 100
    last = count % 10
    if last == 1 and last_two != 11:  # noqa: PLR2004
        return one
    if 2 <= last <= 4 and not 12 <= last_two <= 14:  # noqa: PLR2004
        return few
    return many


#: Code to Russian. Keyed by the code rather than the class so this file needs to import
#: neither the engine nor the service layer — it is wording, not logic.
PHRASES: dict[str, str] = {
    # permissions
    "not_signed_in": "Нужно войти",
    "forbidden": "Так нельзя",
    "not_a_member": "Вы не состоите в этой группе",
    "not_the_owner": "Это может сделать только владелец группы",
    "not_the_organiser": "Это может сделать только тот, кто начал турнир",
    "not_on_this_court": "Счёт вносит тот, кто играл этот матч, или организатор",
    # service
    "group_not_found": "Такой группы нет",
    "player_not_found": "Такого игрока нет",
    "tournament_not_found": "Такого турнира нет",
    # Only the admin table browser can raise this, and the bot has no admin screens.
    # It is here because the check is "every code has words", and an exception to that
    # rule is how the next one goes unnoticed.
    "table_not_found": "Такой таблицы нет",
    "duplicate_group_name": "Группа с таким названием уже есть",
    "duplicate_player_name": "Такое имя в группе уже занято",
    "player_not_in_group": "Этот игрок из другой группы",
    "inactive_player": "Этот игрок больше не в составе",
    "active_tournament_exists": "В этой группе уже идёт турнир — сначала завершите его",
    "invalid_token": "Ссылка недействительна — запросите новую",
    "token_expired": "Ссылка устарела — запросите новую",
    "too_many_requests": "Письмо уже отправлено — проверьте почту",
    "invite_not_found": "Приглашение не найдено",
    "invite_used": "Приглашение уже использовано",
    "no_active_tournament": "Сейчас нет активного турнира",
    "no_tournaments_yet": "Турниров ещё не было",
    "unidentified_caller": "Не вижу, от кого сообщение — напишите от своего имени",
    "player_already_claimed": "{name} уже занят(а)",
    "already_playing_here": "В этой группе вы уже {name}",
    # engine
    "invalid_config": "Такие настройки не сходятся",
    "invalid_player_count": "Игроков должно быть кратно четырём",
    "unsupported_player_count": "Для такого числа игроков расписания пока нет",
    "duplicate_player": "Один и тот же игрок дважды в составе",
    "unknown_match": "Такого матча нет",
    "invalid_score": "Счёт не сходится с матчем",
    "result_already_recorded": "Счёт уже записан — исправьте его",
    "round_incomplete": "В этом раунде сыграно не всё",
    "reroll_too_late": "Пересдавать можно только до первого результата",
    "tournament_finished": "Турнир уже завершён",
    "no_more_rounds": "Раунды кончились",
    "wrong_format": "Так в этом формате нельзя",
}


def say(exc: CodedError) -> str:
    """This error, in Russian — or in English if nobody has written the Russian yet."""
    phrase = PHRASES.get(exc.code)
    if phrase is None:
        return str(exc)
    try:
        return phrase.format(**exc.params)
    except KeyError, IndexError:  # pragma: no cover - a wording bug, not a runtime one
        return phrase


__all__ = ["FORMAT_LABEL", "PATTERN_LABEL", "PHRASES", "plural", "say"]
