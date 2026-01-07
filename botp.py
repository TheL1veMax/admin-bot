from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
import logging
from enum import IntEnum
import json
import os
import asyncio
import time
from datetime import datetime, timedelta

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = '8275792067:AAFkuxFjLrpsvInoheghSYIenRIqVLiBfCM'
GROUP_CHAT_ID = -1002418857530

MODERATOR_REPORT_TOPIC_ID = 14
ADMIN_REPORT_TOPIC_ID = 13
ACCEPTED_MODERATOR_TOPIC_ID = 17849
REJECTED_MODERATOR_TOPIC_ID = 17852
ACCEPTED_ADMIN_TOPIC_ID = 17854
REJECTED_ADMIN_TOPIC_ID = 17856
WARNINGS_TOPIC_ID = 2976
BLACKLIST_TOPIC_ID = 3680

DATA_DIR = '/app/data'
os.makedirs(DATA_DIR, exist_ok=True)

STATS_FILE = os.path.join(DATA_DIR, 'report_stats.json')
WARNINGS_FILE = os.path.join(DATA_DIR, 'warnings_data.json')
BLACKLIST_FILE = os.path.join(DATA_DIR, 'blacklist_data.json')
USER_IDS_FILE = os.path.join(DATA_DIR, 'user_ids.json')

DELETE_AFTER_SECONDS = 60
STATS_COOLDOWN = 10
MAX_WARNINGS = 3
DEPUTY_ADMIN_USERNAME = 'the_pr1estesss'

stats_cooldowns = {}

class Role(IntEnum):
    ГЛАВНЫЙ_АДМИН = 8
    СЗА = 7
    ЗАМ_ГЛАВНОГО = 6
    СТАРШИЙ_АДМИН = 5
    СЗМ = 4
    АДМИН = 3
    МЛ_АДМИН = 2
    СТАРШИЙ_МОДЕРАТОР = 1
    МОДЕРАТОР = 0

USERS_ROLES = {}
USERS_ROLES['glavnyy_admin'] = Role.ГЛАВНЫЙ_АДМИН
USERS_ROLES['gerrinetwork'] = Role.СЗА
USERS_ROLES['the_pr1estesss'] = Role.ЗАМ_ГЛАВНОГО
USERS_ROLES['qwertyuiopasdfghjklzxcvbnm123411'] = Role.СТАРШИЙ_АДМИН
USERS_ROLES['mskmboky'] = Role.СТАРШИЙ_АДМИН
USERS_ROLES['whysparky'] = Role.СЗМ
USERS_ROLES['maga8c'] = Role.АДМИН
USERS_ROLES['admin_user2'] = Role.АДМИН
USERS_ROLES['anayka_lol'] = Role.МЛ_АДМИН
USERS_ROLES['ml_admin2'] = Role.МЛ_АДМИН
USERS_ROLES['matnozdra'] = Role.СТАРШИЙ_МОДЕРАТОР
USERS_ROLES['st_moder2'] = Role.СТАРШИЙ_МОДЕРАТОР
USERS_ROLES['breakbrosmiling'] = Role.МОДЕРАТОР
USERS_ROLES['bosspogranki'] = Role.МОДЕРАТОР
USERS_ROLES['spearskill'] = Role.МОДЕРАТОР
USERS_ROLES['neverexikid'] = Role.МОДЕРАТОР
USERS_ROLES['finn_wolfhard1223'] = Role.МОДЕРАТОР
USERS_ROLES['miwa123009'] = Role.МОДЕРАТОР
USERS_ROLES['sportaisam'] = Role.МОДЕРАТОР
USERS_ROLES['rusich_group35'] = Role.МОДЕРАТОР
USERS_ROLES['za_spartakmsk'] = Role.МОДЕРАТОР

reports_data = {}

