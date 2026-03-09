import asyncio
import logging
import random
from datetime import datetime, timedelta
from typing import Union, Optional

from aiogram import Bot, Dispatcher, types, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    CallbackQuery, Message, FSInputFile
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.storage.memory import MemoryStorage

# Для рассылки по расписанию
import aioschedule

# Для работы с базой данных (используем простой JSON)
import json
import os

# Конфигурация
BOT_TOKEN = "8729608216:AAH3u-dH3So6B96MAqVDospaiTATrzcekQo"
ADMIN_IDS = [7313407194]  # Список админов
CHANNEL_LINK = "https://t.me/+j5plVfjrsrY4MWJi"  # Ссылка на чат
SUPPORT_LINK = "t.me/qwhatss"  # Ссылка на поддержку
GIVEAWAY_CHAT_ID = -1003720079599  # ID чата для раздач

# Файл базы данных
DB_FILE = "users_db.json"

# Настройка логирования
logging.basicConfig(level=logging.INFO)

# Инициализация бота и диспетчера
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# ==== Работа с базой данных (простая JSON "БД") ====
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

def get_user(user_id: int) -> dict:
    """Возвращает данные пользователя или создает нового."""
    db = load_db()
    user_id_str = str(user_id)
    if user_id_str not in db:
        # Новый пользователь
        db[user_id_str] = {
            "balance": 0,
            "registered_at": datetime.now().isoformat(),
            "last_claim_time": None,  # Для отслеживания последнего получения печеньки
            "last_bonus_time": None,  # Для отслеживания последнего получения бонуса
            "username": None
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
    # Сортируем по балансу (по убыванию) и берем первых limit
    sorted_users = sorted(db.items(), key=lambda item: item[1].get('balance', 0), reverse=True)
    return sorted_users[:limit]

def get_user_place(user_id: int) -> int:
    """Возвращает место пользователя в топе."""
    db = load_db()
    sorted_users = sorted(db.items(), key=lambda item: item[1].get('balance', 0), reverse=True)
    for index, (uid, _) in enumerate(sorted_users):
        if int(uid) == user_id:
            return index + 1
    return 0  # Не найден

def can_claim_bonus(user_id: int) -> tuple[bool, Optional[int]]:
    """
    Проверяет, может ли пользователь получить бонус.
    Возвращает (можно ли получить, сколько секунд осталось до следующего бонуса)
    """
    user_data = get_user(user_id)
    last_bonus = user_data.get('last_bonus_time')
    
    if not last_bonus:
        return True, 0
    
    last_bonus_time = datetime.fromisoformat(last_bonus)
    time_diff = datetime.now() - last_bonus_time
    
    # Бонус можно получать раз в 2 часа (7200 секунд)
    cooldown = 7200  # 2 часа в секундах
    elapsed = time_diff.total_seconds()
    
    if elapsed >= cooldown:
        return True, 0
    else:
        remaining = int(cooldown - elapsed)
        return False, remaining

# ==== FSM для админки (рассылка) ====
class AdminStates(StatesGroup):
    waiting_for_broadcast = State()  # Ждем текст рассылки
    waiting_for_user_id_balance = State()  # Ждем ID для изменения баланса
    waiting_for_balance_amount = State()  # Ждем сумму изменения
    waiting_for_user_id_reset = State()  # Ждем ID для сброса

# ==== Генерация клавиатур (Inline) ====
def main_menu_keyboard():
    """Главное меню (5 кнопок)."""
    builder = InlineKeyboardBuilder()
    builder.button(text="👤 Профиль", callback_data="profile")
    builder.button(text="🏆 Топ", callback_data="top")
    builder.button(text="❓ Помощь", callback_data="help")
    builder.button(text="💎 Донат", callback_data="donate")
    builder.button(text="📋 Команды", callback_data="commands")
    builder.adjust(2, 2, 1)  # по 2, 2 и 1 кнопка в ряд
    return builder.as_markup()

def back_button_keyboard():
    """Клавиатура с кнопкой 'Назад'."""
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 Назад", callback_data="back_to_main")
    return builder.as_markup()

def donate_keyboard():
    """Клавиатура для доната (звезды)."""
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
    builder.button(text="🍪 /bonus", callback_data="info_bonus")
    builder.button(text="👤 /start", callback_data="info_start")
    builder.button(text="🔙 Назад", callback_data="back_to_main")
    builder.adjust(2, 1)
    return builder.as_markup()

# ==== Команда /start ====
@dp.message(CommandStart())
async def command_start_handler(message: Message) -> None:
    """Обработчик команды /start."""
    user = message.from_user
    # Регистрируем пользователя или обновляем его username
    user_data = get_user(user.id)
    user_data['username'] = user.username or user.full_name
    update_user(user.id, user_data)

    # Красивое приветствие
    text = (
        f"🥰 <b>Приветик, {user.full_name}!</b>\n\n"
        f"➖➖➖➖➖➖➖➖➖➖\n\n"
        f"🐾 <b>Я - бот для раздачи печенек</b> за активность в нашем "
        f"<a href='{CHANNEL_LINK}'>Telegram канале</a>.\n\n"
        f"🍪 <b>В конце каждого месяца</b> подводятся итоги, а топ-10 охотников "
        f"получают крутые вознаграждения на нашем сервере!\n\n"
        f"🎯 <b>Команды бота:</b>\n"
        f"• <code>/bonus</code> — получить бонусные печеньки (раз в 2 часа)\n"
        f"➖➖➖➖➖➖➖➖➖➖\n\n"
        f"😎 <b>Вперед на Охоту за Печеньками!</b>\n"
        f"<blockquote>Покажи всем, кто здесь BOSS!</blockquote>"
    )

    await message.answer(text, reply_markup=main_menu_keyboard(), disable_web_page_preview=True)

# ==== Команда /bonus (только в групповом чате) ====
@dp.message(Command("bonus"))
async def bonus_command_handler(message: Message) -> None:
    """Обработчик команды /bonus - выдача случайного бонуса раз в 2 часа."""
    # Проверяем, что команда вызвана в нужном чате
    if message.chat.id != GIVEAWAY_CHAT_ID:
        return  # Игнорируем команду в других чатах
    
    user = message.from_user
    user_id = user.id
    
    # Проверяем, можно ли получить бонус
    can_get, remaining = can_claim_bonus(user_id)
    
    if not can_get:
        # Форматируем время ожидания
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
            f"⏳ <b>Бонус пока недоступен!</b>\n\n"
            f"🍪 Ты уже получал бонус недавно.\n"
            f"📅 Следующий бонус будет доступен через: <b>{time_text}</b>\n\n"
            f"<i>Возвращайся позже и забирай свою печеньку!</i>"
        )
        return
    
    # Генерируем случайное количество печенек от 1 до 20
    bonus_amount = random.randint(1, 20)
    
    # Обновляем баланс и время последнего бонуса
    user_data = get_user(user_id)
    current_balance = user_data.get('balance', 0)
    new_balance = current_balance + bonus_amount
    
    user_data['balance'] = new_balance
    user_data['last_bonus_time'] = datetime.now().isoformat()
    update_user(user_id, user_data)
    
    # Отправляем сообщение о получении бонуса
    await message.reply(
        f"🎉 <b>БОНУС ПОЛУЧЕН!</b>\n\n"
        f"🍪 Ты получил: <b>{bonus_amount} печенек</b>\n"
        f"💰 Текущий баланс: <b>{new_balance} 🍪</b>\n\n"
        f"📅 Следующий бонус будет доступен через 2 часа.\n"
        f"<blockquote>Не забывай заходить за новыми печеньками!</blockquote>"
    )
    
    # Уведомляем админов о получении бонуса
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(
                admin_id,
                f"🎁 <b>Бонус получен!</b>\n\n"
                f"👤 Пользователь: {user.full_name}\n"
                f"🆔 ID: <code>{user_id}</code>\n"
                f"🍪 Получил: {bonus_amount} печенек\n"
                f"💰 Текущий баланс: {new_balance} 🍪"
            )
        except:
            pass

