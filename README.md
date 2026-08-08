# Padel Tour

**Сайт:** https://yo-padel-tour.vercel.app · **Бот:** [@YoPadelTourBot](https://t.me/YoPadelTourBot)

Генерация падел-турниров и статистика по ним: Americano и Mexicano, таблица, график
«матч за матчем».

**Готовы движок, хранилище, Telegram-бот, API и веб.** Турнир можно провести из чата: собрать состав
галочками, вводить счёт в два тапа и видеть таблицу — всё в одном сообщении, которое бот
перерисовывает вместо того, чтобы засыпать чат. А на сайте — таблица и график мест
по раундам. Впереди аккаунты.

## Быстрый старт

```bash
uv sync --all-extras
uv run prek install            # хуки на коммит: ruff, ty, pytest

uv run padel-tour play         # начать турнир и вводить счёт
uv run padel-tour resume       # продолжить с того места, где остановились
uv run padel-tour history      # прошедшие турниры
uv run padel-tour demo         # оба формата со случайным счётом, без базы

uv run padel-tour-bot poll     # Telegram-бот локально (нужен BOT_TOKEN в .env)
uv run uvicorn padel_tour.api:app   # HTTP API на :8000

uv run pytest                  # тесты
uv run ruff check .            # линт
uv run ty check                # типы
```

Без `DATABASE_URL` данные лежат в локальном файле `padel.db` — благодаря этому `play`,
а потом `resume` работают на свежем клоне без всякой настройки.

Фронтенд лежит в `web/`:

```bash
cd web && npm install && npm run dev    # :5173, API проксируется на :8000
```

Движок не имеет зависимостей вообще. Всё, что нужно потребителям, живёт в опциональных
группах (`cli`, `db`, `bot`, `api`), чтобы `import padel_tour.engine` ничего лишнего
не тянул.

## Форматы

**Americano** — расписание известно заранее, каждый партнёрит с каждым ровно один раз.
Формально это *whist tournament design*: за n−1 раундов каждая пара игроков ещё и
встречается соперниками ровно дважды. Пересдача (`reroll`) переставляет игроков по слотам
той же схемы, поэтому расписание меняется, но остаётся идеально сбалансированным.

**Mexicano** — первый раунд случайный, дальше таблица режется на четвёрки: ранги 1–4 на
первый корт, 5–8 на второй. Внутри четвёрки пары ставятся по выбранной схеме:
`crossover` (1+4 против 2+3, стандарт), `split` (1+3 против 2+4) или `top-heavy`
(1+2 против 3+4).

**Счёт** — матч до фиксированной суммы очков (обычно 24). Каждый игрок кладёт себе в
копилку счёт своей команды: 14:10 — это +14 обоим победителям и +10 обоим проигравшим.

## Использование движка

```python
from padel_tour.engine import (
    Format,
    TournamentConfig,
    create_americano,
    record_result,
    standings,
    progression,
)

players = ["Аня", "Боря", "Вика", "Гриша", "Даша", "Егор", "Жанна", "Зина"]
config = TournamentConfig(Format.AMERICANO, points_per_match=24)

state = create_americano(players, config, seed=42)
state = record_result(state, round_no=1, court=1, score_a=14, score_b=10)

for row in standings(state):
    print(row.rank, row.player, row.points_for)

series = progression(state)  # данные для графика «матч за матчем»
```

Mexicano отличается тем, что раунды приходят по одному:

```python
from padel_tour.engine import create_mexicano, next_round

config = TournamentConfig(Format.MEXICANO, points_per_match=24, rounds=7)
state = create_mexicano(players, config, seed=42)
# ...записать результат на каждом корте раунда...
state = next_round(state)
```

Каждая операция принимает состояние и возвращает новое — ничего не мутируется. Вся
случайность идёт от `seed`, который хранится в состоянии, поэтому турнир всегда
воспроизводим по паре «состав + seed».

## Ограничения текущей версии

- Игроков должно быть кратно 4 (поддерживаются составы 4, 8, 12, 16, 20, 24). Byes — в планах.
- Americano играется только полным циклом n−1 раундов. Завершить досрочно можно в любой
  момент — таблица остаётся валидной.
- Нет Team Americano, Mixicano и King of the Court.
- Нельзя добавить или убрать игрока по ходу турнира.

## Дальше

| Веха | Содержание |
|---|---|
| M1 ✅ | Движок турниров |
| M2 ✅ | Персистентность и слой сценариев |
| M3 ✅ | Telegram-бот на aiogram 3 |
| M4 ✅ | HTTP API и веб со статистикой и графиками |
| M5 | Привязка аккаунтов: Telegram login и email magic link |

Модель участника выбрана так, чтобы регистрация не была барьером: игрок заводится просто по
имени, а аккаунт (Telegram или email) прикрепляется к нему позже и только если человек хочет
видеть личную статистику.

Подробности и бэклог — [`docs/ROADMAP.md`](docs/ROADMAP.md).
Дизайн движка — [`docs/superpowers/specs/2026-08-06-tournament-engine-design.md`](docs/superpowers/specs/2026-08-06-tournament-engine-design.md).
