import logging
import random
import re
from typing import Dict, List, Tuple
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Токен бота
TOKEN = "7979153629:AAFPh1qGUDzsX8ljP3MZ2ROAQ9vA_XtkBdE"

# ID администратора
ADMIN_ID = 7313407194

# Глобальные счетчики
game_counter = 0  # Счетчик игр
games_history: Dict[int, Dict] = {}  # История игр для администратора

# Хранилище данных
user_data: Dict[int, Dict] = {}
game_data: Dict[int, Dict] = {}
user_bets: Dict[int, int] = {}

# Константы игры
INITIAL_BALANCE = 1000
MIN_BET = 25
GRID_SIZE = 5
TOTAL_CELLS = GRID_SIZE * GRID_SIZE
MIN_MINES = 2
MAX_MINES = 24

# Множители
MULTIPLIERS = {
    2: 1.12, 3: 1.34, 4: 1.63, 5: 1.99, 6: 2.45,
    7: 3.05, 8: 3.85, 9: 4.95, 10: 6.45, 11: 8.55,
    12: 11.45, 13: 15.55, 14: 21.45, 15: 29.95,
    16: 42.45, 17: 61.45, 18: 90.95, 19: 136.95,
    20: 210.45, 21: 330.95, 22: 531.45, 23: 871.95,
    24: 1451.95
}