# ==== Обработчики Inline кнопок (Callback) ====
@dp.callback_query(F.data == "back_to_main")
async def back_to_main(callback: CallbackQuery):
    """Возврат в главное меню."""
    await callback.message.edit_text(
        text="🥰 <b>Главное меню</b>\n\n<i>Выбери нужный раздел:</i>",
        reply_markup=main_menu_keyboard()
    )
    await callback.answer()

# ---- Профиль ----
@dp.callback_query(F.data == "profile")
async def show_profile(callback: CallbackQuery):
    """Показывает профиль пользователя."""
    user = callback.from_user
    user_data = get_user(user.id)

    # Дата регистрации
    reg_date = datetime.fromisoformat(user_data['registered_at']).strftime("%d.%m.%Y %H:%M")
    balance = user_data.get('balance', 0)
    place = get_user_place(user.id)

    text = (
        f"⭐ <b>ПРОФИЛЬ ПОЛЬЗОВАТЕЛЯ</b>\n"
        f"➖➖➖➖➖➖➖➖➖➖\n\n"
        f"👤 <b>Никнейм:</b> {user.full_name}\n"
        f"📱 <b>ID:</b> <code>{user.id}</code>\n"
        f"🗓 <b>Регистрация:</b> {reg_date}\n\n"
        f"💰 <b>В твоем мешке:</b> <code>{balance} 🍪</code>\n"
        f"📊 <b>Позиция в топе:</b> <code>{place} место</code>\n"
        f"➖➖➖➖➖➖➖➖➖➖"
    )

    await callback.message.edit_text(text, reply_markup=back_button_keyboard())
    await callback.answer()

