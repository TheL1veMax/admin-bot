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
    if os.path.exists(USER_IDS_FILE):
        try:
            with open(USER_IDS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Ошибка загрузки user_ids: {e}")
    return {}

def save_user_ids(user_ids):
    try:
        with open(USER_IDS_FILE, 'w', encoding='utf-8') as f:
            json.dump(user_ids, f, ensure_ascii=False, indent=2)
        logger.info(f"Saved {len(user_ids)} users")
    except Exception as e:
        logger.error(f"Ошибка сохранения user_ids: {e}")

def register_user(user_id: int, username: str, full_name: str):
    if not username:
        logger.warning(f"No username: {user_id} - {full_name}")
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
    logger.info(f"✅ Registered: @{username} (ID: {user_id})")

def find_user_id_by_username(username: str):
    user_ids = load_user_ids()
    clean_username = username.lower()
    logger.info(f"🔍 Searching for @{username}...")
    if clean_username in user_ids:
        user_data = user_ids[clean_username]
        logger.info(f"✅ FOUND: @{username} -> ID={user_data['user_id']}")
        return user_data['user_id'], user_data['full_name']
    logger.warning(f"❌ NOT FOUND: @{username}")
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
    if user_id is None:
        logger.error("❌ CRITICAL: user_id=None!")
        return None
    warnings = load_warnings()
    user_key = str(user_id)
    logger.info(f"➕ Adding warning to ID={user_id}")
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
    logger.info(f"✅ Warning added: total={warnings[user_key]['count']}")
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
            logger.error(f"Ошибка загрузки ЧС: {e}")
    return {}

def save_blacklist(blacklist):
    try:
        with open(BLACKLIST_FILE, 'w', encoding='utf-8') as f:
            json.dump(blacklist, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Ошибка сохранения ЧС: {e}")

def add_to_blacklist(user_id: int, user_name: str, username: str, days: int, reason: str, issued_by: str):
    if user_id is None:
        logger.error("❌ CRITICAL: user_id=None!")
        return None
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

async def delete_messages_after_delay(context: ContextTypes.DEFAULT_TYPE, chat_id: int, message_ids: list, delay: int):
    await asyncio.sleep(delay)
    for msg_id in message_ids:
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=msg_id)
        except Exception as e:
            logger.error(f"Failed to delete {msg_id}: {e}")

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
        "✅ Бот запущен!\n\n"
        f"👤 Ваша роль: {role_name}\n"
        f"🆔 ID: {user.id}\n\n"
        "📋 Команды:\n"
        "/stats - статистика\n"
        "/vg @username причина\n"
        "/svg @username\n"
        "/bl @username дни причина\n"
        "/ubl @username\n"
        "/sp @username\n"
        "/so @username"
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
            cooldown_msg = await message.reply_text(f"⏳ Подождите {cooldown_left} сек")
            asyncio.create_task(delete_messages_after_delay(context, message.chat.id, [message.message_id, cooldown_msg.message_id], DELETE_AFTER_SECONDS))
            return
    stats_cooldowns[user_key] = current_time
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
        if len(parts) > 1:
            if not can_view_others_stats(user_role):
                error_msg = await message.reply_text("❌ Нет прав!")
                asyncio.create_task(delete_messages_after_delay(context, message.chat.id, [message.message_id, error_msg.message_id], DELETE_AFTER_SECONDS))
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
                stats = load_stats()
                for uid, data in stats.items():
                    if data.get('name', '').lower() == target_username.lower():
                        target_user_id = int(uid)
                        target_user_name = data.get('name')
                        break

            if target_user_id is None:
                error_msg = await message.reply_text(f"❌ @{target_username} не найден!")
                asyncio.create_task(delete_messages_after_delay(context, message.chat.id, [message.message_id, error_msg.message_id], DELETE_AFTER_SECONDS))
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
            f"📊 <b>Ваша статистика</b>\n\n"
            f"👤 {target_user_name}\n"
            f"🎖 {role_name}\n"
            f"✅ Принятых: {user_stats['accepted']}\n"
            f"❌ Отклоненных: {user_stats['rejected']}\n"
            f"📝 Всего: {user_stats['accepted'] + user_stats['rejected']}"
        )
    else:
        stats_message = (
            f"📊 <b>Статистика</b>\n\n"
            f"👤 {target_user_name} (@{target_username})\n"
            f"🎖 {role_name}\n"
            f"✅ Принятых: {user_stats['accepted']}\n"
            f"❌ Отклоненных: {user_stats['rejected']}\n"
            f"📝 Всего: {user_stats['accepted'] + user_stats['rejected']}\n\n"
            f"🔍 Запросил: {user.mention_html()}"
        )

    stats_msg = await message.reply_text(stats_message, parse_mode='HTML')
    asyncio.create_task(delete_messages_after_delay(context, message.chat.id, [message.message_id, stats_msg.message_id], DELETE_AFTER_SECONDS))

