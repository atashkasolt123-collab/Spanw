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
game_counter = 0
games_history: Dict[int, Dict] = {}

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
MIN_TRANSFER_AMOUNT = 10  # Минимальная сумма перевода

# Обработчик команды /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отправляет приветственное сообщение с кнопками"""
    user_id = update.effective_user.id
    
    if user_id not in user_data:
        user_data[user_id] = {"balance": INITIAL_BALANCE, "username": update.effective_user.username or update.effective_user.first_name}
    
    keyboard = [
        [InlineKeyboardButton("Играть", callback_data="play_menu")],
        [InlineKeyboardButton("Баланс", callback_data="balance")],
        [InlineKeyboardButton("Игровые чаты", callback_data="chats")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    welcome_text = f"""
<b>Добро пожаловать в Spindja Casino!</b>

Мы рады видеть вас в нашем казино!

Подписывайтесь на наш канал @spindja чтобы следить за новостями и конкурсами.

🎮 <b>Ваш баланс:</b> {user_data[user_id]['balance']}₽

<u>Доступные команды:</u>
• <code>/balance</code> / <code>/bal</code> / <code>/b</code> - показать баланс
• <code>/pay сумма</code> - перевести другу (ответом на сообщение)
• <code>/pay ID сумма</code> - перевести по ID пользователя
• Напишите <code>мины</code> - игра в мины
• Напишите <code>кубы</code> - игра в кубы
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
    
    if user_id not in user_data:
        user_data[user_id] = {"balance": INITIAL_BALANCE, "username": update.effective_user.username or update.effective_user.first_name}
    
    balance = user_data[user_id]["balance"]
    saved_bet = user_bets.get(user_id, None)
    bet_info = f"\n💾 Сохраненная ставка: {saved_bet}₽" if saved_bet else ""
    
    balance_text = f"""
<b>💰 Ваш баланс</b>

📊 Текущий баланс: <b>{balance}₽</b>{bet_info}

🎮 <u>Минимальные ставки:</u>
• Все игры: {MIN_BET}₽
• Переводы: {MIN_TRANSFER_AMOUNT}₽

🎲 <u>Доступные игры:</u>
• <b>Мины</b> - 2 мины, множитель 1.12x
• <b>Кубы</b> - несколько режимов игры

💸 <u>Переводы:</u>
Используйте <code>/pay сумма</code> для переводов друзьям!
    """
    
    keyboard = [
        [InlineKeyboardButton("Пополнить баланс", callback_data="deposit")],
        [InlineKeyboardButton("Меню игр", callback_data="play_menu")],
        [InlineKeyboardButton("Игровые чаты", callback_data="chats")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        balance_text,
        parse_mode='HTML',
        reply_markup=reply_markup
    )

# Команда для переводов /pay
async def pay_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Перевод средств другому пользователю"""
    user_id = update.effective_user.id
    username = update.effective_user.username or update.effective_user.first_name
    
    if user_id not in user_data:
        user_data[user_id] = {"balance": INITIAL_BALANCE, "username": username}
    
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
        else:
            await update.message.reply_text("❌ Неверный формат получателя. Используйте числовой ID.")
            return
        
        if target_id == user_id:
            await update.message.reply_text("❌ Нельзя переводить деньги самому себе!")
            return
        
        # Проверяем существование пользователя
        if target_id not in user_data:
            # Создаем запись о пользователе, если он не существует
            user_data[target_id] = {"balance": INITIAL_BALANCE, "username": f"пользователь {target_id}"}
    
    # Проверяем сумму перевода
    if amount < MIN_TRANSFER_AMOUNT:
        await update.message.reply_text(f"❌ Минимальная сумма перевода: {MIN_TRANSFER_AMOUNT}₽")
        return
    
    # Проверяем баланс отправителя
    if user_data[user_id]["balance"] < amount:
        await update.message.reply_text(
            f"❌ Недостаточно средств для перевода.\n"
            f"Ваш баланс: {user_data[user_id]['balance']}₽\n"
            f"Сумма перевода: {amount}₽",
            parse_mode='HTML'
        )
        return
    
    # Рассчитываем комиссию
    fee = int(amount * TRANSFER_FEE_PERCENT / 100)
    net_amount = amount - fee
    
    # Выполняем перевод
    user_data[user_id]["balance"] -= amount
    user_data[target_id]["balance"] += net_amount
    
    # Сообщение об успешном переводе
    transfer_text = f"""
✅ <b>Перевод выполнен успешно!</b>

📤 <u>Отправитель:</u>
👤 {username} (ID: {user_id})
💰 Списано: {amount}₽
💸 Комиссия: {fee}₽ ({TRANSFER_FEE_PERCENT}%)
📊 Новый баланс: {user_data[user_id]['balance']}₽

📥 <u>Получатель:</u>
👤 {target_username} (ID: {target_id})
💰 Получено: {net_amount}₽
📊 Новый баланс: {user_data[target_id]['balance']}₽

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
                 f"📊 Ваш новый баланс: {user_data[target_id]['balance']}₽\n\n"
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
            "Используйте: <code>/число число сумма</code>\n"
            "Например: <code>/число 3 100</code>\n\n"
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
    if user_id not in user_data:
        user_data[user_id] = {"balance": INITIAL_BALANCE, "username": update.effective_user.username or update.effective_user.first_name}
    
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
    
    if user_data[user_id]["balance"] < amount:
        await update.message.reply_text(
            f"❌ Недостаточно средств на балансе.\n"
            f"Ваш баланс: {user_data[user_id]['balance']}₽",
            parse_mode='HTML'
        )
        return
    
    # Бросаем куб
    dice_result = random.randint(1, 6)
    
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
        user_data[user_id]["balance"] += win_amount
        
        result_text = f"""
🎲 <b>Кубы - Быстрая ставка</b>

🎯 Ваша ставка: <b>{bet_name}</b>
💰 Сумма: <b>{amount}₽</b>
🎲 Результат: <b>{dice_result}</b>

✅ <b>ВЫИГРЫШ!</b>
🏆 Выигрыш: <b>{win_amount}₽</b> (x{multiplier})
💰 Новый баланс: <b>{user_data[user_id]['balance']}₽</b>

🎉 Поздравляем с выигрышем!
        """
    else:
        user_data[user_id]["balance"] -= amount
        
        result_text = f"""
🎲 <b>Кубы - Быстрая ставка</b>

🎯 Ваша ставка: <b>{bet_name}</b>
💰 Сумма: <b>{amount}₽</b>
🎲 Результат: <b>{dice_result}</b>

❌ <b>ПРОИГРЫШ</b>
💸 Ставка не возвращается
💰 Новый баланс: <b>{user_data[user_id]['balance']}₽</b>

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
        
        if target_id not in user_data:
            user_data[target_id] = {"balance": INITIAL_BALANCE, "username": f"пользователь {target_id}"}
        
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
    
    # Если пользователь написал "кубы" или "кости" - запускаем игру в кубы
    if text in ["кубы", "кости", "dice"]:
        await start_dice_from_chat(update, user_id)
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
        "• <code>/balance</code> / <code>/bal</code> / <code>/b</code> - показать баланс\n"
        "• <code>/pay сумма</code> - перевести другу\n"
        "• Напишите <code>мины</code> - игра в мины\n"
        "• Напишите <code>кубы</code> - игра в кубы\n"
        "• <code>/чет сумма</code> - ставка на чет\n"
        "• <code>/нечет сумма</code> - ставка на нечет\n"
        "• <code>/число число сумма</code> - ставка на число (1-6)\n"
        "• <code>/больше сумма</code> - ставка на 4-6\n"
        "• <code>/меньше сумма</code> - ставка на 1-3\n"
        "• Напишите сумму с ₽ - установить ставку",
        parse_mode='HTML'
    )

# Запуск игры "Кубы" из чата
async def start_dice_from_chat(update: Update, user_id: int) -> None:
    """Запускает игру Кубы из текстового сообщения"""
    if user_id not in user_data:
        user_data[user_id] = {"balance": INITIAL_BALANCE, "username": update.effective_user.username or update.effective_user.first_name}
    
    balance = user_data[user_id]["balance"]
    
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

👤 {update.effective_user.username or update.effective_user.first_name}
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
• <code>/чет сумма</code>
• <code>/нечет сумма</code>
• <code>/число число сумма</code>
• <code>/больше сумма</code>
• <code>/меньше сумма</code>
    """
    
    await update.message.reply_text(
        text=setup_text,
        parse_mode='HTML',
        reply_markup=reply_markup
    )

# Меню пополнения баланса
async def deposit_menu(query, user_id):
    """Меню пополнения баланса"""
    balance = user_data[user_id]["balance"]
    
    keyboard = [
        [InlineKeyboardButton("Обратиться к администратору", callback_data="contact_admin")],
        [InlineKeyboardButton("Назад", callback_data="balance")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    deposit_text = f"""
<b>💰 Пополнение баланса</b>

💳 Ваш текущий баланс: <b>{balance}₽</b>

<u>Способы пополнения:</u>
1. <b>Администратор</b> - обратитесь к администратору через кнопку ниже
2. <b>Перевод от друга</b> - попросите друга перевести вам средства через команду <code>/pay</code>

📞 <b>Для пополнения баланса:</b>
Нажмите кнопку ниже чтобы связаться с администратором или попросите друга отправить вам перевод.
    """
    
    await query.edit_message_text(
        text=deposit_text,
        parse_mode='HTML',
        reply_markup=reply_markup
    )

# Связь с администратором
async def contact_admin(query, user_id):
    """Связь с администратором"""
    username = user_data[user_id].get("username", "Пользователь")
    balance = user_data[user_id]["balance"]
    
    keyboard = [
        [InlineKeyboardButton("Назад", callback_data="deposit")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    contact_text = f"""
<b>📞 Связь с администратором</b>

👤 Ваш профиль:
• ID: <code>{user_id}</code>
• Имя: {username}
• Баланс: {balance}₽

<u>Администратор:</u>
• ID: <code>{ADMIN_ID}</code>

<u>Инструкция:</u>
1. Напишите администратору в личные сообщения
2. Укажите ваш ID: <code>{user_id}</code>
3. Укажите сумму пополнения
4. Ожидайте ответа

⏱️ Обычно ответ поступает в течение 5-15 минут.
    """
    
    await query.edit_message_text(
        text=contact_text,
        parse_mode='HTML',
        reply_markup=reply_markup
    )

# Меню игры в кубы
async def dice_menu(query, user_id):
    """Меню игры в кубы"""
    balance = user_data[user_id]["balance"]
    
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
    balance = user_data[user_id]["balance"]
    
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
• <code>/чет сумма</code> - ставка на чет
• <code>/нечет сумма</code> - ставка на нечет
    """
    
    await query.edit_message_text(
        text=setup_text,
        parse_mode='HTML',
        reply_markup=reply_markup
    )

# Угадать число в кубах
async def dice_number(query, user_id):
    """Ставка на число в кубах"""
    balance = user_data[user_id]["balance"]
    
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
• <code>/число число сумма</code>
• Например: <code>/число 3 100</code>
    """
    
    await query.edit_message_text(
        text=setup_text,
        parse_mode='HTML',
        reply_markup=reply_markup
    )

# Больше/Меньше в кубах
async def dice_high_low(query, user_id):
    """Ставка на больше/меньше в кубах"""
    balance = user_data[user_id]["balance"]
    
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
• <code>/меньше сумма</code> - ставка на 1-3
• <code>/больше сумма</code> - ставка на 4-6
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
    game_data[user_id] = {
        "game_type": "dice",
        "bet_type": bet_type,
        "bet_value": bet_value,
        "amount": user_bets.get(user_id, MIN_BET)
    }
    
    balance = user_data[user_id]["balance"]
    saved_bet = user_bets.get(user_id, MIN_BET)
    
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
    if user_data[user_id]["balance"] < bet_amount:
        await query.answer("Недостаточно средств!")
        await show_balance(query, user_id)
        return
    
    # Бросаем куб
    dice_result = random.randint(1, 6)
    
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
        user_data[user_id]["balance"] += win_amount
        
        result_text = f"""
🎲 <b>Кубы - Результат</b>

🎯 Ваша ставка: <b>{bet_description}</b>
💰 Сумма: <b>{bet_amount}₽</b>
🎲 Выпало: <b>{dice_result}</b>

✅ <b>ВЫИГРЫШ!</b>
🏆 Выигрыш: <b>{win_amount}₽</b> (x{multiplier})
💰 Новый баланс: <b>{user_data[user_id]['balance']}₽</b>

🎉 Поздравляем с выигрышем!
        """
    else:
        user_data[user_id]["balance"] -= bet_amount
        
        result_text = f"""
🎲 <b>Кубы - Результат</b>

🎯 Ваша ставка: <b>{bet_description}</b>
💰 Сумма: <b>{bet_amount}₽</b>
🎲 Выпало: <b>{dice_result}</b>

❌ <b>ПРОИГРЫШ</b>
💸 Ставка не возвращается
💰 Новый баланс: <b>{user_data[user_id]['balance']}₽</b>

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
    balance = user_data[user_id]["balance"]
    current_bet = game_data[user_id]["amount"] if user_id in game_data else MIN_BET
    
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
    if user_id in game_data:
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
    if user_id not in user_data:
        user_data[user_id] = {"balance": INITIAL_BALANCE, "username": update.effective_user.username or update.effective_user.first_name}
    
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
            "mines_count": 2,
            "bet": saved_bet,
            "revealed_cells": [],
            "game_active": False,
            "current_multiplier": 1.0,
            "prize_cells": set(),
            "game_number": 0
        }
    else:
        game_data[user_id]["bet"] = saved_bet
        game_data[user_id]["mines_count"] = 2
        game_data[user_id]["game_active"] = False
    
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