# ---- Топ ----
@dp.callback_query(F.data == "top")
async def show_top(callback: CallbackQuery):
    """Показывает топ пользователей."""
    user = callback.from_user
    top_users = get_top_users(5)  # Берем топ-5
    balance = get_user(user.id).get('balance', 0)
    place = get_user_place(user.id)

    text = (
        f"🏆 <b>ТОП ОХОТНИКОВ ЗА ПЕЧЕНЬЕМ</b>\n"
        f"<i>(самые крутые ребята)</i>\n"
        f"➖➖➖➖➖➖➖➖➖➖\n\n"
    )

    medals = ["🥇", "🥈", "🥉", "🏅", "🏅"]
    for i, (user_id_str, user_info) in enumerate(top_users):
        # Пытаемся получить имя пользователя
        uname = user_info.get('username', 'Неизвестно')
        # Если это username (без @), то делаем ссылку
        if uname and not uname.startswith('Неизвестно'):
            display_name = f"@{uname}" if not uname.startswith('@') else uname
        else:
            display_name = f"ID {user_id_str}"

        text += f"{medals[i]} <b>{i+1} место:</b> {display_name} — <code>{user_info.get('balance', 0)} 🍪</code>\n"

    text += (
        f"\n➖➖➖➖➖➖➖➖➖➖\n"
        f"💰 <b>В твоем мешке:</b> <code>{balance} 🍪</code>\n"
        f"📊 <b>Твоя позиция:</b> <code>{place} место</code>\n"
        f"➖➖➖➖➖➖➖➖➖➖"
    )

    await callback.message.edit_text(text, reply_markup=back_button_keyboard())
    await callback.answer()

# ---- Помощь ----
@dp.callback_query(F.data == "help")
async def show_help(callback: CallbackQuery):
    """Показывает раздел помощи."""
    text = (
        f"❓ <b>РАЗДЕЛ ПОМОЩИ</b>\n"
        f"➖➖➖➖➖➖➖➖➖➖\n\n"
        f"<b>Как получать печеньки?</b>\n"
        f"🍪 Печеньки выдаются каждый час в нашем канале.\n"
        f"• Жми кнопку <b>'Забрать печеньку!'</b>\n"
        f"• Будь первым — получи +5 печенек!\n\n"
        f"🎁 <b>Бонусная система:</b>\n"
        f"• Введи команду <code>/bonus</code> в чате\n"
        f"• Получай от 1 до 20 печенек раз в 2 часа\n\n"
        f"📊 <b>Топ пользователей:</b>\n"
        f"• В конце месяца топ-10 получают награды\n"
        f"• Следи за своим рейтингом в разделе 'Топ'\n"
        f"➖➖➖➖➖➖➖➖➖➖"
    )
    await callback.message.edit_text(text, reply_markup=support_keyboard())
    await callback.answer()

