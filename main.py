import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Токен бота
TOKEN = "7979153629:AAFPh1qGUDzsX8ljP3MZ2ROAQ9vA_XtkBdE"

# Обработчик команды /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отправляет приветственное сообщение с кнопками"""
    
    # Создаем клавиатуру с кнопками
    keyboard = [
        [InlineKeyboardButton("🎮 Играть", callback_data="play")],
        [InlineKeyboardButton("💬 Игровые чаты", callback_data="chats")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Текст приветственного сообщения
    welcome_text = """
🌟 <b>Привет, добро пожаловать в Spindja!</b> 🌟

🎉 <b>Рады видеть тебя в нашем казино!</b> 🎰

🔔 <b>Подписывайся на наш канал</b> (ссылка t.me/spindja) чтобы следить за новостями и конкурсами. 🔔

💰 <i>Удачи в играх и больших выигрышей!</i> 💰
    """
    
    # Отправляем сообщение с клавиатурой
    await update.message.reply_text(
        welcome_text,
        parse_mode='HTML',
        reply_markup=reply_markup
    )

# Обработчик нажатий на кнопки
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает нажатия на кнопки"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "play":
        # Ответ для кнопки "Играть"
        await query.edit_message_text(
            text="⏳ <b>Скоро...</b> ⏳\n\n🎰 <i>Раздел в разработке. Ожидайте скорого запуска!</i> 🎰",
            parse_mode='HTML'
        )
    
    elif query.data == "chats":
        # Клавиатура для игровых чатов
        keyboard = [
            [InlineKeyboardButton("Перейти в чат", url="https://t.me/+fVJwoK3brgU0NmMy")],
            [InlineKeyboardButton("🔙 Назад", callback_data="back")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Текст для игровых чатов
        chats_text = """
💬 <b>Игровые чаты</b> 💬

🎯 <b>Это отличное место чтобы:</b>
• Найти друзей и единомышленников 👥
• Обсудить стратегии и тактики игры 🎮
• Участвовать в конкурсах и раздачах 🎁
• Поднять денег в увлекательных соревнованиях 💰

🔥 <i>Присоединяйся к нашему сообществу!</i> 🔥
        """
        
        await query.edit_message_text(
            text=chats_text,
            parse_mode='HTML',
            reply_markup=reply_markup
        )
    
    elif query.data == "back":
        # Возврат к главному меню
        keyboard = [
            [InlineKeyboardButton("🎮 Играть", callback_data="play")],
            [InlineKeyboardButton("💬 Игровые чаты", callback_data="chats")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        welcome_text = """
🌟 <b>Привет, добро пожаловать в Spindja!</b> 🌟

🎉 <b>Рады видеть тебя в нашем казино!</b> 🎰

🔔 <b>Подписывайся на наш канал</b> (ссылка t.me/spindja) чтобы следить за новостями и конкурсами. 🔔

💰 <i>Удачи в играх и больших выигрышей!</i> 💰
        """
        
        await query.edit_message_text(
            text=welcome_text,
            parse_mode='HTML',
            reply_markup=reply_markup
        )

# Основная функция
def main() -> None:
    """Запуск бота"""
    # Создаем Application
    application = Application.builder().token(TOKEN).build()
    
    # Регистрируем обработчики
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_handler))
    
    # Запускаем бота
    print("Бот запущен...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
