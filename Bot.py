import logging
from datetime import datetime, timedelta, time
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, CallbackQueryHandler, ConversationHandler, MessageHandler, filters

BOT_TOKEN = "7202762947:AAGQHuyAdD_mNoUGzmkeCBblcVbxbOjgWsA"

# Состояния
(
    CHOOSING_DIRECTION, CHOOSING_TYPE, CHOOSING_DATE_OPTION,
    AWAITING_YAVKA, AWAITING_SDACHA, CONFIRMING
) = range(6)

# Временное хранилище
user_data = {}

logging.basicConfig(level=logging.INFO)

def create_date_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Сегодня", callback_data="today"),
         InlineKeyboardButton("Вчера", callback_data="yesterday")],
        [InlineKeyboardButton("Указать вручную", callback_data="manual")]
    ])

def calculate_night_hours(start, end):
    night_start = time(22, 0)
    night_end = time(6, 0)

    total_night = timedelta()

    if end < start:
        end += timedelta(days=1)

    current = start
    while current < end:
        next_minute = current + timedelta(minutes=1)
        if (night_start <= current.time() or current.time() < night_end):
            total_night += timedelta(minutes=1)
        current = next_minute

    return total_night

def get_summary_text(entry):
    yavka = entry['yavka']
    sdacha = entry['sdacha']
    duration = sdacha - yavka if sdacha > yavka else (sdacha + timedelta(days=1)) - yavka
    night = calculate_night_hours(yavka, sdacha)
    pereotdyh = entry.get('pereotdyh', timedelta())
    
    return (f"Тип: {entry['type']}\n"
            f"Направление: {entry['direction']}\n"
            f"Явка: {yavka}\n"
            f"Сдача: {sdacha}\n"
            f"Общее время: {duration}\n"
            f"Ночные часы: {night}\n"
            f"Переотдых: {pereotdyh}")

# Хэндлеры
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton("Туда", callback_data="Туда"),
                 InlineKeyboardButton("Обратно", callback_data="Обратно")]]
    await update.message.reply_text("Выбери направление:", reply_markup=InlineKeyboardMarkup(keyboard))
    return CHOOSING_DIRECTION

async def direction_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_data[query.from_user.id] = {'direction': query.data}
    keyboard = [[InlineKeyboardButton("Поездом", callback_data="поездом"),
                 InlineKeyboardButton("Пассажиром", callback_data="пассажиром")]]
    await query.edit_message_text("Выбери способ:", reply_markup=InlineKeyboardMarkup(keyboard))
    return CHOOSING_TYPE

async def type_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_data[query.from_user.id]['type'] = query.data
    await query.edit_message_text("Выбери дату:", reply_markup=create_date_keyboard())
    return CHOOSING_DATE_OPTION

async def date_option(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    if query.data == "today":
        date = datetime.now().date()
    elif query.data == "yesterday":
        date = (datetime.now() - timedelta(days=1)).date()
    else:
        await query.edit_message_text("Введи дату в формате ГГГГ-ММ-ДД:")
        return CHOOSING_DATE_OPTION

    user_data[uid]['date'] = date
    await query.edit_message_text("Введи явку (часы:минуты):")
    return AWAITING_YAVKA

async def handle_manual_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        date = datetime.strptime(update.message.text.strip(), "%Y-%m-%d").date()
        user_data[update.effective_user.id]['date'] = date
        await update.message.reply_text("Введи явку (часы:минуты):")
        return AWAITING_YAVKA
    except:
        await update.message.reply_text("Неверный формат. Пример: 2025-04-18")
        return CHOOSING_DATE_OPTION

async def handle_yavka(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    try:
        t = datetime.strptime(update.message.text.strip(), "%H:%M").time()
        user_data[uid]['yavka'] = datetime.combine(user_data[uid]['date'], t)
        await update.message.reply_text("Введи сдачу (часы:минуты):")
        return AWAITING_SDACHA
    except:
        await update.message.reply_text("Неверный формат. Пример: 23:40")
        return AWAITING_YAVKA

async def handle_sdacha(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    try:
        t = datetime.strptime(update.message.text.strip(), "%H:%M").time()
        yavka = user_data[uid]['yavka']
        sdacha_dt = datetime.combine(user_data[uid]['date'], t)
        if sdacha_dt < yavka:
            sdacha_dt += timedelta(days=1)
        user_data[uid]['sdacha'] = sdacha_dt

        # Переотдых
        last_sdacha = context.user_data.get('last_sdacha')
        pereotdyh = timedelta()
        if last_sdacha:
            pereotdyh = user_data[uid]['yavka'] - last_sdacha
            if pereotdyh < timedelta(hours=6):
                pereotdyh = timedelta()
        user_data[uid]['pereotdyh'] = pereotdyh
        context.user_data['last_sdacha'] = sdacha_dt

        await update.message.reply_text("Сохранено:\n" + get_summary_text(user_data[uid]))
        return ConversationHandler.END
    except:
        await update.message.reply_text("Неверный формат. Пример: 06:15")
        return AWAITING_SDACHA

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Отменено.")
    return ConversationHandler.END

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            CHOOSING_DIRECTION: [CallbackQueryHandler(direction_choice)],
            CHOOSING_TYPE: [CallbackQueryHandler(type_choice)],
            CHOOSING_DATE_OPTION: [
                CallbackQueryHandler(date_option, pattern="^(today|yesterday|manual)$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_manual_date)
            ],
            AWAITING_YAVKA: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_yavka)],
            AWAITING_SDACHA: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_sdacha)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(conv_handler)
    app.run_polling()

if __name__ == "__main__":
    main()
