import os
import json
import logging
import requests
from aiogram import Bot, Dispatcher, types, executor
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InputMediaPhoto, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.contrib.middlewares.logging import LoggingMiddleware

# Ось тут зчитаємо каталог із файлу catalog.json
with open("catalog.json", "r", encoding="utf-8") as f:
    CATALOG = json.load(f)

API_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "")  # не обов'язковий

if not API_TOKEN:
    raise Exception("BOT_TOKEN не задано в Secrets!")

logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot)
dp.middleware.setup(LoggingMiddleware())

user_data = {}  # Зберігаємо дані користувача: кольори, кількість, контакт, доставка...

# Стадії замовлення
STEPS = [
    "catalog",           # Вибір кольорів
    "quantity",          # Введення кількості для поточного кольору
    "name",              # ПІБ
    "phone",             # Телефон
    "delivery",          # Спосіб доставки
    "city",              # Населений пункт, область
    "office",            # Номер відділення / поштомату / індекс
    "comment",           # Коментар (опціонально)
    "confirmation"       # Підтвердження і відправка
]

DELIVERY_OPTIONS = ["Нова Пошта", "Укрпошта", "Meest", "Самовивіз"]

# Закінчення для бухт

def get_bukhta_ending(n: int) -> str:
    n = abs(n) % 100
    if 11 <= n <= 14:
        return "бухт"
    n = n % 10
    if n == 1:
        return "бухта"
    elif 2 <= n <= 4:
        return "бухти"
    else:
        return "бухт"

# Команди

@dp.message_handler(commands=["start"])
async def start(message: types.Message):
    user_id = message.from_user.id
    user_data[user_id] = {
        "step": "catalog",
        "selected_colors": [],
        "current_color_index": 0,
        "order": {}
    }
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton("Подивитись каталог"))
    kb.add(KeyboardButton("Замовити"))
    kb.add(KeyboardButton("Контакти"))
    await message.answer("Вітаю! Обери дію:", reply_markup=kb)


CATALOG_DESCRIPTION = "Це наш каталог ротангу"

@dp.message_handler(lambda message: message.text == "Подивитись каталог")
async def show_catalog_album(message: types.Message):
    photos = [InputMediaPhoto(media=item["photo_url"]) for item in CATALOG]

    chunk_size = 10
    for i in range(0, len(photos), chunk_size):
        chunk = photos[i:i+chunk_size]
        await bot.send_media_group(chat_id=message.from_user.id, media=chunk)

    await message.answer(CATALOG_DESCRIPTION)

@dp.message_handler(lambda message: message.text == "Контакти")
async def show_contacts(message: types.Message):
    await message.answer("Наші контакти:\nТелефон: +380123456789\nEmail: example@example.com\nАдреса: м. Харків, вул. Ремонтна, 7")

@dp.message_handler(lambda message: message.text == "Замовити")
async def start_order(message: types.Message):
    await show_catalog(message)

async def show_catalog(message: types.Message):
    user_id = message.from_user.id
    kb = InlineKeyboardMarkup(row_width=2)
    for idx, item in enumerate(CATALOG):
        kb.insert(InlineKeyboardButton(text=item["name"], callback_data=f"color_{idx}"))
    kb.add(InlineKeyboardButton(text="Завершити вибір", callback_data="finish_colors"))

    await message.answer("Обери кольори ротангу (натисни кнопки):", reply_markup=kb)

@dp.callback_query_handler(lambda c: c.data and c.data.startswith("color_"))
async def color_selected(callback_query: types.CallbackQuery):
    user_id = callback_query.from_user.id
    idx = int(callback_query.data.split("_")[1])
    color = CATALOG[idx]

    if user_id not in user_data:
        await callback_query.answer("Почни заново командою /start")
        return

    # Якщо колір вже обраний — не додаємо двічі
    if any(c["name"] == color["name"] for c in user_data[user_id]["selected_colors"]):
        await bot.answer_callback_query(callback_query.id, text=f"{color['name']} вже обрано")
        return

    user_data[user_id]["selected_colors"].append({
        "name": color["name"],
        "photo_url": color["photo_url"],
        "quantity": None
    })
    await bot.answer_callback_query(callback_query.id, text=f"Обрано {color['name']}")

    # Запропонувати ввести кількість для цього кольору або продовжити вибір кольорів
    idx_in_list = len(user_data[user_id]["selected_colors"]) - 1
    user_data[user_id]["current_color_index"] = idx_in_list
    user_data[user_id]["step"] = "quantity"

    await bot.send_message(user_id, f'Введіть кількість бухт для кольору "{color["name"]}":')

@dp.callback_query_handler(lambda c: c.data and c.data.startswith("enter_quantity_"))
async def enter_quantity_handler(callback_query: types.CallbackQuery):
    user_id = callback_query.from_user.id
    idx = int(callback_query.data.split("_")[-1])

    if user_id not in user_data:
        await callback_query.answer("Почни заново командою /start")
        return

    user_data[user_id]["current_color_index"] = idx
    user_data[user_id]["step"] = "quantity"
    await bot.answer_callback_query(callback_query.id)
    await bot.send_message(user_id, f"Введи кількість (у бухтах) для {user_data[user_id]['selected_colors'][idx]['name']}:")

@dp.callback_query_handler(lambda c: c.data == "finish_colors")
async def finish_colors(callback_query: types.CallbackQuery):
    user_id = callback_query.from_user.id

    if user_id not in user_data or len(user_data[user_id]["selected_colors"]) == 0:
        await bot.answer_callback_query(callback_query.id, "Спочатку вибери хоча б один колір!")
        return

    for c in user_data[user_id]["selected_colors"]:
        if c["quantity"] is None:
            await bot.answer_callback_query(callback_query.id, f"Введи кількість для {c['name']}!")
            return

    user_data[user_id]["step"] = "name"
    await bot.answer_callback_query(callback_query.id)
    await bot.send_message(user_id, "Введи, будь ласка, ПІБ:")


