import asyncio
import logging
import random
from datetime import datetime
from typing import Union

from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (InlineKeyboardButton, InlineKeyboardMarkup,
                           ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.client.default import DefaultBotProperties
import sqlite3

# Настройка логирования
logging.basicConfig(level=logging.INFO)

# Токен бота
BOT_TOKEN = "7734038463:AAHklhMrdCy-ggN97vd85DhmKt10za9fqe4"
ADMIN_ID = 7313407194

# Премиум эмодзи (ТОЛЬКО ДЛЯ ТЕКСТА, НЕ ДЛЯ КНОПОК!)
PREMIUM_EMOJIS = {
    "rocket": "5377336433692412420",
    "dollar": "5377852667286559564",
    "dice": "5377346496800786271",
    "transfer": "5377720025811555309",
    "lightning": "5375469677696815127",
    "casino": "5969709082049779216",
    "balance": "5262509177363787445",
    "withdraw": "5226731292334235524",
    "deposit": "5226731292334235524",
    "game": "5258508428212445001",
    "mine": "4979035365823219688",
    "win": "5436386989857320953",
    "lose": "4979035365823219688",
    "prize": "5323761960829862762",
    "user": "5168063997575956782",
    "stats": "5231200819986047254",
    "time": "5258419835922030550",
    "min": "5447183459602669338",
    "card": "5902056028513505203",
    "rules": "5258328383183396223",
    "info": "5258334872878980409",
    "back": "5877629862306385808",
    "play": "5467583879948803288",
    "bet": "5893048571560726748",
    "multiplier": "5201691993775818138",
    "history": "5353025608832004653"
}

# Функция для создания премиум эмодзи в тексте
def premium_emoji(emoji_id: str, fallback: str = "⭐") -> str:
    return f'<tg-emoji emoji-id="{emoji_id}">{fallback}</tg-emoji>'

# Инициализация бота
bot = Bot(
    token=BOT_TOKEN, 
    default=DefaultBotProperties(parse_mode="HTML")
)
dp = Dispatcher(storage=MemoryStorage())

# База данных
def init_db():
    conn = sqlite3.connect('bot_database.db')
    c = conn.cursor()
    
    # Таблица пользователей
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (user_id INTEGER PRIMARY KEY,
                  username TEXT,
                  first_name TEXT,
                  balance REAL DEFAULT 0,
                  total_bet REAL DEFAULT 0,
                  games_played INTEGER DEFAULT 0,
                  referrer_id INTEGER DEFAULT NULL,
                  reg_date TEXT,
                  last_activity TEXT)''')
    
    # Таблица рефералов
    c.execute('''CREATE TABLE IF NOT EXISTS referrals
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  referrer_id INTEGER,
                  referral_id INTEGER,
                  level INTEGER,
                  earnings REAL DEFAULT 0,
                  date TEXT)''')
    
    # Таблица для раздач
    c.execute('''CREATE TABLE IF NOT EXISTS giveaways
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id INTEGER,
                  amount REAL,
                  claimed_at TEXT)''')
    
    # Таблица для статистики игр
    c.execute('''CREATE TABLE IF NOT EXISTS games_stats
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id INTEGER,
                  game_type TEXT,
                  bet REAL,
                  win_amount REAL,
                  multiplier REAL,
                  date TEXT)''')
    
    conn.commit()
    conn.close()

init_db()

# Функции для работы с БД
def get_user(user_id: int):
    conn = sqlite3.connect('bot_database.db')
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    user = c.fetchone()
    conn.close()
    return user

def create_user(user_id: int, username: str, first_name: str, referrer_id: int = None):
    conn = sqlite3.connect('bot_database.db')
    c = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # Проверяем, существует ли пользователь
    c.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
    if c.fetchone() is None:
        c.execute('''INSERT INTO users (user_id, username, first_name, balance, reg_date, last_activity, referrer_id)
                     VALUES (?, ?, ?, ?, ?, ?, ?)''',
                  (user_id, username, first_name, 0, now, now, referrer_id))
        
        # Если есть реферер, добавляем в таблицу рефералов
        if referrer_id:
            c.execute('''INSERT INTO referrals (referrer_id, referral_id, level, date)
                         VALUES (?, ?, 1, ?)''', (referrer_id, user_id, now))
    
    conn.commit()
    conn.close()

def update_balance(user_id: int, amount: float):
    conn = sqlite3.connect('bot_database.db')
    c = conn.cursor()
    c.execute("UPDATE users SET balance = balance + ?, last_activity = ? WHERE user_id = ?",
              (amount, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), user_id))
    conn.commit()
    conn.close()

def get_balance(user_id: int) -> float:
    conn = sqlite3.connect('bot_database.db')
    c = conn.cursor()
    c.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
    result = c.fetchone()
    conn.close()
    return result[0] if result else 0

def add_game_stats(user_id: int, game_type: str, bet: float, win_amount: float, multiplier: float):
    conn = sqlite3.connect('bot_database.db')
    c = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute('''INSERT INTO games_stats (user_id, game_type, bet, win_amount, multiplier, date)
                 VALUES (?, ?, ?, ?, ?, ?)''',
              (user_id, game_type, bet, win_amount, multiplier, now))
    c.execute("UPDATE users SET games_played = games_played + 1, total_bet = total_bet + ? WHERE user_id = ?",
              (bet, user_id))
    conn.commit()
    conn.close()

def get_user_stats(user_id: int):
    conn = sqlite3.connect('bot_database.db')
    c = conn.cursor()
    c.execute("SELECT balance, total_bet, games_played FROM users WHERE user_id = ?", (user_id,))
    result = c.fetchone()
    conn.close()
    return result if result else (0, 0, 0)

def get_referrals_info(user_id: int):
    conn = sqlite3.connect('bot_database.db')
    c = conn.cursor()
    
    # Получаем рефералов по уровням
    levels = {1: [], 2: [], 3: []}
    
    # Уровень 1
    c.execute('''SELECT referral_id FROM referrals 
                 WHERE referrer_id = ? AND level = 1''', (user_id,))
    level1 = c.fetchall()
    levels[1] = [r[0] for r in level1]
    
    # Уровень 2 (рефералы рефералов)
    for ref1 in levels[1]:
        c.execute('''SELECT referral_id FROM referrals 
                     WHERE referrer_id = ? AND level = 1''', (ref1,))
        level2 = c.fetchall()
        levels[2].extend([r[0] for r in level2])
    
    # Уровень 3
    for ref2 in levels[2]:
        c.execute('''SELECT referral_id FROM referrals 
                     WHERE referrer_id = ? AND level = 1''', (ref2,))
        level3 = c.fetchall()
        levels[3].extend([r[0] for r in level3])
    
    conn.close()
    return {1: len(levels[1]), 2: len(levels[2]), 3: len(levels[3])}

def get_all_users():
    conn = sqlite3.connect('bot_database.db')
    c = conn.cursor()
    c.execute("SELECT user_id FROM users")
    users = c.fetchall()
    conn.close()
    return [u[0] for u in users]

def get_top_balance(limit=5):
    conn = sqlite3.connect('bot_database.db')
    c = conn.cursor()
    c.execute("SELECT user_id, username, balance FROM users ORDER BY balance DESC LIMIT ?", (limit,))
    top = c.fetchall()
    conn.close()
    return top

def get_top_turnover(limit=5):
    conn = sqlite3.connect('bot_database.db')
    c = conn.cursor()
    c.execute("SELECT user_id, username, total_bet FROM users ORDER BY total_bet DESC LIMIT ?", (limit,))
    top = c.fetchall()
    conn.close()
    return top

# Состояния для FSM
class AdminStates(StatesGroup):
    mailing = State()
    add_balance = State()
    reduce_balance = State()
    giveaway_amount = State()
    write_to_user = State()
    user_id_for_message = State()
    pay_amount = State()

class GameStates(StatesGroup):
    mines_game = State()
    mines_count = State()
    mines_field = State()
    mines_opened = State()
    bet_amount = State()
    tg_game = State()
    tg_number = State()

# Клавиатуры (БЕЗ ПРЕМИУМ ЭМОДЗИ!)
def main_menu_keyboard():
    buttons = [
        [InlineKeyboardButton(text="Играть", callback_data="play")],
        [InlineKeyboardButton(text="Профиль", callback_data="profile"),
         InlineKeyboardButton(text="Реф. Программа", callback_data="referral")],
        [InlineKeyboardButton(text="Игровые чаты", callback_data="game_chats"),
         InlineKeyboardButton(text="Топ", callback_data="top")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def games_menu_keyboard():
    buttons = [
        [InlineKeyboardButton(text="🎲", callback_data="game_dice"),
         InlineKeyboardButton(text="🎳", callback_data="game_bowling"),
         InlineKeyboardButton(text="🏀", callback_data="game_basketball")],
        [InlineKeyboardButton(text="Telegram", callback_data="telegram_games"),
         InlineKeyboardButton(text="Авторские", callback_data="custom_games")],
        [InlineKeyboardButton(text="Мини игры", callback_data="mini_games")],
        [InlineKeyboardButton(text="Назад", callback_data="back_to_main")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def telegram_games_keyboard():
    buttons = [
        [InlineKeyboardButton(text="Чет/Нечет", callback_data="tg_even_odd"),
         InlineKeyboardButton(text="Больше/Меньше", callback_data="tg_high_low")],
        [InlineKeyboardButton(text="Число", callback_data="tg_number"),
         InlineKeyboardButton(text="7+-", callback_data="tg_seven_plus")],
        [InlineKeyboardButton(text="Назад", callback_data="play")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def custom_games_keyboard():
    buttons = [
        [InlineKeyboardButton(text="2x (50%)", callback_data="custom_2"),
         InlineKeyboardButton(text="5x (10%)", callback_data="custom_5")],
        [InlineKeyboardButton(text="10x (5%)", callback_data="custom_10"),
         InlineKeyboardButton(text="50x (1%)", callback_data="custom_50")],
        [InlineKeyboardButton(text="Назад", callback_data="play")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def mini_games_keyboard():
    buttons = [
        [InlineKeyboardButton(text="Мины", callback_data="mines_menu")],
        [InlineKeyboardButton(text="Назад", callback_data="play")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def mines_menu_keyboard():
    buttons = [
        [InlineKeyboardButton(text="Играть", callback_data="mines_play")],
        [InlineKeyboardButton(text="Назад", callback_data="mini_games"),
         InlineKeyboardButton(text="Изменить", callback_data="mines_change")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def mines_count_keyboard(current_mines):
    """Клавиатура выбора количества мин с коэффициентами"""
    buttons = []
    
    # Коэффициенты для разного количества мин
    multipliers = {
        2: "1.02, 1.11, 1.22, 1.34, 1.48, 1.65, 1.84, 2.07, 2.35, 2.69, 3.1, 3.62, 4.27, 5.13, 6.27, 7.83, 10.07, 13.43, 18.8, 28.2, 47, 94, 282",
        3: "1.07, 1.22, 1.4, 1.63, 1.9, 2.23, 2.65, 3.18, 3.86, 4.75, 5.94, 7.56, 9.83, 13.1, 18.02, 25.74, 38.61, 61.77, 108.1, 216.2, 540.5, 2162",
        4: "1.12, 1.34, 1.63, 1.99, 2.45, 3.07, 3.89, 5, 6.53, 8.71, 11.88, 16.63, 24.02, 36.03, 56.62, 94.37, 169.87, 339.74, 792.73, 2378.2, 11891",
        5: "1.18, 1.48, 1.9, 2.45, 3.22, 4.29, 5.83, 8.07, 11.43, 16.63, 24.95, 38.81, 63.06, 108.1, 198.18, 396.37, 891.82, 2378.2, 8323.7, 49942.2",
        6: "1.24, 1.65, 2.23, 3.07, 4.29, 6.14, 8.97, 13.45, 20.79, 33.26, 55.44, 97.01, 180.17, 360.33, 792.73, 1981.83, 5945.5, 23782, 166474",
        7: "1.31, 1.84, 2.65, 3.89, 5.83, 8.97, 14.2, 23.23, 39.5, 70.22, 131.66, 263.32, 570.53, 1369.27, 3765.48, 12551.61, 56482.25, 451858",
        8: "1.38, 2.07, 3.18, 5, 8.07, 13.45, 23.23, 41.82, 79, 157.99, 338.55, 789.96, 2053.9, 6161.7, 22592.9, 112964.5, 1016680.5",
        9: "1.47, 2.35, 3.86, 6.53, 11.43, 20.79, 39.5, 79, 167.87, 383.7, 959.24, 2685.87, 8729.07, 34916.3, 192039.65, 1920396.5",
        10: "1.57, 2.69, 4.75, 8.71, 16.63, 33.26, 70.22, 157.99, 383.7, 1023.19, 3069.56, 10743.48, 46555.07, 279330.4, 3072634.4",
        11: "1.68, 3.1, 5.94, 11.88, 24.95, 55.44, 131.66, 338.55, 959.24, 3069.56, 11510.87, 53717.38, 349163, 4189956",
        12: "1.81, 3.62, 7.56, 16.63, 38.81, 97.01, 263.32, 789.96, 2685.87, 10743.48, 53717.38, 376021.69, 4888282",
        13: "1.96, 4.27, 9.83, 24.02, 63.06, 180.17, 570.53, 2053.9, 8729.08, 46555.07, 349163, 4888282",
        14: "2.12, 5.13, 13.1, 36.03, 108.1, 360.33, 1369.27, 6161.7, 34916.3, 279330.4, 4189956",
        15: "2.35, 6.27, 18.02, 56.62, 198.18, 792.73, 3765.48, 22592.9, 192039.65, 3072634.4",
        16: "2.61, 7.83, 25.74, 94.37, 396.37, 1981.83, 12551.61, 112964.5, 1920396.5",
        17: "2.94, 10.07, 38.61, 169.87, 891.83, 5945.5, 56482.25, 1016680.5",
        18: "3.36, 13.43, 61.77, 339.74, 2378.2, 23782, 451858",
        19: "3.92, 18.8, 108.1, 792.73, 8323.7, 166474",
        20: "4.7, 28.2, 216.2, 2378.2, 49942.2",
        21: "5.88, 47, 540.5, 11891",
        22: "7.83, 94, 2162",
        23: "11.75, 282",
        24: "23.5"
    }
    
    for i in range(2, 25):
        btn_text = f"{i} 💣"
        if i == current_mines:
            btn_text = f"✅ {i} 💣"
        buttons.append(InlineKeyboardButton(text=btn_text, callback_data=f"mines_count_{i}"))
    
    # Разбиваем на ряды по 5 кнопок
    keyboard = []
    row = []
    for i, btn in enumerate(buttons):
        row.append(btn)
        if (i + 1) % 5 == 0:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    
    # Добавляем информацию о коэффициентах для текущего выбора
    if current_mines in multipliers:
        keyboard.append([InlineKeyboardButton(text=f"📈 Коэф: {multipliers[current_mines]}", callback_data="ignore")])
    
    keyboard.append([InlineKeyboardButton(text="Назад", callback_data="mines_menu")])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def mines_field_keyboard(field, opened, game_over=False):
    """Создает поле 5x5 для игры в мины"""
    keyboard = []
    
    for i in range(5):
        row = []
        for j in range(5):
            cell_id = i * 5 + j
            if game_over:
                # Показываем все клетки после окончания игры
                if field[i][j] == 'mine':
                    row.append(InlineKeyboardButton(text="💣", callback_data=f"cell_{cell_id}"))
                elif cell_id in opened:
                    row.append(InlineKeyboardButton(text="📦", callback_data=f"cell_{cell_id}"))
                else:
                    row.append(InlineKeyboardButton(text="🎁", callback_data=f"cell_{cell_id}"))
            else:
                if cell_id in opened:
                    if field[i][j] == 'mine':
                        row.append(InlineKeyboardButton(text="💥", callback_data=f"cell_{cell_id}"))
                    else:
                        row.append(InlineKeyboardButton(text="📦", callback_data=f"cell_{cell_id}"))
                else:
                    row.append(InlineKeyboardButton(text="🌑", callback_data=f"cell_{cell_id}"))
        keyboard.append(row)
    
    if not game_over:
        keyboard.append([InlineKeyboardButton(text="💰 Забрать", callback_data="mines_take")])
    keyboard.append([InlineKeyboardButton(text="◀️ Назад", callback_data="mines_menu")])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def game_chats_keyboard():
    buttons = [
        [InlineKeyboardButton(text="🇷🇺 Ru - Игровой чат", url="https://t.me/+fR7p2T4FGU4zODUy")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_main")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def profile_keyboard():
    buttons = [
        [InlineKeyboardButton(text="💳 Пополнить", callback_data="deposit"),
         InlineKeyboardButton(text="💸 Вывести", callback_data="withdraw")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_main")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def referral_keyboard():
    buttons = [
        [InlineKeyboardButton(text="🎁 Забрать (от 1$)", callback_data="claim_ref")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_main")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def admin_keyboard():
    buttons = [
        [InlineKeyboardButton(text="📢 Рассылка", callback_data="admin_mailing")],
        [InlineKeyboardButton(text="💰 Пополнить баланс", callback_data="admin_add_balance"),
         InlineKeyboardButton(text="💸 Понизить баланс", callback_data="admin_reduce_balance")],
        [InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton(text="🎁 Раздача денег", callback_data="admin_giveaway")],
        [InlineKeyboardButton(text="✍️ Написать пользователю", callback_data="admin_write")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_main")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def top_keyboard():
    buttons = [
        [InlineKeyboardButton(text="💰 По балансу", callback_data="top_balance"),
         InlineKeyboardButton(text="📊 По обороту", callback_data="top_turnover")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_main")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# Функция для расчета множителя в минах
def get_mines_multiplier(mines_count: int, opened_cells: int):
    multipliers = {
        2: [1.02, 1.11, 1.22, 1.34, 1.48, 1.65, 1.84, 2.07, 2.35, 2.69, 3.1, 3.62, 4.27, 5.13, 6.27, 7.83, 10.07, 13.43, 18.8, 28.2, 47, 94, 282],
        3: [1.07, 1.22, 1.4, 1.63, 1.9, 2.23, 2.65, 3.18, 3.86, 4.75, 5.94, 7.56, 9.83, 13.1, 18.02, 25.74, 38.61, 61.77, 108.1, 216.2, 540.5, 2162],
        4: [1.12, 1.34, 1.63, 1.99, 2.45, 3.07, 3.89, 5, 6.53, 8.71, 11.88, 16.63, 24.02, 36.03, 56.62, 94.37, 169.87, 339.74, 792.73, 2378.2, 11891],
        5: [1.18, 1.48, 1.9, 2.45, 3.22, 4.29, 5.83, 8.07, 11.43, 16.63, 24.95, 38.81, 63.06, 108.1, 198.18, 396.37, 891.82, 2378.2, 8323.7, 49942.2],
        6: [1.24, 1.65, 2.23, 3.07, 4.29, 6.14, 8.97, 13.45, 20.79, 33.26, 55.44, 97.01, 180.17, 360.33, 792.73, 1981.83, 5945.5, 23782, 166474],
        7: [1.31, 1.84, 2.65, 3.89, 5.83, 8.97, 14.2, 23.23, 39.5, 70.22, 131.66, 263.32, 570.53, 1369.27, 3765.48, 12551.61, 56482.25, 451858],
        8: [1.38, 2.07, 3.18, 5, 8.07, 13.45, 23.23, 41.82, 79, 157.99, 338.55, 789.96, 2053.9, 6161.7, 22592.9, 112964.5, 1016680.5],
        9: [1.47, 2.35, 3.86, 6.53, 11.43, 20.79, 39.5, 79, 167.87, 383.7, 959.24, 2685.87, 8729.07, 34916.3, 192039.65, 1920396.5],
        10: [1.57, 2.69, 4.75, 8.71, 16.63, 33.26, 70.22, 157.99, 383.7, 1023.19, 3069.56, 10743.48, 46555.07, 279330.4, 3072634.4],
        11: [1.68, 3.1, 5.94, 11.88, 24.95, 55.44, 131.66, 338.55, 959.24, 3069.56, 11510.87, 53717.38, 349163, 4189956],
        12: [1.81, 3.62, 7.56, 16.63, 38.81, 97.01, 263.32, 789.96, 2685.87, 10743.48, 53717.38, 376021.69, 4888282],
        13: [1.96, 4.27, 9.83, 24.02, 63.06, 180.17, 570.53, 2053.9, 8729.08, 46555.07, 349163, 4888282],
        14: [2.12, 5.13, 13.1, 36.03, 108.1, 360.33, 1369.27, 6161.7, 34916.3, 279330.4, 4189956],
        15: [2.35, 6.27, 18.02, 56.62, 198.18, 792.73, 3765.48, 22592.9, 192039.65, 3072634.4],
        16: [2.61, 7.83, 25.74, 94.37, 396.37, 1981.83, 12551.61, 112964.5, 1920396.5],
        17: [2.94, 10.07, 38.61, 169.87, 891.83, 5945.5, 56482.25, 1016680.5],
        18: [3.36, 13.43, 61.77, 339.74, 2378.2, 23782, 451858],
        19: [3.92, 18.8, 108.1, 792.73, 8323.7, 166474],
        20: [4.7, 28.2, 216.2, 2378.2, 49942.2],
        21: [5.88, 47, 540.5, 11891],
        22: [7.83, 94, 2162],
        23: [11.75, 282],
        24: [23.5]
    }
    
    mult_list = multipliers.get(mines_count, [1.02])
    if opened_cells <= len(mult_list) and opened_cells > 0:
        return mult_list[opened_cells - 1]
    return 1.02

# Обработчики команд
@dp.message(CommandStart())
async def cmd_start(message: types.Message, command: CommandStart):
    user_id = message.from_user.id
    username = message.from_user.username or "NoUsername"
    first_name = message.from_user.first_name
    
    # Проверяем реферальный код
    referrer_id = None
    args = command.args
    if args and args.startswith('ref'):
        try:
            referrer_id = int(args.split('_')[1])
            if referrer_id == user_id:
                referrer_id = None
        except:
            pass
    
    create_user(user_id, username, first_name, referrer_id)
    
    if message.chat.type != "private":
        await message.answer(
            f"{premium_emoji(PREMIUM_EMOJIS['win'], '👏')} Бот работает!"
        )
        return
    
    # Первое сообщение
    await message.answer(
        f"{premium_emoji(PREMIUM_EMOJIS['win'], '👏')} Привет."
    )
    
    # Второе сообщение с меню
    await message.answer(
        f"{premium_emoji(PREMIUM_EMOJIS['win'], '👏')} <b>Привет, добро пожаловать в Plays.</b>\n\n"
        f"📢 Подписывайся на наш канал, чтобы следить за новостями и конкурсами.",
        reply_markup=main_menu_keyboard()
    )

@dp.message(Command("menu"))
async def cmd_menu(message: types.Message):
    if message.chat.type != "private":
        return
    await message.answer(
        f"{premium_emoji(PREMIUM_EMOJIS['win'], '👏')} <b>Главное меню</b>",
        reply_markup=main_menu_keyboard()
    )

@dp.message(Command("games"))
async def cmd_games(message: types.Message):
    if message.chat.type != "private":
        return
    balance = get_balance(message.from_user.id)
    await message.answer(
        f"{premium_emoji(PREMIUM_EMOJIS['game'], '🎮')} <b>Выбирайте игру или режим!</b>\n\n"
        f"{premium_emoji(PREMIUM_EMOJIS['balance'], '💰')} Баланс — {balance:.2f}$\n"
        f"{premium_emoji(PREMIUM_EMOJIS['bet'], '🎯')} Ставка — /bet сумма\n\n"
        f"✨ Пополняй и играй!",
        reply_markup=games_menu_keyboard()
    )

@dp.message(Command("play"))
async def cmd_play(message: types.Message):
    if message.chat.type != "private":
        return
    balance = get_balance(message.from_user.id)
    await message.answer(
        f"{premium_emoji(PREMIUM_EMOJIS['game'], '🎮')} <b>Выбирайте игру или режим!</b>\n\n"
        f"{premium_emoji(PREMIUM_EMOJIS['balance'], '💰')} Баланс — {balance:.2f}$\n"
        f"{premium_emoji(PREMIUM_EMOJIS['bet'], '🎯')} Ставка — /bet сумма\n\n"
        f"✨ Пополняй и играй!",
        reply_markup=games_menu_keyboard()
    )

@dp.message(Command("telegram"))
async def cmd_telegram(message: types.Message):
    if message.chat.type != "private":
        return
    balance = get_balance(message.from_user.id)
    await message.answer(
        f"{premium_emoji('5258508428212445001', '6⃣')} <b>Выберите режим игры!</b>\n\n"
        f"{premium_emoji(PREMIUM_EMOJIS['balance'], '💰')} Баланс — {balance:.2f}$\n"
        f"{premium_emoji(PREMIUM_EMOJIS['bet'], '🎯')} Ставка — /bet сумма\n\n"
        f"✨ Пополняй и играй!",
        reply_markup=telegram_games_keyboard()
    )

@dp.message(Command("avtor"))
async def cmd_avtor(message: types.Message):
    if message.chat.type != "private":
        return
    balance = get_balance(message.from_user.id)
    await message.answer(
        f"{premium_emoji(PREMIUM_EMOJIS['casino'], '🐳')} <b>Выбирайте авторскую игру!</b>\n\n"
        f"{premium_emoji(PREMIUM_EMOJIS['balance'], '💰')} Баланс — {balance:.2f}$\n"
        f"{premium_emoji(PREMIUM_EMOJIS['bet'], '🎯')} Ставка — /bet сумма\n\n"
        f"✨ Пополняй и играй!",
        reply_markup=custom_games_keyboard()
    )

@dp.message(Command("mines"))
async def cmd_mines(message: types.Message, state: FSMContext):
    if message.chat.type != "private":
        return
    balance = get_balance(message.from_user.id)
    data = await state.get_data()
    mines_count = data.get('mines_count', 3)
    
    await message.answer(
        f"{premium_emoji(PREMIUM_EMOJIS['mine'], '💣')} <b>Мины</b>\n\n"
        f"{premium_emoji(PREMIUM_EMOJIS['user'], '👤')} {message.from_user.first_name}\n"
        f"{premium_emoji(PREMIUM_EMOJIS['balance'], '💰')} Баланс — {balance:.2f}$\n"
        f"{premium_emoji(PREMIUM_EMOJIS['bet'], '🎯')} Ставка — /bet сумма\n\n"
        f"{premium_emoji(PREMIUM_EMOJIS['mine'], '💣')} <b>Выбрано — {mines_count} 💣</b>",
        reply_markup=mines_menu_keyboard()
    )

@dp.message(Command("chat"))
async def cmd_chat(message: types.Message):
    if message.chat.type != "private":
        return
    await message.answer(
        f"{premium_emoji(PREMIUM_EMOJIS['game'], '💬')} <b>Игровые чаты</b> — это отличное место, чтобы найти друзей, обсудить игру или поднять денег в конкурсах и раздачах!",
        reply_markup=game_chats_keyboard()
    )

@dp.message(Command("ref"))
async def cmd_ref(message: types.Message):
    if message.chat.type != "private":
        return
    user_id = message.from_user.id
    referrals = get_referrals_info(user_id)
    bot_username = (await bot.get_me()).username
    ref_link = f"https://t.me/{bot_username}?start=ref_{user_id}"
    
    text = (
        f"{premium_emoji(PREMIUM_EMOJIS['prize'], '🐈‍⬛')} <b>Реферальная система — 3 уровня</b>\n\n"
        f"1️⃣ {premium_emoji(PREMIUM_EMOJIS['stats'], '📈')} 60% | {referrals[1]} 😒 | $0.00 | $0.00\n"
        f"2️⃣ {premium_emoji(PREMIUM_EMOJIS['stats'], '📈')} 30% | {referrals[2]} 😒 | $0.00 | $0.00\n"
        f"3️⃣ {premium_emoji(PREMIUM_EMOJIS['stats'], '📈')} 10% | {referrals[3]} 😒 | $0.00 | $0.00\n\n"
        f"<b>Ваша ссылка:</b>\n"
        f"<code>{ref_link}</code>\n\n"
        f"<b>Общий доход:</b>\n"
        f"$0.00"
    )
    
    await message.answer(text, reply_markup=referral_keyboard())

@dp.message(Command("profile"))
async def cmd_profile(message: types.Message):
    if message.chat.type != "private":
        return
    user_id = message.from_user.id
    balance, total_bet, games_played = get_user_stats(user_id)
    
    await message.answer(
        f"{premium_emoji(PREMIUM_EMOJIS['user'], '👤')} <b>#{user_id} | {message.from_user.first_name}</b>\n\n"
        f"{premium_emoji(PREMIUM_EMOJIS['balance'], '💰')} Баланс — {balance:.2f}$\n\n"
        f"{premium_emoji(PREMIUM_EMOJIS['stats'], '📊')} Оборот — {total_bet:.2f}$\n"
        f"{premium_emoji(PREMIUM_EMOJIS['game'], '🎮')} Сыграно — {games_played} ставки",
        reply_markup=profile_keyboard()
    )

@dp.message(Command("balance"))
async def cmd_balance(message: types.Message):
    if message.chat.type != "private":
        return
    balance = get_balance(message.from_user.id)
    await message.answer(
        f"{premium_emoji(PREMIUM_EMOJIS['balance'], '💰')} <b>Ваш баланс:</b> {balance:.2f}$"
    )

@dp.message(Command("top"))
async def cmd_top(message: types.Message):
    if message.chat.type != "private":
        return
    await message.answer(
        f"{premium_emoji(PREMIUM_EMOJIS['stats'], '📊')} <b>Топ игроков</b>\n\n"
        f"Выберите категорию:",
        reply_markup=top_keyboard()
    )

@dp.message(Command("pay"))
async def cmd_pay(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        await message.answer("❌ Эта команда только для администратора")
        return
    
    try:
        parts = message.text.split()
        if len(parts) != 3:
            await message.answer("❌ Используй: /pay сумма user_id\nПример: /pay 10 123456789")
            return
        
        amount = float(parts[1])
        user_id = int(parts[2])
        
        if amount < 0.1:
            await message.answer("❌ Минимальная сумма 0.1$")
            return
        
        update_balance(user_id, amount)
        await message.answer(f"✅ Перевод {amount:.2f}$ пользователю {user_id} выполнен")
        
        # Уведомляем пользователя
        try:
            await bot.send_message(
                user_id,
                f"{premium_emoji(PREMIUM_EMOJIS['balance'], '💰')} <b>Вам переведено {amount:.2f}$</b>"
            )
        except:
            pass
            
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")

@dp.message(Command("bet"))
async def cmd_bet(message: types.Message, state: FSMContext):
    if message.chat.type != "private":
        return
    
    try:
        amount = float(message.text.split()[1])
        if amount < 0.1:
            await message.answer("❌ Минимальная ставка 0.1$")
            return
        if amount > 100:
            await message.answer("❌ Максимальная ставка 100$")
            return
        
        await state.update_data(bet_amount=amount)
        await message.answer(f"✅ Ставка установлена: {amount:.2f}$")
    except:
        await message.answer("❌ Используй: /bet 1.5 (где 1.5 - сумма ставки)")

@dp.message(Command("admin"))
async def cmd_admin(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    await message.answer(
        "🔐 <b>Панель администратора</b>",
        reply_markup=admin_keyboard()
    )

# Обработчики колбэков
@dp.callback_query(F.data == "play")
async def play_callback(callback: types.CallbackQuery):
    balance = get_balance(callback.from_user.id)
    await callback.message.edit_text(
        f"{premium_emoji(PREMIUM_EMOJIS['game'], '🎮')} <b>Выбирайте игру или режим!</b>\n\n"
        f"{premium_emoji(PREMIUM_EMOJIS['balance'], '💰')} Баланс — {balance:.2f}$\n"
        f"{premium_emoji(PREMIUM_EMOJIS['bet'], '🎯')} Ставка — /bet сумма\n\n"
        f"✨ Пополняй и играй!",
        reply_markup=games_menu_keyboard()
    )
    await callback.answer()

@dp.callback_query(F.data == "profile")
async def profile_callback(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    balance, total_bet, games_played = get_user_stats(user_id)
    
    await callback.message.edit_text(
        f"{premium_emoji(PREMIUM_EMOJIS['user'], '👤')} <b>#{user_id} | {callback.from_user.first_name}</b>\n\n"
        f"{premium_emoji(PREMIUM_EMOJIS['balance'], '💰')} Баланс — {balance:.2f}$\n\n"
        f"{premium_emoji(PREMIUM_EMOJIS['stats'], '📊')} Оборот — {total_bet:.2f}$\n"
        f"{premium_emoji(PREMIUM_EMOJIS['game'], '🎮')} Сыграно — {games_played} ставки",
        reply_markup=profile_keyboard()
    )
    await callback.answer()

@dp.callback_query(F.data == "referral")
async def referral_callback(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    referrals = get_referrals_info(user_id)
    bot_username = (await bot.get_me()).username
    ref_link = f"https://t.me/{bot_username}?start=ref_{user_id}"
    
    text = (
        f"{premium_emoji(PREMIUM_EMOJIS['prize'], '🐈‍⬛')} <b>Реферальная система — 3 уровня</b>\n\n"
        f"1️⃣ {premium_emoji(PREMIUM_EMOJIS['stats'], '📈')} 60% | {referrals[1]} 😒 | $0.00 | $0.00\n"
        f"2️⃣ {premium_emoji(PREMIUM_EMOJIS['stats'], '📈')} 30% | {referrals[2]} 😒 | $0.00 | $0.00\n"
        f"3️⃣ {premium_emoji(PREMIUM_EMOJIS['stats'], '📈')} 10% | {referrals[3]} 😒 | $0.00 | $0.00\n\n"
        f"<b>Ваша ссылка:</b>\n"
        f"<code>{ref_link}</code>\n\n"
        f"<b>Общий доход:</b>\n"
        f"$0.00"
    )
    
    await callback.message.edit_text(text, reply_markup=referral_keyboard())
    await callback.answer()

@dp.callback_query(F.data == "top")
async def top_callback(callback: types.CallbackQuery):
    await callback.message.edit_text(
        f"{premium_emoji(PREMIUM_EMOJIS['stats'], '📊')} <b>Топ игроков</b>\n\n"
        f"Выберите категорию:",
        reply_markup=top_keyboard()
    )
    await callback.answer()

@dp.callback_query(F.data == "top_balance")
async def top_balance_callback(callback: types.CallbackQuery):
    top = get_top_balance(5)
    
    text = f"{premium_emoji(PREMIUM_EMOJIS['balance'], '💰')} <b>Топ 5 по балансу</b>\n\n"
    
    emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣"]
    for i, (user_id, username, balance) in enumerate(top):
        name = f"@{username}" if username else f"ID {user_id}"
        text += f"{emojis[i]} {name} — {balance:.2f} 💵\n"
    
    await callback.message.edit_text(
        text,
        reply_markup=top_keyboard()
    )
    await callback.answer()

@dp.callback_query(F.data == "top_turnover")
async def top_turnover_callback(callback: types.CallbackQuery):
    top = get_top_turnover(5)
    
    text = f"{premium_emoji(PREMIUM_EMOJIS['stats'], '📊')} <b>Топ 5 по обороту</b>\n\n"
    
    emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣"]
    for i, (user_id, username, turnover) in enumerate(top):
        name = f"@{username}" if username else f"ID {user_id}"
        text += f"{emojis[i]} {name} — {turnover:.2f} 💵\n"
    
    await callback.message.edit_text(
        text,
        reply_markup=top_keyboard()
    )
    await callback.answer()

@dp.callback_query(F.data == "back_to_main")
async def back_to_main_callback(callback: types.CallbackQuery):
    await callback.message.edit_text(
        f"{premium_emoji(PREMIUM_EMOJIS['win'], '👏')} <b>Главное меню</b>",
        reply_markup=main_menu_keyboard()
    )
    await callback.answer()

@dp.callback_query(F.data == "game_chats")
async def game_chats_callback(callback: types.CallbackQuery):
    await callback.message.edit_text(
        f"{premium_emoji(PREMIUM_EMOJIS['game'], '💬')} <b>Игровые чаты</b> — это отличное место, чтобы найти друзей, обсудить игру или поднять денег в конкурсах и раздачах!",
        reply_markup=game_chats_keyboard()
    )
    await callback.answer()

@dp.callback_query(F.data == "telegram_games")
async def telegram_games_callback(callback: types.CallbackQuery):
    balance = get_balance(callback.from_user.id)
    await callback.message.edit_text(
        f"{premium_emoji('5258508428212445001', '6⃣')} <b>Выберите режим игры!</b>\n\n"
        f"{premium_emoji(PREMIUM_EMOJIS['balance'], '💰')} Баланс — {balance:.2f}$\n"
        f"{premium_emoji(PREMIUM_EMOJIS['bet'], '🎯')} Ставка — /bet сумма\n\n"
        f"✨ Пополняй и играй!",
        reply_markup=telegram_games_keyboard()
    )
    await callback.answer()

@dp.callback_query(F.data == "custom_games")
async def custom_games_callback(callback: types.CallbackQuery):
    balance = get_balance(callback.from_user.id)
    await callback.message.edit_text(
        f"{premium_emoji(PREMIUM_EMOJIS['casino'], '🐳')} <b>Выбирайте авторскую игру!</b>\n\n"
        f"{premium_emoji(PREMIUM_EMOJIS['balance'], '💰')} Баланс — {balance:.2f}$\n"
        f"{premium_emoji(PREMIUM_EMOJIS['bet'], '🎯')} Ставка — /bet сумма\n\n"
        f"✨ Пополняй и играй!",
        reply_markup=custom_games_keyboard()
    )
    await callback.answer()

@dp.callback_query(F.data == "mini_games")
async def mini_games_callback(callback: types.CallbackQuery):
    balance = get_balance(callback.from_user.id)
    await callback.message.edit_text(
        f"{premium_emoji(PREMIUM_EMOJIS['mine'], '💣')} <b>Выбирайте мини-игру!</b>\n\n"
        f"{premium_emoji(PREMIUM_EMOJIS['balance'], '💰')} Баланс — {balance:.2f}$\n"
        f"{premium_emoji(PREMIUM_EMOJIS['bet'], '🎯')} Ставка — /bet сумма\n\n"
        f"✨ Пополняй и сыграй!",
        reply_markup=mini_games_keyboard()
    )
    await callback.answer()

@dp.callback_query(F.data == "mines_menu")
async def mines_menu_callback(callback: types.CallbackQuery, state: FSMContext):
    balance = get_balance(callback.from_user.id)
    data = await state.get_data()
    mines_count = data.get('mines_count', 3)
    
    await callback.message.edit_text(
        f"{premium_emoji(PREMIUM_EMOJIS['mine'], '💣')} <b>Мины</b>\n\n"
        f"{premium_emoji(PREMIUM_EMOJIS['user'], '👤')} {callback.from_user.first_name}\n"
        f"{premium_emoji(PREMIUM_EMOJIS['balance'], '💰')} Баланс — {balance:.2f}$\n"
        f"{premium_emoji(PREMIUM_EMOJIS['bet'], '🎯')} Ставка — /bet сумма\n\n"
        f"{premium_emoji(PREMIUM_EMOJIS['mine'], '💣')} <b>Выбрано — {mines_count} 💣</b>",
        reply_markup=mines_menu_keyboard()
    )
    await callback.answer()

@dp.callback_query(F.data == "mines_change")
async def mines_change_callback(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    mines = data.get('mines_count', 3)
    
    await callback.message.edit_text(
        f"{premium_emoji(PREMIUM_EMOJIS['mine'], '💣')} <b>Выберите количество мин</b>\n\n"
        f"<b>Выбрано — {mines} 💣</b>\n\n"
        f"📊 <i>Коэффициенты для текущего выбора:</i>",
        reply_markup=mines_count_keyboard(mines)
    )
    await callback.answer()

@dp.callback_query(F.data.startswith("mines_count_"))
async def mines_count_selected(callback: types.CallbackQuery, state: FSMContext):
    count = int(callback.data.split("_")[2])
    await state.update_data(mines_count=count)
    await mines_menu_callback(callback, state)

# Telegram игры - ИСПРАВЛЕННАЯ ВЕРСИЯ

@dp.callback_query(F.data == "tg_even_odd")
async def tg_even_odd(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    balance = get_balance(user_id)
    
    data = await state.get_data()
    bet = data.get('bet_amount', 0)
    
    if bet == 0:
        await callback.answer("❌ Сначала установите ставку! Используйте /bet сумма", show_alert=True)
        return
    
    if balance < bet:
        await callback.answer(f"❌ Недостаточно средств! Баланс: {balance:.2f}$", show_alert=True)
        return
    
    # Сохраняем ставку для игры
    await state.update_data(game_bet=bet, game_type="even_odd")
    
    # Клавиатура выбора
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Чет", callback_data="even_choice"),
         InlineKeyboardButton(text="Нечет", callback_data="odd_choice")]
    ])
    
    await callback.message.edit_text(
        f"{premium_emoji(PREMIUM_EMOJIS['dice'], '🎲')} <b>Чет/Нечет</b>\n\n"
        f"Ставка: {bet:.2f}$\n"
        f"Выберите:",
        reply_markup=keyboard
    )
    await callback.answer()

@dp.callback_query(F.data.in_(["even_choice", "odd_choice"]))
async def even_odd_choice(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    choice = "even" if callback.data == "even_choice" else "odd"
    
    data = await state.get_data()
    bet = data.get('game_bet', 0)
    
    # Отправляем дайс
    msg = await callback.message.answer_dice(emoji="🎲")
    dice_value = msg.dice.value
    is_even = dice_value % 2 == 0
    
    # Определяем выигрыш
    win = (choice == "even" and is_even) or (choice == "odd" and not is_even)
    
    if win:
        win_amount = bet * 2
        update_balance(user_id, win_amount)
        add_game_stats(user_id, "even_odd", bet, win_amount, 2)
        
        await callback.message.answer(
            f"{premium_emoji(PREMIUM_EMOJIS['win'], '🏆')} <b>Победа в игре Чет/Нечет!</b>\n\n"
            f"Выпало: {dice_value} {'(чет)' if is_even else '(нечет)'}\n"
            f"❌2x 🔼 Выигрыш {win_amount:.2f}$\n\n"
            f"{premium_emoji(PREMIUM_EMOJIS['balance'], '💰')} Баланс {get_balance(user_id):.2f}$"
        )
    else:
        update_balance(user_id, -bet)
        add_game_stats(user_id, "even_odd", bet, 0, 0)
        
        await callback.message.answer(
            f"{premium_emoji(PREMIUM_EMOJIS['lose'], '💥')} <b>Проигрыш в игре Чет/Нечет!</b>\n\n"
            f"Выпало: {dice_value} {'(чет)' if is_even else '(нечет)'}\n"
            f"Ставка: {bet:.2f}$\n\n"
            f"{premium_emoji(PREMIUM_EMOJIS['balance'], '💰')} Баланс {get_balance(user_id):.2f}$"
        )
    
    await state.update_data(game_bet=None)
    await callback.answer()

@dp.callback_query(F.data == "tg_high_low")
async def tg_high_low(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    balance = get_balance(user_id)
    
    data = await state.get_data()
    bet = data.get('bet_amount', 0)
    
    if bet == 0:
        await callback.answer("❌ Сначала установите ставку! Используйте /bet сумма", show_alert=True)
        return
    
    if balance < bet:
        await callback.answer(f"❌ Недостаточно средств! Баланс: {balance:.2f}$", show_alert=True)
        return
    
    # Сохраняем ставку для игры
    await state.update_data(game_bet=bet, game_type="high_low")
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Больше (4-6)", callback_data="high_choice"),
         InlineKeyboardButton(text="Меньше (1-3)", callback_data="low_choice")]
    ])
    
    await callback.message.edit_text(
        f"{premium_emoji(PREMIUM_EMOJIS['dice'], '🎲')} <b>Больше/Меньше</b>\n\n"
        f"Ставка: {bet:.2f}$\n"
        f"Выберите:",
        reply_markup=keyboard
    )
    await callback.answer()

@dp.callback_query(F.data.in_(["high_choice", "low_choice"]))
async def high_low_choice(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    choice = "high" if callback.data == "high_choice" else "low"
    
    data = await state.get_data()
    bet = data.get('game_bet', 0)
    
    # Отправляем дайс
    msg = await callback.message.answer_dice(emoji="🎲")
    dice_value = msg.dice.value
    is_high = dice_value >= 4
    
    # Определяем выигрыш
    win = (choice == "high" and is_high) or (choice == "low" and not is_high)
    
    if win:
        win_amount = bet * 2
        update_balance(user_id, win_amount)
        add_game_stats(user_id, "high_low", bet, win_amount, 2)
        
        await callback.message.answer(
            f"{premium_emoji(PREMIUM_EMOJIS['win'], '🏆')} <b>Победа в игре Больше/Меньше!</b>\n\n"
            f"Выпало: {dice_value}\n"
            f"❌2x 🔼 Выигрыш {win_amount:.2f}$\n\n"
            f"{premium_emoji(PREMIUM_EMOJIS['balance'], '💰')} Баланс {get_balance(user_id):.2f}$"
        )
    else:
        update_balance(user_id, -bet)
        add_game_stats(user_id, "high_low", bet, 0, 0)
        
        await callback.message.answer(
            f"{premium_emoji(PREMIUM_EMOJIS['lose'], '💥')} <b>Проигрыш в игре Больше/Меньше!</b>\n\n"
            f"Выпало: {dice_value}\n"
            f"Ставка: {bet:.2f}$\n\n"
            f"{premium_emoji(PREMIUM_EMOJIS['balance'], '💰')} Баланс {get_balance(user_id):.2f}$"
        )
    
    await state.update_data(game_bet=None)
    await callback.answer()

@dp.callback_query(F.data == "tg_number")
async def tg_number(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    balance = get_balance(user_id)
    
    data = await state.get_data()
    bet = data.get('bet_amount', 0)
    
    if bet == 0:
        await callback.answer("❌ Сначала установите ставку! Используйте /bet сумма", show_alert=True)
        return
    
    if balance < bet:
        await callback.answer(f"❌ Недостаточно средств! Баланс: {balance:.2f}$", show_alert=True)
        return
    
    # Сохраняем ставку для игры
    await state.update_data(game_bet=bet, game_type="number")
    
    # Клавиатура с числами
    keyboard = []
    row = []
    for i in range(1, 7):
        row.append(InlineKeyboardButton(text=str(i), callback_data=f"number_{i}"))
        if i % 3 == 0:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    
    await callback.message.edit_text(
        f"{premium_emoji(PREMIUM_EMOJIS['dice'], '🎲')} <b>Выберите число (1-6)</b>\n\n"
        f"Ставка: {bet:.2f}$\n"
        f"При выигрыше: x5.7",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
    )
    await callback.answer()

@dp.callback_query(F.data.startswith("number_"))
async def number_choice(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    chosen = int(callback.data.split("_")[1])
    
    data = await state.get_data()
    bet = data.get('game_bet', 0)
    
    # Отправляем дайс
    msg = await callback.message.answer_dice(emoji="🎲")
    dice_value = msg.dice.value
    
    if dice_value == chosen:
        win_amount = bet * 5.7
        update_balance(user_id, win_amount)
        add_game_stats(user_id, "number", bet, win_amount, 5.7)
        
        await callback.message.answer(
            f"{premium_emoji(PREMIUM_EMOJIS['win'], '🏆')} <b>Победа в игре Число!</b>\n\n"
            f"Выпало: {dice_value}, выбрано: {chosen}\n"
            f"❌5.7x 🔼 Выигрыш {win_amount:.2f}$\n\n"
            f"{premium_emoji(PREMIUM_EMOJIS['balance'], '💰')} Баланс {get_balance(user_id):.2f}$"
        )
    else:
        update_balance(user_id, -bet)
        add_game_stats(user_id, "number", bet, 0, 0)
        
        await callback.message.answer(
            f"{premium_emoji(PREMIUM_EMOJIS['lose'], '💥')} <b>Проигрыш в игре Число!</b>\n\n"
            f"Выпало: {dice_value}, выбрано: {chosen}\n"
            f"Ставка: {bet:.2f}$\n\n"
            f"{premium_emoji(PREMIUM_EMOJIS['balance'], '💰')} Баланс {get_balance(user_id):.2f}$"
        )
    
    await state.update_data(game_bet=None)
    await callback.answer()

@dp.callback_query(F.data == "tg_seven_plus")
async def tg_seven_plus(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    balance = get_balance(user_id)
    
    data = await state.get_data()
    bet = data.get('bet_amount', 0)
    
    if bet == 0:
        await callback.answer("❌ Сначала установите ставку! Используйте /bet сумма", show_alert=True)
        return
    
    if balance < bet:
        await callback.answer(f"❌ Недостаточно средств! Баланс: {balance:.2f}$", show_alert=True)
        return
    
    # Сохраняем ставку для игры
    await state.update_data(game_bet=bet, game_type="seven_plus")
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="7 и выше", callback_data="seven_high"),
         InlineKeyboardButton(text="Ниже 7", callback_data="seven_low")]
    ])
    
    await callback.message.edit_text(
        f"{premium_emoji(PREMIUM_EMOJIS['dice'], '🎲')} <b>7+- (сумма двух кубиков)</b>\n\n"
        f"Ставка: {bet:.2f}$\n"
        f"Выберите:",
        reply_markup=keyboard
    )
    await callback.answer()

@dp.callback_query(F.data.in_(["seven_high", "seven_low"]))
async def seven_choice(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    choice = "high" if callback.data == "seven_high" else "low"
    
    data = await state.get_data()
    bet = data.get('game_bet', 0)
    
    # Отправляем два дайса
    msg1 = await callback.message.answer_dice(emoji="🎲")
    msg2 = await callback.message.answer_dice(emoji="🎲")
    dice1 = msg1.dice.value
    dice2 = msg2.dice.value
    total = dice1 + dice2
    
    is_high = total >= 7
    
    # Определяем выигрыш
    win = (choice == "high" and is_high) or (choice == "low" and not is_high)
    
    if win:
        win_amount = bet * 2
        update_balance(user_id, win_amount)
        add_game_stats(user_id, "seven_plus", bet, win_amount, 2)
        
        await callback.message.answer(
            f"{premium_emoji(PREMIUM_EMOJIS['win'], '🏆')} <b>Победа в игре 7+-!</b>\n\n"
            f"Выпало: {dice1} + {dice2} = {total}\n"
            f"❌2x 🔼 Выигрыш {win_amount:.2f}$\n\n"
            f"{premium_emoji(PREMIUM_EMOJIS['balance'], '💰')} Баланс {get_balance(user_id):.2f}$"
        )
    else:
        update_balance(user_id, -bet)
        add_game_stats(user_id, "seven_plus", bet, 0, 0)
        
        await callback.message.answer(
            f"{premium_emoji(PREMIUM_EMOJIS['lose'], '💥')} <b>Проигрыш в игре 7+-!</b>\n\n"
            f"Выпало: {dice1} + {dice2} = {total}\n"
            f"Ставка: {bet:.2f}$\n\n"
            f"{premium_emoji(PREMIUM_EMOJIS['balance'], '💰')} Баланс {get_balance(user_id):.2f}$"
        )
    
    await state.update_data(game_bet=None)
    await callback.answer()
    
    if bet == 0:
        await callback.answer("❌ Сначала установите ставку! Используйте /bet сумма", show_alert=True)
        return
    
    if balance < bet:
        await callback.answer(f"❌ Недостаточно средств! Баланс: {balance:.2f}$", show_alert=True)
        return
    
    # Клавиатура с числами
    keyboard = []
    row = []
    for i in range(1, 7):
        row.append(InlineKeyboardButton(text=str(i), callback_data=f"number_choice_{i}_{bet}"))
        if i % 3 == 0:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    
    await callback.message.answer(
        f"{premium_emoji(PREMIUM_EMOJIS['dice'], '🎲')} <b>Выберите число (1-6)</b>\n\n"
        f"При выигрыше: x5.7",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
    )
    await callback.answer()

@dp.callback_query(F.data.startswith("number_choice_"))
async def number_choice(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    _, _, chosen, bet = callback.data.split('_')
    chosen = int(chosen)
    bet = float(bet)
    
    dice_value = random.randint(1, 6)
    
    if dice_value == chosen:
        win_amount = bet * 5.7
        update_balance(user_id, win_amount)
        add_game_stats(user_id, "number", bet, win_amount, 5.7)
        
        await callback.message.edit_text(
            f"{premium_emoji(PREMIUM_EMOJIS['win'], '🏆')} <b>Победа!</b>\n\n"
            f"Выпало: {dice_value}\n"
            f"❌5.7x 🔼 Выигрыш {win_amount:.2f}$\n\n"
            f"{premium_emoji(PREMIUM_EMOJIS['balance'], '💰')} Баланс {get_balance(user_id):.2f}$"
        )
    else:
        update_balance(user_id, -bet)
        add_game_stats(user_id, "number", bet, 0, 0)
        
        await callback.message.edit_text(
            f"{premium_emoji(PREMIUM_EMOJIS['lose'], '💥')} <b>Проигрыш!</b>\n\n"
            f"Выпало: {dice_value}, выбрано: {chosen}\n\n"
            f"{premium_emoji(PREMIUM_EMOJIS['balance'], '💰')} Баланс {get_balance(user_id):.2f}$"
        )
    
    await callback.answer()

@dp.callback_query(F.data == "tg_seven_plus")
async def tg_seven_plus(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    balance = get_balance(user_id)
    
    data = await state.get_data()
    bet = data.get('bet_amount', 0)
    
    if bet == 0:
        await callback.answer("❌ Сначала установите ставку! Используйте /bet сумма", show_alert=True)
        return
    
    if balance < bet:
        await callback.answer(f"❌ Недостаточно средств! Баланс: {balance:.2f}$", show_alert=True)
        return
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="7 и выше", callback_data=f"seven_choice_high_{bet}"),
         InlineKeyboardButton(text="Ниже 7", callback_data=f"seven_choice_low_{bet}")]
    ])
    
    await callback.message.answer(
        f"{premium_emoji(PREMIUM_EMOJIS['dice'], '🎲')} <b>7+- (сумма двух кубиков)</b>\n\n"
        f"Сделайте ставку:",
        reply_markup=keyboard
    )
    await callback.answer()

@dp.callback_query(F.data.startswith("seven_choice_"))
async def seven_choice(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    _, _, choice, bet = callback.data.split('_')
    bet = float(bet)
    
    # Кидаем два кубика
    dice1 = random.randint(1, 6)
    dice2 = random.randint(1, 6)
    total = dice1 + dice2
    
    is_high = total >= 7
    
    win = (choice == "high" and is_high) or (choice == "low" and not is_high)
    
    if win:
        win_amount = bet * 2
        update_balance(user_id, win_amount)
        add_game_stats(user_id, "seven_plus", bet, win_amount, 2)
        
        await callback.message.edit_text(
            f"{premium_emoji(PREMIUM_EMOJIS['win'], '🏆')} <b>Победа!</b>\n\n"
            f"Выпало: {dice1} + {dice2} = {total}\n"
            f"❌2x 🔼 Выигрыш {win_amount:.2f}$\n\n"
            f"{premium_emoji(PREMIUM_EMOJIS['balance'], '💰')} Баланс {get_balance(user_id):.2f}$"
        )
    else:
        update_balance(user_id, -bet)
        add_game_stats(user_id, "seven_plus", bet, 0, 0)
        
        await callback.message.edit_text(
            f"{premium_emoji(PREMIUM_EMOJIS['lose'], '💥')} <b>Проигрыш!</b>\n\n"
            f"Выпало: {dice1} + {dice2} = {total}\n\n"
            f"{premium_emoji(PREMIUM_EMOJIS['balance'], '💰')} Баланс {get_balance(user_id):.2f}$"
        )
    
    await callback.answer()

# Мины
@dp.callback_query(F.data == "mines_play")
async def mines_play_callback(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    balance = get_balance(user_id)
    
    # Получаем данные
    data = await state.get_data()
    bet = data.get('bet_amount', 0)
    mines_count = data.get('mines_count', 3)
    
    if bet == 0:
        await callback.answer("❌ Сначала установите ставку! Используйте /bet сумма", show_alert=True)
        return
    
    if balance < bet:
        await callback.answer(f"❌ Недостаточно средств! Баланс: {balance:.2f}$", show_alert=True)
        return
    
    # Создаем поле для игры (5x5)
    field = [['safe' for _ in range(5)] for _ in range(5)]
    
    # Расставляем мины
    positions = list(range(25))
    random.shuffle(positions)
    mine_positions = positions[:mines_count]
    
    for pos in mine_positions:
        i, j = divmod(pos, 5)
        field[i][j] = 'mine'
    
    await state.update_data(
        mines_field=field,
        mines_opened=[],
        game_active=True
    )
    
    multiplier = get_mines_multiplier(mines_count, 0)
    
    await callback.message.edit_text(
        f"{premium_emoji(PREMIUM_EMOJIS['mine'], '💣')} <b>Мины · {mines_count}</b>\n\n"
        f"{bet:.2f}$ ❌ {multiplier}x ➡️ {(bet * multiplier):.2f}$\n\n"
        f"🌑 <i>Сделать ход</i> | 🎁 <i>Приз</i> | 📦 <i>Был приз</i>\n"
        f"💣 <i>Бомба</i> | 💥 <i>Взрыв</i>",
        reply_markup=mines_field_keyboard(field, [])
    )
    await callback.answer()

@dp.callback_query(F.data.startswith("cell_"))
async def mines_cell_callback(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    cell_id = int(callback.data.split("_")[1])
    i, j = divmod(cell_id, 5)
    
    data = await state.get_data()
    field = data.get('mines_field')
    opened = data.get('mines_opened', [])
    bet = data.get('bet_amount', 0)
    mines_count = data.get('mines_count', 3)
    
    if not data.get('game_active', False):
        await callback.answer("Игра уже завершена!", show_alert=True)
        return
    
    if cell_id in opened:
        await callback.answer("Эта клетка уже открыта!", show_alert=True)
        return
    
    opened.append(cell_id)
    await state.update_data(mines_opened=opened)
    
    # Проверяем, не бомба ли это
    if field[i][j] == 'mine':
        # Проигрыш
        update_balance(user_id, -bet)
        add_game_stats(user_id, "mines", bet, 0, 0)
        
        await state.update_data(game_active=False)
        
        await callback.message.edit_text(
            f"{premium_emoji(PREMIUM_EMOJIS['lose'], '💥')} <b>ВЗРЫВ!</b>\n\n"
            f"Проигрыш {bet:.2f}$ в игре 💣\n\n"
            f"{premium_emoji(PREMIUM_EMOJIS['balance'], '💰')} Баланс {get_balance(user_id):.2f}$",
            reply_markup=mines_field_keyboard(field, opened, game_over=True)
        )
    else:
        # Выигрыш - продолжаем игру
        multiplier = get_mines_multiplier(mines_count, len(opened))
        current_win = bet * multiplier
        
        # Проверяем, открыты ли все безопасные клетки
        total_safe = 25 - mines_count
        if len(opened) == total_safe:
            # Открыты все призы - победа
            update_balance(user_id, current_win)
            add_game_stats(user_id, "mines", bet, current_win, multiplier)
            await state.update_data(game_active=False)
            
            await callback.message.edit_text(
                f"{premium_emoji(PREMIUM_EMOJIS['win'], '🏆')} <b>ПОБЕДА!</b>\n\n"
                f"Выигрыш {current_win:.2f}$ в игре 💣\n\n"
                f"{premium_emoji(PREMIUM_EMOJIS['balance'], '💰')} Баланс {get_balance(user_id):.2f}$",
                reply_markup=mines_field_keyboard(field, opened, game_over=True)
            )
        else:
            # Продолжаем игру
            await callback.message.edit_text(
                f"{premium_emoji(PREMIUM_EMOJIS['mine'], '💣')} <b>Мины · {mines_count}</b>\n\n"
                f"{bet:.2f}$ ❌ {multiplier}x ➡️ {current_win:.2f}$\n\n"
                f"🌑 <i>Сделать ход</i> | 🎁 <i>Приз</i> | 📦 <i>Был приз</i>\n"
                f"💣 <i>Бомба</i> | 💥 <i>Взрыв</i>",
                reply_markup=mines_field_keyboard(field, opened)
            )
    
    await callback.answer()

@dp.callback_query(F.data == "mines_take")
async def mines_take_callback(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    data = await state.get_data()
    
    if not data.get('game_active', False):
        await callback.answer("Игра уже завершена!", show_alert=True)
        return
    
    bet = data.get('bet_amount', 0)
    mines_count = data.get('mines_count', 3)
    opened = data.get('mines_opened', [])
    field = data.get('mines_field')
    
    if not opened:
        await callback.answer("Сначала откройте хотя бы одну клетку!", show_alert=True)
        return
    
    multiplier = get_mines_multiplier(mines_count, len(opened))
    win = bet * multiplier
    
    update_balance(user_id, win)
    add_game_stats(user_id, "mines", bet, win, multiplier)
    
    await state.update_data(game_active=False)
    
    await callback.message.edit_text(
        f"{premium_emoji(PREMIUM_EMOJIS['win'], '💰')} <b>Вы забрали выигрыш!</b>\n\n"
        f"Выигрыш: {win:.2f}$\n"
        f"Множитель: {multiplier}x\n\n"
        f"{premium_emoji(PREMIUM_EMOJIS['balance'], '💰')} Баланс: {get_balance(user_id):.2f}$",
        reply_markup=mines_field_keyboard(field, opened, game_over=True)
    )
    await callback.answer()

# Обычные игры
@dp.callback_query(F.data.startswith("game_"))
async def game_handler(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    balance = get_balance(user_id)
    
    # Получаем ставку из состояния
    data = await state.get_data()
    bet = data.get('bet_amount', 0)
    
    if bet == 0:
        await callback.answer("❌ Сначала установите ставку! Используйте /bet сумма", show_alert=True)
        return
    
    if balance < bet:
        await callback.answer(f"❌ Недостаточно средств! Баланс: {balance:.2f}$", show_alert=True)
        return
    
    game_type = callback.data.split("_")[1]
    
    if game_type == "dice":
        # Игра в кости
        msg = await callback.message.answer_dice(emoji="🎲")
        dice_value = msg.dice.value
        win = dice_value >= 4
        
        if win:
            win_amount = bet * 1.9
            update_balance(user_id, win_amount)
            add_game_stats(user_id, "dice", bet, win_amount, 1.9)
            
            await callback.message.answer(
                f"{premium_emoji(PREMIUM_EMOJIS['win'], '🏆')} <b>Победа в игре {premium_emoji(PREMIUM_EMOJIS['dice'], '🎲')} на {bet:.2f}$</b>\n\n"
                f"❌1.9 🔼 Выигрыш {win_amount:.2f}$\n\n"
                f"{premium_emoji(PREMIUM_EMOJIS['balance'], '💰')} Баланс {get_balance(user_id):.2f}$"
            )
        else:
            update_balance(user_id, -bet)
            add_game_stats(user_id, "dice", bet, 0, 0)
            
            await callback.message.answer(
                f"{premium_emoji(PREMIUM_EMOJIS['lose'], '💥')} <b>Проигрыш {bet:.2f}$ в игре {premium_emoji(PREMIUM_EMOJIS['dice'], '🎲')}</b>\n\n"
                f"На {dice_value}️⃣ выпало число, для победы надо 4, 5, 6 :(\n\n"
                f"{premium_emoji(PREMIUM_EMOJIS['balance'], '💰')} Баланс {get_balance(user_id):.2f}$"
            )
    
    elif game_type == "basketball":
        # Баскетбол
        msg = await callback.message.answer_dice(emoji="🏀")
        dice_value = msg.dice.value
        
        # В баскетболе: если мяч в кольце (значение 4 или 5)
        if dice_value == 4 or dice_value == 5:
            win_amount = bet * 3
            update_balance(user_id, win_amount)
            add_game_stats(user_id, "basketball", bet, win_amount, 3)
            
            await callback.message.answer(
                f"{premium_emoji(PREMIUM_EMOJIS['win'], '🏆')} <b>Чистый бросок! 🏀</b>\n\n"
                f"❌3x 🔼 Выигрыш {win_amount:.2f}$\n\n"
                f"{premium_emoji(PREMIUM_EMOJIS['balance'], '💰')} Баланс {get_balance(user_id):.2f}$"
            )
        else:
            update_balance(user_id, -bet)
            add_game_stats(user_id, "basketball", bet, 0, 0)
            
            await callback.message.answer(
                f"{premium_emoji(PREMIUM_EMOJIS['lose'], '💥')} <b>Промах! 🏀</b>\n\n"
                f"Мяч не попал в кольцо :(\n\n"
                f"{premium_emoji(PREMIUM_EMOJIS['balance'], '💰')} Баланс {get_balance(user_id):.2f}$"
            )
    
    elif game_type == "bowling":
        # Боулинг
        msg = await callback.message.answer_dice(emoji="🎳")
        dice_value = msg.dice.value
        
        # В боулинге: страйк (значение 6)
        if dice_value == 6:
            win_amount = bet * 5
            update_balance(user_id, win_amount)
            add_game_stats(user_id, "bowling", bet, win_amount, 5)
            
            await callback.message.answer(
                f"{premium_emoji(PREMIUM_EMOJIS['win'], '🏆')} <b>СТРАЙК! 🎳</b>\n\n"
                f"❌5x 🔼 Выигрыш {win_amount:.2f}$\n\n"
                f"{premium_emoji(PREMIUM_EMOJIS['balance'], '💰')} Баланс {get_balance(user_id):.2f}$"
            )
        else:
            update_balance(user_id, -bet)
            add_game_stats(user_id, "bowling", bet, 0, 0)
            
            await callback.message.answer(
                f"{premium_emoji(PREMIUM_EMOJIS['lose'], '💥')} <b>Неудача! 🎳</b>\n\n"
                f"Кегли остались стоять :(\n\n"
                f"{premium_emoji(PREMIUM_EMOJIS['balance'], '💰')} Баланс {get_balance(user_id):.2f}$"
            )
    
    await callback.answer()

# Авторские игры
@dp.callback_query(F.data.startswith("custom_"))
async def custom_game_handler(callback: types.CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    balance = get_balance(user_id)
    
    # Получаем ставку из состояния
    data = await state.get_data()
    bet = data.get('bet_amount', 0)
    
    if bet == 0:
        await callback.answer("❌ Сначала установите ставку! Используйте /bet сумма", show_alert=True)
        return
    
    if balance < bet:
        await callback.answer(f"❌ Недостаточно средств! Баланс: {balance:.2f}$", show_alert=True)
        return
    
    multiplier = int(callback.data.split("_")[1])
    
    # Определяем шанс
    chances = {
        2: 0.5,
        5: 0.1,
        10: 0.05,
        50: 0.01
    }
    
    # Кидаем эмодзи для эффекта
    await callback.message.answer_dice(emoji="🎰")
    
    if random.random() < chances[multiplier]:
        win_amount = bet * multiplier
        update_balance(user_id, win_amount)
        add_game_stats(user_id, f"custom_{multiplier}x", bet, win_amount, multiplier)
        
        await callback.message.answer(
            f"{premium_emoji(PREMIUM_EMOJIS['win'], '🏆')} <b>ПОБЕДА!</b>\n\n"
            f"❌{multiplier}x 🔼 Выигрыш {win_amount:.2f}$\n\n"
            f"{premium_emoji(PREMIUM_EMOJIS['balance'], '💰')} Баланс {get_balance(user_id):.2f}$"
        )
    else:
        update_balance(user_id, -bet)
        add_game_stats(user_id, f"custom_{multiplier}x", bet, 0, 0)
        
        await callback.message.answer(
            f"{premium_emoji(PREMIUM_EMOJIS['lose'], '💥')} <b>Проигрыш!</b>\n\n"
            f"Повезет в следующий раз!\n\n"
            f"{premium_emoji(PREMIUM_EMOJIS['balance'], '💰')} Баланс {get_balance(user_id):.2f}$"
        )
    
    await callback.answer()

@dp.callback_query(F.data == "deposit")
async def deposit_callback(callback: types.CallbackQuery):
    await callback.message.edit_text(
        f"{premium_emoji(PREMIUM_EMOJIS['deposit'], '💳')} <b>Пополнение баланса</b>\n\n"
        f"Для пополнения свяжись с администратором @qwhatss\n\n"
        f"<b>Укажи:</b>\n"
        f"• Айди аккаунта: <code>{callback.from_user.id}</code>\n"
        f"• Сумма пополнения\n"
        f"• Чек\n\n"
        f"Средства поступят в течение 5-10 минут",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Назад", callback_data="profile")]
        ])
    )
    await callback.answer()

@dp.callback_query(F.data == "withdraw")
async def withdraw_callback(callback: types.CallbackQuery):
    await callback.message.edit_text(
        f"{premium_emoji(PREMIUM_EMOJIS['withdraw'], '💸')} <b>Вывод средств</b>\n\n"
        f"Для вывода свяжись с администратором @qwhatss\n\n"
        f"<b>Укажи:</b>\n"
        f"• Айди аккаунта: <code>{callback.from_user.id}</code>\n"
        f"• Сумма вывода\n\n"
        f"Вывод производится в течение 24 часов",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Назад", callback_data="profile")]
        ])
    )
    await callback.answer()

# Админ-панель
@dp.callback_query(F.data == "admin_stats")
async def admin_stats(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Нет доступа", show_alert=True)
        return
    
    conn = sqlite3.connect('bot_database.db')
    c = conn.cursor()
    
    # Общая статистика
    c.execute("SELECT COUNT(*) FROM users")
    total_users = c.fetchone()[0]
    
    c.execute("SELECT SUM(balance) FROM users")
    total_balance = c.fetchone()[0] or 0
    
    c.execute("SELECT SUM(total_bet) FROM users")
    total_bet = c.fetchone()[0] or 0
    
    c.execute("SELECT COUNT(*) FROM games_stats")
    total_games = c.fetchone()[0]
    
    c.execute("SELECT SUM(win_amount) FROM games_stats WHERE win_amount > 0")
    total_wins = c.fetchone()[0] or 0
    
    conn.close()
    
    await callback.message.edit_text(
        f"📊 <b>Статистика бота</b>\n\n"
        f"👥 Всего пользователей: {total_users}\n"
        f"💰 Общий баланс: {total_balance:.2f}$\n"
        f"🎮 Всего игр: {total_games}\n"
        f"📈 Общий оборот: {total_bet:.2f}$\n"
        f"🏆 Всего выигрышей: {total_wins:.2f}$\n"
        f"📉 Профит казино: {total_bet - total_wins:.2f}$",
        reply_markup=admin_keyboard()
    )
    await callback.answer()

@dp.callback_query(F.data == "admin_mailing")
async def admin_mailing(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Нет доступа", show_alert=True)
        return
    
    await callback.message.edit_text(
        "📢 <b>Рассылка</b>\n\n"
        "Отправь текст для рассылки.\n\n"
        "Можно использовать HTML разметку.\n"
        "Для добавления кнопок отправь текст в формате:\n"
        "<code>Текст сообщения</code>\n"
        "---\n"
        "Кнопка 1|https://t.me\n"
        "Кнопка 2|callback_data"
    )
    await state.set_state(AdminStates.mailing)
    await callback.answer()

@dp.message(AdminStates.mailing)
async def process_mailing(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    
    text = message.text
    keyboard = None
    
    # Проверяем, есть ли кнопки
    if '---' in text:
        parts = text.split('---')
        main_text = parts[0].strip()
        buttons_text = parts[1].strip().split('\n')
        
        keyboard_builder = InlineKeyboardBuilder()
        for button_line in buttons_text:
            if '|' in button_line:
                btn_text, btn_data = button_line.split('|')
                if btn_data.startswith(('http://', 'https://')):
                    keyboard_builder.button(text=btn_text.strip(), url=btn_data.strip())
                else:
                    keyboard_builder.button(text=btn_text.strip(), callback_data=btn_data.strip())
        
        keyboard_builder.adjust(1)
        keyboard = keyboard_builder.as_markup()
    else:
        main_text = text
    
    # Получаем всех пользователей
    users = get_all_users()
    sent = 0
    failed = 0
    
    await message.answer(f"📢 Начинаю рассылку {len(users)} пользователям...")
    
    for user_id in users:
        try:
            await bot.send_message(user_id, main_text, reply_markup=keyboard)
            sent += 1
            await asyncio.sleep(0.05)  # Защита от флуда
        except Exception as e:
            failed += 1
            print(f"Ошибка отправки пользователю {user_id}: {e}")
    
    await message.answer(f"✅ Рассылка завершена!\nОтправлено: {sent}\nНе доставлено: {failed}")
    await state.clear()

@dp.callback_query(F.data == "admin_add_balance")
async def admin_add_balance(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Нет доступа", show_alert=True)
        return
    
    await callback.message.edit_text(
        "💰 <b>Пополнение баланса</b>\n\n"
        "Введи ID пользователя и сумму через пробел.\n"
        "Пример: <code>123456789 100</code>"
    )
    await state.set_state(AdminStates.add_balance)
    await callback.answer()

@dp.message(AdminStates.add_balance)
async def process_add_balance(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    
    try:
        user_id, amount = message.text.split()
        user_id = int(user_id)
        amount = float(amount)
        
        update_balance(user_id, amount)
        await message.answer(f"✅ Баланс пользователя {user_id} пополнен на {amount:.2f}$")
        
        # Уведомляем пользователя
        try:
            await bot.send_message(
                user_id,
                f"{premium_emoji(PREMIUM_EMOJIS['balance'], '💰')} Ваш баланс был пополнен на {amount:.2f}$"
            )
        except:
            pass
        
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")
    
    await state.clear()

@dp.callback_query(F.data == "admin_giveaway")
async def admin_giveaway(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Нет доступа", show_alert=True)
        return
    
    await callback.message.edit_text(
        "🎁 <b>Раздача денег</b>\n\n"
        "Введи сумму раздачи (например: 0.1)"
    )
    await state.set_state(AdminStates.giveaway_amount)
    await callback.answer()

@dp.message(AdminStates.giveaway_amount)
async def process_giveaway(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    
    try:
        amount = float(message.text)
        
        giveaway_text = (
            f"{premium_emoji(PREMIUM_EMOJIS['prize'], '🎁')} <b>Ежемесячная раздача!</b>\n\n"
            f"Забери свой фрибет по кнопке!\n"
            f"<b>Размер фрибета: {amount:.2f}$</b>"
        )
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🎁 Забрать", callback_data=f"claim_giveaway_{amount}")]
        ])
        
        users = get_all_users()
        sent = 0
        
        await message.answer(f"🎁 Начинаю раздачу {len(users)} пользователям...")
        
        for user_id in users:
            try:
                await bot.send_message(user_id, giveaway_text, reply_markup=keyboard)
                sent += 1
                await asyncio.sleep(0.05)
            except Exception as e:
                print(f"Ошибка отправки пользователю {user_id}: {e}")
        
        await message.answer(f"✅ Раздача отправлена {sent} пользователям")
        
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")
    
    await state.clear()

@dp.callback_query(F.data.startswith("claim_giveaway_"))
async def claim_giveaway(callback: types.CallbackQuery):
    amount = float(callback.data.split("_")[2])
    user_id = callback.from_user.id
    
    # Проверяем, не забирал ли уже
    conn = sqlite3.connect('bot_database.db')
    c = conn.cursor()
    c.execute("SELECT * FROM giveaways WHERE user_id = ? AND amount = ?", (user_id, amount))
    if c.fetchone():
        await callback.answer("Ты уже забрал эту раздачу!", show_alert=True)
        conn.close()
        return
    
    # Начисляем бонус
    update_balance(user_id, amount)
    
    # Записываем в историю
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute("INSERT INTO giveaways (user_id, amount, claimed_at) VALUES (?, ?, ?)",
              (user_id, amount, now))
    conn.commit()
    conn.close()
    
    await callback.message.edit_text(
        f"{premium_emoji(PREMIUM_EMOJIS['win'], '🎉')} <b>Поздравляем!</b>\n\n"
        f"Ты получил {amount:.2f}$ на баланс!\n\n"
        f"{premium_emoji(PREMIUM_EMOJIS['balance'], '💰')} Текущий баланс: {get_balance(user_id):.2f}$"
    )
    await callback.answer()

# Заглушка для нереализованных функций
@dp.callback_query(F.data == "admin_reduce_balance")
@dp.callback_query(F.data == "admin_write")
@dp.callback_query(F.data == "claim_ref")
@dp.callback_query(F.data == "ignore")
async def not_implemented(callback: types.CallbackQuery):
    await callback.answer("🚧 В разработке", show_alert=True)

# Запуск бота
async def main():
    try:
        print("🤖 Бот запускается...")
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    except Exception as e:
        print(f"❌ Ошибка при запуске бота: {e}")
    finally:
        await bot.session.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Бот остановлен")
