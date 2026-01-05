from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
import logging
from enum import IntEnum
import json
import os
import asyncio
import time

# Настройка логирования
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Конфигурация
BOT_TOKEN = '8275792067:AAFkuxFjLrpsvInoheghSYIenRIqVLiBfCM'
GROUP_CHAT_ID = -1002418857530  # ID вашей группы с темами

# ID тем
MODERATOR_REPORT_TOPIC_ID = 14  # Тема: отчетность модерации (модератор, ст.модератор)
ADMIN_REPORT_TOPIC_ID = 13  # Тема: отчетность администрации (мл.админ, админ, СЗМ)
ACCEPTED_MODERATOR_TOPIC_ID = 17849  # Принятые отчеты модераторов
REJECTED_MODERATOR_TOPIC_ID = 17852  # Отклоненные отчеты модераторов
ACCEPTED_ADMIN_TOPIC_ID = 17854  # Принятые отчеты админов
REJECTED_ADMIN_TOPIC_ID = 17856  # Отклоненные отчеты админов
WARNINGS_TOPIC_ID = 2976  # УКАЖИТЕ ID темы для выговоров

# Путь для постоянного хранилища (Railway Volume)
DATA_DIR = '/app/data'

# Создаем директорию если её нет (для локального тестирования)
os.makedirs(DATA_DIR, exist_ok=True)

# Файлы для хранения данных (в Volume)
STATS_FILE = os.path.join(DATA_DIR, 'report_stats.json')
WARNINGS_FILE = os.path.join(DATA_DIR, 'warnings_data.json')

# Время до удаления сообщений (в секундах)
DELETE_AFTER_SECONDS = 60  # 1 минута

# Кулдаун для команды /stats (в секундах)
STATS_COOLDOWN = 10

# Максимальное количество выговоров
MAX_WARNINGS = 3

# Username зама главного админа для оповещений
DEPUTY_ADMIN_USERNAME = 'the_pr1estesss'

# Словарь для хранения времени последнего использования /stats
stats_cooldowns = {}

# Иерархия ролей
class Role(IntEnum):
    """Роли в порядке убывания полномочий"""
    ГЛАВНЫЙ_АДМИН = 7
    ЗАМ_ГЛАВНОГО = 6
    СТАРШИЙ_АДМИН = 5
    СЗМ = 4
    АДМИН = 3
    МЛ_АДМИН = 2
    СТАРШИЙ_МОДЕРАТОР = 1
    МОДЕРАТОР = 0

# Список пользователей с их ролями (username: роль)
USERS_ROLES = {
    # ГЛАВНЫЙ АДМИН (не упоминается в отчетах, но может проверять)
    'главный_админ': Role.ГЛАВНЫЙ_АДМИН,  # УКАЖИТЕ USERNAME ГЛАВНОГО АДМИНА

    # Проверяющие всех (не сдают отчеты)
    'the_pr1estesss': Role.ЗАМ_ГЛАВНОГО,
    'qwertyuiopasdfghjklzxcvbnm123411': Role.СТАРШИЙ_АДМИН,
    'mskmboky': Role.СТАРШИЙ_АДМИН,

    # Проверяющие только модераторов (сдают отчеты в администрацию)
    'whysparky': Role.СЗМ,
    'maga8c': Role.АДМИН,
    'admin_user2': Role.АДМИН,

    # Сдают отчеты в администрацию
    'anayka_lol': Role.МЛ_АДМИН,
    'ml_admin2': Role.МЛ_АДМИН,

    # Сдают отчеты в модерацию
    'matnozdra': Role.СТАРШИЙ_МОДЕРАТОР,
    'st_moder2': Role.СТАРШИЙ_МОДЕРАТОР,
    'breakbrosmiling': Role.МОДЕРАТОР,
    'bosspogranki': Role.МОДЕРАТОР,
    'spearskill': Role.МОДЕРАТОР,
    'neverexikid': Role.МОДЕРАТОР,
    'finn_wolfhard1223': Role.МОДЕРАТОР,
    'miwa123009': Role.МОДЕРАТОР,
    'sportaisam': Role.МОДЕРАТОР,
    'rusich_group35': Role.МОДЕРАТОР,
    'za_spartakmsk': Role.МОДЕРАТОР,
    'moder2': Role.МОДЕРАТОР,
}

# Словарь для хранения информации об отчетах
reports_data = {}

