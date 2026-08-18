/**
 * Two languages, no library.
 *
 * `react-i18next` under two locales is a runtime, a plugin chain and a config file in
 * exchange for `t('key')`. What a library actually buys is the guarantee that no key is
 * missing — and TypeScript gives that for free: `en` is typed against the keys of `ru`, so
 * a forgotten phrase is a build failure rather than a blank on somebody's screen.
 *
 * Counting and dates go through `Intl`. The hand-written `plural()` this replaces knew only
 * Russian and would have lied in English.
 */

export type Locale = 'ru' | 'en'

export const LOCALES: Locale[] = ['ru', 'en']

/** Shown in the switcher. Each language names itself — nobody looks for "Russian". */
export const LOCALE_LABEL: Record<Locale, string> = { ru: 'RU', en: 'EN' }

export const ru = {
  // ─────────────────────────────────────────────────────────────── chrome
  'nav.signIn': 'Войти',
  'nav.signOut': 'Выйти',
  'nav.home': '← На главную',
  'nav.toGroup': '← К группе',
  'nav.language': 'Язык',

  'async.loading': 'Загружаем',
  'async.failedTitle': 'Не открылось',
  'async.failedBody': '{message}. Обновите страницу или проверьте ссылку.',
  'async.somethingWrong': 'Что-то пошло не так',

  'notFound.title': 'Такой страницы нет',
  'notFound.body': 'Проверьте ссылку.',

  // ─────────────────────────────────────────────────────────────── home
  'home.formats': 'Американо · Мексикано',
  'home.tagline': 'Кто с кем играет, кто впереди и как это менялось.',
  'home.startHere': 'Начните здесь',
  'home.startBody':
    'Группы видны только своим. Войдите по ссылке из почты — или откройте приглашение, если вам его прислали.',
  'home.telegramHint': 'В Telegram проще: добавьте бота в чат и напишите',
  'home.yourGroups': 'Ваши группы',
  'home.noGroups': 'Пока ни одной. Заведите свою — вы станете её владельцем.',
  'home.newGroup': 'Новая группа',
  'home.newGroupPlaceholder': 'Вторничный падел',
  'home.create': 'Завести',
  'home.creating': 'Заводим…',
  'home.createFailed': 'Не создалась',

  // ─────────────────────────────────────────────────────────────── signing in
  'signIn.eyebrow': 'Вход',
  'signIn.title': 'Ссылка вместо пароля',
  'signIn.body': 'Оставьте адрес — пришлём ссылку, по которой вы окажетесь внутри. Пароля здесь нет.',
  'signIn.emailLabel': 'Почта',
  'signIn.send': 'Прислать ссылку',
  'signIn.sending': 'Отправляем…',
  'signIn.failed': 'Не отправилось',
  'signIn.checkMail': 'Проверьте почту',
  'signIn.sentTo': 'Отправили ссылку на {email}. Она действует пятнадцать минут и срабатывает один раз.',

  'enter.noToken': 'В ссылке нет токена',
  'enter.failed': 'Ссылка не сработала',
  'enter.title': 'Не вошли',
  'enter.askNew': 'Запросите новую ссылку',

  // ─────────────────────────────────────────────────────────────── invitation
  'invite.notFound': 'Приглашение не найдено',
  'invite.eyebrow': 'Приглашение',
  'invite.youAre': 'Вы — {name}',
  'invite.body': 'Приняв, вы получите свою историю матчей и сможете вносить счёт в своих играх.',
  'invite.accept': 'Играть как {name}',
  'invite.accepting': 'Принимаем…',
  'invite.signInFirst': 'Чтобы приглашение осталось за вами, сначала войдите.',
  'invite.signInAndContinue': 'Войти и продолжить',
  'invite.failed': 'Не получилось',

  // ─────────────────────────────────────────────────────────────── group
  'group.nowPlaying': 'Сейчас идёт {format} — раунд {round} из {total}',
  'group.nobodyPlaying': 'Сейчас никто не играет',
  'group.toTournament': 'К турниру',
  'group.assemble': 'Собрать турнир',
  'group.archive': 'Прошедшие турниры',
  'group.noneYet': 'Пока ни одного',
  'group.assembleFirst': 'Соберите первый — он появится здесь.',
  'group.someoneWill': 'Как только кто-нибудь соберёт турнир, он появится здесь.',
  'group.playedOf': 'сыграно {played} из {total}',
  'group.winner': 'победитель',

  // ─────────────────────────────────────────────────────────────── player
  'player.eyebrow': 'Игрок',
  'player.summary': 'Сводка',
  'player.tournaments': 'Турниров',
  'player.matches': 'Матчей',
  'player.wins': 'Побед',
  'player.pointsPerMatch': 'Очков за матч',
  'player.bestRank': 'Лучшее место',
  'player.podiums': 'Призовых',
  'player.history': 'Турниры',
  'player.neverPlayed': 'Ещё не играл',
  'player.neverPlayedBody': 'Сыграйте турнир — он появится здесь.',

  // ─────────────────────────────────────────────────────────────── tournament
  'tournament.finished': 'Завершён',
  'tournament.live': 'Идёт сейчас',
  'tournament.matchTo': 'матч до {points}',
  'tournament.nextRound': 'Следующий раунд',
  'tournament.reroll': 'Пересдать',
  'tournament.finish': 'Завершить',
  'tournament.actionFailed': 'Не получилось',

  // ─────────────────────────────────────────────────────────────── drawing one
  'draw.title': 'Собрать турнир',
  'draw.pickWho': 'Отметьте, кто играет',
  'draw.whoPlays': 'Кто играет',
  'draw.needMultiple': 'нужно 4, 8, 12, 16…',
  'draw.rules': 'Правила',
  'draw.format': 'Формат',
  'draw.americanoHint': 'каждый с каждым в паре',
  'draw.mexicanoHint': 'пары по таблице',
  'draw.matchTo': 'Матч до',
  'draw.pairs': 'Пары',
  'draw.crossover': 'Крест',
  'draw.crossoverHint': '1+4 против 2+3',
  'draw.split': 'Через одного',
  'draw.splitHint': '1+3 против 2+4',
  'draw.topHeavy': 'По силе',
  'draw.topHeavyHint': '1+2 против 3+4',
  'draw.rounds': 'Раундов',
  'draw.go': 'Жеребьёвка',
  'draw.going': 'Жеребьёвка…',
  'draw.failed': 'Не собралось',

  // ─────────────────────────────────────────────────────────────── roster
  'roster.title': 'Состав',
  'roster.rename': 'переименовать',
  'nav.admin': 'Админка',
  'admin.eyebrow': 'ТОЛЬКО ДЛЯ АДМИНИСТРАТОРОВ',
  'admin.title': 'Управление',
  'admin.notYou': 'Этот раздел доступен только администраторам. Если это ошибка — проверьте, тем ли способом вы вошли: вход по почте и вход из бота создают разные аккаунты.',
  'admin.overview': 'Сводка',
  'admin.people': 'Люди',
  'admin.groups': 'Группы',
  'admin.tournaments': 'Турниры',
  'admin.data': 'Таблицы',
  'admin.accounts': 'Аккаунты',
  'admin.groupsCount': 'Группы',
  'admin.playersCount': 'Игроки',
  'admin.tournamentsCount': 'Турниры',
  'admin.health': 'Состояние',
  'admin.noName': 'Без имени',
  'admin.noWayIn': 'Нет способов входа',
  'admin.noPlayers': 'Не привязан ни к кому',
  'admin.lastSeen': 'Последний раз',
  'admin.never': 'никогда',
  'admin.badge': 'админ',
  'admin.detach': 'отвязать',
  'admin.nameLabel': 'Как зовут',
  'admin.save': 'Сохранить',
  'admin.mergeInto': 'присоединить к…',
  'admin.merge': 'присоединить',
  'admin.nothingToMove': 'ничего, кроме способа входа',
  'admin.confirmMerge': 'Присоединить эту запись к выбранной? Переедет — {rows}. Эта запись будет удалена, отменить нельзя.',
  'admin.delete': 'удалить',
  'admin.confirmDelete': 'Удалить «{name}»? Вместе с ней исчезнут игроки: {players} и турниры: {tournaments}. Это необратимо.',
  'admin.confirmDetach': 'Отвязать {name} от этого аккаунта?',
  'admin.deleted': 'Удалено: «{name}», игроков {players}, турниров {tournaments}.',
  'admin.withheld': 'Не показываются: {columns}',
  'admin.showing': 'Показано {shown} из {total}',
  'archive.yourPlace': 'ваше место',
  'home.yourTournaments': 'Ваши турниры',
  'home.noTournaments': 'Пока ничего. Турниры появятся здесь, когда вы сыграете — или когда владелец группы привяжет к вам игрока.',
  'roster.claimed': 'привязан',
  'roster.copy': 'Копировать',
  'roster.copied': 'Скопировано',
  'roster.inviteExplain': 'Ссылка для {name}. Отправьте её — тот, кто откроет, станет этим игроком, и вся его статистика будет его.',
  'roster.inviteTerms': 'Сработает один раз и действует 7 дней.',
  'roster.invite': 'пригласить',
  'roster.remove': 'убрать',
  'roster.cancel': 'отмена',
  'roster.ok': 'ОК',
  'roster.newNameFor': 'Новое имя для {name}',
  'roster.inviteLinkFor': 'Ссылка-приглашение для {name}',
  'roster.addPlayer': 'Добавить игрока',
  'roster.addPlaceholder': 'Аня',
  'roster.add': 'Добавить',
  'roster.adding': 'Добавляем…',
  'roster.renameFailed': 'Не переименовался',
  'roster.removeFailed': 'Не убрался',
  'roster.inviteFailed': 'Не выписалось',
  'roster.addFailed': 'Не добавился',

  // ─────────────────────────────────────────────────────────────── court
  'court.number': 'Корт {court}',
  'court.live': 'Идёт',
  'court.roundOf': 'раунд из {total}',
  'court.roundDone': 'доигран',
  'court.fixScore': 'исправить счёт',
  'court.prevRound': 'Предыдущий раунд',
  'court.nextRound': 'Следующий раунд',
  'court.pointsFor': 'Очки пары {pair}',
  'court.ok': 'ОК',
  'court.scoreFailed': 'Не записалось',

  // ─────────────────────────────────────────────────────────────── figures
  'podium.title': 'Пьедестал',
  'podium.points': '{points} очков',
  'standings.title': 'Таблица',
  'standings.place': 'Место',
  'standings.player': 'Игрок',
  'standings.matches': 'Матчи',
  'standings.wins': 'Победы',
  'standings.points': 'Очки',
  'standings.diff': 'Разница',

  'climb.title': 'Ход турнира',
  'climb.subtitle': 'места по раундам',
  'climb.aria': 'Места по раундам. Лидирует {name}.',

  'format.americano': 'Американо',
  'format.mexicano': 'Мексикано',

  'api.requestFailed': 'Запрос не прошёл ({status})',
  'api.empty': 'Пусто',

  // ─────────────────────────────────────────────────────────────── counting
  'company.title': 'С кем и против кого',
  'company.partners': 'В паре с',
  'company.opponents': 'Против',
  'count.matches.one': 'матч',
  'count.matches.few': 'матча',
  'count.matches.many': 'матчей',
  'count.matches.other': 'матча',
  'count.players.one': 'игрок',
  'count.players.few': 'игрока',
  'count.players.many': 'игроков',
  'count.players.other': 'игрока',
  'count.rounds.one': 'раунд',
  'count.rounds.few': 'раунда',
  'count.rounds.many': 'раундов',
  'count.rounds.other': 'раунда',
  'count.courts.one': 'корт',
  'count.courts.few': 'корта',
  'count.courts.many': 'кортов',
  'count.courts.other': 'корта',

  // ─────────────────────────────────────────── refusals, keyed by the server's code
  'error.not_signed_in': 'Нужно войти',
  'error.forbidden': 'Так нельзя',
  'error.not_a_member': 'Вы не состоите в этой группе',
  'error.not_the_owner': 'Это может сделать только владелец группы',
  'error.not_the_organiser': 'Это может сделать только тот, кто начал турнир',
  'error.not_on_this_court': 'Счёт вносит тот, кто играл этот матч, или организатор',
  'error.group_not_found': 'Такой группы нет',
  'error.player_not_found': 'Такого игрока нет',
  'error.tournament_not_found': 'Такого турнира нет',
  'error.duplicate_group_name': 'Группа с таким названием уже есть',
  'error.duplicate_player_name': 'Такое имя в группе уже занято',
  'error.player_not_in_group': 'Этот игрок из другой группы',
  'error.inactive_player': 'Этот игрок больше не в составе',
  'error.active_tournament_exists': 'В этой группе уже идёт турнир — сначала завершите его',
  'error.invalid_token': 'Ссылка недействительна — запросите новую',
  'error.token_expired': 'Ссылка устарела — запросите новую',
  'error.too_many_requests': 'Письмо уже отправлено — проверьте почту',
  'error.invite_not_found': 'Приглашение не найдено',
  'error.invite_used': 'Приглашение уже использовано',
  'error.player_already_claimed': '{name} уже занят(а)',
  'error.already_playing_here': 'В этой группе вы уже {name}',
  'error.no_active_tournament': 'Сейчас нет активного турнира',
  'error.no_tournaments_yet': 'Турниров ещё не было',
  'error.unidentified_caller': 'Не вижу, от кого сообщение',
  'error.invalid_config': 'Такие настройки не сходятся',
  'error.invalid_player_count': 'Игроков должно быть кратно четырём',
  'error.unsupported_player_count': 'Для такого числа игроков расписания пока нет',
  'error.duplicate_player': 'Один и тот же игрок дважды в составе',
  'error.table_not_found': 'Такой таблицы нет',
  'error.unknown_match': 'Такого матча нет',
  'error.invalid_score': 'Счёт не сходится с матчем',
  'error.result_already_recorded': 'Счёт уже записан — исправьте его',
  'error.round_incomplete': 'В этом раунде сыграно не всё',
  'error.reroll_too_late': 'Пересдавать можно только до первого результата',
  'error.tournament_finished': 'Турнир уже завершён',
  'error.no_more_rounds': 'Раунды кончились',
  'error.wrong_format': 'Так в этом формате нельзя',
} as const

