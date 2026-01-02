import telebot
from telebot import types
import sqlite3
import random
import time

# ================= НАСТРОЙКИ =================
TOKEN = '8589509755:AAEDnctjq8KFxQ7ouIyQjh-R4qALxBUt3gU'
ADMIN_ID = 6938345434 
RATES = {'ton_usdt': 5.25, 'btc_usdt': 64500, 'usdt_ton': 1/5.25, 'usdt_btc': 1/64500}

bot = telebot.TeleBot(TOKEN)

# ================= БАЗА ДАННЫХ =================
def init_db():
    with sqlite3.connect('mega_pro.db') as conn:
        cursor = conn.cursor()
        # Исправленный синтаксис создания таблиц (убраны лишние скобки)
        cursor.execute('''CREATE TABLE IF NOT EXISTS users 
            (id INTEGER PRIMARY KEY, usdt REAL DEFAULT 10.0, btc REAL DEFAULT 0, 
            ton REAL DEFAULT 0, ref_id INTEGER, name TEXT, last_bonus TEXT, is_dealer INTEGER DEFAULT 0)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS promo 
            (code TEXT PRIMARY KEY, amount REAL, uses INTEGER)''')
        conn.commit()

def get_u(uid, name="User"):
    init_db()
    with sqlite3.connect('mega_pro.db') as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT usdt, btc, ton, ref_id, last_bonus, is_dealer FROM users WHERE id = ?", (uid,))
        res = cursor.fetchone()
        if res: 
            return {'usdt': res[0], 'btc': res[1], 'ton': res[2], 'ref': res[3], 'last_bonus': res[4], 'is_dealer': res[5]}
        cursor.execute("INSERT INTO users (id, usdt, btc, ton, name) VALUES (?, 10.0, 0, 0, ?)", (uid, name))
        conn.commit()
        return {'usdt': 10.0, 'btc': 0, 'ton': 0, 'ref': None, 'last_bonus': None, 'is_dealer': 0}

def update_bal(uid, amount, cur='usdt'):
    with sqlite3.connect('mega_pro.db') as conn:
        conn.execute(f"UPDATE users SET {cur} = {cur} + ? WHERE id = ?", (amount, uid))

# ================= КЛАВИАТУРЫ =================
def main_kb(uid):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add("👛 Кошелек", "🔄 Обмен", "🎲 Игры", "📊 Рейтинг", "👥 Рефералы", "🎁 Бонусы", "⭐ Пожертвовать")
    if uid == ADMIN_ID: markup.add("⚙️ Admin")
    return markup

# ================= ОБМЕННИК =================
@bot.message_handler(func=lambda m: m.text == "🔄 Обмен")
def exchange_menu(message):
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("💎 TON → 💵 USDT", callback_data="ex_ton_usdt"),
        types.InlineKeyboardButton("💵 USDT → 💎 TON", callback_data="ex_usdt_ton"),
        types.InlineKeyboardButton("₿ BTC → 💵 USDT", callback_data="ex_btc_usdt"),
        types.InlineKeyboardButton("💵 USDT → ₿ BTC", callback_data="ex_usdt_btc")
    )
    bot.send_message(message.chat.id, "💱 <b>Выберите направление обмена:</b>", parse_mode='HTML', reply_markup=markup)

@bot.callback_query_handler(func=lambda c: c.data.startswith("ex_"))
def exchange_step(call):
    _, f, t = call.data.split('_')
    msg = bot.send_message(call.message.chat.id, f"Введите количество {f.upper()} для обмена:")
    bot.register_next_step_handler(msg, lambda m: finalize_ex(m, f, t))

def finalize_ex(m, f, t):
    try:
        amt = float(m.text.replace(',', '.'))
        u = get_u(m.from_user.id)
        if u[f] < amt: return bot.send_message(m.chat.id, "❌ Недостаточно средств!")
        rate = RATES[f"{f}_{t}"]
        res = amt * rate
        update_bal(m.from_user.id, -amt, f)
        update_bal(m.from_user.id, res, t)
        bot.send_message(m.chat.id, f"✅ Успешно! +{res:.4f} {t.upper()}")
    except: bot.send_message(m.chat.id, "❌ Ошибка ввода (введите число).")