# Обработчик команды /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отправляет приветственное сообщение с кнопками"""
    user_id = update.effective_user.id
    
    if user_id not in user_data:
        user_data[user_id] = {"balance": INITIAL_BALANCE}
    
    keyboard = [
        [InlineKeyboardButton("Играть", callback_data="play_menu")],
        [InlineKeyboardButton("Баланс", callback_data="balance")],
        [InlineKeyboardButton("Игровые чаты", callback_data="chats")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    welcome_text = """
<b>Добро пожаловать в Spindja Casino!</b>

Мы рады видеть вас в нашем казино!

Подписывайтесь на наш канал @spindja чтобы следить за новостями и конкурсами.

Удачи в играх и больших выигрышей!

<u>Быстрый старт:</u>
• Напишите <code>мины</code> для быстрого начала игры
• Напишите сумму с ₽ для установки ставки
    """
    
    await update.message.reply_text(
        welcome_text,
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
            "Используйте: <code>/game тип_игры номер_игры</code>\n"
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
    
    game_details = f"""
<b>Игра №{game_num} - Мины</b>

👤 Игрок: {game_info['user_id']} ({game_info.get('username', 'Неизвестно')})
💰 Ставка: {game_info['bet']}₽
💣 Количество мин: {game_info['mines_count']}
🎮 Статус: {game_info.get('status', 'Завершена')}
📅 Время: {game_info.get('time', 'Неизвестно')}

<u>Поле с минами:</u>
{field_text}

<u>Позиции мин (индексы):</u>
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
        
        if target_id not in user_data:
            user_data[target_id] = {"balance": INITIAL_BALANCE}
        
        user_data[target_id]["balance"] += amount
        
        await update.message.reply_text(
            f"✅ Баланс пользователя <code>{target_id}</code> пополнен на <b>{amount}₽</b>.\n"
            f"Новый баланс: <b>{user_data[target_id]['balance']}₽</b>",
            parse_mode='HTML'
        )
        
        try:
            await context.bot.send_message(
                chat_id=target_id,
                text=f"🎉 Ваш баланс пополнен на <b>{amount}₽</b> администратором!\n"
                     f"Новый баланс: <b>{user_data[target_id]['balance']}₽</b>",
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
    
    # Проверяем, не является ли сообщение командой
    if text.startswith('/'):
        return
    
    # Проверяем на наличие суммы для ставки
    pattern = r'(\d+)\s*(?:₽|руб|рублей|р)'
    match = re.search(pattern, text)
    
    if match:
        await handle_bet_message(update, user_id, match)
        return
    
    # Если ничего не распознали, предлагаем помощь
    await update.message.reply_text(
        "🤔 Не понял ваше сообщение.\n\n"
        "<u>Доступные команды:</u>\n"
        "• Напишите <code>мины</code> - начать игру\n"
        "• Напишите сумму с ₽ - установить ставку\n"
        "• Используйте кнопки меню",
        parse_mode='HTML'
    )

# Запуск игры "Мины" из чата
async def start_mines_from_chat(update: Update, user_id: int) -> None:
    """Запускает игру Мины из текстового сообщения"""
    if user_id not in user_data:
        user_data[user_id] = {"balance": INITIAL_BALANCE}
    
    balance = user_data[user_id]["balance"]
    
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
            "mines_count": 5,
            "bet": saved_bet,
            "revealed_cells": [],
            "game_active": False,
            "current_multiplier": 1.0,
            "prize_cells": set(),
            "game_number": 0
        }
    else:
        game_data[user_id]["bet"] = saved_bet
        game_data[user_id]["game_active"] = False
    
    mines_count = game_data[user_id]["mines_count"]
    multiplier = MULTIPLIERS[mines_count]
    potential_win = int(game_data[user_id]["bet"] * multiplier)
    
    bet_source = "💾 (сохраненная)" if user_bets.get(user_id) and game_data[user_id]["bet"] == user_bets[user_id] else ""
    
    keyboard = [
        [
            InlineKeyboardButton(f"Ставка: {game_data[user_id]['bet']}₽", callback_data="change_bet"),
            InlineKeyboardButton(f"Мины: {mines_count}", callback_data="change_mines")
        ],
        [InlineKeyboardButton(f"Играть ({multiplier}x)", callback_data="start_mines_game")],
        [InlineKeyboardButton("Назад в меню", callback_data="back_to_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    setup_text = f"""
<b>🎮 Быстрый старт: Мины</b>

👤 {update.effective_user.username or update.effective_user.first_name}
💰 Баланс — {balance} ₽
Ставка — {game_data[user_id]['bet']} ₽ {bet_source}(от {MIN_BET})

Выбрано — {mines_count} мин 💣
Множитель — {multiplier}x
Потенциальный выигрыш — {potential_win} ₽

<u>Используйте кнопки для настройки игры:</u>
• Изменить ставку
• Изменить количество мин
• Начать игру
    """
    
    await update.message.reply_text(
        text=setup_text,
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
    
    if user_id not in user_data:
        user_data[user_id] = {"balance": INITIAL_BALANCE}
    
    user_bets[user_id] = amount
    
    await update.message.reply_text(
        f"✅ Ставка сохранена!\n"
        f"Ваша ставка: <b>{amount}₽</b>\n\n"
        f"Теперь при входе в игру <b>«Мины»</b> эта ставка будет установлена автоматически.\n\n"
        f"<u>Напишите <code>мины</code> для быстрого старта!</u>",
        parse_mode='HTML'
    )

# Показать баланс
async def show_balance(query, user_id):
    """Показывает баланс пользователя"""
    balance = user_data[user_id]["balance"]
    keyboard = [[InlineKeyboardButton("Назад", callback_data="back_to_main")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    saved_bet = user_bets.get(user_id, None)
    bet_info = f"\n💾 Сохраненная ставка: {saved_bet}₽" if saved_bet else ""
    
    balance_text = f"""
<b>Ваш баланс</b>

💰 Баланс: {balance} ₽{bet_info}

Минимальная ставка: {MIN_BET} ₽

<u>Быстрые команды:</u>
• Напишите <code>мины</code> - начать игру
• Напишите сумму с ₽ - изменить ставку
    """
    
    await query.edit_message_text(
        text=balance_text,
        parse_mode='HTML',
        reply_markup=reply_markup
    )

# Главное меню игр
async def play_menu(query, user_id):
    """Меню выбора игры"""
    keyboard = [
        [InlineKeyboardButton("Мины", callback_data="game_mines")],
        [InlineKeyboardButton("Назад", callback_data="back_to_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    saved_bet = user_bets.get(user_id, None)
    bet_info = f"\n💾 Ваша сохраненная ставка: {saved_bet}₽" if saved_bet else ""
    
    menu_text = f"""
<b>Выберите игру</b>{bet_info}

Доступные игры:
• Мины - классическая игра с поиском сокровищ

<u>Быстрый старт:</u>
Напишите в чат <code>мины</code> для начала игры!
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
    
    balance = user_data[user_id]["balance"]
    
    if user_id not in game_data:
        game_data[user_id] = {
            "mines_count": 5,
            "bet": MIN_BET,
            "revealed_cells": [],
            "game_active": False,
            "current_multiplier": 1.0,
            "prize_cells": set(),
            "game_number": game_counter + 1
        }
    
    saved_bet = user_bets.get(user_id)
    if saved_bet:
        if saved_bet <= balance:
            game_data[user_id]["bet"] = saved_bet
        else:
            game_data[user_id]["bet"] = min(saved_bet, balance)
            if balance < MIN_BET:
                game_data[user_id]["bet"] = MIN_BET
    
    mines_count = game_data[user_id]["mines_count"]
    multiplier = MULTIPLIERS[mines_count]
    potential_win = int(game_data[user_id]["bet"] * multiplier)
    
    bet_source = "💾 (сохраненная)" if saved_bet and game_data[user_id]["bet"] == saved_bet else ""
    
    keyboard = [
        [
            InlineKeyboardButton(f"Ставка: {game_data[user_id]['bet']}₽", callback_data="change_bet"),
            InlineKeyboardButton(f"Мины: {mines_count}", callback_data="change_mines")
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

Выбрано — {mines_count} мин 💣
Множитель — {multiplier}x
Потенциальный выигрыш — {potential_win} ₽

<u>Номер игры:</u> #{game_data[user_id]['game_number']}

Выберите количество мин от {MIN_MINES} до {MAX_MINES}
Чем больше мин, тем выше множитель!
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
    mines_count = game["mines_count"]
    
    all_cells = list(range(TOTAL_CELLS))
    mines_positions = random.sample(all_cells, mines_count)
    
    non_mine_cells = [cell for cell in all_cells if cell not in mines_positions]
    prize_positions = random.sample(non_mine_cells, min(2, len(non_mine_cells)))
    
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
        "username": user_data.get(user_id, {}).get("username", "Неизвестно"),
        "bet": game["bet"],
        "mines_count": mines_count,
        "mines": set(mines_positions),
        "prizes": set(prize_positions),
        "status": "Активна",
        "time": "Текущее время"  # В реальном проекте добавьте timestamp
    }

# Игровой процесс мин
async def play_mines_game(query, user_id):
    """Основной игровой процесс мин"""
    if not game_data[user_id]["game_active"]:
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
    
    keyboard.append([
        InlineKeyboardButton(f"Забрать {int(game['won_amount'])}₽", callback_data="cashout"),
        InlineKeyboardButton("Назад", callback_data="game_mines")
    ])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    field_text = generate_field_text(user_id)
    
    game_text = f"""
<b>Мины · {mines_count} мин</b>
<u>Номер игры:</u> #{game['game_number']}

Ставка {bet}₽ x{game['current_multiplier']:.2f} ➡️ Выигрыш {int(game['won_amount'])}₽

{field_text}

Текущий множитель: {game['current_multiplier']:.2f}x
Максимальный множитель: {multiplier}x
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
        user_data[user_id]["balance"] += win_amount
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
Новый баланс: {user_data[user_id]['balance']}₽
        """
    else:
        user_data[user_id]["balance"] -= game["bet"]
        
        keyboard = [
            [InlineKeyboardButton("Играть снова", callback_data="start_mines_game")],
            [InlineKeyboardButton("Назад в меню", callback_data="game_mines")]
        ]
        
        end_text = f"""
<b>Игра окончена</b>
<u>Номер игры:</u> #{game['game_number']}

💥 Вы наткнулись на мину!

Ставка {game['bet']}₽ не возвращается.
Новый баланс: {user_data[user_id]['balance']}₽
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
    user_data[user_id]["balance"] += win_amount
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
📈 Ваш новый баланс: {user_data[user_id]['balance']}₽

Поздравляем с выигрышем!
    """
    
    await query.edit_message_text(
        text=cashout_text,
        parse_mode='HTML',
        reply_markup=reply_markup
    )

# Главный обработчик кнопок
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает нажатия на кнопки"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    
    if user_id not in user_data:
        user_data[user_id] = {"balance": INITIAL_BALANCE}
    
    # Сохраняем имя пользователя
    user_data[user_id]["username"] = query.from_user.username or query.from_user.first_name
    
    # Основные команды
    if query.data == "play_menu":
        await play_menu(query, user_id)
    
    elif query.data == "balance":
        await show_balance(query, user_id)
    
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
    
    elif query.data == "back_to_main":
        keyboard = [
            [InlineKeyboardButton("Играть", callback_data="play_menu")],
            [InlineKeyboardButton("Баланс", callback_data="balance")],
            [InlineKeyboardButton("Игровые чаты", callback_data="chats")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        welcome_text = """
<b>Добро пожаловать в Spindja Casino!</b>

<u>Быстрые команды:</u>
• Напишите <code>мины</code> - начать игру
• Напишите сумму с ₽ - установить ставку
        """
        
        await query.edit_message_text(
            text=welcome_text,
            parse_mode='HTML',
            reply_markup=reply_markup
        )
    
    # Игра в мины
    elif query.data == "game_mines":
        await mines_setup(query, user_id)
    
    elif query.data == "change_bet":
        await change_bet(query, user_id)
    
    elif query.data == "change_mines":
        await change_mines(query, user_id)
    
    elif query.data.startswith("set_bet_"):
        bet = int(query.data.split("_")[2])
        if bet <= user_data[user_id]["balance"]:
            game_data[user_id]["bet"] = bet
        await mines_setup(query, user_id)
    
    elif query.data.startswith("set_mines_"):
        mines = int(query.data.split("_")[2])
        if MIN_MINES <= mines <= MAX_MINES:
            game_data[user_id]["mines_count"] = mines
        await mines_setup(query, user_id)
    
    elif query.data == "start_mines_game":
        if user_data[user_id]["balance"] < game_data[user_id]["bet"]:
            await query.answer("Недостаточно средств на балансе!")
            await show_balance(query, user_id)
        else:
            await play_mines_game(query, user_id)
    
    elif query.data.startswith("cell_"):
        cell_idx = int(query.data.split("_")[1])
        await handle_cell_click(query, user_id, cell_idx)
    
    elif query.data == "cashout":
        await handle_cashout(query, user_id)
    
    elif query.data.startswith("cell_opened_"):
        await query.answer("Эта ячейка уже открыта!")

# Изменение ставки
async def change_bet(query, user_id):
    """Изменение ставки"""
    balance = user_data[user_id]["balance"]
    current_bet = game_data[user_id]["bet"]
    
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
             f"Ваш баланс: {balance}₽",
        parse_mode='HTML',
        reply_markup=reply_markup
    )

# Изменение количества мин
async def change_mines(query, user_id):
    """Изменение количества мин"""
    keyboard = []
    
    row = []
    for mines in range(MIN_MINES, MAX_MINES + 1):
        multiplier = MULTIPLIERS[mines]
        row.append(InlineKeyboardButton(f"{mines}({multiplier}x)", callback_data=f"set_mines_{mines}"))
        if len(row) == 4:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    
    keyboard.append([InlineKeyboardButton("Назад", callback_data="game_mines")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        text="<b>Выберите количество мин</b>\n\nЧем больше мин, тем выше множитель!",
        parse_mode='HTML',
        reply_markup=reply_markup
    )

# Основная функция
def main() -> None:
    """Запуск бота"""
    application = Application.builder().token(TOKEN).build()
    
    # Регистрируем обработчики команд
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("givemoney", givemoney))
    application.add_handler(CommandHandler("game", game_command))
    
    # Регистрируем обработчик кнопок
    application.add_handler(CallbackQueryHandler(button_handler))
    
    # Регистрируем обработчик текстовых сообщений
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        handle_text_message
    ))
    
    print("Бот запущен...")
    print(f"Администратор: {ADMIN_ID}")
    print("Для админа доступны команды:")
    print("/givemoney ID сумма - выдать баланс")
    print("/game mines номер - просмотр информации об игре")
    
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
