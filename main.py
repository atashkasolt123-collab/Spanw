import logging
import random
import re
import asyncio
import sqlite3
import os
from typing import Dict, List, Tuple, Set, Any
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Dice
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters
from datetime import datetime, timedelta
import threading
import time

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Токен бота
TOKEN = "7979153629:AAFDc8hILEVuQ7lyDrVBIOX1ddLqzp3WcLw"

# ID администратора
ADMIN_ID = 7313407194
ADMIN_USERNAME = "@pensiya_get"

# Минимальные суммы (ОБНОВЛЕНО)
MIN_DEPOSIT = 25  # Минимальное пополнение
MIN_WITHDRAWAL = 750  # Минимальный вывод
MIN_TRANSFER_AMOUNT = 10  # Минимальный перевод между пользователями

# Глобальные счетчики
game_counter = 0
games_history: Dict[int, Dict] = {}

# Хранилище данных для игрового процесса
game_data: Dict[int, Dict] = {}
user_bets: Dict[int, int] = {}

# Хранилище заявок на вывод
withdrawal_requests: Dict[int, Dict] = {}

# Константы игры
INITIAL_BALANCE = 0  # НАЧАЛЬНЫЙ БАЛАНС 0₽
MIN_BET = 25
GRID_SIZE = 5
TOTAL_CELLS = GRID_SIZE * GRID_SIZE
MIN_MINES = 2
MAX_MINES = 2

# Множители
MULTIPLIERS = {
    2: 1.12
}

# Множители для игры в кубы
DICE_MULTIPLIERS = {
    "even_odd": 2.0,  # Чет/Нечет
    "number": 6.0,    # Угадать число
    "high_low": 2.0   # Больше/Меньше
}

# Комиссия за перевод (в процентах)
TRANSFER_FEE_PERCENT = 0  # 0% комиссия

# Таймер для ежедневных наград топ-игрокам
DAILY_TOP_REWARD = 100  # 100₽ для каждого из топ-3
LAST_DAILY_REWARD_DATE = None

