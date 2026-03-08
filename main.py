import asyncio
import logging
from datetime import datetime
from typing import Union

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
import asyncio

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

# ==== FSM для админки (рассылка) ====
class AdminStates(StatesGroup):
    waiting_for_broadcast = State()  # Ждем текст рассылки
    waiting_for_user_id_balance = State()  # Ждем ID для изменения баланса
    waiting_for_balance_amount = State()  # Ждем сумму изменения
    waiting_for_user_id_reset = State()  # Ждем ID для сброса

# ==== Генерация клавиатур (Inline) ====
def main_menu_keyboard():
    """Главное меню (4 кнопки)."""
    builder = InlineKeyboardBuilder()
    builder.button(text="👤 Профиль", callback_data="profile")
    builder.button(text="🏆 Топ", callback_data="top")
    builder.button(text="❓ Помощь", callback_data="help")
    builder.button(text="💎 Донат", callback_data="donate")
    builder.adjust(2)  # по 2 кнопки в ряд
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
        f"Я - бот для раздачи печенек за активность в нашем "
        f"<a href='{CHANNEL_LINK}'>Telegram канале</a>.\n\n"
        f"🍪 В конце каждого месяца подводятся итоги, а топ-10 охотников "
        f"получают крутые вознаграждения на нашем сервере!\n\n"
        f"😎 <b>Вперед на Охоту за Печеньками!</b>\n"
        f"Покажи всем, кто здесь BOSS!"
    )

    await message.answer(text, reply_markup=main_menu_keyboard(), disable_web_page_preview=True)

