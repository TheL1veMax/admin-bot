from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ChatPermissions
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
import logging
from enum import IntEnum
import os
import asyncio
import time
from datetime import datetime, timedelta
import psycopg2
from psycopg2.extras import RealDictCursor
from contextlib import contextmanager
import re

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = '8275792067:AAFkuxFjLrpsvInoheghSYIenRIqVLiBfCM'
GROUP_CHAT_ID = -1002418857530
PUBLIC_CHAT_USERNAME = "pmkk_loves_chat"
PUBLIC_CHAT_USERNAME = 'pmkk_loves_chat'
DATABASE_URL = os.getenv('DATABASE_URL')
# ID канала для логов
LOGS_CHAT_ID = -1003629150527

MODERATOR_REPORT_TOPIC_ID = 14
ADMIN_REPORT_TOPIC_ID = 13
ACCEPTED_MODERATOR_TOPIC_ID = 17849
REJECTED_MODERATOR_TOPIC_ID = 17852
ACCEPTED_ADMIN_TOPIC_ID = 17854
REJECTED_ADMIN_TOPIC_ID = 17856
WARNINGS_TOPIC_ID = 2976
BLACKLIST_TOPIC_ID = 3680

DELETE_AFTER_SECONDS = 60
PUNISHMENT_DELETE_SECONDS = 120  # 2 минуты
STATS_COOLDOWN = 10
MAX_WARNINGS = 3
AUTO_MUTE_HOURS = 12
DEPUTY_ADMIN_USERNAME = 'the_pr1estesss'
DUPLICATE_CHECK_DAYS = 3

stats_cooldowns = {}
pending_punishments = {}

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

USERS_ROLES = {
    'glavnyy_admin': Role.ГЛАВНЫЙ_АДМИН,
    'gerrinetwork': Role.СЗА,
    'the_pr1estesss': Role.ЗАМ_ГЛАВНОГО,
    'qwertyuiopasdfghjklzxcvbnm123411': Role.СТАРШИЙ_АДМИН,
    'mskmboky': Role.СТАРШИЙ_АДМИН,
    'whysparky': Role.СЗМ,
    'maga8c': Role.АДМИН,
    'qwelex_z': Role.АДМИН,
    'anayka_lol': Role.МЛ_АДМИН,
    'ml_admin2': Role.МЛ_АДМИН,
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
    'za_spartakmsk': Role.МОДЕРАТОР
}

reports_data = {}

@contextmanager
def get_db_connection():
    conn = psycopg2.connect(DATABASE_URL)
    try:
        yield conn
        conn.commit()
    except Exception as e:
        conn.rollback()
        logger.error(f"Database error: {e}")
        raise
    finally:
        conn.close()

def init_database():
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id BIGINT PRIMARY KEY,
                    username VARCHAR(255),
                    full_name VARCHAR(255),
                    last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS report_stats (
                    user_id BIGINT PRIMARY KEY,
                    username VARCHAR(255),
                    full_name VARCHAR(255),
                    accepted INTEGER DEFAULT 0,
                    rejected INTEGER DEFAULT 0
                )
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS warnings (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    username VARCHAR(255),
                    full_name VARCHAR(255),
                    reason TEXT,
                    issued_by VARCHAR(255),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    active BOOLEAN DEFAULT TRUE
                )
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS blacklist (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    username VARCHAR(255),
                    full_name VARCHAR(255),
                    days INTEGER,
                    reason TEXT,
                    issued_by VARCHAR(255),
                    start_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    end_date TIMESTAMP,
                    active BOOLEAN DEFAULT TRUE
                )
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS punishments (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    username VARCHAR(255),
                    full_name VARCHAR(255),
                    punishment_type VARCHAR(50),
                    duration VARCHAR(50),
                    rule VARCHAR(255),
                    issued_by BIGINT,
                    issued_by_username VARCHAR(255),
                    approved_by BIGINT,
                    approved_by_username VARCHAR(255),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            cur.execute("CREATE INDEX IF NOT EXISTS idx_warnings_user_id ON warnings(user_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_warnings_active ON warnings(active)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_blacklist_user_id ON blacklist(user_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_blacklist_active ON blacklist(active)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_punishments_user_id ON punishments(user_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_punishments_created_at ON punishments(created_at)")

def get_display_name(user):
    if hasattr(user, 'full_name') and user.full_name:
        name_str = str(user.full_name).strip()
        if name_str and name_str.lower() not in ['none', 'null', '', 'group']:
            return name_str
    if hasattr(user, 'first_name') and user.first_name:
        name_str = str(user.first_name).strip()
        if name_str and name_str.lower() not in ['none', 'null', '', 'group']:
            return name_str
    if hasattr(user, 'username') and user.username:
        return f"@{user.username}"
    return f"User_{user.id}"

def register_user(user_id: int, username: str, full_name: str):
    if not username:
        return
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO users (user_id, username, full_name, last_seen)
                    VALUES (%s, %s, %s, CURRENT_TIMESTAMP)
                    ON CONFLICT (user_id) DO UPDATE
                    SET username = EXCLUDED.username,
                        full_name = EXCLUDED.full_name,
                        last_seen = CURRENT_TIMESTAMP
                """, (user_id, username.lower(), full_name))
    except Exception as e:
        logger.error(f"Register user error: {e}")

def find_user_id_by_username(username: str):
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT user_id, full_name FROM users
                    WHERE LOWER(username) = LOWER(%s)
                """, (username,))
                result = cur.fetchone()
                if result:
                    return result['user_id'], result['full_name']
    except Exception as e:
        logger.error(f"Find user error: {e}")
    return None, None

def parse_report_details(caption: str):
    lines = caption.strip().split('\n')
    violator = None
    moderator = None
    recommendation = None
    rule = None

    for i, line in enumerate(lines):
        line = line.strip()
        if line.startswith('@') and violator is None:
            violator = line.lstrip('@')
        elif line.startswith('@') and violator and moderator is None:
            moderator = line.lstrip('@')
        elif '/' in line or 'h' in line.lower() or 'д' in line.lower() or 'warn' in line.lower():
            recommendation = line
        elif line and not line.startswith('@'):
            rule = line

    return {
        'violator': violator,
        'moderator': moderator,
        'recommendation': recommendation,
        'rule': rule
    }

