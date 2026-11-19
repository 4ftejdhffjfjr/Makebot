import asyncio
import logging
import os
import sqlite3
from datetime import datetime

from cryptography.fernet import Fernet, InvalidToken

from aiogram import Bot, Dispatcher, F, types
from aiogram.types import Message, CallbackQuery, PreCheckoutQuery
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.exceptions import TelegramBadRequest
import socket

# 1. Сохраняем оригинальную функцию
original_getaddrinfo = socket.getaddrinfo

# 2. Создаем подмену для api.telegram.org
def new_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    if host == 'api.telegram.org':
        # Возвращаем прямой IPv4-адрес серверов Telegram
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('149.154.167.220', port))]
    return original_getaddrinfo(host, port, family, type, proto, flags)

# 3. Применяем патч
socket.getaddrinfo = new_getaddrinfo

# ==========================================
# --- НАСТРОЙКИ ---
# ==========================================
BOT_TOKEN = "9071984522:AAGQgBn4mzzeixs0bbLq-Fu7JOgS9CJwAEQ"    
ADMIN_ID = 5029096746             
REQUIRED_CHANNEL = "@Make_bots155"     
CONTACT_TEXT = "📞 Наши контакты:\nТелефон: +7 (995) 412-89-08\nАдмин: @Plot1335"
MAX_BOTS_PER_USER = 3
HOSTING_PRICE = 250
HOSTING_DAYS = 14
KEY_FILE = "6YURra1GjvPtqFAuTzHSHNxRhtXw_bpo_qlzHxu5-Pg="

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# --- БАЗА ДАННЫХ ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "database.db")
db = sqlite3.connect(DB_PATH, check_same_thread=False)
db.row_factory = sqlite3.Row

# --- ШИФРОВАНИЕ ТОКЕНОВ (FERNET) ---
def _load_or_create_key() -> bytes:
    key_path = os.path.join(BASE_DIR, KEY_FILE)
    if os.path.exists(key_path):
        with open(key_path, "rb") as f:
            return f.read().strip()
    key = Fernet.generate_key()
    with open(key_path, "wb") as f:
        f.write(key)
    log.warning(f"🔐 Создан новый ключ шифрования: {key_path}. НЕ ТЕРЯЙ ЕГО!")
    return key

FERNET = Fernet(_load_or_create_key())

def _is_fernet_token(s: str) -> bool:
    return isinstance(s, str) and s.startswith("gAAAAA")

def enc(text: str) -> str:
    return FERNET.encrypt(text.encode()).decode()

def dec(text: str) -> str:
    if not text:
        return text
    try:
        return FERNET.decrypt(text.encode()).decode()
    except InvalidToken:
        if ":" in text and not _is_fernet_token(text):
            return text
        raise ValueError("Не удалось расшифровать токен. Потерян secret.key.")

def iso(now): return now.isoformat()

def init_db():
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA synchronous=NORMAL")

    db.execute("""CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        first_name TEXT
    )""")
    db.execute("""CREATE TABLE IF NOT EXISTS client_bots (
        bot_id INTEGER PRIMARY KEY,
        owner_id INTEGER NOT NULL,
        username TEXT,
        token_enc TEXT NOT NULL,
        title TEXT,
        description TEXT,
        created_at TEXT NOT NULL
    )""")

    db.execute("CREATE INDEX IF NOT EXISTS idx_client_bots_owner ON client_bots(owner_id)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_client_bots_created ON client_bots(created_at)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)")
    db.commit()

def migrate_plaintext_tokens():
    rows = db.execute("SELECT bot_id, token_enc FROM client_bots").fetchall()
    migrated = 0
    for r in rows:
        if not _is_fernet_token(r["token_enc"]):
            try:
                db.execute("UPDATE client_bots SET token_enc=? WHERE bot_id=?", (enc(r["token_enc"]), r["bot_id"]))
                migrated += 1
            except Exception as e:
                log.error(f"Ошибка шифрования бота {r['bot_id']}: {e}")
    if migrated:
        db.commit()
        log.info(f"🔐 Перешифровано токенов: {migrated}")

def get_client_bot(bot_id):
    return db.execute("SELECT * FROM client_bots WHERE bot_id=?", (bot_id,)).fetchone()

def get_owned_bot(bot_id, owner_id):
    return db.execute("SELECT * FROM client_bots WHERE bot_id=? AND owner_id=?", (bot_id, owner_id)).fetchone()

