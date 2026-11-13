import asyncio
import logging
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, LabeledPrice, PreCheckoutQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

# ================= НАСТРОЙКИ =================
BOT_TOKEN = '9071984522:AAE_GLgzZD774mwh0ORC1Y7nLAWHL4Nyb20'
ADMIN_ID = 5029096746
CHANNEL_ID = "@Make_bots155"
# =============================================

SERVICES = {
    "1": {"name": "Бот-визитка (Базовый)", "price": 1500},
    "2": {"name": "Бот-магазин (Стандарт)", "price": 3500},
    "3": {"name": "Бот под ключ (Премиум)", "price": 7000}
}

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

async def is_subscribed(user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        if member.status in ['left', 'kicked']:
            return False
        return True
    except Exception:
        return False

def sub_menu():
    kb = InlineKeyboardBuilder()
    kb.button(text="📢 Подписаться на канал", url=f"https://t.me/{CHANNEL_ID.replace('@', '')}")
    kb.button(text="✅ Я подписался", callback_data="check_sub")
    kb.adjust(1)
    return kb.as_markup()

def main_menu():
    kb = InlineKeyboardBuilder()
    kb.button(text="🛍 Каталог услуг", callback_data="catalog")
    kb.button(text="🛒 Моя корзина", callback_data="cart")
    kb.button(text="📞 Связаться с нами", callback_data="contact")
    kb.adjust(1)
    return kb.as_markup()

def catalog_menu():
    kb = InlineKeyboardBuilder()
    for key, item in SERVICES.items():
        kb.button(text=f"{item['name']} - {item['price']} ⭐", callback_data=f"buy_{key}")
    kb.button(text="⬅️ Назад", callback_data="back_to_main")
    kb.adjust(1)
    return kb.as_markup()

user_carts = {}
all_users = set()
all_orders = []

@dp.message(Command("start"))
async def cmd_start(message: Message):
    all_users.add(message.from_user.id)
    if not await is_subscribed(message.from_user.id):
        await message.answer("Привет! 👋 Чтобы пользоваться ботом, подпишись на наш канал:", reply_markup=sub_menu())
        return
    await message.answer(f"Привет, {message.from_user.first_name}! 👋\nВыбери услугу.", reply_markup=main_menu())

@dp.callback_query(F.data == "check_sub")
async def check_sub(call: CallbackQuery):
    if await is_subscribed(call.from_user.id):
        await call.message.edit_text("Отлично! Подписка подтверждена.", reply_markup=main_menu())
    else:
        await call.answer("Вы ещё не подписались!", show_alert=True)

@dp.callback_query(F.data == "catalog")
async def show_catalog(call: CallbackQuery):
    await call.message.edit_text("Выберите услугу:", reply_markup=catalog_menu())
    await call.answer()

@dp.callback_query(F.data.startswith("buy_"))
async def process_buy(call: CallbackQuery):
    service_id = call.data.split("_")[1]
    service = SERVICES.get(service_id)
    if not service:
        await call.answer("Услуга не найдена", show_alert=True)
        return
    user_id = call.from_user.id
    if user_id not in user_carts:
        user_carts[user_id] = []
    user_carts[user_id].append(service_id)
    await call.answer(f"✅ {service['name']} добавлена!", show_alert=True)

@dp.callback_query(F.data == "cart")
async def show_cart(call: CallbackQuery):
    user_id = call.from_user.id
    cart = user_carts.get(user_id, [])
    if not cart:
        await call.message.edit_text("Ваша корзина пуста 😔", reply_markup=main_menu())
        return
    text = "🛒 <b>Ваша корзина:</b>\n\n"
    total_price = 0
    kb = InlineKeyboardBuilder()
    for i, item_id in enumerate(cart):
        item = SERVICES[item_id]
        text += f"{i+1}. {item['name']} - {item['price']} ⭐\n"
        total_price += item['price']
        kb.button(text=f"❌ Удалить {i+1}. {item['name']}", callback_data=f"del_{i}")
    text += f"\n<b>Итого к оплате: {total_price} ⭐</b>\n\n"
    text += "<i>⚠️ Внимание: чтобы очистить корзину полностью, перезапустите бота (нажмите /start).</i>"
    kb.button(text=f"💳 Оплатить {total_price} ⭐", callback_data="pay_stars")
    kb.button(text="⬅️ В меню", callback_data="back_to_main")
    kb.adjust(1)
    await call.message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="HTML")
    await call.answer()

@dp.callback_query(F.data.startswith("del_"))
async def delete_item(call: CallbackQuery):
    user_id = call.from_user.id
    index_to_del = int(call.data.split("_")[1])
    if user_id in user_carts and len(user_carts[user_id]) > index_to_del:
        del user_carts[user_id][index_to_del]
        await call.answer("Товар удален!")
        await show_cart(call)
    else:
        await call.answer("Ошибка", show_alert=True)

@dp.callback_query(F.data == "pay_stars")
async def send_invoice(call: CallbackQuery):
    user_id = call.from_user.id
    cart = user_carts.get(user_id, [])
    if not cart:
        await call.answer("Корзина пуста!", show_alert=True)
        return
    total_price = sum(SERVICES[item]['price'] for item in cart)
    await bot.send_invoice(
        chat_id=call.message.chat.id, title="Оплата заказа", description="Оплата услуг",
        payload="custom_payload", provider_token="", currency="XTR",
        prices=[LabeledPrice(label="Заказ", amount=total_price)], start_parameter="create_invoice"
    )
    await call.answer()

@dp.pre_checkout_query()
async def process_pre_checkout(pre_checkout_q: PreCheckoutQuery):
    await bot.answer_pre_checkout_query(pre_checkout_q.id, ok=True)

@dp.message(F.successful_payment)
async def process_successful_payment(message: Message):
    user_id = message.from_user.id
    payment_info = message.successful_payment
    if user_id in user_carts:
        all_orders.append({
            "user_id": user_id,
            "username": message.from_user.username,
            "amount": payment_info.total_amount,
            "items": [SERVICES[i]["name"] for i in user_carts[user_id]]
        })
        del user_carts[user_id]
    await message.answer("✅ Оплата прошла успешно! Мы свяжемся с вами.", reply_markup=main_menu())

@dp.callback_query(F.data == "contact")
async def contact_info(call: CallbackQuery):
    await call.message.edit_text("📞 Менеджер: @Plot1335\n✉️ Почта: vinmont4@gmail.com", reply_markup=main_menu())
    await call.answer()

@dp.callback_query(F.data == "back_to_main")
async def back_to_main(call: CallbackQuery):
    await call.message.edit_text("Главное меню:", reply_markup=main_menu())
    await call.answer()

@dp.message(Command("admin"))
async def admin_panel(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("У вас нет доступа.")
        return
    text = "👑 <b>Админ-панель</b>\n\n"
    text += f"👥 Пользователей: <b>{len(all_users)}</b>\n"
    text += f"🛒 Заказов: <b>{len(all_orders)}</b>\n"
    total_earned = sum(order['amount'] for order in all_orders)
    text += f"💰 Заработано: <b>{total_earned} ⭐</b>\n\n"
    if all_orders:
        text += "<b>Последние заказы:</b>\n"
        for order in all_orders[-5:]:
            user = f"@{order['username']}" if order['username'] else f"ID {order['user_id']}"
            items = ", ".join(order['items'])
            text += f"• {user}: {items} ({order['amount']} ⭐)\n"
    else:
        text += "Заказов пока нет."
    await message.answer(text, parse_mode="HTML")

async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    print("Бот запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