# ---- Команды ----
@dp.callback_query(F.data == "commands")
async def show_commands(callback: CallbackQuery):
    """Показывает раздел с командами."""
    text = (
        f"📋 <b>ДОСТУПНЫЕ КОМАНДЫ</b>\n"
        f"➖➖➖➖➖➖➖➖➖➖\n\n"
        f"<b>👤 Основные команды:</b>\n"
        f"• <code>/start</code> — запуск бота и главное меню\n"
        f"• <code>/bonus</code> — получить бонус (раз в 2 часа, только в чате)\n\n"
        f"<b>👑 Админ-команды:</b>\n"
        f"• <code>/admin</code> — панель администратора\n\n"
        f"<b>💡 Как использовать /bonus:</b>\n"
        f"• Команда работает только в чате канала\n"
        f"• Дает от 1 до 20 печенек случайно\n"
        f"• Доступна раз в 2 часа для каждого\n"
        f"➖➖➖➖➖➖➖➖➖➖"
    )
    await callback.message.edit_text(text, reply_markup=commands_keyboard())
    await callback.answer()

@dp.callback_query(F.data == "info_bonus")
async def info_bonus(callback: CallbackQuery):
    """Подробная информация о команде /bonus."""
    text = (
        f"🍪 <b>КОМАНДА /bonus</b>\n"
        f"➖➖➖➖➖➖➖➖➖➖\n\n"
        f"<b>📌 Описание:</b>\n"
        f"Команда для получения бонусных печенек в чате канала.\n\n"
        f"<b>⚙️ Параметры:</b>\n"
        f"• 🎲 <b>Количество:</b> от 1 до 20 печенек (случайно)\n"
        f"• ⏰ <b>Перезарядка:</b> 2 часа\n"
        f"• 📍 <b>Где работает:</b> только в чате канала\n\n"
        f"<b>💬 Пример использования:</b>\n"
        f"<code>/bonus</code> — ввести в чате канала\n\n"
        f"<blockquote>Не забывай заходить каждые 2 часа за новой порцией печенек!</blockquote>\n"
        f"➖➖➖➖➖➖➖➖➖➖"
    )
    await callback.message.edit_text(text, reply_markup=commands_keyboard())
    await callback.answer()

@dp.callback_query(F.data == "info_start")
async def info_start(callback: CallbackQuery):
    """Подробная информация о команде /start."""
    text = (
        f"👤 <b>КОМАНДА /start</b>\n"
        f"➖➖➖➖➖➖➖➖➖➖\n\n"
        f"<b>📌 Описание:</b>\n"
        f"Основная команда для запуска бота и регистрации пользователя.\n\n"
        f"<b>⚙️ Что делает:</b>\n"
        f"• ✅ Регистрирует тебя в системе\n"
        f"• 📊 Показывает главное меню\n"
        f"• 👤 Обновляет твой профиль\n\n"
        f"<b>💬 Пример использования:</b>\n"
        f"<code>/start</code> — ввести в личных сообщениях с ботом\n\n"
        f"<blockquote>После /start ты можешь пользоваться всеми функциями бота!</blockquote>\n"
        f"➖➖➖➖➖➖➖➖➖➖"
    )
    await callback.message.edit_text(text, reply_markup=commands_keyboard())
    await callback.answer()

# ---- Донат ----
@dp.callback_query(F.data == "donate")
async def show_donate(callback: CallbackQuery):
    """Показывает раздел доната."""
    text = (
        f"💎 <b>ПОДДЕРЖКА ПРОЕКТА</b>\n"
        f"➖➖➖➖➖➖➖➖➖➖\n\n"
        f"❤️ Если тебе понравился бот и ты хочешь поддержать его развитие, "
        f"можешь сделать добровольное пожертвование.\n\n"
        f"🙃 <b>Выбери желаемую сумму:</b>\n"
        f"➖➖➖➖➖➖➖➖➖➖"
    )
    await callback.message.edit_text(text, reply_markup=donate_keyboard())
    await callback.answer()