# --- СОСТОЯНИЯ (FSM) ---
class BotSettings(StatesGroup):
    waiting_for_name = State()
    waiting_for_desc = State()

class UserBotStates(StatesGroup):
    waiting_for_token = State()

class AdminStates(StatesGroup):
    waiting_for_broadcast = State()

# НОВЫЕ СОСТОЯНИЯ ДЛЯ ЗАЯВКИ "ПОД КЛЮЧ"
class TurnkeyOrder(StatesGroup):
    niche = State()          # Ниша
    pay_methods = State()    # Способы оплаты
    features = State()       # Админ-панель/рассылки
    wishes = State()         # Пожелания
    payment_type = State()   # Полная оплата или 50%

# --- ТОВАРЫ ---
PRODUCTS = {
    "vizitka": {"name": "🪪 Бот-визитка", "price": 200, "desc": "Срок: 2-3 часа. Простой бот для связи с клиентами."},
    "shop": {"name": "🛍 Бот-магазин", "price": 500, "desc": "Срок: 5 часов. Бот с каталогом товаров и корзиной."},
    "turnkey": {
        "name": "💎 Бот под ключ (Премиум)", 
        "price": 1200, 
        "desc": (
            "🚀 <b>ПОЛНАЯ НАСТРОЙКА БЕЗ ВАШЕГО УЧАСТИЯ:</b>\n"
            "Вам не нужно разбираться в токенах и коде — мы сами создадим бота, оформим дизайн, загрузим ваши товары и подключим оплату.\n\n"
            "🎁 <b>ПРИВИЛЕГИИ ТАРИФА:</b>\n"
            "• 2 круга бесплатных правок после сдачи\n"
            "• Приоритетная поддержка менеджера\n"
            "• Индивидуальные задачи по вашим бизнес-процессам\n\n"
            "👇 Нажмите кнопку ниже, чтобы ответить на 4 вопроса и получить расчет."
        )
    }
}

# --- ПРОВЕРКА ПОДПИСКИ ---
async def is_subscribed(user_id: int) -> bool:
    if not REQUIRED_CHANNEL:
        return True
    try:
        member = await bot.get_chat_member(chat_id=REQUIRED_CHANNEL, user_id=user_id)
        return member.status in ["member", "administrator", "creator"]
    except TelegramBadRequest:
        return True

def sub_check_kb():
    builder = InlineKeyboardBuilder()
    builder.button(text="📢 Подписаться", url=f"https://t.me/{REQUIRED_CHANNEL.replace('@', '')}")
    builder.button(text="✅ Я подписался", callback_data="check_sub")
    builder.adjust(1)
    return builder.as_markup()

# ==========================================
# --- КЛАВИАТУРЫ ---
# ==========================================
def main_menu_kb():
    builder = InlineKeyboardBuilder()
    builder.button(text="🛍 Каталог услуг", callback_data="catalog")
    builder.button(text="🤖 Мои боты", callback_data="my_bots")
    builder.button(text="🛒 Моя корзина", callback_data="cart")
    builder.button(text="📞 Контакты", callback_data="contacts")
    builder.adjust(1)
    return builder.as_markup()

def catalog_kb():
    builder = InlineKeyboardBuilder()
    for key, item in PRODUCTS.items():
        builder.button(text=f"{item['name']} — {item['price']} ⭐", callback_data=f"buy_{key}")
    builder.button(text="🛒 Перейти в корзину", callback_data="cart")
    builder.button(text="⬅️ Назад", callback_data="main_menu")
    builder.adjust(1)
    return builder.as_markup()

def my_bots_kb(uid):
    kb = InlineKeyboardBuilder()
    for r in db.execute("SELECT * FROM client_bots WHERE owner_id=? ORDER BY created_at", (uid,)).fetchall():
        kb.button(text=f"⚙️ @{r['username']} · не запущен", callback_data=f"bot_{r['bot_id']}")
    kb.button(text="➕ Создать бота автоматически", callback_data="create_bot")
    kb.button(text="🔑 У меня уже есть токен", callback_data="paste_token")
    kb.button(text="⬅️ В главное меню", callback_data="main_menu")
    kb.adjust(1)
    return kb.as_markup()

