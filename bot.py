import os
import json
import logging
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    ContextTypes, filters, ConversationHandler
)
import requests
from bs4 import BeautifulSoup

# Включаем логи
logging.basicConfig(level=logging.INFO)

# Стадии ConversationHandler
(
    SELECT_CITIES, SELECT_CATEGORIES, SET_PRICE_RANGE,
    SET_SEARCH_QUERY, SAVE_CONFIG, PARSE
) = range(6)

# База данных в памяти (временно)
user_data = {}

# Города Беларуси (пример)
CITIES = ["Минск", "Гомель", "Могилёв", "Витебск", "Гродно", "Брест", "Бобруйск", "Барановичи"]
# Категории (пример)
CATEGORIES = {
    "Авто": ["Легковые", "Мото", "Запчасти"],
    "Недвижимость": ["Квартиры", "Дома", "Комнаты"],
    "Электроника": ["Телефоны", "Компьютеры"],
    "Работа": ["Вакансии", "Резюме"]
}

TOKEN = os.getenv("BOT_TOKEN")  # берём токен из переменной окружения

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_data[user_id] = {
        "cities": [],
        "categories": [],
        "price_min": 0,
        "price_max": 1000000,
        "search_query": "",
        "config_name": ""
    }
    kb = [["Выбрать города", "Меню категорий"], ["Цена от/до", "Поиск"],
          ["Создать конфиг", "Парсинг"]]
    reply_markup = ReplyKeyboardMarkup(kb, resize_keyboard=True)
    await update.message.reply_text("Привет! Выбери действие:", reply_markup=reply_markup)

# ----------------- Города -----------------
async def ask_cities(update: Update, context: ContextTypes.DEFAULT_TYPE):
    buttons = [CITIES[i:i+3] for i in range(0, len(CITIES), 3)]
    buttons.append(["✅ Готово"])
    reply_markup = ReplyKeyboardMarkup(buttons, resize_keyboard=True)
    await update.message.reply_text("Выбери до 3 городов (нажимай на названия):", reply_markup=reply_markup)
    return SELECT_CITIES