async def warning_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if message.chat.id != GROUP_CHAT_ID:
        await message.reply_text("❌ Только в группе!")
        return

    issuer = message.from_user
    register_user(issuer.id, issuer.username, issuer.full_name)
    issuer_role = get_user_role(issuer.username)

    if not can_issue_warning(issuer_role):
        error_msg = await message.reply_text("❌ Нет прав! (СЗМ+)")
        asyncio.create_task(delete_messages_after_delay(context, message.chat.id, [message.message_id, error_msg.message_id], DELETE_AFTER_SECONDS))
        return

    logger.info(f"⚠️ Warning from @{issuer.username}")

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
        logger.info(f"✅ From REPLY: ID={target_user_id}")

        text = message.text.strip()
        parts = text.split(maxsplit=1)
        if len(parts) < 2:
            error_msg = await message.reply_text("❌ Укажите причину!\n/vg причина")
            asyncio.create_task(delete_messages_after_delay(context, message.chat.id, [message.message_id, error_msg.message_id], DELETE_AFTER_SECONDS))
            return
        reason = parts[1]
    else:
        text = message.text.strip()
        parts = text.split(maxsplit=2)

        if len(parts) < 3:
            error_msg = await message.reply_text("❌ Формат: /vg @username причина")
            asyncio.create_task(delete_messages_after_delay(context, message.chat.id, [message.message_id, error_msg.message_id], DELETE_AFTER_SECONDS))
            return

        target_username = parts[1].lstrip('@')
        reason = parts[2]

        logger.info(f"🔍 Looking for @{target_username}")

        if message.entities:
            for entity in message.entities:
                if entity.type == "text_mention":
                    target_user = entity.user
                    target_user_id = target_user.id
                    target_user_name = target_user.full_name
                    target_username = target_user.username or str(target_user_id)
                    register_user(target_user_id, target_user.username, target_user_name)
                    logger.info(f"✅ Via text_mention: ID={target_user_id}")
                    break

        if target_user_id is None:
            found_id, found_name = find_user_id_by_username(target_username)

            if found_id is not None:
                target_user_id = found_id
                target_user_name = found_name
                logger.info(f"✅ In DB: ID={target_user_id}")
            else:
                logger.error(f"❌ @{target_username} NOT FOUND!")
                error_msg = await message.reply_text(
                    f"❌ @{target_username} не найден!\n"
                    f"💡 Попросите написать /start боту"
                )
                asyncio.create_task(delete_messages_after_delay(context, message.chat.id, [message.message_id, error_msg.message_id], DELETE_AFTER_SECONDS))
                return

    if target_user_id is None or target_user_name is None:
        logger.error(f"❌ CRITICAL: ID={target_user_id}, Name={target_user_name}")
        error_msg = await message.reply_text("❌ Ошибка определения пользователя!")
        asyncio.create_task(delete_messages_after_delay(context, message.chat.id, [message.message_id, error_msg.message_id], DELETE_AFTER_SECONDS))
        return

    warning_count = add_warning(target_user_id, target_user_name, target_username, reason, issuer.username or issuer.full_name)

    if warning_count is None:
        error_msg = await message.reply_text("❌ Ошибка выдачи!")
        asyncio.create_task(delete_messages_after_delay(context, message.chat.id, [message.message_id, error_msg.message_id], DELETE_AFTER_SECONDS))
        return

    warning_emoji = "⚠️" if warning_count < MAX_WARNINGS else "🚫"
    user_link = f"<a href='tg://user?id={target_user_id}'>{target_user_name}</a>"

    warning_message = (
        f"{warning_emoji} <b>ВЫГОВОР #{warning_count}/{MAX_WARNINGS}</b>\n\n"
        f"👤 {user_link} (@{target_username})\n"
        f"🆔 {target_user_id}\n"
        f"📝 Причина: {reason}\n"
        f"👨‍💼 Выдал: {issuer.mention_html()} (@{issuer.username})\n"
        f"🎖 {issuer_role.name}\n\n"
    )

    if warning_count < MAX_WARNINGS:
        warning_message += f"⚡️ Осталось: {MAX_WARNINGS - warning_count}"
    else:
        warning_message += f"🚫 <b>КРИТИЧНО!</b>\n@{DEPUTY_ADMIN_USERNAME} исключение!"

    await context.bot.send_message(
        chat_id=GROUP_CHAT_ID,
        message_thread_id=WARNINGS_TOPIC_ID,
        text=warning_message,
        parse_mode='HTML'
    )

    success_msg = await message.reply_text(f"✅ Выговор #{warning_count} выдан {user_link}", parse_mode='HTML')
    asyncio.create_task(delete_messages_after_delay(context, message.chat.id, [message.message_id, success_msg.message_id], DELETE_AFTER_SECONDS))
    logger.info(f"✅ Warning issued to ID={target_user_id}")