@dp.callback_query(F.data.startswith("donate_"))
async def process_donate(callback: CallbackQuery):
    """Обработка выбора суммы доната."""
    amount = callback.data.split("_")[1]
    await callback.message.edit_text(
        f"💎 <b>ПОДДЕРЖКА ПРОЕКТА</b>\n"
        f"➖➖➖➖➖➖➖➖➖➖\n\n"
        f"✅ Выбрано: <b>{amount} звёзд</b>\n\n"
        f"📤 Отправьте подарок на пользователя: <code>@Dev_pranik</code>\n\n"
        f"<i>После отправки звезд напишите в поддержку для подтверждения и получения бонусов!</i>\n"
        f"➖➖➖➖➖➖➖➖➖➖",
        reply_markup=back_button_keyboard()
    )
    await callback.answer()

# ==== Система раздачи печенек (по расписанию) ====
# Хранилище активных раздач: {claim_id: claimed_user_id}
active_claims = {}

def generate_claim_id() -> str:
    """Генерирует уникальный ID для раздачи."""
    import time
    return str(int(time.time()))

async def send_cookie_giveaway():
    """Отправляет сообщение о раздаче печенек в указанный чат."""
    claim_id = generate_claim_id()
    active_claims[claim_id] = None  # Пока никто не забрал

    text = (
        f"🍪 <b>РАЗДАЧА ПЕЧЕНЬЕК!</b>\n"
        f"➖➖➖➖➖➖➖➖➖➖\n\n"
        f"🔥 <b>Кто первый нажмёт кнопку</b> — тот получит +5 печенек!\n\n"
        f"⚡️ <i>Торопись, удача любит смелых!</i>\n"
        f"➖➖➖➖➖➖➖➖➖➖"
    )

    try:
        # Отправляем раздачу в указанный чат
        await bot.send_message(
            GIVEAWAY_CHAT_ID,
            text,
            reply_markup=claim_keyboard(claim_id)
        )
        logging.info(f"Раздача отправлена в чат {GIVEAWAY_CHAT_ID}, ID: {claim_id}")
        
        # Также уведомляем админов об успешной отправке
        for admin_id in ADMIN_IDS:
            try:
                await bot.send_message(
                    admin_id,
                    f"✅ <b>Раздача успешно отправлена</b>\n"
                    f"📋 ID раздачи: <code>{claim_id}</code>\n"
                    f"📍 Чат: <code>{GIVEAWAY_CHAT_ID}</code>"
                )
            except:
                pass
                
    except Exception as e:
        error_text = f"❌ Ошибка при отправке раздачи в чат {GIVEAWAY_CHAT_ID}: {e}"
        logging.error(error_text)
        
        # Уведомляем админов об ошибке
        for admin_id in ADMIN_IDS:
            try:
                await bot.send_message(admin_id, f"❌ <b>Ошибка раздачи</b>\n\n{error_text}")
            except:
                pass

@dp.callback_query(F.data.startswith("claim_"))
async def process_claim(callback: CallbackQuery):
    """Обрабатывает нажатие на кнопку 'Забрать печеньку'."""
    claim_id = callback.data.split("_")[1]
    user_id = callback.from_user.id

    # Проверяем, существует ли такая раздача и не забрана ли она
    if claim_id not in active_claims:
        await callback.answer("❌ Эта раздача уже закончилась или недействительна.", show_alert=True)
        return

    if active_claims[claim_id] is not None:
        # Кто-то уже забрал
        await callback.answer("🍪 К сожалению, печеньку уже забрали. Повезёт в следующий раз!", show_alert=True)
        return

    # Забираем печеньку
    active_claims[claim_id] = user_id
    user_data = get_user(user_id)
    new_balance = user_data.get('balance', 0) + 5
    user_data['balance'] = new_balance
    update_user(user_id, user_data)

    await callback.message.edit_text(
        f"🎉 <b>ПОЗДРАВЛЯЮ, {callback.from_user.full_name}!</b>\n"
        f"➖➖➖➖➖➖➖➖➖➖\n\n"
        f"🍪 Ты успел первым и получил <b>+5 печенек</b>!\n"
        f"💰 Теперь в твоём мешке: <b>{new_balance} 🍪</b>\n"
        f"➖➖➖➖➖➖➖➖➖➖"
    )
    await callback.answer("✅ Ты получил 5 печенек!", show_alert=True)
    
    # Уведомляем админов о том, кто получил печеньку
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(
                admin_id,
                f"🍪 <b>Печеньку получил!</b>\n\n"
                f"👤 Пользователь: {callback.from_user.full_name}\n"
                f"🆔 ID: <code>{user_id}</code>\n"
                f"💰 Текущий баланс: {new_balance} 🍪"
            )
        except:
            pass