# ================= РЕЙТИНГ =================
@bot.message_handler(func=lambda m: m.text == "📊 Рейтинг")
def show_rating(message):
    with sqlite3.connect('mega_pro.db') as conn:
        users = conn.execute("SELECT name, usdt, ton, btc FROM users").fetchall()
    top = sorted(users, key=lambda x: x[1] + (x[2]*RATES['ton_usdt']) + (x[3]*RATES['btc_usdt']), reverse=True)[:10]
    txt = "🏆 <b>ТОП-10 БОГАЧЕЙ</b>\n⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
    for i, u in enumerate(top, 1):
        total = u[1] + (u[2]*RATES['ton_usdt']) + (u[3]*RATES['btc_usdt'])
        txt += f"{i}. {u[0]} — <code>{total:.2f} USDT</code>\n"
    bot.send_message(message.chat.id, txt, parse_mode='HTML')

# ================= ИГРЫ =================
@bot.message_handler(func=lambda m: m.text == "🎲 Игры")
def games_hub(message):
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("🏰 Mines", callback_data="g_mines"),
        types.InlineKeyboardButton("🚀 Crash", callback_data="g_crash"),
        types.InlineKeyboardButton("🎡 Roulette", callback_data="g_roul"),
        types.InlineKeyboardButton("🎲 Dice", callback_data="g_dice")
    )
    bot.send_message(message.chat.id, "🎯 <b>Выберите игру:</b>", parse_mode='HTML', reply_markup=markup)

# --- CRASH (НОВАЯ МЕХАНИКА) ---
@bot.callback_query_handler(func=lambda c: c.data == "g_crash")
def crash_start(call):
    msg = bot.send_message(call.message.chat.id, "💰 Введите ставку USDT:")
    bot.register_next_step_handler(msg, crash_get_bet)

def crash_get_bet(m):
    try:
        bet = float(m.text.replace(',', '.'))
        if get_u(m.from_user.id)['usdt'] < bet: return bot.send_message(m.chat.id, "❌ Мало USDT!")
        msg = bot.send_message(m.chat.id, "🚀 Введите множитель X (например 2.5):")
        bot.register_next_step_handler(msg, lambda ms: crash_logic(ms, bet))
    except: bot.send_message(m.chat.id, "❌ Ошибка")

def crash_logic(m, bet):
    try:
        target_x = float(m.text.replace(',', '.'))
        uid = m.from_user.id
        update_bal(uid, -bet)
        crash_point = round(random.uniform(1.0, 4.5), 2)
        bot.send_message(m.chat.id, f"🚀 Ракета летит... Цель: {target_x}x")
        time.sleep(2)
        if crash_point >= target_x:
            win = round(bet * target_x, 2)
            update_bal(uid, win)
            bot.send_message(m.chat.id, f"✅ Долетела до {crash_point}x! Выигрыш: {win} USDT")
        else:
            bot.send_message(m.chat.id, f"💥 Взрыв на {crash_point}x! Ставка сгорела.")
    except: pass

# --- MINES (БАШНИ) ---
active_mines = {}
@bot.callback_query_handler(func=lambda c: c.data == "g_mines")
def start_mines(call):
    msg = bot.send_message(call.message.chat.id, "Введите ставку USDT:")
    bot.register_next_step_handler(msg, init_mines)

def init_mines(m):
    try:
        bet = float(m.text.replace(',', '.'))
        if get_u(m.from_user.id)['usdt'] < bet: return
        update_bal(m.from_user.id, -bet)
        active_mines[m.from_user.id] = {'mines': random.sample(range(25), 3), 'open': [], 'bet': bet}
        render_mines(m.chat.id, m.from_user.id)
    except: pass

def render_mines(chat_id, uid, mid=None):
    game = active_mines[uid]
    markup = types.InlineKeyboardMarkup(row_width=5)
    btns = [types.InlineKeyboardButton("💎" if i in game['open'] else "❓", callback_data=f"m_c_{i}") for i in range(25)]
    markup.add(*btns)
    coeff = round(1.2 ** len(game['open']), 2)
    markup.add(types.InlineKeyboardButton(f"💰 ЗАБРАТЬ {round(game['bet']*coeff, 2)}", callback_data="m_cash"))
    if mid: bot.edit_message_text("🏰 Mines", chat_id, mid, reply_markup=markup)
    else: bot.send_message(chat_id, "🏰 Mines", reply_markup=markup)