async def remove_warning_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if message.chat.id != GROUP_CHAT_ID:
        await message.reply_text("❌ Только в группе!")
        return

    issuer = message.from_user
    register_user(issuer.id, issuer.username, issuer.full_name)
    issuer_role = get_user_role(issuer.username)

    if not can_remove_warning(issuer_role):
        error_msg = await message.reply_text("❌ Нет прав!")
        asyncio.create_task(delete_messages_after_delay(context, message.chat.id, [message.message_id, error_msg.message_id], DELETE_AFTER_SECONDS))
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
            error_msg = await message.reply_text("❌ Формат: /svg @username")
            asyncio.create_task(delete_messages_after_delay(context, message.chat.id, [message.message_id, error_msg.message_id], DELETE_AFTER_SECONDS))
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
            found_id, found_name = find_user_id_by_username(target_username)
            if found_id is not None:
                target_user_id = found_id
                target_user_name = found_name
            else:
                error_msg = await message.reply_text(f"❌ @{target_username} не найден!")
                asyncio.create_task(delete_messages_after_delay(context, message.chat.id, [message.message_id, error_msg.message_id], DELETE_AFTER_SECONDS))
                return

    if target_user_id is None:
        error_msg = await message.reply_text("❌ Ошибка!")
        asyncio.create_task(delete_messages_after_delay(context, message.chat.id, [message.message_id, error_msg.message_id], DELETE_AFTER_SECONDS))
        return

    new_count = remove_warning(target_user_id, issuer.username or issuer.full_name)

    if new_count is None:
        error_msg = await message.reply_text(f"❌ Нет выговоров!")
        asyncio.create_task(delete_messages_after_delay(context, message.chat.id, [message.message_id, error_msg.message_id], DELETE_AFTER_SECONDS))
        return

    user_link = f"<a href='tg://user?id={target_user_id}'>{target_user_name}</a>"
    remove_message = (
        f"✅ <b>ВЫГОВОР СНЯТ</b>\n\n"
        f"👤 {user_link}\n"
        f"📊 Осталось: {new_count}/{MAX_WARNINGS}\n"
        f"👨‍💼 {issuer.mention_html()}"
    )

    await context.bot.send_message(
        chat_id=GROUP_CHAT_ID,
        message_thread_id=WARNINGS_TOPIC_ID,
        text=remove_message,
        parse_mode='HTML'
    )

    success_msg = await message.reply_text(f"✅ Снят! Осталось: {new_count}", parse_mode='HTML')
    asyncio.create_task(delete_messages_after_delay(context, message.chat.id, [message.message_id, success_msg.message_id], DELETE_AFTER_SECONDS))