# ==== Админка ====
def is_admin(user_id: int) -> bool:
    """Проверка, является ли пользователь админом."""
    return user_id in ADMIN_IDS

@dp.message(Command("admin"))
async def admin_panel(message: Message):
    """Панель администратора."""
    if not is_admin(message.from_user.id):
        await message.answer("⛔ <b>Доступ запрещён.</b>\n\n<i>Эта команда только для администраторов.</i>")
        return

    text = (
        f"👑 <b>ПАНЕЛЬ АДМИНИСТРАТОРА</b>\n"
        f"➖➖➖➖➖➖➖➖➖➖\n\n"
        f"<b>Выберите действие:</b>\n"
        f"➖➖➖➖➖➖➖➖➖➖"
    )
    builder = InlineKeyboardBuilder()
    builder.button(text="📢 Сделать рассылку", callback_data="admin_broadcast")
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
            "Введите текст для рассылки всем пользователям:\n"
            "<i>(можно использовать HTML-разметку)</i>"
        )
        await state.set_state(AdminStates.waiting_for_broadcast)
        await callback.answer()

    elif action == "admin_change_balance":
        await callback.message.edit_text(
            "💰 <b>Изменение баланса</b>\n\n"
            "Введите ID пользователя, которому хотите изменить баланс:"
        )
        await state.set_state(AdminStates.waiting_for_user_id_balance)
        await callback.answer()

    elif action == "admin_reset_balance":
        await callback.message.edit_text(
            "🔄 <b>Сброс баланса</b>\n\n"
            "Введите ID пользователя для сброса баланса:"
        )
        await state.set_state(AdminStates.waiting_for_user_id_reset)
        await callback.answer()

    elif action == "admin_stats":
        db = get_all_users()
        total_users = len(db)
        total_cookies = sum(u.get('balance', 0) for u in db.values())
        avg_cookies = total_cookies / max(total_users, 1)
        
        # Подсчет пользователей с балансом > 0
        active_users = sum(1 for u in db.values() if u.get('balance', 0) > 0)
        
        await callback.message.edit_text(
            f"📊 <b>СТАТИСТИКА БОТА</b>\n"
            f"➖➖➖➖➖➖➖➖➖➖\n\n"
            f"👥 <b>Всего пользователей:</b> <code>{total_users}</code>\n"
            f"✨ <b>Активных пользователей:</b> <code>{active_users}</code>\n"
            f"🍪 <b>Всего печенек:</b> <code>{total_cookies}</code>\n"
            f"📈 <b>Среднее печенек:</b> <code>{avg_cookies:.1f}</code>\n"
            f"➖➖➖➖➖➖➖➖➖➖",
            reply_markup=back_button_keyboard()
        )
        await callback.answer()

    elif action == "admin_test_giveaway":
        await send_cookie_giveaway()  # Отправляем тестовую раздачу
        await callback.message.edit_text(
            f"✅ <b>Тестовая раздача отправлена</b>\n\n"
            f"📍 Чат: <code>{GIVEAWAY_CHAT_ID}</code>\n"
            f"➖➖➖➖➖➖➖➖➖➖",
            reply_markup=back_button_keyboard()
        )
        await callback.answer()

    else:
        await callback.answer()

# Рассылка
@dp.message(AdminStates.waiting_for_broadcast)
async def process_broadcast(message: Message, state: FSMContext):
    """Обработка текста рассылки и отправка."""
    if not is_admin(message.from_user.id):
        await state.clear()
        return

    broadcast_text = message.text
    status_msg = await message.answer(
        f"📢 <b>Начинаю рассылку...</b>\n\n"
        f"<b>Текст:</b>\n<blockquote>{broadcast_text}</blockquote>"
    )

    db = get_all_users()
    sent = 0
    failed = 0
    for user_id_str in db.keys():
        try:
            await bot.send_message(int(user_id_str), broadcast_text)
            sent += 1
            if sent % 10 == 0:  # Обновляем статус каждые 10 отправок
                await status_msg.edit_text(
                    f"📢 <b>Рассылка в процессе...</b>\n\n"
                    f"✅ Отправлено: <code>{sent}</code>\n"
                    f"❌ Ошибок: <code>{failed}</code>"
                )
            await asyncio.sleep(0.05)  # Небольшая задержка, чтобы не спамить
        except Exception as e:
            failed += 1
            logging.error(f"Не удалось отправить пользователю {user_id_str}: {e}")

    await status_msg.edit_text(
        f"📢 <b>Рассылка завершена</b>\n\n"
        f"✅ <b>Успешно отправлено:</b> <code>{sent}</code>\n"
        f"❌ <b>Ошибок доставки:</b> <code>{failed}</code>"
    )
    await state.clear()