@dp.message_handler()
async def handle_steps(message: types.Message):
    user_id = message.from_user.id

    if user_id not in user_data:
        await message.answer("Почни замовлення командою /start")
        return

    step = user_data[user_id].get("step")

    if not step:
        await message.answer("Замовлення завершено або ще не почате. Напиши /start, щоб почати заново.")
        return

    if step == "quantity":
        try:
            qty = int(message.text)
            idx = user_data[user_id]["current_color_index"]
            user_data[user_id]["selected_colors"][idx]["quantity"] = qty
            user_data[user_id]["step"] = "catalog"  # повертаємось до вибору кольорів

            ending = get_bukhta_ending(qty)
            await message.answer(
                f"Кількість для {user_data[user_id]['selected_colors'][idx]['name']} встановлено: {qty} {ending}.\n"
                "Якщо хочеш додати/змінити кількість інших кольорів — обирай їх у каталозі або заверши вибір."
            )
            # Показати каталог ще раз для вибору інших кольорів або завершення
            await show_catalog(message)

        except ValueError:
            await message.answer("Введи, будь ласка, число (кількість бухт).")

    elif step == "name":
        user_data[user_id]["order"]["name"] = message.text
        user_data[user_id]["step"] = "phone"
        await message.answer("Введи телефон:")

    elif step == "phone":
        user_data[user_id]["order"]["phone"] = message.text
        user_data[user_id]["step"] = "delivery"

        kb = InlineKeyboardMarkup(row_width=2)
        for opt in DELIVERY_OPTIONS:
            kb.insert(InlineKeyboardButton(opt, callback_data=f"delivery_{opt}"))
        await message.answer("Оберіть спосіб доставки:", reply_markup=kb)

    elif step == "city":
        user_data[user_id]["order"]["city"] = message.text
        user_data[user_id]["step"] = "office"
        await message.answer("Введи номер відділення / поштомату / індекс:")

    elif step == "office":
        user_data[user_id]["order"]["office"] = message.text
        user_data[user_id]["step"] = "comment"
        await message.answer("Якщо є коментар — введи його, або напиши 'немає':")

    elif step == "comment":
        user_data[user_id]["order"]["comment"] = message.text
        user_data[user_id]["step"] = "confirmation"
        await confirm_order(message)

    else:
        await message.answer("Почни замовлення командою /start")


@dp.callback_query_handler(lambda c: c.data and c.data.startswith("delivery_"))
async def delivery_chosen(callback_query: types.CallbackQuery):
    user_id = callback_query.from_user.id
    delivery = callback_query.data.split("_", 1)[1]
    user_data[user_id]["order"]["delivery"] = delivery
    user_data[user_id]["step"] = "city"
    await bot.answer_callback_query(callback_query.id)
    await bot.send_message(user_id, "Введи населений пункт і область:")

async def confirm_order(message: types.Message):
    user_id = message.from_user.id
    data = user_data[user_id]

    text = "Підтвердіть ваше замовлення:\n\n"

    for c in data["selected_colors"]:
        qty = c["quantity"]
        ending = get_bukhta_ending(qty)
        text += f"{c['name']}: {qty} {ending}\n"

    order = data["order"]
    text += f"\nПІБ: {order.get('name','')}\n"
    text += f"Телефон: {order.get('phone','')}\n"
    text += f"Доставка: {order.get('delivery','')}\n"
    text += f"Населений пункт: {order.get('city','')}\n"
    text += f"Відділення/Поштомат/Індекс: {order.get('office','')}\n"
    text += f"Коментар: {order.get('comment','')}\n\n"

    kb = InlineKeyboardMarkup(row_width=2)
    kb.insert(InlineKeyboardButton("Підтвердити", callback_data="confirm_yes"))
    kb.insert(InlineKeyboardButton("Відмінити", callback_data="confirm_no"))

    await message.answer(text, reply_markup=kb)

@dp.callback_query_handler(lambda c: c.data in ["confirm_yes", "confirm_no"])
async def confirm_callback(callback_query: types.CallbackQuery):
    user_id = callback_query.from_user.id
    if callback_query.data == "confirm_yes":
        await send_to_google_sheet(user_id)
        user_data.pop(user_id, None)
        await bot.answer_callback_query(callback_query.id, "Замовлення відправлено!")
    else:
        user_data.pop(user_id, None)
        await bot.answer_callback_query(callback_query.id, "Замовлення скасовано.")
    await bot.send_message(user_id, "Якщо хочеш зробити нове замовлення — напиши /start")

async def send_to_google_sheet(user_id):
    data = user_data.get(user_id)
    if not data:
        return

    payload = {
        "colors": [{"color": c["name"], "quantity": c["quantity"]} for c in data["selected_colors"]],
        "delivery": data["order"].get("delivery", ""),
        "phone": data["order"].get("phone", ""),
        "name": data["order"].get("name", ""),
        "city": data["order"].get("city", ""),
        "postcode": data["order"].get("office", ""),
        "comment": data["order"].get("comment", ""),
    }

    try:
        resp = requests.post(WEBHOOK_URL, json=payload)
        if resp.status_code != 200:
            logging.error(f"Помилка відправки в Google Sheets: {resp.status_code} {resp.text}")
    except Exception as e:
        logging.error(f"Виняток при відправці в Google Sheets: {e}")

if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)