# ========== БАЗА ДАННЫХ SQLite ==========
class Database:
    def __init__(self, db_name="casino.db"):
        self.db_name = db_name
        self.init_database()
    
    def init_database(self):
        """Инициализация базы данных"""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()
        
        # Таблица пользователей
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            balance INTEGER DEFAULT 0,
            total_won INTEGER DEFAULT 0,
            total_games INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')
        
        # Таблица транзакций (пополнения/выводы)
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            amount INTEGER,
            type TEXT,  -- 'deposit', 'withdrawal', 'win', 'loss', 'transfer_in', 'transfer_out', 'daily_reward'
            description TEXT,
            admin_id INTEGER,
            status TEXT DEFAULT 'completed',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        )
        ''')
        
        # Таблица игр
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS games (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            game_type TEXT,  -- 'mines', 'dice'
            bet_amount INTEGER,
            result TEXT,  -- 'win', 'loss', 'cashout'
            win_amount INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        )
        ''')
        
        # Таблица переводов между пользователями
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS transfers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            from_user_id INTEGER,
            to_user_id INTEGER,
            amount INTEGER,
            fee INTEGER DEFAULT 0,
            net_amount INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (from_user_id) REFERENCES users (user_id),
            FOREIGN KEY (to_user_id) REFERENCES users (user_id)
        )
        ''')
        
        # Таблица ежедневных наград
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS daily_rewards (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            reward_amount INTEGER,
            rank INTEGER,
            reward_date DATE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        )
        ''')
        
        conn.commit()
        conn.close()
    
    def get_connection(self):
        """Получить соединение с базой данных"""
        return sqlite3.connect(self.db_name)
    
    def get_user(self, user_id: int):
        """Получить пользователя из базы данных"""
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
        user = cursor.fetchone()
        conn.close()
        
        if user:
            return {
                'user_id': user[0],
                'username': user[1],
                'first_name': user[2],
                'balance': user[3],
                'total_won': user[4],
                'total_games': user[5],
                'created_at': user[6],
                'updated_at': user[7]
            }
        return None
    
    def create_user(self, user_id: int, username: str, first_name: str):
        """Создать нового пользователя"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Проверяем, существует ли пользователь
        cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
        if not cursor.fetchone():
            cursor.execute('''
            INSERT INTO users (user_id, username, first_name, balance)
            VALUES (?, ?, ?, ?)
            ''', (user_id, username, first_name, INITIAL_BALANCE))
            conn.commit()
        
        conn.close()
    
    def update_user_balance(self, user_id: int, amount: int, transaction_type: str, 
                          description: str = "", admin_id: int = None):
        """Обновить баланс пользователя и создать запись о транзакции"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Получаем текущий баланс
        cursor.execute('SELECT balance FROM users WHERE user_id = ?', (user_id,))
        result = cursor.fetchone()
        
        if not result:
            conn.close()
            return False
        
        current_balance = result[0]
        new_balance = current_balance + amount
        
        # Обновляем баланс
        cursor.execute('''
        UPDATE users 
        SET balance = ?, updated_at = CURRENT_TIMESTAMP 
        WHERE user_id = ?
        ''', (new_balance, user_id))
        
        # Обновляем статистику если это выигрыш
        if transaction_type == 'win':
            cursor.execute('''
            UPDATE users 
            SET total_won = total_won + ?, total_games = total_games + 1 
            WHERE user_id = ?
            ''', (amount, user_id))
        elif transaction_type == 'loss':
            cursor.execute('''
            UPDATE users 
            SET total_games = total_games + 1 
            WHERE user_id = ?
            ''', (user_id,))
        
        # Создаем запись о транзакции
        cursor.execute('''
        INSERT INTO transactions (user_id, amount, type, description, admin_id)
        VALUES (?, ?, ?, ?, ?)
        ''', (user_id, amount, transaction_type, description, admin_id))
        
        conn.commit()
        conn.close()
        return True
    
    def get_user_balance(self, user_id: int):
        """Получить баланс пользователя"""
        user = self.get_user(user_id)
        if user:
            return user['balance']
        return INITIAL_BALANCE
    
    def get_transaction_history(self, user_id: int, limit: int = 10):
        """Получить историю транзакций пользователя"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
        SELECT amount, type, description, created_at 
        FROM transactions 
        WHERE user_id = ? 
        ORDER BY created_at DESC 
        LIMIT ?
        ''', (user_id, limit))
        
        transactions = cursor.fetchall()
        conn.close()
        
        return [
            {
                'amount': t[0],
                'type': t[1],
                'description': t[2],
                'date': t[3]
            }
            for t in transactions
        ]
    
    def get_total_deposits(self, user_id: int):
        """Получить общую сумму пополнений пользователя"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
        SELECT COALESCE(SUM(amount), 0) 
        FROM transactions 
        WHERE user_id = ? AND type = 'deposit' AND status = 'completed'
        ''', (user_id,))
        
        total = cursor.fetchone()[0]
        conn.close()
        return total
    
    def get_total_withdrawals(self, user_id: int):
        """Получить общую сумму выводов пользователя"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
        SELECT COALESCE(SUM(amount), 0) 
        FROM transactions 
        WHERE user_id = ? AND type = 'withdrawal' AND status = 'completed'
        ''', (user_id,))
        
        total = cursor.fetchone()[0]
        conn.close()
        return total
    
    def record_game(self, user_id: int, game_type: str, bet_amount: int, 
                   result: str, win_amount: int = 0):
        """Записать результат игры"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
        INSERT INTO games (user_id, game_type, bet_amount, result, win_amount)
        VALUES (?, ?, ?, ?, ?)
        ''', (user_id, game_type, bet_amount, result, win_amount))
        
        conn.commit()
        conn.close()
    
    def record_transfer(self, from_user_id: int, to_user_id: int, 
                       amount: int, fee: int, net_amount: int):
        """Записать перевод между пользователями"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
        INSERT INTO transfers (from_user_id, to_user_id, amount, fee, net_amount)
        VALUES (?, ?, ?, ?, ?)
        ''', (from_user_id, to_user_id, amount, fee, net_amount))
        
        conn.commit()
        conn.close()
    
    def get_top_users_by_balance(self, limit: int = 10):
        """Получить топ пользователей по балансу"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
        SELECT user_id, username, first_name, balance, total_won, total_games 
        FROM users 
        WHERE balance > 0 
        ORDER BY balance DESC 
        LIMIT ?
        ''', (limit,))
        
        users = cursor.fetchall()
        conn.close()
        
        return [
            {
                'user_id': u[0],
                'username': u[1],
                'first_name': u[2],
                'balance': u[3],
                'total_won': u[4],
                'total_games': u[5]
            }
            for u in users
        ]
    
    def get_top_users_by_wins(self, limit: int = 10):
        """Получить топ пользователей по выигрышам"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
        SELECT user_id, username, first_name, balance, total_won, total_games 
        FROM users 
        WHERE total_won > 0 
        ORDER BY total_won DESC 
        LIMIT ?
        ''', (limit,))
        
        users = cursor.fetchall()
        conn.close()
        
        return [
            {
                'user_id': u[0],
                'username': u[1],
                'first_name': u[2],
                'balance': u[3],
                'total_won': u[4],
                'total_games': u[5]
            }
            for u in users
        ]
    
    def check_daily_reward_given(self, date_str: str):
        """Проверить, выдавались ли награды за указанную дату"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
        SELECT COUNT(*) FROM daily_rewards WHERE reward_date = ?
        ''', (date_str,))
        
        count = cursor.fetchone()[0]
        conn.close()
        return count > 0
    
    def give_daily_top_rewards(self, date_str: str):
        """Выдать ежедневные награды топ-3 игрокам"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Получаем топ-3 по балансу
        cursor.execute('''
        SELECT user_id, username, balance 
        FROM users 
        WHERE balance > 0 
        ORDER BY balance DESC 
        LIMIT 3
        ''', )
        
        top_users = cursor.fetchall()
        
        if not top_users:
            conn.close()
            return []
        
        rewarded_users = []
        rank = 1
        
        for user in top_users:
            user_id = user[0]
            username = user[1]
            balance = user[2]
            
            # Добавляем награду
            cursor.execute('''
            INSERT INTO daily_rewards (user_id, reward_amount, rank, reward_date)
            VALUES (?, ?, ?, ?)
            ''', (user_id, DAILY_TOP_REWARD, rank, date_str))
            
            # Обновляем баланс
            cursor.execute('''
            UPDATE users SET balance = balance + ? WHERE user_id = ?
            ''', (DAILY_TOP_REWARD, user_id))
            
            # Записываем транзакцию
            cursor.execute('''
            INSERT INTO transactions (user_id, amount, type, description)
            VALUES (?, ?, ?, ?)
            ''', (user_id, DAILY_TOP_REWARD, 'daily_reward', f'Ежедневная награда за {rank} место в топе'))
            
            rewarded_users.append({
                'user_id': user_id,
                'username': username,
                'rank': rank,
                'reward': DAILY_TOP_REWARD,
                'new_balance': balance + DAILY_TOP_REWARD
            })
            
            rank += 1
        
        conn.commit()
        conn.close()
        return rewarded_users

# Инициализируем базу данных
db = Database()

# ========== ФУНКЦИИ РАБОТЫ С БАЗОЙ ДАННЫХ ==========
def get_or_create_user(user_id: int, username: str = "", first_name: str = ""):
    """Получить или создать пользователя"""
    user = db.get_user(user_id)
    if not user:
        db.create_user(user_id, username, first_name)
        user = db.get_user(user_id)
    return user

def get_balance(user_id: int):
    """Получить баланс пользователя"""
    return db.get_user_balance(user_id)

def update_balance(user_id: int, amount: int, transaction_type: str, 
                  description: str = "", admin_id: int = None):
    """Обновить баланс пользователя"""
    return db.update_user_balance(user_id, amount, transaction_type, description, admin_id)

def get_transaction_stats(user_id: int):
    """Получить статистику транзакций пользователя"""
    total_deposits = db.get_total_deposits(user_id)
    total_withdrawals = db.get_total_withdrawals(user_id)
    return total_deposits, total_withdrawals

# ========== КОМАНДА /RESERVE - КАЗНА БОТА ==========
async def reserve_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает казну бота (случайную сумму)"""
    user_id = update.effective_user.id
    
    # Генерируем случайную сумму для казны
    reserve_amount = random.randint(100000, 500000)  # от 100к до 500к
    
    # Создаем красивый вывод
    reserve_text = f"""
<b>💰 Казна бота</b>

💎 <b>Баланс казны:</b> {reserve_amount:,}₽

📊 <b>Информация:</b>
Казна бота пополняется за счет комиссий с игр и пополнений.
Средства из казны используются для выплат выигрышей и бонусов.

💡 <b>Для пополнения/вывода:</b>
Обращайтесь к администратору {ADMIN_USERNAME}
    """
    
    keyboard = [
        [InlineKeyboardButton(f"Связаться с {ADMIN_USERNAME}", url=f"https://t.me/{ADMIN_USERNAME[1:]}")],
        [InlineKeyboardButton("Обновить", callback_data="refresh_reserve")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        reserve_text,
        parse_mode='HTML',
        reply_markup=reply_markup
    )

# ========== КОМАНДА /TOP - ТОП ИГРОКОВ ==========
async def top_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает топ игроков по балансу"""
    user_id = update.effective_user.id
    
    # Получаем топ-10 по балансу
    top_by_balance = db.get_top_users_by_balance(10)
    
    # Получаем топ-5 по выигрышам
    top_by_wins = db.get_top_users_by_wins(5)
    
    # Формируем текст топа по балансу
    top_balance_text = ""
    if top_by_balance:
        for i, user in enumerate(top_by_balance, 1):
            username = user['username'] or user['first_name'] or f"ID: {user['user_id']}"
            emoji = "👑" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
            top_balance_text += f"{emoji} {username}: <b>{user['balance']:,}₽</b>\n"
    else:
        top_balance_text = "Пока никто не пополнил баланс 😔\n"
    
    # Формируем текст топа по выигрышам
    top_wins_text = ""
    if top_by_wins:
        for i, user in enumerate(top_by_wins[:5], 1):
            username = user['username'] or user['first_name'] or f"ID: {user['user_id']}"
            emoji = "🏆" if i == 1 else "🎖️" if i == 2 else "⭐" if i == 3 else f"{i}."
            games_count = user['total_games']
            win_rate = (user['total_won'] / (user['total_won'] + games_count * 100)) * 100 if games_count > 0 else 0
            top_wins_text += f"{emoji} {username}: <b>{user['total_won']:,}₽</b> ({games_count} игр)\n"
    else:
        top_wins_text = "Пока никто не выигрывал 😔\n"
    
    # Проверяем, выдавались ли сегодня награды
    today_str = datetime.now().strftime("%Y-%m-%d")
    rewards_given_today = db.check_daily_reward_given(today_str)
    
    reward_info = "✅ Сегодня награды уже выданы" if rewards_given_today else "⏳ Награды будут выданы сегодня"
    
    top_text = f"""
<b>🏆 Топ игроков Spindja Casino</b>

💰 <b>Топ по балансу:</b>
{top_balance_text}

🎯 <b>Топ по выигрышам:</b>
{top_wins_text}

🎁 <b>Ежедневные награды:</b>
Каждый день топ-3 игрока по балансу получают по <b>100₽</b>
{reward_info}

📅 Следующая раздача наград: <b>завтра в 00:00</b>

💡 <b>Как попасть в топ?</b>
• Пополняйте баланс
• Играйте и выигрывайте
• Переводите средства друзьям
    """
    
    keyboard = [
        [InlineKeyboardButton("Мой баланс", callback_data="balance")],
        [InlineKeyboardButton("Пополнить баланс", callback_data="deposit")],
        [InlineKeyboardButton("Казна бота", callback_data="show_reserve")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        top_text,
        parse_mode='HTML',
        reply_markup=reply_markup
    )

# ========== ЕЖЕДНЕВНЫЕ НАГРАДЫ ТОП-ИГРОКАМ ==========
async def check_and_give_daily_rewards(context: ContextTypes.DEFAULT_TYPE):
    """Проверяет и выдает ежедневные награды топ-игрокам"""
    try:
        today_str = datetime.now().strftime("%Y-%m-%d")
        
        # Проверяем, выдавались ли уже награды сегодня
        if not db.check_daily_reward_given(today_str):
            # Выдаем награды
            rewarded_users = db.give_daily_top_rewards(today_str)
            
            if rewarded_users:
                # Уведомляем администратора
                admin_message = "🎉 <b>Ежедневные награды выданы!</b>\n\n"
                for user in rewarded_users:
                    admin_message += f"{user['rank']}. @{user['username'] or 'Аноним'}: +{user['reward']}₽ (Баланс: {user['new_balance']}₽)\n"
                
                try:
                    await context.bot.send_message(
                        chat_id=ADMIN_ID,
                        text=admin_message,
                        parse_mode='HTML'
                    )
                except:
                    pass
                
                # Уведомляем пользователей
                for user in rewarded_users:
                    try:
                        await context.bot.send_message(
                            chat_id=user['user_id'],
                            text=f"🎁 <b>Поздравляем!</b>\n\n"
                                 f"Вы заняли {user['rank']}-е место в ежедневном топе и получаете награду <b>{user['reward']}₽</b>!\n"
                                 f"Ваш новый баланс: <b>{user['new_balance']}₽</b>\n\n"
                                 f"Спасибо за игру в Spindja Casino! 🎰",
                            parse_mode='HTML'
                        )
                    except:
                        pass
                
                logger.info(f"Ежедневные награды выданы для {len(rewarded_users)} пользователей")
            else:
                logger.info("Нет пользователей для выдачи ежедневных наград")
    except Exception as e:
        logger.error(f"Ошибка при выдаче ежедневных наград: {e}")

# ========== ОБРАБОТЧИКИ КОМАНД ==========
# Обработчик команды /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отправляет приветственное сообщение с кнопками"""
    user_id = update.effective_user.id
    username = update.effective_user.username or update.effective_user.first_name
    first_name = update.effective_user.first_name
    
    # Получаем или создаем пользователя в БД
    get_or_create_user(user_id, username, first_name)
    
    balance = get_balance(user_id)
    
    keyboard = [
        [InlineKeyboardButton("Играть", callback_data="play_menu")],
        [InlineKeyboardButton("Баланс", callback_data="balance")],
        [InlineKeyboardButton("Топ игроков", callback_data="show_top")],
        [InlineKeyboardButton("Казна бота", callback_data="show_reserve")],
        [InlineKeyboardButton("Вывести средства", callback_data="withdraw_menu")],
        [InlineKeyboardButton("Пополнить баланс", callback_data="deposit")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    welcome_text = f"""
<b>🎰 Добро пожаловать в Spindja Casino!</b>

Мы рады видеть вас в нашем казино!

🎮 <b>Ваш баланс:</b> {balance}₽

🎁 <b>Новое:</b> Ежедневные награды топ-3 игрокам по 100₽!

<u>Доступные команды:</u>
• <code>/balance</code> / <code>/bal</code> / <code>/b</code> - показать баланс
• <code>/top</code> - топ игроков по балансу
• <code>/reserve</code> - казна бота
• <code>/pay сумма</code> - перевести другу (ответом на сообщение)
• <code>/pay ID сумма</code> - перевести по ID пользователя
• Напишите <code>мины</code> - игра в мины
• Напишите <code>кубы</code> - игра в кубы
• <code>/chet сумма</code> - ставка на чет (2,4,6) - x2
• <code>/nechet сумма</code> - ставка на нечет (1,3,5) - x2
• <code>/number число сумма</code> - ставка на число (1-6) - x6
• <code>/more сумма</code> - ставка на больше (4-6) - x2
• <code>/less сумма</code> - ставка на меньше (1-3) - x2
    """
    
    await update.message.reply_text(
        welcome_text,
        parse_mode='HTML',
        reply_markup=reply_markup
    )

# Команда для проверки баланса
async def balance_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает баланс пользователя"""
    user_id = update.effective_user.id
    username = update.effective_user.username or update.effective_user.first_name
    first_name = update.effective_user.first_name
    
    # Получаем или создаем пользователя в БД
    get_or_create_user(user_id, username, first_name)
    
    await show_balance_message(update.message, user_id)

async def show_balance_message(message, user_id: int):
    """Показывает баланс пользователя"""
    balance = get_balance(user_id)
    
    # Рассчитываем общие суммы
    total_deposits, total_withdrawals = get_transaction_stats(user_id)
    
    saved_bet = user_bets.get(user_id, None)
    bet_info = f"\n💾 Сохраненная ставка: {saved_bet}₽" if saved_bet else ""
    
    balance_text = f"""
<b>💰 Ваш баланс</b>

📊 Текущий баланс: <b>{balance}₽</b>{bet_info}

📈 <u>Статистика:</u>
• Всего пополнено: <b>{total_deposits}₽</b>
• Всего выведено: <b>{total_withdrawals}₽</b>

🎮 <u>Минимальные суммы:</u>
• Все игры: {MIN_BET}₽
• Переводы: {MIN_TRANSFER_AMOUNT}₽
• Пополнение: от {MIN_DEPOSIT}₽
• Вывод: от {MIN_WITHDRAWAL}₽

🎲 <u>Доступные игры:</u>
• <b>Мины</b> - 2 мины, множитель 1.12x
• <b>Кубы</b> - несколько режимов игры

💸 <u>Переводы:</u>
Используйте <code>/pay сумма</code> для переводов друзьям!

🎁 <u>Ежедневные награды:</u>
Топ-3 игрока по балансу каждый день получают по 100₽!
    """
    
    keyboard = [
        [InlineKeyboardButton("Пополнить баланс", callback_data="deposit")],
        [InlineKeyboardButton("Вывести средства", callback_data="withdraw_menu")],
        [InlineKeyboardButton("Топ игроков", callback_data="show_top")],
        [InlineKeyboardButton("Меню игр", callback_data="play_menu")],
        [InlineKeyboardButton("Назад", callback_data="back_to_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await message.reply_text(
        balance_text,
        parse_mode='HTML',
        reply_markup=reply_markup
    )

# Меню пополнения баланса
async def deposit_menu(query, user_id):
    """Меню пополнения баланса"""
    balance = get_balance(user_id)
    
    keyboard = [
        [InlineKeyboardButton(f"Связаться с {ADMIN_USERNAME}", url=f"https://t.me/{ADMIN_USERNAME[1:]}")],
        [InlineKeyboardButton("Назад", callback_data="balance")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    deposit_text = f"""
<b>💰 Пополнение баланса</b>

💳 Ваш текущий баланс: <b>{balance}₽</b>

<u>Требования к пополнению:</u>
• Минимальная сумма: <b>{MIN_DEPOSIT}₽</b>
• Пополнение через администратора: {ADMIN_USERNAME}

💎 <b>Доступные способы пополнения:</b>
1. <b>Криптовалюта</b> (USDT, BTC, ETH) - через CryptoBot
2. <b>Банковские карты</b> РФ
3. <b>QIWI</b> / <b>ЮMoney</b>

📞 <b>Инструкция по пополнению:</b>
1. Нажмите кнопку ниже для связи с администратором
2. Укажите ваш ID: <code>{user_id}</code>
3. Укажите желаемую сумму пополнения (от {MIN_DEPOSIT}₽)
4. Выберите способ оплаты
5. Дождитесь подтверждения от администратора

⏱️ Пополнение происходит в течение 5-15 минут после подтверждения.
    """
    
    await query.edit_message_text(
        text=deposit_text,
        parse_mode='HTML',
        reply_markup=reply_markup
    )

# Меню вывода средств
async def withdraw_menu(query, user_id):
    """Меню вывода средств"""
    balance = get_balance(user_id)
    
    keyboard = [
        [InlineKeyboardButton(f"Связаться с {ADMIN_USERNAME}", url=f"https://t.me/{ADMIN_USERNAME[1:]}")],
        [InlineKeyboardButton("Назад", callback_data="balance")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    withdraw_text = f"""
<b>💸 Вывод средств</b>

💳 Ваш текущий баланс: <b>{balance}₽</b>

<u>Требования к выводу:</u>
• Минимальная сумма вывода: <b>{MIN_WITHDRAWAL}₽</b>
• Вывод через администратора: {ADMIN_USERNAME}

💎 <b>Доступные способы вывода:</b>
1. <b>Криптовалюта</b> (USDT через CryptoBot) - приоритетный способ
2. <b>Банковские карты</b> РФ
3. <b>QIWI</b> / <b>ЮMoney</b>

📋 <b>Инструкция по выводу:</b>
1. Нажмите кнопку ниже для связи с администратором
2. Укажите ваш ID: <code>{user_id}</code>
3. Укажите сумму вывода (от {MIN_WITHDRAWAL}₽)
4. Выберите способ получения средств
5. Укажите реквизиты (адрес кошелька/номер карты)
6. Дождитесь подтверждения и получения средств

⏱️ Вывод происходит в течение 5-30 минут после подтверждения.

⚠️ <b>Внимание:</b> При выводе на криптокошельки через CryptoBot возможны дополнительные комиссии сети.
    """
    
    await query.edit_message_text(
        text=withdraw_text,
        parse_mode='HTML',
        reply_markup=reply_markup
    )

# Команда для переводов /pay
async def pay_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Перевод средств другому пользователю"""
    user_id = update.effective_user.id
    username = update.effective_user.username or update.effective_user.first_name
    first_name = update.effective_user.first_name
    
    # Получаем или создаем отправителя в БД
    get_or_create_user(user_id, username, first_name)
    
    # Проверяем, является ли сообщение ответом на другое сообщение
    reply_to_message = update.message.reply_to_message
    
    if reply_to_message:
        # Перевод ответом на сообщение
        target_user = reply_to_message.from_user
        
        if target_user.id == user_id:
            await update.message.reply_text("❌ Нельзя переводить деньги самому себе!")
            return
        
        if not context.args:
            await update.message.reply_text(
                "❌ Укажите сумму перевода.\n"
                "Используйте: <code>/pay сумма</code>\n"
                "Например: <code>/pay 100</code>",
                parse_mode='HTML'
            )
            return
        
        try:
            amount = int(context.args[0])
        except ValueError:
            await update.message.reply_text("❌ Неверный формат суммы.")
            return
        
        # Получаем информацию о получателе
        target_id = target_user.id
        target_username = target_user.username or target_user.first_name
        target_first_name = target_user.first_name
        
    else:
        # Перевод по ID
        if len(context.args) < 2:
            await update.message.reply_text(
                "❌ Неправильный формат команды.\n\n"
                "<u>Способ 1 (ответом на сообщение):</u>\n"
                "Ответьте на сообщение друга: <code>/pay сумма</code>\n\n"
                "<u>Способ 2 (по ID):</u>\n"
                "<code>/pay ID_пользователя сумма</code>\n\n"
                "Например: <code>/pay 123456789 100</code>",
                parse_mode='HTML'
            )
            return
        
        # Пытаемся определить получателя
        target_arg = context.args[0]
        try:
            amount = int(context.args[1])
        except ValueError:
            await update.message.reply_text("❌ Неверный формат суммы.")
            return
        
        # Пробуем получить ID из аргумента
        if target_arg.isdigit():
            # Это числовой ID
            target_id = int(target_arg)
            target_username = f"пользователь {target_id}"
            target_first_name = f"Пользователь {target_id}"
        else:
            await update.message.reply_text("❌ Неверный формат получателя. Используйте числовой ID.")
            return
        
        if target_id == user_id:
            await update.message.reply_text("❌ Нельзя переводить деньги самому себе!")
            return
        
        # Создаем получателя в БД, если он не существует
        get_or_create_user(target_id, target_username, target_first_name)
    
    # Проверяем сумму перевода
    if amount < MIN_TRANSFER_AMOUNT:
        await update.message.reply_text(f"❌ Минимальная сумма перевода: {MIN_TRANSFER_AMOUNT}₽")
        return
    
    # Проверяем баланс отправителя
    sender_balance = get_balance(user_id)
    if sender_balance < amount:
        await update.message.reply_text(
            f"❌ Недостаточно средств для перевода.\n"
            f"Ваш баланс: {sender_balance}₽\n"
            f"Сумма перевода: {amount}₽",
            parse_mode='HTML'
        )
        return
    
    # Рассчитываем комиссию
    fee = int(amount * TRANSFER_FEE_PERCENT / 100)
    net_amount = amount - fee
    
    # Выполняем перевод в базе данных
    # Списание у отправителя
    update_balance(
        user_id, 
        -amount, 
        'transfer_out', 
        f"Перевод пользователю {target_id} ({target_username})",
        None
    )
    
    # Зачисление получателю
    update_balance(
        target_id, 
        net_amount, 
        'transfer_in', 
        f"Перевод от пользователя {user_id} ({username})",
        None
    )
    
    # Записываем перевод в отдельную таблицу
    db.record_transfer(user_id, target_id, amount, fee, net_amount)
    
    # Сообщение об успешном переводе
    transfer_text = f"""
✅ <b>Перевод выполнен успешно!</b>

📤 <u>Отправитель:</u>
👤 {username} (ID: {user_id})
💰 Списано: {amount}₽
💸 Комиссия: {fee}₽ ({TRANSFER_FEE_PERCENT}%)
📊 Новый баланс: {get_balance(user_id)}₽

📥 <u>Получатель:</u>
👤 {target_username} (ID: {target_id})
💰 Получено: {net_amount}₽
📊 Новый баланс: {get_balance(target_id)}₽

🕒 Перевод мгновенный
    """
    
    await update.message.reply_text(
        transfer_text,
        parse_mode='HTML'
    )
    
    # Уведомляем получателя
    try:
        await context.bot.send_message(
            chat_id=target_id,
            text=f"🎉 <b>Вам поступил перевод!</b>\n\n"
                 f"📤 От: {username} (ID: {user_id})\n"
                 f"💰 Сумма: {net_amount}₽\n"
                 f"💸 Комиссия: {fee}₽\n"
                 f"📊 Ваш новый баланс: {get_balance(target_id)}₽\n\n"
                 f"💝 Спасибо за использование нашего казино!",
            parse_mode='HTML'
        )
    except Exception as e:
        logger.error(f"Не удалось уведомить получателя {target_id}: {e}")

# Команды для быстрых ставок в кубы
async def dice_even_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Ставка на чет в кубах"""
    user_id = update.effective_user.id
    await process_dice_quick_bet(update, context, user_id, "even")

async def dice_odd_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Ставка на нечет в кубах"""
    user_id = update.effective_user.id
    await process_dice_quick_bet(update, context, user_id, "odd")

async def dice_number_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Ставка на число в кубах"""
    user_id = update.effective_user.id
    
    if len(context.args) != 2:
        await update.message.reply_text(
            "❌ Неправильный формат команды.\n"
            "Используйте: <code>/number число сумма</code>\n"
            "Например: <code>/number 3 100</code>\n\n"
            "<u>Доступные числа:</u> 1, 2, 3, 4, 5, 6",
            parse_mode='HTML'
        )
        return
    
    try:
        number = int(context.args[0])
        amount = int(context.args[1])
        
        if number < 1 or number > 6:
            await update.message.reply_text("❌ Число должно быть от 1 до 6.")
            return
        
        if amount < MIN_BET:
            await update.message.reply_text(f"❌ Минимальная ставка: {MIN_BET}₽")
            return
        
        await process_dice_quick_bet(update, context, user_id, "number", number, amount)
        
    except ValueError:
        await update.message.reply_text("❌ Неверный формат числа или суммы.")

async def dice_high_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Ставка на больше (4-6) в кубах"""
    user_id = update.effective_user.id
    await process_dice_quick_bet(update, context, user_id, "high")

async def dice_low_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Ставка на меньше (1-3) в кубах"""
    user_id = update.effective_user.id
    await process_dice_quick_bet(update, context, user_id, "low")

async def process_dice_quick_bet(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, 
                                 bet_type: str, number: int = None, amount: int = None) -> None:
    """Обрабатывает быстрые ставки в кубы"""
    username = update.effective_user.username or update.effective_user.first_name
    first_name = update.effective_user.first_name
    
    # Получаем или создаем пользователя в БД
    get_or_create_user(user_id, username, first_name)
    
    # Если amount не передан, берем из аргументов
    if amount is None:
        if not context.args:
            await update.message.reply_text(
                f"❌ Укажите сумму ставки.\n"
                f"Например: <code>/{bet_type} 100</code>",
                parse_mode='HTML'
            )
            return
        try:
            amount = int(context.args[0])
        except ValueError:
            await update.message.reply_text("❌ Неверный формат суммы.")
            return
    
    if amount < MIN_BET:
        await update.message.reply_text(f"❌ Минимальная ставка: {MIN_BET}₽")
        return
    
    balance = get_balance(user_id)
    if balance < amount:
        await update.message.reply_text(
            f"❌ Недостаточно средств на балансе.\n"
            f"Ваш баланс: {balance}₽",
            parse_mode='HTML'
        )
        return
    
    # Бросаем куб через Telegram Dice
    dice_message = await update.message.reply_dice(emoji="🎲")
    dice_result = dice_message.dice.value
    
    await asyncio.sleep(2)  # Ждем пока анимация куба завершится
    
    # Определяем выигрыш
    win = False
    multiplier = DICE_MULTIPLIERS["even_odd"]
    bet_name = ""
    
    if bet_type == "even":  # Чет
        bet_name = "чёт"
        win = dice_result in [2, 4, 6]
        multiplier = DICE_MULTIPLIERS["even_odd"]
    elif bet_type == "odd":  # Нечет
        bet_name = "нечёт"
        win = dice_result in [1, 3, 5]
        multiplier = DICE_MULTIPLIERS["even_odd"]
    elif bet_type == "number":  # Число
        bet_name = f"число {number}"
        win = dice_result == number
        multiplier = DICE_MULTIPLIERS["number"]
    elif bet_type == "high":  # Больше (4-6)
        bet_name = "больше (4-6)"
        win = dice_result in [4, 5, 6]
        multiplier = DICE_MULTIPLIERS["high_low"]
    elif bet_type == "low":  # Меньше (1-3)
        bet_name = "меньше (1-3)"
        win = dice_result in [1, 2, 3]
        multiplier = DICE_MULTIPLIERS["high_low"]
    
    # Обрабатываем результат
    if win:
        win_amount = int(amount * multiplier)
        update_balance(user_id, win_amount, 'win', f"Выигрыш в кубах: {bet_name}")
        db.record_game(user_id, 'dice', amount, 'win', win_amount)
        
        result_text = f"""
🎲 <b>Кубы - Быстрая ставка</b>

🎯 Ваша ставка: <b>{bet_name}</b>
💰 Сумма: <b>{amount}₽</b>
🎲 Результат: <b>{dice_result}</b>

✅ <b>ВЫИГРЫШ!</b>
🏆 Выигрыш: <b>{win_amount}₽</b> (x{multiplier})
💰 Новый баланс: <b>{get_balance(user_id)}₽</b>

🎉 Поздравляем с выигрышем!
        """
    else:
        update_balance(user_id, -amount, 'loss', f"Проигрыш в кубах: {bet_name}")
        db.record_game(user_id, 'dice', amount, 'loss', 0)
        
        result_text = f"""
🎲 <b>Кубы - Быстрая ставка</b>

🎯 Ваша ставка: <b>{bet_name}</b>
💰 Сумма: <b>{amount}₽</b>
🎲 Результат: <b>{dice_result}</b>

❌ <b>ПРОИГРЫШ</b>
💸 Ставка не возвращается
💰 Новый баланс: <b>{get_balance(user_id)}₽</b>

😔 В следующий раз повезет!
        """
    
    # Добавляем клавиатуру с кнопками
    keyboard = [
        [InlineKeyboardButton("Играть в Кубы", callback_data="game_dice")],
        [InlineKeyboardButton("Меню игр", callback_data="play_menu")],
        [InlineKeyboardButton("Баланс", callback_data="balance")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        result_text,
        parse_mode='HTML',
        reply_markup=reply_markup
    )

# Команда для администратора /game
async def game_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает информацию об игре (только для администратора)"""
    user_id = update.effective_user.id
    
    if user_id != ADMIN_ID:
        await update.message.reply_text("❌ У вас нет прав для выполнения этой команды.")
        return
    
    if len(context.args) < 2:
        await update.message.reply_text(
            "❌ Неправильный формат команды.\n"
            "Используйте: <code>/game mines номер_игры</code>\n"
            "Например: <code>/game mines 1</code>\n\n"
            f"Всего сыграно игр: {game_counter}",
            parse_mode='HTML'
        )
        return
    
    game_type = context.args[0].lower()
    try:
        game_num = int(context.args[1])
    except ValueError:
        await update.message.reply_text("❌ Неверный номер игры.")
        return
    
    if game_type != "mines":
        await update.message.reply_text("❌ Доступен только тип 'mines'.")
        return
    
    if game_num not in games_history:
        await update.message.reply_text(f"❌ Игра №{game_num} не найдена.")
        return
    
    game_info = games_history[game_num]
    
    # Генерация поля с минами для администратора
    field_text = ""
    for row in range(GRID_SIZE):
        row_text = ""
        for col in range(GRID_SIZE):
            cell_idx = row * GRID_SIZE + col
            if cell_idx in game_info["mines"]:
                row_text += "💣"
            elif cell_idx in game_info["prizes"]:
                row_text += "🎁"
            else:
                row_text += "⬜"
        field_text += row_text + "\n"
    
    # Преобразуем индексы в координаты (строка, столбец)
    mine_positions = []
    for idx in sorted(game_info["mines"]):
        row = idx // GRID_SIZE + 1
        col = idx % GRID_SIZE + 1
        mine_positions.append(f"({row},{col})")
    
    prize_positions = []
    for idx in sorted(game_info["prizes"]):
        row = idx // GRID_SIZE + 1
        col = idx % GRID_SIZE + 1
        prize_positions.append(f"({row},{col})")
    
    game_details = f"""
<b>Игра №{game_num} - Мины</b>

👤 Игрок: {game_info['user_id']} ({game_info.get('username', 'Неизвестно')})
💰 Ставка: {game_info['bet']}₽
💣 Количество мин: 2 (фиксировано)
🎮 Статус: {game_info.get('status', 'Завершена')}
📅 Время: {game_info.get('time', 'Неизвестно')}

<u>Поле с минами:</u>
{field_text}

<u>Позиции мин (координаты строка,столбец):</u>
{', '.join(mine_positions)}

<u>Позиции мин (индексы 0-24):</u>
{', '.join(map(str, sorted(game_info['mines'])))}

<u>Позиции призов:</u>
{', '.join(map(str, sorted(game_info['prizes'])))}
    """
    
    await update.message.reply_text(
        game_details,
        parse_mode='HTML'
    )

# Команда /givemoney для администратора
async def givemoney(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Выдает баланс пользователю (только для администратора)"""
    user_id = update.effective_user.id
    
    if user_id != ADMIN_ID:
        await update.message.reply_text("❌ У вас нет прав для выполнения этой команды.")
        return
    
    if len(context.args) != 2:
        await update.message.reply_text(
            "❌ Неправильный формат команды.\n"
            "Используйте: <code>/givemoney ID_пользователя сумма</code>\n"
            "Например: <code>/givemoney 123456789 1000</code>",
            parse_mode='HTML'
        )
        return
    
    try:
        target_id = int(context.args[0])
        amount = int(context.args[1])
        
        if amount <= 0:
            await update.message.reply_text("❌ Сумма должна быть положительной.")
            return
        
        # Получаем или создаем пользователя
        target_user = db.get_user(target_id)
        if not target_user:
            # Создаем пользователя
            db.create_user(target_id, f"пользователь {target_id}", f"Пользователь {target_id}")
        
        # Пополняем баланс через БД
        update_balance(
            target_id, 
            amount, 
            'deposit', 
            f"Пополнение баланса администратором {user_id}",
            user_id
        )
        
        await update.message.reply_text(
            f"✅ Баланс пользователя <code>{target_id}</code> пополнен на <b>{amount}₽</b>.\n"
            f"Новый баланс: <b>{get_balance(target_id)}₽</b>",
            parse_mode='HTML'
        )
        
        try:
            await context.bot.send_message(
                chat_id=target_id,
                text=f"🎉 Ваш баланс пополнен на <b>{amount}₽</b> администратором!\n"
                     f"Новый баланс: <b>{get_balance(target_id)}₽</b>",
                parse_mode='HTML'
            )
        except:
            pass
            
    except ValueError:
        await update.message.reply_text("❌ Неверный формат ID или суммы.")

# Команда /delbalance для администратора
async def delbalance(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Снимает баланс с пользователя (только для администратора)"""
    user_id = update.effective_user.id
    
    if user_id != ADMIN_ID:
        await update.message.reply_text("❌ У вас нет прав для выполнения этой команды.")
        return
    
    if len(context.args) != 2:
        await update.message.reply_text(
            "❌ Неправильный формат команды.\n"
            "Используйте: <code>/delbalance ID_пользователя сумма</code>\n"
            "Например: <code>/delbalance 123456789 1000</code>",
            parse_mode='HTML'
        )
        return
    
    try:
        target_id = int(context.args[0])
        amount = int(context.args[1])
        
        if amount <= 0:
            await update.message.reply_text("❌ Сумма должна быть положительной.")
            return
        
        target_user = db.get_user(target_id)
        if not target_user:
            await update.message.reply_text(f"❌ Пользователь с ID {target_id} не найден.")
            return
        
        target_balance = get_balance(target_id)
        if target_balance < amount:
            await update.message.reply_text(
                f"❌ У пользователя недостаточно средств.\n"
                f"Баланс пользователя: {target_balance}₽\n"
                f"Сумма списания: {amount}₽",
                parse_mode='HTML'
            )
            return
        
        # Списание через БД
        update_balance(
            target_id, 
            -amount, 
            'withdrawal', 
            f"Списание баланса администратором {user_id}",
            user_id
        )
        
        await update.message.reply_text(
            f"✅ С пользователя <code>{target_id}</code> списано <b>{amount}₽</b>.\n"
            f"Новый баланс: <b>{get_balance(target_id)}₽</b>",
            parse_mode='HTML'
        )
        
        try:
            await context.bot.send_message(
                chat_id=target_id,
                text=f"⚠️ С вашего баланса списано <b>{amount}₽</b> администратором!\n"
                     f"Новый баланс: <b>{get_balance(target_id)}₽</b>",
                parse_mode='HTML'
            )
        except:
            pass
            
    except ValueError:
        await update.message.reply_text("❌ Неверный формат ID или суммы.")

# Обработчик текстовых сообщений
async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает текстовые сообщения"""
    user_id = update.effective_user.id
    text = update.message.text.strip().lower()
    
    # Если пользователь написал "мины" - запускаем игру
    if text == "мины":
        await start_mines_from_chat(update, user_id)
        return
    
    # Если пользователь написал "кубы" или "кости" - запускаем игру в кубы
    if text in ["кубы", "кости", "dice"]:
        await start_dice_from_chat(update, user_id)
        return
    
    # Проверяем на наличие суммы для ставки
    pattern = r'(\d+)\s*(?:₽|руб|рублей|р)'
    match = re.search(pattern, text)
    
    if match:
        await handle_bet_message(update, user_id, match)
        return

# Запуск игры "Кубы" из чата
async def start_dice_from_chat(update: Update, user_id: int) -> None:
    """Запускает игру Кубы из текстового сообщения"""
    username = update.effective_user.username or update.effective_user.first_name
    first_name = update.effective_user.first_name
    
    # Получаем или создаем пользователя в БД
    get_or_create_user(user_id, username, first_name)
    
    balance = get_balance(user_id)
    
    keyboard = [
        [
            InlineKeyboardButton("Чет/Нечет", callback_data="dice_even_odd"),
            InlineKeyboardButton("Число", callback_data="dice_number")
        ],
        [
            InlineKeyboardButton("Больше/Меньше", callback_data="dice_high_low"),
            InlineKeyboardButton("Назад", callback_data="play_menu")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    setup_text = f"""
<b>🎮 Игра в Кубы</b>

👤 {username}
💰 Баланс: {balance}₽

<u>Выберите тип ставки:</u>

🎲 <b>Чет/Нечет</b>
• Чет (2,4,6): x{DICE_MULTIPLIERS["even_odd"]}
• Нечет (1,3,5): x{DICE_MULTIPLIERS["even_odd"]}

🎯 <b>Число</b>
• Угадать число (1-6): x{DICE_MULTIPLIERS["number"]}

⚖️ <b>Больше/Меньше</b>
• Больше (4-6): x{DICE_MULTIPLIERS["high_low"]}
• Меньше (1-3): x{DICE_MULTIPLIERS["high_low"]}

<u>Быстрые команды:</u>
• <code>/chet сумма</code> - ставка на чет
• <code>/nechet сумма</code> - ставка на нечет
• <code>/number число сумма</code> - ставка на число
• <code>/more сумма</code> - ставка на больше (4-6)
• <code>/less сумма</code> - ставка на меньше (1-3)
    """
    
    await update.message.reply_text(
        text=setup_text,
        parse_mode='HTML',
        reply_markup=reply_markup
    )

# Меню игры в кубы
async def dice_menu(query, user_id):
    """Меню игры в кубы"""
    balance = get_balance(user_id)
    
    keyboard = [
        [
            InlineKeyboardButton("Чет/Нечет", callback_data="dice_even_odd"),
            InlineKeyboardButton("Число", callback_data="dice_number")
        ],
        [
            InlineKeyboardButton("Больше/Меньше", callback_data="dice_high_low"),
            InlineKeyboardButton("Назад", callback_data="play_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    setup_text = f"""
<b>🎮 Игра в Кубы</b>

👤 {query.from_user.username or query.from_user.first_name}
💰 Баланс: {balance}₽
🎲 Минимальная ставка: {MIN_BET}₽

<u>Выберите тип ставки:</u>

🎲 <b>Чет/Нечет</b>
• Чет (2,4,6): x{DICE_MULTIPLIERS["even_odd"]}
• Нечет (1,3,5): x{DICE_MULTIPLIERS["even_odd"]}

🎯 <b>Число</b>
• Угадать число (1-6): x{DICE_MULTIPLIERS["number"]}

⚖️ <b>Больше/Меньше</b>
• Больше (4-6): x{DICE_MULTIPLIERS["high_low"]}
• Меньше (1-3): x{DICE_MULTIPLIERS["high_low"]}
    """
    
    await query.edit_message_text(
        text=setup_text,
        parse_mode='HTML',
        reply_markup=reply_markup
    )

# Чет/Нечет в кубах
async def dice_even_odd(query, user_id):
    """Ставка на чет/нечет в кубах"""
    balance = get_balance(user_id)
    
    keyboard = [
        [
            InlineKeyboardButton("Чет (2,4,6)", callback_data="dice_bet_even"),
            InlineKeyboardButton("Нечет (1,3,5)", callback_data="dice_bet_odd")
        ],
        [InlineKeyboardButton("Назад", callback_data="game_dice")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    setup_text = f"""
<b>🎮 Кубы - Чет/Нечет</b>

💰 Баланс: {balance}₽
🎯 Множитель: x{DICE_MULTIPLIERS["even_odd"]}

<u>Правила:</u>
• Выберите <b>Чет</b> - выигрываете, если выпадет 2, 4 или 6
• Выберите <b>Нечет</b> - выигрываете, если выпадет 1, 3 или 5

🏆 Выигрыш: <b>ставка × {DICE_MULTIPLIERS["even_odd"]}</b>

<u>Быстрая команда:</u>
• <code>/chet сумма</code> - ставка на чет
• <code>/nechet сумма</code> - ставка на нечет
    """
    
    await query.edit_message_text(
        text=setup_text,
        parse_mode='HTML',
        reply_markup=reply_markup
    )

# Угадать число в кубах
async def dice_number(query, user_id):
    """Ставка на число в кубах"""
    balance = get_balance(user_id)
    
    keyboard = [
        [
            InlineKeyboardButton("1", callback_data="dice_bet_num_1"),
            InlineKeyboardButton("2", callback_data="dice_bet_num_2"),
            InlineKeyboardButton("3", callback_data="dice_bet_num_3")
        ],
        [
            InlineKeyboardButton("4", callback_data="dice_bet_num_4"),
            InlineKeyboardButton("5", callback_data="dice_bet_num_5"),
            InlineKeyboardButton("6", callback_data="dice_bet_num_6")
        ],
        [InlineKeyboardButton("Назад", callback_data="game_dice")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    setup_text = f"""
<b>🎮 Кубы - Угадать число</b>

💰 Баланс: {balance}₽
🎯 Множитель: x{DICE_MULTIPLIERS["number"]}

<u>Правила:</u>
• Выберите число от 1 до 6
• Если куб покажет выбранное число - вы выигрываете
• В противном случае - проигрыш

🏆 Выигрыш: <b>ставка × {DICE_MULTIPLIERS["number"]}</b>

<u>Быстрая команда:</u>
• <code>/number число сумма</code>
• Например: <code>/number 3 100</code>
    """
    
    await query.edit_message_text(
        text=setup_text,
        parse_mode='HTML',
        reply_markup=reply_markup
    )

# Больше/Меньше в кубах
async def dice_high_low(query, user_id):
    """Ставка на больше/меньше в кубах"""
    balance = get_balance(user_id)
    
    keyboard = [
        [
            InlineKeyboardButton("Меньше (1-3)", callback_data="dice_bet_low"),
            InlineKeyboardButton("Больше (4-6)", callback_data="dice_bet_high")
        ],
        [InlineKeyboardButton("Назад", callback_data="game_dice")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    setup_text = f"""
<b>🎮 Кубы - Больше/Меньше</b>

💰 Баланс: {balance}₽
🎯 Множитель: x{DICE_MULTIPLIERS["high_low"]}

<u>Правила:</u>
• <b>Меньше</b> - выигрываете, если выпадет 1, 2 или 3
• <b>Больше</b> - выигрываете, если выпадет 4, 5 или 6

🏆 Выигрыш: <b>ставка × {DICE_MULTIPLIERS["high_low"]}</b>

<u>Быстрая команда:</u>
• <code>/less сумма</code> - ставка на 1-3
• <code>/more сумма</code> - ставка на 4-6
    """
    
    await query.edit_message_text(
        text=setup_text,
        parse_mode='HTML',
        reply_markup=reply_markup
    )

# Обработка ставки в кубах
async def process_dice_bet(query, user_id, bet_type: str, bet_value: str = None):
    """Обрабатывает ставку в кубах"""
    # Сохраняем данные ставки
    saved_bet = user_bets.get(user_id, MIN_BET)
    game_data[user_id] = {
        "game_type": "dice",
        "bet_type": bet_type,
        "bet_value": bet_value,
        "amount": saved_bet
    }
    
    balance = get_balance(user_id)
    
    # Определяем описание ставки
    bet_description = ""
    if bet_type == "even":
        bet_description = "Чет (2,4,6)"
        multiplier = DICE_MULTIPLIERS["even_odd"]
    elif bet_type == "odd":
        bet_description = "Нечет (1,3,5)"
        multiplier = DICE_MULTIPLIERS["even_odd"]
    elif bet_type == "number":
        bet_description = f"Число {bet_value}"
        multiplier = DICE_MULTIPLIERS["number"]
    elif bet_type == "high":
        bet_description = "Больше (4-6)"
        multiplier = DICE_MULTIPLIERS["high_low"]
    elif bet_type == "low":
        bet_description = "Меньше (1-3)"
        multiplier = DICE_MULTIPLIERS["high_low"]
    else:
        bet_description = "Неизвестно"
        multiplier = 1.0
    
    keyboard = [
        [
            InlineKeyboardButton(f"Ставка: {saved_bet}₽", callback_data="dice_change_bet"),
            InlineKeyboardButton("Играть", callback_data="dice_roll")
        ],
        [InlineKeyboardButton("Изменить ставку", callback_data=f"dice_{bet_type}_{bet_value}" if bet_value else f"dice_{bet_type}")]
    ]
    
    # Добавляем кнопку "Назад" в зависимости от типа ставки
    if bet_type in ["even", "odd"]:
        keyboard.append([InlineKeyboardButton("Назад", callback_data="dice_even_odd")])
    elif bet_type == "number":
        keyboard.append([InlineKeyboardButton("Назад", callback_data="dice_number")])
    elif bet_type in ["high", "low"]:
        keyboard.append([InlineKeyboardButton("Назад", callback_data="dice_high_low")])
    else:
        keyboard.append([InlineKeyboardButton("Назад", callback_data="game_dice")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    setup_text = f"""
<b>🎮 Кубы - Подтверждение ставки</b>

🎯 Ставка: <b>{bet_description}</b>
💰 Сумма: <b>{saved_bet}₽</b> (от {MIN_BET}₽)
🎲 Множитель: <b>x{multiplier}</b>
🏆 Потенциальный выигрыш: <b>{int(saved_bet * multiplier)}₽</b>

💸 Ваш баланс: <b>{balance}₽</b>

<u>Нажмите "Играть" чтобы бросить куб!</u>
    """
    
    await query.edit_message_text(
        text=setup_text,
        parse_mode='HTML',
        reply_markup=reply_markup
    )

# Бросок куба
async def dice_roll(query, user_id):
    """Бросает куб и определяет результат"""
    if user_id not in game_data or "game_type" not in game_data[user_id]:
        await query.answer("Сначала сделайте ставку!")
        return
    
    game = game_data[user_id]
    bet_amount = game["amount"]
    
    # Проверяем баланс
    balance = get_balance(user_id)
    if balance < bet_amount:
        await query.answer("Недостаточно средств!")
        return
    
    # Бросаем куб через Telegram Dice
    try:
        dice_message = await query.message.reply_dice(emoji="🎲")
        dice_result = dice_message.dice.value
        
        await asyncio.sleep(2)  # Ждем пока анимация куба завершится
        
    except Exception as e:
        logger.error(f"Ошибка при броске куба: {e}")
        # Если не удалось отправить анимацию, используем случайное число
        dice_result = random.randint(1, 6)
        await query.message.reply_text(f"🎲 Бросаем куб... Выпало: {dice_result}")
        await asyncio.sleep(1)
    
    # Определяем выигрыш
    win = False
    multiplier = 1.0
    bet_description = ""
    
    if game["bet_type"] == "even":
        bet_description = "Чет (2,4,6)"
        win = dice_result in [2, 4, 6]
        multiplier = DICE_MULTIPLIERS["even_odd"]
    elif game["bet_type"] == "odd":
        bet_description = "Нечет (1,3,5)"
        win = dice_result in [1, 3, 5]
        multiplier = DICE_MULTIPLIERS["even_odd"]
    elif game["bet_type"] == "number":
        bet_description = f"Число {game['bet_value']}"
        win = dice_result == int(game['bet_value'])
        multiplier = DICE_MULTIPLIERS["number"]
    elif game["bet_type"] == "high":
        bet_description = "Больше (4-6)"
        win = dice_result in [4, 5, 6]
        multiplier = DICE_MULTIPLIERS["high_low"]
    elif game["bet_type"] == "low":
        bet_description = "Меньше (1-3)"
        win = dice_result in [1, 2, 3]
        multiplier = DICE_MULTIPLIERS["high_low"]
    
    # Обрабатываем результат
    if win:
        win_amount = int(bet_amount * multiplier)
        update_balance(user_id, win_amount, 'win', f"Выигрыш в кубах: {bet_description}")
        db.record_game(user_id, 'dice', bet_amount, 'win', win_amount)
        
        result_text = f"""
🎲 <b>Кубы - Результат</b>

🎯 Ваша ставка: <b>{bet_description}</b>
💰 Сумма: <b>{bet_amount}₽</b>
🎲 Выпало: <b>{dice_result}</b>

✅ <b>ВЫИГРЫШ!</b>
🏆 Выигрыш: <b>{win_amount}₽</b> (x{multiplier})
💰 Новый баланс: <b>{get_balance(user_id)}₽</b>

🎉 Поздравляем с выигрышем!
        """
    else:
        update_balance(user_id, -bet_amount, 'loss', f"Проигрыш в кубах: {bet_description}")
        db.record_game(user_id, 'dice', bet_amount, 'loss', 0)
        
        result_text = f"""
🎲 <b>Кубы - Результат</b>

🎯 Ваша ставка: <b>{bet_description}</b>
💰 Сумма: <b>{bet_amount}₽</b>
🎲 Выпало: <b>{dice_result}</b>

❌ <b>ПРОИГРЫШ</b>
💸 Ставка не возвращается
💰 Новый баланс: <b>{get_balance(user_id)}₽</b>

😔 В следующий раз повезет!
        """
    
    # Клавиатура после игры
    keyboard = [
        [InlineKeyboardButton("Играть снова", callback_data="game_dice")],
        [InlineKeyboardButton("Меню игр", callback_data="play_menu")],
        [InlineKeyboardButton("Баланс", callback_data="balance")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        result_text,
        parse_mode='HTML',
        reply_markup=reply_markup
    )

# Изменение ставки в кубах
async def dice_change_bet(query, user_id):
    """Изменение ставки в кубах"""
    balance = get_balance(user_id)
    current_bet = game_data[user_id]["amount"] if user_id in game_data and "amount" in game_data[user_id] else MIN_BET
    
    saved_bet = user_bets.get(user_id, None)
    saved_bet_info = f"\n💾 Сохраненная ставка: {saved_bet}₽" if saved_bet else ""
    
    keyboard = []
    bet_options = [25, 50, 100, 250, 500, 1000, 2500, 5000]
    
    row = []
    for bet in bet_options:
        if bet <= balance:
            button_text = f"{bet}₽"
            if saved_bet and bet == saved_bet:
                button_text = f"💾{bet}₽"
            row.append(InlineKeyboardButton(button_text, callback_data=f"dice_set_bet_{bet}"))
        if len(row) == 4:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    
    # Определяем куда вернуться
    if user_id in game_data and "bet_type" in game_data[user_id]:
        bet_type = game_data[user_id]["bet_type"]
        bet_value = game_data[user_id].get("bet_value", "")
        if bet_value:
            keyboard.append([InlineKeyboardButton("Назад", callback_data=f"dice_{bet_type}_{bet_value}")])
        else:
            keyboard.append([InlineKeyboardButton("Назад", callback_data=f"dice_{bet_type}")])
    else:
        keyboard.append([InlineKeyboardButton("Назад", callback_data="game_dice")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        text=f"<b>Выберите ставку для Кубов</b>{saved_bet_info}\n\n"
             f"Текущая ставка: {current_bet}₽\n"
             f"Ваш баланс: {balance}₽",
        parse_mode='HTML',
        reply_markup=reply_markup
    )

# Запуск игры "Мины" из чата
async def start_mines_from_chat(update: Update, user_id: int) -> None:
    """Запускает игру Мины из текстового сообщения"""
    username = update.effective_user.username or update.effective_user.first_name
    first_name = update.effective_user.first_name
    
    # Получаем или создаем пользователя в БД
    get_or_create_user(user_id, username, first_name)
    
    balance = get_balance(user_id)
    
    if balance < MIN_BET:
        await update.message.reply_text(
            f"❌ Недостаточно средств для игры.\n"
            f"Минимальная ставка: {MIN_BET}₽\n"
            f"Ваш баланс: {balance}₽\n\n"
            f"Используйте <code>/start</code> для пополнения баланса.",
            parse_mode='HTML'
        )
        return
    
    # Используем сохраненную ставку или минимальную
    saved_bet = user_bets.get(user_id, MIN_BET)
    if saved_bet > balance:
        saved_bet = MIN_BET
    
    # Инициализируем игру
    if user_id not in game_data:
        game_data[user_id] = {
            "mines_count": 2,
            "bet": saved_bet,
            "revealed_cells": [],
            "game_active": False,
            "current_multiplier": 1.0,
            "prize_cells": set(),
            "game_number": 0,
            "mines": set(),
            "won_amount": 0
        }
    else:
        game_data[user_id]["bet"] = saved_bet
        game_data[user_id]["mines_count"] = 2
        game_data[user_id]["game_active"] = False
        game_data[user_id]["revealed_cells"] = []
        game_data[user_id]["current_multiplier"] = 1.0
        game_data[user_id]["prize_cells"] = set()
        game_data[user_id]["mines"] = set()
        game_data[user_id]["won_amount"] = 0
    
    mines_count = game_data[user_id]["mines_count"]
    multiplier = MULTIPLIERS[mines_count]
    potential_win = int(game_data[user_id]["bet"] * multiplier)
    
    bet_source = "💾 (сохраненная)" if user_bets.get(user_id) and game_data[user_id]["bet"] == user_bets[user_id] else ""
    
    keyboard = [
        [
            InlineKeyboardButton(f"Ставка: {game_data[user_id]['bet']}₽", callback_data="change_bet"),
            InlineKeyboardButton("Мины: 2", callback_data="mines_info")
        ],
        [InlineKeyboardButton(f"Играть ({multiplier}x)", callback_data="start_mines_game")],
        [InlineKeyboardButton("Назад в меню", callback_data="back_to_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    setup_text = f"""
<b>🎮 Быстрый старт: Мины</b>

👤 {username}
💰 Баланс — {balance} ₽
Ставка — {game_data[user_id]['bet']} ₽ {bet_source}(от {MIN_BET})

💣 Количество мин — 2 (фиксировано)
🎯 Множитель — {multiplier}x
🏆 Потенциальный выигрыш — {potential_win} ₽
    """
    
    await update.message.reply_text(
        text=setup_text,
        parse_mode='HTML',
        reply_markup=reply_markup
    )

# Информация о минах
async def mines_info(query, user_id):
    """Показывает информацию о фиксированном количестве мин"""
    mines_count = 2
    multiplier = MULTIPLIERS[mines_count]
    
    keyboard = [[InlineKeyboardButton("Назад", callback_data="game_mines")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    info_text = f"""
<b>Информация о минах</b>

🎯 В игре "Мины" фиксированное количество мин: <b>2</b>
📊 Множитель: <b>{multiplier}x</b>
🎮 Игровое поле: <b>5x5</b> (25 клеток)
💣 Количество мин: <b>2</b>
🎁 Количество призов: <b>2</b>
    """
    
    await query.edit_message_text(
        text=info_text,
        parse_mode='HTML',
        reply_markup=reply_markup
    )

# Обработка сообщений со ставками
async def handle_bet_message(update: Update, user_id: int, match: re.Match) -> None:
    """Обрабатывает сообщения со ставками"""
    amount = int(match.group(1))
    
    if amount < MIN_BET:
        await update.message.reply_text(
            f"❌ Минимальная ставка составляет {MIN_BET}₽.\n"
            f"Вы указали: {amount}₽"
        )
        return
    
    username = update.effective_user.username or update.effective_user.first_name
    first_name = update.effective_user.first_name
    
    # Получаем или создаем пользователя в БД
    get_or_create_user(user_id, username, first_name)
    
    user_bets[user_id] = amount
    
    await update.message.reply_text(
        f"✅ Ставка сохранена!\n"
        f"Ваша ставка: <b>{amount}₽</b>\n\n"
        f"Теперь при входе в игры эта ставка будет установлена автоматически.\n\n"
        f"<u>Доступные игры:</u>\n"
        f"• Напишите <code>мины</code> - игра в мины\n"
        f"• Напишите <code>кубы</code> - игра в кубы",
        parse_mode='HTML'
    )

# Показать баланс
async def show_balance(query, user_id):
    """Показывает баланс пользователя"""
    username = query.from_user.username or query.from_user.first_name
    first_name = query.from_user.first_name
    
    # Получаем или создаем пользователя в БД
    get_or_create_user(user_id, username, first_name)
    
    balance = get_balance(user_id)
    keyboard = [
        [InlineKeyboardButton("Пополнить баланс", callback_data="deposit")],
        [InlineKeyboardButton("Вывести средства", callback_data="withdraw_menu")],
        [InlineKeyboardButton("Назад", callback_data="back_to_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    saved_bet = user_bets.get(user_id, None)
    bet_info = f"\n💾 Сохраненная ставка: {saved_bet}₽" if saved_bet else ""
    
    # Рассчитываем общие суммы
    total_deposits, total_withdrawals = get_transaction_stats(user_id)
    
    balance_text = f"""
<b>Ваш баланс</b>

💰 Баланс: {balance} ₽{bet_info}

📈 <u>Статистика:</u>
• Всего пополнено: <b>{total_deposits}₽</b>
• Всего выведено: <b>{total_withdrawals}₽</b>

🎮 Минимальная ставка: {MIN_BET} ₽

<u>Доступные игры:</u>
• <b>Мины</b> - 2 мины, множитель 1.12x
• <b>Кубы</b> - несколько режимов игры

💸 <u>Переводы:</u>
Используйте <code>/pay сумма</code> для переводов друзьям!
    """
    
    await query.edit_message_text(
        text=balance_text,
        parse_mode='HTML',
        reply_markup=reply_markup
    )

# Главный обработчик кнопок
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает нажатия на кнопки"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    username = query.from_user.username or query.from_user.first_name
    first_name = query.from_user.first_name
    
    # Получаем или создаем пользователя в БД
    get_or_create_user(user_id, username, first_name)
    
    # Обработка основных команд
    if query.data == "play_menu":
        await play_menu(query, user_id)
        return
    
    elif query.data == "balance":
        await show_balance(query, user_id)
        return
    
    elif query.data == "deposit":
        await deposit_menu(query, user_id)
        return
    
    elif query.data == "withdraw_menu":
        await withdraw_menu(query, user_id)
        return
    
    elif query.data == "show_top":
        await show_top_menu(query, user_id)
        return
    
    elif query.data == "show_reserve":
        await show_reserve_menu(query, user_id)
        return
    
    elif query.data == "refresh_reserve":
        await refresh_reserve(query, user_id)
        return
    
    elif query.data == "chats":
        keyboard = [
            [InlineKeyboardButton("Перейти в чат", url="https://t.me/+fVJwoK3brgU0NmMy")],
            [InlineKeyboardButton("Назад", callback_data="back_to_main")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        chats_text = """
<b>Игровые чаты</b>

Присоединяйтесь к нашему сообществу!
        """
        
        await query.edit_message_text(
            text=chats_text,
            parse_mode='HTML',
            reply_markup=reply_markup
        )
        return
    
    elif query.data == "back_to_main":
        keyboard = [
            [InlineKeyboardButton("Играть", callback_data="play_menu")],
            [InlineKeyboardButton("Баланс", callback_data="balance")],
            [InlineKeyboardButton("Топ игроков", callback_data="show_top")],
            [InlineKeyboardButton("Казна бота", callback_data="show_reserve")],
            [InlineKeyboardButton("Вывести средства", callback_data="withdraw_menu")],
            [InlineKeyboardButton("Пополнить баланс", callback_data="deposit")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        welcome_text = """
<b>🎰 Добро пожаловать в Spindja Casino!</b>

<u>Быстрые команды:</u>
• <code>/balance</code> / <code>/bal</code> / <code>/b</code> - показать баланс
• <code>/top</code> - топ игроков по балансу
• <code>/reserve</code> - казна бота
• <code>/pay сумма</code> - перевести другу
• Напишите <code>мины</code> - игра в мины (2 мины)
• Напишите <code>кубы</code> - игра в кубы
• <code>/chet сумма</code> - ставка на чет (2,4,6) - x2
• <code>/nechet сумма</code> - ставка на нечет (1,3,5) - x2
• <code>/number число сумма</code> - ставка на число (1-6) - x6
• <code>/more сумма</code> - ставка на больше (4-6) - x2
• <code>/less сумма</code> - ставка на меньше (1-3) - x2
        """
        
        await query.edit_message_text(
            text=welcome_text,
            parse_mode='HTML',
            reply_markup=reply_markup
        )
        return
    
    # Игра в мины
    elif query.data == "game_mines":
        await mines_setup(query, user_id)
        return
    
    elif query.data == "change_bet":
        await change_bet(query, user_id)
        return
    
    elif query.data == "mines_info":
        await mines_info(query, user_id)
        return
    
    elif query.data.startswith("set_bet_"):
        bet = int(query.data.split("_")[2])
        balance = get_balance(user_id)
        if bet <= balance:
            game_data[user_id]["bet"] = bet
            user_bets[user_id] = bet
        await mines_setup(query, user_id)
        return
    
    elif query.data == "start_mines_game":
        balance = get_balance(user_id)
        if balance < game_data[user_id]["bet"]:
            await query.answer("Недостаточно средств на балансе!")
            return
        else:
            await play_mines_game(query, user_id)
            return
    
    elif query.data.startswith("cell_"):
        cell_idx = int(query.data.split("_")[1])
        await handle_cell_click(query, user_id, cell_idx)
        return
    
    elif query.data == "cashout":
        await handle_cashout(query, user_id)
        return
    
    elif query.data.startswith("cell_opened_"):
        await query.answer("Эта ячейка уже открыта!")
        return
    
    # Игра в кубы
    elif query.data == "game_dice":
        await dice_menu(query, user_id)
        return
    
    elif query.data == "dice_even_odd":
        await dice_even_odd(query, user_id)
        return
    
    elif query.data == "dice_number":
        await dice_number(query, user_id)
        return
    
    elif query.data == "dice_high_low":
        await dice_high_low(query, user_id)
        return
    
    elif query.data == "dice_bet_even":
        await process_dice_bet(query, user_id, "even")
        return
    
    elif query.data == "dice_bet_odd":
        await process_dice_bet(query, user_id, "odd")
        return
    
    elif query.data.startswith("dice_bet_num_"):
        number = query.data.split("_")[3]
        await process_dice_bet(query, user_id, "number", number)
        return
    
    elif query.data == "dice_bet_high":
        await process_dice_bet(query, user_id, "high")
        return
    
    elif query.data == "dice_bet_low":
        await process_dice_bet(query, user_id, "low")
        return
    
    elif query.data == "dice_change_bet":
        await dice_change_bet(query, user_id)
        return
    
    elif query.data.startswith("dice_set_bet_"):
        bet = int(query.data.split("_")[3])
        balance = get_balance(user_id)
        if bet <= balance:
            # Сохраняем ставку для кубов
            user_bets[user_id] = bet
            if user_id in game_data and "bet_type" in game_data[user_id]:
                game_data[user_id]["amount"] = bet
                # Возвращаемся к соответствующему экрану
                bet_type = game_data[user_id]["bet_type"]
                bet_value = game_data[user_id].get("bet_value", "")
                if bet_value:
                    await process_dice_bet(query, user_id, bet_type, bet_value)
                else:
                    await process_dice_bet(query, user_id, bet_type)
            else:
                await dice_menu(query, user_id)
        return
    
    elif query.data == "dice_roll":
        await dice_roll(query, user_id)
        return

# Главное меню игр
async def play_menu(query, user_id):
    """Меню выбора игры"""
    balance = get_balance(user_id)
    
    keyboard = [
        [InlineKeyboardButton("Мины (2 мины)", callback_data="game_mines")],
        [InlineKeyboardButton("Кубы", callback_data="game_dice")],
        [InlineKeyboardButton("Назад", callback_data="back_to_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    saved_bet = user_bets.get(user_id, None)
    bet_info = f"\n💾 Ваша сохраненная ставка: {saved_bet}₽" if saved_bet else ""
    
    menu_text = f"""
<b>Выберите игру</b>{bet_info}

🎮 <b>Мины</b>
• Фиксировано 2 мины на поле 5x5
• Множитель: 1.12x

🎲 <b>Кубы</b>
• Чет/Нечет - x{DICE_MULTIPLIERS["even_odd"]}
• Угадать число - x{DICE_MULTIPLIERS["number"]}
• Больше/Меньше - x{DICE_MULTIPLIERS["high_low"]}

<u>Быстрый старт:</u>
• Напишите в чат <code>мины</code> - игра в мины
• Напишите в чат <code>кубы</code> - игра в кубы
    """
    
    await query.edit_message_text(
        text=menu_text,
        parse_mode='HTML',
        reply_markup=reply_markup
    )

# Настройка игры в мины
async def mines_setup(query, user_id):
    """Настройка игры в мины"""
    global game_counter
    
    balance = get_balance(user_id)
    
    if user_id not in game_data:
        game_data[user_id] = {
            "mines_count": 2,
            "bet": MIN_BET,
            "revealed_cells": [],
            "game_active": False,
            "current_multiplier": 1.0,
            "prize_cells": set(),
            "game_number": game_counter + 1,
            "mines": set(),
            "won_amount": 0
        }
    
    saved_bet = user_bets.get(user_id)
    if saved_bet:
        if saved_bet <= balance:
            game_data[user_id]["bet"] = saved_bet
        else:
            game_data[user_id]["bet"] = min(saved_bet, balance)
            if balance < MIN_BET:
                game_data[user_id]["bet"] = MIN_BET
    else:
        game_data[user_id]["bet"] = MIN_BET
    
    mines_count = game_data[user_id]["mines_count"]
    multiplier = MULTIPLIERS[mines_count]
    potential_win = int(game_data[user_id]["bet"] * multiplier)
    
    bet_source = "💾 (сохраненная)" if saved_bet and game_data[user_id]["bet"] == saved_bet else ""
    
    keyboard = [
        [
            InlineKeyboardButton(f"Ставка: {game_data[user_id]['bet']}₽", callback_data="change_bet"),
            InlineKeyboardButton("Инфо о минах", callback_data="mines_info")
        ],
        [InlineKeyboardButton(f"Играть ({multiplier}x)", callback_data="start_mines_game")],
        [InlineKeyboardButton("Назад", callback_data="play_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    setup_text = f"""
<b>Мины</b>

👤 {query.from_user.username or query.from_user.first_name}
💰 Баланс — {balance} ₽
Ставка — {game_data[user_id]['bet']} ₽ {bet_source}(от {MIN_BET})

💣 Количество мин — 2 (фиксировано)
🎯 Множитель — {multiplier}x
🏆 Потенциальный выигрыш — {potential_win} ₽

<u>Номер игры:</u> #{game_data[user_id]['game_number']}
    """
    
    await query.edit_message_text(
        text=setup_text,
        parse_mode='HTML',
        reply_markup=reply_markup
    )

# Инициализация игрового поля
def init_game_field(user_id):
    """Инициализирует игровое поле с минами и призами"""
    global game_counter
    
    game = game_data[user_id]
    
    all_cells = list(range(TOTAL_CELLS))
    
    # Всегда 2 мины
    mines_positions = random.sample(all_cells, 2)
    
    non_mine_cells = [cell for cell in all_cells if cell not in mines_positions]
    # Всегда 2 приза
    prize_positions = random.sample(non_mine_cells, 2)
    
    game["mines"] = set(mines_positions)
    game["prize_cells"] = set(prize_positions)
    game["revealed_cells"] = []
    game["game_active"] = True
    game["current_multiplier"] = 1.0
    game["won_amount"] = 0
    
    # Увеличиваем счетчик игр
    game_counter += 1
    game["game_number"] = game_counter
    
    # Сохраняем информацию об игре для администратора
    games_history[game_counter] = {
        "user_id": user_id,
        "username": query.from_user.username or query.from_user.first_name,
        "bet": game["bet"],
        "mines_count": 2,
        "mines": set(mines_positions),
        "prizes": set(prize_positions),
        "status": "Активна",
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }

# Игровой процесс мин
async def play_mines_game(query, user_id):
    """Основной игровой процесс мин"""
    if user_id not in game_data or not game_data[user_id]["game_active"]:
        init_game_field(user_id)
    
    game = game_data[user_id]
    mines_count = game["mines_count"]
    bet = game["bet"]
    multiplier = MULTIPLIERS[mines_count]
    
    keyboard = []
    for row in range(GRID_SIZE):
        row_buttons = []
        for col in range(GRID_SIZE):
            cell_idx = row * GRID_SIZE + col
            if cell_idx in game["revealed_cells"]:
                if cell_idx in game["mines"]:
                    row_buttons.append(InlineKeyboardButton("💥", callback_data=f"cell_opened_{cell_idx}"))
                elif cell_idx in game["prize_cells"]:
                    row_buttons.append(InlineKeyboardButton("🎁", callback_data=f"cell_opened_{cell_idx}"))
                else:
                    row_buttons.append(InlineKeyboardButton("📦", callback_data=f"cell_opened_{cell_idx}"))
            else:
                row_buttons.append(InlineKeyboardButton("⬛", callback_data=f"cell_{cell_idx}"))
        keyboard.append(row_buttons)
    
    cashout_text = f"Забрать {int(game['won_amount'])}₽" if game['won_amount'] > 0 else "Забрать 0₽"
    keyboard.append([
        InlineKeyboardButton(cashout_text, callback_data="cashout"),
        InlineKeyboardButton("Назад", callback_data="game_mines")
    ])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    field_text = generate_field_text(user_id)
    
    revealed_mines = len([c for c in game["revealed_cells"] if c in game["mines"]])
    
    game_text = f"""
<b>Мины · 2 мины</b>
<u>Номер игры:</u> #{game['game_number']}

Ставка {bet}₽ x{game['current_multiplier']:.2f} ➡️ Выигрыш {int(game['won_amount'])}₽

{field_text}

Текущий множитель: {game['current_multiplier']:.2f}x
Максимальный множитель: {multiplier}x
💣 Осталось мин: {2 - revealed_mines}
    """
    
    await query.edit_message_text(
        text=game_text,
        parse_mode='HTML',
        reply_markup=reply_markup
    )

# Генерация текста игрового поля
def generate_field_text(user_id):
    """Генерирует текстовое представление игрового поля"""
    game = game_data[user_id]
    revealed = set(game["revealed_cells"])
    mines = game["mines"]
    prizes = game["prize_cells"]
    
    field_text = ""
    for row in range(GRID_SIZE):
        row_text = ""
        for col in range(GRID_SIZE):
            cell_idx = row * GRID_SIZE + col
            
            if cell_idx in revealed:
                if cell_idx in mines:
                    row_text += "💥"
                elif cell_idx in prizes:
                    row_text += "🎁"
                else:
                    row_text += "📦"
            else:
                row_text += "⬛"
        
        field_text += row_text + "\n"
    
    return field_text

# Обработка нажатия на ячейку
async def handle_cell_click(query, user_id, cell_idx):
    """Обрабатывает нажатие на ячейку"""
    game = game_data[user_id]
    
    if cell_idx in game["revealed_cells"]:
        await query.answer("Эта ячейка уже открыта!")
        return
    
    game["revealed_cells"].append(cell_idx)
    
    if cell_idx in game["mines"]:
        game["game_active"] = False
        games_history[game["game_number"]]["status"] = "Проиграл"
        
        # Записываем проигрыш в БД
        update_balance(user_id, -game["bet"], 'loss', f"Проигрыш в минах (игра #{game['game_number']})")
        db.record_game(user_id, 'mines', game["bet"], 'loss', 0)
        
        await end_game(query, user_id, win=False)
        return
    
    game["current_multiplier"] *= 1.12
    game["won_amount"] = int(game["bet"] * game["current_multiplier"])
    
    await play_mines_game(query, user_id)

# Завершение игры
async def end_game(query, user_id, win=True):
    """Завершает игру"""
    game = game_data[user_id]
    
    if win:
        win_amount = game["won_amount"]
        update_balance(user_id, win_amount, 'win', f"Выигрыш в минах (игра #{game['game_number']})")
        db.record_game(user_id, 'mines', game["bet"], 'win', win_amount)
        games_history[game["game_number"]]["status"] = "Выиграл"
        
        keyboard = [
            [InlineKeyboardButton("Играть снова", callback_data="start_mines_game")],
            [InlineKeyboardButton("Назад в меню", callback_data="game_mines")]
        ]
        
        end_text = f"""
<b>Поздравляем! Вы выиграли!</b>
<u>Номер игры:</u> #{game['game_number']}

🎉 Вы успешно собрали {win_amount}₽!

Ваш выигрыш добавлен на баланс.
Новый баланс: {get_balance(user_id)}₽
        """
    else:
        games_history[game["game_number"]]["status"] = "Проиграл"
        
        keyboard = [
            [InlineKeyboardButton("Играть снова", callback_data="start_mines_game")],
            [InlineKeyboardButton("Назад в меню", callback_data="game_mines")]
        ]
        
        end_text = f"""
<b>Игра окончена</b>
<u>Номер игры:</u> #{game['game_number']}

💥 Вы наткнулись на мину!

Ставка {game['bet']}₽ не возвращается.
Новый баланс: {get_balance(user_id)}₽
        """
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    game["game_active"] = False
    
    await query.edit_message_text(
        text=end_text,
        parse_mode='HTML',
        reply_markup=reply_markup
    )

# Обналичивание
async def handle_cashout(query, user_id):
    """Обрабатывает обналичивание выигрыша"""
    game = game_data[user_id]
    
    if not game["game_active"] or game["won_amount"] == 0:
        await query.answer("Нечего забирать!")
        return
    
    win_amount = game["won_amount"]
    update_balance(user_id, win_amount, 'win', f"Вывод выигрыша в минах (игра #{game['game_number']})")
    db.record_game(user_id, 'mines', game["bet"], 'cashout', win_amount)
    game["game_active"] = False
    games_history[game["game_number"]]["status"] = "Забрал выигрыш"
    
    keyboard = [
        [InlineKeyboardButton("Играть снова", callback_data="start_mines_game")],
        [InlineKeyboardButton("Назад в меню", callback_data="game_mines")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    cashout_text = f"""
<b>Вы успешно забрали выигрыш!</b>
<u>Номер игры:</u> #{game['game_number']}

💰 Вы забрали: {win_amount}₽
📈 Ваш новый баланс: {get_balance(user_id)}₽

Поздравляем с выигрышем!
    """
    
    await query.edit_message_text(
        text=cashout_text,
        parse_mode='HTML',
        reply_markup=reply_markup
    )

# Изменение ставки
async def change_bet(query, user_id):
    """Изменение ставки"""
    balance = get_balance(user_id)
    current_bet = game_data[user_id]["bet"] if user_id in game_data and "bet" in game_data[user_id] else MIN_BET
    
    saved_bet = user_bets.get(user_id, None)
    saved_bet_info = f"\n💾 Сохраненная ставка: {saved_bet}₽" if saved_bet else ""
    
    keyboard = []
    bet_options = [25, 50, 100, 250, 500, 1000, 2500, 5000]
    
    row = []
    for bet in bet_options:
        if bet <= balance:
            button_text = f"{bet}₽"
            if saved_bet and bet == saved_bet:
                button_text = f"💾{bet}₽"
            row.append(InlineKeyboardButton(button_text, callback_data=f"set_bet_{bet}"))
        if len(row) == 4:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    
    keyboard.append([InlineKeyboardButton("Назад", callback_data="game_mines")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        text=f"<b>Выберите ставку</b>{saved_bet_info}\n\n"
             f"Текущая ставка: {current_bet}₽\n"
             f"Ваш баланс: {balance}₽\n\n"
             f"<i>В игре всегда 2 мины с множителем 1.12x</i>",
        parse_mode='HTML',
        reply_markup=reply_markup
    )

# Меню топа игроков
async def show_top_menu(query, user_id):
    """Показывает топ игроков"""
    # Получаем топ-10 по балансу
    top_by_balance = db.get_top_users_by_balance(10)
    
    # Получаем топ-5 по выигрышам
    top_by_wins = db.get_top_users_by_wins(5)
    
    # Формируем текст топа по балансу
    top_balance_text = ""
    if top_by_balance:
        for i, user in enumerate(top_by_balance, 1):
            username = user['username'] or user['first_name'] or f"ID: {user['user_id']}"
            emoji = "👑" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
            top_balance_text += f"{emoji} {username}: <b>{user['balance']:,}₽</b>\n"
    else:
        top_balance_text = "Пока никто не пополнил баланс 😔\n"
    
    # Формируем текст топа по выигрышам
    top_wins_text = ""
    if top_by_wins:
        for i, user in enumerate(top_by_wins[:5], 1):
            username = user['username'] or user['first_name'] or f"ID: {user['user_id']}"
            emoji = "🏆" if i == 1 else "🎖️" if i == 2 else "⭐" if i == 3 else f"{i}."
            games_count = user['total_games']
            win_rate = (user['total_won'] / (user['total_won'] + games_count * 100)) * 100 if games_count > 0 else 0
            top_wins_text += f"{emoji} {username}: <b>{user['total_won']:,}₽</b> ({games_count} игр)\n"
    else:
        top_wins_text = "Пока никто не выигрывал 😔\n"
    
    # Проверяем, выдавались ли сегодня награды
    today_str = datetime.now().strftime("%Y-%m-%d")
    rewards_given_today = db.check_daily_reward_given(today_str)
    
    reward_info = "✅ Сегодня награды уже выданы" if rewards_given_today else "⏳ Награды будут выданы сегодня в 00:00"
    
    # Получаем позицию текущего пользователя в топе
    user_position = None
    user_balance = get_balance(user_id)
    if user_balance > 0 and top_by_balance:
        for i, user in enumerate(top_by_balance, 1):
            if user['user_id'] == user_id:
                user_position = i
                break
    
    user_position_text = ""
    if user_position:
        user_position_text = f"\n🎯 <b>Ваша позиция в топе:</b> {user_position} место\n"
    elif user_balance > 0:
        user_position_text = f"\n🎯 <b>Ваша позиция в топе:</b> ниже 10-го места\n"
    
    top_text = f"""
<b>🏆 Топ игроков Spindja Casino</b>

💰 <b>Топ по балансу:</b>
{top_balance_text}

🎯 <b>Топ по выигрышам:</b>
{top_wins_text}
{user_position_text}
🎁 <b>Ежедневные награды:</b>
Каждый день топ-3 игрока по балансу получают по <b>100₽</b>
{reward_info}

💡 <b>Как попасть в топ?</b>
• Пополняйте баланс (от {MIN_DEPOSIT}₽)
• Играйте и выигрывайте
• Переводите средства друзьям
    """
    
    keyboard = [
        [InlineKeyboardButton("Мой баланс", callback_data="balance")],
        [InlineKeyboardButton("Пополнить баланс", callback_data="deposit")],
        [InlineKeyboardButton("Казна бота", callback_data="show_reserve")],
        [InlineKeyboardButton("Назад", callback_data="back_to_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        text=top_text,
        parse_mode='HTML',
        reply_markup=reply_markup
    )

# Меню казны бота
async def show_reserve_menu(query, user_id):
    """Показывает казну бота"""
    # Генерируем случайную сумму для казны
    reserve_amount = random.randint(100000, 500000)  # от 100к до 500к
    
    # Создаем красивый вывод
    reserve_text = f"""
<b>💰 Казна бота</b>

💎 <b>Баланс казны:</b> {reserve_amount:,}₽

📊 <b>Информация:</b>
Казна бота пополняется за счет комиссий с игр и пополнений.
Средства из казны используются для выплат выигрышей и бонусов.

💡 <b>Для пополнения/вывода:</b>
Обращайтесь к администратору {ADMIN_USERNAME}
    """
    
    keyboard = [
        [InlineKeyboardButton(f"Связаться с {ADMIN_USERNAME}", url=f"https://t.me/{ADMIN_USERNAME[1:]}")],
        [InlineKeyboardButton("Обновить казну", callback_data="refresh_reserve")],
        [InlineKeyboardButton("Назад", callback_data="back_to_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        text=reserve_text,
        parse_mode='HTML',
        reply_markup=reply_markup
    )

# Обновление казны
async def refresh_reserve(query, user_id):
    """Обновляет казну бота"""
    # Генерируем новую случайную сумму
    reserve_amount = random.randint(100000, 500000)
    
    reserve_text = f"""
<b>💰 Казна бота (обновлено)</b>

💎 <b>Баланс казны:</b> {reserve_amount:,}₽

📊 Казна обновлена! Сумма изменена.
    """
    
    keyboard = [
        [InlineKeyboardButton(f"Связаться с {ADMIN_USERNAME}", url=f"https://t.me/{ADMIN_USERNAME[1:]}")],
        [InlineKeyboardButton("Обновить еще раз", callback_data="refresh_reserve")],
        [InlineKeyboardButton("Назад", callback_data="back_to_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        text=reserve_text,
        parse_mode='HTML',
        reply_markup=reply_markup
    )

# ========== ОСНОВНАЯ ФУНКЦИЯ ==========
async def scheduled_daily_rewards(context: ContextTypes.DEFAULT_TYPE):
    """Планировщик для ежедневных наград"""
    await check_and_give_daily_rewards(context)

def main() -> None:
    """Запуск бота"""
    application = Application.builder().token(TOKEN).build()
    
    # Регистрируем обработчики команд
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("givemoney", givemoney))
    application.add_handler(CommandHandler("game", game_command))
    application.add_handler(CommandHandler("delbalance", delbalance))
    application.add_handler(CommandHandler("reserve", reserve_command))
    application.add_handler(CommandHandler("top", top_command))
    
    # Команды для баланса и переводов
    application.add_handler(CommandHandler("balance", balance_command))
    application.add_handler(CommandHandler("bal", balance_command))
    application.add_handler(CommandHandler("b", balance_command))
    
    application.add_handler(CommandHandler("pay", pay_command))
    application.add_handler(CommandHandler("transfer", pay_command))
    application.add_handler(CommandHandler("send", pay_command))
    
    # Регистрируем команды для быстрых ставок в кубы (русские)
    application.add_handler(CommandHandler("chet", dice_even_command))
    application.add_handler(CommandHandler("nechet", dice_odd_command))
    application.add_handler(CommandHandler("number", dice_number_command))
    application.add_handler(CommandHandler("more", dice_high_command))
    application.add_handler(CommandHandler("less", dice_low_command))
    
    # Английские команды для совместимости
    application.add_handler(CommandHandler("even", dice_even_command))
    application.add_handler(CommandHandler("odd", dice_odd_command))
    application.add_handler(CommandHandler("high", dice_high_command))
    application.add_handler(CommandHandler("low", dice_low_command))
    
    # Регистрируем обработчик кнопок
    application.add_handler(CallbackQueryHandler(button_handler))
    
    # Регистрируем обработчик текстовых сообщений
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        handle_text_message
    ))
    
    # Настраиваем планировщик для ежедневных наград
    job_queue = application.job_queue
    if job_queue:
        # Проверяем каждые 30 минут
        job_queue.run_repeating(
            scheduled_daily_rewards,
            interval=1800,  # 30 минут в секундах
            first=10
        )
    
    print("=" * 60)
    print("🎰 Spindja Casino Бот запущен...")
    print("=" * 60)
    print(f"📁 База данных: casino.db")
    print(f"💰 Начальный баланс: {INITIAL_BALANCE}₽")
    print(f"⚙️ Администратор: {ADMIN_ID} ({ADMIN_USERNAME})")
    print(f"💎 Минимальное пополнение: {MIN_DEPOSIT}₽")
    print(f"💸 Минимальный вывод: {MIN_WITHDRAWAL}₽")
    print("\n📊 Основные команды:")
    print("• /balance / /bal / /b - показать баланс")
    print("• /top - топ игроков по балансу")
    print("• /reserve - казна бота (случайная сумма)")
    print("• /pay сумма - перевести другу")
    print(f"• Пополнение: от {MIN_DEPOSIT}₽ через {ADMIN_USERNAME}")
    print(f"• Вывод: от {MIN_WITHDRAWAL}₽ через {ADMIN_USERNAME} (крипто приоритет)")
    print("\n🎮 Игры:")
    print("• Напишите 'мины' - игра в мины (2 мины, x1.12)")
    print("• Напишите 'кубы' - игра в кубы (анимированные кубики)")
    print("\n🎲 Быстрые ставки в Кубы:")
    print("• /chet сумма - ставка на чет (2,4,6) - x2")
    print("• /nechet сумма - ставка на нечет (1,3,5) - x2")
    print("• /number число сумма - ставка на число (1-6) - x6")
    print("• /more сумма - ставка на больше (4-6) - x2")
    print("• /less сумма - ставка на меньше (1-3) - x2")
    print("\n🎁 Ежедневные награды:")
    print("• Топ-3 игрока по балансу получают по 100₽ каждый день")
    print("• Награды выдаются автоматически в 00:00")
    print("\n⚙️ Для админа:")
    print("• /givemoney ID сумма - выдать баланс")
    print("• /delbalance ID сумма - снять баланс")
    print("• /game mines номер - просмотр информации об игре")
    print("=" * 60)
    
    # Запускаем бота
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