def check_duplicate_punishment(user_id: int, rule: str, punishment_type: str, duration: str, days: int = DUPLICATE_CHECK_DAYS):
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT id, created_at, issued_by_username, approved_by_username
                    FROM punishments
                    WHERE user_id = %s 
                    AND LOWER(rule) = LOWER(%s)
                    AND punishment_type = %s
                    AND duration = %s
                    AND created_at > NOW() - INTERVAL '%s days'
                    ORDER BY created_at DESC
                    LIMIT 1
                """, (user_id, rule, punishment_type, duration, days))
                return cur.fetchone()
    except Exception as e:
        logger.error(f"Check duplicate error: {e}")
    return None

def add_punishment(user_id: int, username: str, full_name: str, punishment_type: str, 
                   duration: str, rule: str, issued_by: int, issued_by_username: str,
                   approved_by: int, approved_by_username: str):
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO punishments 
                    (user_id, username, full_name, punishment_type, duration, rule,
                     issued_by, issued_by_username, approved_by, approved_by_username)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (user_id, username, full_name, punishment_type, duration, rule,
                      issued_by, issued_by_username, approved_by, approved_by_username))
                return True
    except Exception as e:
        logger.error(f"Add punishment error: {e}")
    return False

def get_active_warnings_count(user_id: int):
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT COUNT(*) FROM punishments
                    WHERE user_id = %s 
                    AND punishment_type = 'warn'
                    AND created_at > NOW() - INTERVAL '30 days'
                """, (user_id,))
                return cur.fetchone()[0]
    except Exception as e:
        logger.error(f"Get warnings count error: {e}")
    return 0

def calculate_until_date(duration: str):
    if duration == 'forever':
        return None

    now = datetime.now()

    duration_map = {
        '1h': timedelta(hours=1),
        '2h': timedelta(hours=2),
        '6h': timedelta(hours=6),
        '12h': timedelta(hours=12),
        '1d': timedelta(days=1),
        '3d': timedelta(days=3),
        '7d': timedelta(days=7),
        '30d': timedelta(days=30)
    }

    delta = duration_map.get(duration)
    if delta:
        return int((now + delta).timestamp())

    return None

def get_user_stats(user_id: int):
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT accepted, rejected, full_name FROM report_stats
                    WHERE user_id = %s
                """, (user_id,))
                result = cur.fetchone()
                if result:
                    return {
                        'accepted': result['accepted'],
                        'rejected': result['rejected'],
                        'name': result['full_name']
                    }
    except Exception as e:
        logger.error(f"Get stats error: {e}")
    return {'accepted': 0, 'rejected': 0, 'name': ''}

def update_user_stats(user_id: int, user_name: str, action: str):
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    INSERT INTO report_stats (user_id, full_name, accepted, rejected)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (user_id) DO UPDATE
                    SET accepted = report_stats.accepted + EXCLUDED.accepted,
                        rejected = report_stats.rejected + EXCLUDED.rejected,
                        full_name = EXCLUDED.full_name
                    RETURNING accepted, rejected
                """, (
                    user_id, 
                    user_name,
                    1 if action == 'accept' else 0,
                    1 if action == 'reject' else 0
                ))
                result = cur.fetchone()
                return {
                    'accepted': result['accepted'],
                    'rejected': result['rejected'],
                    'name': user_name
                }
    except Exception as e:
        logger.error(f"Update stats error: {e}")
        return {'accepted': 0, 'rejected': 0, 'name': user_name}

def add_warning(user_id: int, user_name: str, username: str, reason: str, issued_by: str):
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO warnings (user_id, username, full_name, reason, issued_by)
                    VALUES (%s, %s, %s, %s, %s)
                """, (user_id, username, user_name, reason, issued_by))

                cur.execute("""
                    SELECT COUNT(*) FROM warnings
                    WHERE user_id = %s AND active = TRUE
                """, (user_id,))
                count = cur.fetchone()[0]
                return count
    except Exception as e:
        logger.error(f"Add warning error: {e}")
        return 0

def remove_warning(user_id: int, removed_by: str):
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT id FROM warnings
                    WHERE user_id = %s AND active = TRUE
                    ORDER BY created_at DESC
                    LIMIT 1
                """, (user_id,))
                result = cur.fetchone()

                if not result:
                    return None

                warning_id = result[0]
                cur.execute("UPDATE warnings SET active = FALSE WHERE id = %s", (warning_id,))

                cur.execute("""
                    SELECT COUNT(*) FROM warnings
                    WHERE user_id = %s AND active = TRUE
                """, (user_id,))
                count = cur.fetchone()[0]
                return count
    except Exception as e:
        logger.error(f"Remove warning error: {e}")
        return None

def add_to_blacklist(user_id: int, user_name: str, username: str, days: int, reason: str, issued_by: str):
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                end_date = datetime.now() + timedelta(days=days)

                cur.execute("UPDATE blacklist SET active = FALSE WHERE user_id = %s AND active = TRUE", (user_id,))

                cur.execute("""
                    INSERT INTO blacklist 
                    (user_id, username, full_name, days, reason, issued_by, end_date)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    RETURNING id, start_date, end_date
                """, (user_id, username, user_name, days, reason, issued_by, end_date))

                result = cur.fetchone()
                return {
                    'name': user_name,
                    'username': username,
                    'days': days,
                    'reason': reason,
                    'issued_by': issued_by,
                    'start_date': result['start_date'].isoformat(),
                    'end_date': result['end_date'].isoformat()
                }
    except Exception as e:
        logger.error(f"Add blacklist error: {e}")
        return None

def remove_from_blacklist(user_id: int):
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE blacklist SET active = FALSE WHERE user_id = %s AND active = TRUE", (user_id,))
                return cur.rowcount > 0
    except Exception as e:
        logger.error(f"Remove blacklist error: {e}")
        return False

async def delete_messages_after_delay(context: ContextTypes.DEFAULT_TYPE, chat_id: int, message_ids: list, delay: int):
    await asyncio.sleep(delay)
    for msg_id in message_ids:
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=msg_id)
        except Exception as e:
            logger.error(f"Failed to delete {msg_id}: {e}")


async def send_log(context: ContextTypes.DEFAULT_TYPE, log_text: str, parse_mode: str = 'HTML'):
    """Отправляет лог-сообщение в отдельный чат/канал"""
    try:
        await context.bot.send_message(
            chat_id=LOGS_CHAT_ID,
            text=log_text,
            parse_mode=parse_mode
        )
    except Exception as e:
        logger.error(f"Не удалось отправить лог: {e}")

def get_user_role(username: str):
    if not username:
        return None
    clean_username = username.strip().lstrip('@').lower()
    return USERS_ROLES.get(clean_username)

def can_check_report(checker_role, report_type: str):
    if checker_role is None:
        return False
    if checker_role >= Role.СЗА:
        return True
    if checker_role >= Role.СТАРШИЙ_АДМИН:
        return True
    if checker_role >= Role.АДМИН and report_type == 'moderator':
        return True
    return False

def can_issue_warning(user_role):
    return user_role is not None and user_role >= Role.СЗМ

def can_remove_warning(user_role):
    return user_role is not None and user_role >= Role.СЗМ

def can_manage_blacklist(user_role):
    return user_role is not None and user_role >= Role.СЗМ

def can_view_others_stats(user_role):
    return user_role is not None and user_role >= Role.СЗМ

def can_reset_stats(user_role):
    return user_role is not None and user_role >= Role.СЗМ

def can_punish_forever(user_role):
    return user_role is not None and user_role >= Role.ЗАМ_ГЛАВНОГО

def can_issue_punishment(user_role):
    return user_role is not None and user_role >= Role.СЗМ