export type Key = keyof typeof ru

/**
 * The same keys in English. Typed against `ru`, so leaving one out does not compile.
 *
 * The `count.*.few` and `count.*.many` entries are unused here — English has two plural
 * categories, not four — but they are filled rather than skipped, because the alternative
 * is making the type partial, and a partial type is how a missing phrase becomes a blank.
 */
export const en: Record<Key, string> = {
  'nav.signIn': 'Sign in',
  'nav.signOut': 'Sign out',
  'nav.home': '← Home',
  'nav.toGroup': '← Back to group',
  'nav.language': 'Language',

  'async.loading': 'Loading',
  'async.failedTitle': 'Did not open',
  'async.failedBody': '{message}. Reload the page, or check the link.',
  'async.somethingWrong': 'Something went wrong',

  'notFound.title': 'No such page',
  'notFound.body': 'Check the link.',

  'home.formats': 'Americano · Mexicano',
  'home.tagline': 'Who plays with whom, who is ahead, and how that changed.',
  'home.startHere': 'Start here',
  'home.startBody':
    'Groups are private to their members. Follow the link from your inbox — or open an invitation, if somebody sent you one.',
  'home.telegramHint': 'Easier in Telegram: add the bot to a chat and send',
  'home.yourGroups': 'Your groups',
  'home.noGroups': 'None yet. Start one — you will own it.',
  'home.newGroup': 'New group',
  'home.newGroupPlaceholder': 'Tuesday padel',
  'home.create': 'Create',
  'home.creating': 'Creating…',
  'home.createFailed': 'Could not create it',

  'signIn.eyebrow': 'Sign in',
  'signIn.title': 'A link instead of a password',
  'signIn.body': 'Leave your address and we will send a link that takes you in. There is no password here.',
  'signIn.emailLabel': 'Email',
  'signIn.send': 'Send the link',
  'signIn.sending': 'Sending…',
  'signIn.failed': 'Could not send it',
  'signIn.checkMail': 'Check your inbox',
  'signIn.sentTo': 'A link is on its way to {email}. It lasts fifteen minutes and works once.',

  'enter.noToken': 'The link carries no token',
  'enter.failed': 'The link did not work',
  'enter.title': 'Not signed in',
  'enter.askNew': 'Ask for a new link',

  'invite.notFound': 'No such invitation',
  'invite.eyebrow': 'Invitation',
  'invite.youAre': 'You are {name}',
  'invite.body': 'Accept and you get your own match history, and can enter scores for your games.',
  'invite.accept': 'Play as {name}',
  'invite.accepting': 'Accepting…',
  'invite.signInFirst': 'Sign in first, so the invitation stays yours.',
  'invite.signInAndContinue': 'Sign in and continue',
  'invite.failed': 'That did not work',

  'group.nowPlaying': '{format} in progress — round {round} of {total}',
  'group.nobodyPlaying': 'Nobody is playing right now',
  'group.toTournament': 'Go to the tournament',
  'group.assemble': 'Start a tournament',
  'group.archive': 'Past tournaments',
  'group.noneYet': 'None yet',
  'group.assembleFirst': 'Start the first one — it will show up here.',
  'group.someoneWill': 'As soon as somebody starts a tournament, it will show up here.',
  'group.playedOf': '{played} of {total} played',
  'group.winner': 'winner',

  'player.eyebrow': 'Player',
  'player.summary': 'Summary',
  'player.tournaments': 'Tournaments',
  'player.matches': 'Matches',
  'player.wins': 'Wins',
  'player.pointsPerMatch': 'Points per match',
  'player.bestRank': 'Best finish',
  'player.podiums': 'Podiums',
  'player.history': 'Tournaments',
  'player.neverPlayed': 'Has not played yet',
  'player.neverPlayedBody': 'Play a tournament — it will show up here.',

  'tournament.finished': 'Finished',
  'tournament.live': 'In progress',
  'tournament.matchTo': 'to {points}',
  'tournament.nextRound': 'Next round',
  'tournament.reroll': 'Redraw',
  'tournament.finish': 'Finish',
  'tournament.actionFailed': 'That did not work',

  'draw.title': 'Start a tournament',
  'draw.pickWho': 'Tick who is playing',
  'draw.whoPlays': 'Who is playing',
  'draw.needMultiple': 'needs 4, 8, 12, 16…',
  'draw.rules': 'Rules',
  'draw.format': 'Format',
  'draw.americanoHint': 'everyone partners everyone',
  'draw.mexicanoHint': 'pairs from the table',
  'draw.matchTo': 'Match to',
  'draw.pairs': 'Pairs',
  'draw.crossover': 'Crossover',
  'draw.crossoverHint': '1+4 vs 2+3',
  'draw.split': 'Split',
  'draw.splitHint': '1+3 vs 2+4',
  'draw.topHeavy': 'Top-heavy',
  'draw.topHeavyHint': '1+2 vs 3+4',
  'draw.rounds': 'Rounds',
  'draw.go': 'Draw',
  'draw.going': 'Drawing…',
  'draw.failed': 'Could not draw it',

  'roster.title': 'Roster',
  'roster.rename': 'rename',
  'nav.admin': 'Admin',
  'admin.eyebrow': 'ADMINISTRATORS ONLY',
  'admin.title': 'Administration',
  'admin.notYou': 'This section is for administrators. If that seems wrong, check which door you came in by: email and the bot create different accounts.',
  'admin.overview': 'Overview',
  'admin.people': 'People',
  'admin.groups': 'Groups',
  'admin.tournaments': 'Tournaments',
  'admin.data': 'Tables',
  'admin.accounts': 'Accounts',
  'admin.groupsCount': 'Groups',
  'admin.playersCount': 'Players',
  'admin.tournamentsCount': 'Tournaments',
  'admin.health': 'Health',
  'admin.noName': 'No name',
  'admin.noWayIn': 'No way in',
  'admin.noPlayers': 'Attached to nobody',
  'admin.lastSeen': 'Last seen',
  'admin.never': 'never',
  'admin.badge': 'admin',
  'admin.detach': 'detach',
  'admin.nameLabel': 'Name',
  'admin.save': 'Save',
  'admin.mergeInto': 'merge into…',
  'admin.merge': 'merge',
  'admin.nothingToMove': 'nothing but the way in',
  'admin.confirmMerge': 'Merge this account into the chosen one? Moving: {rows}. This account is deleted, and there is no undo.',
  'admin.delete': 'delete',
  'admin.confirmDelete': 'Delete "{name}"? It takes {players} players and {tournaments} tournaments with it. There is no undo.',
  'admin.confirmDetach': 'Detach {name} from this account?',
  'admin.deleted': 'Deleted "{name}": {players} players, {tournaments} tournaments.',
  'admin.withheld': 'Withheld: {columns}',
  'admin.showing': 'Showing {shown} of {total}',
  'archive.yourPlace': 'your place',
  'home.yourTournaments': 'Your tournaments',
  'home.noTournaments': 'Nothing yet. Tournaments appear here once you play — or once a group owner attaches a player to you.',
  'roster.claimed': 'claimed',
  'roster.copy': 'Copy',
  'roster.copied': 'Copied',
  'roster.inviteExplain': 'A link for {name}. Send it — whoever opens it becomes this player, and the history becomes theirs.',
  'roster.inviteTerms': 'Works once, and lasts seven days.',
  'roster.invite': 'invite',
  'roster.remove': 'remove',
  'roster.cancel': 'cancel',
  'roster.ok': 'OK',
  'roster.newNameFor': 'New name for {name}',
  'roster.inviteLinkFor': 'Invitation link for {name}',
  'roster.addPlayer': 'Add a player',
  'roster.addPlaceholder': 'Anya',
  'roster.add': 'Add',
  'roster.adding': 'Adding…',
  'roster.renameFailed': 'Could not rename',
  'roster.removeFailed': 'Could not remove',
  'roster.inviteFailed': 'Could not issue it',
  'roster.addFailed': 'Could not add',

  'court.number': 'Court {court}',
  'court.live': 'Playing',
  'court.roundOf': 'of {total} rounds',
  'court.roundDone': 'played out',
  'court.fixScore': 'fix the score',
  'court.prevRound': 'Previous round',
  'court.nextRound': 'Next round',
  'court.pointsFor': 'Points for {pair}',
  'court.ok': 'OK',
  'court.scoreFailed': 'Could not save it',

  'podium.title': 'Podium',
  'podium.points': '{points} points',
  'standings.title': 'Table',
  'standings.place': 'Place',
  'standings.player': 'Player',
  'standings.matches': 'Matches',
  'standings.wins': 'Wins',
  'standings.points': 'Points',
  'standings.diff': 'Diff',

  'climb.title': 'How it went',
  'climb.subtitle': 'places by round',
  'climb.aria': 'Places by round. {name} is leading.',

  'format.americano': 'Americano',
  'format.mexicano': 'Mexicano',

  'api.requestFailed': 'The request failed ({status})',
  'api.empty': 'Empty',

  'company.title': 'With and against',
  'company.partners': 'Partnered',
  'company.opponents': 'Faced',
  'count.matches.one': 'match',
  'count.matches.few': 'matches',
  'count.matches.many': 'matches',
  'count.matches.other': 'matches',
  'count.players.one': 'player',
  'count.players.few': 'players',
  'count.players.many': 'players',
  'count.players.other': 'players',
  'count.rounds.one': 'round',
  'count.rounds.few': 'rounds',
  'count.rounds.many': 'rounds',
  'count.rounds.other': 'rounds',
  'count.courts.one': 'court',
  'count.courts.few': 'courts',
  'count.courts.many': 'courts',
  'count.courts.other': 'courts',

  'error.not_signed_in': 'Sign in to see this',
  'error.forbidden': 'Not allowed',
  'error.not_a_member': 'You are not a member of this group',
  'error.not_the_owner': 'Only the group owner can do this',
  'error.not_the_organiser': 'Only whoever started this tournament can do this',
  'error.not_on_this_court': 'Scores are entered by whoever played the match, or the organiser',
  'error.group_not_found': 'No such group',
  'error.player_not_found': 'No such player',
  'error.tournament_not_found': 'No such tournament',
  'error.duplicate_group_name': 'A group with that name already exists',
  'error.duplicate_player_name': 'That name is already taken in this group',
  'error.player_not_in_group': 'That player belongs to another group',
  'error.inactive_player': 'That player is no longer on the roster',
  'error.active_tournament_exists': 'This group already has a tournament running — finish it first',
  'error.invalid_token': 'This link is not valid — ask for a new one',
  'error.token_expired': 'This link has expired — ask for a new one',
  'error.too_many_requests': 'A link is already on its way — check your inbox',
  'error.invite_not_found': 'No such invitation',
  'error.invite_used': 'That invitation has already been accepted',
  'error.player_already_claimed': '{name} is already claimed',
  'error.already_playing_here': 'In this group you already play as {name}',
  'error.no_active_tournament': 'No tournament is running right now',
  'error.no_tournaments_yet': 'No tournaments have been played yet',
  'error.unidentified_caller': 'Cannot tell who this came from',
  'error.invalid_config': 'Those settings do not add up',
  'error.invalid_player_count': 'The number of players has to be a multiple of four',
  'error.unsupported_player_count': 'No schedule is known for that many players',
  'error.duplicate_player': 'The same player appears twice',
  'error.table_not_found': 'No such table',
  'error.unknown_match': 'No such match',
  'error.invalid_score': 'That score does not add up to the match total',
  'error.result_already_recorded': 'That match already has a score — correct it instead',
  'error.round_incomplete': 'This round is not played out yet',
  'error.reroll_too_late': 'Redrawing is only possible before the first result',
  'error.tournament_finished': 'This tournament is over',
  'error.no_more_rounds': 'No rounds left',
  'error.wrong_format': 'That does not apply to this format',
}