@bot.callback_query_handler(func=lambda c: c.data.startswith("m_c_"))
def click_mine(call):
    uid, idx = call.from_user.id, int(call.data.split('_')[2])
    if uid not in active_mines: return
    game = active_mines[uid]
    if idx in game['mines']:
        bot.edit_message_text("💥 БУМ!", call.message.chat.id, call.message.message_id)
        del active_mines[uid]
    else:
        game['open'].append(idx)
        render_mines(call.message.chat.id, uid, call.message.message_id)

@bot.callback_query_handler(func=lambda c: c.data == "m_cash")
def cash_mine(call):
    uid = call.from_user.id
    if uid not in active_mines: return
    game = active_mines[uid]
    win = round(game['bet'] * (1.2 ** len(game['open'])), 2)
    update_bal(uid, win)
    bot.edit_message_text(f"✅ Выигрыш: {win} USDT!", call.message.chat.id, call.message.message_id)
    del active_mines[uid]

# ================= АДМИНКА + ПРОМО =================
@bot.message_handler(func=lambda m: m.text == "⚙️ Admin")
def admin_p(message):
    if message.from_user.id != ADMIN_ID: return
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("🎟 Создать Промо", callback_data="a_promo"))
    bot.send_message(message.chat.id, "🛠 Админ-панель", reply_markup=markup)

@bot.callback_query_handler(func=lambda c: c.data == "a_promo")
def create_promo_start(call):
    msg = bot.send_message(call.message.chat.id, "Формат: КОД СУММА КОЛВО (например GIFT 10 5)")
    bot.register_next_step_handler(msg, save_promo)

def save_promo(m):
    try:
        c, a, u = m.text.split()
        with sqlite3.connect('mega_pro.db') as conn:
            conn.execute("INSERT INTO promo VALUES (?, ?, ?)", (c.upper(), float(a), int(u)))
        bot.send_message(m.chat.id, "✅ Промокод создан!")
    except: bot.send_message(m.chat.id, "❌ Ошибка формата!")

@bot.message_handler(func=lambda m: m.text == "🎁 Бонусы")
def bonus_m(message):
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("🎟 Ввести промо", callback_data="u_promo"))
    bot.send_message(message.chat.id, "🎁 Меню бонусов", reply_markup=markup)

@bot.callback_query_handler(func=lambda c: c.data == "u_promo")
def use_promo_start(call):
    msg = bot.send_message(call.message.chat.id, "Введите промокод:")
    bot.register_next_step_handler(msg, activate_promo)

def activate_promo(m):
    code = m.text.upper()
    with sqlite3.connect('mega_pro.db') as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT amount, uses FROM promo WHERE code = ?", (code,))
        res = cursor.fetchone()
        if res and res[1] > 0:
            update_bal(m.from_user.id, res[0])
            conn.execute("UPDATE promo SET uses = uses - 1 WHERE code = ?", (code,))
            conn.commit()
            bot.send_message(m.chat.id, f"✅ Активирован! +{res[0]} USDT")
        else: bot.send_message(m.chat.id, "❌ Неверный код или лимит исчерпан.")

# ================= СТАРТ / КОШЕЛЕК / STARS =================
@bot.message_handler(commands=['start'])
def start(message):
    get_u(message.from_user.id, message.from_user.first_name)
    bot.send_message(message.chat.id, "💎 <b>CRYPTO BOT</b>", reply_markup=main_kb(message.from_user.id), parse_mode='HTML')

@bot.message_handler(func=lambda m: m.text == "👛 Кошелек")
def my_wallet(message):
    u = get_u(message.from_user.id)
    bot.send_message(message.chat.id, f"👛 <b>Баланс:</b>\nUSDT: {u['usdt']:.2f}\nTON: {u['ton']:.2f}\nBTC: {u['btc']:.6f}", parse_mode='HTML')

@bot.message_handler(func=lambda m: m.text == "⭐ Пожертвовать")
def donate_stars(message):
    bot.send_invoice(message.chat.id, "Донат", "Поддержка", "stars_pay", "", "XTR", [types.LabeledPrice("Stars", 50)])

@bot.pre_checkout_query_handler(func=lambda q: True)
def pre_checkout(q): bot.answer_pre_checkout_query(q.id, ok=True)

@bot.message_handler(func=lambda m: m.text == "👥 Рефералы")
def ref_system(message):
    link = f"https://t.me/{bot.get_me().username}?start={message.from_user.id}"
    bot.send_message(message.chat.id, f"👥 Ссылка для друзей:\n{link}")

init_db()
bot.polling(none_stop=True)