def bot_settings_kb(bot_id):
    builder = InlineKeyboardBuilder()
    builder.button(text="✏️ Название", callback_data=f"set_name_{bot_id}")
    builder.button(text="📝 Описание", callback_data=f"set_desc_{bot_id}")
    builder.button(text="🚀 Запустить на 14 дн. · 250 ⭐", callback_data=f"pay_hosting_{bot_id}")
    builder.button(text="⬅️ Назад к моим ботам", callback_data="my_bots")
    builder.adjust(2, 1, 1)
    return builder.as_markup()

# ==========================================
# --- ОБРАБОТЧИКИ ---
# ==========================================

@dp.message(CommandStart())
async def start_cmd(message: Message):
    db.execute("""INSERT INTO users (user_id, username, first_name) VALUES (?,?,?)
                  ON CONFLICT(user_id) DO UPDATE SET username=excluded.username, first_name=excluded.first_name""",
               (message.from_user.id, message.from_user.username, message.from_user.first_name))
    db.commit()

    if not await is_subscribed(message.from_user.id):
        await message.answer("👋 Привет! Чтобы пользоваться ботом, подпишись на наш канал.", reply_markup=sub_check_kb())
        return

    await message.answer(f"👋 Привет, <b>{message.from_user.first_name}</b>!\n\nДобро пожаловать в магазин.", reply_markup=main_menu_kb(), parse_mode="HTML")

@dp.callback_query(F.data == "check_sub")
async def check_sub(call: CallbackQuery):
    if await is_subscribed(call.from_user.id):
        await call.message.edit_text("✅ Спасибо за подписку!\n\nВыбери услугу:", reply_markup=main_menu_kb())
    else:
        await call.answer("❌ Вы всё ещё не подписаны!", show_alert=True)

@dp.callback_query(F.data == "main_menu")
async def main_menu(call: CallbackQuery):
    await call.message.edit_text("🏠 Главное меню. Выбери услугу:", reply_markup=main_menu_kb())
    await call.answer()

# --- КАТАЛОГ ---
@dp.callback_query(F.data == "catalog")
async def catalog(call: CallbackQuery, state: FSMContext):
    await state.clear()  # <--- Отменяем незавершенные опросы при выходе в каталог
    if not await is_subscribed(call.from_user.id):
        await call.message.edit_text("❌ Сначала подпишитесь!", reply_markup=sub_check_kb())
        return
    await call.message.edit_text("🛍 <b>Каталог услуг</b>\n\nВыберите товар:", reply_markup=catalog_kb(), parse_mode="HTML")
    await call.answer()

# --- КАРТОЧКА ТОВАРА ---
@dp.callback_query(F.data.startswith("buy_"))
async def show_product_info(call: CallbackQuery):
    product_key = call.data.split("_")[1]
    product = PRODUCTS.get(product_key)
    if not product:
        await call.answer("❌ Товар не найден.", show_alert=True)
        return

    text = f"<b>{product['name']}</b>\n\n<i>{product['desc']}</i>\n\n💰 <b>Стоимость:</b> {product['price']} ⭐"
    builder = InlineKeyboardBuilder()
    
    if product_key == "turnkey":
        # Для премиум-тарифа своя кнопка
        builder.button(text="📝 Заполнить заявку", callback_data="start_turnkey_order")
    else:
        # Для обычных товаров корзина
        builder.button(text="🛒 Добавить в корзину", callback_data=f"addcart_{product_key}")
        
    builder.button(text="⬅️ Назад в каталог", callback_data="catalog")
    builder.adjust(1)

    await call.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
    await call.answer()

# ==========================================
# --- СЦЕНАРИЙ "ПОД КЛЮЧ" (ОПРОС) ---
# ==========================================

@dp.callback_query(F.data == "start_turnkey_order")
async def start_turnkey(call: CallbackQuery, state: FSMContext):
    await state.set_state(TurnkeyOrder.niche)
    builder = InlineKeyboardBuilder()
    builder.button(text="❌ Отменить", callback_data="catalog")
    await call.message.edit_text(
        "Шаг 1 из 4 📝\n\n<b>Для какой ниши нужен бот?</b>\n(Например: магазин одежды, доставка еды, запись на маникюр и т.д.)",
        reply_markup=builder.as_markup(), parse_mode="HTML"
    )
    await call.answer()