# Изменение баланса
@dp.message(AdminStates.waiting_for_user_id_balance)
async def process_user_id_for_balance(message: Message, state: FSMContext):
    """Запрос суммы для изменения баланса."""
    try:
        user_id = int(message.text.strip())
        # Проверяем, есть ли такой пользователь
        get_user(user_id)  # Создаст, если нет
        await state.update_data(target_user_id=user_id)
        await message.answer(
            f"💰 <b>Изменение баланса</b>\n\n"
            f"🆔 Пользователь: <code>{user_id}</code>\n"
            f"Введите сумму изменения (например: <code>+5</code> или <code>-3</code>):"
        )
        await state.set_state(AdminStates.waiting_for_balance_amount)
    except ValueError:
        await message.answer("❌ <b>Ошибка</b>\n\nНекорректный ID. Введите число.")

@dp.message(AdminStates.waiting_for_balance_amount)
async def process_balance_amount(message: Message, state: FSMContext):
    """Изменение баланса."""
    try:
        amount = int(message.text.strip())
        data = await state.get_data()
        user_id = data['target_user_id']

        user_data = get_user(user_id)
        current = user_data.get('balance', 0)
        new_balance = current + amount
        if new_balance < 0:
            new_balance = 0
        user_data['balance'] = new_balance
        update_user(user_id, user_data)

        await message.answer(
            f"✅ <b>Баланс изменен</b>\n\n"
            f"👤 Пользователь: <code>{user_id}</code>\n"
            f"📊 Было: <code>{current} 🍪</code>\n"
            f"📈 Стало: <code>{new_balance} 🍪</code>"
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
            f"👤 Пользователь: <code>{user_id}</code>\n"
            f"📊 Предыдущий баланс: <code>{old_balance} 🍪</code>"
        )
    except ValueError:
        await message.answer("❌ <b>Ошибка</b>\n\nНекорректный ID.")
    finally:
        await state.clear()

# ==== Планировщик ====
async def scheduler():
    """Запуск планировщика для рассылки раз в час."""
    aioschedule.every().hour.at(":00").do(send_cookie_giveaway)  # Каждый час в 00 минут
    # Для теста можно чаще, например, каждые 10 минут:
    # aioschedule.every(10).minutes.do(send_cookie_giveaway)
    while True:
        await aioschedule.run_pending()
        await asyncio.sleep(1)

# ==== Запуск бота ====
async def on_startup():
    """Действия при запуске."""
    # Создаем базу, если нет
    if not os.path.exists(DB_FILE):
        save_db({})
    
    # Проверяем доступность чата для раздач
    try:
        chat = await bot.get_chat(GIVEAWAY_CHAT_ID)
        logging.info(f"✅ Чат для раздач доступен: {chat.title}")
        
        # Отправляем уведомление админам о запуске
        for admin_id in ADMIN_IDS:
            try:
                await bot.send_message(
                    admin_id,
                    f"🚀 <b>Бот успешно запущен!</b>\n\n"
                    f"📊 <b>Статус:</b>\n"
                    f"• Чат для раздач: <code>{chat.title}</code>\n"
                    f"• Планировщик: активен\n"
                    f"• База данных: загружена"
                )
            except:
                pass
    except Exception as e:
        logging.error(f"❌ Не удалось получить доступ к чату {GIVEAWAY_CHAT_ID}: {e}")
        logging.error("Убедитесь, что бот добавлен в чат и является администратором!")
    
    # Запускаем планировщик в фоне
    asyncio.create_task(scheduler())
    logging.info("Бот запущен и планировщик активен.")

async def main():
    """Главная функция."""
    await on_startup()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
