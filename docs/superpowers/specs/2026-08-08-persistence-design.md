# M2 — Персистентность и слой сценариев

Дата: 2026-08-08
Статус: согласован
Предыдущая веха: [движок турниров](2026-08-06-tournament-engine-design.md)

## Задача

Движок M1 умеет всё про правила, но живёт в оперативной памяти: закрыл процесс — турнира
нет. M2 добавляет два слоя под уже готовую логику:

1. **Хранилище** — группы, игроки, турниры, раунды, матчи в Postgres.
2. **Слой сценариев** — единственная точка входа для всех интерфейсов. Бот (M3), API (M4)
   и CLI зовут его, а не движок и не базу напрямую.

Результат вехи проверяется руками: турнир проводится в CLI, процесс завершается, CLI
запускается снова и продолжает с того же раунда.

**HTTP API в M2 не входит** — он переехал в M4, к своему первому настоящему потребителю
([Р-007](../../DECISIONS.md)).

## Зависимости идут в одну сторону

```
cli / bot / api  →  services  →  repositories  →  db
                        ↓
                     engine            (ничего не знает об остальных)
```

Движок остаётся тем, чем был: чистой библиотекой без зависимостей. Слой сценариев собирает
`TournamentState` из строк базы, зовёт функции движка, раскладывает результат обратно.
Никакой бизнес-логики в репозиториях и никакого SQL в сценариях.

## Модель данных

Первичные ключи — UUIDv7 из `uuid.uuid7()` ([Р-009](../../DECISIONS.md)).

| Таблица | Поля | Смысл |
|---|---|---|
| `groups` | `id`, `name`, `telegram_chat_id?`, `created_at` | сообщество |
| `players` | `id`, `group_id`, `name`, `is_active`, `created_at` | игрок группы, аккаунт не нужен |
| `tournaments` | `id`, `group_id`, `format`, `points_per_match`, `pairing_pattern`, `total_rounds`, `seed`, `status`, `created_at`, `finished_at?` | турнир |
| `tournament_players` | `tournament_id`, `player_id`, `draw_position` | состав + позиция жеребьёвки |
| `rounds` | `id`, `tournament_id`, `number` | раунд |
| `matches` | `id`, `round_id`, `court`, `team_a1`, `team_a2`, `team_b1`, `team_b2`, `score_a?`, `score_b?` | матч; счёт `NULL`, пока не сыгран |

Ключевые ограничения, которые база должна держать сама, а не «мы же аккуратные»:

- `unique (group_id, name)` на игроках — двух Ань в одной группе не бывает;
- `unique (tournament_id, number)` на раундах и `unique (round_id, court)` на матчах;
- `unique (tournament_id, draw_position)` — позиция жеребьёвки уникальна, это последняя
  ступень тай-брейка и она обязана быть однозначной;
- `check ((score_a is null) = (score_b is null))` — половинчатого счёта не существует.

`draw_position` хранится, а не пересчитывается из seed: seed задаёт её при создании, но
после этого она становится фактом турнира. Пересчёт при каждом чтении означал бы, что
изменение алгоритма перемешивания задним числом переставит места в старых турнирах.

**Игроки не удаляются, а деактивируются** (`is_active`). Ушедший из группы человек остаётся
в истории сыгранных турниров — иначе статистика рассыпается.

### Почему раунды и матчи хранятся явно

В Americano расписание выводится из seed, в Mexicano — нет: оно зависит от результатов.
Единый способ хранения для обоих форматов ([Р-004](../../DECISIONS.md)) заодно даёт то,
по чему считается статистика: запрос «с кем Аня чаще выигрывает» по таблице матчей
пишется, по seed — нет.

## Слой сценариев

Модуль `padel_tour.services`, функции принимают сессию первым аргументом:

