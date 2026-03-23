import json
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup, WebAppInfo
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, ConversationHandler, ContextTypes, filters
)

BOT_TOKEN = "твой_токен"
MINI_APP_URL = "https://твой-домен/index.html"

STEP_FIELD, STEP_COUNTRY, STEP_IELTS, STEP_GPA, STEP_BUDGET = range(5)

FIELDS = ["Computer Science", "Medicine", "Economics", "Engineering", "Law", "Business"]
COUNTRIES = ["Germany", "Czech Republic", "Hungary", "Austria", "Netherlands", "Finland", "Canada", "Australia", "Любая страна"]
BUDGETS = ["Бесплатно", "до $5000", "до $15000", "до $30000", "Любой"]


#загрузка базы вузов ебучих

def load_universities():
    with open("universities.json", encoding="utf-8") as f:
        return json.load(f)

UNIS = load_universities()


#фильтр

def find_unis(field, country, ielts, gpa, budget_max):
    result = []
    for uni in UNIS:
        if field not in uni["fields"]:
            continue
        if country != "Любая страна" and country != uni["country"]:
            continue
        if ielts < uni["ielts_min"]:
            continue
        if gpa < uni["gpa_min"]:
            continue
        if budget_max is not None and uni["tuition_usd"] > budget_max:
            continue
        result.append(uni)
    return result


#helpers 

def make_keyboard(options):
    buttons = [InlineKeyboardButton(o, callback_data=o) for o in options]
    rows = [buttons[i:i+2] for i in range(0, len(buttons), 2)]
    return InlineKeyboardMarkup(rows)

def budget_to_number(label):
    mapping = {
        "Бесплатно": 0,
        "до $5000": 5000,
        "до $15000": 15000,
        "до $30000": 30000,
        "Любой": None
    }
    return mapping[label]

def uni_card(uni):
    cost = "Бесплатно" if uni["tuition_usd"] == 0 else f"${uni['tuition_usd']}/год"
    grant = "✅ Есть стипендии" if uni["scholarship"] else "❌ Стипендий нет"
    return (
        f"🏛 *{uni['name']}*\n"
        f"📍 {uni['city']}, {uni['country']}\n"
        f"🗣 IELTS ≥ {uni['ielts_min']} | GPA ≥ {uni['gpa_min']}\n"
        f"💰 {cost}\n"
        f"{grant}\n"
        f"🔗 {uni['url']}"
    )


#обработчики 

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data.clear()
    btn = KeyboardButton(
        "🎓 Открыть UniSearch",
        web_app=WebAppInfo(url=MINI_APP_URL)
    )
    markup = ReplyKeyboardMarkup([[btn]], resize_keyboard=True)
    await update.message.reply_text(
        "Привет! Нажми кнопку ниже чтобы найти университет 👇",
        reply_markup=markup
    )

async def handle_webapp_data(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    data = json.loads(update.message.web_app_data.data)
    count = data.get("count", 0)
    unis = data.get("unis", [])

    if count == 0:
        await update.message.reply_text("😔 По твоим параметрам ничего не нашлось. Попробуй изменить фильтры.")
        return

    lines = [f"🎉 Нашла *{count}* вариантов:\n"]
    for name in unis[:10]:
        uni = next((u for u in UNIS if u["name"] == name), None)
        if uni:
            lines.append(uni_card(uni))

    for msg in lines:
        await update.message.reply_text(msg, parse_mode="Markdown")

async def step_field(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    ctx.user_data["field"] = query.data
    await query.edit_message_text(
        f"✅ {query.data}\n\nШаг 2 — выбери страну:",
        reply_markup=make_keyboard(COUNTRIES)
    )
    return STEP_COUNTRY


async def step_country(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    ctx.user_data["country"] = query.data
    await query.edit_message_text(
        f"✅ {query.data}\n\nШаг 3 — введи IELTS (например 6.5):"
    )
    return STEP_IELTS


async def step_ielts(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        ielts = float(update.message.text)
        if not 0 <= ielts <= 9:
            raise ValueError
    except ValueError:
        await update.message.reply_text("Введи число от 0 до 9, например 7.0")
        return STEP_IELTS
    ctx.user_data["ielts"] = ielts
    await update.message.reply_text("Шаг 4 — введи GPA (от 0 до 4, например 3.5):")
    return STEP_GPA


async def step_gpa(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        gpa = float(update.message.text)
        if not 0 <= gpa <= 4:
            raise ValueError
    except ValueError:
        await update.message.reply_text("Введи число от 0 до 4")
        return STEP_GPA
    ctx.user_data["gpa"] = gpa
    await update.message.reply_text(
        "Шаг 5 — бюджет:",
        reply_markup=make_keyboard(BUDGETS)
    )
    return STEP_BUDGET


async def step_budget(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    d = ctx.user_data
    budget_max = budget_to_number(query.data)
    results = find_unis(d["field"], d["country"], d["ielts"], d["gpa"], budget_max)

    if not results:
        await query.edit_message_text("😔 Ничего не нашлось. Попробуй /start с другими параметрами.")
        return ConversationHandler.END

    await query.edit_message_text(f"🎉 Нашла {len(results)} вариантов:")
    for uni in results[:10]:
        await query.message.reply_text(uni_card(uni), parse_mode="Markdown")
    return ConversationHandler.END


async def cmd_cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Отменила. Напиши /start чтобы начать заново.")
    return ConversationHandler.END


#пуск 

def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, handle_webapp_data))

    conv = ConversationHandler(
        entry_points=[CommandHandler("classic", cmd_start)],
        states={
            STEP_FIELD:   [CallbackQueryHandler(step_field)],
            STEP_COUNTRY: [CallbackQueryHandler(step_country)],
            STEP_IELTS:   [MessageHandler(filters.TEXT & ~filters.COMMAND, step_ielts)],
            STEP_GPA:     [MessageHandler(filters.TEXT & ~filters.COMMAND, step_gpa)],
            STEP_BUDGET:  [CallbackQueryHandler(step_budget)],
        },
        fallbacks=[CommandHandler("cancel", cmd_cancel)]
    )

    app.add_handler(conv)
    app.run_polling()

main()
