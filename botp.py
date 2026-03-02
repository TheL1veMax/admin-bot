from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ChatPermissions
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
import logging
from enum import IntEnum
import os
import asyncio
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import psycopg2
from psycopg2.extras import RealDictCursor
from contextlib import contextmanager
import re

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv('BOT_TOKEN')

ADMIN_GROUP_ID = -1002418857530
PUBLIC_CHAT_ID = -1002901099291
PUBLIC_CHAT_USERNAME = 'pmkk_loves_chat'
ANNOUNCEMENTS_TOPIC_ID = 2 
DATABASE_URL = os.getenv('DATABASE_URL')
MSK = ZoneInfo('Europe/Moscow')
# ID канала для логов
LOG_CHANNEL_ID = -1003629150527

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
    ГЛАВНЫЙ_АДМИН = 10
    СЗА = 9
    ТС = 8
    ЗАМ_ГЛАВНОГО = 7
    КУРАТОР = 6
    СТАРШИЙ_АДМИН = 5
    СЗМ = 4
    АДМИН = 3
    МЛ_АДМИН = 2
    СТАРШИЙ_МОДЕРАТОР = 1
    МОДЕРАТОР = 0

USERS_ROLES = {
    'glavnyy_admin': Role.ГЛАВНЫЙ_АДМИН,
    'gerrinetwork': Role.СЗА,
    'mskmboky': Role.ТС,  
    'the_pr1estesss': Role.ЗАМ_ГЛАВНОГО,
    'qwertyuiopasdfghjklzxcvbnm123411': Role.КУРАТОР,
    'stadm': Role.СТАРШИЙ_АДМИН,
    'whysparky': Role.СЗМ,
    'maga8c': Role.АДМИН,
    'mladmin': Role.МЛ_АДМИН,
    'mladmin2': Role.МЛ_АДМИН,
    'stmoder': Role.СТАРШИЙ_МОДЕРАТОР,
    'stmpder': Role.СТАРШИЙ_МОДЕРАТОР,
    'stmoder2': Role.СТАРШИЙ_МОДЕРАТОР,
    'DBoss_baby': Role.МОДЕРАТОР,
    'Uniteboys': Role.МОДЕРАТОР,
    'marlowyq': Role.МОДЕРАТОР,
    'polinnnkka0': Role.МОДЕРАТОР,
    'milllllans': Role.МОДЕРАТОР,
    'grechka_aw': Role.МОДЕРАТОР,
    'daser979': Role.МОДЕРАТОР,
    'Aall_189': Role.МОДЕРАТОР,
    'matnozdra': Role.МОДЕРАТОР,
    'Riykaa_bro': Role.МОДЕРАТОР,
    'favoritgg6': Role.МОДЕРАТОР,
    'qwelex_z': Role.МОДЕРАТОР,
    'Noob_126': Role.МОДЕРАТОР
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
                CREATE TABLE IF NOT EXISTS appeal_counter_store (
                    id INTEGER PRIMARY KEY DEFAULT 1,
                    last_id INTEGER DEFAULT 0
                )
            """)
            cur.execute("""
                INSERT INTO appeal_counter_store (id, last_id)
                VALUES (1, 0)
                ON CONFLICT (id) DO NOTHING
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

    now = datetime.now(MSK)

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
                end_date = datetime.now(MSK) + timedelta(days=days)

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


# Словарь для пагинации
pagination_data = {}

async def delete_messages_after_delay(context: ContextTypes.DEFAULT_TYPE, chat_id: int, message_ids: list, delay: int):
    """Удаляет сообщения из чата после задержки"""
    await asyncio.sleep(delay)
    for msg_id in message_ids:
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=msg_id)
            logger.info(f"🗑️ Удалено сообщение {msg_id} из чата {chat_id}")
        except Exception as e:
            logger.error(f"❌ Не удалось удалить {msg_id}: {e}")



def get_user_role_name(username: str) -> str:
    """Получить название роли по username"""
    if not username:
        return "Модератор"

    username_lower = username.lower()
    role = USERS_ROLES.get(username_lower)

    if role is None:
        return "Модератор"

    role_names = {
        Role.ГЛАВНЫЙ_АДМИН: "Главный Админ",
        Role.СЗА: "СЗА",
        Role.ТС: "Технический Специалист",
        Role.ЗАМ_ГЛАВНОГО: "Зам. Главного",
        Role.СТАРШИЙ_АДМИН: "Старший Админ",
        Role.КУРАТОР: "Куратор",
        Role.СЗМ: "СЗМ",
        Role.АДМИН: "Админ",
        Role.МЛ_АДМИН: "Мл. Админ",
        Role.СТАРШИЙ_МОДЕРАТОР: "Ст. Модератор",
        Role.МОДЕРАТОР: "Модератор"
    }

    return role_names.get(role, "Модератор")

async def send_log(context: ContextTypes.DEFAULT_TYPE, log_text: str, parse_mode: str = 'HTML'):
    """Отправляет лог-сообщение в отдельный чат/канал"""
    try:
        await context.bot.send_message(
            chat_id=LOG_CHANNEL_ID,
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
    if checker_role >= Role.ТС:
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

def can_handle_appeal(user_role):
    """ТС и СЗА+ могут рассматривать обжалования"""
    return user_role is not None and user_role >= Role.ТС

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    user_display_name = get_display_name(user)
    register_user(user.id, user.username, user_display_name)
    user_role = get_user_role(user.username)
    role_name = user_role.name if user_role is not None else "Не назначена"

    # Формируем отображаемое название роли
    role_display = get_user_role_name(user.username) if user_role is not None else "Участник"

    # Проверяем есть ли активные наказания
    active_punishments = get_user_active_punishments(user.id)
    has_restrictions = len(active_punishments) > 0
    restrictions_text = "⛔️ Есть" if has_restrictions else "✅ Нет"

    extra_commands = ""
    if user_role is not None and can_handle_appeal(user_role):
        extra_commands = "\n/obn - список заявок на обжалование (ТС/СЗА+)"

    message_text = (
        "✅ Бот для проверки отчетов модерации запущен!\n\n"
        f"👤 Ваша роль: {role_display}\n\n"
        "📋 Отправляйте отчеты в соответствующую тему:\n"
        "• Модераторы и ст.модераторы → Отчетность модерации\n"
        "• Мл.админы, админы, СЗМ → Отчетность администрации\n"
        "• СЗА и Главный Админ → не сдают отчеты\n\n"
        "⚠️ Команды:\n"
        "/stats - ваша статистика отчетов\n"
        "/stats @username - статистика пользователя (СЗМ+)\n"
        "/leaderboard - топ-15 модераторов и админов\n"
        "/history @username - история наказаний (СЗМ+)\n"
        "/vg - выдать выговор (СЗМ+)\n"
        "/svg - снять выговор (СЗМ+)\n"
        "/bl - добавить в черный список (СЗМ+)\n"
        "/ubl - убрать из черного списка (СЗМ+)\n"
        "/sp - сбросить принятые отчеты (СЗМ+)\n"
        "/so - сбросить отклоненные отчеты (СЗМ+)\n"
        "/info - информация о пользователе (Мл. Админ+)\n"
        "/snwarn - снять один варн (Мл. Админ+)"
        f"{extra_commands}"
    )

    # Кнопки для всех пользователей
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📋 Обжалование наказания", callback_data="appeal_start"),
            InlineKeyboardButton("📜 История наказаний", callback_data="my_history")
        ]
    ])

    await update.message.reply_text(message_text)

    # Второе сообщение — статус + кнопки
    status_text = (
        f"👤 Ваша роль в чате: <b>{role_display}</b>\n"
        f"⚖️ Ограничения: <b>{restrictions_text}</b>"
    )
    await update.message.reply_text(status_text, parse_mode='HTML', reply_markup=keyboard)

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
    role_name = target_role.name if target_role is not None else "Не назначена"

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


async def delete_message_job(context, chat_id, message_id):
    """Удаление сообщения"""
    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
    except:
        pass

async def leaderboard_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Топ модераторов и админов"""
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT 
                        u.username,
                        u.full_name,
                        rs.accepted,
                        rs.rejected,
                        (rs.accepted + rs.rejected) as total
                    FROM report_stats rs
                    JOIN users u ON rs.user_id = u.user_id
                    WHERE rs.accepted > 0
                    ORDER BY rs.accepted DESC
                    LIMIT 15
                """)

                results = cur.fetchall()

        if not results:
            await update.message.reply_text("📊 Пока нет данных")
            return

        leaderboard_text = "🏆 <b>ТОП-15 МОДЕРАТОРОВ И АДМИНОВ</b>\n"
        leaderboard_text += "За всё время\n\n"

        medals = ["🥇", "🥈", "🥉"]

        for idx, (username, full_name, accepted, rejected, total) in enumerate(results, 1):
            medal = medals[idx-1] if idx <= 3 else f"{idx}."

            user_role_obj = get_user_role(username)
            role_name = user_role_obj.name if user_role_obj is not None else "Модератор"

            acceptance_rate = int((accepted / total * 100)) if total > 0 else 0

            leaderboard_text += f"{medal} @{username}\n"
            leaderboard_text += f"   🎖 {role_name}\n"
            leaderboard_text += f"   ✅ Принято: {accepted} | ❌ Отклонено: {rejected}\n"
            leaderboard_text += f"   📊 Процент: {acceptance_rate}%\n\n"

        leaderboard_text += f"⏰ {datetime.now(MSK).strftime('%d.%m.%Y %H:%M')}"

        sent_msg = await update.message.reply_text(leaderboard_text, parse_mode='HTML')

        try:
            await update.message.delete()
        except:
            pass

        context.job_queue.run_once(
            lambda c: delete_message_job(c, update.message.chat_id, sent_msg.message_id),
            180
        )

    except Exception as e:
        logger.error(f"Leaderboard error: {e}")
        await update.message.reply_text("❌ Ошибка получения топа")