# ===== ФУНКЦИИ ДЛЯ СТАТИСТИКИ =====

def load_stats():
    """Загрузить статистику из файла"""
    if os.path.exists(STATS_FILE):
        try:
            with open(STATS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Ошибка загрузки статистики: {e}")
            return {}
    return {}

def save_stats(stats):
    """Сохранить статистику в файл"""
    try:
        with open(STATS_FILE, 'w', encoding='utf-8') as f:
            json.dump(stats, f, ensure_ascii=False, indent=2)
        logger.info(f"Stats saved to {STATS_FILE}")
    except Exception as e:
        logger.error(f"Ошибка сохранения статистики: {e}")

def get_user_stats(user_id: int):
    """Получить статистику пользователя"""
    stats = load_stats()
    user_key = str(user_id)

    if user_key not in stats:
        stats[user_key] = {
            'accepted': 0,
            'rejected': 0,
            'name': ''
        }

    return stats[user_key]

def get_user_stats_by_username(username: str):
    """Получить статистику пользователя по username"""
    stats = load_stats()

    # Ищем пользователя по имени
    for user_id, data in stats.items():
        if data.get('name', '').lower() == username.lower():
            return user_id, data

    return None, None

def update_user_stats(user_id: int, user_name: str, action: str):
    """Обновить статистику пользователя"""
    stats = load_stats()
    user_key = str(user_id)

    if user_key not in stats:
        stats[user_key] = {
            'accepted': 0,
            'rejected': 0,
            'name': user_name
        }

    stats[user_key]['name'] = user_name

    if action == 'accept':
        stats[user_key]['accepted'] += 1
    elif action == 'reject':
        stats[user_key]['rejected'] += 1

    save_stats(stats)
    return stats[user_key]

# ===== ФУНКЦИИ ДЛЯ ВЫГОВОРОВ =====

def load_warnings():
    """Загрузить данные о выговорах из файла"""
    if os.path.exists(WARNINGS_FILE):
        try:
            with open(WARNINGS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Ошибка загрузки выговоров: {e}")
            return {}
    return {}

def save_warnings(warnings):
    """Сохранить данные о выговорах в файл"""
    try:
        with open(WARNINGS_FILE, 'w', encoding='utf-8') as f:
            json.dump(warnings, f, ensure_ascii=False, indent=2)
        logger.info(f"Warnings saved to {WARNINGS_FILE}")
    except Exception as e:
        logger.error(f"Ошибка сохранения выговоров: {e}")

def get_user_warnings(user_id: int):
    """Получить количество выговоров пользователя"""
    warnings = load_warnings()
    user_key = str(user_id)

    if user_key not in warnings:
        warnings[user_key] = {
            'count': 0,
            'name': '',
            'username': '',
            'history': []
        }

    return warnings[user_key]

def add_warning(user_id: int, user_name: str, username: str, reason: str, issued_by: str):
    """Добавить выговор пользователю"""
    warnings = load_warnings()
    user_key = str(user_id)

    if user_key not in warnings:
        warnings[user_key] = {
            'count': 0,
            'name': user_name,
            'username': username,
            'history': []
        }

    warnings[user_key]['count'] += 1
    warnings[user_key]['name'] = user_name
    warnings[user_key]['username'] = username
    warnings[user_key]['history'].append({
        'reason': reason,
        'issued_by': issued_by,
        'timestamp': str(time.time()),
        'action': 'added'
    })

    save_warnings(warnings)
    return warnings[user_key]['count']

def remove_warning(user_id: int, removed_by: str):
    """Снять выговор с пользователя"""
    warnings = load_warnings()
    user_key = str(user_id)

    if user_key not in warnings or warnings[user_key]['count'] == 0:
        return None  # Нет выговоров для снятия

    warnings[user_key]['count'] -= 1
    warnings[user_key]['history'].append({
        'reason': 'Выговор снят',
        'issued_by': removed_by,
        'timestamp': str(time.time()),
        'action': 'removed'
    })

    save_warnings(warnings)
    return warnings[user_key]['count']

# ===== КОНЕЦ ФУНКЦИЙ ДЛЯ ВЫГОВОРОВ =====

async def delete_messages_after_delay(context: ContextTypes.DEFAULT_TYPE, chat_id: int, message_ids: list, delay: int):
    """Удалить сообщения через заданное время"""
    await asyncio.sleep(delay)

    for msg_id in message_ids:
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=msg_id)
            logger.info(f"Deleted message {msg_id} from chat {chat_id}")
        except Exception as e:
            logger.error(f"Failed to delete message {msg_id}: {e}")

def get_user_role(username: str) -> Role:
    """Получить роль пользователя по username"""
    if not username:
        logger.warning("Username is None or empty")
        return None
    clean_username = username.lstrip('@').lower()
    logger.info(f"Checking role for username: {clean_username}")
    return USERS_ROLES.get(clean_username)

def can_check_report(checker_role: Role, report_type: str) -> bool:
    """Проверка прав на проверку отчетов"""
    if checker_role is None:
        return False

    if checker_role >= Role.СТАРШИЙ_АДМИН:
        return True

    if checker_role >= Role.АДМИН and report_type == 'moderator':
        return True

    return False

def can_issue_warning(user_role: Role) -> bool:
    """Проверка прав на выдачу выговоров (СЗМ и выше)"""
    if user_role is None:
        return False
    return user_role >= Role.СЗМ

def can_remove_warning(user_role: Role) -> bool:
    """Проверка прав на снятие выговоров (СЗМ и выше)"""
    if user_role is None:
        return False
    return user_role >= Role.СЗМ

def can_view_others_stats(user_role: Role) -> bool:
    """Проверка прав на просмотр чужой статистики (СЗМ и выше)"""
    if user_role is None:
        return False
    return user_role >= Role.СЗМ

def get_report_category(user_role: Role) -> str:
    """Определить категорию отчета по роли отправителя"""
    if user_role is None:
        return None

    if user_role <= Role.СТАРШИЙ_МОДЕРАТОР:
        return 'moderator'

    if Role.МЛ_АДМИН <= user_role <= Role.СЗМ:
        return 'admin'

    return None

def get_topic_ids_for_category(category: str) -> dict:
    """Получить ID тем для категории отчета"""
    if category == 'moderator':
        return {
            'report': MODERATOR_REPORT_TOPIC_ID,
            'accepted': ACCEPTED_MODERATOR_TOPIC_ID,
            'rejected': REJECTED_MODERATOR_TOPIC_ID
        }
    elif category == 'admin':
        return {
            'report': ADMIN_REPORT_TOPIC_ID,
            'accepted': ACCEPTED_ADMIN_TOPIC_ID,
            'rejected': REJECTED_ADMIN_TOPIC_ID
        }
    return None

def get_checkers_usernames(category: str) -> list:
    """Получить список юзернеймов проверяющих для категории (БЕЗ главного админа)"""
    if category == 'moderator':
        return [username for username, role in USERS_ROLES.items() 
                if Role.АДМИН <= role < Role.ГЛАВНЫЙ_АДМИН and username]
    elif category == 'admin':
        return [username for username, role in USERS_ROLES.items() 
                if Role.СТАРШИЙ_АДМИН <= role < Role.ГЛАВНЫЙ_АДМИН and username]
    return []

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /start"""
    user_role = get_user_role(update.message.from_user.username)
    role_name = user_role.name if user_role else "Не назначена"

    message_text = (
        "✅ Бот для проверки отчетов модерации запущен!\n\n"
        f"👤 Ваша роль: {role_name}\n\n"
        "📋 Отправляйте отчеты в соответствующую тему:\n"
        "• Модераторы и ст.модераторы → Отчетность модерации\n"
        "• Мл.админы, админы, СЗМ → Отчетность администрации\n\n"
        "⚠️ Команды:\n"
        "/stats - ваша статистика отчетов\n"
        "/stats @username - статистика другого пользователя (СЗМ+)\n"
        "/vg - выдать выговор (ответ на сообщение + причина)\n"
        "/svg - снять выговор (ответ на сообщение)"
    )

    await update.message.reply_text(message_text)

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /stats - показать статистику (свою или чужую)"""
    message = update.message
    user = message.from_user
    user_role = get_user_role(user.username)

    # Проверка кулдауна
    current_time = time.time()
    user_key = str(user.id)

    if user_key in stats_cooldowns:
        time_passed = current_time - stats_cooldowns[user_key]
        if time_passed < STATS_COOLDOWN:
            cooldown_left = int(STATS_COOLDOWN - time_passed)
            cooldown_msg = await message.reply_text(
                f"⏳ Подождите {cooldown_left} секунд перед следующим использованием /stats"
            )

            # Удаляем сообщения через минуту
            asyncio.create_task(
                delete_messages_after_delay(
                    context,
                    message.chat.id,
                    [message.message_id, cooldown_msg.message_id],
                    DELETE_AFTER_SECONDS
                )
            )
            return

    # Обновляем время последнего использования
    stats_cooldowns[user_key] = current_time

    # Определяем чью статистику показывать
    target_user_id = None
    target_user_name = None
    target_username = None

    # Проверяем есть ли аргументы команды
    text = message.text.strip()
    parts = text.split(maxsplit=1)

    if len(parts) > 1:
        # Запрос статистики другого пользователя
        if not can_view_others_stats(user_role):
            error_msg = await message.reply_text(
                "❌ У вас нет прав для просмотра чужой статистики! (требуется СЗМ или выше)"
            )
            asyncio.create_task(
                delete_messages_after_delay(
                    context,
                    message.chat.id,
                    [message.message_id, error_msg.message_id],
                    DELETE_AFTER_SECONDS
                )
            )
            return

        # Парсим username или mention
        target_input = parts[1].lstrip('@')

        # Пытаемся найти через reply
        if message.reply_to_message:
            target_user = message.reply_to_message.from_user
            target_user_id = target_user.id
            target_user_name = target_user.full_name
            target_username = target_user.username or str(target_user_id)

        # Через entities (mention)
        elif message.entities:
            for entity in message.entities:
                if entity.type == "text_mention":
                    target_user = entity.user
                    target_user_id = target_user.id
                    target_user_name = target_user.full_name
                    target_username = target_user.username or str(target_user_id)
                    break

        # Через текстовый username
        if target_user_id is None:
            target_username = target_input
            # Ищем в сохраненной статистике
            found_id, found_data = get_user_stats_by_username(target_username)
            if found_id:
                target_user_id = int(found_id)
                target_user_name = found_data.get('name', f'@{target_username}')
            else:
                # Пользователь не найден
                error_msg = await message.reply_text(
                    f"❌ Пользователь @{target_username} не найден в статистике!\n"
                    f"Возможно, он еще не сдавал отчеты."
                )
                asyncio.create_task(
                    delete_messages_after_delay(
                        context,
                        message.chat.id,
                        [message.message_id, error_msg.message_id],
                        DELETE_AFTER_SECONDS
                    )
                )
                return
    else:
        # Показываем свою статистику
        target_user_id = user.id
        target_user_name = user.full_name
        target_username = user.username

    # Получаем статистику
    user_stats = get_user_stats(target_user_id)

    # Формируем сообщение
    if target_user_id == user.id:
        stats_message = (
            f"📊 <b>Ваша статистика отчетов</b>\n\n"
            f"👤 {target_user_name}\n"
            f"✅ Принятых: {user_stats['accepted']}\n"
            f"❌ Отклоненных: {user_stats['rejected']}\n"
            f"📝 Всего: {user_stats['accepted'] + user_stats['rejected']}"
        )
    else:
        stats_message = (
            f"📊 <b>Статистика отчетов пользователя</b>\n\n"
            f"👤 {target_user_name} (@{target_username})\n"
            f"✅ Принятых: {user_stats['accepted']}\n"
            f"❌ Отклоненных: {user_stats['rejected']}\n"
            f"📝 Всего: {user_stats['accepted'] + user_stats['rejected']}\n\n"
            f"🔍 Запросил: {user.mention_html()}"
        )

    stats_msg = await message.reply_text(stats_message, parse_mode='HTML')

    # Удаляем сообщения через минуту
    asyncio.create_task(
        delete_messages_after_delay(
            context,
            message.chat.id,
            [message.message_id, stats_msg.message_id],
            DELETE_AFTER_SECONDS
        )
    )

    logger.info(f"Stats viewed: {target_username} by {user.username}")

async def warning_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /vg - выдать выговор"""
    message = update.message

    if message.chat.id != GROUP_CHAT_ID:
        await message.reply_text("❌ Команда работает только в группе!")
        return

    issuer = message.from_user
    issuer_role = get_user_role(issuer.username)

    if not can_issue_warning(issuer_role):
        await message.reply_text("❌ У вас нет прав на выдачу выговоров! (требуется СЗМ или выше)")
        return

    target_user = None
    target_user_id = None
    target_user_name = None
    target_username = None
    reason = None

    if message.reply_to_message:
        target_user = message.reply_to_message.from_user
        target_user_id = target_user.id
        target_user_name = target_user.full_name
        target_username = target_user.username or str(target_user_id)

        text = message.text.strip()
        parts = text.split(maxsplit=1)
        if len(parts) < 2:
            await message.reply_text("❌ Укажите причину выговора!\n\nПример: /vg Нарушение правил")
            return
        reason = parts[1]

    elif message.entities:
        for entity in message.entities:
            if entity.type == "text_mention":
                target_user = entity.user
                target_user_id = target_user.id
                target_user_name = target_user.full_name
                target_username = target_user.username or str(target_user_id)

                text = message.text
                mention_end = entity.offset + entity.length
                reason = text[mention_end:].strip()

                if not reason:
                    await message.reply_text("❌ Укажите причину выговора!")
                    return
                break

            elif entity.type == "mention":
                text = message.text
                username_start = entity.offset
                username_end = entity.offset + entity.length
                mentioned_username = text[username_start:username_end].lstrip('@')

                reason = text[username_end:].strip()

                if not reason:
                    await message.reply_text("❌ Укажите причину выговора!")
                    return

                target_username = mentioned_username
                target_user_name = f"@{mentioned_username}"
                target_user_id = None
                break

    else:
        text = message.text.strip()
        parts = text.split(maxsplit=2)

        if len(parts) < 3:
            await message.reply_text(
                "❌ Неправильный формат!\n\n"
                "Используйте один из способов:\n"
                "1. Ответьте на сообщение: /vg причина\n"
                "2. Упомяните: /vg @username причина"
            )
            return

        target_username = parts[1].lstrip('@')
        reason = parts[2]
        target_user_name = f"@{target_username}"
        target_user_id = None

    if not target_username and not target_user_id:
        await message.reply_text(
            "❌ Не удалось определить пользователя!\n\n"
            "Попробуйте ответить на его сообщение командой /vg причина"
        )
        return

    if target_user_id is None:
        target_user_id = f"username_{target_username}"
        logger.info(f"Using simplified mode for {target_username}")

    warning_count = add_warning(
        target_user_id,
        target_user_name,
        target_username,
        reason,
        issuer.username or issuer.full_name
    )

    warning_emoji = "⚠️" if warning_count < MAX_WARNINGS else "🚫"

    if isinstance(target_user_id, int):
        user_link = f"<a href='tg://user?id={target_user_id}'>{target_user_name}</a>"
    else:
        user_link = f"@{target_username}"

    warning_message = (
        f"{warning_emoji} <b>ВЫГОВОР #{warning_count}/{MAX_WARNINGS}</b>\n\n"
        f"👤 Получатель: {user_link}\n"
        f"📝 Причина: {reason}\n"
        f"👨‍💼 Выдал: {issuer.mention_html()} (@{issuer.username})\n"
        f"🎖 Роль: {issuer_role.name}\n\n"
    )

    if warning_count < MAX_WARNINGS:
        warning_message += f"⚡️ Осталось выговоров до исключения: {MAX_WARNINGS - warning_count}"
    else:
        warning_message += (
            f"🚫 <b>КРИТИЧЕСКОЕ ПРЕДУПРЕЖДЕНИЕ!</b>\n"
            f"У пользователя {MAX_WARNINGS} выговора!\n"
            f"@{DEPUTY_ADMIN_USERNAME} требуется исключение из группы!"
        )

    await context.bot.send_message(
        chat_id=GROUP_CHAT_ID,
        message_thread_id=WARNINGS_TOPIC_ID,
        text=warning_message,
        parse_mode='HTML'
    )

    await message.reply_text(f"✅ Выговор #{warning_count} выдан {user_link}", parse_mode='HTML')

    logger.info(f"Warning issued: {target_username} by {issuer.username}, count: {warning_count}")

async def remove_warning_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /svg - снять выговор"""
    message = update.message

    if message.chat.id != GROUP_CHAT_ID:
        await message.reply_text("❌ Команда работает только в группе!")
        return

    issuer = message.from_user
    issuer_role = get_user_role(issuer.username)

    if not can_remove_warning(issuer_role):
        await message.reply_text("❌ У вас нет прав на снятие выговоров! (требуется СЗМ или выше)")
        return

    target_user = None
    target_user_id = None
    target_user_name = None
    target_username = None

    if message.reply_to_message:
        target_user = message.reply_to_message.from_user
        target_user_id = target_user.id
        target_user_name = target_user.full_name
        target_username = target_user.username or str(target_user_id)

    elif message.entities:
        for entity in message.entities:
            if entity.type == "text_mention":
                target_user = entity.user
                target_user_id = target_user.id
                target_user_name = target_user.full_name
                target_username = target_user.username or str(target_user_id)
                break

            elif entity.type == "mention":
                text = message.text
                username_start = entity.offset
                username_end = entity.offset + entity.length
                mentioned_username = text[username_start:username_end].lstrip('@')

                target_username = mentioned_username
                target_user_name = f"@{mentioned_username}"
                target_user_id = None
                break

    else:
        text = message.text.strip()
        parts = text.split(maxsplit=1)

        if len(parts) < 2:
            await message.reply_text(
                "❌ Неправильный формат!\n\n"
                "Используйте:\n"
                "1. Ответьте на сообщение: /svg\n"
                "2. Упомяните: /svg @username"
            )
            return

        target_username = parts[1].lstrip('@')
        target_user_name = f"@{target_username}"
        target_user_id = None

    if not target_username and not target_user_id:
        await message.reply_text("❌ Не удалось определить пользователя!")
        return

    if target_user_id is None:
        target_user_id = f"username_{target_username}"

    new_count = remove_warning(target_user_id, issuer.username or issuer.full_name)

    if new_count is None:
        await message.reply_text(f"❌ У пользователя @{target_username} нет выговоров для снятия!")
        return

    if isinstance(target_user_id, int):
        user_link = f"<a href='tg://user?id={target_user_id}'>{target_user_name}</a>"
    else:
        user_link = f"@{target_username}"

    remove_message = (
        f"✅ <b>ВЫГОВОР СНЯТ</b>\n\n"
        f"👤 Пользователь: {user_link}\n"
        f"📊 Текущее количество выговоров: {new_count}/{MAX_WARNINGS}\n"
        f"👨‍💼 Снял: {issuer.mention_html()} (@{issuer.username})\n"
        f"🎖 Роль: {issuer_role.name}"
    )

    await context.bot.send_message(
        chat_id=GROUP_CHAT_ID,
        message_thread_id=WARNINGS_TOPIC_ID,
        text=remove_message,
        parse_mode='HTML'
    )

    await message.reply_text(f"✅ Выговор снят! Осталось: {new_count}/{MAX_WARNINGS}", parse_mode='HTML')

    logger.info(f"Warning removed: {target_username} by {issuer.username}, new count: {new_count}")

async def handle_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка отчета"""
    message = update.message

    if message.chat.id != GROUP_CHAT_ID:
        return

    if not message.photo:
        return

    topic_id = message.message_thread_id

    logger.info(f"Received photo in topic_id: {topic_id}")

    if topic_id == MODERATOR_REPORT_TOPIC_ID:
        category = 'moderator'
    elif topic_id == ADMIN_REPORT_TOPIC_ID:
        category = 'admin'
    else:
        logger.info(f"Topic {topic_id} is not a report topic, ignoring")
        return

    sender = message.from_user
    logger.info(f"Report from: {sender.username} (ID: {sender.id})")

    sender_role = get_user_role(sender.username)
    expected_category = get_report_category(sender_role)

    logger.info(f"Sender role: {sender_role}, Expected category: {expected_category}, Actual category: {category}")

    if expected_category != category:
        if expected_category is None:
            await message.reply_text("❌ Ваша роль не требует сдачи отчетов!")
        else:
            correct_topic = "Отчетность модерации" if expected_category == 'moderator' else "Отчетность администрации"
            await message.reply_text(f"❌ Отправьте отчет в тему: {correct_topic}")
        return

    photo = message.photo[-1].file_id
    caption = message.caption or ""

    keyboard = [
        [
            InlineKeyboardButton("✅ Принять отчет", callback_data=f"accept_{category}_{message.message_id}"),
            InlineKeyboardButton("❌ Отклонить", callback_data=f"reject_{category}_{message.message_id}")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    checkers = get_checkers_usernames(category)
    checker_mentions = ' '.join([f"@{username}" for username in checkers])

    category_name = "МОДЕРАЦИИ" if category == 'moderator' else "АДМИНИСТРАЦИИ"

    user_stats = get_user_stats(sender.id)

    report_message = (
        f"📋 <b>НОВЫЙ ОТЧЕТ {category_name}</b>\n\n"
        f"👤 Отправил: {sender.mention_html()}\n"
        f"🎖 Роль: {sender_role.name if sender_role else 'Неизвестна'}\n"
        f"📊 Принятых отчетов: {user_stats['accepted']}\n"
        f"📝 Детали:\n{caption}\n\n"
        f"⚠️ Требуется проверка!\n"
        f"{checker_mentions}"
    )

    try:
        bot_message = await context.bot.send_photo(
            chat_id=GROUP_CHAT_ID,
            message_thread_id=topic_id,
            photo=photo,
            caption=report_message,
            reply_markup=reply_markup,
            parse_mode='HTML'
        )

        reports_data[f"{category}_{message.message_id}"] = {
            'photo': photo,
            'caption': caption,
            'sender_id': sender.id,
            'sender_name': sender.full_name,
            'sender_role': sender_role.name if sender_role else 'Неизвестна',
            'category': category,
            'original_message_id': message.message_id,
            'bot_message_id': bot_message.message_id,
            'user_message_id': message.message_id
        }

        logger.info(f"Report sent successfully for {sender.username}")
    except Exception as e:
        logger.error(f"Error sending report: {e}")

async def handle_button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка нажатия кнопок"""
    query = update.callback_query

    parts = query.data.split('_')
    action = parts[0]
    category = parts[1]
    report_id = parts[2]

    checker = query.from_user
    checker_role = get_user_role(checker.username)

    if not can_check_report(checker_role, category):
        category_name = "модераторов" if category == 'moderator' else "администрации"
        await query.answer(
            f"❌ У вас нет прав для проверки отчетов {category_name}!",
            show_alert=True
        )
        return

    await query.answer()

    report_key = f"{category}_{report_id}"
    if report_key not in reports_data:
        await query.edit_message_caption(
            caption=query.message.caption + "\n\n❌ Данные отчета не найдены",
            parse_mode='HTML'
        )
        return

    report = reports_data[report_key]

    updated_stats = update_user_stats(
        report['sender_id'], 
        report['sender_name'], 
        action
    )

    topics = get_topic_ids_for_category(category)
    if action == 'accept':
        target_topic_id = topics['accepted']
        status = "✅ ПРИНЯТ"
        status_emoji = "✅"
    else:
        target_topic_id = topics['rejected']
        status = "❌ ОТКЛОНЕН"
        status_emoji = "❌"

    category_name = "МОДЕРАЦИИ" if category == 'moderator' else "АДМИНИСТРАЦИИ"
    final_caption = (
        f"{status_emoji} <b>Отчет {category_name} {status}</b>\n\n"
        f"👤 Отправил: {report['sender_name']}\n"
        f"🎖 Роль: {report['sender_role']}\n"
        f"📊 Принятых отчетов: {updated_stats['accepted']}\n"
        f"📊 Отклоненных отчетов: {updated_stats['rejected']}\n"
        f"👨‍💼 Проверил: {checker.mention_html()} (@{checker.username})\n"
        f"🎖 Роль проверяющего: {checker_role.name}\n"
        f"📝 Детали:\n{report['caption']}"
    )

    await context.bot.send_photo(
        chat_id=GROUP_CHAT_ID,
        message_thread_id=target_topic_id,
        photo=report['photo'],
        caption=final_caption,
        parse_mode='HTML'
    )

    await query.edit_message_caption(
        caption=query.message.caption + f"\n\n{status} (@{checker.username})",
        parse_mode='HTML'
    )

    messages_to_delete = [
        report['user_message_id'],
        report['bot_message_id']
    ]

    asyncio.create_task(
        delete_messages_after_delay(
            context, 
            GROUP_CHAT_ID, 
            messages_to_delete, 
            DELETE_AFTER_SECONDS
        )
    )

    logger.info(f"Report {report_key} was {action}ed by @{checker.username}")

    del reports_data[report_key]

def main():
    """Запуск бота"""
    logger.info(f"Starting bot with data directory: {DATA_DIR}")
    logger.info(f"Stats file: {STATS_FILE}")
    logger.info(f"Warnings file: {WARNINGS_FILE}")

    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("vg", warning_command))
    application.add_handler(CommandHandler("svg", remove_warning_command))
    application.add_handler(MessageHandler(
        filters.PHOTO & filters.ChatType.SUPERGROUP, 
        handle_report
    ))
    application.add_handler(CallbackQueryHandler(handle_button_callback))

    logger.info("Бот запущен с улучшенной системой /stats!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