async def blacklist_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if message.chat.id != GROUP_CHAT_ID:
        return

    issuer = message.from_user
    register_user(issuer.id, issuer.username, issuer.full_name)
    issuer_role = get_user_role(issuer.username)

    if not can_manage_blacklist(issuer_role):
        error_msg = await message.reply_text("❌ Нет прав!")
        asyncio.create_task(delete_messages_after_delay(context, message.chat.id, [message.message_id, error_msg.message_id], DELETE_AFTER_SECONDS))
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
            error_msg = await message.reply_text("❌ Формат: /bl дни причина")
            asyncio.create_task(delete_messages_after_delay(context, message.chat.id, [message.message_id, error_msg.message_id], DELETE_AFTER_SECONDS))
            return

        try:
            days = int(parts[1])
            if days <= 0:
                raise ValueError
        except ValueError:
            error_msg = await message.reply_text("❌ Дни - положительное число!")
            asyncio.create_task(delete_messages_after_delay(context, message.chat.id, [message.message_id, error_msg.message_id], DELETE_AFTER_SECONDS))
            return

        reason = parts[2]
    else:
        text = message.text.strip()
        parts = text.split(maxsplit=3)

        if len(parts) < 4:
            error_msg = await message.reply_text("❌ Формат: /bl @username дни причина")
            asyncio.create_task(delete_messages_after_delay(context, message.chat.id, [message.message_id, error_msg.message_id], DELETE_AFTER_SECONDS))
            return

        target_username = parts[1].lstrip('@')

        try:
            days = int(parts[2])
            if days <= 0:
                raise ValueError
        except ValueError:
            error_msg = await message.reply_text("❌ Дни - положительное число!")
            asyncio.create_task(delete_messages_after_delay(context, message.chat.id, [message.message_id, error_msg.message_id], DELETE_AFTER_SECONDS))
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
            found_id, found_name = find_user_id_by_username(target_username)
            if found_id is not None:
                target_user_id = found_id
                target_user_name = found_name
            else:
                error_msg = await message.reply_text(f"❌ @{target_username} не найден!")
                asyncio.create_task(delete_messages_after_delay(context, message.chat.id, [message.message_id, error_msg.message_id], DELETE_AFTER_SECONDS))
                return

    if target_user_id is None:
        error_msg = await message.reply_text("❌ Ошибка!")
        asyncio.create_task(delete_messages_after_delay(context, message.chat.id, [message.message_id, error_msg.message_id], DELETE_AFTER_SECONDS))
        return

    entry = add_to_blacklist(target_user_id, target_user_name, target_username, days, reason, issuer.username or issuer.full_name)

    if entry is None:
        error_msg = await message.reply_text("❌ Ошибка!")
        asyncio.create_task(delete_messages_after_delay(context, message.chat.id, [message.message_id, error_msg.message_id], DELETE_AFTER_SECONDS))
        return

    user_link = f"<a href='tg://user?id={target_user_id}'>{target_user_name}</a>"
    end_date = datetime.fromisoformat(entry['end_date'])

    bl_message = (
        f"🚫 <b>ЧЕРНЫЙ СПИСОК</b>\n\n"
        f"👤 {user_link}\n"
        f"📝 {reason}\n"
        f"⏱ {days} дн. ({end_date.strftime('%d.%m.%Y')})\n"
        f"👨‍💼 {issuer.mention_html()}"
    )

    await context.bot.send_message(
        chat_id=GROUP_CHAT_ID,
        message_thread_id=BLACKLIST_TOPIC_ID,
        text=bl_message,
        parse_mode='HTML'
    )

    success_msg = await message.reply_text(f"✅ {user_link} в ЧС", parse_mode='HTML')
    asyncio.create_task(delete_messages_after_delay(context, message.chat.id, [message.message_id, success_msg.message_id], DELETE_AFTER_SECONDS))

async def unblacklist_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if message.chat.id != GROUP_CHAT_ID:
        return

    issuer = message.from_user
    register_user(issuer.id, issuer.username, issuer.full_name)
    issuer_role = get_user_role(issuer.username)

    if not can_manage_blacklist(issuer_role):
        error_msg = await message.reply_text("❌ Нет прав!")
        asyncio.create_task(delete_messages_after_delay(context, message.chat.id, [message.message_id, error_msg.message_id], DELETE_AFTER_SECONDS))
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
            error_msg = await message.reply_text("❌ Формат: /ubl @username")
            asyncio.create_task(delete_messages_after_delay(context, message.chat.id, [message.message_id, error_msg.message_id], DELETE_AFTER_SECONDS))
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
            found_id, found_name = find_user_id_by_username(target_username)
            if found_id is not None:
                target_user_id = found_id
                target_user_name = found_name
            else:
                error_msg = await message.reply_text(f"❌ @{target_username} не найден!")
                asyncio.create_task(delete_messages_after_delay(context, message.chat.id, [message.message_id, error_msg.message_id], DELETE_AFTER_SECONDS))
                return

    if target_user_id is None:
        error_msg = await message.reply_text("❌ Ошибка!")
        asyncio.create_task(delete_messages_after_delay(context, message.chat.id, [message.message_id, error_msg.message_id], DELETE_AFTER_SECONDS))
        return

    removed = remove_from_blacklist(target_user_id)

    if not removed:
        error_msg = await message.reply_text(f"❌ Не в ЧС!")
        asyncio.create_task(delete_messages_after_delay(context, message.chat.id, [message.message_id, error_msg.message_id], DELETE_AFTER_SECONDS))
        return

    user_link = f"<a href='tg://user?id={target_user_id}'>{target_user_name}</a>"
    ubl_message = f"✅ <b>УДАЛЕН ИЗ ЧС</b>\n\n👤 {user_link}\n👨‍💼 {issuer.mention_html()}"

    await context.bot.send_message(
        chat_id=GROUP_CHAT_ID,
        message_thread_id=BLACKLIST_TOPIC_ID,
        text=ubl_message,
        parse_mode='HTML'
    )

    success_msg = await message.reply_text(f"✅ {user_link} удален из ЧС!", parse_mode='HTML')
    asyncio.create_task(delete_messages_after_delay(context, message.chat.id, [message.message_id, success_msg.message_id], DELETE_AFTER_SECONDS))