async def select_cities(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    city = update.message.text
    if city == "✅ Готово":
        await start(update, context)
        return ConversationHandler.END
    if city in CITIES:
        if len(user_data[user_id]["cities"]) < 3:
            if city not in user_data[user_id]["cities"]:
                user_data[user_id]["cities"].append(city)
        await update.message.reply_text(f"Выбрано: {', '.join(user_data[user_id]['cities'])}")
    return SELECT_CITIES

# ----------------- Категории -----------------
async def ask_categories(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [[cat] for cat in CATEGORIES.keys()]
    kb.append(["✅ Назад"])
    reply_markup = ReplyKeyboardMarkup(kb, resize_keyboard=True)
    await update.message.reply_text("Выбери категорию:", reply_markup=reply_markup)
    return SELECT_CATEGORIES

async def select_categories(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    cat = update.message.text
    if cat == "✅ Назад":
        await start(update, context)
        return ConversationHandler.END
    if cat in CATEGORIES:
        subcats = CATEGORIES[cat]
        kb = [[sc] for sc in subcats] + [["✅ Назад к категориям"]]
        reply_markup = ReplyKeyboardMarkup(kb, resize_keyboard=True)
        await update.message.reply_text(f"Выбери подкатегорию в '{cat}':", reply_markup=reply_markup)
        context.user_data["current_category"] = cat
        return SELECT_CATEGORIES
    # Если выбрана подкатегория
    for main_cat, subs in CATEGORIES.items():
        if cat in subs:
            full_cat = f"{main_cat} / {cat}"
            if full_cat not in user_data[user_id]["categories"]:
                user_data[user_id]["categories"].append(full_cat)
            await update.message.reply_text(f"Добавлено: {full_cat}")
            return SELECT_CATEGORIES
    await update.message.reply_text("Неизвестная опция.")
    return SELECT_CATEGORIES

# ----------------- Цена -----------------
async def ask_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Введи диапазон цены через пробел: например → `100 50000`")
    return SET_PRICE_RANGE

async def set_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    try:
        pmin, pmax = map(int, update.message.text.split())
        if pmin < 0 or pmax < pmin:
            raise ValueError
        user_data[user_id]["price_min"] = pmin
        user_data[user_id]["price_max"] = pmax
        await update.message.reply_text(f"Цена: от {pmin} до {pmax}")
    except:
        await update.message.reply_text("Ошибка! Введите два числа: мин и макс.")
        return SET_PRICE_RANGE
    await start(update, context)
    return ConversationHandler.END

# ----------------- Поиск -----------------
async def ask_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Введите поисковый запрос (ключевые слова):")
    return SET_SEARCH_QUERY

async def set_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_data[user_id]["search_query"] = update.message.text
    await update.message.reply_text(f"Поиск: '{update.message.text}'")
    await start(update, context)
    return ConversationHandler.END

# ----------------- Сохранение конфига -----------------
async def ask_save_config(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Введите название конфигурации (латиницей, без пробелов):")
    return SAVE_CONFIG

async def save_config(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    name = update.message.text.strip()
    if not name.isalnum():
        await update.message.reply_text("Название только латинские буквы и цифры!")
        return SAVE_CONFIG
    config = user_data[user_id].copy()
    config.pop("config_name", None)
    os.makedirs("configs", exist_ok=True)
    with open(f"configs/{user_id}_{name}.json", "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
    await update.message.reply_text(f"✅ Конфиг '{name}' сохранён!")
    await start(update, context)
    return ConversationHandler.END

# ----------------- Парсинг -----------------
def scrape_kufar(cities, categories, price_min, price_max, query):
    # Упрощённый парсинг через Kufar API или HTML
    # В реальности лучше использовать официальный API, но его нет → парсим HTML
    results = []

    # Пример: парсим Минск, категория "Авто / Легковые"
    for city in cities[:1]:  # Ограничим 1 городом для демо
        for cat in categories[:1]:  # и 1 категорией
            city_code = city.lower().replace("ё", "е")
            cat_url_part = cat.replace(" ", "-").replace("/", "").lower()

            url = f"https://auto.kufar.by/listings?ot=1&query={query}&rgn={city_code}"
            try:
                res = requests.get(url, timeout=10)
                soup = BeautifulSoup(res.text, 'lxml')
                listings = soup.select('a[href^="https://auto.kufar.by/"]')[:3]  # первые 3
                for item in listings:
                    title = item.get_text(strip=True)
                    link = item['href']
                    if title and len(title) > 10:
                        results.append(f"{title}\n{link}")
            except Exception as e:
                results.append(f"Ошибка при парсинге: {str(e)}")
            break
        break
    return results or ["Ничего не найдено 😕"]

async def parse(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    data = user_data[user_id]
    msg = await update.message.reply_text("🔍 Ищу объявления...")
    results = scrape_kufar(
        data["cities"],
        data["categories"],
        data["price_min"],
        data["price_max"],
        data["search_query"]
    )
    await msg.edit_text("\n\n".join(results[:5]))  # присылаем первые 5

# ----------------- Основной запуск -----------------
def main():
    app = Application.builder().token(TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex("Выбрать города"), ask_cities),
            MessageHandler(filters.Regex("Меню категорий"), ask_categories),
            MessageHandler(filters.Regex("Цена от/до"), ask_price),
            MessageHandler(filters.Regex("Поиск"), ask_search),
            MessageHandler(filters.Regex("Создать конфиг"), ask_save_config),
        ],
        states={
            SELECT_CITIES: [MessageHandler(filters.TEXT & ~filters.COMMAND, select_cities)],
            SELECT_CATEGORIES: [MessageHandler(filters.TEXT & ~filters.COMMAND, select_categories)],
            SET_PRICE_RANGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_price)],
            SET_SEARCH_QUERY: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_search)],
            SAVE_CONFIG: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_config)],
        },
        fallbacks=[CommandHandler("start", start)],
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(conv_handler)
    app.add_handler(MessageHandler(filters.Regex("Парсинг"), parse))  # ← добавлено отдельно

    app.run_polling()

if __name__ == "__main__":
    main()
