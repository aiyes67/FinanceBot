import os
import logging
from datetime import datetime, date, timedelta
from typing import Dict, Any, Tuple

from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)
import asyncpg

# ==========================================
# ⚙️ НАСТРОЙКИ И КОНФИГУРАЦИЯ
# ==========================================
BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_TELEGRAM_BOT_TOKEN_HERE")
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://user:password@localhost/finance_db")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Поул подключений к БД
pool: asyncpg.Pool = None

# ==========================================
# 🌐 ЛОКАЛИЗАЦИЯ И ИНТЕРФЕЙС
# ==========================================
MONTHS = {
    "ru": ["Январь", "Февраль", "Март", "Апрель", "Май", "Июнь", "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"],
    "en": ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"],
    "kk": ["Қаңтар", "Ақпан", "Наурыз", "Сәуір", "Мамыр", "Маусым", "Шілде", "Тамыз", "Қыркүйек", "Қазан", "Қараша", "Желтоқсан"],
}

T = {
    "ru": {
        "menu": {
            "add_expense": "➖ Расход", "add_income": "➕ Доход",
            "balance_menu": "⚙️ Баланс", "tx_history": "📜 Транзакции",
            "day": "📊 День", "week": "📊 Неделя", "month": "📊 Месяц", "year": "📊 Год",
            "lang": "🌐 Язык",
        },
        "titles": {
            ("day", False): "Сегодня", ("day", True): "Вчера",
            ("week", False): "Текущая неделя", ("week", True): "Прошлая неделя",
            ("month", False): "Текущий месяц", ("month", True): "Прошлый месяц",
            ("year", False): "Текущий год", ("year", True): "Прошлый год",
        },
        "extra": {"week": "Неделя", "empty": "Нет операций за этот период."},
        "prompt_amount": "Введите сумму и категорию (например: 1500 Продукты):",
        "saved": "Запись успешно сохранена!",
        "choose_lang": "Выберите язык / Тілді таңдаңыз / Select language:",
    },
    "en": {
        "menu": {
            "add_expense": "➖ Expense", "add_income": "➕ Income",
            "balance_menu": "⚙️ Balance", "tx_history": "📜 Transactions",
            "day": "📊 Day", "week": "📊 Week", "month": "📊 Month", "year": "📊 Year",
            "lang": "🌐 Language",
        },
        "titles": {
            ("day", False): "Today", ("day", True): "Yesterday",
            ("week", False): "Current Week", ("week", True): "Last Week",
            ("month", False): "Current Month", ("month", True): "Last Month",
            ("year", False): "Current Year", ("year", True): "Last Year",
        },
        "extra": {"week": "Week", "empty": "No transactions for this period."},
        "prompt_amount": "Enter amount and category (e.g. 1500 Groceries):",
        "saved": "Transaction successfully saved!",
        "choose_lang": "Select language:",
    },
    "kk": {
        "menu": {
            "add_expense": "➖ Шығыс", "add_income": "➕ Кіріс",
            "balance_menu": "⚙️ Баланс", "tx_history": "📜 Операциялар",
            "day": "📊 Күн", "week": "📊 Апта", "month": "📊 Ай", "year": "📊 Жыл",
            "lang": "🌐 Тіл",
        },
        "titles": {
            ("day", False): "Бүгін", ("day", True): "Кеше",
            ("week", False): "Ағымдағы апта", ("week", True): "Өткен апта",
            ("month", False): "Ағымдағы ай", ("month", True): "Өткен ай",
            ("year", False): "Ағымдағы жыл", ("year", True): "Өткен жыл",
        },
        "extra": {"week": "Апта", "empty": "Бұл кезеңде операциялар жоқ."},
        "prompt_amount": "Соманы және санатты енгізіңіз (мысалы: 1500 Азық-түлік):",
        "saved": "Операция сәтті сақталды!",
        "choose_lang": "Тілді таңдаңыз:",
    }
}

MENU_ORDER = [
    ["add_expense", "add_income"],
    ["balance_menu", "tx_history"],
    ["day", "week", "month", "year"],
    ["lang"]
]

COMMANDS = {
    "/day": "day", "/yesterday": "lastday",
    "/week": "week", "/month": "month", "/year": "year",
    "/lastweek": "lastweek", "/lastmonth": "lastmonth", "/lastyear": "lastyear",
    "/expense": "add_expense", "/income": "add_income",
    "/balance": "balance_menu", "/tx": "tx_history", "/lang": "lang",
}

# ==========================================
# 🛠 ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ДАТИРОВАНИЯ
# ==========================================
def monday_of(d: date) -> date:
    return d - timedelta(days=d.weekday())

