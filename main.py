import asyncio
import random
from datetime import datetime
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.enums.parse_mode import ParseMode
from aiogram.client.default import DefaultBotProperties

# Токен бота
BOT_TOKEN = "8720038863:AAHdj6ewEX_s3M55wgTU5oeAx3TtpxMLpeo"

# ID кастомных эмодзи
EMOJI = {
    "star": "5325547803936572038",
    "settings": "5377361859898805044",
    "gift": "5226731292334235524",
    "1": "5303184424622376167",
    "2": "5305511184500278068",
    "3": "5303433253552669683",
    "dollar": "5409048419211682843"
}

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

# Глобальные переменные для хранения курса
current_volume = 0
current_price = 0
last_update = None

def custom_emoji(emoji_id: str, fallback: str = "⭐") -> str:
    return f'<tg-emoji emoji-id="{emoji_id}">{fallback}</tg-emoji>'

def generate_new_course_data():
    """Генерирует новые случайные значения"""
    volume = round(random.uniform(780_000_000, 960_000_000), 2)
    price = round(random.uniform(0.07, 0.48), 4)
    return volume, price

async def update_course_periodically():
    """Фоновая задача: обновляет курс каждые 5 минут"""
    global current_volume, current_price, last_update
    while True:
        current_volume, current_price = generate_new_course_data()
        last_update = datetime.now()
        print(f"🔄 Курс обновлён: {current_volume:,.0f}$ / {current_price}$ в {last_update.strftime('%H:%M:%S')}")
        await asyncio.sleep(1500)  # 5 минут = 300 секунд

# Клавиатура главного меню
def main_menu_keyboard():
    builder = InlineKeyboardBuilder()
    builder.add(types.InlineKeyboardButton(text="📊 Курс", callback_data="course"))
    return builder.as_markup()

# Кнопка "Назад"
def back_keyboard():
    builder = InlineKeyboardBuilder()
    builder.add(types.InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_main"))
    return builder.as_markup()

# Старт
@dp.message(Command("start"))
async def cmd_start(message: Message):
    fullname = message.from_user.full_name
    text = (
        f"{custom_emoji(EMOJI['star'])} | Привет, {fullname} — "
        f"добро пожаловать в LBC Coin BOT!\n\n"
        f"{custom_emoji(EMOJI['settings'])} | Используй кнопку ниже:"
    )
    await message.answer(text, reply_markup=main_menu_keyboard())

# Курс
@dp.callback_query(lambda c: c.data == "course")
async def course_callback(callback: CallbackQuery):
    global current_volume, current_price, last_update
    
    # Если курс ещё не сгенерирован (при первом запуске)
    if current_volume == 0:
        current_volume, current_price = generate_new_course_data()
        last_update = datetime.now()
    
    time_msk = last_update.strftime("%H:%M:%S")
    text = (
        f"{custom_emoji(EMOJI['star'])} Курс LBC на {time_msk}\n"
        f"Объём: {current_volume:,.0f}$ {custom_emoji(EMOJI['dollar'])}\n"
        f"Курс: {current_price}$ {custom_emoji(EMOJI['dollar'])}"
    )
    await callback.message.edit_text(text, reply_markup=back_keyboard())
    await callback.answer()

# Назад в главное меню
@dp.callback_query(lambda c: c.data == "back_to_main")
async def back_to_main_callback(callback: CallbackQuery):
    fullname = callback.from_user.full_name
    text = (
        f"{custom_emoji(EMOJI['star'])} | Привет, {fullname} — "
        f"добро пожаловать в LBC Coin BOT!\n\n"
        f"{custom_emoji(EMOJI['settings'])} | Используй кнопку ниже:"
    )
    await callback.message.edit_text(text, reply_markup=main_menu_keyboard())
    await callback.answer()

# Запуск
async def main():
    print("🚀 Бот запускается...")
    
    # Запускаем фоновую задачу для обновления курса каждые 5 минут
    asyncio.create_task(update_course_periodically())
    
    # Генерируем первый курс сразу при старте
    global current_volume, current_price, last_update
    current_volume, current_price = generate_new_course_data()
    last_update = datetime.now()
    print(f"💰 Начальный курс: {current_volume:,.0f}$ / {current_price}$")
    
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