# ==== Обработчики Inline кнопок (Callback) ====
@dp.callback_query(F.data == "back_to_main")
async def back_to_main(callback: CallbackQuery):
    """Возврат в главное меню."""
    await callback.message.edit_text(
        text="🥰 Главное меню",
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
        f"⭐ <b>Твой профиль:</b>\n\n"
        f"👤 Ник: {user.full_name}\n"
        f"📱 ID: <code>{user.id}</code>\n"
        f"🗓️ Дата регистрации: {reg_date}\n\n"
        f"💰 В твоем мешке: <b>{balance} 🍪</b>\n"
        f"📊 Позиция в топе: <b>{place} Место</b>"
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

    text = "🏆 <b>Топ Охотников за Печеньем:</b>\n(самые крутые ребята)\n\n"

    medals = ["🥇", "🥈", "🥉", "🏅", "🏅"]
    for i, (user_id_str, user_info) in enumerate(top_users):
        # Пытаемся получить имя пользователя
        uname = user_info.get('username', 'Неизвестно')
        # Если это username (без @), то делаем ссылку
        if uname and not uname.startswith('Неизвестно'):
            display_name = f"@{uname}" if not uname.startswith('@') else uname
        else:
            display_name = f"ID {user_id_str}"

        text += f"{medals[i]} {i+1} Место: {display_name} ({user_info.get('balance', 0)} 🍪)\n"

    text += f"\n💰 В твоем мешке: <b>{balance} 🍪</b>\n"
    text += f"📊 Позиция в топе: <b>{place} Место</b>"

    await callback.message.edit_text(text, reply_markup=back_button_keyboard())
    await callback.answer()

# ---- Помощь ----
@dp.callback_query(F.data == "help")
async def show_help(callback: CallbackQuery):
    """Показывает раздел помощи."""
    text = (
        "❓ <b>Помощь:</b>\n\n"
        "😉 Если что-то не понятно, воспользуйся кнопочным меню.\n"
        "Печеньки выдаются каждый час в нашем канале. Жми кнопку 'Забрать' и будь первым!"
    )
    await callback.message.edit_text(text, reply_markup=support_keyboard())
    await callback.answer()

# ---- Донат ----
@dp.callback_query(F.data == "donate")
async def show_donate(callback: CallbackQuery):
    """Показывает раздел доната."""
    text = (
        "💎 <b>Поддержка проекта.</b>\n\n"
        "❤️ Если тебе понравился бот и ты хочешь поддержать его развитие, "
        "можешь сделать добровольное пожертвование.\n\n"
        "🙃 Для этого просто выбери желаемую сумму:"
    )
    await callback.message.edit_text(text, reply_markup=donate_keyboard())
    await callback.answer()

@dp.callback_query(F.data.startswith("donate_"))
async def process_donate(callback: CallbackQuery):
    """Обработка выбора суммы доната."""
    amount = callback.data.split("_")[1]
    await callback.message.edit_text(
        f"💎 Отправьте подарок на пользователя: @Dev_pranik\n"
        f"(Выбрано: {amount} звёзд)",
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
        "🍪 <b>РАЗДАЧА ПЕЧЕНЬЕК!</b>\n\n"
        "Кто первый нажмёт кнопку — тот получит +5 печенек!\n"
        "Торопись, удача любит смелых!"
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
                    f"✅ Раздача успешно отправлена в чат!\nID раздачи: {claim_id}"
                )
            except:
                pass
                
    except Exception as e:
        error_text = f"❌ Ошибка при отправке раздачи в чат {GIVEAWAY_CHAT_ID}: {e}"
        logging.error(error_text)
        
        # Уведомляем админов об ошибке
        for admin_id in ADMIN_IDS:
            try:
                await bot.send_message(admin_id, error_text)
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
        f"🎉 Поздравляю, {callback.from_user.full_name}!\n"
        f"Ты успел первым и получил +5 🍪!\n"
        f"Теперь в твоём мешке: {new_balance} 🍪."
    )
    await callback.answer("✅ Ты получил 5 печенек!", show_alert=True)
    
    # Уведомляем админов о том, кто получил печеньку
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(
                admin_id,
                f"🍪 Печеньку получил: {callback.from_user.full_name} (ID: {user_id})\n"
                f"Теперь у него {new_balance} 🍪"
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
        await message.answer("⛔ Доступ запрещён.")
        return

    text = (
        "👑 <b>Панель администратора</b>\n\n"
        "Выберите действие:"
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
            "📢 Введите текст для рассылки всем пользователям:"
        )
        await state.set_state(AdminStates.waiting_for_broadcast)
        await callback.answer()

    elif action == "admin_change_balance":
        await callback.message.edit_text(
            "💰 Введите ID пользователя, которому хотите изменить баланс:"
        )
        await state.set_state(AdminStates.waiting_for_user_id_balance)
        await callback.answer()

    elif action == "admin_reset_balance":
        await callback.message.edit_text(
            "🔄 Введите ID пользователя для сброса баланса (поставьте 0):"
        )
        await state.set_state(AdminStates.waiting_for_user_id_reset)
        await callback.answer()

    elif action == "admin_stats":
        db = get_all_users()
        total_users = len(db)
        total_cookies = sum(u.get('balance', 0) for u in db.values())
        await callback.message.edit_text(
            f"📊 <b>Статистика</b>\n\n"
            f"👥 Всего пользователей: {total_users}\n"
            f"🍪 Всего печенек: {total_cookies}\n"
            f"⭐ Среднее печенек: {total_cookies / max(total_users, 1):.1f}",
            reply_markup=back_button_keyboard()
        )
        await callback.answer()

    elif action == "admin_test_giveaway":
        await send_cookie_giveaway()  # Отправляем тестовую раздачу
        await callback.message.edit_text(
            "✅ Тестовая раздача отправлена в указанный чат.",
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
    await message.answer(f"Начинаю рассылку...\nТекст:\n{broadcast_text}")

    db = get_all_users()
    sent = 0
    failed = 0
    for user_id_str in db.keys():
        try:
            await bot.send_message(int(user_id_str), broadcast_text)
            sent += 1
            await asyncio.sleep(0.05)  # Небольшая задержка, чтобы не спамить
        except Exception as e:
            failed += 1
            logging.error(f"Не удалось отправить пользователю {user_id_str}: {e}")

    await message.answer(f"✅ Рассылка завершена.\nОтправлено: {sent}\nОшибок: {failed}")
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
        await message.answer("Введите сумму изменения (например: +5 или -3):")
        await state.set_state(AdminStates.waiting_for_balance_amount)
    except ValueError:
        await message.answer("❌ Некорректный ID. Введите число.")

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

        await message.answer(f"✅ Баланс пользователя {user_id} изменён.\n"
                             f"Было: {current}, стало: {new_balance} 🍪")
    except ValueError:
        await message.answer("❌ Некорректная сумма.")
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
        await message.answer(f"✅ Баланс пользователя {user_id} сброшен.\nБыло: {old_balance}")
    except ValueError:
        await message.answer("❌ Некорректный ID.")
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