def load_user_ids():
    """Загрузка базы username -> user_id"""
    if os.path.exists(USER_IDS_FILE):
        try:
            with open(USER_IDS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Ошибка загрузки user_ids: {e}")
    return {}

def save_user_ids(user_ids):
    """Сохранение базы username -> user_id"""
    try:
        with open(USER_IDS_FILE, 'w', encoding='utf-8') as f:
            json.dump(user_ids, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Ошибка сохранения user_ids: {e}")

def register_user(user_id: int, username: str, full_name: str):
    """Регистрация пользователя в базе"""
    if not username:
        return
    user_ids = load_user_ids()
    clean_username = username.lower()
    user_ids[clean_username] = {
        'user_id': user_id,
        'username': username,
        'full_name': full_name,
        'last_seen': str(time.time())
    }
    save_user_ids(user_ids)

def find_user_id_by_username(username: str):
    """Поиск user_id по username"""
    user_ids = load_user_ids()
    clean_username = username.lower()
    if clean_username in user_ids:
        return user_ids[clean_username]['user_id'], user_ids[clean_username]['full_name']
    return None, None

def load_stats():
    if os.path.exists(STATS_FILE):
        try:
            with open(STATS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Ошибка загрузки статистики: {e}")
    return {}

def save_stats(stats):
    try:
        with open(STATS_FILE, 'w', encoding='utf-8') as f:
            json.dump(stats, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Ошибка сохранения статистики: {e}")

def get_user_stats(user_id: int):
    stats = load_stats()
    user_key = str(user_id)
    if user_key not in stats:
        stats[user_key] = {'accepted': 0, 'rejected': 0, 'name': ''}
    return stats[user_key]

def get_user_stats_by_username(username: str):
    stats = load_stats()
    for user_id, data in stats.items():
        if data.get('name', '').lower() == username.lower():
            return user_id, data
    return None, None

def update_user_stats(user_id: int, user_name: str, action: str):
    stats = load_stats()
    user_key = str(user_id)
    if user_key not in stats:
        stats[user_key] = {'accepted': 0, 'rejected': 0, 'name': user_name}
    stats[user_key]['name'] = user_name
    if action == 'accept':
        stats[user_key]['accepted'] += 1
    elif action == 'reject':
        stats[user_key]['rejected'] += 1
    save_stats(stats)
    return stats[user_key]

def reset_user_stats(user_id: int, stat_type: str):
    """Сброс статистики пользователя"""
    stats = load_stats()
    user_key = str(user_id)

    if user_key not in stats:
        return None

    old_value = stats[user_key].get(stat_type, 0)
    stats[user_key][stat_type] = 0
    save_stats(stats)

    return old_value

def load_warnings():
    if os.path.exists(WARNINGS_FILE):
        try:
            with open(WARNINGS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Ошибка загрузки выговоров: {e}")
    return {}

def save_warnings(warnings):
    try:
        with open(WARNINGS_FILE, 'w', encoding='utf-8') as f:
            json.dump(warnings, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Ошибка сохранения выговоров: {e}")

def add_warning(user_id: int, user_name: str, username: str, reason: str, issued_by: str):
    warnings = load_warnings()
    user_key = str(user_id)
    if user_key not in warnings:
        warnings[user_key] = {'count': 0, 'name': user_name, 'username': username, 'history': []}
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
    warnings = load_warnings()
    user_key = str(user_id)
    if user_key not in warnings or warnings[user_key]['count'] == 0:
        return None
    warnings[user_key]['count'] -= 1
    warnings[user_key]['history'].append({
        'reason': 'Выговор снят',
        'issued_by': removed_by,
        'timestamp': str(time.time()),
        'action': 'removed'
    })
    save_warnings(warnings)
    return warnings[user_key]['count']

def load_blacklist():
    if os.path.exists(BLACKLIST_FILE):
        try:
            with open(BLACKLIST_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Ошибка загрузки черного списка: {e}")
    return {}

def save_blacklist(blacklist):
    try:
        with open(BLACKLIST_FILE, 'w', encoding='utf-8') as f:
            json.dump(blacklist, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Ошибка сохранения черного списка: {e}")

def add_to_blacklist(user_id: int, user_name: str, username: str, days: int, reason: str, issued_by: str):
    blacklist = load_blacklist()
    user_key = str(user_id)

    start_date = datetime.now()
    end_date = start_date + timedelta(days=days)

    entry = {
        'name': user_name,
        'username': username,
        'days': days,
        'reason': reason,
        'issued_by': issued_by,
        'start_date': start_date.isoformat(),
        'end_date': end_date.isoformat(),
        'active': True
    }

    if user_key not in blacklist:
        blacklist[user_key] = {'history': []}

    blacklist[user_key]['current'] = entry
    blacklist[user_key]['history'].append(entry)

    save_blacklist(blacklist)
    return entry

def remove_from_blacklist(user_id: int):
    blacklist = load_blacklist()
    user_key = str(user_id)

    if user_key in blacklist and 'current' in blacklist[user_key]:
        blacklist[user_key]['current']['active'] = False
        del blacklist[user_key]['current']
        save_blacklist(blacklist)
        return True
    return False

def is_blacklisted(user_id: int):
    blacklist = load_blacklist()
    user_key = str(user_id)

    if user_key in blacklist and 'current' in blacklist[user_key]:
        entry = blacklist[user_key]['current']
        end_date = datetime.fromisoformat(entry['end_date'])

        if datetime.now() >= end_date:
            entry['active'] = False
            del blacklist[user_key]['current']
            save_blacklist(blacklist)
            return False, None

        return True, entry

    return False, None

async def delete_messages_after_delay(context: ContextTypes.DEFAULT_TYPE, chat_id: int, message_ids: list, delay: int):
    await asyncio.sleep(delay)
    for msg_id in message_ids:
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=msg_id)
        except Exception as e:
            logger.error(f"Failed to delete message {msg_id}: {e}")

def get_user_role(username: str) -> Role:
    if not username:
        return None
    clean_username = username.strip().lstrip('@').lower()
    return USERS_ROLES.get(clean_username)

def can_check_report(checker_role: Role, report_type: str) -> bool:
    if checker_role is None:
        return False
    if checker_role >= Role.СЗА:
        return True
    if checker_role >= Role.СТАРШИЙ_АДМИН:
        return True
    if checker_role >= Role.АДМИН and report_type == 'moderator':
        return True
    return False

def can_issue_warning(user_role: Role) -> bool:
    return user_role is not None and user_role >= Role.СЗМ

def can_remove_warning(user_role: Role) -> bool:
    return user_role is not None and user_role >= Role.СЗМ

def can_manage_blacklist(user_role: Role) -> bool:
    return user_role is not None and user_role >= Role.СЗМ

def can_view_others_stats(user_role: Role) -> bool:
    return user_role is not None and user_role >= Role.СЗМ

def can_reset_stats(user_role: Role) -> bool:
    return user_role is not None and user_role >= Role.СЗМ

def get_report_category(user_role: Role) -> str:
    if user_role is None:
        return None
    if user_role >= Role.СЗА:
        return None
    if user_role <= Role.СТАРШИЙ_МОДЕРАТОР:
        return 'moderator'
    if Role.МЛ_АДМИН <= user_role <= Role.СЗМ:
        return 'admin'
    return None

def get_topic_ids_for_category(category: str) -> dict:
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
    if category == 'moderator':
        return [username for username, role in USERS_ROLES.items() 
                if Role.АДМИН <= role < Role.ГЛАВНЫЙ_АДМИН]
    elif category == 'admin':
        return [username for username, role in USERS_ROLES.items() 
                if Role.СТАРШИЙ_АДМИН <= role < Role.ГЛАВНЫЙ_АДМИН]
    return []

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    register_user(user.id, user.username, user.full_name)

    user_role = get_user_role(user.username)
    role_name = user_role.name if user_role else "Не назначена"
    message_text = (
        "✅ Бот для проверки отчетов модерации запущен!\n\n"
        f"👤 Ваша роль: {role_name}\n\n"
        "📋 Отправляйте отчеты в соответствующую тему:\n"
        "• Модераторы и ст.модераторы → Отчетность модерации\n"
        "• Мл.админы, админы, СЗМ → Отчетность администрации\n"
        "• СЗА и Главный Админ → не сдают отчеты\n\n"
        "⚠️ Команды:\n"
        "/stats - ваша статистика отчетов\n"
        "/stats @username - статистика пользователя (СЗМ+)\n"
        "/vg - выдать выговор (СЗМ+)\n"
        "/svg - снять выговор (СЗМ+)\n"
        "/bl - добавить в черный список (СЗМ+)\n"
        "/ubl - убрать из черного списка (СЗМ+)\n"
        "/sp - сбросить принятые отчеты (СЗМ+)\n"
        "/so - сбросить отклоненные отчеты (СЗМ+)"
    )
    await update.message.reply_text(message_text)

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    user = message.from_user
    register_user(user.id, user.username, user.full_name)

    user_role = get_user_role(user.username)

    current_time = time.time()
    user_key = str(user.id)

    if user_key in stats_cooldowns:
        time_passed = current_time - stats_cooldowns[user_key]
        if time_passed < STATS_COOLDOWN:
            cooldown_left = int(STATS_COOLDOWN - time_passed)
            cooldown_msg = await message.reply_text(
                f"⏳ Подождите {cooldown_left} сек перед следующим использованием /stats"
            )
            asyncio.create_task(
                delete_messages_after_delay(context, message.chat.id, 
                                          [message.message_id, cooldown_msg.message_id], 
                                          DELETE_AFTER_SECONDS)
            )
            return

    stats_cooldowns[user_key] = current_time

    text = message.text.strip()
    parts = text.split(maxsplit=1)

    if len(parts) > 1:
        if not can_view_others_stats(user_role):
            error_msg = await message.reply_text(
                "❌ У вас нет прав для просмотра чужой статистики! (требуется СЗМ+)"
            )
            asyncio.create_task(
                delete_messages_after_delay(context, message.chat.id, 
                                          [message.message_id, error_msg.message_id], 
                                          DELETE_AFTER_SECONDS)
            )
            return

        target_username = parts[1].lstrip('@')
        target_user_id = None
        target_user_name = None

        if message.reply_to_message:
            target_user = message.reply_to_message.from_user
            target_user_id = target_user.id
            target_user_name = target_user.full_name
            target_username = target_user.username or str(target_user_id)
            register_user(target_user_id, target_user.username, target_user_name)
        elif message.entities:
            for entity in message.entities:
                if entity.type == "text_mention":
                    target_user = entity.user
                    target_user_id = target_user.id
                    target_user_name = target_user.full_name
                    target_username = target_user.username or str(target_user_id)
                    register_user(target_user_id, target_user.username, target_user_name)
                    break

        if target_user_id is None:
            found_id, found_data = get_user_stats_by_username(target_username)
            if found_id:
                target_user_id = int(found_id)
                target_user_name = found_data.get('name', f'@{target_username}')
            else:
                error_msg = await message.reply_text(
                    f"❌ Пользователь @{target_username} не найден в статистике!"
                )
                asyncio.create_task(
                    delete_messages_after_delay(context, message.chat.id, 
                                              [message.message_id, error_msg.message_id], 
                                              DELETE_AFTER_SECONDS)
                )
                return
    else:
        target_user_id = user.id
        target_user_name = user.full_name
        target_username = user.username

    user_stats = get_user_stats(target_user_id)
    target_role = get_user_role(target_username)
    role_name = target_role.name if target_role else "Не назначена"

    if target_user_id == user.id:
        stats_message = (
            f"📊 <b>Ваша статистика отчетов</b>\n\n"
            f"👤 {target_user_name}\n"
            f"🎖 Ранг: {role_name}\n"
            f"✅ Принятых: {user_stats['accepted']}\n"
            f"❌ Отклоненных: {user_stats['rejected']}\n"
            f"📝 Всего: {user_stats['accepted'] + user_stats['rejected']}"
        )
    else:
        stats_message = (
            f"📊 <b>Статистика отчетов пользователя</b>\n\n"
            f"👤 {target_user_name} (@{target_username})\n"
            f"🎖 Ранг: {role_name}\n"
            f"✅ Принятых: {user_stats['accepted']}\n"
            f"❌ Отклоненных: {user_stats['rejected']}\n"
            f"📝 Всего: {user_stats['accepted'] + user_stats['rejected']}\n\n"
            f"🔍 Запросил: {user.mention_html()}"
        )

    stats_msg = await message.reply_text(stats_message, parse_mode='HTML')
    asyncio.create_task(
        delete_messages_after_delay(context, message.chat.id, 
                                   [message.message_id, stats_msg.message_id], 
                                   DELETE_AFTER_SECONDS)
    )

async def reset_accepted_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /sp - сброс принятых отчетов"""
    message = update.message

    if message.chat.id != GROUP_CHAT_ID:
        await message.reply_text("❌ Команда работает только в группе!")
        return

    issuer = message.from_user
    register_user(issuer.id, issuer.username, issuer.full_name)
    issuer_role = get_user_role(issuer.username)

    if not can_reset_stats(issuer_role):
        error_msg = await message.reply_text("❌ У вас нет прав на сброс статистики! (требуется СЗМ+)")
        asyncio.create_task(
            delete_messages_after_delay(context, message.chat.id,
                                      [message.message_id, error_msg.message_id],
                                      DELETE_AFTER_SECONDS)
        )
        return

    target_user_id = None
    target_user_name = None
    target_username = None

    if message.reply_to_message:
        target_user = message.reply_to_message.from_user
        target_user_id = target_user.id
        target_user_name = target_user.full_name
        target_username = target_user.username or str(target_user_id)
        register_user(target_user_id, target_user.username, target_user_name)
    else:
        text = message.text.strip()
        parts = text.split(maxsplit=1)

        if len(parts) < 2:
            error_msg = await message.reply_text(
                "❌ Неправильный формат!\n\n"
                "Используйте:\n"
                "1. Ответ на сообщение: /sp\n"
                "2. Упоминание: /sp @username"
            )
            asyncio.create_task(
                delete_messages_after_delay(context, message.chat.id,
                                          [message.message_id, error_msg.message_id],
                                          DELETE_AFTER_SECONDS)
            )
            return

        target_username = parts[1].lstrip('@')

        if message.entities:
            for entity in message.entities:
                if entity.type == "text_mention":
                    target_user = entity.user
                    target_user_id = target_user.id
                    target_user_name = target_user.full_name
                    target_username = target_user.username or str(target_user_id)
                    register_user(target_user_id, target_user.username, target_user_name)
                    break

        if target_user_id is None:
            target_user_id, target_user_name = find_user_id_by_username(target_username)
            if target_user_id is None:
                found_id, found_data = get_user_stats_by_username(target_username)
                if found_id:
                    target_user_id = int(found_id)
                    target_user_name = found_data.get('name', f'@{target_username}')
                else:
                    error_msg = await message.reply_text(
                        f"❌ Пользователь @{target_username} не найден!\n"
                        f"💡 Попросите его написать /start боту"
                    )
                    asyncio.create_task(
                        delete_messages_after_delay(context, message.chat.id,
                                                  [message.message_id, error_msg.message_id],
                                                  DELETE_AFTER_SECONDS)
                    )
                    return

    old_value = reset_user_stats(target_user_id, 'accepted')

    if old_value is None:
        error_msg = await message.reply_text(f"❌ Пользователь @{target_username} не найден в статистике!")
        asyncio.create_task(
            delete_messages_after_delay(context, message.chat.id,
                                      [message.message_id, error_msg.message_id],
                                      DELETE_AFTER_SECONDS)
        )
        return

    if isinstance(target_user_id, int):
        user_link = f"<a href='tg://user?id={target_user_id}'>{target_user_name}</a>"
    else:
        user_link = f"@{target_username}"

    success_msg = await message.reply_text(
        f"✅ <b>Принятые отчеты сброшены</b>\n\n"
        f"👤 Пользователь: {user_link}\n"
        f"📊 Было: {old_value} → Стало: 0\n"
        f"👨‍💼 Сбросил: {issuer.mention_html()}\n"
        f"🎖 Роль: {issuer_role.name}",
        parse_mode='HTML'
    )

    asyncio.create_task(
        delete_messages_after_delay(context, message.chat.id,
                                  [message.message_id, success_msg.message_id],
                                  DELETE_AFTER_SECONDS)
    )

    logger.info(f"Reset accepted stats: {target_username} by {issuer.username}, was {old_value}")

async def reset_rejected_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /so - сброс отклоненных отчетов"""
    message = update.message

    if message.chat.id != GROUP_CHAT_ID:
        await message.reply_text("❌ Команда работает только в группе!")
        return

    issuer = message.from_user
    register_user(issuer.id, issuer.username, issuer.full_name)
    issuer_role = get_user_role(issuer.username)

    if not can_reset_stats(issuer_role):
        error_msg = await message.reply_text("❌ У вас нет прав на сброс статистики! (требуется СЗМ+)")
        asyncio.create_task(
            delete_messages_after_delay(context, message.chat.id,
                                      [message.message_id, error_msg.message_id],
                                      DELETE_AFTER_SECONDS)
        )
        return

    target_user_id = None
    target_user_name = None
    target_username = None

    if message.reply_to_message:
        target_user = message.reply_to_message.from_user
        target_user_id = target_user.id
        target_user_name = target_user.full_name
        target_username = target_user.username or str(target_user_id)
        register_user(target_user_id, target_user.username, target_user_name)
    else:
        text = message.text.strip()
        parts = text.split(maxsplit=1)

        if len(parts) < 2:
            error_msg = await message.reply_text(
                "❌ Неправильный формат!\n\n"
                "Используйте:\n"
                "1. Ответ на сообщение: /so\n"
                "2. Упоминание: /so @username"
            )
            asyncio.create_task(
                delete_messages_after_delay(context, message.chat.id,
                                          [message.message_id, error_msg.message_id],
                                          DELETE_AFTER_SECONDS)
            )
            return

        target_username = parts[1].lstrip('@')

        if message.entities:
            for entity in message.entities:
                if entity.type == "text_mention":
                    target_user = entity.user
                    target_user_id = target_user.id
                    target_user_name = target_user.full_name
                    target_username = target_user.username or str(target_user_id)
                    register_user(target_user_id, target_user.username, target_user_name)
                    break

        if target_user_id is None:
            target_user_id, target_user_name = find_user_id_by_username(target_username)
            if target_user_id is None:
                found_id, found_data = get_user_stats_by_username(target_username)
                if found_id:
                    target_user_id = int(found_id)
                    target_user_name = found_data.get('name', f'@{target_username}')
                else:
                    error_msg = await message.reply_text(
                        f"❌ Пользователь @{target_username} не найден!\n"
                        f"💡 Попросите его написать /start боту"
                    )
                    asyncio.create_task(
                        delete_messages_after_delay(context, message.chat.id,
                                                  [message.message_id, error_msg.message_id],
                                                  DELETE_AFTER_SECONDS)
                    )
                    return

    old_value = reset_user_stats(target_user_id, 'rejected')

    if old_value is None:
        error_msg = await message.reply_text(f"❌ Пользователь @{target_username} не найден в статистике!")
        asyncio.create_task(
            delete_messages_after_delay(context, message.chat.id,
                                      [message.message_id, error_msg.message_id],
                                      DELETE_AFTER_SECONDS)
        )
        return

    if isinstance(target_user_id, int):
        user_link = f"<a href='tg://user?id={target_user_id}'>{target_user_name}</a>"
    else:
        user_link = f"@{target_username}"

    success_msg = await message.reply_text(
        f"✅ <b>Отклоненные отчеты сброшены</b>\n\n"
        f"👤 Пользователь: {user_link}\n"
        f"📊 Было: {old_value} → Стало: 0\n"
        f"👨‍💼 Сбросил: {issuer.mention_html()}\n"
        f"🎖 Роль: {issuer_role.name}",
        parse_mode='HTML'
    )

    asyncio.create_task(
        delete_messages_after_delay(context, message.chat.id,
                                  [message.message_id, success_msg.message_id],
                                  DELETE_AFTER_SECONDS)
    )

    logger.info(f"Reset rejected stats: {target_username} by {issuer.username}, was {old_value}")

async def warning_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /vg - выдать выговор"""
    message = update.message

    if message.chat.id != GROUP_CHAT_ID:
        await message.reply_text("❌ Команда работает только в группе!")
        return

    issuer = message.from_user
    register_user(issuer.id, issuer.username, issuer.full_name)
    issuer_role = get_user_role(issuer.username)

    if not can_issue_warning(issuer_role):
        error_msg = await message.reply_text("❌ У вас нет прав на выдачу выговоров! (требуется СЗМ+)")
        asyncio.create_task(
            delete_messages_after_delay(context, message.chat.id,
                                      [message.message_id, error_msg.message_id],
                                      DELETE_AFTER_SECONDS)
        )
        return

    target_user_id = None
    target_user_name = None
    target_username = None
    reason = None

    if message.reply_to_message:
        target_user = message.reply_to_message.from_user
        target_user_id = target_user.id
        target_user_name = target_user.full_name
        target_username = target_user.username or str(target_user_id)
        register_user(target_user_id, target_user.username, target_user_name)

        text = message.text.strip()
        parts = text.split(maxsplit=1)
        if len(parts) < 2:
            error_msg = await message.reply_text("❌ Укажите причину выговора!\n\nПример: /vg Нарушение правил")
            asyncio.create_task(
                delete_messages_after_delay(context, message.chat.id,
                                          [message.message_id, error_msg.message_id],
                                          DELETE_AFTER_SECONDS)
            )
            return
        reason = parts[1]
    else:
        text = message.text.strip()
        parts = text.split(maxsplit=2)

        if len(parts) < 3:
            error_msg = await message.reply_text(
                "❌ Неправильный формат!\n\n"
                "Используйте:\n"
                "1. Ответьте на сообщение: /vg причина\n"
                "2. Упомяните: /vg @username причина"
            )
            asyncio.create_task(
                delete_messages_after_delay(context, message.chat.id,
                                          [message.message_id, error_msg.message_id],
                                          DELETE_AFTER_SECONDS)
            )
            return

        target_username = parts[1].lstrip('@')
        reason = parts[2]

        if message.entities:
            for entity in message.entities:
                if entity.type == "text_mention":
                    target_user = entity.user
                    target_user_id = target_user.id
                    target_user_name = target_user.full_name
                    target_username = target_user.username or str(target_user_id)
                    register_user(target_user_id, target_user.username, target_user_name)
                    break

        if target_user_id is None:
            target_user_id, target_user_name = find_user_id_by_username(target_username)
            if target_user_id is None:
                error_msg = await message.reply_text(
                    f"❌ Пользователь @{target_username} не найден!\n"
                    f"💡 Попросите его написать /start боту или используйте ответ на сообщение"
                )
                asyncio.create_task(
                    delete_messages_after_delay(context, message.chat.id,
                                              [message.message_id, error_msg.message_id],
                                              DELETE_AFTER_SECONDS)
                )
                return

    if not target_username and not target_user_id:
        error_msg = await message.reply_text("❌ Не удалось определить пользователя!")
        asyncio.create_task(
            delete_messages_after_delay(context, message.chat.id,
                                      [message.message_id, error_msg.message_id],
                                      DELETE_AFTER_SECONDS)
        )
        return

    warning_count = add_warning(target_user_id, target_user_name, target_username, reason, 
                                issuer.username or issuer.full_name)

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
        warning_message += f"⚡️ Осталось до исключения: {MAX_WARNINGS - warning_count}"
    else:
        warning_message += (
            f"🚫 <b>КРИТИЧЕСКОЕ ПРЕДУПРЕЖДЕНИЕ!</b>\n"
            f"У пользователя {MAX_WARNINGS} выговора!\n"
            f"@{DEPUTY_ADMIN_USERNAME} требуется исключение!"
        )

    await context.bot.send_message(
        chat_id=GROUP_CHAT_ID,
        message_thread_id=WARNINGS_TOPIC_ID,
        text=warning_message,
        parse_mode='HTML'
    )

    success_msg = await message.reply_text(f"✅ Выговор #{warning_count} выдан {user_link}", parse_mode='HTML')

    asyncio.create_task(
        delete_messages_after_delay(context, message.chat.id,
                                  [message.message_id, success_msg.message_id],
                                  DELETE_AFTER_SECONDS)
    )

    logger.info(f"Warning issued: {target_username} by {issuer.username}, count: {warning_count}")

async def remove_warning_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /svg - снять выговор"""
    message = update.message

    if message.chat.id != GROUP_CHAT_ID:
        await message.reply_text("❌ Команда работает только в группе!")
        return

    issuer = message.from_user
    register_user(issuer.id, issuer.username, issuer.full_name)
    issuer_role = get_user_role(issuer.username)

    if not can_remove_warning(issuer_role):
        error_msg = await message.reply_text("❌ У вас нет прав на снятие выговоров! (требуется СЗМ+)")
        asyncio.create_task(
            delete_messages_after_delay(context, message.chat.id,
                                      [message.message_id, error_msg.message_id],
                                      DELETE_AFTER_SECONDS)
        )
        return

    target_user_id = None
    target_user_name = None
    target_username = None

    if message.reply_to_message:
        target_user = message.reply_to_message.from_user
        target_user_id = target_user.id
        target_user_name = target_user.full_name
        target_username = target_user.username or str(target_user_id)
        register_user(target_user_id, target_user.username, target_user_name)
    else:
        text = message.text.strip()
        parts = text.split(maxsplit=1)

        if len(parts) < 2:
            error_msg = await message.reply_text(
                "❌ Неправильный формат!\n\n"
                "Используйте:\n"
                "1. Ответьте на сообщение: /svg\n"
                "2. Упомяните: /svg @username"
            )
            asyncio.create_task(
                delete_messages_after_delay(context, message.chat.id,
                                          [message.message_id, error_msg.message_id],
                                          DELETE_AFTER_SECONDS)
            )
            return

        target_username = parts[1].lstrip('@')

        if message.entities:
            for entity in message.entities:
                if entity.type == "text_mention":
                    target_user = entity.user
                    target_user_id = target_user.id
                    target_user_name = target_user.full_name
                    target_username = target_user.username or str(target_user_id)
                    register_user(target_user_id, target_user.username, target_user_name)
                    break

        if target_user_id is None:
            target_user_id, target_user_name = find_user_id_by_username(target_username)
            if target_user_id is None:
                error_msg = await message.reply_text(
                    f"❌ Пользователь @{target_username} не найден!\n"
                    f"💡 Попросите его написать /start боту"
                )
                asyncio.create_task(
                    delete_messages_after_delay(context, message.chat.id,
                                              [message.message_id, error_msg.message_id],
                                              DELETE_AFTER_SECONDS)
                )
                return

    if not target_username and not target_user_id:
        error_msg = await message.reply_text("❌ Не удалось определить пользователя!")
        asyncio.create_task(
            delete_messages_after_delay(context, message.chat.id,
                                      [message.message_id, error_msg.message_id],
                                      DELETE_AFTER_SECONDS)
        )
        return

    new_count = remove_warning(target_user_id, issuer.username or issuer.full_name)

    if new_count is None:
        error_msg = await message.reply_text(f"❌ У пользователя @{target_username} нет выговоров для снятия!")
        asyncio.create_task(
            delete_messages_after_delay(context, message.chat.id,
                                      [message.message_id, error_msg.message_id],
                                      DELETE_AFTER_SECONDS)
        )
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

    success_msg = await message.reply_text(f"✅ Выговор снят! Осталось: {new_count}/{MAX_WARNINGS}", parse_mode='HTML')

    asyncio.create_task(
        delete_messages_after_delay(context, message.chat.id,
                                  [message.message_id, success_msg.message_id],
                                  DELETE_AFTER_SECONDS)
    )

    logger.info(f"Warning removed: {target_username} by {issuer.username}, new count: {new_count}")

async def blacklist_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /bl - добавить в черный список"""
    message = update.message

    if message.chat.id != GROUP_CHAT_ID:
        await message.reply_text("❌ Команда работает только в группе!")
        return

    issuer = message.from_user
    register_user(issuer.id, issuer.username, issuer.full_name)
    issuer_role = get_user_role(issuer.username)

    if not can_manage_blacklist(issuer_role):
        error_msg = await message.reply_text("❌ У вас нет прав на управление черным списком! (требуется СЗМ+)")
        asyncio.create_task(
            delete_messages_after_delay(context, message.chat.id,
                                      [message.message_id, error_msg.message_id],
                                      DELETE_AFTER_SECONDS)
        )
        return

    target_user_id = None
    target_user_name = None
    target_username = None
    days = None
    reason = None

    if message.reply_to_message:
        target_user = message.reply_to_message.from_user
        target_user_id = target_user.id
        target_user_name = target_user.full_name
        target_username = target_user.username or str(target_user_id)
        register_user(target_user_id, target_user.username, target_user_name)

        text = message.text.strip()
        parts = text.split(maxsplit=2)

        if len(parts) < 3:
            error_msg = await message.reply_text(
                "❌ Укажите количество дней и причину!\n\n"
                "Пример: /bl 7 Нарушение правил"
            )
            asyncio.create_task(
                delete_messages_after_delay(context, message.chat.id,
                                          [message.message_id, error_msg.message_id],
                                          DELETE_AFTER_SECONDS)
            )
            return

        try:
            days = int(parts[1])
            if days <= 0:
                raise ValueError
        except ValueError:
            error_msg = await message.reply_text("❌ Количество дней должно быть положительным числом!")
            asyncio.create_task(
                delete_messages_after_delay(context, message.chat.id,
                                          [message.message_id, error_msg.message_id],
                                          DELETE_AFTER_SECONDS)
            )
            return

        reason = parts[2]
    else:
        text = message.text.strip()
        parts = text.split(maxsplit=3)

        if len(parts) < 4:
            error_msg = await message.reply_text(
                "❌ Неправильный формат!\n\n"
                "Используйте:\n"
                "1. Ответ на сообщение: /bl дни причина\n"
                "2. Упоминание: /bl @username дни причина\n\n"
                "Пример: /bl @breakbrosmiling 7 Нарушение правил"
            )
            asyncio.create_task(
                delete_messages_after_delay(context, message.chat.id,
                                          [message.message_id, error_msg.message_id],
                                          DELETE_AFTER_SECONDS)
            )
            return

        target_username = parts[1].lstrip('@')

        try:
            days = int(parts[2])
            if days <= 0:
                raise ValueError
        except ValueError:
            error_msg = await message.reply_text("❌ Количество дней должно быть положительным числом!")
            asyncio.create_task(
                delete_messages_after_delay(context, message.chat.id,
                                          [message.message_id, error_msg.message_id],
                                          DELETE_AFTER_SECONDS)
            )
            return

        reason = parts[3]

        if message.entities:
            for entity in message.entities:
                if entity.type == "text_mention":
                    target_user = entity.user
                    target_user_id = target_user.id
                    target_user_name = target_user.full_name
                    target_username = target_user.username or str(target_user_id)
                    register_user(target_user_id, target_user.username, target_user_name)
                    break

        if target_user_id is None:
            target_user_id, target_user_name = find_user_id_by_username(target_username)
            if target_user_id is None:
                error_msg = await message.reply_text(
                    f"❌ Пользователь @{target_username} не найден!\n"
                    f"💡 Попросите его написать /start боту"
                )
                asyncio.create_task(
                    delete_messages_after_delay(context, message.chat.id,
                                              [message.message_id, error_msg.message_id],
                                              DELETE_AFTER_SECONDS)
                )
                return

    if not target_username and not target_user_id:
        error_msg = await message.reply_text("❌ Не удалось определить пользователя!")
        asyncio.create_task(
            delete_messages_after_delay(context, message.chat.id,
                                      [message.message_id, error_msg.message_id],
                                      DELETE_AFTER_SECONDS)
        )
        return

    entry = add_to_blacklist(target_user_id, target_user_name, target_username, days, reason,
                             issuer.username or issuer.full_name)

    if isinstance(target_user_id, int):
        user_link = f"<a href='tg://user?id={target_user_id}'>{target_user_name}</a>"
    else:
        user_link = f"@{target_username}"

    start_date = datetime.fromisoformat(entry['start_date'])
    end_date = datetime.fromisoformat(entry['end_date'])

    blacklist_message = (
        f"🚫 <b>ЧЕРНЫЙ СПИСОК</b>\n\n"
        f"👤 Пользователь: {user_link}\n"
        f"📝 Причина: {reason}\n"
        f"⏱ Срок: {days} дн. ({start_date.strftime('%d.%m.%Y')} - {end_date.strftime('%d.%m.%Y')})\n"
        f"👨‍💼 Выдал: {issuer.mention_html()} (@{issuer.username})\n"
        f"🎖 Роль: {issuer_role.name}\n\n"
        f"⚠️ Пользователь добавлен в черный список до {end_date.strftime('%d.%m.%Y')}"
    )

    await context.bot.send_message(
        chat_id=GROUP_CHAT_ID,
        message_thread_id=BLACKLIST_TOPIC_ID,
        text=blacklist_message,
        parse_mode='HTML'
    )

    success_msg = await message.reply_text(
        f"✅ {user_link} добавлен в черный список на {days} дн.\n"
        f"До: {end_date.strftime('%d.%m.%Y')}",
        parse_mode='HTML'
    )

    asyncio.create_task(
        delete_messages_after_delay(context, message.chat.id,
                                  [message.message_id, success_msg.message_id],
                                  DELETE_AFTER_SECONDS)
    )

    logger.info(f"Blacklist: {target_username} by {issuer.username} for {days} days")

async def unblacklist_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /ubl - убрать из черного списка"""
    message = update.message

    if message.chat.id != GROUP_CHAT_ID:
        await message.reply_text("❌ Команда работает только в группе!")
        return

    issuer = message.from_user
    register_user(issuer.id, issuer.username, issuer.full_name)
    issuer_role = get_user_role(issuer.username)

    if not can_manage_blacklist(issuer_role):
        error_msg = await message.reply_text("❌ У вас нет прав на управление черным списком! (требуется СЗМ+)")
        asyncio.create_task(
            delete_messages_after_delay(context, message.chat.id,
                                      [message.message_id, error_msg.message_id],
                                      DELETE_AFTER_SECONDS)
        )
        return

    target_user_id = None
    target_user_name = None
    target_username = None

    if message.reply_to_message:
        target_user = message.reply_to_message.from_user
        target_user_id = target_user.id
        target_user_name = target_user.full_name
        target_username = target_user.username or str(target_user_id)
        register_user(target_user_id, target_user.username, target_user_name)
    else:
        text = message.text.strip()
        parts = text.split(maxsplit=1)

        if len(parts) < 2:
            error_msg = await message.reply_text(
                "❌ Неправильный формат!\n\n"
                "Используйте:\n"
                "1. Ответ на сообщение: /ubl\n"
                "2. Упоминание: /ubl @username"
            )
            asyncio.create_task(
                delete_messages_after_delay(context, message.chat.id,
                                          [message.message_id, error_msg.message_id],
                                          DELETE_AFTER_SECONDS)
            )
            return

        target_username = parts[1].lstrip('@')

        if message.entities:
            for entity in message.entities:
                if entity.type == "text_mention":
                    target_user = entity.user
                    target_user_id = target_user.id
                    target_user_name = target_user.full_name
                    target_username = target_user.username or str(target_user_id)
                    register_user(target_user_id, target_user.username, target_user_name)
                    break

        if target_user_id is None:
            target_user_id, target_user_name = find_user_id_by_username(target_username)
            if target_user_id is None:
                error_msg = await message.reply_text(
                    f"❌ Пользователь @{target_username} не найден!\n"
                    f"💡 Попросите его написать /start боту"
                )
                asyncio.create_task(
                    delete_messages_after_delay(context, message.chat.id,
                                              [message.message_id, error_msg.message_id],
                                              DELETE_AFTER_SECONDS)
                )
                return

    if not target_username and not target_user_id:
        error_msg = await message.reply_text("❌ Не удалось определить пользователя!")
        asyncio.create_task(
            delete_messages_after_delay(context, message.chat.id,
                                      [message.message_id, error_msg.message_id],
                                      DELETE_AFTER_SECONDS)
        )
        return

    removed = remove_from_blacklist(target_user_id)

    if not removed:
        error_msg = await message.reply_text(f"❌ Пользователь @{target_username} не находится в черном списке!")
        asyncio.create_task(
            delete_messages_after_delay(context, message.chat.id,
                                      [message.message_id, error_msg.message_id],
                                      DELETE_AFTER_SECONDS)
        )
        return

    if isinstance(target_user_id, int):
        user_link = f"<a href='tg://user?id={target_user_id}'>{target_user_name}</a>"
    else:
        user_link = f"@{target_username}"

    unblacklist_message = (
        f"✅ <b>УДАЛЕН ИЗ ЧЕРНОГО СПИСКА</b>\n\n"
        f"👤 Пользователь: {user_link}\n"
        f"👨‍💼 Убрал: {issuer.mention_html()} (@{issuer.username})\n"
        f"🎖 Роль: {issuer_role.name}\n\n"
        f"✅ Пользователь восстановлен досрочно"
    )

    await context.bot.send_message(
        chat_id=GROUP_CHAT_ID,
        message_thread_id=BLACKLIST_TOPIC_ID,
        text=unblacklist_message,
        parse_mode='HTML'
    )

    success_msg = await message.reply_text(f"✅ {user_link} удален из черного списка!", parse_mode='HTML')

    asyncio.create_task(
        delete_messages_after_delay(context, message.chat.id,
                                  [message.message_id, success_msg.message_id],
                                  DELETE_AFTER_SECONDS)
    )

    logger.info(f"Unblacklisted: {target_username} by {issuer.username}")

async def handle_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message

    if message.chat.id != GROUP_CHAT_ID or not message.photo:
        return

    topic_id = message.message_thread_id

    if topic_id == MODERATOR_REPORT_TOPIC_ID:
        category = 'moderator'
    elif topic_id == ADMIN_REPORT_TOPIC_ID:
        category = 'admin'
    else:
        return

    sender = message.from_user
    register_user(sender.id, sender.username, sender.full_name)
    sender_role = get_user_role(sender.username)
    expected_category = get_report_category(sender_role)

    if expected_category != category:
        if expected_category is None:
            await message.reply_text("❌ Ваша роль не требует сдачи отчетов!")
        else:
            correct_topic = "Отчетность модерации" if expected_category == 'moderator' else "Отчетность администрации"
            await message.reply_text(f"❌ Отправьте отчет в тему: {correct_topic}")
        return

    photo = message.photo[-1].file_id
    caption = message.caption or ""

    keyboard = [[
        InlineKeyboardButton("✅ Принять отчет", callback_data=f"accept_{category}_{message.message_id}"),
        InlineKeyboardButton("❌ Отклонить", callback_data=f"reject_{category}_{message.message_id}")
    ]]
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
    query = update.callback_query
    parts = query.data.split('_')
    action = parts[0]
    category = parts[1]
    report_id = parts[2]

    checker = query.from_user
    register_user(checker.id, checker.username, checker.full_name)
    checker_role = get_user_role(checker.username)

    if not can_check_report(checker_role, category):
        await query.answer("❌ У вас нет прав!", show_alert=True)
        return

    await query.answer()

    report_key = f"{category}_{report_id}"
    if report_key not in reports_data:
        return

    report = reports_data[report_key]
    updated_stats = update_user_stats(report['sender_id'], report['sender_name'], action)

    topics = get_topic_ids_for_category(category)
    target_topic_id = topics['accepted'] if action == 'accept' else topics['rejected']
    status = "✅ ПРИНЯТ" if action == 'accept' else "❌ ОТКЛОНЕН"

    final_caption = (
        f"{status}\n\n"
        f"👤 Отправил: {report['sender_name']}\n"
        f"🎖 Роль: {report['sender_role']}\n"
        f"📊 Принятых: {updated_stats['accepted']} | Отклоненных: {updated_stats['rejected']}\n"
        f"👨‍💼 Проверил: @{checker.username}\n"
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

    asyncio.create_task(
        delete_messages_after_delay(context, GROUP_CHAT_ID, 
                                   [report['user_message_id'], report['bot_message_id']], 
                                   DELETE_AFTER_SECONDS)
    )

    del reports_data[report_key]

def main():
    logger.info("🚀 Запуск бота - ФИНАЛЬНАЯ ВЕРСИЯ")
    logger.info(f"👥 Загружено пользователей: {len(USERS_ROLES)}")
    logger.info(f"📋 ID темы выговоров: {WARNINGS_TOPIC_ID}")
    logger.info(f"📋 ID темы черного списка: {BLACKLIST_TOPIC_ID}")
    logger.info("✅ Все функции активны")

    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("vg", warning_command))
    application.add_handler(CommandHandler("svg", remove_warning_command))
    application.add_handler(CommandHandler("bl", blacklist_command))
    application.add_handler(CommandHandler("ubl", unblacklist_command))
    application.add_handler(CommandHandler("sp", reset_accepted_command))
    application.add_handler(CommandHandler("so", reset_rejected_command))
    application.add_handler(MessageHandler(filters.PHOTO & filters.ChatType.SUPERGROUP, handle_report))
    application.add_handler(CallbackQueryHandler(handle_button_callback))

    logger.info("✅ Бот запущен! Все системы работают")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