👤 {update.effective_user.username or update.effective_user.first_name}
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
    
    if user_id not in user_data:
        user_data[user_id] = {"balance": INITIAL_BALANCE, "username": update.effective_user.username or update.effective_user.first_name}
    
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
    balance = user_data[user_id]["balance"]
    keyboard = [
        [InlineKeyboardButton("Пополнить баланс", callback_data="deposit")],
        [InlineKeyboardButton("Назад", callback_data="back_to_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    saved_bet = user_bets.get(user_id, None)
    bet_info = f"\n💾 Сохраненная ставка: {saved_bet}₽" if saved_bet else ""
    
    balance_text = f"""
<b>Ваш баланс</b>

💰 Баланс: {balance} ₽{bet_info}

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

# Главное меню игр
async def play_menu(query, user_id):
    """Меню выбора игры"""
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
    
    balance = user_data[user_id]["balance"]
    
    if user_id not in game_data:
        game_data[user_id] = {
            "mines_count": 2,
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
        "username": user_data.get(user_id, {}).get("username", "Неизвестно"),
        "bet": game["bet"],
        "mines_count": 2,
        "mines": set(mines_positions),
        "prizes": set(prize_positions),
        "status": "Активна",
        "time": "Текущее время"
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
<b>Мины · 2 мины</b>
<u>Номер игры:</u> #{game['game_number']}

Ставка {bet}₽ x{game['current_multiplier']:.2f} ➡️ Выигрыш {int(game['won_amount'])}₽

{field_text}

Текущий множитель: {game['current_multiplier']:.2f}x
Максимальный множитель: {multiplier}x
💣 Осталось мин: {2 - len([c for c in game['revealed_cells'] if c in game['mines']])}
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
        user_data[user_id] = {"balance": INITIAL_BALANCE, "username": query.from_user.username or query.from_user.first_name}
    
    # Сохраняем имя пользователя
    user_data[user_id]["username"] = query.from_user.username or query.from_user.first_name
    
    # Основные команды
    if query.data == "play_menu":
        await play_menu(query, user_id)
    
    elif query.data == "balance":
        await show_balance(query, user_id)
    
    elif query.data == "deposit":
        await deposit_menu(query, user_id)
    
    elif query.data == "contact_admin":
        await contact_admin(query, user_id)
    
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
• <code>/balance</code> / <code>/bal</code> / <code>/b</code> - показать баланс
• <code>/pay сумма</code> - перевести другу
• Напишите <code>мины</code> - игра в мины (2 мины)
• Напишите <code>кубы</code> - игра в кубы
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
    
    elif query.data == "mines_info":
        await mines_info(query, user_id)
    
    elif query.data.startswith("set_bet_"):
        bet = int(query.data.split("_")[2])
        if bet <= user_data[user_id]["balance"]:
            game_data[user_id]["bet"] = bet
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
    
    # Игра в кубы
    elif query.data == "game_dice":
        await dice_menu(query, user_id)
    
    elif query.data == "dice_even_odd":
        await dice_even_odd(query, user_id)
    
    elif query.data == "dice_number":
        await dice_number(query, user_id)
    
    elif query.data == "dice_high_low":
        await dice_high_low(query, user_id)
    
    elif query.data == "dice_bet_even":
        await process_dice_bet(query, user_id, "even")
    
    elif query.data == "dice_bet_odd":
        await process_dice_bet(query, user_id, "odd")
    
    elif query.data.startswith("dice_bet_num_"):
        number = query.data.split("_")[3]
        await process_dice_bet(query, user_id, "number", number)
    
    elif query.data == "dice_bet_high":
        await process_dice_bet(query, user_id, "high")
    
    elif query.data == "dice_bet_low":
        await process_dice_bet(query, user_id, "low")
    
    elif query.data == "dice_change_bet":
        await dice_change_bet(query, user_id)
    
    elif query.data.startswith("dice_set_bet_"):
        bet = int(query.data.split("_")[3])
        if bet <= user_data[user_id]["balance"]:
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
    
    elif query.data == "dice_roll":
        await dice_roll(query, user_id)

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
             f"Ваш баланс: {balance}₽\n\n"
             f"<i>В игре всегда 2 мины с множителем 1.12x</i>",
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
    
    # Команды для баланса и переводов
    application.add_handler(CommandHandler("balance", balance_command))
    application.add_handler(CommandHandler("bal", balance_command))
    application.add_handler(CommandHandler("b", balance_command))
    
    application.add_handler(CommandHandler("pay", pay_command))
    application.add_handler(CommandHandler("transfer", pay_command))
    application.add_handler(CommandHandler("send", pay_command))
    
    # Регистрируем команды для быстрых ставок в кубы
    application.add_handler(CommandHandler("чет", dice_even_command))
    application.add_handler(CommandHandler("нечет", dice_odd_command))
    application.add_handler(CommandHandler("число", dice_number_command))
    application.add_handler(CommandHandler("больше", dice_high_command))
    application.add_handler(CommandHandler("меньше", dice_low_command))
    
    # Алиасы для команд
    application.add_handler(CommandHandler("even", dice_even_command))
    application.add_handler(CommandHandler("odd", dice_odd_command))
    application.add_handler(CommandHandler("number", dice_number_command))
    application.add_handler(CommandHandler("high", dice_high_command))
    application.add_handler(CommandHandler("low", dice_low_command))
    
    # Регистрируем обработчик кнопок
    application.add_handler(CallbackQueryHandler(button_handler))
    
    # Регистрируем обработчик текстовых сообщений
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        handle_text_message
    ))
    
    print("=" * 50)
    print("Бот запущен...")
    print("=" * 50)
    print(f"Администратор: {ADMIN_ID}")
    print("\n📊 <b>Команды баланса:</b>")
    print("• /balance / /bal / /b - показать баланс")
    print("• /pay сумма - перевести другу (ответом на сообщение)")
    print("• /pay ID сумма - перевести по ID пользователя")
    print("\n🎮 <b>Игры:</b>")
    print("• Напишите 'мины' - игра в мины")
    print("• Напишите 'кубы' - игра в кубы")
    print("\n🎲 <b>Быстрые ставки в Кубы:</b>")
    print("• /чет сумма - ставка на чет (2,4,6) - x2")
    print("• /нечет сумма - ставка на нечет (1,3,5) - x2")
    print("• /число число сумма - ставка на число (1-6) - x6")
    print("• /больше сумма - ставка на 4-6 - x2")
    print("• /меньше сумма - ставка на 1-3 - x2")
    print("\n⚙️ <b>Для админа:</b>")
    print("• /givemoney ID сумма - выдать баланс")
    print("• /game mines номер - просмотр информации об игре")
    print("=" * 50)

if __name__ == '__main__':
    main()