def get_report_category(user_role):
    if user_role is None:
        return None
    if user_role >= Role.СЗА:
        return None
    if user_role <= Role.СТАРШИЙ_МОДЕРАТОР:
        return 'moderator'
    if Role.МЛ_АДМИН <= user_role <= Role.СЗМ:
        return 'admin'
    return None

def get_topic_ids_for_category(category: str):
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

def get_checkers_usernames(category: str):
    if category == 'moderator':
        return [username for username, role in USERS_ROLES.items() 
                if Role.АДМИН <= role < Role.ГЛАВНЫЙ_АДМИН]
    elif category == 'admin':
        return [username for username, role in USERS_ROLES.items() 
                if Role.СТАРШИЙ_АДМИН <= role < Role.ГЛАВНЫЙ_АДМИН]
    return []

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    user_display_name = get_display_name(user)
    register_user(user.id, user.username, user_display_name)
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

    user_display_name = get_display_name(user)
    register_user(user.id, user.username, user_display_name)
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
                    if target_user.id != 1087968824:
                        target_user_id = target_user.id
                        target_user_name = get_display_name(target_user)
                        target_username = target_user.username or str(target_user_id)
                        register_user(target_user_id, target_user.username, target_user_name)
                        break

        if target_user_id is None:
            found_id, _ = find_user_id_by_username(target_username)
            if found_id is not None:
                target_user_id = found_id
                target_user_name = f"@{target_username}"
            else:
                error_msg = await message.reply_text(f"❌ @{target_username} не найден!")
                asyncio.create_task(delete_messages_after_delay(context, message.chat.id, [message.message_id, error_msg.message_id], DELETE_AFTER_SECONDS))
                return
    elif message.reply_to_message:
        target_user = message.reply_to_message.from_user
        if target_user.id == 1087968824:
            target_user_id = user.id
            target_user_name = user_display_name
            target_username = user.username or str(user.id)
        else:
            target_user_id = target_user.id
            target_user_name = get_display_name(target_user)
            target_username = target_user.username or str(target_user_id)
            register_user(target_user_id, target_user.username, target_user_name)
    else:
        target_user_id = user.id
        target_user_name = user_display_name
        target_username = user.username or str(user.id)

    user_stats = get_user_stats(target_user_id)
    target_role = get_user_role(target_username) if isinstance(target_username, str) and not target_username.isdigit() else None
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
            f"👤 {target_user_name}\n"
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
    issuer_display_name = get_display_name(issuer)
    register_user(issuer.id, issuer.username, issuer_display_name)
    issuer_role = get_user_role(issuer.username)

    if not can_issue_warning(issuer_role):
        error_msg = await message.reply_text("❌ Нет прав! (СЗМ+)")
        asyncio.create_task(delete_messages_after_delay(context, message.chat.id, [message.message_id, error_msg.message_id], DELETE_AFTER_SECONDS))
        return

    target_user_id = None
    target_user_name = None
    target_username = None
    reason = None

    text = message.text.strip()
    parts = text.split(maxsplit=2)

    if len(parts) >= 3 and (parts[1].startswith('@') or parts[1].isdigit()):
        target_username = parts[1].lstrip('@')
        reason = parts[2]

        if message.entities:
            for entity in message.entities:
                if entity.type == "text_mention":
                    target_user = entity.user
                    if target_user.id != 1087968824:
                        target_user_id = target_user.id
                        target_user_name = get_display_name(target_user)
                        target_username = target_user.username or str(target_user_id)
                        register_user(target_user_id, target_user.username, target_user_name)
                        break

        if target_user_id is None:
            found_id, _ = find_user_id_by_username(target_username)
            if found_id is not None:
                target_user_id = found_id
                target_user_name = f"@{target_username}"
            else:
                error_msg = await message.reply_text(f"❌ @{target_username} не найден!\n💡 Попросите написать /start боту")
                asyncio.create_task(delete_messages_after_delay(context, message.chat.id, [message.message_id, error_msg.message_id], DELETE_AFTER_SECONDS))
                return
    elif message.reply_to_message:
        target_user = message.reply_to_message.from_user

        if target_user.id == 1087968824:
            error_msg = await message.reply_text("❌ Нельзя выдать выговор анонимному сообщению!")
            asyncio.create_task(delete_messages_after_delay(context, message.chat.id, [message.message_id, error_msg.message_id], DELETE_AFTER_SECONDS))
            return

        target_user_id = target_user.id
        target_user_name = get_display_name(target_user)
        target_username = target_user.username or str(target_user_id)
        register_user(target_user_id, target_user.username, target_user_name)

        if len(parts) < 2:
            error_msg = await message.reply_text("❌ Укажите причину!\n/vg причина")
            asyncio.create_task(delete_messages_after_delay(context, message.chat.id, [message.message_id, error_msg.message_id], DELETE_AFTER_SECONDS))
            return
        reason = ' '.join(parts[1:])
    else:
        error_msg = await message.reply_text("❌ Формат: /vg @username причина")
        asyncio.create_task(delete_messages_after_delay(context, message.chat.id, [message.message_id, error_msg.message_id], DELETE_AFTER_SECONDS))
        return

    warning_count = add_warning(target_user_id, target_user_name, target_username or str(target_user_id), reason, issuer.username or issuer_display_name)
    warning_emoji = "⚠️" if warning_count < MAX_WARNINGS else "🚫"
    user_link = f"<a href='tg://user?id={target_user_id}'>{target_user_name}</a>"

    warning_message = (
        f"{warning_emoji} <b>ВЫГОВОР #{warning_count}/{MAX_WARNINGS}</b>\n\n"
        f"👤 {user_link}\n"
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

    log_text = (
        f"⚠️ <b>ВЫДАН ВЫГОВОР #{warning_count}/{MAX_WARNINGS}</b>\n\n"
        f"👤 Получил: {target_user_name} (@{target_username})\n"
        f"🆔 ID: {target_user_id}\n"
        f"📝 Причина: {reason}\n"
        f"👨‍💼 Выдал: @{issuer.username} ({issuer_role.name})\n"
        f"⏰ {datetime.now().strftime('%d.%m.%Y %H:%M')}"
    )
    await send_log(context, log_text)

    success_msg = await message.reply_text(f"✅ Выговор #{warning_count} выдан {user_link}", parse_mode='HTML')
    asyncio.create_task(delete_messages_after_delay(context, message.chat.id, [message.message_id, success_msg.message_id], PUNISHMENT_DELETE_SECONDS))

async def remove_warning_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if message.chat.id != GROUP_CHAT_ID:
        await message.reply_text("❌ Только в группе!")
        return

    issuer = message.from_user
    issuer_display_name = get_display_name(issuer)
    register_user(issuer.id, issuer.username, issuer_display_name)
    issuer_role = get_user_role(issuer.username)

    if not can_remove_warning(issuer_role):
        error_msg = await message.reply_text("❌ Нет прав!")
        asyncio.create_task(delete_messages_after_delay(context, message.chat.id, [message.message_id, error_msg.message_id], DELETE_AFTER_SECONDS))
        return

    target_user_id = None
    target_user_name = None
    target_username = None

    text = message.text.strip()
    parts = text.split(maxsplit=1)

    if len(parts) >= 2 and (parts[1].startswith('@') or parts[1].replace('@', '').isdigit()):
        target_username = parts[1].lstrip('@')

        if message.entities:
            for entity in message.entities:
                if entity.type == "text_mention":
                    target_user = entity.user
                    if target_user.id != 1087968824:
                        target_user_id = target_user.id
                        target_user_name = get_display_name(target_user)
                        target_username = target_user.username or str(target_user_id)
                        register_user(target_user_id, target_user.username, target_user_name)
                        break

        if target_user_id is None:
            found_id, _ = find_user_id_by_username(target_username)
            if found_id is not None:
                target_user_id = found_id
                target_user_name = f"@{target_username}"
            else:
                error_msg = await message.reply_text(f"❌ @{target_username} не найден!")
                asyncio.create_task(delete_messages_after_delay(context, message.chat.id, [message.message_id, error_msg.message_id], DELETE_AFTER_SECONDS))
                return
    elif message.reply_to_message:
        target_user = message.reply_to_message.from_user

        if target_user.id == 1087968824:
            error_msg = await message.reply_text("❌ Нельзя снять выговор с анонимного сообщения!")
            asyncio.create_task(delete_messages_after_delay(context, message.chat.id, [message.message_id, error_msg.message_id], DELETE_AFTER_SECONDS))
            return

        target_user_id = target_user.id
        target_user_name = get_display_name(target_user)
        target_username = target_user.username or str(target_user_id)
        register_user(target_user_id, target_user.username, target_user_name)
    else:
        error_msg = await message.reply_text("❌ Формат: /svg @username")
        asyncio.create_task(delete_messages_after_delay(context, message.chat.id, [message.message_id, error_msg.message_id], DELETE_AFTER_SECONDS))
        return

    new_count = remove_warning(target_user_id, issuer.username or issuer_display_name)

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
    asyncio.create_task(delete_messages_after_delay(context, message.chat.id, [message.message_id, success_msg.message_id], PUNISHMENT_DELETE_SECONDS))

async def blacklist_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if message.chat.id != GROUP_CHAT_ID:
        return

    issuer = message.from_user
    issuer_display_name = get_display_name(issuer)
    register_user(issuer.id, issuer.username, issuer_display_name)
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

    text = message.text.strip()
    parts = text.split(maxsplit=3)

    if len(parts) >= 4 and (parts[1].startswith('@') or parts[1].isdigit()):
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
                    if target_user.id != 1087968824:
                        target_user_id = target_user.id
                        target_user_name = get_display_name(target_user)
                        target_username = target_user.username or str(target_user_id)
                        register_user(target_user_id, target_user.username, target_user_name)
                        break

        if target_user_id is None:
            found_id, _ = find_user_id_by_username(target_username)
            if found_id is not None:
                target_user_id = found_id
                target_user_name = f"@{target_username}"
            else:
                error_msg = await message.reply_text(f"❌ @{target_username} не найден!")
                asyncio.create_task(delete_messages_after_delay(context, message.chat.id, [message.message_id, error_msg.message_id], DELETE_AFTER_SECONDS))
                return
    elif message.reply_to_message:
        target_user = message.reply_to_message.from_user

        if target_user.id == 1087968824:
            error_msg = await message.reply_text("❌ Нельзя добавить анонимное сообщение в ЧС!")
            asyncio.create_task(delete_messages_after_delay(context, message.chat.id, [message.message_id, error_msg.message_id], DELETE_AFTER_SECONDS))
            return

        target_user_id = target_user.id
        target_user_name = get_display_name(target_user)
        target_username = target_user.username or str(target_user_id)
        register_user(target_user_id, target_user.username, target_user_name)

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
        error_msg = await message.reply_text("❌ Формат: /bl @username дни причина")
        asyncio.create_task(delete_messages_after_delay(context, message.chat.id, [message.message_id, error_msg.message_id], DELETE_AFTER_SECONDS))
        return

    entry = add_to_blacklist(target_user_id, target_user_name, target_username or str(target_user_id), days, reason, issuer.username or issuer_display_name)
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

    log_text = (
        f"🚫 <b>ДОБАВЛЕН В ЧЕРНЫЙ СПИСОК</b>\n\n"
        f"👤 Пользователь: {target_user_name} (@{target_username})\n"
        f"🆔 ID: {target_user_id}\n"
        f"📝 Причина: {reason}\n"
        f"⏱ Срок: {days} дн. ({end_date.strftime('%d.%m.%Y')})\n"
        f"👨‍💼 Выдал: @{issuer.username} ({issuer_role.name})\n"
        f"⏰ {datetime.now().strftime('%d.%m.%Y %H:%M')}"
    )
    await send_log(context, log_text)

    success_msg = await message.reply_text(f"✅ {user_link} в ЧС", parse_mode='HTML')
    asyncio.create_task(delete_messages_after_delay(context, message.chat.id, [message.message_id, success_msg.message_id], PUNISHMENT_DELETE_SECONDS))

async def unblacklist_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if message.chat.id != GROUP_CHAT_ID:
        return

    issuer = message.from_user
    issuer_display_name = get_display_name(issuer)
    register_user(issuer.id, issuer.username, issuer_display_name)
    issuer_role = get_user_role(issuer.username)

    if not can_manage_blacklist(issuer_role):
        error_msg = await message.reply_text("❌ Нет прав!")
        asyncio.create_task(delete_messages_after_delay(context, message.chat.id, [message.message_id, error_msg.message_id], DELETE_AFTER_SECONDS))
        return

    target_user_id = None
    target_user_name = None
    target_username = None

    text = message.text.strip()
    parts = text.split(maxsplit=1)

    if len(parts) >= 2 and (parts[1].startswith('@') or parts[1].replace('@', '').isdigit()):
        target_username = parts[1].lstrip('@')

        if message.entities:
            for entity in message.entities:
                if entity.type == "text_mention":
                    target_user = entity.user
                    if target_user.id != 1087968824:
                        target_user_id = target_user.id
                        target_user_name = get_display_name(target_user)
                        target_username = target_user.username or str(target_user_id)
                        register_user(target_user_id, target_user.username, target_user_name)
                        break

        if target_user_id is None:
            found_id, _ = find_user_id_by_username(target_username)
            if found_id is not None:
                target_user_id = found_id
                target_user_name = f"@{target_username}"
            else:
                error_msg = await message.reply_text(f"❌ @{target_username} не найден!")
                asyncio.create_task(delete_messages_after_delay(context, message.chat.id, [message.message_id, error_msg.message_id], DELETE_AFTER_SECONDS))
                return
    elif message.reply_to_message:
        target_user = message.reply_to_message.from_user

        if target_user.id == 1087968824:
            error_msg = await message.reply_text("❌ Нельзя убрать анонимное сообщение из ЧС!")
            asyncio.create_task(delete_messages_after_delay(context, message.chat.id, [message.message_id, error_msg.message_id], DELETE_AFTER_SECONDS))
            return

        target_user_id = target_user.id
        target_user_name = get_display_name(target_user)
        target_username = target_user.username or str(target_user_id)
        register_user(target_user_id, target_user.username, target_user_name)
    else:
        error_msg = await message.reply_text("❌ Формат: /ubl @username")
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
    asyncio.create_task(delete_messages_after_delay(context, message.chat.id, [message.message_id, success_msg.message_id], PUNISHMENT_DELETE_SECONDS))

async def reset_accepted_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if message.chat.id != GROUP_CHAT_ID:
        return

    issuer = message.from_user
    issuer_display_name = get_display_name(issuer)
    register_user(issuer.id, issuer.username, issuer_display_name)
    issuer_role = get_user_role(issuer.username)

    if not can_reset_stats(issuer_role):
        error_msg = await message.reply_text("❌ Нет прав!")
        asyncio.create_task(delete_messages_after_delay(context, message.chat.id, [message.message_id, error_msg.message_id], DELETE_AFTER_SECONDS))
        return

    target_user_id = None
    target_user_name = None
    target_username = None

    text = message.text.strip()
    parts = text.split(maxsplit=1)

    if len(parts) >= 2 and (parts[1].startswith('@') or parts[1].replace('@', '').isdigit()):
        target_username = parts[1].lstrip('@')

        if message.entities:
            for entity in message.entities:
                if entity.type == "text_mention":
                    target_user = entity.user
                    if target_user.id != 1087968824:
                        target_user_id = target_user.id
                        target_user_name = get_display_name(target_user)
                        target_username = target_user.username or str(target_user_id)
                        register_user(target_user_id, target_user.username, target_user_name)
                        break

        if target_user_id is None:
            found_id, _ = find_user_id_by_username(target_username)
            if found_id is not None:
                target_user_id = found_id
                target_user_name = f"@{target_username}"
            else:
                error_msg = await message.reply_text(f"❌ @{target_username} не найден!")
                asyncio.create_task(delete_messages_after_delay(context, message.chat.id, [message.message_id, error_msg.message_id], DELETE_AFTER_SECONDS))
                return
    elif message.reply_to_message:
        target_user = message.reply_to_message.from_user

        if target_user.id == 1087968824:
            error_msg = await message.reply_text("❌ Нельзя сбросить статистику анонимного сообщения!")
            asyncio.create_task(delete_messages_after_delay(context, message.chat.id, [message.message_id, error_msg.message_id], DELETE_AFTER_SECONDS))
            return

        target_user_id = target_user.id
        target_user_name = get_display_name(target_user)
        target_username = target_user.username or str(target_user_id)
        register_user(target_user_id, target_user.username, target_user_name)
    else:
        error_msg = await message.reply_text("❌ Формат: /sp @username")
        asyncio.create_task(delete_messages_after_delay(context, message.chat.id, [message.message_id, error_msg.message_id], DELETE_AFTER_SECONDS))
        return

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT accepted FROM report_stats WHERE user_id = %s", (target_user_id,))
                result = cur.fetchone()

                if not result:
                    error_msg = await message.reply_text(f"❌ Не найден в статистике!")
                    asyncio.create_task(delete_messages_after_delay(context, message.chat.id, [message.message_id, error_msg.message_id], DELETE_AFTER_SECONDS))
                    return

                old_value = result[0]
                cur.execute("UPDATE report_stats SET accepted = 0 WHERE user_id = %s", (target_user_id,))
    except Exception as e:
        logger.error(f"Reset accepted error: {e}")
        return

    user_link = f"<a href='tg://user?id={target_user_id}'>{target_user_name}</a>"
    success_msg = await message.reply_text(f"✅ Принятые сброшены\n{user_link}: {old_value} → 0", parse_mode='HTML')
    asyncio.create_task(delete_messages_after_delay(context, message.chat.id, [message.message_id, success_msg.message_id], DELETE_AFTER_SECONDS))

async def reset_rejected_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if message.chat.id != GROUP_CHAT_ID:
        return

    issuer = message.from_user
    issuer_display_name = get_display_name(issuer)
    register_user(issuer.id, issuer.username, issuer_display_name)
    issuer_role = get_user_role(issuer.username)

    if not can_reset_stats(issuer_role):
        error_msg = await message.reply_text("❌ Нет прав!")
        asyncio.create_task(delete_messages_after_delay(context, message.chat.id, [message.message_id, error_msg.message_id], DELETE_AFTER_SECONDS))
        return

    target_user_id = None
    target_user_name = None
    target_username = None

    text = message.text.strip()
    parts = text.split(maxsplit=1)

    if len(parts) >= 2 and (parts[1].startswith('@') or parts[1].replace('@', '').isdigit()):
        target_username = parts[1].lstrip('@')

        if message.entities:
            for entity in message.entities:
                if entity.type == "text_mention":
                    target_user = entity.user
                    if target_user.id != 1087968824:
                        target_user_id = target_user.id
                        target_user_name = get_display_name(target_user)
                        target_username = target_user.username or str(target_user_id)
                        register_user(target_user_id, target_user.username, target_user_name)
                        break

        if target_user_id is None:
            found_id, _ = find_user_id_by_username(target_username)
            if found_id is not None:
                target_user_id = found_id
                target_user_name = f"@{target_username}"
            else:
                error_msg = await message.reply_text(f"❌ @{target_username} не найден!")
                asyncio.create_task(delete_messages_after_delay(context, message.chat.id, [message.message_id, error_msg.message_id], DELETE_AFTER_SECONDS))
                return
    elif message.reply_to_message:
        target_user = message.reply_to_message.from_user

        if target_user.id == 1087968824:
            error_msg = await message.reply_text("❌ Нельзя сбросить статистику анонимного сообщения!")
            asyncio.create_task(delete_messages_after_delay(context, message.chat.id, [message.message_id, error_msg.message_id], DELETE_AFTER_SECONDS))
            return

        target_user_id = target_user.id
        target_user_name = get_display_name(target_user)
        target_username = target_user.username or str(target_user_id)
        register_user(target_user_id, target_user.username, target_user_name)
    else:
        error_msg = await message.reply_text("❌ Формат: /so @username")
        asyncio.create_task(delete_messages_after_delay(context, message.chat.id, [message.message_id, error_msg.message_id], DELETE_AFTER_SECONDS))
        return

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT rejected FROM report_stats WHERE user_id = %s", (target_user_id,))
                result = cur.fetchone()

                if not result:
                    error_msg = await message.reply_text(f"❌ Не найден в статистике!")
                    asyncio.create_task(delete_messages_after_delay(context, message.chat.id, [message.message_id, error_msg.message_id], DELETE_AFTER_SECONDS))
                    return

                old_value = result[0]
                cur.execute("UPDATE report_stats SET rejected = 0 WHERE user_id = %s", (target_user_id,))
    except Exception as e:
        logger.error(f"Reset rejected error: {e}")
        return

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
    sender_display_name = get_display_name(sender)
    register_user(sender.id, sender.username, sender_display_name)
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

    report_message = (
        f"📋 <b>НОВЫЙ ОТЧЕТ {category_name}</b>\n\n"
        f"👤 Отправил: {sender.mention_html()}\n"
        f"🎖 Роль: {sender_role.name if sender_role else 'Неизвестна'}\n"
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
            'sender_name': sender_display_name,
            'sender_username': sender.username,
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
    await query.answer()

    data = query.data

    if data.startswith('accept_') or data.startswith('reject_'):
        await handle_report_decision(update, context)
    elif data.startswith('punish_'):
        await handle_punishment_type(update, context)
    elif data.startswith('duration_'):
        await handle_punishment_duration(update, context)
    elif data.startswith('confirm_duplicate_'):
        await handle_duplicate_confirmation(update, context)
    elif data.startswith('back_punishment_'):
        report_id = data.split('_')[-1]
        punishment_key = f"punishment_{report_id}"
        if punishment_key not in pending_punishments:
            await query.answer("❌ Данные не найдены!", show_alert=True)
            return
        punishment_data = pending_punishments[punishment_key]

        keyboard = [
            [InlineKeyboardButton("🔇 Мут", callback_data=f"punish_mute_{report_id}")],
            [InlineKeyboardButton("⚠️ Варн", callback_data=f"punish_warn_{report_id}")],
            [InlineKeyboardButton("🚫 Бан", callback_data=f"punish_ban_{report_id}")],
            [InlineKeyboardButton("✋ Выдать вручную", callback_data=f"punish_manual_{report_id}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        punishment_text = (
            f"⚖️ Выберите наказание\n\n"
            f"👤 Нарушитель: @{punishment_data['violator_username']}\n"
            f"📋 Правило: {punishment_data['rule']}\n"
            f"💡 Рекомендация: {punishment_data.get('recommendation') or 'не указана'}"
        )
        await query.edit_message_text(punishment_text, parse_mode='HTML', reply_markup=reply_markup)
    elif data.startswith('cancel_punishment_'):
        punishment_key = f"punishment_{data.split('_')[-1]}"
        if punishment_key in pending_punishments:
            del pending_punishments[punishment_key]
        await query.edit_message_text("❌ Отменено")

async def handle_report_decision(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    parts = query.data.split('_')
    action = parts[0]
    category = parts[1]
    report_id = parts[2]

    checker = query.from_user
    checker_display_name = get_display_name(checker)
    register_user(checker.id, checker.username, checker_display_name)
    checker_role = get_user_role(checker.username)

    if not can_check_report(checker_role, category):
        await query.answer("❌ Нет прав!", show_alert=True)
        return

    report_key = f"{category}_{report_id}"
    if report_key not in reports_data:
        await query.answer("❌ Отчет не найден!", show_alert=True)
        return

    report = reports_data[report_key]
    updated_stats = update_user_stats(report['sender_id'], report['sender_name'], action)

    topics = get_topic_ids_for_category(category)
    target_topic_id = topics['accepted'] if action == 'accept' else topics['rejected']

    category_title = "МОДЕРАЦИИ" if category == 'moderator' else "АДМИНИСТРАЦИИ"
    status_emoji = "✅" if action == 'accept' else "❌"
    status_text = "ПРИНЯТ" if action == 'accept' else "ОТКЛОНЕН"

    checker_display = f"{checker_display_name} (@{checker.username})" if checker_role >= Role.СЗА else checker_role.name

    final_caption = (
        f"{status_emoji} <b>Отчет {category_title} {status_text}</b>\n\n"
        f"👤 Отправил: {report['sender_name']}\n"
        f"🎖 Роль: {report['sender_role']}\n"
        f"📊 Принятых отчетов: {updated_stats['accepted']}\n"
        f"📝 Детали:\n{report['caption']}\n\n"
        f"👨‍💼 Проверил: {checker_display}\n"
        f"🎖 Роль проверяющего: {checker_role.name}"
    )

    await context.bot.send_photo(
        chat_id=GROUP_CHAT_ID,
        message_thread_id=target_topic_id,
        photo=report['photo'],
        caption=final_caption,
        parse_mode='HTML'
    )

    status_emoji = "✅" if action == "accept" else "❌"
    log_text = (
        f"{status_emoji} <b>ОТЧЕТ {'ПРИНЯТ' if action == 'accept' else 'ОТКЛОНЕН'}</b>\n\n"
        f"📁 Категория: {category_title}\n"
        f"👤 Отправитель: {report['sender_name']} (@{report['sender_username']})\n"
        f"🎖 Роль: {report['sender_role']}\n"
        f"👨‍💼 Проверил: {checker_display} (@{checker.username})\n"
        f"📊 Статистика: ✅{updated_stats['accepted']} | ❌{updated_stats['rejected']}\n"
        f"⏰ {datetime.now().strftime('%d.%m.%Y %H:%M')}"
    )
    await send_log(context, log_text)

    await query.edit_message_caption(
        caption=query.message.caption + f"\n\n{status_emoji} {status_text} (@{checker.username})",
        parse_mode='HTML'
    )

    if action == 'accept':
        parsed = parse_report_details(report['caption'])

        if parsed['violator'] and parsed['rule']:
            violator_username = parsed['violator']
            violator_id, violator_name = find_user_id_by_username(violator_username)
            if not violator_id:
                await context.bot.send_message(chat_id=LOGS_CHAT_ID, text=f"⚠️ @{violator_username} НЕ НАЙДЕН В БАЗЕ", parse_mode='HTML')
            if violator_id:
                punishment_key = f"punishment_{report_id}"
                pending_punishments[punishment_key] = {
                    'violator_id': violator_id,
                    'violator_username': parsed['violator'],
                    'violator_name': violator_name or f"@{parsed['violator']}",
                    'moderator_id': report['sender_id'],
                    'moderator_username': report['sender_username'],
                    'approver_id': checker.id,
                    'approver_username': checker.username,
                    'approver_role': checker_role,
                    'rule': parsed['rule'],
                    'recommendation': parsed['recommendation'] or ''
                }

                keyboard = [
                    [InlineKeyboardButton("🔇 Мут", callback_data=f"punish_mute_{report_id}")],
                    [InlineKeyboardButton("⚠️ Варн", callback_data=f"punish_warn_{report_id}")],
                    [InlineKeyboardButton("🚫 Бан", callback_data=f"punish_ban_{report_id}")],
                    [InlineKeyboardButton("✋ Выдать вручную", callback_data=f"punish_manual_{report_id}")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)

                punishment_text = (
                    f"⚖️ <b>Выберите наказание</b>\n\n"
                    f"👤 Нарушитель: @{parsed['violator']}\n"
                    f"📋 Правило: {parsed['rule']}\n"
                    f"💡 Рекомендация: {parsed['recommendation'] or 'не указана'}"
                )

                await query.message.reply_text(
                    punishment_text,
                    parse_mode='HTML',
                    reply_markup=reply_markup
                )

    asyncio.create_task(
        delete_messages_after_delay(context, GROUP_CHAT_ID, 
                                   [report['user_message_id'], report['bot_message_id']], 
                                   DELETE_AFTER_SECONDS)
    )

    del reports_data[report_key]

async def handle_punishment_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    parts = query.data.split('_')
    punishment_type = parts[1]
    report_id = parts[2]

    punishment_key = f"punishment_{report_id}"

    # Обработка ручной выдачи
    if punishment_type == "manual":
        if punishment_key not in pending_punishments:
            await query.answer("❌ Данные не найдены!", show_alert=True)
            return

        punishment_data = pending_punishments[punishment_key]
        manual_text = (
            f"✋ <b>Выдайте наказание вручную</b>\n\n"
            f"👤 Нарушитель: @{punishment_data['violator_username']}\n"
            f"🆔 ID: {punishment_data['violator_id']}\n"
            f"📋 Правило: {punishment_data['rule']}\n"
            f"💡 Рекомендация: {punishment_data.get('recommendation') or 'Не указана'}\n\n"
            f"⚠️ Наказание нужно выдать в соответствии с правилами"
        )
        bot_msg = await query.edit_message_text(manual_text, parse_mode='HTML')

        # Автоудаление через 2 минуты
        asyncio.create_task(delete_messages_after_delay(context, GROUP_CHAT_ID, [bot_msg.message_id], 120))

        # Логируем
        log_text = (
            f"✋ <b>ВЫДАНО ВРУЧНУЮ</b>\n\n"
            f"👤 Нарушитель: @{punishment_data['violator_username']} (ID: {punishment_data['violator_id']})\n"
            f"📋 Правило: {punishment_data['rule']}\n"
            f"💡 Рекомендация: {punishment_data.get('recommendation') or 'Не указана'}\n"
            f"👨‍💼 Модератор: @{punishment_data['moderator_username']}\n"
            f"✅ Решение принял: @{query.from_user.username}\n"
            f"⏰ {datetime.now().strftime('%d.%m.%Y %H:%M')}\n\n"
            f"⚠️ Наказание нужно выдать в соответствии с правилами"
        )
        await send_log(context, log_text)

        del pending_punishments[punishment_key]
        return
    if punishment_key not in pending_punishments:
        await query.answer("❌ Данные не найдены!", show_alert=True)
        return

    punishment_data = pending_punishments[punishment_key]
    punishment_data['type'] = punishment_type

    checker_role = get_user_role(query.from_user.username)

    if not can_issue_punishment(checker_role):
        await query.answer("❌ Нет прав на выдачу наказаний! (СЗМ+)", show_alert=True)
        return

    if punishment_type == 'warn':
        violator_id = punishment_data['violator_id']
        rule = punishment_data['rule']

        duplicate = check_duplicate_punishment(violator_id, rule, 'warn', 'once')

        if duplicate:
            days_ago = (datetime.now() - duplicate['created_at']).days
            keyboard = [[
                InlineKeyboardButton("✅ Да", callback_data=f"confirm_duplicate_warn_{report_id}"),
                InlineKeyboardButton("❌ Нет", callback_data=f"cancel_punishment_{report_id}")
            ]]
            reply_markup = InlineKeyboardMarkup(keyboard)

            warning_text = (
                f"⚠️ <b>ВНИМАНИЕ!</b>\n\n"
                f"@{punishment_data['violator_username']} уже получал варн\n"
                f"за \"{rule}\" {days_ago} дн. назад\n\n"
                f"Продолжить?"
            )

            await query.edit_message_text(
                warning_text,
                parse_mode='HTML',
                reply_markup=reply_markup
            )
            return

        await execute_punishment(context, punishment_data, 'warn', 'once')
        bot_msg = await query.edit_message_text(f"✅ Варн выдан @{punishment_data['violator_username']}")

        # Автоудаление через 2 минуты
        asyncio.create_task(delete_messages_after_delay(context, GROUP_CHAT_ID, [bot_msg.message_id], 120))
        del pending_punishments[punishment_key]

    else:
        can_forever = can_punish_forever(checker_role)

        keyboard = [
            [
                InlineKeyboardButton("1ч", callback_data=f"duration_{punishment_type}_1h_{report_id}"),
                InlineKeyboardButton("2ч", callback_data=f"duration_{punishment_type}_2h_{report_id}"),
                InlineKeyboardButton("6ч", callback_data=f"duration_{punishment_type}_6h_{report_id}"),
                InlineKeyboardButton("12ч", callback_data=f"duration_{punishment_type}_12h_{report_id}")
            ],
            [
                InlineKeyboardButton("1д", callback_data=f"duration_{punishment_type}_1d_{report_id}"),
                InlineKeyboardButton("3д", callback_data=f"duration_{punishment_type}_3d_{report_id}"),
                InlineKeyboardButton("7д", callback_data=f"duration_{punishment_type}_7d_{report_id}"),
                InlineKeyboardButton("30д", callback_data=f"duration_{punishment_type}_30d_{report_id}")
            ]
        ]

        if can_forever:
            keyboard.append([
                InlineKeyboardButton("Навсегда", callback_data=f"duration_{punishment_type}_forever_{report_id}")
            ])

        # Кнопка "Назад"
        keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data=f"back_punishment_{report_id}")])

        reply_markup = InlineKeyboardMarkup(keyboard)

        punishment_name = "мута" if punishment_type == 'mute' else "бана"

        await query.edit_message_text(
            f"⏱ Выберите срок {punishment_name}:",
            reply_markup=reply_markup
        )

async def handle_punishment_duration(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    parts = query.data.split('_')
    punishment_type = parts[1]
    duration = parts[2]
    report_id = parts[3]

    punishment_key = f"punishment_{report_id}"
    if punishment_key not in pending_punishments:
        await query.answer("❌ Данные не найдены!", show_alert=True)
        return

    punishment_data = pending_punishments[punishment_key]
    violator_id = punishment_data['violator_id']
    rule = punishment_data['rule']

    checker_role = get_user_role(query.from_user.username)

    if duration == 'forever' and not can_punish_forever(checker_role):
        await query.answer("❌ Нет прав на бессрочные наказания! (только ЗГА и СЗА)", show_alert=True)
        return

    duplicate = check_duplicate_punishment(violator_id, rule, punishment_type, duration)

    if duplicate:
        days_ago = (datetime.now() - duplicate['created_at']).days
        keyboard = [[
            InlineKeyboardButton("✅ Да", callback_data=f"confirm_duplicate_{punishment_type}_{duration}_{report_id}"),
            InlineKeyboardButton("❌ Нет", callback_data=f"cancel_punishment_{report_id}")
        ]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        punishment_name = "мут" if punishment_type == 'mute' else "бан"
        duration_text = "навсегда" if duration == 'forever' else duration

        warning_text = (
            f"⚠️ <b>ВНИМАНИЕ!</b>\n\n"
            f"@{punishment_data['violator_username']} уже получал\n"
            f"{punishment_name} {duration_text} за \"{rule}\"\n"
            f"{days_ago} дн. назад\n\n"
            f"Продолжить?"
        )

        await query.edit_message_text(
            warning_text,
            parse_mode='HTML',
            reply_markup=reply_markup
        )
        return

    await execute_punishment(context, punishment_data, punishment_type, duration)

    punishment_name = "Мут" if punishment_type == 'mute' else "Бан"
    duration_text = "навсегда" if duration == 'forever' else duration

    await query.edit_message_text(
        f"✅ {punishment_name} {duration_text} выдан @{punishment_data['violator_username']}"
    )

    del pending_punishments[punishment_key]

async def handle_duplicate_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data.replace('confirm_duplicate_', '')
    parts = data.split('_')

    if data.startswith('warn_'):
        punishment_type = 'warn'
        duration = 'once'
        report_id = parts[1]
    else:
        punishment_type = parts[0]
        duration = parts[1]
        report_id = parts[2]

    punishment_key = f"punishment_{report_id}"
    if punishment_key not in pending_punishments:
        await query.answer("❌ Данные не найдены!", show_alert=True)
        return

    punishment_data = pending_punishments[punishment_key]

    await execute_punishment(context, punishment_data, punishment_type, duration)

    punishment_name = "Варн" if punishment_type == 'warn' else ("Мут" if punishment_type == 'mute' else "Бан")
    duration_text = "" if punishment_type == 'warn' else (" навсегда" if duration == 'forever' else f" {duration}")

    await query.edit_message_text(
        f"✅ {punishment_name}{duration_text} выдан @{punishment_data['violator_username']}"
    )

    del pending_punishments[punishment_key]

async def execute_punishment(context: ContextTypes.DEFAULT_TYPE, punishment_data: dict, 
                            punishment_type: str, duration: str):

    violator_id = punishment_data['violator_id']
    violator_username = punishment_data['violator_username']
    violator_name = punishment_data['violator_name']
    moderator_username = punishment_data['moderator_username']
    approver_username = punishment_data['approver_username']
    approver_role = punishment_data.get('approver_role')
    rule = punishment_data['rule']

    add_punishment(
        violator_id, violator_username, violator_name,
        punishment_type, duration, rule,
        punishment_data['moderator_id'], moderator_username,
        punishment_data['approver_id'], approver_username
    )

    punishment_emoji = {
        'mute': '🚫',
        'warn': '⚠️',
        'ban': '🔒'
    }

    punishment_name = {
        'mute': 'мут',
        'warn': 'варн',
        'ban': 'бан'
    }

    duration_text = {
        '1h': '1 час',
        '2h': '2 часа',
        '6h': '6 часов',
        '12h': '12 часов',
        '1d': '1 день',
        '3d': '3 дня',
        '7d': '7 дней',
        '30d': '30 дней',
        'forever': 'навсегда',
        'once': ''
    }

    duration_display = f" {duration_text.get(duration, duration)}" if duration != 'once' else ""

    approver_display = f"@{approver_username}" if approver_role >= Role.СЗА else approver_role.name

    notification = (
        f"{punishment_emoji[punishment_type]} @{violator_username} получил {punishment_name[punishment_type]}{duration_display}\n"
        f"📝 Правило: {rule}\n"
        f"👮 Модератор: @{moderator_username}\n"
        f"✅ Одобрил: {approver_display}"
    )

    try:
        if punishment_type == 'mute':
            until_date = calculate_until_date(duration)
            await context.bot.restrict_chat_member(
                chat_id=f'@{PUBLIC_CHAT_USERNAME}',
                user_id=violator_id,
                permissions=ChatPermissions(can_send_messages=False),
                until_date=until_date
            )
            logger.info(f"Muted user {violator_id} for {duration}")

        elif punishment_type == 'ban':
            until_date = calculate_until_date(duration)
            await context.bot.ban_chat_member(
                chat_id=f'@{PUBLIC_CHAT_USERNAME}',
                user_id=violator_id,
                until_date=until_date
            )
            logger.info(f"Banned user {violator_id} for {duration}")

        elif punishment_type == 'warn':
            warn_count = get_active_warnings_count(violator_id)
            if warn_count >= MAX_WARNINGS:
                auto_mute_until = calculate_until_date('12h')
                await context.bot.restrict_chat_member(
                    chat_id=f'@{PUBLIC_CHAT_USERNAME}',
                    user_id=violator_id,
                    permissions=ChatPermissions(can_send_messages=False),
                    until_date=auto_mute_until
                )
                notification += f"\n\n🚫 <b>АВТОМУТ 12 ЧАСОВ</b>\n(3 варна)"
                logger.info(f"Auto-muted user {violator_id} for 12h (3 warns)")

        msg = await context.bot.send_message(
            chat_id=f"@{PUBLIC_CHAT_USERNAME}",
            text=notification,
            parse_mode='HTML'
        )

        asyncio.create_task(
            delete_messages_after_delay(context, msg.chat_id, [msg.message_id], PUNISHMENT_DELETE_SECONDS)
        )

    except Exception as e:
        logger.error(f"Failed to execute punishment: {e}")

async def handle_main_chat_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Автосохранение пользователей (кроме отчетов с фото)"""
    try:
        message = update.message or update.edited_message
        if not message:
            return

        # Если это ФОТО В ТОПИКЕ = пропускаем (это отчет!)
        if message.photo and message.message_thread_id:
            return

        chat = message.chat
        user = message.from_user

        is_main = chat.id == GROUP_CHAT_ID or (chat.username and chat.username.lower() == PUBLIC_CHAT_USERNAME.lower())
        if not is_main or user.is_bot:
            return

        user_display_name = get_display_name(user)
        register_user(user.id, user.username, user_display_name)
        logger.info(f"💾 Сохранен: @{user.username or user.id}")
    except Exception as e:
        logger.error(f"❌ {e}", exc_info=True)

def main():
    if not DATABASE_URL:
        logger.error("❌ DATABASE_URL не задан!")
        return

    try:
        init_database()
        logger.info("✅ База данных инициализирована")
    except Exception as e:
        logger.error(f"❌ Ошибка инициализации БД: {e}")
        return

    logger.info("🚀 Bot started with PostgreSQL!")

    application = Application.builder().token(BOT_TOKEN).build()

    # Сначала СПЕЦИФИЧНЫЕ (фото-отчеты)
    application.add_handler(MessageHandler(filters.PHOTO & filters.ChatType.SUPERGROUP, handle_report))

    # Потом ОБЩИЕ (автосохранение)
    application.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, handle_main_chat_message))

    # Команды
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("vg", warning_command))
    application.add_handler(CommandHandler("svg", remove_warning_command))
    application.add_handler(CommandHandler("bl", blacklist_command))
    application.add_handler(CommandHandler("ubl", unblacklist_command))
    application.add_handler(CommandHandler("sp", reset_accepted_command))
    application.add_handler(CommandHandler("so", reset_rejected_command))

    # Кнопки
    application.add_handler(CallbackQueryHandler(handle_button_callback))

    logger.info("✅ Bot running with automatic punishments!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()

