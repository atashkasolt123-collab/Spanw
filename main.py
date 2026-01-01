import asyncio
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiogram.utils.keyboard import ReplyKeyboardBuilder

# Настройка логирования
logging.basicConfig(level=logging.INFO)

# Токен вашего бота
BOT_TOKEN = "7979153629:AAHImYe78sJNWakDeNzEfgJClQzz9SQEUMU"

# Инициализация бота и диспетчера
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Создаем клавиатуру для главного меню
def get_main_keyboard():
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🎮 Играть"), KeyboardButton(text="💬 Игровые чаты")]
        ],
        resize_keyboard=True,
        input_field_placeholder="Выберите действие..."
    )
    return keyboard

# Создаем клавиатуру для меню чатов
def get_chats_keyboard():
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📲 Перейти в чат")],
            [KeyboardButton(text="🔙 Назад")]
        ],
        resize_keyboard=True,
        input_field_placeholder="Выберите действие..."
    )
    return keyboard

# Обработчик команды /start
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user = message.from_user
    
    # Отправляем стикер приветствия
    await message.answer_sticker("CAACAgIAAxkBAAIBYmZn5JnW-JJ_iPvrG8jSBrnSgFfQAAIBAAPANk8Tota8sSe9z1M1BA")
    
    welcome_text = f"""
🎰 <b>Привет {user.first_name}, добро пожаловать в Spindja!</b>

📢 <b>Подписывайся на наш канал</b> (ссылка t.me/spindja) чтобы следить за новостями и конкурсами.
    """
    
    await message.answer(
        welcome_text, 
        parse_mode="HTML", 
        reply_markup=get_main_keyboard()
    )

# Обработчик кнопки "🎮 Играть"
@dp.message(lambda message: message.text == "🎮 Играть")
async def process_play_game(message: types.Message):
    # Отправляем стикер "скоро"
    await message.answer_sticker("CAACAgIAAxkBAAIBZGZn5K1nQcIqwAeoAT84VdX4DgKNAAIEAAPANk8TLSP6BC-KgHk1BA")
    
    await message.answer(
        "🕒 <b>Скоро...</b>\n\n"
        "Игра находится в разработке. Следите за обновлениями в нашем канале!",
        parse_mode="HTML",
        reply_markup=get_main_keyboard()
    )

# Обработчик кнопки "💬 Игровые чаты"
@dp.message(lambda message: message.text == "💬 Игровые чаты")
async def process_game_chats(message: types.Message):
    # Отправляем стикер чата
    await message.answer_sticker("CAACAgIAAxkBAAIBZmZn5Qkbyp7ex5C-2wLTh0vALlW1AAIHAAPANk8T4qyiMmkW0-o1BA")
    
    chat_text = """
💬 <b>Игровые чаты</b> 

Это отличное место чтобы:
• 🔍 Найти друзей
• 💭 Обсудить игру
• 💰 Поднять денег в конкурсах и раздачах

<b>Ссылка на чат:</b> https://t.me/+fVJwoK3brgU0NmMy
    """
    
    await message.answer(
        chat_text, 
        parse_mode="HTML", 
        reply_markup=get_chats_keyboard()
    )

# Обработчик кнопки "📲 Перейти в чат"
@dp.message(lambda message: message.text == "📲 Перейти в чат")
async def process_go_to_chat(message: types.Message):
    await message.answer(
        "👇 <b>Нажмите на ссылку ниже, чтобы перейти в игровой чат:</b>\n\n"
        "🔗 https://t.me/+fVJwoK3brgU0NmMy",
        parse_mode="HTML",
        reply_markup=get_chats_keyboard()
    )

# Обработчик кнопки "🔙 Назад"
@dp.message(lambda message: message.text == "🔙 Назад")
async def process_back(message: types.Message):
    user = message.from_user
    
    welcome_text = f"""
🎰 <b>Привет {user.first_name}, добро пожаловать в Spindja!</b>

📢 <b>Подписывайся на наш канал</b> (ссылка t.me/spindja) чтобы следить за новостями и конкурсами.
    """
    
    await message.answer(
        welcome_text, 
        parse_mode="HTML", 
        reply_markup=get_main_keyboard()
    )

# Основная функция
async def main():
    print("🎲 Бот Spindja запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Бот остановлен")