def period_bounds(period: str, offset: int = 0, today: date = None) -> Tuple[date, date]:
    today = today or date.today()

    if period == "day":
        d = today + timedelta(days=offset)
        return d, d

    if period == "week":
        start = monday_of(today) + timedelta(days=7 * offset)
        return start, start + timedelta(days=6)

    if period == "month":
        y, m0 = divmod(today.year * 12 + today.month - 1 + offset, 12)
        ny, nm0 = divmod(today.year * 12 + today.month - 1 + offset + 1, 12)
        return date(y, m0 + 1, 1), date(ny, nm0 + 1, 1) - timedelta(days=1)

    year = today.year + offset
    return date(year, 1, 1), date(year, 12, 31)

def min_offset(period: str, first: date, today: date = None) -> int:
    today = today or date.today()
    if period == "day":
        off = (first - today).days
    elif period == "week":
        off = (monday_of(first) - monday_of(today)).days // 7
    elif period == "month":
        off = (first.year * 12 + first.month) - (today.year * 12 + today.month)
    else:
        off = first.year - today.year
    return min(off, 0)

def period_title(lang: str, period: str, offset: int, start: date) -> str:
    t = T[lang]
    if offset == 0:
        tag = t["titles"].get((period, False))
    elif offset == -1:
        tag = t["titles"].get((period, True))
    else:
        tag = None

    if period == "day":
        return tag or start.strftime("%d.%m.%Y")
    if period == "week":
        return tag or t["extra"]["week"]
    name = f"{MONTHS[lang][start.month - 1]} {start.year}" if period == "month" else str(start.year)
    return f"{tag} — {name}" if tag else name

def short_label(lang: str, period: str, start: date, end: date) -> str:
    if period == "day":
        return start.strftime("%d.%m")
    if period == "week":
        return f"{start:%d.%m}–{end:%d.%m}"
    if period == "month":
        return f"{MONTHS[lang][start.month - 1]} {start.year}"
    return str(start.year)

# ==========================================
# 🗄 РАБОТА С БАЗОЙ ДАННЫХ
# ==========================================
async def get_user_lang(user_id: int) -> str:
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT lang FROM users WHERE user_id = $1", user_id)
        if not row:
            await conn.execute("INSERT INTO users (user_id, lang) VALUES ($1, 'ru')", user_id)
            return "ru"
        return row["lang"]

async def set_user_lang(user_id: int, lang: str):
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO users (user_id, lang) VALUES ($1, $2) ON CONFLICT (user_id) DO UPDATE SET lang = $2",
            user_id, lang
        )

async def get_first_tx_date(user_id: int) -> date:
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT MIN(tx_date) FROM transactions WHERE user_id = $1", user_id)
        return row[0] if row and row[0] else date.today()