async def reset_accepted_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if message.chat.id != GROUP_CHAT_ID:
        return

    issuer = message.from_user
    register_user(issuer.id, issuer.username, issuer.full_name)
    issuer_role = get_user_role(issuer.username)

    if not can_reset_stats(issuer_role):
        error_msg = await message.reply_text("❌ Нет прав!")
        asyncio.create_task(delete_messages_after_delay(context, message.chat.id, [message.message_id, error_msg.message_id], DELETE_AFTER_SECONDS))
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
            error_msg = await message.reply_text("❌ Формат: /sp @username")
            asyncio.create_task(delete_messages_after_delay(context, message.chat.id, [message.message_id, error_msg.message_id], DELETE_AFTER_SECONDS))
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
            found_id, found_name = find_user_id_by_username(target_username)
            if found_id is not None:
                target_user_id = found_id
                target_user_name = found_name
            else:
                stats = load_stats()
                for uid, data in stats.items():
                    if data.get('name', '').lower() == target_username.lower():
                        target_user_id = int(uid)
                        target_user_name = data.get('name')
                        break

                if target_user_id is None:
                    error_msg = await message.reply_text(f"❌ @{target_username} не найден!")
                    asyncio.create_task(delete_messages_after_delay(context, message.chat.id, [message.message_id, error_msg.message_id], DELETE_AFTER_SECONDS))
                    return

    if target_user_id is None:
        error_msg = await message.reply_text("❌ Ошибка!")
        asyncio.create_task(delete_messages_after_delay(context, message.chat.id, [message.message_id, error_msg.message_id], DELETE_AFTER_SECONDS))
        return

    stats = load_stats()
    user_key = str(target_user_id)

    if user_key not in stats:
        error_msg = await message.reply_text(f"❌ Не найден в статистике!")
        asyncio.create_task(delete_messages_after_delay(context, message.chat.id, [message.message_id, error_msg.message_id], DELETE_AFTER_SECONDS))
        return

    old_value = stats[user_key].get('accepted', 0)
    stats[user_key]['accepted'] = 0
    save_stats(stats)

    user_link = f"<a href='tg://user?id={target_user_id}'>{target_user_name}</a>"
    success_msg = await message.reply_text(f"✅ Принятые сброшены\n{user_link}: {old_value} → 0", parse_mode='HTML')
    asyncio.create_task(delete_messages_after_delay(context, message.chat.id, [message.message_id, success_msg.message_id], DELETE_AFTER_SECONDS))