export const DICTIONARIES: Record<Locale, Record<Key, string>> = { ru, en }

/** Bases that get counted. Each needs the four plural categories in the dictionary. */
export type Countable = 'players' | 'rounds' | 'courts' | 'matches'

export type Params = Record<string, string | number>

function fill(template: string, params?: Params): string {
  if (!params) return template
  return template.replace(/\{(\w+)\}/g, (whole, name: string) =>
    name in params ? String(params[name]) : whole,
  )
}

export function isLocale(value: string | null): value is Locale {
  return value === 'ru' || value === 'en'
}

/** Stored choice, then what the browser is set to, then Russian. */
export function preferredLocale(stored: string | null, browser: string): Locale {
  if (isLocale(stored)) return stored
  return browser.toLowerCase().startsWith('en') ? 'en' : 'ru'
}

export interface Translate {
  (key: Key, params?: Params): string
  /** "8 игроков" / "8 players", with the category `Intl` picks for this language. */
  count(what: Countable, n: number): string
  date(iso: string): string
  /** A thrown failure, said in this language. */
  say(failure: unknown): string
  locale: Locale
}

export function translator(locale: Locale, describe: (failure: unknown) => string): Translate {
  const words = DICTIONARIES[locale]
  const rules = new Intl.PluralRules(locale)
  const dates = new Intl.DateTimeFormat(locale, { day: 'numeric', month: 'long' })

  const t = ((key: Key, params?: Params) => fill(words[key], params)) as Translate

  t.count = (what: Countable, n: number) => {
    const category = rules.select(n)
    const key = `count.${what}.${category}` as Key
    // `Intl` can return categories a language does not use (`two`, `zero`); falling back to
    // `other` is what those mean anyway, and beats printing "undefined" next to a number.
    return `${n} ${words[key] ?? words[`count.${what}.other` as Key]}`
  }
  t.date = (iso: string) => dates.format(new Date(iso))
  t.say = describe
  t.locale = locale

  return t
}
