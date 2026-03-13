import asyncio
import logging
import random
import uuid
import re
from datetime import datetime, timedelta
from typing import Union, Optional, Dict, List, Any
import json
import os
import time

from aiogram import Bot, Dispatcher, types, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode, ChatType
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    CallbackQuery, Message, InlineQueryResultArticle,
    InputTextMessageContent
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.storage.memory import MemoryStorage

# Для рассылки по расписанию
import aioschedule

# Конфигурация
BOT_TOKEN = "8729608216:AAH3u-dH3So6B96MAqVDospaiTATrzcekQo"
ADMIN_IDS = [7313407194]  # Список админов
CHANNEL_LINK = "https://t.me/+j5plVfjrsrY4MWJi"  # Ссылка на чат
SUPPORT_LINK = "t.me/qwhatss"  # Ссылка на поддержку
GIVEAWAY_CHAT_ID = -1003720079599  # ID чата для раздач

# Файл базы данных
DB_FILE = "users_db.json"
CHECKS_FILE = "checks_db.json"
TICKETS_FILE = "tickets_db.json"

# Настройка логирования
logging.basicConfig(level=logging.INFO)

# Инициализация бота и диспетчера
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# ==== Премиум эмодзи (ТОЛЬКО ДЛЯ ПОЛЬЗОВАТЕЛЬСКИХ ТЕКСТОВ) ====
PREMIUM_EMOJIS = {
    "rocket": ("🚀", "5377336433692412420"),
    "dollar": ("💵", "5377852667286559564"),
    "dice": ("🎲", "5377346496800786271"),
    "transfer": ("🔄", "5377720025811555309"),
    "lightning": ("⚡", "5375469677696815127"),
    "casino": ("🎰", "5969709082049779216"),
    "balance": ("💰", "5262509177363787445"),
    "withdraw": ("💸", "5226731292334235524"),
    "deposit": ("💳", "5226731292334235524"),
    "game": ("🎮", "5258508428212445001"),
    "mine": ("💣", "4979035365823219688"),
    "win": ("🏆", "5436386989857320953"),
    "lose": ("💥", "4979035365823219688"),
    "prize": ("🎁", "5323761960829862762"),
    "user": ("👤", "5168063997575956782"),
    "stats": ("📊", "5231200819986047254"),
    "time": ("⏰", "5258419835922030550"),
    "min": ("📍", "5447183459602669338"),
    "card": ("💳", "5902056028513505203"),
    "rules": ("📋", "5258328383183396223"),
    "info": ("ℹ️", "5258334872878980409"),
    "back": ("↩️", "5877629862306385808"),
    "play": ("▶️", "5467583879948803288"),
    "bet": ("🎯", "5893048571560726748"),
    "multiplier": ("📈", "5201691993775818138"),
    "history": ("📜", "5353025608832004653"),
    "check": ("🧾", "5902056028513505203"),
    "users": ("👥", "5168063997575956782"),
    "crown": ("👑", "5377311257601253397"),
    "warning": ("⚠️", "5375469677696815127"),
    "success": ("✅", "5375471152190916117"),
    "error": ("❌", "5375471152190916117"),
    "link": ("🔗", "5375469677696815127"),
    "settings": ("⚙️", "5375469677696815127"),
    "refresh": ("🔄", "5377720025811555309"),
    "support": ("📞", "5375469677696815127"),
    "ticket": ("🎫", "5375469677696815127"),
    "cat": ("🐱", "5377346496800786271"),
    "tip": ("💫", "5375469677696815127"),
    "heart": ("❤️", "5375469677696815127"),
}

def premium_emoji(name: str) -> str:
    """Возвращает HTML-код для премиум эмодзи (только для пользовательских текстов)."""
    if name in PREMIUM_EMOJIS:
        emoji, emoji_id = PREMIUM_EMOJIS[name]
        return f'<tg-emoji emoji-id="{emoji_id}">{emoji}</tg-emoji>'
    return name

# ==== Работа с базой данных ====
def load_db():
    """Загружает базу данных из файла."""
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            return {}
    return {}

def save_db(db):
    """Сохраняет базу данных в файл."""
    with open(DB_FILE, 'w', encoding='utf-8') as f:
        json.dump(db, f, ensure_ascii=False, indent=4)