async def history_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """История наказаний пользователя с пагинацией"""
    user = update.message.from_user
    user_role = get_user_role(user.username)

    if user_role is None or user_role < Role.СЗМ:
        await update.message.reply_text("❌ Нет доступа! (только СЗМ+)")
        return

    if not context.args:
        await update.message.reply_text(
            "📝 Использование:\n"
            "/history @username - история наказаний\n"
            "/history ID - история по ID"
        )
        return

    target = context.args[0].lstrip('@')

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                if target.isdigit():
                    target_id = int(target)
                    cur.execute("SELECT username, full_name FROM users WHERE user_id = %s", (target_id,))
                else:
                    cur.execute("SELECT user_id, full_name FROM users WHERE LOWER(username) = LOWER(%s)", (target,))

                user_info = cur.fetchone()

                if not user_info:
                    await update.message.reply_text("❌ Пользователь не найден")
                    return

                if target.isdigit():
                    target_username = user_info[0]
                    target_name = user_info[1]
                else:
                    target_id = user_info[0]
                    target_name = user_info[1]
                    target_username = target

                cur.execute("""
                    SELECT 
                        punishment_type,
                        duration,
                        rule,
                        issued_by_username,
                        approved_by_username,
                        created_at
                    FROM punishments
                    WHERE user_id = %s
                    ORDER BY created_at DESC
                """, (target_id,))

                punishments = cur.fetchall()

        if not punishments:
            msg = await update.message.reply_text(
                f"📜 <b>ИСТОРИЯ НАКАЗАНИЙ</b>\n\n"
                f"👤 @{target_username}\n\n"
                f"✅ Нет наказаний",
                parse_mode='HTML'
            )
            try:
                await update.message.delete()
            except:
                pass
            context.job_queue.run_once(
                lambda c: delete_message_job(c, update.message.chat_id, msg.message_id),
                300
            )
            return

        pagination_key = f"{user.id}_{target_username}"
        pagination_data[pagination_key] = {
            'punishments': punishments,
            'target_username': target_username,
            'target_id': target_id,
            'page': 0
        }

        await send_history_page(update.message.chat_id, pagination_key, context, is_reply=True, message=update.message)

        try:
            await update.message.delete()
        except:
            pass

    except Exception as e:
        logger.error(f"History error: {e}")
        await update.message.reply_text("❌ Ошибка получения истории")

async def send_history_page(chat_id, pagination_key, context, page=None, is_reply=False, message=None, callback_query=None):
    """Отправка страницы истории наказаний"""
    data = pagination_data.get(pagination_key)
    if not data:
        if callback_query:
            await callback_query.answer("❌ Данные устарели, используйте /history заново")
        return

    if page is not None:
        data['page'] = page

    current_page = data['page']
    punishments = data['punishments']
    target_username = data['target_username']
    target_id = data['target_id']

    per_page = 5
    total_pages = (len(punishments) + per_page - 1) // per_page
    start_idx = current_page * per_page
    end_idx = start_idx + per_page
    page_punishments = punishments[start_idx:end_idx]

    mutes = sum(1 for p in punishments if p[0] == 'mute')
    warns = sum(1 for p in punishments if p[0] == 'warn')
    bans = sum(1 for p in punishments if p[0] == 'ban')

    history_text = f"📜 <b>ИСТОРИЯ НАКАЗАНИЙ</b>\n\n"
    history_text += f"👤 @{target_username} (ID: {target_id})\n"
    history_text += f"📊 Всего: {len(punishments)} | 🔇 Мутов: {mutes} | ⚠️ Варнов: {warns} | 🔒 Банов: {bans}\n"
    history_text += f"📄 Страница {current_page + 1}/{total_pages}\n\n"

    emoji_map = {'mute': '🔇', 'warn': '⚠️', 'ban': '🔒'}
    name_map = {'mute': 'МУТ', 'warn': 'ВАРН', 'ban': 'БАН'}
    dur_text = {
        '1h': '1 час', '2h': '2 часа', '6h': '6 часов', '12h': '12 часов',
        '1d': '1 день', '3d': '3 дня', '7d': '7 дней', '30d': '30 дней',
        'forever': 'навсегда', 'once': ''
    }

    for idx, (pun_type, duration, rule, mod_user, appr_user, created) in enumerate(page_punishments, start_idx + 1):
        duration_display = dur_text.get(duration, duration)
        if duration != 'once' and duration_display:
            duration_display = f" {duration_display}"
        else:
            duration_display = ""

        history_text += f"{idx}. {emoji_map[pun_type]} <b>{name_map[pun_type]}{duration_display}</b>\n"
        history_text += f"   📋 {rule}\n"
        history_text += f"   👮 @{mod_user} | ✅ @{appr_user}\n"
        history_text += f"   📅 {created.strftime('%d.%m.%Y %H:%M')}\n\n"

    history_text += f"⏰ {datetime.now(MSK).strftime('%d.%m.%Y %H:%M')}"

    buttons = []
    if current_page > 0:
        buttons.append(InlineKeyboardButton("⬅️ Назад", callback_data=f"history_prev_{pagination_key}"))
    if current_page < total_pages - 1:
        buttons.append(InlineKeyboardButton("Вперёд ➡️", callback_data=f"history_next_{pagination_key}"))

    keyboard = InlineKeyboardMarkup([buttons]) if buttons else None

    if is_reply and message:
        sent_msg = await message.reply_text(history_text, parse_mode='HTML', reply_markup=keyboard)
        data['response_message_id'] = sent_msg.message_id
        context.job_queue.run_once(
            lambda c: delete_message_job(c, chat_id, sent_msg.message_id),
            300
        )
    elif callback_query:
        await callback_query.edit_message_text(history_text, parse_mode='HTML', reply_markup=keyboard)
        await callback_query.answer()

async def history_pagination_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка кнопок пагинации истории"""
    query = update.callback_query
    data = query.data

    if data.startswith('history_prev_'):
        pagination_key = data.replace('history_prev_', '')
        if pagination_key in pagination_data:
            new_page = max(0, pagination_data[pagination_key]['page'] - 1)
            await send_history_page(query.message.chat_id, pagination_key, context, page=new_page, callback_query=query)

    elif data.startswith('history_next_'):
        pagination_key = data.replace('history_next_', '')
        if pagination_key in pagination_data:
            punishments = pagination_data[pagination_key]['punishments']
            per_page = 5
            total_pages = (len(punishments) + per_page - 1) // per_page
            new_page = min(total_pages - 1, pagination_data[pagination_key]['page'] + 1)
            await send_history_page(query.message.chat_id, pagination_key, context, page=new_page, callback_query=query)


async def announcement_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /obv - отправка объявлений в топик"""
    if update.message.chat.type != 'private':
        await update.message.reply_text("❌ Команда работает только в ЛС с ботом")
        return

    username = update.message.from_user.username
    if not username:
        await update.message.reply_text("❌ У вас нет username")
        return

    user_role = get_user_role(username)
    allowed = [Role.СЗМ, Role.КУРАТОР, Role.ЗАМ_ГЛАВНОГО, Role.СЗА]

    if not user_role or user_role not in allowed:
        await update.message.reply_text("❌ Нет прав\nДоступ: СЗМ, Куратор, Зам Гл.Админа, СЗА")
        return

    if not update.message.text.startswith('/obv '):
        await update.message.reply_text("Использование: /obv текст\n\nПример:\n/obv Уважаемые коллеги...")
        return

    text = update.message.text[5:].strip()
    if not text:
        await update.message.reply_text("❌ Введите текст после /obv")
        return

    role_name = get_user_role_name(username)
    msg = f"📢 <b>ОБЪЯВЛЕНИЕ</b>\n\n{text}\n\n👤 Отправил: {role_name}"

    try:
        await context.bot.send_message(ADMIN_GROUP_ID, msg, message_thread_id=ANNOUNCEMENTS_TOPIC_ID, parse_mode='HTML')
        await update.message.reply_text("✅ Объявление отправлено!")
    except Exception as e:
        logger.error(f"Ошибка /obv: {e}")
        await update.message.reply_text(f"❌ Ошибка: {e}")