async def get_report_data(user_id: int, start_d: date, end_d: date):
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT type, category, SUM(amount) as total
            FROM transactions
            WHERE user_id = $1 AND tx_date BETWEEN $2 AND $3
            GROUP BY type, category
            ORDER BY total DESC
            """,
            user_id, start_d, end_d
        )
        return rows

# ==========================================
# ⌨️ КЛАВИАТУРЫ И ОТРЕЗКИ
# ==========================================
def build_main_keyboard(lang: str) -> ReplyKeyboardMarkup:
    btn_text = T[lang]["menu"]
    keyboard = [[btn_text[key] for key in row] for row in MENU_ORDER]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def report_keyboard(lang: str, period: str, offset: int, min_off: int) -> InlineKeyboardMarkup:
    nav = []
    if offset - 1 >= min_off:
        s, e = period_bounds(period, offset - 1)
        nav.append(InlineKeyboardButton(
            text="◀ " + short_label(lang, period, s, e),
            callback_data=f"rep:{period}:{offset - 1}"
        ))
    if offset + 1 <= 0:
        s, e = period_bounds(period, offset + 1)
        nav.append(InlineKeyboardButton(
            text=short_label(lang, period, s, e) + " ▶",
            callback_data=f"rep:{period}:{offset + 1}"
        ))

    views = [
        InlineKeyboardButton(
            text=("✅ " if p == period else "") + T[lang]["menu"][p].replace("📊 ", ""),
            callback_data=f"rep:{p}:0"
        )
        for p in ("day", "week", "month", "year")
    ]
    
    inline_kb = []
    if nav:
        inline_kb.append(nav)
    inline_kb.append(views)
    
    return InlineKeyboardMarkup(inline_kb)

# ==========================================
# 📊 ГЕНЕРАЦИЯ И ОТПРАВКА ОТЧЕТА
# ==========================================
async def send_report(chat_id: int, user_id: int, lang: str, period: str, offset: int = 0, message_id: int = None, context: ContextTypes.DEFAULT_TYPE = None):
    start_d, end_d = period_bounds(period, offset)
    first_d = await get_first_tx_date(user_id)
    min_off = min_offset(period, first_d)

    rows = await get_report_data(user_id, start_d, end_d)
    
    title = period_title(lang, period, offset, start_d)
    
    inc_lines, exp_lines = [], []
    tot_inc, tot_exp = 0, 0

    for r in rows:
        amt = float(r["total"])
        if r["type"] == "income":
            tot_inc += amt
            inc_lines.append(f" • {r['category']}: {amt:,.2f}")
        else:
            tot_exp += amt
            exp_lines.append(f" • {r['category']}: {amt:,.2f}")

    text = f"📅 <b>{title}</b>\n"
    text += f"<i>({start_d.strftime('%d.%m.%Y')} — {end_d.strftime('%d.%m.%Y')})</i>\n\n"

    if not rows:
        text += T[lang]["extra"]["empty"]
    else:
        if tot_inc > 0:
            text += f"<b>➕ Доходы: {tot_inc:,.2f}</b>\n" + "\n".join(inc_lines) + "\n\n"
        if tot_exp > 0:
            text += f"<b>➖ Расходы: {tot_exp:,.2f}</b>\n" + "\n".join(exp_lines) + "\n\n"
        
        balance = tot_inc - tot_exp
        text += f"<b>⚖️ Итог: {balance:+,.2f}</b>"

    kb = report_keyboard(lang, period, offset, min_off)

    if message_id and context:
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            parse_mode="HTML",
            reply_markup=kb
        )
    else:
        await context.bot.send_message(
            chat_id=chat_id,
            text=text,
            parse_mode="HTML",
            reply_markup=kb
        )

# ==========================================
# 🤖 ОБРАБОТЧИКИ КОМАНД И СООБЩЕНИЙ
# ==========================================
async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    lang = await get_user_lang(user_id)
    await update.message.reply_text(
        f"Привет! Выберите действие:",
        reply_markup=build_main_keyboard(lang)
    )

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    lang = await get_user_lang(user_id)
    msg_text = update.message.text.strip()

    # Маппинг текста кнопок меню к экшенам
    inv_menu = {v: k for k, v in T[lang]["menu"].items()}
    action = inv_menu.get(msg_text) or COMMANDS.get(msg_text)

    if action in ("day", "week", "month", "year"):
        await send_report(update.effective_chat.id, user_id, lang, action, offset=0, context=context)
    elif action in ("lastday", "lastweek", "lastmonth", "lastyear"):
        period = action.replace("last", "")
        await send_report(update.effective_chat.id, user_id, lang, period, offset=-1, context=context)
    elif action == "lang":
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🇷🇺 Русский", callback_data="setlang:ru"),
             InlineKeyboardButton("🇬🇧 English", callback_data="setlang:en"),
             InlineKeyboardButton("🇰🇿 Қазақша", callback_data="setlang:kk")]
        ])
        await update.message.reply_text(T[lang]["choose_lang"], reply_markup=kb)
    elif action in ("add_expense", "add_income"):
        context.user_data["pending_tx_type"] = "expense" if action == "add_expense" else "income"
        await update.message.reply_text(T[lang]["prompt_amount"])
    else:
        # Быстрый ввод операции: например "1500 Продукты"
        pending_type = context.user_data.pop("pending_tx_type", "expense")
        parts = msg_text.split(maxsplit=1)
        try:
            amount = float(parts[0].replace(",", "."))
            category = parts[1] if len(parts) > 1 else "Разное"
            
            async with pool.acquire() as conn:
                await conn.execute(
                    "INSERT INTO transactions (user_id, amount, type, category, tx_date) VALUES ($1, $2, $3, $4, $5)",
                    user_id, amount, pending_type, category, date.today()
                )
            await update.message.reply_text(T[lang]["saved"])
        except ValueError:
            pass

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    lang = await get_user_lang(user_id)
    data = query.data.split(":")

    if data[0] == "rep":
        period = data[1]
        offset = int(data[2])
        if period in ("day", "week", "month", "year"):
            await send_report(
                chat_id=query.message.chat_id,
                user_id=user_id,
                lang=lang,
                period=period,
                offset=offset,
                message_id=query.message.message_id,
                context=context
            )
    elif data[0] == "setlang":
        new_lang = data[1]
        await set_user_lang(user_id, new_lang)
        await query.message.edit_text("Язык изменен! / Language updated!")
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text="Обновленное меню:",
            reply_markup=build_main_keyboard(new_lang)
        )

# ==========================================
# 🚀 ЗАПУСК БОТА И ИНИЦИАЛИЗАЦИЯ
# ==========================================
async def post_init(application):
    global pool
    pool = await asyncpg.create_pool(DATABASE_URL)
    logger.info("Подключение к БД успешно установлено.")

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).post_init(post_init).build()

    app.add_handler(CommandHandler("start", start_handler))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

    logger.info("Запуск бота...")
    app.run_polling()

if __name__ == "__main__":
    main()