@dp.message(TurnkeyOrder.niche)
async def turnkey_niche(message: Message, state: FSMContext):
    await state.update_data(tk_niche=message.text)
    await state.set_state(TurnkeyOrder.pay_methods)
    
    builder = InlineKeyboardBuilder()
    builder.button(text="Звезды ⭐", callback_data="tkpay_stars")
    builder.button(text="Карты РФ 💳", callback_data="tkpay_cards")
    builder.button(text="Крипта 🪙", callback_data="tkpay_crypto")
    builder.button(text="Всё сразу 🔥", callback_data="tkpay_all")
    builder.adjust(2)
    
    await message.answer(
        "Шаг 2 из 4 💳\n\n<b>Какие способы оплаты нужны в боте?</b>\n(Выберите вариант)",
        reply_markup=builder.as_markup(), parse_mode="HTML"
    )

@dp.callback_query(TurnkeyOrder.pay_methods, F.data.startswith("tkpay_"))
async def turnkey_pay_methods(call: CallbackQuery, state: FSMContext):
    mapping = {"tkpay_stars": "Звезды", "tkpay_cards": "Карты РФ", "tkpay_crypto": "Крипта", "tkpay_all": "Всё сразу"}
    await state.update_data(tk_pay=mapping.get(call.data, "Не указано"))
    await state.set_state(TurnkeyOrder.features)

    builder = InlineKeyboardBuilder()
    builder.button(text="Да, нужны 📊", callback_data="tkfeat_yes")
    builder.button(text="Нет, не нужны ❌", callback_data="tkfeat_no")
    builder.adjust(2)

    await call.message.edit_text(
        "Шаг 3 из 4 ⚙️\n\n<b>Нужна ли админ-панель и функция рассылки?</b>",
        reply_markup=builder.as_markup(), parse_mode="HTML"
    )
    await call.answer()

@dp.callback_query(TurnkeyOrder.features, F.data.startswith("tkfeat_"))
async def turnkey_features(call: CallbackQuery, state: FSMContext):
    await state.update_data(tk_feat="Да" if call.data == "tkfeat_yes" else "Нет")
    await state.set_state(TurnkeyOrder.wishes)
    
    builder = InlineKeyboardBuilder()
    builder.button(text="Пропустить (нет пожеланий)", callback_data="skip_wishes")
    builder.adjust(1)

    await call.message.edit_text(
        "Шаг 4 из 4 💬\n\n<b>Оставьте пожелания в свободной форме:</b>\n(Опишите, что важно учесть. Или нажмите кнопку ниже)",
        reply_markup=builder.as_markup(), parse_mode="HTML"
    )
    await call.answer()

@dp.callback_query(F.data == "skip_wishes")
async def turnkey_skip_wishes(call: CallbackQuery, state: FSMContext):
    await state.update_data(tk_wish="Нет")
    await turnkey_finish_survey(call.message, state)

@dp.message(TurnkeyOrder.wishes)
async def turnkey_wishes(message: Message, state: FSMContext):
    await state.update_data(tk_wish=message.text)
    await turnkey_finish_survey(message, state)

# --- ФИНАЛ ОПРОСА И ВЫБОР ОПЛАТЫ ---
async def turnkey_finish_survey(message: Message, state: FSMContext):
    await state.set_state(TurnkeyOrder.payment_type)
    builder = InlineKeyboardBuilder()
    builder.button(text="💳 Полная оплата — 1200 ⭐ (+ бонус логотип)", callback_data="pay_tk_full")
    builder.button(text="💵 Предоплата 50% — 600 ⭐", callback_data="pay_tk_half")
    builder.adjust(1)
    
    await message.answer(
        "✅ <b>Спасибо! Заявка собрана.</b>\n\n"
        "Теперь выберите удобный формат оплаты. После оплаты менеджер сразу приступит к работе.",
        reply_markup=builder.as_markup(), parse_mode="HTML"
    )

# --- ОТПРАВКА СЧЕТОВ НА ОПЛАТУ ---
@dp.callback_query(F.data.in_({"pay_tk_full", "pay_tk_half"}))
async def turnkey_invoice(call: CallbackQuery):
    is_full = call.data == "pay_tk_full"
    amount = 1200 if is_full else 600
    title = "Полная оплата (Бот под ключ)" if is_full else "Предоплата 50% (Бот под ключ)"
    
    await call.message.answer_invoice(
        title=title,
        description=f"Создание Telegram-бота под ключ. {('Оплата 100%' if is_full else 'Предоплата 50%')}",
        payload=f"turnkey_{'full' if is_full else 'half'}",
        currency="XTR",
        prices=[types.LabeledPrice(label="Итого", amount=amount)],
        provider_token=""
    )
    await call.answer("Счет выставлен! Перейдите к оплате.")