async def warning_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if message.chat.id != ADMIN_GROUP_ID:
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
        chat_id=ADMIN_GROUP_ID,
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
        f"⏰ {datetime.now(MSK).strftime('%d.%m.%Y %H:%M')}"
    )
    await send_log(context, log_text)

    success_msg = await message.reply_text(f"✅ Выговор #{warning_count} выдан {user_link}", parse_mode='HTML')
    asyncio.create_task(delete_messages_after_delay(context, message.chat.id, [message.message_id, success_msg.message_id], PUNISHMENT_DELETE_SECONDS))

async def remove_warning_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if message.chat.id != ADMIN_GROUP_ID:
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
        chat_id=ADMIN_GROUP_ID,
        message_thread_id=WARNINGS_TOPIC_ID,
        text=remove_message,
        parse_mode='HTML'
    )

    success_msg = await message.reply_text(f"✅ Снят! Осталось: {new_count}", parse_mode='HTML')
    asyncio.create_task(delete_messages_after_delay(context, message.chat.id, [message.message_id, success_msg.message_id], PUNISHMENT_DELETE_SECONDS))

async def blacklist_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if message.chat.id != ADMIN_GROUP_ID:
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

        days_str = parts[2].lower().rstrip('d').rstrip('д')
        try:
            days = int(days_str)
            if days <= 0:
                raise ValueError
        except ValueError:
            error_msg = await message.reply_text("❌ Укажите срок числом дней, например: 30d")
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

        days_str = parts[1].lower().rstrip('d').rstrip('д')
        try:
            days = int(days_str)
            if days <= 0:
                raise ValueError
        except ValueError:
            error_msg = await message.reply_text("❌ Укажите срок числом дней, например: 30d")
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

    # Кикаем из группы администрации
    try:
        await context.bot.ban_chat_member(chat_id=ADMIN_GROUP_ID, user_id=target_user_id)
        await context.bot.unban_chat_member(chat_id=ADMIN_GROUP_ID, user_id=target_user_id)
    except Exception as e:
        logger.error(f"Ошибка при кике из группы: {e}")

    bl_message = (
        f"🚫 <b>ЧЕРНЫЙ СПИСОК</b>\n\n"
        f"👤 {user_link}\n"
        f"📝 Причина: {reason}\n"
        f"⏱ Срок: {days} дн. (до {end_date.strftime('%d.%m.%Y')})\n"
        f"👨‍💼 Добавил: {issuer.mention_html()}\n"
        f"⚠️ Пользователь исключён из группы."
    )

    await context.bot.send_message(
        chat_id=ADMIN_GROUP_ID,
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
        f"⏰ {datetime.now(MSK).strftime('%d.%m.%Y %H:%M')}"
    )
    await send_log(context, log_text)

    success_msg = await message.reply_text(f"✅ {user_link} в ЧС", parse_mode='HTML')
    asyncio.create_task(delete_messages_after_delay(context, message.chat.id, [message.message_id, success_msg.message_id], PUNISHMENT_DELETE_SECONDS))

async def unblacklist_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if message.chat.id != ADMIN_GROUP_ID:
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
        chat_id=ADMIN_GROUP_ID,
        message_thread_id=BLACKLIST_TOPIC_ID,
        text=ubl_message,
        parse_mode='HTML'
    )

    success_msg = await message.reply_text(f"✅ {user_link} удален из ЧС!", parse_mode='HTML')
    asyncio.create_task(delete_messages_after_delay(context, message.chat.id, [message.message_id, success_msg.message_id], PUNISHMENT_DELETE_SECONDS))