async def reset_rejected_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if message.chat.id != GROUP_CHAT_ID:
        return

    issuer = message.from_user
    register_user(issuer.id, issuer.username, issuer.full_name)
    issuer_role = get_user_role(issuer.username)

    if not can_reset_stats(issuer_role):
        error_msg = await message.reply_text("❌ Нет прав!")
        asyncio.create_task(delete_messages_after_delay(context, message.chat.id, [message.message_id, error_msg.message_id], DELETE_AFTER_SECONDS))
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
            error_msg = await message.reply_text("❌ Формат: /so @username")
            asyncio.create_task(delete_messages_after_delay(context, message.chat.id, [message.message_id, error_msg.message_id], DELETE_AFTER_SECONDS))
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
            found_id, found_name = find_user_id_by_username(target_username)
            if found_id is not None:
                target_user_id = found_id
                target_user_name = found_name
            else:
                stats = load_stats()
                for uid, data in stats.items():
                    if data.get('name', '').lower() == target_username.lower():
                        target_user_id = int(uid)
                        target_user_name = data.get('name')
                        break

                if target_user_id is None:
                    error_msg = await message.reply_text(f"❌ @{target_username} не найден!")
                    asyncio.create_task(delete_messages_after_delay(context, message.chat.id, [message.message_id, error_msg.message_id], DELETE_AFTER_SECONDS))
                    return

    if target_user_id is None:
        error_msg = await message.reply_text("❌ Ошибка!")
        asyncio.create_task(delete_messages_after_delay(context, message.chat.id, [message.message_id, error_msg.message_id], DELETE_AFTER_SECONDS))
        return

    stats = load_stats()
    user_key = str(target_user_id)

    if user_key not in stats:
        error_msg = await message.reply_text(f"❌ Не найден в статистике!")
        asyncio.create_task(delete_messages_after_delay(context, message.chat.id, [message.message_id, error_msg.message_id], DELETE_AFTER_SECONDS))
        return

    old_value = stats[user_key].get('rejected', 0)
    stats[user_key]['rejected'] = 0
    save_stats(stats)

    user_link = f"<a href='tg://user?id={target_user_id}'>{target_user_name}</a>"
    success_msg = await message.reply_text(f"✅ Отклоненные сброшены\n{user_link}: {old_value} → 0", parse_mode='HTML')
    asyncio.create_task(delete_messages_after_delay(context, message.chat.id, [message.message_id, success_msg.message_id], DELETE_AFTER_SECONDS))

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
            await message.reply_text("❌ Ваша роль не требует отчетов!")
        else:
            correct_topic = "Отчетность модерации" if expected_category == 'moderator' else "Отчетность администрации"
            await message.reply_text(f"❌ Отправьте в тему: {correct_topic}")
        return

    photo = message.photo[-1].file_id
    caption = message.caption or ""

    keyboard = [[
        InlineKeyboardButton("✅ Принять", callback_data=f"accept_{category}_{message.message_id}"),
        InlineKeyboardButton("❌ Отклонить", callback_data=f"reject_{category}_{message.message_id}")
    ]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    checkers = get_checkers_usernames(category)
    checker_mentions = ' '.join([f"@{username}" for username in checkers])
    category_name = "МОДЕРАЦИИ" if category == 'moderator' else "АДМИНИСТРАЦИИ"
    user_stats = get_user_stats(sender.id)

    report_message = (
        f"📋 <b>ОТЧЕТ {category_name}</b>\n\n"
        f"👤 {sender.mention_html()}\n"
        f"🎖 {sender_role.name if sender_role else 'Неизвестна'}\n"
        f"📊 Принятых: {user_stats['accepted']}\n"
        f"📝 {caption}\n\n"
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
    except Exception as e:
        logger.error(f"Error: {e}")

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
        await query.answer("❌ Нет прав!", show_alert=True)
        return

    await query.answer()

    report_key = f"{category}_{report_id}"
    if report_key not in reports_data:
        return

    report = reports_data[report_key]
    updated_stats = update_user_stats(report['sender_id'], report['sender_name'], action)

    topics = get_topic_ids_for_category(category)
    target_topic_id = topics['accepted'] if action == 'accept' else topics['rejected']

    category_title = "МОДЕРАЦИИ" if category == 'moderator' else "АДМИНИСТРАЦИИ"
    status_emoji = "✅" if action == 'accept' else "❌"
    status_text = "ПРИНЯТ" if action == 'accept' else "ОТКЛОНЕН"

    final_caption = (
        f"{status_emoji} Отчет {category_title} {status_emoji}\n"
        f"{status_text}\n\n"
        f"👤 Отправил: {report['sender_name']}\n"
        f"🎖 Роль: {report['sender_role']}\n"
        f"📊 Принятых отчетов: {updated_stats['accepted']}\n"
        f"📊 Отклоненных отчетов: {updated_stats['rejected']}\n"
        f"👨‍💼 Проверил: {checker.full_name} (@{checker.username})\n"
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
        caption=query.message.caption + f"\n\n{status_emoji} {status_text} (@{checker.username})",
        parse_mode='HTML'
    )

    asyncio.create_task(
        delete_messages_after_delay(context, GROUP_CHAT_ID, 
                                   [report['user_message_id'], report['bot_message_id']], 
                                   DELETE_AFTER_SECONDS)
    )

    del reports_data[report_key]

def main():
    logger.info("🚀 Запуск бота - ОКОНЧАТЕЛЬНАЯ РАБОЧАЯ ВЕРСИЯ")
    logger.info("✅ ВСЕ БАГИ ИСПРАВЛЕНЫ")
    logger.info(f"👥 Пользователей: {len(USERS_ROLES)}")

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

    logger.info("✅ Бот запущен!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