# ==========================================
# --- ДОБАВЛЕНИЕ В КОРЗИНУ (СТАРЫЕ ТОВАРЫ) ---
# ==========================================
@dp.callback_query(F.data.startswith("addcart_"))
async def add_to_cart_action(call: CallbackQuery, state: FSMContext):
    product_key = call.data.split("_")[1]
    product = PRODUCTS[product_key]
    
    data = await state.get_data()
    cart = data.get("cart", {})
    cart[product_key] = cart.get(product_key, 0) + 1
    await state.update_data(cart=cart)
    
    await call.answer(f"✅ {product['name']} добавлен в корзину!", show_alert=False)
    await call.message.edit_text("🛍 <b>Каталог услуг</b>\n\nВыберите товар:", reply_markup=catalog_kb(), parse_mode="HTML")

# ==========================================
# --- КОРЗИНА ---
# ==========================================
@dp.callback_query(F.data == "cart")
async def show_cart(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    cart = data.get("cart", {})
    
    if not cart:
        await call.message.edit_text("🛒 <b>Ваша корзина пуста.</b>", reply_markup=main_menu_kb(), parse_mode="HTML")
        await call.answer()
        return

    text = "🛒 <b>Ваша корзина:</b>\n\n"
    total_price = 0
    
    for key, qty in cart.items():
        item = PRODUCTS[key]
        text += f"▪️ <b>{item['name']}</b> (x{qty})\n"
        text += f"Цена: {item['price']} ⭐\n\n"
        total_price += item['price'] * qty
        
    text += f"💰 <b>Итого к оплате:</b> {total_price} ⭐"

    builder = InlineKeyboardBuilder()
    builder.button(text="💳 Оплатить", callback_data="checkout")
    builder.button(text="🗑 Очистить корзину", callback_data="clear_cart")
    builder.button(text="⬅️ В меню", callback_data="main_menu")
    builder.adjust(1)
    
    await call.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
    await call.answer()

@dp.callback_query(F.data == "clear_cart")
async def clear_cart(call: CallbackQuery, state: FSMContext):
    await state.update_data(cart={})
    await call.message.edit_text("🗑 Корзина очищена.", reply_markup=main_menu_kb())
    await call.answer()

@dp.callback_query(F.data == "checkout")
async def checkout(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    cart = data.get("cart", {})
    
    if not cart:
        await call.answer("Корзина пуста!", show_alert=True)
        return
        
    total_price = sum(PRODUCTS[k]['price'] * q for k, q in cart.items())
    items_names = ", ".join([PRODUCTS[k]['name'] for k in cart.keys()])
    
    await call.message.answer_invoice(
        title="Оплата заказа",
        description=f"Вы заказываете: {items_names}",
        payload="cart_payment",
        currency="XTR",
        prices=[types.LabeledPrice(label="Итого", amount=total_price)],
        provider_token=""
    )
    await call.answer()

# --- МОИ БОТЫ ---
@dp.callback_query(F.data == "my_bots")
async def my_bots(call: CallbackQuery):
    if not await is_subscribed(call.from_user.id):
        await call.message.edit_text("❌ Сначала подпишитесь на канал!", reply_markup=sub_check_kb())
        return

    text = "🤖 <b>Мои боты</b>\n\nЗдесь можно добавить и настроить бота.\n\n🔐 <i>Токен хранится в зашифрованном виде.</i>"
    await call.message.edit_text(text, reply_markup=my_bots_kb(call.from_user.id), parse_mode="HTML")
    await call.answer()

@dp.callback_query(F.data.startswith("bot_"))
async def handle_bot_settings(callback: CallbackQuery):
    try:
        bot_id = int(callback.data.split("_", 1)[1])
    except (IndexError, ValueError):
        await callback.answer("❌ Некорректный ID бота.", show_alert=True)
        return

    client_bot = get_owned_bot(bot_id, callback.from_user.id)
    if not client_bot:
        await callback.answer("❌ Бот не найден.", show_alert=True)
        return
        
    text = f"🛠 <b>Настройки бота</b>\n\nИмя: <b>{client_bot['title']}</b>\nЮзернейм: @{client_bot['username']}\n\nВыберите действие:"
    await callback.message.edit_text(text, reply_markup=bot_settings_kb(bot_id), parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data.startswith("pay_hosting_"))
async def handle_pay_hosting(callback: CallbackQuery):
    try:
        bot_id = int(callback.data.split("_")[2])
    except (IndexError, ValueError):
        await callback.answer("❌ Некорректный ID.", show_alert=True)
        return

    await callback.answer(
        "🚧 Запуск бота на серверах в разработке.\n"
        f"💰 Стоимость: {HOSTING_PRICE} ⭐ / {HOSTING_DAYS} дней.", show_alert=True
    )

@dp.callback_query(F.data.startswith("set_name_"))
async def handle_set_name(callback: CallbackQuery, state: FSMContext):
    try: bot_id = int(callback.data.split("_")[2])
    except: return await callback.answer("Ошибка ID", show_alert=True)
    if not get_owned_bot(bot_id, callback.from_user.id): return await callback.answer("Не ваш бот", show_alert=True)

    await state.update_data(bot_id=bot_id, owner_id=callback.from_user.id)
    builder = InlineKeyboardBuilder().button(text="⬅️ Отмена", callback_data=f"bot_{bot_id}")
    await callback.message.edit_text("✏️ <b>Введите новое название:</b>", reply_markup=builder.as_markup(), parse_mode="HTML")
    await state.set_state(BotSettings.waiting_for_name)
    await callback.answer()

@dp.message(BotSettings.waiting_for_name)
async def process_new_name(message: Message, state: FSMContext):
    data = await state.get_data()
    bot_id, owner_id = data.get("bot_id"), data.get("owner_id")
    new_name = (message.text or "").strip()
    if not new_name or len(new_name) > 64: return await message.answer("❌ От 1 до 64 символов.")
    
    client_bot = get_owned_bot(bot_id, owner_id)
    if not client_bot: return await state.clear()
        
    child_bot = None
    try:
        child_bot = Bot(token=dec(client_bot['token_enc']))
        await child_bot.set_my_name(name=new_name)
        db.execute("UPDATE client_bots SET title=? WHERE bot_id=? AND owner_id=?", (new_name, bot_id, owner_id))
        db.commit()
        await message.answer(f"✅ Название изменено на: <b>{new_name}</b>", parse_mode="HTML")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")
    finally:
        if child_bot: await child_bot.session.close()
        await state.clear()

@dp.callback_query(F.data.startswith("set_desc_"))
async def handle_set_desc(callback: CallbackQuery, state: FSMContext):
    try: bot_id = int(callback.data.split("_")[2])
    except: return await callback.answer("Ошибка ID", show_alert=True)
    if not get_owned_bot(bot_id, callback.from_user.id): return await callback.answer("Не ваш бот", show_alert=True)

    await state.update_data(bot_id=bot_id, owner_id=callback.from_user.id)
    builder = InlineKeyboardBuilder().button(text="⬅️ Отмена", callback_data=f"bot_{bot_id}")
    await callback.message.edit_text("📝 <b>Введите новое описание:</b>", reply_markup=builder.as_markup(), parse_mode="HTML")
    await state.set_state(BotSettings.waiting_for_desc)
    await callback.answer()

@dp.message(BotSettings.waiting_for_desc)
async def process_new_desc(message: Message, state: FSMContext):
    data = await state.get_data()
    bot_id, owner_id = data.get("bot_id"), data.get("owner_id")
    new_desc = (message.text or "").strip()
    if not new_desc or len(new_desc) > 512: return await message.answer("❌ От 1 до 512 символов.")
    
    client_bot = get_owned_bot(bot_id, owner_id)
    if not client_bot: return await state.clear()
        
    child_bot = None
    try:
        child_bot = Bot(token=dec(client_bot['token_enc']))
        await child_bot.set_my_description(description=new_desc)
        db.execute("UPDATE client_bots SET description=? WHERE bot_id=? AND owner_id=?", (new_desc, bot_id, owner_id))
        db.commit()
        await message.answer(f"✅ Описание обновлено!", parse_mode="HTML")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")
    finally:
        if child_bot: await child_bot.session.close()
        await state.clear()

@dp.callback_query(F.data == "create_bot")
async def create_bot(call: CallbackQuery):
    count = db.execute("SELECT COUNT(*) c FROM client_bots WHERE owner_id=?", (call.from_user.id,)).fetchone()["c"]
    if count >= MAX_BOTS_PER_USER: return await call.answer(f"Максимум {MAX_BOTS_PER_USER} бота", show_alert=True)
        
    builder = InlineKeyboardBuilder()
    builder.button(text="🤖 BotFather", url="https://t.me/BotFather")
    builder.button(text="⬅️ Назад", callback_data="my_bots")
    await call.message.edit_text("1. Перейдите в BotFather\n2. Отправьте /newbot\n3. Скопируйте токен\n4. Вернитесь и нажмите «У меня есть токен»", reply_markup=builder.as_markup(), parse_mode="HTML")
    await call.answer()

@dp.callback_query(F.data == "paste_token")
async def enter_token(callback: CallbackQuery, state: FSMContext):
    builder = InlineKeyboardBuilder().button(text="⬅️ Отмена", callback_data="my_bots")
    await callback.message.edit_text("🔑 <b>Отправьте токен:</b>", reply_markup=builder.as_markup(), parse_mode="HTML")
    await state.set_state(UserBotStates.waiting_for_token)
    await callback.answer()

@dp.message(UserBotStates.waiting_for_token)
async def process_token(message: Message, state: FSMContext):
    token = (message.text or "").strip()
    if ":" not in token or len(token) < 20: return await message.answer("❌ Не похоже на токен.")
        
    try:
        temp_bot = Bot(token=token)
        bot_info = await temp_bot.get_me()
        await temp_bot.session.close()
        
        existing = get_client_bot(bot_info.id)
        if existing:
            if existing["owner_id"] != message.from_user.id:
                await message.answer("⚠️ Бот уже добавлен другим.")
            else:
                db.execute("UPDATE client_bots SET token_enc=? WHERE bot_id=?", (enc(token), bot_info.id))
                db.commit()
                await message.answer(f"✅ Токен для @{bot_info.username} обновлён!")
        else:
            db.execute("INSERT INTO client_bots (bot_id, owner_id, username, token_enc, title, description, created_at) VALUES (?,?,?,?,?,?,?)",
                       (bot_info.id, message.from_user.id, bot_info.username, enc(token), bot_info.first_name, "Здравствуйте!", iso(datetime.now())))
            db.commit()
            await message.answer(f"✅ Бот @{bot_info.username} добавлен!")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")
    await state.clear()

# ==========================================
# --- ОБРАБОТКА ПЛАТЕЖЕЙ (С АВТО-КАРТОЧКОЙ) ---
# ==========================================
@dp.pre_checkout_query()
async def process_pre_checkout_query(pre_checkout_query: PreCheckoutQuery):
    await pre_checkout_query.answer(ok=True)

@dp.message(F.successful_payment)
async def process_successful_payment(message: Message, state: FSMContext):
    payload = message.successful_payment.invoice_payload
    amount = message.successful_payment.total_amount
    user = message.from_user
    
    if payload == "cart_payment":
        await message.answer(f"🎉 <b>Оплата прошла!</b>\nСумма: {amount} ⭐", parse_mode="HTML")
        await bot.send_message(ADMIN_ID, f"💰 <b>Заказ из корзины!</b>\nСумма: {amount} ⭐\nКлиент: @{user.username} (ID: {user.id})")
        await state.update_data(cart={})
        
    elif payload.startswith("turnkey_"):
        # ДОСТАЕМ ОТВЕТЫ ИЗ ОПРОСА
        data = await state.get_data()
        niche = data.get("tk_niche", "Не указано")
        pay = data.get("tk_pay", "Не указано")
        feat = data.get("tk_feat", "Не указано")
        wish = data.get("tk_wish", "Нет")
        is_full = (payload == "turnkey_full")
        
        status_text = "✅ Полная оплата (100%)" if is_full else "⚠️ Предоплата 50% (остаток после сдачи)"
        
        # Сообщение клиенту
        await message.answer(
            f"🎉 <b>Оплата получена!</b>\n\n"
            f"Мы уже начали работу над вашим ботом. Менеджер свяжется с вами в ближайшее время.",
            parse_mode="HTML"
        )
        
        # КРАСИВАЯ КАРТОЧКА ДЛЯ АДМИНА
        admin_text = (
            f"🔥 <b>НОВАЯ ЗАЯВКА НА «ПОД КЛЮЧ»</b> 🔥\n\n"
            f"👤 <b>Клиент:</b> @{user.username if user.username else 'нет_юзернейма'} (ID: <code>{user.id}</code>)\n"
            f"💰 <b>Оплата:</b> {amount} ⭐ ({status_text})\n\n"
            f"📋 <b>ДЕТАЛИ ЗАКАЗА:</b>\n"
            f"▪️ <b>Ниша:</b> {niche}\n"
            f"▪️ <b>Способы оплаты:</b> {pay}\n"
            f"▪️ <b>Админ-панель/Рассылки:</b> {feat}\n"
            f"▪️ <b>Пожелания:</b> {wish}\n\n"
            f"👇 <i>Свяжитесь с клиентом для старта работ!</i>"
        )
        await bot.send_message(ADMIN_ID, admin_text, parse_mode="HTML")
        await state.clear() # Очищаем опрос

# --- КОНТАКТЫ ---
@dp.callback_query(F.data == "contacts")
async def contacts(call: CallbackQuery):
    await call.message.edit_text(f"📞 <b>Связаться с нами</b>\n\n{CONTACT_TEXT}", reply_markup=main_menu_kb(), parse_mode="HTML")
    await call.answer()

# ==========================================
# --- АДМИН-ПАНЕЛЬ ---
# ==========================================
@dp.message(Command("admin"))
async def admin_panel(message: Message):
    if message.from_user.id != ADMIN_ID: return
    builder = InlineKeyboardBuilder()
    builder.button(text="📊 Статистика", callback_data="admin_stats")
    builder.button(text="📢 Сделать рассылку", callback_data="admin_broadcast")
    builder.adjust(1)
    await message.answer("👑 <b>Админ-панель</b>", reply_markup=builder.as_markup(), parse_mode="HTML")

@dp.callback_query(F.data == "admin_stats")
async def admin_stats(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID: return
    users_count = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    bots_count = db.execute("SELECT COUNT(*) FROM client_bots").fetchone()[0]
    owners_count = db.execute("SELECT COUNT(DISTINCT owner_id) FROM client_bots").fetchone()[0]
    builder = InlineKeyboardBuilder().button(text="⬅️ Назад", callback_data="admin_back")
    await call.message.edit_text(f"📊 <b>Статистика</b>\n\n👥 Пользователей: {users_count}\n🤖 Ботов: {bots_count}\n👤 Владельцев: {owners_count}", reply_markup=builder.as_markup(), parse_mode="HTML")
    await call.answer()

@dp.callback_query(F.data == "admin_back")
async def admin_back(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID: return
    builder = InlineKeyboardBuilder()
    builder.button(text="📊 Статистика", callback_data="admin_stats")
    builder.button(text="📢 Сделать рассылку", callback_data="admin_broadcast")
    builder.adjust(1)
    await call.message.edit_text("👑 <b>Админ-панель</b>", reply_markup=builder.as_markup(), parse_mode="HTML")
    await call.answer()

@dp.callback_query(F.data == "admin_broadcast")
async def admin_broadcast_start(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID: return
    await call.message.answer("📢 Отправьте текст для рассылки (или /cancel):")
    await state.set_state(AdminStates.waiting_for_broadcast)
    await call.answer()

@dp.message(AdminStates.waiting_for_broadcast)
async def admin_broadcast_send(message: Message, state: FSMContext):
    if message.text and message.text == "/cancel":
        await state.clear()
        await message.answer("Отменено.")
        return

    users = db.execute("SELECT user_id FROM users").fetchall()
    success, failed = 0, 0
    status_msg = await message.answer(f"⏳ Рассылка для {len(users)} чел...")
    
    for user in users:
        try:
            await message.copy_to(chat_id=user['user_id'])
            success += 1
            await asyncio.sleep(0.05)
        except Exception:
            failed += 1
            
    await status_msg.edit_text(f"✅ <b>Готово!</b>\nДоставлено: {success}\nОшибок: {failed}")
    await state.clear()

# --- ЗАПУСК ---
async def main():
    init_db()
    migrate_plaintext_tokens()  
    log.info("Бот запущен с системой заявок!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