async def reset_accepted_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if message.chat.id != ADMIN_GROUP_ID:
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
    if message.chat.id != ADMIN_GROUP_ID:
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
    if message.chat.id != ADMIN_GROUP_ID or not message.photo:
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
            chat_id=ADMIN_GROUP_ID,
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
    """Обработка нажатий на кнопки"""
    query = update.callback_query
    await query.answer()

    data = query.data

    # Проверка на обжалование
    if data.startswith('appeal'):
        await handle_appeal_callback(update, context)
        return

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
            await query.answer("⚠️ Данные устарели!", show_alert=True)
            return

        punishment_data = pending_punishments[punishment_key]

        keyboard = [
            [InlineKeyboardButton("🔇 Мут", callback_data=f"punish_mute_{report_id}")],
            [InlineKeyboardButton("⚠️ Варн", callback_data=f"punish_warn_{report_id}")],
            [InlineKeyboardButton("🚫 Бан", callback_data=f"punish_ban_{report_id}")],
            [InlineKeyboardButton("✋ Выдать вручную", callback_data=f"punish_manual_{report_id}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        punishment_text = f"⚖️ Выберите наказание\n\n"
        punishment_text += f"👤 Нарушитель: {punishment_data['violator_username']}\n"
        punishment_text += f"📋 Правило: {punishment_data['rule']}\n"
        punishment_text += f"💡 Рекомендация: {punishment_data.get('recommendation') or 'Не указана'}"

        await query.edit_message_text(punishment_text, parse_mode='HTML', reply_markup=reply_markup)

    elif data.startswith('cancel_punishment_'):
        punishment_key = f"punishment_{data.split('_')[-1]}"
        if punishment_key in pending_punishments:
            del pending_punishments[punishment_key]
        await query.edit_message_text("❌ Наказание отменено")



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

    # Для СЗА и выше показываем имя и юзернейм, для остальных - только имя и юзернейм
    if checker_role is not None and checker_role >= Role.СЗА:
        checker_display = f"{checker_display_name} (@{checker.username})"
    else:
        checker_display = f"{checker_display_name} (@{checker.username})"

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
        chat_id=ADMIN_GROUP_ID,
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
        f"⏰ {datetime.now(MSK).strftime('%d.%m.%Y %H:%M')}"
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
                await context.bot.send_message(chat_id=LOG_CHANNEL_ID, text=f"⚠️ @{violator_username} НЕ НАЙДЕН В БАЗЕ", parse_mode='HTML')
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
                    'recommendation': parsed['recommendation'] or '',
                    'report_message_id': report.get('message_id'),
                    'report_topic_id': report.get('topic_id')
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
        delete_messages_after_delay(context, ADMIN_GROUP_ID, 
                                   [report['user_message_id'], report['bot_message_id']], 
                                   DELETE_AFTER_SECONDS)
    )

    del reports_data[report_key]


    # Удаление из категории ОТЧЕТНОСТЬ
    if query.message.message_thread_id in [MODERATOR_REPORT_TOPIC_ID, ADMIN_REPORT_TOPIC_ID]:
        asyncio.create_task(
            delete_messages_after_delay(
                context,
                query.message.chat.id,
                [query.message.message_id],
                120
            )
        )
        logger.info(f"⏰ Отклонённый отчёт будет удалён через 2 мин")

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
        await query.edit_message_text(manual_text, parse_mode='HTML')

        # Логируем
        log_text = (
            f"✋ <b>ВЫДАНО ВРУЧНУЮ</b>\n\n"
            f"👤 Нарушитель: @{punishment_data['violator_username']} (ID: {punishment_data['violator_id']})\n"
            f"📋 Правило: {punishment_data['rule']}\n"
            f"💡 Рекомендация: {punishment_data.get('recommendation') or 'Не указана'}\n"
            f"👨‍💼 Модератор: @{punishment_data['moderator_username']}\n"
            f"✅ Решение принял: @{query.from_user.username}\n"
            f"⏰ {datetime.now(MSK).strftime('%d.%m.%Y %H:%M')}"
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
            days_ago = (datetime.now(MSK) - duplicate['created_at']).days
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
        await query.edit_message_text(f"✅ Варн выдан @{punishment_data['violator_username']}")
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
        days_ago = (datetime.now(MSK) - duplicate['created_at']).days
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


async def send_punishment_dm(context: ContextTypes.DEFAULT_TYPE, violator_id: int, violator_username: str,
                            punishment_type: str, duration: str, rule: str, photo_file_id: str, 
                            is_manual: bool = False):
    """Отправка ЛС пользователю о наказании с возможностью обжалования"""

    # Эмодзи для типов наказаний
    punishment_emoji = {
        'mute': '🔇',
        'warn': '⚠️',
        'ban': '🚫'
    }

    emoji = punishment_emoji.get(punishment_type, '⚠️')

    # Название наказания
    punishment_names = {
        'mute': 'Мут',
        'warn': 'Варн',
        'ban': 'Бан'
    }

    punishment_name = punishment_names.get(punishment_type, punishment_type.upper())

    # Длительность человекочитаемая
    duration_readable = {
        '1h': '1 час',
        '2h': '2 часа',
        '6h': '6 часов',
        '12h': '12 часов',
        '1d': '1 день',
        '3d': '3 дня',
        '7d': '7 дней',
        '30d': '30 дней',
        'forever': 'Навсегда',
        'once': '1 предупреждение'
    }

    duration_text = duration_readable.get(duration, duration)

    # Формируем сообщение
    if is_manual:
        message = f"{emoji} <b>Вы получили {punishment_name}</b>\n\n"
        message += f"📋 <b>Правило:</b> {rule}\n"
        if duration != 'once':
            message += f"⏱ <b>Длительность:</b> {duration_text}\n\n"
        else:
            message += "\n"
        message += f"ℹ️ Наказание было выдано вручную в соответствии с правилами\n\n"
        message += f"📞 <b>Обжаловать наказание:</b> @gerrinetwork"
    else:
        message = f"{emoji} <b>Вы получили {punishment_name}</b>\n\n"
        message += f"📋 <b>Правило:</b> {rule}\n"
        if duration != 'once':
            message += f"⏱ <b>Длительность:</b> {duration_text}\n\n"
        else:
            message += "\n"
        message += f"📞 <b>Обжаловать наказание:</b> @gerrinetwork"

    # Кнопка обжалования
    keyboard = [
        [InlineKeyboardButton("📝 Обжаловать наказание", 
                             callback_data=f"appeal_{violator_id}_{punishment_type}_{duration}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    try:
        # Отправляем фото с сообщением в ЛС
        await context.bot.send_photo(
            chat_id=violator_id,
            photo=photo_file_id,
            caption=message,
            parse_mode='HTML',
            reply_markup=reply_markup
        )
        logger.info(f"✅ Отправлено ЛС пользователю {violator_id} о наказании")
        return True
    except Exception as e:
        logger.error(f"❌ Не удалось отправить ЛС пользователю {violator_id}: {e}")
        return False

async def execute_punishment(context: ContextTypes.DEFAULT_TYPE, punishment_data: dict,
                            punishment_type: str, duration: str):
    """Выполнение наказания"""
    violator_id = punishment_data['violator_id']
    violator_username = punishment_data['violator_username']
    violator_name = punishment_data['violator_name']
    moderator_username = punishment_data['moderator_username']
    approver_username = punishment_data['approver_username']
    rule = punishment_data['rule']
    report_message_id = punishment_data.get('report_message_id')
    report_topic_id = punishment_data.get('report_topic_id')

    add_punishment(violator_id, violator_username, violator_name, punishment_type, duration, rule,
                   punishment_data['moderator_id'], moderator_username,
                   punishment_data['approver_id'], approver_username)

    emoji = {'mute': '🔇', 'warn': '⚠️', 'ban': '🔒'}
    name = {'mute': 'мут', 'warn': 'варн', 'ban': 'бан'}
    dur_text = {'1h': '1 час', '2h': '2 часа', '6h': '6 часов', '12h': '12 часов',
                '1d': '1 день', '3d': '3 дня', '7d': '7 дней', '30d': '30 дней',
                'forever': 'навсегда', 'once': ''}

    duration_display = f" на {dur_text.get(duration, duration)}" if duration != 'once' else ""

    moderator_role_obj = get_user_role(moderator_username)
    moderator_display = moderator_role_obj.name if moderator_role_obj is not None else "Модератор"

    approver_role_obj = get_user_role(approver_username)
    if approver_role_obj is not None and approver_role_obj == Role.СЗА:
        approver_display = f"@{approver_username}"
    else:
        approver_display = approver_role_obj.name if approver_role_obj is not None else "Админ"

    notification = (
        f"{emoji[punishment_type]} @{violator_username} получил {name[punishment_type]}{duration_display}\n"
        f"📝 Правило: {rule}\n"
        f"🎖 Ранг: {moderator_display}\n"
        f"✅ Одобрил: {approver_display}"
    )

    try:
        if punishment_type == 'mute':
            until_date = calculate_until_date(duration)
            await context.bot.restrict_chat_member(
                chat_id=PUBLIC_CHAT_ID, user_id=violator_id,
                permissions=ChatPermissions(can_send_messages=False), until_date=until_date)
        elif punishment_type == 'ban':
            until_date = calculate_until_date(duration)
            await context.bot.ban_chat_member(chat_id=PUBLIC_CHAT_ID, user_id=violator_id, until_date=until_date)
        elif punishment_type == 'warn':
            add_warning(violator_id, violator_name, violator_username, rule, moderator_username)

        try:
            pub_msg = await context.bot.send_message(chat_id=PUBLIC_CHAT_ID, text=notification, parse_mode='HTML')
            asyncio.create_task(delete_messages_after_delay(
                context, PUBLIC_CHAT_ID, [pub_msg.message_id], 120))
        except Exception as e:
            logger.error(f"Notification error: {e}")

        end_date = "—"
        if punishment_type in ['mute', 'ban'] and duration != 'forever':
            until_date_calc = calculate_until_date(duration)
            if until_date_calc:
                end_date = datetime.fromtimestamp(until_date_calc, tz=MSK).strftime('%d.%m.%Y %H:%M')

        log_text = (
            f"{emoji[punishment_type]} <b>ВЫДАН {name[punishment_type].upper()}</b>\n\n"
            f"👤 @{violator_username} (ID: {violator_id})\n"
            f"📋 Правило: {rule}\n"
            f"⏱ Длительность: {dur_text.get(duration, duration)}\n"
        )
        if duration != 'forever' and punishment_type in ['mute', 'ban']:
            log_text += f"🔚 До: {end_date}\n"

        log_text += f"\n🎖 Ранг: {moderator_display} (@{moderator_username})\n"

        if approver_role_obj is not None and approver_role_obj == Role.СЗА:
            log_text += f"✅ Одобрил: {approver_role_obj.name} (@{approver_username})\n"
        else:
            log_text += f"✅ Одобрил: {approver_display}\n"

        log_text += f"⏰ {datetime.now(MSK).strftime('%d.%m.%Y %H:%M')}"
        await send_log(context, log_text)

        if report_message_id and report_topic_id:
            try:
                await context.bot.delete_message(chat_id=MAIN_CHAT_ID, message_id=report_message_id)
                logger.info(f"✅ Deleted report {report_message_id}")
            except Exception as e:
                logger.error(f"❌ Delete error: {e}")

    except Exception as e:
        logger.error(f"Punishment error: {e}")
        raise


async def handle_appeal_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка обжалования наказания"""
    query = update.callback_query
    await query.answer()

    data = query.data  # appeal_<user_id>_<type>_<duration>
    parts = data.split('_')

    if len(parts) < 4:
        await query.answer("❌ Ошибка данных", show_alert=True)
        return

    violator_id = int(parts[1])
    punishment_type = parts[2]
    duration = parts[3]

    user = query.from_user
    user_display = get_display_name(user)

    # Эмодзи для типов
    punishment_emoji = {
        'mute': '🔇 Мут',
        'warn': '⚠️ Варн',
        'ban': '🚫 Бан'
    }

    punishment_name = punishment_emoji.get(punishment_type, punishment_type.upper())

    # Формируем сообщение об обжаловании
    appeal_message = f"📝 <b>ОБЖАЛОВАНИЕ НАКАЗАНИЯ</b>\n\n"
    appeal_message += f"👤 <b>Пользователь:</b> {user.mention_html()} (@{user.username or 'нет username'})\n"
    appeal_message += f"🆔 <b>ID:</b> <code>{violator_id}</code>\n"
    appeal_message += f"⚠️ <b>Тип наказания:</b> {punishment_name}\n"
    appeal_message += f"⏱ <b>Длительность:</b> {duration}\n\n"
    appeal_message += f"💬 <i>Пользователь хочет обжаловать наказание.\nДля рассмотрения обращения свяжитесь с ним.</i>"

    try:
        # Отправляем СЗА (@gerrinetwork)
        gerri_id, gerri_name = find_user_id_by_username('gerrinetwork')

        if gerri_id:
            await context.bot.send_message(
                chat_id=gerri_id,
                text=appeal_message,
                parse_mode='HTML'
            )

            # Отправляем также в лог канал
            await send_log(context, appeal_message)

            # Убираем кнопку и добавляем статус
            await query.edit_message_caption(
                caption=query.message.caption + "\n\n✅ <b>Обжалование отправлено СЗА (@gerrinetwork)</b>",
                parse_mode='HTML'
            )
        else:
            await query.answer("❌ СЗА не найден в системе", show_alert=True)

    except Exception as e:
        logger.error(f"Ошибка отправки обжалования: {e}")
        await query.answer("❌ Ошибка отправки обжалования", show_alert=True)


async def handle_main_chat_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Автосохранение пользователей"""
    try:
        message = update.message or update.edited_message
        if not message:
            return
        if message.photo and message.message_thread_id:
            return
        chat = message.chat
        user = message.from_user
        is_main = chat.id == ADMIN_GROUP_ID or (chat.username and chat.username.lower() == PUBLIC_CHAT_USERNAME.lower())
        if not is_main or user.is_bot:
            return
        user_display_name = get_display_name(user)
        register_user(user.id, user.username, user_display_name)
        logger.info(f"💾 Сохранен: @{user.username or user.id}")
    except Exception as e:
        logger.error(f"❌ {e}", exc_info=True)



def get_next_appeal_id() -> int:
    """Получить следующий ID обжалования из БД (сохраняется между перезапусками)"""
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE appeal_counter_store
                    SET last_id = last_id + 1
                    WHERE id = 1
                    RETURNING last_id
                """)
                return cur.fetchone()[0]
    except Exception as e:
        logger.error(f"get_next_appeal_id error: {e}")
        appeal_counter[0] += 1
        return appeal_counter[0]

# ==================== ОБЖАЛОВАНИЯ ====================
reject_states = {}

# Хранилище активных заявок на обжалование
# appeal_id -> {user_id, username, full_name, punishment_id, punishment_type, duration, rule,
#               issued_by_username, reason, text, photo_file_id, status, created_at, handler_id}
active_appeals = {}
appeal_counter = [0]

# Временные данные при создании обжалования
appeal_states = {}
# user_id -> {step, punishment_id, reason, text, photo_file_id}


def get_user_active_punishments(user_id: int):
    """Получить активные наказания пользователя (последние 30 дней)"""
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT id, punishment_type, duration, rule, issued_by_username,
                           approved_by_username, created_at
                    FROM punishments
                    WHERE user_id = %s
                    AND created_at > NOW() - INTERVAL '30 days'
                    ORDER BY created_at DESC
                """, (user_id,))
                return cur.fetchall()
    except Exception as e:
        logger.error(f"Get active punishments error: {e}")
        return []


def get_all_user_punishments(user_id: int):
    """Все наказания пользователя"""
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT id, punishment_type, duration, rule, issued_by_username,
                           approved_by_username, created_at
                    FROM punishments
                    WHERE user_id = %s
                    ORDER BY created_at DESC
                    LIMIT 20
                """, (user_id,))
                return cur.fetchall()
    except Exception as e:
        logger.error(f"Get all punishments error: {e}")
        return []


def get_punishment_by_id(punishment_id: int):
    """Получить наказание по ID"""
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT id, user_id, username, full_name, punishment_type, duration, rule,
                           issued_by_username, approved_by_username, created_at
                    FROM punishments WHERE id = %s
                """, (punishment_id,))
                return cur.fetchone()
    except Exception as e:
        logger.error(f"Get punishment by id error: {e}")
        return None


APPEAL_REASONS = [
    ("Ошибочное наказание", "appeal_reason_0"),
    ("Наказание не соответствует правилам", "appeal_reason_1"),
    ("Нарушение процедуры выдачи наказания", "appeal_reason_2"),
    ("Предвзятость со стороны администратора", "appeal_reason_3"),
    ("Отсутствие доказательной базы", "appeal_reason_4"),
]

PUN_TYPE_NAME = {'mute': '🔇 Мут', 'ban': '🔒 Бан', 'warn': '⚠️ Варн'}

def fmt_dt(dt) -> str:
    """Форматировать datetime в МСК с датой и временем"""
    if dt is None:
        return '—'
    if dt.tzinfo is None:
        from zoneinfo import ZoneInfo as _ZI
        dt = dt.replace(tzinfo=_ZI('Europe/Moscow'))
    return dt.strftime('%d.%m.%Y %H:%M')

def format_punishment(ptype: str, duration: str) -> str:
    """Красивый формат наказания"""
    type_name = PUN_TYPE_NAME.get(ptype, ptype)
    if ptype == 'warn':
        return type_name  # варн без длительности
    dur_name = DUR_TEXT.get(duration, duration)
    return f"{type_name} — {dur_name}" 
DUR_TEXT = {
    '1h': '1 час', '2h': '2 часа', '6h': '6 часов', '12h': '12 часов',
    '1d': '1 день', '3d': '3 дня', '7d': '7 дней', '30d': '30 дней',
    'forever': 'навсегда', 'once': 'разово'
}

SZA_USERNAME = 'gerrinetwork'


# ---- Обработчик кнопки "История наказаний" из /start ----
async def my_history_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user

    punishments = get_all_user_punishments(user.id)
    if not punishments:
        await query.message.reply_text("✅ У вас нет наказаний в истории.")
        return

    text = "📜 <b>Ваша история наказаний:</b>\n\nВыберите наказание для просмотра:"
    buttons = []
    for p in punishments:
        ptype = PUN_TYPE_NAME.get(p['punishment_type'], p['punishment_type'])
        date_str = fmt_dt(p['created_at'])
        label = f"{format_punishment(p['punishment_type'], p['duration'])} — {date_str}"
        buttons.append([InlineKeyboardButton(label, callback_data=f"view_pun_{p['id']}")])

    buttons.append([InlineKeyboardButton("🔙 Назад", callback_data="back_to_start")])
    await query.message.reply_text(text, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(buttons))


# ---- Просмотр конкретного наказания ----
async def view_punishment_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user

    pun_id = int(query.data.replace("view_pun_", ""))
    p = get_punishment_by_id(pun_id)

    if not p or p['user_id'] != user.id:
        await query.answer("❌ Наказание не найдено", show_alert=True)
        return

    pun_fmt = format_punishment(p['punishment_type'], p['duration'])
    date_str = fmt_dt(p['created_at'])

    # Показываем юзернейм только СЗА
    viewer_role = get_user_role(user.username)
    if viewer_role is not None and viewer_role >= Role.СЗА:
        issuer_text = f"@{p['issued_by_username']}"
    else:
        issuer_role_name = get_user_role_name(p['issued_by_username'])
        issuer_text = issuer_role_name

    text = (
        f"📋 <b>Наказание #{p['id']}</b>\n\n"
        f"🔹 Наказание: {pun_fmt}\n"
        f"📝 Правило: {p['rule']}\n"
        f"👮 Выдал: {issuer_text}\n"
        f"📅 Дата: {date_str}"
    )

    buttons = [
        [InlineKeyboardButton("⚖️ Обжаловать наказание", callback_data=f"appeal_pun_{pun_id}")],
        [InlineKeyboardButton("🔙 Назад", callback_data="my_history")]
    ]
    await query.message.reply_text(text, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(buttons))


# ---- Начало обжалования конкретного наказания ----
async def appeal_start_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user

    if query.data == "appeal_start":
        # Из главного меню — показать список активных наказаний
        punishments = get_user_active_punishments(user.id)
        if not punishments:
            await query.message.reply_text("✅ У вас нет активных наказаний для обжалования.")
            return
        text = "⚖️ <b>Выберите наказание для обжалования:</b>"
        buttons = []
        for p in punishments[:1]:  # только последнее наказание
            date_str = fmt_dt(p['created_at'])
            label = f"{format_punishment(p['punishment_type'], p['duration'])} — {date_str}"
            buttons.append([InlineKeyboardButton(label, callback_data=f"appeal_pun_{p['id']}")])
        buttons.append([InlineKeyboardButton("🔙 Назад", callback_data="back_to_start")])
        await query.message.reply_text(text, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(buttons))
        return

    # appeal_pun_{id}
    pun_id = int(query.data.replace("appeal_pun_", ""))
    p = get_punishment_by_id(pun_id)
    if not p or p['user_id'] != user.id:
        await query.answer("❌ Наказание не найдено", show_alert=True)
        return

    # Начинаем процесс обжалования
    appeal_states[user.id] = {'step': 'reason', 'punishment_id': pun_id}

    text = "⚖️ <b>Обжалование наказания</b>\n\nВыберите причину обжалования:"
    buttons = [[InlineKeyboardButton(reason, callback_data=cb)] for reason, cb in APPEAL_REASONS]
    buttons.append([InlineKeyboardButton("❌ Отмена", callback_data="appeal_cancel")])
    await query.message.reply_text(text, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(buttons))


# ---- Выбор причины обжалования ----
async def appeal_reason_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user

    if user.id not in appeal_states:
        await query.answer("❌ Сессия устарела", show_alert=True)
        return

    reason_idx = int(query.data.replace("appeal_reason_", ""))
    reason_text = APPEAL_REASONS[reason_idx][0]
    appeal_states[user.id]['reason'] = reason_text
    appeal_states[user.id]['step'] = 'text'

    skip_kb = InlineKeyboardMarkup([[InlineKeyboardButton("⏭ Пропустить", callback_data="appeal_skip_text")]])
    await query.message.reply_text(
        f"✅ Причина: <b>{reason_text}</b>\n\n"
        "✍️ Напишите подробное описание вашей ситуации\n"
        "или нажмите кнопку ниже чтобы пропустить:",
        parse_mode='HTML',
        reply_markup=skip_kb
    )


# ---- Получение текста обжалования ----
async def handle_appeal_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user

    if user.id not in appeal_states or appeal_states[user.id].get('step') != 'text':
        return False  # не наше сообщение

    if update.message.text == '/skip':
        appeal_states[user.id]['text'] = None
    else:
        appeal_states[user.id]['text'] = update.message.text

    appeal_states[user.id]['step'] = 'photo'

    skip_kb = InlineKeyboardMarkup([[InlineKeyboardButton("⏭ Пропустить", callback_data="appeal_skip_photo")]])
    await update.message.reply_text(
        "📎 Прикрепите скриншот/фото как доказательство\n"
        "или нажмите кнопку ниже чтобы пропустить:",
        reply_markup=skip_kb
    )
    return True


# ---- Получение фото обжалования ----
async def handle_appeal_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user

    if user.id not in appeal_states or appeal_states[user.id].get('step') != 'photo':
        return False

    if update.message.photo:
        appeal_states[user.id]['photo_file_id'] = update.message.photo[-1].file_id
    else:
        appeal_states[user.id]['photo_file_id'] = None

    await submit_appeal(update, context, user)
    return True


async def handle_appeal_skip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    if user.id not in appeal_states:
        return False

    step = appeal_states[user.id].get('step')
    if step == 'text':
        appeal_states[user.id]['text'] = None
        appeal_states[user.id]['step'] = 'photo'
        skip_kb = InlineKeyboardMarkup([[InlineKeyboardButton("⏭ Пропустить", callback_data="appeal_skip_photo")]])
        await update.message.reply_text(
            "📎 Прикрепите скриншот/фото как доказательство\n"
            "или нажмите кнопку ниже чтобы пропустить:",
            reply_markup=skip_kb
        )
        return True
    elif step == 'photo':
        appeal_states[user.id]['photo_file_id'] = None
        await submit_appeal(update, context, user)
        return True
    return False


async def submit_appeal(update, context, user):
    """Финальная отправка заявки"""
    state = appeal_states.pop(user.id, {})
    pun_id = state.get('punishment_id')
    p = get_punishment_by_id(pun_id)

    if not p:
        await update.message.reply_text("❌ Ошибка: наказание не найдено.")
        return

    appeal_id = get_next_appeal_id()

    active_appeals[appeal_id] = {
        'appeal_id': appeal_id,
        'user_id': user.id,
        'username': user.username,
        'full_name': get_display_name(user),
        'punishment_id': pun_id,
        'punishment_type': p['punishment_type'],
        'duration': p['duration'],
        'rule': p['rule'],
        'issued_by_username': p['issued_by_username'],
        'reason': state.get('reason', 'Не указана'),
        'text': state.get('text'),
        'photo_file_id': state.get('photo_file_id'),
        'status': 'pending',
        'created_at': datetime.now(MSK),
        'handler_id': None
    }

    await update.message.reply_text(
        f"📨 Ваша жалоба <b>#{appeal_id}</b> отправлена на рассмотрение к администрации.\n\n"
        "⏳ Ожидайте ответа.",
        parse_mode='HTML'
    )


# ---- Команда /obn для ТС и СЗА ----
async def obn_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.chat.type != 'private':
        await update.message.reply_text("❌ Только в ЛС с ботом!")
        return

    user = update.message.from_user
    user_role = get_user_role(user.username)

    if not can_handle_appeal(user_role):
        await update.message.reply_text("❌ Нет доступа! (только ТС и СЗА+)")
        return

    active = {aid: a for aid, a in active_appeals.items()
               if a['status'] in ('pending', 'in_progress')}

    if not active:
        await update.message.reply_text("📭 Нет активных заявок на обжалование.")
        return

    text = f"📋 <b>Активные заявки на обжалование ({len(active)}):</b>\n\nВыберите заявку:"
    buttons = []
    STATUS_ICON = {'pending': '🕐', 'in_progress': '🔍'}
    for aid, a in active.items():
        ptype = PUN_TYPE_NAME.get(a['punishment_type'], a['punishment_type'])
        dur = DUR_TEXT.get(a['duration'], a['duration'])
        uname = f"@{a['username']}" if a['username'] else a['full_name']
        icon = STATUS_ICON.get(a['status'], '🕐')
        label = f"{icon} #{aid} {uname} — {ptype} {dur}"
        buttons.append([InlineKeyboardButton(label, callback_data=f"obn_view_{aid}")])

    await update.message.reply_text(text, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(buttons))


# ---- Просмотр заявки ТС/СЗА ----
async def obn_view_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    user_role = get_user_role(user.username)

    if not can_handle_appeal(user_role):
        await query.answer("❌ Нет доступа", show_alert=True)
        return

    appeal_id = int(query.data.replace("obn_view_", ""))
    a = active_appeals.get(appeal_id)

    if not a:
        await query.answer("❌ Заявка не найдена", show_alert=True)
        return

    pun_fmt = format_punishment(a['punishment_type'], a['duration'])
    uname = f"@{a['username']}" if a['username'] else a['full_name']
    issuer_role_name = get_user_role_name(a['issued_by_username'])

    text = (
        f"📋 <b>Заявка на обжалование #{appeal_id}</b>\n\n"
        f"👤 Пользователь: {uname}\n"
        f"🔹 Наказание: {pun_fmt}\n"
        f"📝 Правило: {a['rule']}\n"
        f"👮 Выдал: @{a['issued_by_username']} ({issuer_role_name})\n"
        f"⚖️ Причина обжалования: {a['reason']}\n"
        f"📅 Подана: {fmt_dt(a['created_at'])}"
    )

    buttons = [
        [InlineKeyboardButton("🔍 Начать работу", callback_data=f"obn_work_{appeal_id}")],
        [InlineKeyboardButton("🔙 Назад", callback_data="obn_back")]
    ]
    await query.message.reply_text(text, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(buttons))


# ---- Начать работу с заявкой ----
async def obn_work_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    user_role = get_user_role(user.username)

    if not can_handle_appeal(user_role):
        await query.answer("❌ Нет доступа", show_alert=True)
        return

    appeal_id = int(query.data.replace("obn_work_", ""))
    a = active_appeals.get(appeal_id)

    if not a:
        await query.answer("❌ Заявка не найдена", show_alert=True)
        return

    a['status'] = 'in_progress'
    a['handler_id'] = user.id

    # Показываем детали + фото + текст
    details_text = (
        f"🔍 <b>Рассмотрение заявки #{appeal_id}</b>\n\n"
        f"👤 Пользователь: @{a['username']}\n"
        f"💬 Описание от пользователя:\n"
        f"{a['text'] or '<i>Не указано</i>'}"
    )

    if a.get('photo_file_id'):
        await query.message.reply_photo(
            photo=a['photo_file_id'],
            caption=details_text,
            parse_mode='HTML'
        )
    else:
        await query.message.reply_text(details_text, parse_mode='HTML')

    action_kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Одобрить", callback_data=f"obn_approve_{appeal_id}"),
            InlineKeyboardButton("❌ Отклонить", callback_data=f"obn_reject_{appeal_id}")
        ]
    ])
    await query.message.reply_text(
        f"✅ Заявка <b>#{appeal_id}</b> взята в работу.\n"
        "Выберите решение:",
        parse_mode='HTML',
        reply_markup=action_kb
    )


# ---- Команда /zk — закрыть заявку ----
async def zk_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.chat.type != 'private':
        await update.message.reply_text("❌ Только в ЛС с ботом!")
        return

    user = update.message.from_user
    user_role = get_user_role(user.username)

    if not can_handle_appeal(user_role):
        await update.message.reply_text("❌ Нет доступа!")
        return

    if not context.args:
        await update.message.reply_text("❌ Формат: /zk номер_заявки")
        return

    try:
        appeal_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ Укажите номер заявки числом")
        return

    a = active_appeals.get(appeal_id)
    if not a:
        await update.message.reply_text(f"❌ Заявка #{appeal_id} не найдена")
        return

    handler_role_name = get_user_role_name(user.username)

    # Уведомление пользователю — заявка остаётся в списке до одобрения/отклонения
    try:
        await context.bot.send_message(
            chat_id=a['user_id'],
            text=(
                f"📋 <b>Заявка на обжалование #{appeal_id}</b>\n\n"
                f"🔍 Ваша заявка принята в работу.\n"
                f"👤 Рассматривает: <b>{handler_role_name}</b>\n\n"
                f"⏳ Ожидайте финального решения."
            ),
            parse_mode='HTML'
        )
    except Exception as e:
        logger.error(f"Не удалось уведомить пользователя об обработке заявки: {e}")

    await update.message.reply_text(
        f"✅ Пользователь уведомлён о том, что заявка <b>#{appeal_id}</b> принята в работу.\n"
        f"Заявка остаётся в списке до одобрения или отклонения.",
        parse_mode='HTML'
    )


# ---- Кнопка "Назад к старту" ----
async def back_to_start_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    # Просто просим написать /start снова
    await query.message.reply_text("🏠 Нажмите /start чтобы вернуться в главное меню.")


async def obn_back_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.reply_text("📋 Введите /obn чтобы посмотреть список заявок снова.")


# ---- Общий обработчик сообщений в ЛС (для шагов обжалования) ----
async def handle_private_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or update.message.chat.type != 'private':
        return

    user = update.message.from_user

    # Сначала проверяем ввод причины отклонения (ТС/СЗА)
    if user.id in reject_states:
        await handle_reject_reason(update, context)
        return

    if user.id not in appeal_states:
        return

    step = appeal_states[user.id].get('step')

    if step == 'text':
        if update.message.text:
            await handle_appeal_text(update, context)
    elif step == 'photo':
        if update.message.photo:
            await handle_appeal_photo(update, context)
        else:
            await update.message.reply_text("📎 Пожалуйста, отправьте фото или нажмите кнопку «Пропустить»")




# ---- Пропустить описание (кнопка) ----
async def appeal_skip_text_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user

    if user.id not in appeal_states:
        await query.answer("❌ Сессия устарела", show_alert=True)
        return

    appeal_states[user.id]['text'] = None
    appeal_states[user.id]['step'] = 'photo'

    skip_kb = InlineKeyboardMarkup([[InlineKeyboardButton("⏭ Пропустить", callback_data="appeal_skip_photo")]])
    await query.message.reply_text(
        "📎 Прикрепите скриншот/фото как доказательство\n"
        "или нажмите кнопку ниже чтобы пропустить:",
        reply_markup=skip_kb
    )


# ---- Пропустить фото (кнопка) ----
async def appeal_skip_photo_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user

    if user.id not in appeal_states:
        await query.answer("❌ Сессия устарела", show_alert=True)
        return

    appeal_states[user.id]['photo_file_id'] = None
    # Нужно передать update.callback_query.message как update-like объект
    # Создаём "псевдо"-submit через message из callback
    state = appeal_states.pop(user.id, {})
    pun_id = state.get('punishment_id')
    p = get_punishment_by_id(pun_id)

    if not p:
        await query.message.reply_text("❌ Ошибка: наказание не найдено.")
        return

    appeal_id = get_next_appeal_id()

    active_appeals[appeal_id] = {
        'appeal_id': appeal_id,
        'user_id': user.id,
        'username': user.username,
        'full_name': get_display_name(user),
        'punishment_id': pun_id,
        'punishment_type': p['punishment_type'],
        'duration': p['duration'],
        'rule': p['rule'],
        'issued_by_username': p['issued_by_username'],
        'reason': state.get('reason', 'Не указана'),
        'text': state.get('text'),
        'photo_file_id': None,
        'status': 'pending',
        'created_at': datetime.now(MSK),
        'handler_id': None
    }

    await query.message.reply_text(
        f"📨 Ваша жалоба <b>#{appeal_id}</b> отправлена на рассмотрение к администрации.\n\n"
        "⏳ Ожидайте ответа.",
        parse_mode='HTML'
    )


# ---- Одобрить обжалование ----
async def obn_approve_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    user_role = get_user_role(user.username)

    if not can_handle_appeal(user_role):
        await query.answer("❌ Нет доступа", show_alert=True)
        return

    appeal_id = int(query.data.replace("obn_approve_", ""))
    a = active_appeals.get(appeal_id)

    if not a:
        await query.answer("❌ Заявка не найдена", show_alert=True)
        return

    a['status'] = 'approved'
    handler_role_name = get_user_role_name(user.username)

    # Снимаем наказание
    removed = remove_all_punishments_for_appeal(a['user_id'], a['punishment_type'])
    removal_note = "\n🔓 Наказание снято." if removed else "\n⚠️ Не удалось снять наказание автоматически."

    # Уведомить пользователя
    try:
        await context.bot.send_message(
            chat_id=a['user_id'],
            text=(
                f"✅ <b>Обжалование было одобрено</b>\n\n"
                f"👤 Одобрил: <b>{handler_role_name}</b>"
                f"{removal_note}"
            ),
            parse_mode='HTML'
        )
    except Exception as e:
        logger.error(f"Ошибка уведомления об одобрении: {e}")

    await query.message.reply_text(
        f"✅ Заявка <b>#{appeal_id}</b> одобрена. Пользователь уведомлён.{removal_note}",
        parse_mode='HTML'
    )


# ---- Отклонить обжалование (шаг 1 — запрос причины) ----
async def obn_reject_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    user_role = get_user_role(user.username)

    if not can_handle_appeal(user_role):
        await query.answer("❌ Нет доступа", show_alert=True)
        return

    appeal_id = int(query.data.replace("obn_reject_", ""))
    a = active_appeals.get(appeal_id)

    if not a:
        await query.answer("❌ Заявка не найдена", show_alert=True)
        return

    reject_states[user.id] = {'appeal_id': appeal_id}

    await query.message.reply_text(
        f"📝 Укажите причину отклонения заявки <b>#{appeal_id}</b>:\n"
        "(Напишите причину следующим сообщением)",
        parse_mode='HTML'
    )


# ---- Получение причины отклонения ----
async def handle_reject_reason(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user

    if user.id not in reject_states:
        return False

    user_role = get_user_role(user.username)
    if not can_handle_appeal(user_role):
        return False

    appeal_id = reject_states.pop(user.id)['appeal_id']
    a = active_appeals.get(appeal_id)

    if not a:
        await update.message.reply_text("❌ Заявка не найдена.")
        return True

    a['status'] = 'rejected'
    handler_role_name = get_user_role_name(user.username)
    reject_reason = update.message.text

    # Уведомить пользователя
    try:
        await context.bot.send_message(
            chat_id=a['user_id'],
            text=(
                f"❌ <b>Обжалование было отклонено</b>\n\n"
                f"📝 Причина: {reject_reason}\n"
                f"👤 Отклонил: <b>{handler_role_name}</b>"
            ),
            parse_mode='HTML'
        )
    except Exception as e:
        logger.error(f"Ошибка уведомления об отклонении: {e}")

    await update.message.reply_text(
        f"✅ Заявка <b>#{appeal_id}</b> отклонена. Пользователь уведомлён.",
        parse_mode='HTML'
    )
    return True



# ---- Вспомогательные функции для /info и /swarn ----

def get_user_warn_count(user_id: int) -> int:
    """Количество активных варнов"""
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT COUNT(*) FROM warnings WHERE user_id = %s AND active = TRUE",
                    (user_id,)
                )
                return cur.fetchone()[0]
    except Exception as e:
        logger.error(f"get_user_warn_count error: {e}")
        return 0


def get_user_blacklist_status(user_id: int):
    """Активная запись в ЧС или None"""
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT id, days, reason, issued_by, start_date, end_date
                    FROM blacklist
                    WHERE user_id = %s AND active = TRUE
                    ORDER BY start_date DESC LIMIT 1
                """, (user_id,))
                return cur.fetchone()
    except Exception as e:
        logger.error(f"get_user_blacklist_status error: {e}")
        return None


def get_user_recent_punishments(user_id: int, limit: int = 5):
    """Последние N наказаний из таблицы punishments"""
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT punishment_type, duration, rule, issued_by_username, created_at
                    FROM punishments
                    WHERE user_id = %s
                    ORDER BY created_at DESC
                    LIMIT %s
                """, (user_id, limit))
                return cur.fetchall()
    except Exception as e:
        logger.error(f"get_user_recent_punishments error: {e}")
        return []