def load_checks():
    """Загружает базу чеков из файла."""
    if os.path.exists(CHECKS_FILE):
        try:
            with open(CHECKS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            return {}
    return {}

def save_checks(checks):
    """Сохраняет базу чеков в файл."""
    with open(CHECKS_FILE, 'w', encoding='utf-8') as f:
        json.dump(checks, f, ensure_ascii=False, indent=4)

def load_tickets():
    """Загружает базу тикетов из файла."""
    if os.path.exists(TICKETS_FILE):
        try:
            with open(TICKETS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            return {}
    return {}

def save_tickets(tickets):
    """Сохраняет базу тикетов в файл."""
    with open(TICKETS_FILE, 'w', encoding='utf-8') as f:
        json.dump(tickets, f, ensure_ascii=False, indent=4)

def get_user(user_id: int) -> dict:
    """Возвращает данные пользователя или создает нового."""
    db = load_db()
    user_id_str = str(user_id)
    if user_id_str not in db:
        db[user_id_str] = {
            "balance": 0,
            "registered_at": datetime.now().isoformat(),
            "last_claim_time": None,
            "last_bonus_time": None,
            "last_cat_time": None,
            "username": None,
            "total_earned": 0,
            "checks_created": 0,
            "checks_activated": 0,
            "tickets_created": 0
        }
        save_db(db)
    return db[user_id_str]

def update_user(user_id: int, data: dict):
    """Обновляет данные пользователя."""
    db = load_db()
    user_id_str = str(user_id)
    if user_id_str in db:
        db[user_id_str].update(data)
    else:
        db[user_id_str] = data
    save_db(db)

def get_all_users() -> dict:
    """Возвращает всех пользователей."""
    return load_db()

def get_top_users(limit: int = 10) -> list:
    """Возвращает топ пользователей по балансу."""
    db = load_db()
    sorted_users = sorted(db.items(), key=lambda item: item[1].get('balance', 0), reverse=True)
    return sorted_users[:limit]

def get_user_place(user_id: int) -> int:
    """Возвращает место пользователя в топе."""
    db = load_db()
    sorted_users = sorted(db.items(), key=lambda item: item[1].get('balance', 0), reverse=True)
    for index, (uid, _) in enumerate(sorted_users):
        if int(uid) == user_id:
            return index + 1
    return 0

def can_claim_bonus(user_id: int) -> tuple[bool, Optional[int]]:
    """Проверяет, может ли пользователь получить бонус."""
    user_data = get_user(user_id)
    last_bonus = user_data.get('last_bonus_time')
    
    if not last_bonus:
        return True, 0
    
    last_bonus_time = datetime.fromisoformat(last_bonus)
    time_diff = datetime.now() - last_bonus_time
    
    cooldown = 7200  # 2 часа в секундах
    elapsed = time_diff.total_seconds()
    
    if elapsed >= cooldown:
        return True, 0
    else:
        remaining = int(cooldown - elapsed)
        return False, remaining

def can_use_cat(user_id: int) -> tuple[bool, Optional[int]]:
    """Проверяет, может ли пользователь использовать котика."""
    user_data = get_user(user_id)
    last_cat = user_data.get('last_cat_time')
    
    if not last_cat:
        return True, 0
    
    last_cat_time = datetime.fromisoformat(last_cat)
    time_diff = datetime.now() - last_cat_time
    
    cooldown = 86400  # 24 часа в секундах
    elapsed = time_diff.total_seconds()
    
    if elapsed >= cooldown:
        return True, 0
    else:
        remaining = int(cooldown - elapsed)
        return False, remaining

# ==== Система тикетов ====
def create_ticket(user_id: int, question: str) -> dict:
    """Создает новый тикет."""
    tickets = load_tickets()
    ticket_id = str(uuid.uuid4())[:8]
    
    ticket_data = {
        "id": ticket_id,
        "user_id": user_id,
        "question": question,
        "created_at": datetime.now().isoformat(),
        "status": "open",
        "answered": False,
        "answer": None
    }
    
    tickets[ticket_id] = ticket_data
    save_tickets(tickets)
    
    user_data = get_user(user_id)
    user_data['tickets_created'] = user_data.get('tickets_created', 0) + 1
    update_user(user_id, user_data)
    
    return ticket_data

def get_ticket(ticket_id: str) -> Optional[dict]:
    """Возвращает тикет по ID."""
    tickets = load_tickets()
    return tickets.get(ticket_id)

def answer_ticket(ticket_id: str, answer_text: str):
    """Отвечает на тикет."""
    tickets = load_tickets()
    if ticket_id in tickets:
        tickets[ticket_id]['answer'] = answer_text
        tickets[ticket_id]['answered_at'] = datetime.now().isoformat()
        tickets[ticket_id]['answered'] = True
        save_tickets(tickets)

# ==== Система чеков ====
def generate_check_code() -> str:
    """Генерирует уникальный код для чека."""
    return str(uuid.uuid4())[:8].upper()

def create_check(creator_id: int, amount: int, max_activations: int) -> dict:
    """Создает новый чек."""
    checks = load_checks()
    check_code = generate_check_code()
    
    check_data = {
        "code": check_code,
        "creator_id": creator_id,
        "amount": amount,
        "max_activations": max_activations,
        "current_activations": 0,
        "created_at": datetime.now().isoformat(),
        "expires_at": (datetime.now() + timedelta(days=7)).isoformat(),
        "activated_by": [],
        "active": True
    }
    
    checks[check_code] = check_data
    save_checks(checks)
    
    user_data = get_user(creator_id)
    user_data['checks_created'] = user_data.get('checks_created', 0) + 1
    update_user(creator_id, user_data)
    
    return check_data

def activate_check_logic(check_code: str, user_id: int) -> dict:
    """Активирует чек и возвращает результат (логика)."""
    checks = load_checks()
    
    if check_code not in checks:
        return {"success": False, "reason": "not_found"}
    
    check = checks[check_code]
    
    if not check.get('active', True):
        return {"success": False, "reason": "inactive"}
    
    if check['current_activations'] >= check['max_activations']:
        check['active'] = False
        save_checks(checks)
        return {"success": False, "reason": "expired"}
    
    if user_id in check['activated_by']:
        return {"success": False, "reason": "already_activated"}
    
    expires_at = datetime.fromisoformat(check['expires_at'])
    if datetime.now() > expires_at:
        check['active'] = False
        save_checks(checks)
        return {"success": False, "reason": "expired"}
    
    check['current_activations'] += 1
    check['activated_by'].append(user_id)
    
    if check['current_activations'] >= check['max_activations']:
        check['active'] = False
    
    save_checks(checks)
    
    user_data = get_user(user_id)
    user_data['balance'] += check['amount']
    user_data['checks_activated'] = user_data.get('checks_activated', 0) + 1
    update_user(user_id, user_data)
    
    return {
        "success": True,
        "amount": check['amount'],
        "creator_id": check['creator_id'],
        "remaining": check['max_activations'] - check['current_activations']
    }

def get_user_checks(user_id: int) -> list:
    """Возвращает все чеки, созданные пользователем."""
    checks = load_checks()
    user_checks = []
    for code, check in checks.items():
        if check['creator_id'] == user_id:
            user_checks.append(check)
    return user_checks

# ==== Полезные советы для котиков ====
CAT_TIPS = [
    "Улыбнись, даже если на душе скребут кошки! 😺",
    "Сделай перерыв на чашечку кофе ☕",
    "Погладь котика (или друга) — это поднимает настроение! 🐱",
    "Выпей стакан воды — гидратация важна! 💧",
    "Сделай 10 приседаний, чтобы взбодриться! 💪",
    "Напиши другу тёплое сообщение 💌",
    "Вспомни три приятных момента за сегодня ✨",
    "Посмотри в окно — там целый мир! 🌍",
    "Съешь что-нибудь вкусное 🍪",
    "Сделай глубокий вдох и выдох 🧘",
    "Ты молодец, что пользуешься нашим ботом! ⭐",
    "Котики желают тебе удачного дня! 🍀",
    "Не забывай отдыхать между делами 😴",
    "Твоя улыбка делает мир лучше! 🌈",
    "Сегодня точно будет хороший день! ☀️"
]

# ==== ID стикеров котиков ====
CAT_STICKERS = [
    "CAACAgUAAxkBAAEQvpJptD4nBJ-x_H7ugN-t65sibIvz-wACwAoAAm-W2VUnXCFMljNebToE",
    "CAACAgUAAxkBAAEQvpRptD45SAtSkFZVy276Xye4U3sDXgACcAsAApwv2FVG0dpCX41YUjoE",
    "CAACAgUAAxkBAAEQvpZptD5Gf3coDLGYeNm9AXMP-rHXcgACbgkAAhDo2FWbNi6McBmZEjoE"
]

# ==== FSM для админки, тикетов и чеков ====
class AdminStates(StatesGroup):
    waiting_for_broadcast = State()
    waiting_for_broadcast_buttons = State()
    waiting_for_user_id_balance = State()
    waiting_for_balance_amount = State()
    waiting_for_user_id_reset = State()
    waiting_for_ticket_answer = State()

class TicketStates(StatesGroup):
    waiting_for_question = State()

class CheckStates(StatesGroup):
    waiting_for_amount = State()
    waiting_for_activations = State()

# ==== Генерация клавиатур (Inline) ====
def main_menu_keyboard(is_private: bool = True):
    """Главное меню."""
    builder = InlineKeyboardBuilder()
    builder.button(text="👤 Профиль", callback_data="profile")
    builder.button(text="🏆 Топ", callback_data="top")
    builder.button(text="❓ Помощь", callback_data="help")
    builder.button(text="💎 Донат", callback_data="donate")
    builder.button(text="📋 Команды", callback_data="commands")
    builder.button(text="🐱 Котики", callback_data="cat_menu")
    
    # Кнопка "Чеки" и "Поддержка" только в личных сообщениях
    if is_private:
        builder.button(text="🧾 Чеки", callback_data="checks_menu")
        builder.button(text="📞 Поддержка", callback_data="support_menu")
        builder.adjust(2, 2, 2, 1)
    else:
        builder.adjust(2, 2, 2)
    
    return builder.as_markup()

def back_button_keyboard():
    """Клавиатура с кнопкой 'Назад'."""
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 Назад", callback_data="back_to_main")
    return builder.as_markup()

def cat_menu_keyboard():
    """Меню котиков."""
    builder = InlineKeyboardBuilder()
    builder.button(text="🐱 Мур мяу", callback_data="get_cat")
    builder.button(text="🔙 Назад", callback_data="back_to_main")
    builder.adjust(1)
    return builder.as_markup()

def cat_result_keyboard():
    """Клавиатура после получения котика."""
    builder = InlineKeyboardBuilder()
    builder.button(text="📋 Меню", callback_data="back_to_main")
    return builder.as_markup()

def support_menu_keyboard():
    """Меню поддержки."""
    builder = InlineKeyboardBuilder()
    builder.button(text="🎫 Создать тикет", callback_data="create_ticket")
    builder.button(text="🔙 Назад", callback_data="back_to_main")
    builder.adjust(1)
    return builder.as_markup()

def checks_menu_keyboard():
    """Меню чеков."""
    builder = InlineKeyboardBuilder()
    builder.button(text="🎁 Создать чек", callback_data="check_create")
    builder.button(text="📜 Мои чеки", callback_data="check_my")
    builder.button(text="🔙 Назад", callback_data="back_to_main")
    builder.adjust(2, 1)
    return builder.as_markup()

def check_keyboard(check_code: str):
    """Клавиатура для чека."""
    builder = InlineKeyboardBuilder()
    builder.button(text="🎁 Активировать чек", callback_data=f"activate_check_{check_code}")
    builder.button(text="📋 Копировать код", callback_data=f"copy_code_{check_code}")
    builder.button(text="🔄 Поделиться", switch_inline_query=f"Чек {check_code}")
    builder.adjust(1)
    return builder.as_markup()

def donate_keyboard():
    """Клавиатура для доната."""
    builder = InlineKeyboardBuilder()
    builder.button(text="⭐ 15 звёзд", callback_data="donate_15")
    builder.button(text="⭐ 50 звёзд", callback_data="donate_50")
    builder.button(text="⭐ 100 звёзд", callback_data="donate_100")
    builder.adjust(3)
    builder.row(InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main"))
    return builder.as_markup()

def support_keyboard():
    """Клавиатура для раздела помощь."""
    builder = InlineKeyboardBuilder()
    builder.button(text="📞 Поддержка", url=SUPPORT_LINK)
    builder.button(text="🔙 Назад", callback_data="back_to_main")
    builder.adjust(1)
    return builder.as_markup()

def claim_keyboard(claim_id: str):
    """Клавиатура для кнопки 'Забрать' в раздаче."""
    builder = InlineKeyboardBuilder()
    builder.button(text="🍪 Забрать печеньку!", callback_data=f"claim_{claim_id}")
    return builder.as_markup()

def commands_keyboard():
    """Клавиатура для раздела команд."""
    builder = InlineKeyboardBuilder()
    builder.button(text="🎲 /bonus", callback_data="info_bonus")
    builder.button(text="👤 /start", callback_data="info_start")
    builder.button(text="🏆 /top", callback_data="info_top")
    builder.button(text="🧾 /check", callback_data="info_check")
    builder.button(text="🐱 /cat", callback_data="info_cat")
    builder.button(text="🔙 Назад", callback_data="back_to_main")
    builder.adjust(2, 2, 2)
    return builder.as_markup()

def broadcast_buttons_keyboard():
    """Клавиатура для выбора типа кнопок в рассылке (БЕЗ ПРЕМИУМ ЭМОДЗИ)."""
    builder = InlineKeyboardBuilder()
    builder.button(text="🔗 Без кнопок", callback_data="broadcast_no_buttons")
    builder.button(text="🔗 Одна кнопка", callback_data="broadcast_one_button")
    builder.button(text="🔗 Две кнопки", callback_data="broadcast_two_buttons")
    builder.button(text="🔗 Три кнопки", callback_data="broadcast_three_buttons")
    builder.button(text="❌ Отмена", callback_data="broadcast_cancel")
    builder.adjust(1)
    return builder.as_markup()

def admin_ticket_keyboard(ticket_id: str):
    """Клавиатура для ответа на тикет в админке."""
    builder = InlineKeyboardBuilder()
    builder.button(text="✍️ Ответить", callback_data=f"answer_ticket_{ticket_id}")
    return builder.as_markup()

# ==== Получение информации о боте ====
async def get_bot_info():
    """Получает информацию о боте."""
    bot_info = await bot.get_me()
    return bot_info.username

# ==== Команда /start ====
@dp.message(CommandStart())
async def command_start_handler(message: Message) -> None:
    """Обработчик команды /start."""
    user = message.from_user
    is_private = message.chat.type == ChatType.PRIVATE
    
    # Регистрируем пользователя или обновляем его username
    user_data = get_user(user.id)
    user_data['username'] = user.username or user.full_name
    update_user(user.id, user_data)
    
    # Получаем username бота
    bot_username = (await bot.get_me()).username

    # Разные приветствия для лички и чата
    if is_private:
        text = (
            f"{premium_emoji('rocket')} <b>Приветик, {user.full_name}!</b>\n"
            f"➖➖➖➖➖➖➖➖➖➖\n\n"
            f"{premium_emoji('game')} <b>Я - бот для раздачи печенек</b> за активность в нашем "
            f"<a href='{CHANNEL_LINK}'>Telegram канале</a>.\n\n"
            f"{premium_emoji('prize')} <b>В конце каждого месяца</b> подводятся итоги, а топ-10 охотников "
            f"получают крутые вознаграждения!\n\n"
            f"{premium_emoji('rules')} <b>Основные возможности:</b>\n"
            f"• {premium_emoji('dice')} <code>/bonus</code> — бонус раз в 2 часа (1-20 печенек)\n"
            f"• {premium_emoji('check')} <code>/check</code> — создать чек на печеньки (только в личке)\n"
            f"• {premium_emoji('cat')} <code>/cat</code> — получить котика (раз в 24 часа)\n"
            f"• {premium_emoji('win')} <code>/top</code> — топ пользователей\n"
            f"• {premium_emoji('support')} <code>/support</code> — техподдержка\n\n"
            f"➖➖➖➖➖➖➖➖➖➖\n"
            f"{premium_emoji('lightning')} <b>Вперед на Охоту за Печеньками!</b>\n"
            f"<blockquote>Покажи всем, кто здесь BOSS!</blockquote>"
        )
    else:
        text = (
            f"{premium_emoji('rocket')} <b>Привет, {user.full_name}!</b>\n"
            f"➖➖➖➖➖➖➖➖➖➖\n\n"
            f"{premium_emoji('game')} Я бот для раздачи печенек в этом чате!\n\n"
            f"{premium_emoji('dice')} <code>/bonus</code> — получить бонус раз в 2 часа\n"
            f"{premium_emoji('cat')} <code>/cat</code> — получить котика (раз в 24 часа)\n"
            f"{premium_emoji('win')} <code>/top</code> — топ пользователей\n\n"
            f"{premium_emoji('info')} Для создания чеков и обращения в поддержку напиши мне в личку: @{bot_username}"
        )

    await message.answer(text, reply_markup=main_menu_keyboard(is_private), disable_web_page_preview=True)

# ==== Команда /cat ====
@dp.message(Command("cat"))
async def cat_command_handler(message: Message) -> None:
    """Обработчик команды /cat."""
    user = message.from_user
    user_id = user.id
    is_private = message.chat.type == ChatType.PRIVATE
    
    can_get, remaining = can_use_cat(user_id)
    
    if not can_get:
        hours = remaining // 3600
        minutes = (remaining % 3600) // 60
        
        time_text = ""
        if hours > 0:
            time_text += f"{hours} ч. "
        if minutes > 0:
            time_text += f"{minutes} мин."
        
        await message.answer(
            f"{premium_emoji('time')} <b>Котик пока отдыхает!</b>\n\n"
            f"{premium_emoji('cat')} Следующий котик будет доступен через: <b>{time_text}</b>\n\n"
            f"<i>Возвращайся позже за порцией милоты!</i>",
            reply_markup=back_button_keyboard() if is_private else None
        )
        return
    
    # Показываем меню котиков
    text = (
        f"{premium_emoji('cat')} <b>КОТИКИ - ТВОЙ ИСТОЧНИК РАДОСТИ!</b>\n"
        f"➖➖➖➖➖➖➖➖➖➖\n\n"
        f"{premium_emoji('game')} Нажимай на кнопку и поднимай настроение!\n"
        f"{premium_emoji('time')} <i>Доступно раз в 24 часа</i>\n"
        f"➖➖➖➖➖➖➖➖➖➖"
    )
    
    await message.answer(text, reply_markup=cat_menu_keyboard())

# ==== Команда /top ====
@dp.message(Command("top"))
async def top_command_handler(message: Message) -> None:
    """Быстрый вывод топа пользователей."""
    top_users = get_top_users(10)
    user_id = message.from_user.id
    user_balance = get_user(user_id).get('balance', 0)
    user_place = get_user_place(user_id)
    
    text = (
        f"{premium_emoji('win')} <b>ТОП ПОЛЬЗОВАТЕЛЕЙ</b>\n"
        f"➖➖➖➖➖➖➖➖➖➖\n\n"
    )
    
    medals = ["🥇", "🥈", "🥉"]
    for i, (uid_str, user_info) in enumerate(top_users):
        uname = user_info.get('username', 'Неизвестно')
        if uname and not uname.startswith('Неизвестно'):
            display_name = f"@{uname}" if not uname.startswith('@') else uname
        else:
            display_name = f"ID {uid_str}"
        
        medal = medals[i] if i < 3 else f"{i+1}."
        balance = user_info.get('balance', 0)
        text += f"{medal} <b>{display_name}</b> — {premium_emoji('balance')} <code>{balance}</code>\n"
    
    text += (
        f"\n➖➖➖➖➖➖➖➖➖➖\n"
        f"{premium_emoji('user')} <b>Ваша позиция:</b> {user_place}\n"
        f"{premium_emoji('balance')} <b>Ваш баланс:</b> <code>{user_balance}</code>\n"
        f"➖➖➖➖➖➖➖➖➖➖"
    )
    
    await message.answer(text, reply_markup=back_button_keyboard())

# ==== Команда /check (только в личке) ====
@dp.message(Command("check"))
async def check_command_handler(message: Message, state: FSMContext) -> None:
    """Создание чека через команду (только в личных сообщениях)."""
    # Проверяем, что команда вызвана в личных сообщениях
    if message.chat.type != ChatType.PRIVATE:
        bot_username = (await bot.get_me()).username
        await message.answer(
            f"{premium_emoji('error')} <b>Команда недоступна в чатах</b>\n\n"
            f"Создавать чеки можно только в личных сообщениях с ботом.\n"
            f"Напишите мне в личку: @{bot_username}"
        )
        return
    
    args = message.text.split()
    if len(args) == 3:
        try:
            amount = int(args[1])
            activations = int(args[2])
            await process_check_creation(message, amount, activations, state)
        except ValueError:
            await message.answer(
                f"{premium_emoji('error')} <b>Неверный формат</b>\n\n"
                f"Используйте: <code>/check сумма количество</code>\n"
                f"Пример: <code>/check 100 5</code>"
            )
    else:
        await message.answer(
            f"{premium_emoji('check')} <b>СОЗДАНИЕ ЧЕКА</b>\n"
            f"➖➖➖➖➖➖➖➖➖➖\n\n"
            f"Введите сумму печенек для чека:",
            reply_markup=back_button_keyboard()
        )
        await state.set_state(CheckStates.waiting_for_amount)

async def process_check_creation(message: Message, amount: int, activations: int, state: FSMContext):
    """Обработка создания чека."""
    user_id = message.from_user.id
    user_data = get_user(user_id)
    
    if user_data['balance'] < amount * activations:
        await message.answer(
            f"{premium_emoji('error')} <b>Недостаточно печенек!</b>\n\n"
            f"Требуется: {amount * activations} 🍪\n"
            f"У вас: {user_data['balance']} 🍪"
        )
        return
    
    user_data['balance'] -= amount * activations
    update_user(user_id, user_data)
    
    check = create_check(user_id, amount, activations)
    
    text = (
        f"{premium_emoji('prize')} <b>ЧЕК СОЗДАН!</b>\n"
        f"➖➖➖➖➖➖➖➖➖➖\n\n"
        f"{premium_emoji('balance')} <b>Сумма:</b> {amount} 🍪\n"
        f"{premium_emoji('users')} <b>Активаций:</b> {activations}\n"
        f"{premium_emoji('check')} <b>Код чека:</b> <code>{check['code']}</code>\n\n"
        f"{premium_emoji('time')} <b>Действует до:</b> {check['expires_at'][:10]}\n\n"
        f"<i>Поделитесь кодом или нажмите кнопку ниже</i>\n"
        f"➖➖➖➖➖➖➖➖➖➖"
    )
    
    await message.answer(text, reply_markup=check_keyboard(check['code']))
    if state:
        await state.clear()

# ==== Команда /bonus ====
@dp.message(Command("bonus"))
async def bonus_command_handler(message: Message) -> None:
    """Обработчик команды /bonus."""
    if message.chat.id != GIVEAWAY_CHAT_ID:
        return
    
    user = message.from_user
    user_id = user.id
    
    can_get, remaining = can_claim_bonus(user_id)
    
    if not can_get:
        hours = remaining // 3600
        minutes = (remaining % 3600) // 60
        seconds = remaining % 60
        
        time_text = ""
        if hours > 0:
            time_text += f"{hours} ч. "
        if minutes > 0:
            time_text += f"{minutes} мин. "
        if seconds > 0 and hours == 0:
            time_text += f"{seconds} сек."
        
        await message.reply(
            f"{premium_emoji('time')} <b>Бонус пока недоступен!</b>\n\n"
            f"{premium_emoji('prize')} Следующий бонус через: <b>{time_text}</b>\n\n"
            f"<i>Возвращайся позже!</i>"
        )
        return
    
    bonus_amount = random.randint(1, 20)
    user_data = get_user(user_id)
    current_balance = user_data.get('balance', 0)
    new_balance = current_balance + bonus_amount
    
    user_data['balance'] = new_balance
    user_data['last_bonus_time'] = datetime.now().isoformat()
    user_data['total_earned'] = user_data.get('total_earned', 0) + bonus_amount
    update_user(user_id, user_data)
    
    await message.reply(
        f"{premium_emoji('prize')} <b>БОНУС ПОЛУЧЕН!</b>\n"
        f"➖➖➖➖➖➖➖➖➖➖\n\n"
        f"{premium_emoji('dice')} Ты получил: <b>{bonus_amount} печенек</b>\n"
        f"{premium_emoji('balance')} Текущий баланс: <b>{new_balance} 🍪</b>\n\n"
        f"{premium_emoji('time')} Следующий бонус через 2 часа\n"
        f"➖➖➖➖➖➖➖➖➖➖"
    )

# ==== Обработчики Inline кнопок ====
@dp.callback_query(F.data == "back_to_main")
async def back_to_main(callback: CallbackQuery):
    """Возврат в главное меню."""
    is_private = callback.message.chat.type == ChatType.PRIVATE
    await callback.message.edit_text(
        text=f"{premium_emoji('rocket')} <b>Главное меню</b>\n\n<i>Выбери нужный раздел:</i>",
        reply_markup=main_menu_keyboard(is_private)
    )
    await callback.answer()

# ---- Котики ----
@dp.callback_query(F.data == "cat_menu")
async def cat_menu(callback: CallbackQuery):
    """Меню котиков."""
    text = (
        f"{premium_emoji('cat')} <b>КОТИКИ - ТВОЙ ИСТОЧНИК РАДОСТИ!</b>\n"
        f"➖➖➖➖➖➖➖➖➖➖\n\n"
        f"{premium_emoji('game')} Нажимай на кнопку и поднимай настроение!\n"
        f"{premium_emoji('time')} <i>Доступно раз в 24 часа</i>\n"
        f"➖➖➖➖➖➖➖➖➖➖"
    )
    await callback.message.edit_text(text, reply_markup=cat_menu_keyboard())
    await callback.answer()

@dp.callback_query(F.data == "get_cat")
async def get_cat(callback: CallbackQuery):
    """Получить котика."""
    user = callback.from_user
    user_id = user.id
    is_private = callback.message.chat.type == ChatType.PRIVATE
    
    can_get, remaining = can_use_cat(user_id)
    
    if not can_get:
        hours = remaining // 3600
        minutes = (remaining % 3600) // 60
        
        time_text = ""
        if hours > 0:
            time_text += f"{hours} ч. "
        if minutes > 0:
            time_text += f"{minutes} мин."
        
        await callback.message.edit_text(
            f"{premium_emoji('time')} <b>Котик пока отдыхает!</b>\n\n"
            f"{premium_emoji('cat')} Следующий котик будет доступен через: <b>{time_text}</b>\n\n"
            f"<i>Возвращайся позже за порцией милоты!</i>",
            reply_markup=back_button_keyboard() if is_private else None
        )
        await callback.answer()
        return
    
    # Обновляем время последнего котика
    user_data = get_user(user_id)
    user_data['last_cat_time'] = datetime.now().isoformat()
    update_user(user_id, user_data)
    
    # Выбираем случайный стикер
    sticker_id = random.choice(CAT_STICKERS)
    
    # Выбираем случайный совет
    tip = random.choice(CAT_TIPS)
    
    # Отправляем стикер
    await bot.send_sticker(callback.message.chat.id, sticker_id)
    
    # Отправляем сообщение с советом
    text = (
        f"{premium_emoji('cat')} <b>Ваш котик на сегодня!</b>\n"
        f"➖➖➖➖➖➖➖➖➖➖\n\n"
        f"{premium_emoji('tip')} <b>Полезный совет:</b>\n"
        f"<blockquote>{tip}</blockquote>\n"
        f"➖➖➖➖➖➖➖➖➖➖"
    )
    
    await callback.message.answer(text, reply_markup=cat_result_keyboard())
    await callback.answer()

# ---- Поддержка ----
@dp.callback_query(F.data == "support_menu")
async def support_menu(callback: CallbackQuery):
    """Меню поддержки (только в личке)."""
    if callback.message.chat.type != ChatType.PRIVATE:
        await callback.answer("❌ Поддержка доступна только в личных сообщениях", show_alert=True)
        return
    
    text = (
        f"{premium_emoji('support')} <b>ТЕХНИЧЕСКАЯ ПОДДЕРЖКА PitaiaTime</b>\n"
        f"➖➖➖➖➖➖➖➖➖➖\n\n"
        f"{premium_emoji('info')} Мы всегда рады помочь вам с любыми вопросами!\n\n"
        f"{premium_emoji('rules')} <b>Как обратиться в поддержку:</b>\n"
        f"1️⃣ Нажми «Создать тикет»\n"
        f"2️⃣ Подробно опиши ситуацию\n"
        f"3️⃣ Приложи скриншоты/фото/видео (если нужно)\n\n"
        f"{premium_emoji('lightning')} <b>Полезные советы:</b>\n"
        f"• Чем подробнее описание — тем быстрее решение\n"
        f"• Скриншоты ускоряют диагностику\n"
        f"• Не дублируй запросы\n"
        f"➖➖➖➖➖➖➖➖➖➖"
    )
    
    await callback.message.edit_text(text, reply_markup=support_menu_keyboard())
    await callback.answer()

@dp.callback_query(F.data == "create_ticket")
async def create_ticket_start(callback: CallbackQuery, state: FSMContext):
    """Начало создания тикета."""
    if callback.message.chat.type != ChatType.PRIVATE:
        await callback.answer("❌ Создание тикетов доступно только в личных сообщениях", show_alert=True)
        return
    
    await callback.message.edit_text(
        f"{premium_emoji('ticket')} <b>СОЗДАНИЕ ТИКЕТА</b>\n"
        f"➖➖➖➖➖➖➖➖➖➖\n\n"
        f"Напишите ваш вопрос подробно:\n"
        f"<i>(можно прикрепить фото/видео/файлы)</i>",
        reply_markup=back_button_keyboard()
    )
    await state.set_state(TicketStates.waiting_for_question)
    await callback.answer()

@dp.message(TicketStates.waiting_for_question)
async def process_ticket_question(message: Message, state: FSMContext):
    """Обработка вопроса в тикете."""
    if message.chat.type != ChatType.PRIVATE:
        await state.clear()
        return
    
    user = message.from_user
    question = message.text or message.caption or "Без текста"
    
    # Если есть медиа, добавляем информацию
    if message.photo:
        question += f"\n[Прикреплено фото]"
    if message.video:
        question += f"\n[Прикреплено видео]"
    if message.document:
        question += f"\n[Прикреплен документ: {message.document.file_name}]"
    
    # Создаем тикет
    ticket = create_ticket(user.id, question)
    
    # Формируем информацию о пользователе (БЕЗ ПРЕМИУМ ЭМОДЗИ ДЛЯ АДМИНОВ)
    user_info = f"@{user.username}" if user.username else f"{user.full_name}"
    user_link = f"<a href='tg://user?id={user.id}'>{user_info}</a>"
    
    # Отправляем уведомление админам (БЕЗ premium_emoji!)
    for admin_id in ADMIN_IDS:
        try:
            admin_text = (
                f"🎫 <b>НОВЫЙ ВОПРОС</b>\n"
                f"➖➖➖➖➖➖➖➖➖➖\n\n"
                f"👤 <b>Пользователь:</b> {user_link}\n"
                f"🆔 <b>ID:</b> <code>{user.id}</code>\n"
                f"📝 <b>Вопрос:</b>\n<blockquote>{question}</blockquote>\n"
                f"⏰ <b>Время:</b> {datetime.now().strftime('%d.%m.%Y %H:%M')}\n"
                f"🎫 <b>Тикет ID:</b> <code>{ticket['id']}</code>\n"
                f"➖➖➖➖➖➖➖➖➖➖"
            )
            
            # Пересылаем медиа, если есть
            if message.photo:
                await bot.send_photo(admin_id, message.photo[-1].file_id, caption=admin_text, reply_markup=admin_ticket_keyboard(ticket['id']))
            elif message.video:
                await bot.send_video(admin_id, message.video.file_id, caption=admin_text, reply_markup=admin_ticket_keyboard(ticket['id']))
            elif message.document:
                await bot.send_document(admin_id, message.document.file_id, caption=admin_text, reply_markup=admin_ticket_keyboard(ticket['id']))
            else:
                await bot.send_message(admin_id, admin_text, reply_markup=admin_ticket_keyboard(ticket['id']))
        except Exception as e:
            logging.error(f"Ошибка отправки уведомления админу {admin_id}: {e}")
    
    # Отвечаем пользователю (С premium_emoji!)
    await message.answer(
        f"{premium_emoji('success')} <b>Ваш вопрос отправлен!</b>\n"
        f"➖➖➖➖➖➖➖➖➖➖\n\n"
        f"{premium_emoji('time')} Ожидайте ответа в ближайшее время.\n"
        f"{premium_emoji('ticket')} Номер тикета: <code>{ticket['id']}</code>\n\n"
        f"<i>Ответ придёт в этот чат</i>\n"
        f"➖➖➖➖➖➖➖➖➖➖",
        reply_markup=back_button_keyboard()
    )
    await state.clear()

@dp.callback_query(F.data.startswith("answer_ticket_"))
async def answer_ticket_start(callback: CallbackQuery, state: FSMContext):
    """Начало ответа на тикет."""
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Не для тебя кнопка", show_alert=True)
        return
    
    ticket_id = callback.data.replace("answer_ticket_", "")
    await state.update_data(ticket_id=ticket_id)
    
    await callback.message.answer(
        f"✍️ <b>Ответ на тикет {ticket_id}</b>\n\n"
        f"Введите текст ответа:"
    )
    await state.set_state(AdminStates.waiting_for_ticket_answer)
    await callback.answer()

@dp.message(AdminStates.waiting_for_ticket_answer)
async def process_ticket_answer(message: Message, state: FSMContext):
    """Обработка ответа на тикет."""
    if not is_admin(message.from_user.id):
        await state.clear()
        return
    
    data = await state.get_data()
    ticket_id = data.get('ticket_id')
    answer_text = message.text
    
    ticket = get_ticket(ticket_id)
    if not ticket:
        await message.answer("❌ Тикет не найден")
        await state.clear()
        return
    
    # Сохраняем ответ
    answer_ticket(ticket_id, answer_text)
    
    # Отправляем ответ пользователю (С premium_emoji!)
    try:
        user_text = (
            f"{premium_emoji('ticket')} <b>ОТВЕТ НА ВАШ ВОПРОС</b>\n"
            f"➖➖➖➖➖➖➖➖➖➖\n\n"
            f"{premium_emoji('support')} <b>Ответ от поддержки:</b>\n"
            f"<blockquote>{answer_text}</blockquote>\n"
            f"➖➖➖➖➖➖➖➖➖➖\n\n"
            f"<i>Если у вас остались вопросы, создайте новый тикет</i>"
        )
        await bot.send_message(ticket['user_id'], user_text)
        await message.answer(f"✅ Ответ отправлен пользователю!")
    except Exception as e:
        await message.answer(f"❌ Ошибка отправки ответа: {e}")
    
    await state.clear()

# ---- Профиль ----
@dp.callback_query(F.data == "profile")
async def show_profile(callback: CallbackQuery):
    """Показывает профиль пользователя."""
    user = callback.from_user
    user_data = get_user(user.id)

    reg_date = datetime.fromisoformat(user_data['registered_at']).strftime("%d.%m.%Y %H:%M")
    balance = user_data.get('balance', 0)
    place = get_user_place(user.id)
    total_earned = user_data.get('total_earned', 0)
    checks_created = user_data.get('checks_created', 0)
    checks_activated = user_data.get('checks_activated', 0)
    tickets_created = user_data.get('tickets_created', 0)

    text = (
        f"{premium_emoji('user')} <b>ПРОФИЛЬ ПОЛЬЗОВАТЕЛЯ</b>\n"
        f"➖➖➖➖➖➖➖➖➖➖\n\n"
        f"{premium_emoji('user')} <b>Никнейм:</b> {user.full_name}\n"
        f"{premium_emoji('min')} <b>ID:</b> <code>{user.id}</code>\n"
        f"{premium_emoji('time')} <b>Регистрация:</b> {reg_date}\n\n"
        f"{premium_emoji('balance')} <b>Текущий баланс:</b> <code>{balance} 🍪</code>\n"
        f"{premium_emoji('stats')} <b>Всего заработано:</b> <code>{total_earned} 🍪</code>\n"
        f"{premium_emoji('win')} <b>Позиция в топе:</b> <code>{place}</code>\n\n"
        f"{premium_emoji('check')} <b>Статистика чеков:</b>\n"
        f"• Создано: {checks_created}\n"
        f"• Активировано: {checks_activated}\n"
        f"{premium_emoji('ticket')} <b>Обращений в поддержку:</b> {tickets_created}\n"
        f"➖➖➖➖➖➖➖➖➖➖"
    )

    await callback.message.edit_text(text, reply_markup=back_button_keyboard())
    await callback.answer()

# ---- Топ ----
@dp.callback_query(F.data == "top")
async def show_top(callback: CallbackQuery):
    """Показывает топ пользователей."""
    user = callback.from_user
    top_users = get_top_users(10)
    balance = get_user(user.id).get('balance', 0)
    place = get_user_place(user.id)

    text = (
        f"{premium_emoji('win')} <b>ТОП ОХОТНИКОВ ЗА ПЕЧЕНЬЕМ</b>\n"
        f"<i>(самые крутые ребята)</i>\n"
        f"➖➖➖➖➖➖➖➖➖➖\n\n"
    )

    medals = ["🥇", "🥈", "🥉", "🏅", "🏅", "🏅", "🏅", "🏅", "🏅", "🏅"]
    for i, (user_id_str, user_info) in enumerate(top_users):
        uname = user_info.get('username', 'Неизвестно')
        if uname and not uname.startswith('Неизвестно'):
            display_name = f"@{uname}" if not uname.startswith('@') else uname
        else:
            display_name = f"ID {user_id_str}"

        text += f"{medals[i]} <b>{i+1}.</b> {display_name} — {premium_emoji('balance')} <code>{user_info.get('balance', 0)}</code>\n"

    text += (
        f"\n➖➖➖➖➖➖➖➖➖➖\n"
        f"{premium_emoji('user')} <b>Ваша позиция:</b> {place}\n"
        f"{premium_emoji('balance')} <b>Ваш баланс:</b> <code>{balance}</code>\n"
        f"➖➖➖➖➖➖➖➖➖➖"
    )

    await callback.message.edit_text(text, reply_markup=back_button_keyboard())
    await callback.answer()

# ---- Помощь ----
@dp.callback_query(F.data == "help")
async def show_help(callback: CallbackQuery):
    """Показывает раздел помощи."""
    is_private = callback.message.chat.type == ChatType.PRIVATE
    bot_username = (await bot.get_me()).username
    
    if is_private:
        text = (
            f"{premium_emoji('info')} <b>РАЗДЕЛ ПОМОЩИ</b>\n"
            f"➖➖➖➖➖➖➖➖➖➖\n\n"
            f"{premium_emoji('prize')} <b>Как получать печеньки?</b>\n"
            f"• Ежечасные раздачи в чате с кнопкой\n"
            f"• Команда <code>/bonus</code> раз в 2 часа\n"
            f"• Активация чеков от других пользователей\n\n"
            f"{premium_emoji('cat')} <b>Котики:</b>\n"
            f"• Команда <code>/cat</code> или кнопка в меню\n"
            f"• Получай милых котиков раз в 24 часа\n"
            f"• Полезные советы для настроения\n\n"
            f"{premium_emoji('check')} <b>Система чеков:</b>\n"
            f"• Создавай чеки на печеньки (только в личке)\n"
            f"• Делись с друзьями\n"
            f"• Указывай количество активаций\n\n"
            f"{premium_emoji('support')} <b>Поддержка:</b>\n"
            f"• Кнопка «Поддержка» в меню\n"
            f"• Создавай тикеты с вопросами\n"
            f"• Получай ответы от администрации\n\n"
            f"{premium_emoji('win')} <b>Топ пользователей:</b>\n"
            f"• В конце месяца топ-10 получают награды\n"
            f"• Следи за рейтингом в разделе 'Топ'\n"
            f"➖➖➖➖➖➖➖➖➖➖"
        )
    else:
        text = (
            f"{premium_emoji('info')} <b>РАЗДЕЛ ПОМОЩИ</b>\n"
            f"➖➖➖➖➖➖➖➖➖➖\n\n"
            f"{premium_emoji('prize')} <b>Как получать печеньки?</b>\n"
            f"• Ежечасные раздачи с кнопкой\n"
            f"• Команда <code>/bonus</code> раз в 2 часа\n\n"
            f"{premium_emoji('cat')} <b>Котики:</b>\n"
            f"• Команда <code>/cat</code>\n"
            f"• Раз в 24 часа\n\n"
            f"{premium_emoji('check')} <b>Чеки и поддержка:</b>\n"
            f"• Для создания чеков напиши в личку: @{bot_username}\n"
            f"• Поддержка доступна только в личке\n\n"
            f"{premium_emoji('win')} <b>Топ пользователей:</b>\n"
            f"• В конце месяца топ-10 получают награды\n"
            f"➖➖➖➖➖➖➖➖➖➖"
        )
    
    await callback.message.edit_text(text, reply_markup=support_keyboard())
    await callback.answer()

# ---- Команды ----
@dp.callback_query(F.data == "commands")
async def show_commands(callback: CallbackQuery):
    """Показывает раздел с командами."""
    is_private = callback.message.chat.type == ChatType.PRIVATE
    bot_username = (await bot.get_me()).username
    
    if is_private:
        text = (
            f"{premium_emoji('rules')} <b>ДОСТУПНЫЕ КОМАНДЫ</b>\n"
            f"➖➖➖➖➖➖➖➖➖➖\n\n"
            f"<b>👤 Основные команды:</b>\n"
            f"• <code>/start</code> — запуск бота и главное меню\n"
            f"• <code>/bonus</code> — получить бонус (раз в 2 часа, только в чате)\n"
            f"• <code>/cat</code> — получить котика (раз в 24 часа)\n"
            f"• <code>/top</code> — топ пользователей\n"
            f"• <code>/check</code> — создать чек на печеньки\n\n"
            f"{premium_emoji('check')} <b>Как создать чек:</b>\n"
            f"• <code>/check 100 5</code> — чек на 100 печенек, 5 активаций\n"
            f"➖➖➖➖➖➖➖➖➖➖"
        )
    else:
        text = (
            f"{premium_emoji('rules')} <b>ДОСТУПНЫЕ КОМАНДЫ</b>\n"
            f"➖➖➖➖➖➖➖➖➖➖\n\n"
            f"<b>👤 Команды в чате:</b>\n"
            f"• <code>/bonus</code> — получить бонус (раз в 2 часа)\n"
            f"• <code>/cat</code> — получить котика (раз в 24 часа)\n"
            f"• <code>/top</code> — топ пользователей\n\n"
            f"{premium_emoji('check')} <b>Для создания чеков</b> напишите мне в личку: @{bot_username}\n"
            f"{premium_emoji('support')} <b>Поддержка</b> тоже только в личке\n"
            f"➖➖➖➖➖➖➖➖➖➖"
        )
    
    await callback.message.edit_text(text, reply_markup=commands_keyboard())
    await callback.answer()

# ---- Информация о командах ----
@dp.callback_query(F.data == "info_bonus")
async def info_bonus(callback: CallbackQuery):
    """Информация о команде /bonus."""
    text = (
        f"{premium_emoji('dice')} <b>КОМАНДА /bonus</b>\n"
        f"➖➖➖➖➖➖➖➖➖➖\n\n"
        f"<b>📌 Описание:</b>\n"
        f"Бонусные печеньки в чате канала\n\n"
        f"<b>⚙️ Параметры:</b>\n"
        f"• {premium_emoji('dice')} <b>Количество:</b> 1-20 печенек\n"
        f"• {premium_emoji('time')} <b>Перезарядка:</b> 2 часа\n"
        f"• {premium_emoji('min')} <b>Где работает:</b> только в чате\n\n"
        f"<b>💬 Пример:</b> <code>/bonus</code>\n\n"
        f"<blockquote>Заходи каждые 2 часа!</blockquote>\n"
        f"➖➖➖➖➖➖➖➖➖➖"
    )
    await callback.message.edit_text(text, reply_markup=commands_keyboard())
    await callback.answer()

@dp.callback_query(F.data == "info_start")
async def info_start(callback: CallbackQuery):
    """Информация о команде /start."""
    text = (
        f"{premium_emoji('user')} <b>КОМАНДА /start</b>\n"
        f"➖➖➖➖➖➖➖➖➖➖\n\n"
        f"<b>📌 Описание:</b>\n"
        f"Запуск бота и регистрация\n\n"
        f"<b>⚙️ Что делает:</b>\n"
        f"• ✅ Регистрирует в системе\n"
        f"• 📊 Показывает меню\n"
        f"• 👤 Обновляет профиль\n\n"
        f"<b>💬 Пример:</b> <code>/start</code>\n"
        f"➖➖➖➖➖➖➖➖➖➖"
    )
    await callback.message.edit_text(text, reply_markup=commands_keyboard())
    await callback.answer()

@dp.callback_query(F.data == "info_top")
async def info_top(callback: CallbackQuery):
    """Информация о команде /top."""
    text = (
        f"{premium_emoji('win')} <b>КОМАНДА /top</b>\n"
        f"➖➖➖➖➖➖➖➖➖➖\n\n"
        f"<b>📌 Описание:</b>\n"
        f"Показывает топ пользователей\n\n"
        f"<b>⚙️ Особенности:</b>\n"
        f"• Топ-10 по балансу\n"
        f"• Работает везде\n"
        f"• Показывает вашу позицию\n\n"
        f"<b>💬 Пример:</b> <code>/top</code>\n"
        f"➖➖➖➖➖➖➖➖➖➖"
    )
    await callback.message.edit_text(text, reply_markup=commands_keyboard())
    await callback.answer()

@dp.callback_query(F.data == "info_check")
async def info_check(callback: CallbackQuery):
    """Информация о команде /check."""
    text = (
        f"{premium_emoji('check')} <b>КОМАНДА /check</b>\n"
        f"➖➖➖➖➖➖➖➖➖➖\n\n"
        f"<b>📌 Описание:</b>\n"
        f"Создание чеков на печеньки (только в личке)\n\n"
        f"<b>⚙️ Формат:</b>\n"
        f"<code>/check [сумма] [активации]</code>\n\n"
        f"<b>💬 Примеры:</b>\n"
        f"• <code>/check 100 5</code> — 5 активаций по 100 🍪\n"
        f"• <code>/check 50 1</code> — 1 активация на 50 🍪\n\n"
        f"<blockquote>Чек действует 7 дней</blockquote>\n"
        f"➖➖➖➖➖➖➖➖➖➖"
    )
    await callback.message.edit_text(text, reply_markup=commands_keyboard())
    await callback.answer()

@dp.callback_query(F.data == "info_cat")
async def info_cat(callback: CallbackQuery):
    """Информация о команде /cat."""
    text = (
        f"{premium_emoji('cat')} <b>КОМАНДА /cat</b>\n"
        f"➖➖➖➖➖➖➖➖➖➖\n\n"
        f"<b>📌 Описание:</b>\n"
        f"Получи порцию милоты и полезный совет!\n\n"
        f"<b>⚙️ Параметры:</b>\n"
        f"• {premium_emoji('cat')} <b>Котик:</b> случайный стикер\n"
        f"• {premium_emoji('tip')} <b>Совет:</b> полезный на день\n"
        f"• {premium_emoji('time')} <b>Перезарядка:</b> 24 часа\n"
        f"• {premium_emoji('min')} <b>Где работает:</b> везде\n\n"
        f"<b>💬 Пример:</b> <code>/cat</code>\n"
        f"➖➖➖➖➖➖➖➖➖➖"
    )
    await callback.message.edit_text(text, reply_markup=commands_keyboard())
    await callback.answer()

# ---- Меню чеков (только в личке) ----
@dp.callback_query(F.data == "checks_menu")
async def checks_menu(callback: CallbackQuery):
    """Меню чеков (только в личных сообщениях)."""
    if callback.message.chat.type != ChatType.PRIVATE:
        await callback.answer("❌ Меню чеков доступно только в личных сообщениях", show_alert=True)
        return
    
    text = (
        f"{premium_emoji('check')} <b>СИСТЕМА ЧЕКОВ</b>\n"
        f"➖➖➖➖➖➖➖➖➖➖\n\n"
        f"{premium_emoji('prize')} Создавай чеки на печеньки и делись с друзьями!\n"
        f"{premium_emoji('users')} Каждый чек можно активировать несколько раз\n\n"
        f"<b>Выбери действие:</b>\n"
        f"➖➖➖➖➖➖➖➖➖➖"
    )
    await callback.message.edit_text(text, reply_markup=checks_menu_keyboard())
    await callback.answer()

@dp.callback_query(F.data == "check_create")
async def check_create_start(callback: CallbackQuery, state: FSMContext):
    """Начало создания чека (только в личке)."""
    if callback.message.chat.type != ChatType.PRIVATE:
        await callback.answer("❌ Создание чеков доступно только в личных сообщениях", show_alert=True)
        return
    
    await callback.message.edit_text(
        f"{premium_emoji('check')} <b>СОЗДАНИЕ ЧЕКА</b>\n"
        f"➖➖➖➖➖➖➖➖➖➖\n\n"
        f"Введите сумму печенек для чека:",
        reply_markup=back_button_keyboard()
    )
    await state.set_state(CheckStates.waiting_for_amount)
    await callback.answer()

@dp.message(CheckStates.waiting_for_amount)
async def process_check_amount(message: Message, state: FSMContext):
    """Обработка суммы чека."""
    if message.chat.type != ChatType.PRIVATE:
        await state.clear()
        return
    
    try:
        amount = int(message.text.strip())
        if amount < 1:
            await message.answer(
                f"{premium_emoji('error')} <b>Ошибка</b>\n\nСумма должна быть больше 0!"
            )
            return
        if amount > 1000000:
            await message.answer(
                f"{premium_emoji('error')} <b>Ошибка</b>\n\nСлишком большая сумма!"
            )
            return
        
        await state.update_data(check_amount=amount)
        await message.answer(
            f"{premium_emoji('check')} <b>СОЗДАНИЕ ЧЕКА</b>\n"
            f"➖➖➖➖➖➖➖➖➖➖\n\n"
            f"Сумма: <b>{amount} 🍪</b>\n\n"
            f"Введите количество активаций:",
            reply_markup=back_button_keyboard()
        )
        await state.set_state(CheckStates.waiting_for_activations)
    except ValueError:
        await message.answer(
            f"{premium_emoji('error')} <b>Ошибка</b>\n\nВведите число!"
        )

@dp.message(CheckStates.waiting_for_activations)
async def process_check_activations(message: Message, state: FSMContext):
    """Обработка количества активаций."""
    if message.chat.type != ChatType.PRIVATE:
        await state.clear()
        return
    
    try:
        activations = int(message.text.strip())
        if activations < 1:
            await message.answer(
                f"{premium_emoji('error')} <b>Ошибка</b>\n\nКоличество активаций должно быть больше 0!"
            )
            return
        if activations > 100:
            await message.answer(
                f"{premium_emoji('error')} <b>Ошибка</b>\n\nМаксимум 100 активаций!"
            )
            return
        
        data = await state.get_data()
        amount = data['check_amount']
        user_id = message.from_user.id
        
        user_data = get_user(user_id)
        if user_data['balance'] < amount * activations:
            await message.answer(
                f"{premium_emoji('error')} <b>Недостаточно печенек!</b>\n\n"
                f"Требуется: {amount * activations} 🍪\n"
                f"У вас: {user_data['balance']} 🍪"
            )
            await state.clear()
            return
        
        user_data['balance'] -= amount * activations
        update_user(user_id, user_data)
        
        check = create_check(user_id, amount, activations)
        
        text = (
            f"{premium_emoji('prize')} <b>ЧЕК СОЗДАН!</b>\n"
            f"➖➖➖➖➖➖➖➖➖➖\n\n"
            f"{premium_emoji('balance')} <b>Сумма:</b> {amount} 🍪\n"
            f"{premium_emoji('users')} <b>Активаций:</b> {activations}\n"
            f"{premium_emoji('check')} <b>Код чека:</b> <code>{check['code']}</code>\n\n"
            f"{premium_emoji('time')} <b>Действует до:</b> {check['expires_at'][:10]}\n\n"
            f"<i>Поделитесь кодом или нажмите кнопку ниже</i>\n"
            f"➖➖➖➖➖➖➖➖➖➖"
        )
        
        await message.answer(text, reply_markup=check_keyboard(check['code']))
        await state.clear()
        
    except ValueError:
        await message.answer(
            f"{premium_emoji('error')} <b>Ошибка</b>\n\nВведите число!"
        )

@dp.callback_query(F.data == "check_my")
async def show_my_checks(callback: CallbackQuery):
    """Показывает чеки пользователя."""
    if callback.message.chat.type != ChatType.PRIVATE:
        await callback.answer("❌ Эта функция доступна только в личных сообщениях", show_alert=True)
        return
    
    user_id = callback.from_user.id
    checks = get_user_checks(user_id)
    
    if not checks:
        await callback.message.edit_text(
            f"{premium_emoji('info')} <b>У вас нет созданных чеков</b>\n\n"
            f"Создайте первый чек в меню!",
            reply_markup=checks_menu_keyboard()
        )
        await callback.answer()
        return
    
    text = f"{premium_emoji('check')} <b>ВАШИ ЧЕКИ</b>\n➖➖➖➖➖➖➖➖➖➖\n\n"
    
    for check in checks[:5]:
        status = "✅ Активен" if check['active'] else "❌ Неактивен"
        text += (
            f"<b>Код:</b> <code>{check['code']}</code>\n"
            f"{premium_emoji('balance')} Сумма: {check['amount']} 🍪\n"
            f"{premium_emoji('users')} Активации: {check['current_activations']}/{check['max_activations']}\n"
            f"Статус: {status}\n"
            f"➖➖➖➖➖➖➖➖➖➖\n"
        )
    
    await callback.message.edit_text(text, reply_markup=checks_menu_keyboard())
    await callback.answer()

# ==== Система чеков - ОБРАБОТКА ТЕКСТОВЫХ СООБЩЕНИЙ ====
@dp.callback_query(F.data.startswith("copy_code_"))
async def copy_code_callback(callback: CallbackQuery):
    """Обработчик кнопки копирования кода."""
    check_code = callback.data.replace("copy_code_", "")
    await callback.answer(
        f"✅ Код скопирован: {check_code}",
        show_alert=False
    )

@dp.message(F.text.regexp(r'^[A-F0-9]{8}$').as_("check_code"))
async def process_check_code_message(message: Message, check_code: str):
    """Обрабатывает сообщения, которые являются кодом чека."""
    user_id = message.from_user.id
    
    # Проверяем существование чека
    checks = load_checks()
    if check_code not in checks:
        await message.reply(
            f"{premium_emoji('error')} <b>Чек не найден!</b>\n\n"
            f"Код <code>{check_code}</code> не существует или был удален."
        )
        return
    
    check = checks[check_code]
    
    # Проверяем статус чека
    if not check.get('active', True):
        await message.reply(
            f"{premium_emoji('error')} <b>Чек уже неактивен!</b>\n\n"
            f"Этот чек больше нельзя активировать."
        )
        return
    
    if check['current_activations'] >= check['max_activations']:
        await message.reply(
            f"{premium_emoji('error')} <b>Чек использован!</b>\n\n"
            f"Все активации этого чека уже использованы."
        )
        return
    
    expires_at = datetime.fromisoformat(check['expires_at'])
    if datetime.now() > expires_at:
        await message.reply(
            f"{premium_emoji('error')} <b>Срок действия чека истек!</b>\n\n"
            f"Чек действовал до {expires_at.strftime('%d.%m.%Y')}"
        )
        return
    
    # Если пользователь уже активировал этот чек
    if user_id in check['activated_by']:
        await message.reply(
            f"{premium_emoji('warning')} <b>Вы уже активировали этот чек!</b>\n\n"
            f"Каждый чек можно активировать только один раз."
        )
        return
    
    # Показываем информацию о чеке с кнопкой активации
    text = (
        f"{premium_emoji('check')} <b>ЧЕК НАЙДЕН!</b>\n"
        f"➖➖➖➖➖➖➖➖➖➖\n\n"
        f"<b>Код чека:</b> <code>{check_code}</code>\n"
        f"{premium_emoji('balance')} <b>Сумма:</b> {check['amount']} 🍪\n"
        f"{premium_emoji('users')} <b>Доступно активаций:</b> {check['max_activations'] - check['current_activations']}\n"
        f"{premium_emoji('time')} <b>Действует до:</b> {check['expires_at'][:10]}\n\n"
        f"<i>Нажмите кнопку ниже, чтобы активировать чек</i>\n"
        f"➖➖➖➖➖➖➖➖➖➖"
    )
    
    await message.reply(text, reply_markup=check_keyboard(check_code))

@dp.message(F.text.lower().contains("чек"))
async def process_check_mention(message: Message):
    """Обрабатывает сообщения, содержащие слово 'чек' и код."""
    text = message.text.upper()
    # Ищем код чека (8 символов: буквы A-F и цифры)
    match = re.search(r'[A-F0-9]{8}', text)
    if match:
        check_code = match.group()
        await process_check_code_message(message, check_code)

@dp.callback_query(F.data.startswith("activate_check_"))
async def activate_check_callback(callback: CallbackQuery):
    """Активация чека."""
    check_code = callback.data.replace("activate_check_", "")
    user_id = callback.from_user.id
    
    result = activate_check_logic(check_code, user_id)
    
    if result["success"]:
        await callback.message.edit_text(
            f"{premium_emoji('prize')} <b>ЧЕК АКТИВИРОВАН!</b>\n"
            f"➖➖➖➖➖➖➖➖➖➖\n\n"
            f"{premium_emoji('balance')} <b>Получено:</b> {result['amount']} 🍪\n"
            f"{premium_emoji('users')} <b>Осталось активаций:</b> {result['remaining']}\n"
            f"➖➖➖➖➖➖➖➖➖➖",
            reply_markup=back_button_keyboard()
        )
        await callback.answer(f"✅ +{result['amount']} печенек!", show_alert=True)
    else:
        reasons = {
            "not_found": "Чек не найден",
            "inactive": "Чек неактивен",
            "expired": "Срок действия чека истек",
            "already_activated": "Вы уже активировали этот чек"
        }
        reason = reasons.get(result["reason"], "Ошибка активации")
        await callback.answer(f"❌ {reason}", show_alert=True)

# ==== Inline режим для быстрого шаринга чеков ====
@dp.inline_query()
async def inline_query_handler(inline_query: types.InlineQuery):
    """Обработка inline запросов."""
    query = inline_query.query.lower()
    
    if not query.startswith("чек"):
        return
    
    parts = query.split()
    if len(parts) < 2:
        return
    
    if len(parts[1]) == 8 and all(c in 'ABCDEF0123456789' for c in parts[1].upper()):
        check_code = parts[1].upper()
        checks = load_checks()
        
        if check_code in checks:
            check = checks[check_code]
            result = InlineQueryResultArticle(
                id=check_code,
                title=f"Чек {check_code}",
                description=f"{check['amount']} 🍪, осталось {check['max_activations'] - check['current_activations']} активаций",
                input_message_content=InputTextMessageContent(
                    message_text=(
                        f"{premium_emoji('check')} <b>ЧЕК НА ПЕЧЕНЬКИ</b>\n"
                        f"➖➖➖➖➖➖➖➖➖➖\n\n"
                        f"<b>Код:</b> <code>{check_code}</code>\n"
                        f"{premium_emoji('balance')} <b>Сумма:</b> {check['amount']} 🍪\n"
                        f"{premium_emoji('users')} <b>Осталось:</b> {check['max_activations'] - check['current_activations']}\n\n"
                        f"<i>Отправь этот код другу или нажми кнопку!</i>"
                    ),
                    parse_mode=ParseMode.HTML
                ),
                reply_markup=check_keyboard(check_code)
            )
            await inline_query.answer([result], cache_time=1)

# ---- Донат ----
@dp.callback_query(F.data == "donate")
async def show_donate(callback: CallbackQuery):
    """Показывает раздел доната."""
    text = (
        f"{premium_emoji('dollar')} <b>ПОДДЕРЖКА ПРОЕКТА</b>\n"
        f"➖➖➖➖➖➖➖➖➖➖\n\n"
        f"{premium_emoji('heart')} Если хочешь поддержать развитие бота,\n"
        f"выбери сумму пожертвования:\n"
        f"➖➖➖➖➖➖➖➖➖➖"
    )
    await callback.message.edit_text(text, reply_markup=donate_keyboard())
    await callback.answer()

@dp.callback_query(F.data.startswith("donate_"))
async def process_donate(callback: CallbackQuery):
    """Обработка выбора суммы доната."""
    amount = callback.data.split("_")[1]
    await callback.message.edit_text(
        f"{premium_emoji('dollar')} <b>ПОДДЕРЖКА ПРОЕКТА</b>\n"
        f"➖➖➖➖➖➖➖➖➖➖\n\n"
        f"✅ Выбрано: <b>{amount} звёзд</b>\n\n"
        f"{premium_emoji('user')} Отправьте подарок на: <code>@Dev_pranik</code>\n\n"
        f"<i>После отправки напишите в поддержку</i>\n"
        f"➖➖➖➖➖➖➖➖➖➖",
        reply_markup=back_button_keyboard()
    )
    await callback.answer()

# ==== Система раздачи печенек ====
active_claims = {}

def generate_claim_id() -> str:
    """Генерирует уникальный ID для раздачи."""
    return str(int(time.time()))

async def send_cookie_giveaway():
    """Отправляет сообщение о раздаче печенек."""
    claim_id = generate_claim_id()
    active_claims[claim_id] = None

    text = (
        f"{premium_emoji('prize')} <b>РАЗДАЧА ПЕЧЕНЬЕК!</b>\n"
        f"➖➖➖➖➖➖➖➖➖➖\n\n"
        f"{premium_emoji('lightning')} <b>Кто первый нажмёт кнопку</b> — получит +5 печенек!\n\n"
        f"{premium_emoji('dice')} <i>Торопись, удача любит смелых!</i>\n"
        f"➖➖➖➖➖➖➖➖➖➖"
    )

    try:
        await bot.send_message(
            GIVEAWAY_CHAT_ID,
            text,
            reply_markup=claim_keyboard(claim_id)
        )
        logging.info(f"Раздача отправлена в чат {GIVEAWAY_CHAT_ID}, ID: {claim_id}")
        
        for admin_id in ADMIN_IDS:
            try:
                await bot.send_message(
                    admin_id,
                    f"✅ <b>Раздача отправлена</b>\n"
                    f"Код: <code>{claim_id}</code>"
                )
            except:
                pass
    except Exception as e:
        logging.error(f"Ошибка отправки раздачи: {e}")

@dp.callback_query(F.data.startswith("claim_"))
async def process_claim(callback: CallbackQuery):
    """Обрабатывает нажатие на кнопку 'Забрать печеньку'."""
    claim_id = callback.data.split("_")[1]
    user_id = callback.from_user.id

    if claim_id not in active_claims:
        await callback.answer("❌ Раздача закончилась", show_alert=True)
        return

    if active_claims[claim_id] is not None:
        await callback.answer("🍪 Печеньку уже забрали", show_alert=True)
        return

    active_claims[claim_id] = user_id
    user_data = get_user(user_id)
    new_balance = user_data.get('balance', 0) + 5
    user_data['balance'] = new_balance
    user_data['total_earned'] = user_data.get('total_earned', 0) + 5
    update_user(user_id, user_data)

    await callback.message.edit_text(
        f"{premium_emoji('prize')} <b>ПОЗДРАВЛЯЮ, {callback.from_user.full_name}!</b>\n"
        f"➖➖➖➖➖➖➖➖➖➖\n\n"
        f"{premium_emoji('dice')} Ты получил <b>+5 печенек</b>!\n"
        f"{premium_emoji('balance')} Баланс: <b>{new_balance} 🍪</b>\n"
        f"➖➖➖➖➖➖➖➖➖➖"
    )
    await callback.answer("✅ +5 печенек!", show_alert=True)

# ==== Админка (БЕЗ ПРЕМИУМ ЭМОДЗИ) ====
def is_admin(user_id: int) -> bool:
    """Проверка, является ли пользователь админом."""
    return user_id in ADMIN_IDS

@dp.message(Command("admin"))
async def admin_panel(message: Message):
    """Панель администратора."""
    if not is_admin(message.from_user.id):
        await message.answer("❌ <b>Доступ запрещён.</b>")
        return

    text = (
        "👑 <b>ПАНЕЛЬ АДМИНИСТРАТОРА</b>\n"
        "➖➖➖➖➖➖➖➖➖➖\n\n"
        "<b>Выберите действие:</b>"
    )
    builder = InlineKeyboardBuilder()
    builder.button(text="📢 Рассылка", callback_data="admin_broadcast")
    builder.button(text="💰 Изменить баланс", callback_data="admin_change_balance")
    builder.button(text="🔄 Сбросить баланс", callback_data="admin_reset_balance")
    builder.button(text="📊 Статистика", callback_data="admin_stats")
    builder.button(text="🍪 Тест раздачи", callback_data="admin_test_giveaway")
    builder.adjust(1)

    await message.answer(text, reply_markup=builder.as_markup())

@dp.callback_query(F.data.startswith("admin_"))
async def admin_actions(callback: CallbackQuery, state: FSMContext):
    """Обработка действий админа."""
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Не для тебя кнопка", show_alert=True)
        return

    action = callback.data

    if action == "admin_broadcast":
        await callback.message.edit_text(
            "📢 <b>Создание рассылки</b>\n\n"
            "Введите текст для рассылки (можно использовать HTML-разметку):"
        )
        await state.set_state(AdminStates.waiting_for_broadcast)
        await callback.answer()

    elif action == "admin_change_balance":
        await callback.message.edit_text(
            "💰 <b>Изменение баланса</b>\n\n"
            "Введите ID пользователя:"
        )
        await state.set_state(AdminStates.waiting_for_user_id_balance)
        await callback.answer()

    elif action == "admin_reset_balance":
        await callback.message.edit_text(
            "🔄 <b>Сброс баланса</b>\n\n"
            "Введите ID пользователя:"
        )
        await state.set_state(AdminStates.waiting_for_user_id_reset)
        await callback.answer()

    elif action == "admin_stats":
        db = get_all_users()
        checks = load_checks()
        tickets = load_tickets()
        total_users = len(db)
        total_cookies = sum(u.get('balance', 0) for u in db.values())
        active_users = sum(1 for u in db.values() if u.get('balance', 0) > 0)
        total_checks = len(checks)
        active_checks = sum(1 for c in checks.values() if c.get('active', False))
        open_tickets = sum(1 for t in tickets.values() if t.get('status') == 'open' and not t.get('answered'))
        
        await callback.message.edit_text(
            f"📊 <b>СТАТИСТИКА БОТА</b>\n"
            f"➖➖➖➖➖➖➖➖➖➖\n\n"
            f"👥 <b>Всего пользователей:</b> <code>{total_users}</code>\n"
            f"👤 <b>Активных:</b> <code>{active_users}</code>\n"
            f"💰 <b>Всего печенек:</b> <code>{total_cookies}</code>\n"
            f"🧾 <b>Всего чеков:</b> <code>{total_checks}</code>\n"
            f"🎁 <b>Активных чеков:</b> <code>{active_checks}</code>\n"
            f"🎫 <b>Открытых тикетов:</b> <code>{open_tickets}</code>\n"
            f"➖➖➖➖➖➖➖➖➖➖",
            reply_markup=back_button_keyboard()
        )
        await callback.answer()

    elif action == "admin_test_giveaway":
        await send_cookie_giveaway()
        await callback.message.edit_text(
            "✅ <b>Тестовая раздача отправлена</b>",
            reply_markup=back_button_keyboard()
        )
        await callback.answer()

# ==== Рассылка с поддержкой кнопок (БЕЗ ПРЕМИУМ ЭМОДЗИ) ====
@dp.message(AdminStates.waiting_for_broadcast)
async def process_broadcast_text(message: Message, state: FSMContext):
    """Обработка текста рассылки."""
    if not is_admin(message.from_user.id):
        await state.clear()
        return

    broadcast_text = message.text
    
    await state.update_data(broadcast_text=broadcast_text)
    
    await message.answer(
        "⚙️ <b>Настройка кнопок рассылки</b>\n\n"
        f"Текст рассылки:\n<blockquote>{broadcast_text}</blockquote>\n\n"
        f"Выберите тип кнопок для рассылки:",
        reply_markup=broadcast_buttons_keyboard()
    )
    await state.set_state(AdminStates.waiting_for_broadcast_buttons)

@dp.callback_query(AdminStates.waiting_for_broadcast_buttons)
async def process_broadcast_buttons(callback: CallbackQuery, state: FSMContext):
    """Обработка выбора кнопок для рассылки."""
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Доступ запрещён", show_alert=True)
        await state.clear()
        return

    action = callback.data
    
    if action == "broadcast_cancel":
        await callback.message.edit_text(
            "ℹ️ <b>Рассылка отменена</b>",
            reply_markup=back_button_keyboard()
        )
        await state.clear()
        await callback.answer()
        return

    data = await state.get_data()
    broadcast_text = data.get('broadcast_text', '')
    
    if action == "broadcast_no_buttons":
        await send_broadcast(callback.message, broadcast_text, None, state)
    
    elif action == "broadcast_one_button":
        await callback.message.edit_text(
            "🔗 <b>Создание кнопки</b>\n\n"
            f"Введите текст и ссылку для кнопки в формате:\n"
            f"<code>Текст кнопки | https://ссылка.ру</code>\n\n"
            f"Пример: <code>Перейти в канал | {CHANNEL_LINK}</code>"
        )
        await state.set_state(AdminStates.waiting_for_broadcast_buttons)
        await state.update_data(button_type="one")
        await callback.answer()
    
    elif action == "broadcast_two_buttons":
        await callback.message.edit_text(
            "🔗 <b>Создание двух кнопок</b>\n\n"
            f"Введите текст и ссылку для каждой кнопки в формате:\n"
            f"<code>Кнопка 1 | ссылка1</code>\n"
            f"<code>Кнопка 2 | ссылка2</code>\n\n"
            f"Пример:\n"
            f"<code>Канал | {CHANNEL_LINK}</code>\n"
            f"<code>Поддержка | {SUPPORT_LINK}</code>"
        )
        await state.set_state(AdminStates.waiting_for_broadcast_buttons)
        await state.update_data(button_type="two")
        await callback.answer()
    
    elif action == "broadcast_three_buttons":
        await callback.message.edit_text(
            "🔗 <b>Создание трех кнопок</b>\n\n"
            f"Введите текст и ссылку для каждой кнопки в формате:\n"
            f"<code>Кнопка 1 | ссылка1</code>\n"
            f"<code>Кнопка 2 | ссылка2</code>\n"
            f"<code>Кнопка 3 | ссылка3</code>\n\n"
            f"Каждая кнопка с новой строки!"
        )
        await state.set_state(AdminStates.waiting_for_broadcast_buttons)
        await state.update_data(button_type="three")
        await callback.answer()

@dp.message(AdminStates.waiting_for_broadcast_buttons)
async def process_broadcast_buttons_text(message: Message, state: FSMContext):
    """Обработка текста с кнопками."""
    if not is_admin(message.from_user.id):
        await state.clear()
        return

    data = await state.get_data()
    button_type = data.get('button_type')
    broadcast_text = data.get('broadcast_text', '')
    
    lines = message.text.strip().split('\n')
    buttons = []
    
    try:
        if button_type == "one" and len(lines) >= 1:
            btn_text, url = lines[0].split('|')
            buttons.append((btn_text.strip(), url.strip()))
        elif button_type == "two" and len(lines) >= 2:
            for line in lines[:2]:
                btn_text, url = line.split('|')
                buttons.append((btn_text.strip(), url.strip()))
        elif button_type == "three" and len(lines) >= 3:
            for line in lines[:3]:
                btn_text, url = line.split('|')
                buttons.append((btn_text.strip(), url.strip()))
        else:
            await message.answer(
                "❌ <b>Ошибка</b>\n\n"
                f"Неверный формат или количество кнопок. Попробуйте снова."
            )
            return
        
        builder = InlineKeyboardBuilder()
        for btn_text, url in buttons:
            builder.button(text=btn_text, url=url)
        builder.adjust(1)
        keyboard = builder.as_markup() if buttons else None
        
        await send_broadcast(message, broadcast_text, keyboard, state)
        
    except Exception as e:
        await message.answer(
            f"❌ <b>Ошибка</b>\n\n"
            f"Неверный формат. Используйте: Текст | https://ссылка\n"
            f"Ошибка: {str(e)}"
        )

async def send_broadcast(message: Message, text: str, keyboard: Optional[InlineKeyboardMarkup], state: FSMContext):
    """Отправляет рассылку всем пользователям."""
    status_msg = await message.answer(
        "📢 <b>Начинаю рассылку...</b>"
    )

    db = get_all_users()
    sent = 0
    failed = 0
    
    for user_id_str in db.keys():
        try:
            await bot.send_message(int(user_id_str), text, reply_markup=keyboard, parse_mode=ParseMode.HTML)
            sent += 1
            if sent % 10 == 0:
                await status_msg.edit_text(
                    f"📢 <b>Рассылка...</b>\n"
                    f"✅ Отправлено: {sent}\n"
                    f"❌ Ошибок: {failed}"
                )
            await asyncio.sleep(0.05)
        except Exception as e:
            failed += 1
            logging.error(f"Ошибка отправки пользователю {user_id_str}: {e}")

    await status_msg.edit_text(
        f"✅ <b>Рассылка завершена</b>\n"
        f"✅ Отправлено: {sent}\n"
        f"❌ Ошибок: {failed}"
    )
    await state.clear()

# Изменение баланса
@dp.message(AdminStates.waiting_for_user_id_balance)
async def process_user_id_for_balance(message: Message, state: FSMContext):
    """Запрос суммы для изменения баланса."""
    try:
        user_id = int(message.text.strip())
        get_user(user_id)
        await state.update_data(target_user_id=user_id)
        await message.answer(
            f"💰 <b>Изменение баланса</b>\n\n"
            f"Пользователь: <code>{user_id}</code>\n"
            f"Введите сумму (+5 или -3):"
        )
        await state.set_state(AdminStates.waiting_for_balance_amount)
    except ValueError:
        await message.answer("❌ <b>Ошибка</b>\n\nНекорректный ID.")

@dp.message(AdminStates.waiting_for_balance_amount)
async def process_balance_amount(message: Message, state: FSMContext):
    """Изменение баланса."""
    try:
        amount = int(message.text.strip())
        data = await state.get_data()
        user_id = data['target_user_id']

        user_data = get_user(user_id)
        current = user_data.get('balance', 0)
        new_balance = max(0, current + amount)
        user_data['balance'] = new_balance
        update_user(user_id, user_data)

        await message.answer(
            f"✅ <b>Баланс изменен</b>\n\n"
            f"Было: {current} 🍪\n"
            f"Стало: {new_balance} 🍪"
        )
    except ValueError:
        await message.answer("❌ <b>Ошибка</b>\n\nНекорректная сумма.")
    finally:
        await state.clear()

# Сброс баланса
@dp.message(AdminStates.waiting_for_user_id_reset)
async def process_reset_balance(message: Message, state: FSMContext):
    """Сброс баланса пользователя."""
    try:
        user_id = int(message.text.strip())
        user_data = get_user(user_id)
        old_balance = user_data.get('balance', 0)
        user_data['balance'] = 0
        update_user(user_id, user_data)
        await message.answer(
            f"✅ <b>Баланс сброшен</b>\n\n"
            f"Было: {old_balance} 🍪"
        )
    except ValueError:
        await message.answer("❌ <b>Ошибка</b>\n\nНекорректный ID.")
    finally:
        await state.clear()

# ==== Планировщик ====
async def scheduled_task():
    """Задача, которая выполняется по расписанию."""
    await send_cookie_giveaway()

async def scheduler():
    """Запуск планировщика для рассылки раз в час."""
    aioschedule.every().hour.at(":00").do(scheduled_task)
    while True:
        await aioschedule.run_pending()
        await asyncio.sleep(1)

# ==== Запуск бота ====
async def on_startup():
    """Действия при запуске."""
    if not os.path.exists(DB_FILE):
        save_db({})
    if not os.path.exists(CHECKS_FILE):
        save_checks({})
    if not os.path.exists(TICKETS_FILE):
        save_tickets({})
    
    try:
        chat = await bot.get_chat(GIVEAWAY_CHAT_ID)
        bot_username = (await bot.get_me()).username
        logging.info(f"✅ Чат для раздач доступен: {chat.title}")
        logging.info(f"✅ Бот: @{bot_username}")
        
        for admin_id in ADMIN_IDS:
            try:
                await bot.send_message(
                    admin_id,
                    f"🚀 <b>Бот запущен!</b>\n\n"
                    f"🐱 Система котиков активна\n"
                    f"🧾 Система чеков активна\n"
                    f"🎫 Система тикетов активна\n"
                    f"🍪 Планировщик раздач запущен\n"
                    f"🔗 Поддержка кнопок в рассылках"
                )
            except:
                pass
    except Exception as e:
        logging.error(f"❌ Ошибка доступа к чату: {e}")
    
    asyncio.create_task(scheduler())
    logging.info("Бот запущен")

async def main():
    """Главная функция."""
    await on_startup()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