```python
# группы и игроки
create_group(session, name, telegram_chat_id=None) -> GroupView
add_player(session, group_id, name) -> PlayerView
list_players(session, group_id, *, include_inactive=False) -> list[PlayerView]
rename_player(session, player_id, name) -> PlayerView
deactivate_player(session, player_id) -> PlayerView

# жизненный цикл турнира
start_tournament(session, group_id, player_ids, config, seed=None) -> TournamentView
reroll_tournament(session, tournament_id) -> TournamentView
record_score(session, tournament_id, round_no, court, score_a, score_b) -> TournamentView
amend_score(session, tournament_id, round_no, court, score_a, score_b) -> TournamentView
advance_round(session, tournament_id) -> TournamentView       # Mexicano
finish_tournament(session, tournament_id) -> TournamentView

# чтение
get_tournament(session, tournament_id) -> TournamentView
list_tournaments(session, group_id, *, limit, offset) -> list[TournamentSummary]
active_tournament(session, group_id) -> TournamentView | None
```

`TournamentView` — то, что интерфейсу нужно показать: состояние движка, имена игроков,
таблица и progression, уже посчитанные. Ни бот, ни веб не должны сами вызывать
`standings()` и склеивать имена — иначе они разойдутся в мелочах.

Правило сессий: **функция сценария не коммитит**. Транзакцией управляет вызывающий —
у бота это один апдейт, у API один запрос. Так сценарии остаются композируемыми.

### Как состояние ездит туда-обратно

```
загрузка:  строки БД → PlayerId = str(player.id) → TournamentState → движок
сохранение: движок вернул новый State → diff по (round, court) → UPDATE только изменённого
```

Движок оперирует непрозрачными `PlayerId: str`, и мы подставляем туда строковый UUID.
Имена подставляются только на границе, в `TournamentView`. Благодаря этому переименование
игрока не трогает ни одного сохранённого турнира.

Сохранение пишет не всё состояние целиком, а только то, что изменилось: запись счёта — это
один `UPDATE` одной строки матча, а не перезапись турнира. Новый раунд Mexicano —
это `INSERT` раунда и его матчей.

## Ошибки

Иерархия сценариев отдельная от движка: `padel_tour.services.errors`. Движковые ошибки
(`InvalidScoreError`, `RoundIncompleteError`, …) пробрасываются как есть — они уже написаны
для человека. Добавляются свои:

`GroupNotFoundError`, `PlayerNotFoundError`, `TournamentNotFoundError`,
`PlayerNotInGroupError`, `DuplicateGroupNameError`, `ActiveTournamentExistsError`.

Последняя нужна, потому что в группе не может идти два турнира одновременно: бот показывает
один экран на чат, и второй активный турнир сделал бы этот экран неоднозначным.

## Миграции и окружения

Alembic, одна линейная история. Первая ревизия создаёт всю схему.

| Где | База | Зачем |
|---|---|---|
| локально | SQLite (aiosqlite), файл `padel.db` | ноль настройки |
| тесты локально | SQLite в памяти | мгновенно |
| тесты в CI | Postgres сервис-контейнером | ловит различия диалектов |
| деплой | Neon Postgres (asyncpg) | продакшн |

Обоснование двух диалектов — [Р-008](../../DECISIONS.md). Практическое следствие: в моделях
не используются Postgres-специфичные типы. UUID хранится как `Uuid` из SQLAlchemy, который
сам ложится в `uuid` на Postgres и в `char(32)` на SQLite.

`DATABASE_URL` не задан — берётся SQLite. Задан — берётся он.

## Тестирование

- **Репозитории** — что ограничения базы действительно срабатывают: дубль имени игрока
  падает, половинчатый счёт падает, две позиции жеребьёвки падают.
- **Сценарии** — на настоящей базе, не на моках. Мок репозитория проверил бы, что мы
  вызвали то, что вызвали, а не что данные легли правильно.
- **Круговой прогон** — главный тест вехи: провести турнир, выбросить сессию и все объекты,
  загрузить заново и убедиться, что расписание, таблица и progression совпадают до байта.
- **Оба диалекта** — весь набор идёт и на SQLite, и на Postgres.

## Верификация

- `pytest` локально (SQLite) и в CI (Postgres) — зелёные.
- `ruff`, `ruff format`, `ty` — чисто.
- `alembic upgrade head` на пустой базе и `alembic downgrade base` обратно.
- Руками: `padel-tour play` создаёт турнир, вводим пару результатов, **убиваем процесс**,
  `padel-tour resume` показывает тот же турнир с теми же очками и продолжает с нужного
  раунда. Отдельно — что `padel-tour history` показывает завершённые турниры.