def remove_one_warn(user_id: int):
    """Снять один (самый старый активный) варн. Возвращает оставшееся кол-во или None при ошибке."""
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT id FROM warnings
                    WHERE user_id = %s AND active = TRUE
                    ORDER BY created_at ASC
                    LIMIT 1
                """, (user_id,))
                result = cur.fetchone()
                if not result:
                    return -1  # нет варнов
                cur.execute("UPDATE warnings SET active = FALSE WHERE id = %s", (result[0],))
                cur.execute(
                    "SELECT COUNT(*) FROM warnings WHERE user_id = %s AND active = TRUE",
                    (user_id,)
                )
                return cur.fetchone()[0]
    except Exception as e:
        logger.error(f"remove_one_warn error: {e}")
        return None


def remove_all_punishments_for_appeal(user_id: int, punishment_type: str):
    """Снять активное наказание при одобрении обжалования"""
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                if punishment_type == 'warn':
                    # Снимаем один самый последний варн
                    cur.execute("""
                        UPDATE warnings SET active = FALSE
                        WHERE id = (
                            SELECT id FROM warnings
                            WHERE user_id = %s AND active = TRUE
                            ORDER BY created_at DESC LIMIT 1
                        )
                    """, (user_id,))
                elif punishment_type in ('ban', 'mute'):
                    cur.execute("""
                        UPDATE blacklist SET active = FALSE
                        WHERE user_id = %s AND active = TRUE
                    """, (user_id,))
        return True
    except Exception as e:
        logger.error(f"remove_all_punishments_for_appeal error: {e}")
        return False


# ---- /info команда ----
async def info_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    issuer = message.from_user
    issuer_role = get_user_role(issuer.username)

    if issuer_role is None or issuer_role < Role.МЛ_АДМИН:
        err = await message.reply_text("❌ Нет прав! (Мл. Админ+)")
        asyncio.create_task(delete_messages_after_delay(
            context, message.chat.id, [message.message_id, err.message_id], DELETE_AFTER_SECONDS))
        return

    target_user_id = None
    target_username = None

    text = message.text.strip()
    parts = text.split(maxsplit=1)

    if len(parts) >= 2:
        arg = parts[1].lstrip('@')
        if arg.isdigit():
            target_user_id = int(arg)
        else:
            target_username = arg
            found_id, _ = find_user_id_by_username(target_username)
            if found_id:
                target_user_id = found_id
            else:
                err = await message.reply_text(
                    f"❌ @{target_username} не найден в базе!\n💡 Попросите написать /start боту")
                asyncio.create_task(delete_messages_after_delay(
                    context, message.chat.id, [message.message_id, err.message_id], DELETE_AFTER_SECONDS))
                return
    elif message.reply_to_message:
        target_user = message.reply_to_message.from_user
        target_user_id = target_user.id
        target_username = target_user.username

    if not target_user_id:
        err = await message.reply_text(
            "❌ Укажите пользователя:\n/info @username или /info ID\nили ответьте на сообщение")
        asyncio.create_task(delete_messages_after_delay(
            context, message.chat.id, [message.message_id, err.message_id], DELETE_AFTER_SECONDS))
        return

    # Получаем данные
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    "SELECT user_id, username, full_name FROM users WHERE user_id = %s",
                    (target_user_id,)
                )
                user_row = cur.fetchone()
    except Exception as e:
        logger.error(f"info_command DB error: {e}")
        user_row = None

    if not user_row:
        err = await message.reply_text("❌ Пользователь не найден в базе.")
        asyncio.create_task(delete_messages_after_delay(
            context, message.chat.id, [message.message_id, err.message_id], DELETE_AFTER_SECONDS))
        return

    uid = user_row['user_id']
    uname = f"@{user_row['username']}" if user_row['username'] else user_row['full_name']
    role_name = get_user_role_name(user_row['username']) if user_row['username'] else "Участник"

    warn_count = get_user_warn_count(uid)
    bl = get_user_blacklist_status(uid)
    recent_puns = get_user_recent_punishments(uid, 6)

    # ЧС статус (чёрный список администрации)
    if bl:
        end_dt = bl['end_date']
        if end_dt:
            now_msk = datetime.now(MSK)
            # end_dt может быть без timezone
            if end_dt.tzinfo is None:
                from zoneinfo import ZoneInfo as _ZI
                end_dt = end_dt.replace(tzinfo=_ZI('Europe/Moscow'))
            days_left = (end_dt - now_msk).days
            hours_left = int((end_dt - now_msk).total_seconds() // 3600)
            if days_left > 0:
                time_left = f"{days_left} дн."
            elif hours_left > 0:
                time_left = f"{hours_left} ч."
            else:
                time_left = "менее часа"
            bl_text = (
                f"⛔️ Да\n"
                f"   📅 До: {end_dt.strftime('%d.%m.%Y')}\n"
                f"   ⏳ Осталось: {time_left}\n"
                f"   📝 Причина: {bl['reason'] or 'не указана'}"
            )
        else:
            bl_text = f"⛔️ Да (бессрочно)\n   📝 Причина: {bl['reason'] or 'не указана'}"
    else:
        bl_text = "✅ Нет"

    # Последние наказания
    pun_lines = ""
    if recent_puns:
        pun_lines = "\n\n📋 <b>Последние наказания:</b>"
        for p in recent_puns:
            pun_fmt = format_punishment(p['punishment_type'], p['duration'])
            date_str = fmt_dt(p['created_at'])
            pun_lines += f"\n• {pun_fmt} — {date_str}"

    info_text = (
        f"👤 <b>Информация о пользователе</b>\n\n"
        f"🆔 ID: <code>{uid}</code>\n"
        f"👤 Юзер: {uname}\n"
        f"🎖 Роль: {role_name}\n"
        f"⚠️ Варны: <b>{warn_count}</b>\n"
        f"🚫 ЧС Админки: {bl_text}"
        f"{pun_lines}"
    )

    reply = await message.reply_text(info_text, parse_mode='HTML')
    asyncio.create_task(delete_messages_after_delay(
        context, message.chat.id, [message.message_id, reply.message_id], 120))


# ---- /swarn команда ----
async def snwarn_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if message.chat.id != ADMIN_GROUP_ID:
        return

    issuer = message.from_user
    issuer_role = get_user_role(issuer.username)

    if issuer_role is None or issuer_role < Role.МЛ_АДМИН:
        err = await message.reply_text("❌ Нет прав! (Мл. Админ+)")
        asyncio.create_task(delete_messages_after_delay(
            context, message.chat.id, [message.message_id, err.message_id], DELETE_AFTER_SECONDS))
        return

    target_user_id = None
    target_username = None

    text = message.text.strip()
    parts = text.split(maxsplit=1)

    if len(parts) >= 2:
        arg = parts[1].lstrip('@')
        if arg.isdigit():
            target_user_id = int(arg)
        else:
            target_username = arg
            found_id, _ = find_user_id_by_username(target_username)
            if found_id:
                target_user_id = found_id
            else:
                err = await message.reply_text(
                    f"❌ @{target_username} не найден в базе!\n💡 Попросите написать /start боту")
                asyncio.create_task(delete_messages_after_delay(
                    context, message.chat.id, [message.message_id, err.message_id], DELETE_AFTER_SECONDS))
                return
    elif message.reply_to_message:
        target_user = message.reply_to_message.from_user
        target_user_id = target_user.id
        target_username = target_user.username

    if not target_user_id:
        err = await message.reply_text(
            "❌ Укажите пользователя:\n/snwarn @username или ответьте на сообщение")
        asyncio.create_task(delete_messages_after_delay(
            context, message.chat.id, [message.message_id, err.message_id], DELETE_AFTER_SECONDS))
        return

    result = remove_one_warn(target_user_id)
    display = f"@{target_username}" if target_username else f"ID {target_user_id}"

    if result == -1:
        err = await message.reply_text(f"ℹ️ У {display} нет активных варнов.")
        asyncio.create_task(delete_messages_after_delay(
            context, message.chat.id, [message.message_id, err.message_id], DELETE_AFTER_SECONDS))
    elif result is None:
        err = await message.reply_text("❌ Ошибка при снятии варна.")
        asyncio.create_task(delete_messages_after_delay(
            context, message.chat.id, [message.message_id, err.message_id], DELETE_AFTER_SECONDS))
    else:
        reply = await message.reply_text(
            f"✅ Варн снят с {display}\n"
            f"⚠️ Оставшихся варнов: <b>{result}</b>",
            parse_mode='HTML'
        )
        asyncio.create_task(delete_messages_after_delay(
            context, message.chat.id, [message.message_id, reply.message_id], DELETE_AFTER_SECONDS))


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

    application.add_handler(MessageHandler(filters.PHOTO & filters.ChatType.SUPERGROUP, handle_report))
    application.add_handler(MessageHandler(filters.ChatType.SUPERGROUP & ~filters.COMMAND, handle_main_chat_message))
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("vg", warning_command))
    application.add_handler(CommandHandler("svg", remove_warning_command))
    application.add_handler(CommandHandler("bl", blacklist_command))
    application.add_handler(CommandHandler("ubl", unblacklist_command))
    application.add_handler(CommandHandler("sp", reset_accepted_command))
    application.add_handler(CommandHandler("so", reset_rejected_command))
    application.add_handler(CommandHandler("leaderboard", leaderboard_command))
    application.add_handler(CommandHandler("history", history_command))
    application.add_handler(CallbackQueryHandler(history_pagination_callback, pattern='^history_(prev|next)_'))
    application.add_handler(CommandHandler("obv", announcement_command))
    application.add_handler(CommandHandler("info", info_command))
    application.add_handler(CommandHandler("snwarn", snwarn_command))
    application.add_handler(CommandHandler("obn", obn_command))
    application.add_handler(CommandHandler("zk", zk_command))
    application.add_handler(CallbackQueryHandler(my_history_callback, pattern='^my_history$'))
    application.add_handler(CallbackQueryHandler(view_punishment_callback, pattern='^view_pun_'))
    application.add_handler(CallbackQueryHandler(appeal_start_callback, pattern='^appeal_(start|pun_)'))
    application.add_handler(CallbackQueryHandler(appeal_reason_callback, pattern='^appeal_reason_'))
    application.add_handler(CallbackQueryHandler(obn_view_callback, pattern='^obn_view_'))
    application.add_handler(CallbackQueryHandler(obn_work_callback, pattern='^obn_work_'))
    application.add_handler(CallbackQueryHandler(back_to_start_callback, pattern='^back_to_start$'))
    application.add_handler(CallbackQueryHandler(obn_back_callback, pattern='^obn_back$'))
    application.add_handler(CallbackQueryHandler(appeal_skip_text_callback, pattern='^appeal_skip_text$'))
    application.add_handler(CallbackQueryHandler(appeal_skip_photo_callback, pattern='^appeal_skip_photo$'))
    application.add_handler(CallbackQueryHandler(obn_approve_callback, pattern='^obn_approve_'))
    application.add_handler(CallbackQueryHandler(obn_reject_callback, pattern='^obn_reject_'))
    application.add_handler(MessageHandler(filters.ChatType.PRIVATE & ~filters.COMMAND, handle_private_message))
    application.add_handler(CallbackQueryHandler(handle_button_callback))

    logger.info("✅ Bot running with automatic punishments!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()


    # Удаление из категории ОТЧЕТНОСТЬ
    if query.message.message_thread_id in [MODERATOR_REPORT_TOPIC_ID, ADMIN_REPORT_TOPIC_ID]:
        asyncio.create_task(
            delete_messages_after_delay(
                context,
                query.message.chat.id,
                [query.message.message_id],
                120
            )
        )
        logger.info(f"⏰ Принятый отчёт будет удалён через 2 мин")






# ✅ ФИКС УВЕДОМЛЕНИЙ: PUBLIC_CHAT_ID удаление через 2 мин