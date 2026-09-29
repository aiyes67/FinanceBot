import os
import re
import json
import urllib.request
import urllib.error
from urllib.parse import urlparse, parse_qs
from contextlib import contextmanager
from datetime import datetime, date, timedelta, timezone
from http.server import BaseHTTPRequestHandler
from zoneinfo import ZoneInfo

import psycopg2
from psycopg2.extras import RealDictCursor

# ============================================================
# CONFIG
# ============================================================

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
DATABASE_URL = os.environ.get("DATABASE_URL", "")
try:
    OWNER_ID = int(os.environ.get("OWNER_ID") or "0")
except ValueError:
    OWNER_ID = 0
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "")

try:
    TZ = ZoneInfo("Asia/Almaty")
except Exception:
    TZ = timezone(timedelta(hours=5))

LANGS = {"ru": "Русский", "en": "English", "kk": "Қазақша"}

# ============================================================
# TRANSLATIONS
# ============================================================

T = {
    "ru": {
        "help": (
            "💰 Финансовый помощник\n\n"
            "Нажми ➖ Расход или ➕ Доход, потом напиши сумму и описание, например: кофе 1500.\n\n"
            "📅 День / 📊 Неделя / Месяц / Год — отчёты, листай ◀ ▶.\n"
            "🧾 Транзакции — список операций, там же удаление.\n"
            "💼 Баланс — итог за всё время и очистка истории.\n"
            "🌐 Язык — сменить язык"
        ),
        "menu": {
            "add_expense": "➖ Расход", "add_income": "➕ Доход",
            "day": "📅 День", "week": "📊 Неделя",
            "month": "📊 Месяц", "year": "📊 Год",
            "transactions": "🧾 Транзакции", "balance": "💼 Баланс",
            "lang": "🌐 Язык",
        },
        "prompt_add_expense": "Напиши сумму и описание расхода, например: кофе 1500",
        "prompt_add_income": "Напиши сумму и описание дохода, например: зарплата 400000",
        "no_amount": "Не вижу сумму. Напиши, например: кофе 1500",
        "saved": "✅ Записано:",
        "cat_prompt": "Категория (по желанию):",
        "denied": "Доступ закрыт.",
        "error": "Произошла ошибка при обработке.",
        "lang_prompt": "Выбери язык:",
        "lang_set": "Язык: Русский",
        "income": "Доходы", "expense": "Расходы", "balance": "Баланс", "count": "Операций",
        "top": "Топ расходов по категориям:", "no_category": "Без категории",
        "cats": {"food": "Еда", "transport": "Транспорт", "home": "Жильё", "shopping": "Покупки",
                 "health": "Здоровье", "fun": "Досуг", "other": "Другое",
                 "salary": "Зарплата", "business": "Бизнес"},
        "titles": {
            ("day", False): "Сегодня", ("day", True): "Вчера",
            ("week", False): "Текущая неделя", ("week", True): "Прошлая неделя",
            ("month", False): "Текущий месяц", ("month", True): "Прошлый месяц",
            ("year", False): "Текущий год", ("year", True): "Прошлый год",
        },
        "tx_empty": "Операций пока нет. Добавь первую кнопкой ➖ Расход или ➕ Доход.",
        "tx_title": "🧾 Транзакции",
        "tx_page": "Стр. {n}/{total}",
        "tx_deleted": "Удалено.",
        "del_btn": "🗑",
        "del_confirm": "Удалить эту операцию?",
        "del_yes": "🗑 Удалить",
        "del_no": "↩️ Отмена",
        "balance_title": "💼 Общий баланс",
        "first_tx": "Первая",
        "last_tx": "Последняя",
        "clear_btn": "🧹 Очистить историю",
        "clear_choose": "Что удалить?",
        "clear_expenses": "🧹 Только расходы",
        "clear_incomes": "🧹 Только доходы",
        "clear_all": "🧹 Всё",
        "clear_cancel": "↩️ Отмена",
        "clear_confirm": "Удалить {what}? Это действие необратимо.",
        "clear_yes": "✅ Да, удалить",
        "clear_done": "Удалено операций: {n}.",
        "clear_expenses_what": "все расходы",
        "clear_incomes_what": "все доходы",
        "clear_all_what": "всю историю",
    },
    "en": {
        "help": (
            "💰 Finance assistant\n\n"
            "Tap ➖ Expense or ➕ Income, then type the amount and a description, e.g.: coffee 1500.\n\n"
            "📅 Day / 📊 Week / Month / Year — reports, browse with ◀ ▶.\n"
            "🧾 Transactions — list with delete.\n"
            "💼 Balance — all-time totals and history cleanup.\n"
            "🌐 Language — change language"
        ),
        "menu": {
            "add_expense": "➖ Expense", "add_income": "➕ Income",
            "day": "📅 Day", "week": "📊 Week",
            "month": "📊 Month", "year": "📊 Year",
            "transactions": "🧾 Transactions", "balance": "💼 Balance",
            "lang": "🌐 Language",
        },
        "prompt_add_expense": "Type the amount and a description of the expense, e.g.: coffee 1500",
        "prompt_add_income": "Type the amount and a description of the income, e.g.: salary 400000",
        "no_amount": "I can't see an amount. Try: coffee 1500",
        "saved": "✅ Saved:",
        "cat_prompt": "Category (optional):",
        "denied": "Access denied.",
        "error": "Something went wrong.",
        "lang_prompt": "Choose a language:",
        "lang_set": "Language: English",
        "income": "Income", "expense": "Expenses", "balance": "Balance", "count": "Transactions",
        "top": "Top expense categories:", "no_category": "Uncategorized",
        "cats": {"food": "Food", "transport": "Transport", "home": "Home", "shopping": "Shopping",
                 "health": "Health", "fun": "Fun", "other": "Other",
                 "salary": "Salary", "business": "Business"},
        "titles": {
            ("day", False): "Today", ("day", True): "Yesterday",
            ("week", False): "This week", ("week", True): "Last week",
            ("month", False): "This month", ("month", True): "Last month",
            ("year", False): "This year", ("year", True): "Last year",
        },
        "tx_empty": "No transactions yet. Add the first one with ➖ Expense or ➕ Income.",
        "tx_title": "🧾 Transactions",
        "tx_page": "Page {n}/{total}",
        "tx_deleted": "Deleted.",
        "del_btn": "🗑",
        "del_confirm": "Delete this transaction?",
        "del_yes": "🗑 Delete",
        "del_no": "↩️ Cancel",
        "balance_title": "💼 Total balance",
        "first_tx": "First",
        "last_tx": "Last",
        "clear_btn": "🧹 Clear history",
        "clear_choose": "What to delete?",
        "clear_expenses": "🧹 Expenses only",
        "clear_incomes": "🧹 Incomes only",
        "clear_all": "🧹 Everything",
        "clear_cancel": "↩️ Cancel",
        "clear_confirm": "Delete {what}? This cannot be undone.",
        "clear_yes": "✅ Yes, delete",
        "clear_done": "Deleted: {n}.",
        "clear_expenses_what": "all expenses",
        "clear_incomes_what": "all incomes",
        "clear_all_what": "the whole history",
    },
    "kk": {
        "help": (
            "💰 Қаржылық көмекші\n\n"
            "➖ Шығыс немесе ➕ Кіріс батырмасын басып, соманы және сипаттаманы жаз, мысалы: кофе 1500.\n\n"
            "📅 Күн / 📊 Апта / Ай / Жыл — есептер, ◀ ▶ арқылы ауыстыр.\n"
            "🧾 Транзакциялар — тізім және жою.\n"
            "💼 Баланс — жалпы қорытынды және тарихты тазалау.\n"
            "🌐 Тіл — тілді ауыстыру"
        ),
        "menu": {
            "add_expense": "➖ Шығыс", "add_income": "➕ Кіріс",
            "day": "📅 Күн", "week": "📊 Апта",
            "month": "📊 Ай", "year": "📊 Жыл",
            "transactions": "🧾 Транзакциялар", "balance": "💼 Баланс",
            "lang": "🌐 Тіл",
        },
        "prompt_add_expense": "Шығыстың сомасын және сипаттамасын жаз, мысалы: кофе 1500",
        "prompt_add_income": "Кірістің сомасын және сипаттамасын жаз, мысалы: жалақы 400000",
        "no_amount": "Соманы көрмедім. Мысалы: кофе 1500",
        "saved": "✅ Жазылды:",
        "cat_prompt": "Санат (қалауыңша):",
        "denied": "Қолжетімділік жабық.",
        "error": "Өңдеу кезінде қате шықты.",
        "lang_prompt": "Тілді таңда:",
        "lang_set": "Тіл: Қазақша",
        "income": "Кіріс", "expense": "Шығыс", "balance": "Баланс", "count": "Операциялар",
        "top": "Санаттар бойынша шығыстар үздігі:", "no_category": "Санатсыз",
        "cats": {"food": "Тамақ", "transport": "Көлік", "home": "Тұрғын үй", "shopping": "Сатып алу",
                 "health": "Денсаулық", "fun": "Демалыс", "other": "Басқа",
                 "salary": "Жалақы", "business": "Бизнес"},
        "titles": {
            ("day", False): "Бүгін", ("day", True): "Кеше",
            ("week", False): "Осы апта", ("week", True): "Өткен апта",
            ("month", False): "Осы ай", ("month", True): "Өткен ай",
            ("year", False): "Осы жыл", ("year", True): "Өткен жыл",
        },
        "tx_empty": "Әзірге операция жоқ. Алғашқысын ➖ Шығыс немесе ➕ Кіріс батырмасымен қос.",
        "tx_title": "🧾 Транзакциялар",
        "tx_page": "Бет {n}/{total}",
        "tx_deleted": "Жойылды.",
        "del_btn": "🗑",
        "del_confirm": "Осы операцияны жою керек пе?",
        "del_yes": "🗑 Жою",
        "del_no": "↩️ Болдырмау",
        "balance_title": "💼 Жалпы баланс",
        "first_tx": "Бірінші",
        "last_tx": "Соңғы",
        "clear_btn": "🧹 Тарихты тазалау",
        "clear_choose": "Нені жою керек?",
        "clear_expenses": "🧹 Тек шығыстар",
        "clear_incomes": "🧹 Тек кірістер",
        "clear_all": "🧹 Барлығы",
        "clear_cancel": "↩️ Болдырмау",
        "clear_confirm": "{what} жою керек пе? Бұл әрекетті қайтару мүмкін емес.",
        "clear_yes": "✅ Иә, жою",
        "clear_done": "Жойылған операциялар: {n}.",
        "clear_expenses_what": "барлық шығыстарды",
        "clear_incomes_what": "барлық кірістерді",
        "clear_all_what": "бүкіл тарихты",
    },
}

MENU_ORDER = [
    ["add_expense", "add_income"],
    ["day", "week", "month", "year"],
    ["transactions", "balance"],
    ["lang"],
]
LABEL_TO_ACTION = {label: action for lang in T.values() for action, label in lang["menu"].items()}

COMMANDS = {
    "/day": "day", "/today": "day",
    "/week": "week", "/month": "month", "/year": "year",
    "/lastweek": "lastweek", "/lastmonth": "lastmonth", "/lastyear": "lastyear",
    "/yesterday": "yesterday",
    "/expense": "add_expense", "/income": "add_income", "/lang": "lang",
    "/transactions": "transactions", "/tx": "transactions", "/balance": "balance",
}

CATEGORY_KEYS = {
    "add_expense": ["food", "transport", "home", "shopping", "health", "fun", "other"],
    "add_income": ["salary", "business", "other"],
}

REPORT_PERIODS = ("day", "week", "month", "year")
TX_PER_PAGE = 10

# ============================================================
# KEYBOARDS
# ============================================================

def menu_markup(lang):
    return {
        "keyboard": [[{"text": T[lang]["menu"][a]} for a in row] for row in MENU_ORDER],
        "resize_keyboard": True,
        "is_persistent": True,
    }


def cat_label(lang, key):
    if not key:
        return T[lang]["no_category"]
    return T[lang]["cats"].get(key, key)


def category_keyboard(state, tx_id, lang):
    buttons = [
        {"text": T[lang]["cats"][k], "callback_data": f"cat:{tx_id}:{k}"}
        for k in CATEGORY_KEYS[state]
    ]
    return {"inline_keyboard": [buttons[i:i + 3] for i in range(0, len(buttons), 3)]}


def report_keyboard(lang, period, offset, min_off):
    nav = []
    if offset - 1 >= min_off:
        s, e = period_bounds(period, offset - 1)
        nav.append({"text": "◀ " + short_label(lang, period, s, e),
                    "callback_data": f"rep:{period}:{offset - 1}"})
    if offset + 1 <= 0:
        s, e = period_bounds(period, offset + 1)
        nav.append({"text": short_label(lang, period, s, e) + " ▶",
                    "callback_data": f"rep:{period}:{offset + 1}"})

    views = [
        {"text": ("✅ " if p == period else "")
                 + T[lang]["menu"][p].replace("📊 ", "").replace("📅 ", ""),
         "callback_data": f"rep:{p}:0"}
        for p in REPORT_PERIODS
    ]
    rows = []
    if nav:
        rows.append(nav)
    rows.append(views[:2])
    rows.append(views[2:])
    return {"inline_keyboard": rows}


def transactions_keyboard(lang, rows, page, total_pages):
    keyboard = []
    for tx in rows:
        icon = "➖" if tx["type"] == "expense" else "➕"
        d = tx["transaction_date"]
        desc = tx["description"] or cat_label(lang, tx["category"])
        line = f"{icon} {money(tx['amount'])} — {desc} ({d:%d.%m})"
        keyboard.append([
            {"text": line[:60], "callback_data": "noop"},
            {"text": T[lang]["del_btn"], "callback_data": f"del:{tx['id']}"},
        ])

    nav = []
    if page > 0:
        nav.append({"text": "◀", "callback_data": f"txp:{page - 1}"})
    nav.append({"text": T[lang]["tx_page"].format(n=page + 1, total=total_pages),
                "callback_data": "noop"})
    if page + 1 < total_pages:
        nav.append({"text": "▶", "callback_data": f"txp:{page + 1}"})
    keyboard.append(nav)
    return {"inline_keyboard": keyboard}


def delete_confirm_keyboard(lang, tx_id):
    return {"inline_keyboard": [[
        {"text": T[lang]["del_yes"], "callback_data": f"delok:{tx_id}"},
        {"text": T[lang]["del_no"], "callback_data": "delno"},
    ]]}


def balance_keyboard(lang):
    return {"inline_keyboard": [[
        {"text": T[lang]["clear_btn"], "callback_data": "clear:menu"}
    ]]}


def clear_menu_keyboard(lang):
    return {"inline_keyboard": [
        [{"text": T[lang]["clear_expenses"], "callback_data": "clear:expense"}],
        [{"text": T[lang]["clear_incomes"], "callback_data": "clear:income"}],
        [{"text": T[lang]["clear_all"], "callback_data": "clear:all"}],
        [{"text": T[lang]["clear_cancel"], "callback_data": "clear:cancel"}],
    ]]}


def clear_confirm_keyboard(lang, mode):
    return {"inline_keyboard": [[
        {"text": T[lang]["clear_yes"], "callback_data": f"clearok:{mode}"},
        {"text": T[lang]["clear_no"], "callback_data": "clear:cancel"},
    ]]}

# ============================================================
# TELEGRAM
# ============================================================

def tg(method, payload):
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/{method}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    return urllib.request.urlopen(req, timeout=10).read()


def send_message(chat_id, text, reply_markup=None):
    payload = {"chat_id": chat_id, "text": text[:4000]}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    try:
        tg("sendMessage", payload)
    except Exception as e:
        print("send_message error:", repr(e))

# ============================================================
# DB
# ============================================================

@contextmanager
def db():
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    try:
        with conn.cursor() as cur:
            yield cur
        conn.commit()
    finally:
        conn.close()


def get_user(user_id):
    try:
        with db() as cur:
            cur.execute(
                """
                SELECT
                  (SELECT lang FROM user_settings WHERE user_id = %s) AS lang,
                  (SELECT state FROM user_state
                    WHERE user_id = %s AND updated_at > now() - interval '30 minutes') AS state;
                """,
                (user_id, user_id),
            )
            row = cur.fetchone()
        return row["lang"], row["state"]
    except Exception as e:
        print("get_user error:", repr(e))
        return None, None


def set_lang(user_id, lang):
    with db() as cur:
        cur.execute(
            """
            INSERT INTO user_settings (user_id, lang) VALUES (%s, %s)
            ON CONFLICT (user_id) DO UPDATE SET lang = EXCLUDED.lang;
            """,
            (user_id, lang),
        )


def set_state(user_id, state):
    with db() as cur:
        if state is None:
            cur.execute("DELETE FROM user_state WHERE user_id = %s", (user_id,))
        else:
            cur.execute(
                """
                INSERT INTO user_state (user_id, state, updated_at)
                VALUES (%s, %s, now())
                ON CONFLICT (user_id) DO UPDATE
                  SET state = EXCLUDED.state, updated_at = now();
                """,
                (user_id, state),
            )


def add_transaction(user_id, tx_type, amount, description, tx_date):
    with db() as cur:
        cur.execute(
            """
            INSERT INTO transactions
            (user_id, type, amount, currency, description, transaction_date)
            VALUES (%s, %s, %s, 'KZT', %s, %s)
            RETURNING id;
            """,
            (user_id, tx_type, amount, description, tx_date),
        )
        return cur.fetchone()["id"]


def set_category(user_id, tx_id, category):
    with db() as cur:
        cur.execute(
            "UPDATE transactions SET category = %s WHERE id = %s AND user_id = %s",
            (category, tx_id, user_id),
        )


def delete_transaction(user_id, tx_id):
    with db() as cur:
        cur.execute(
            "DELETE FROM transactions WHERE id = %s AND user_id = %s RETURNING id",
            (tx_id, user_id),
        )
        return cur.fetchone() is not None


def clear_transactions(user_id, mode):
    with db() as cur:
        if mode == "all":
            cur.execute("DELETE FROM transactions WHERE user_id = %s", (user_id,))
        else:
            cur.execute(
                "DELETE FROM transactions WHERE user_id = %s AND type = %s",
                (user_id, mode),
            )
        return cur.rowcount


def get_report(user_id, start, end):
    with db() as cur:
        cur.execute(
            """
            SELECT type, COALESCE(SUM(amount), 0) AS total, COUNT(*) AS cnt
            FROM transactions
            WHERE user_id = %s AND transaction_date BETWEEN %s AND %s
            GROUP BY type;
            """,
            (user_id, start, end),
        )
        totals = {r["type"]: r for r in cur.fetchall()}

        cur.execute(
            """
            SELECT category, SUM(amount) AS total
            FROM transactions
            WHERE user_id = %s AND type = 'expense'
              AND transaction_date BETWEEN %s AND %s
            GROUP BY category ORDER BY 2 DESC LIMIT 5;
            """,
            (user_id, start, end),
        )
        top = cur.fetchall()

    income = float(totals.get("income", {}).get("total", 0))
    expense = float(totals.get("expense", {}).get("total", 0))
    income_cnt = int(totals.get("income", {}).get("cnt", 0) or 0)
    expense_cnt = int(totals.get("expense", {}).get("cnt", 0) or 0)
    return {
        "income": income, "expense": expense, "balance": income - expense,
        "count": income_cnt + expense_cnt, "top": top,
        "income_cnt": income_cnt, "expense_cnt": expense_cnt,
    }


def get_balance(user_id):
    with db() as cur:
        cur.execute(
            """
            SELECT type, COALESCE(SUM(amount), 0) AS total, COUNT(*) AS cnt
            FROM transactions WHERE user_id = %s GROUP BY type;
            """,
            (user_id,),
        )
        totals = {r["type"]: r for r in cur.fetchall()}
        cur.execute(
            "SELECT MIN(transaction_date) AS d, MAX(transaction_date) AS d2 "
            "FROM transactions WHERE user_id = %s",
            (user_id,),
        )
        span = cur.fetchone()

    income = float(totals.get("income", {}).get("total", 0))
    expense = float(totals.get("expense", {}).get("total", 0))
    income_cnt = int(totals.get("income", {}).get("cnt", 0) or 0)
    expense_cnt = int(totals.get("expense", {}).get("cnt", 0) or 0)
    return {
        "income": income, "expense": expense, "balance": income - expense,
        "income_cnt": income_cnt, "expense_cnt": expense_cnt,
        "count": income_cnt + expense_cnt,
        "first": span["d"], "last": span["d2"],
    }


def list_transactions(user_id, page=0, per_page=TX_PER_PAGE):
    offset = page * per_page
    with db() as cur:
        cur.execute("SELECT COUNT(*) AS n FROM transactions WHERE user_id = %s", (user_id,))
        total = cur.fetchone()["n"]
        cur.execute(
            """
            SELECT id, type, amount, description, category, transaction_date
            FROM transactions WHERE user_id = %s
            ORDER BY transaction_date DESC, id DESC
            LIMIT %s OFFSET %s;
            """,
            (user_id, per_page, offset),
        )
        rows = cur.fetchall()
    return rows, total


def first_transaction_date(user_id):
    with db() as cur:
        cur.execute(
            "SELECT MIN(transaction_date) AS d FROM transactions WHERE user_id = %s",
            (user_id,),
        )
        return cur.fetchone()["d"]

# ============================================================
# PARSING
# ============================================================

AMOUNT_RE = re.compile(
    r"(\d{1,3}(?:[ \u00a0]\d{3})+(?:[.,]\d+)?|\d+(?:[.,]\d+)?)\s*"
    r"(миллион\w*|million|млн|тыс\w*|мың|к|k|m)?(?=\s|$|[^\w])",
    re.IGNORECASE,
)

DATE_WORDS = [
    (re.compile(r"\b(?:позавчера|day before yesterday)\b", re.IGNORECASE), 2),
    (re.compile(r"\b(?:вчера|yesterday|кеше)\b", re.IGNORECASE), 1),
    (re.compile(r"\b(?:сегодня|today|бүгін)\b", re.IGNORECASE), 0),
]

NOISE_WORDS = re.compile(r"\b(?:расход|доход|expense|income|шығыс|кіріс)\b", re.IGNORECASE)


def _to_float(s):
    try:
        return float(s.replace(" ", "").replace("\u00a0", "").replace(",", "."))
    except ValueError:
        return None


def parse_entry(text):
    matches = list(AMOUNT_RE.finditer(text))
    if not matches:
        return None

    cands = [m for m in matches if not (_to_float(m.group(1)) is not None
                                        and 1900 <= _to_float(m.group(1)) <= 2100)]
    m = (cands or matches)[-1]
    amount = _to_float(m.group(1))
    if amount is None:
        return None

    suffix = (m.group(2) or "").lower()
    if suffix:
        big = suffix.startswith(("миллион", "million", "млн", "m"))
        amount *= 1_000_000 if big else 1000
    if amount <= 0:
        return None

    rest = text[:m.start()] + " " + text[m.end():]
    tx_date = datetime.now(TZ).date()
    for pattern, delta in DATE_WORDS:
        if pattern.search(rest):
            rest = pattern.sub(" ", rest)
            tx_date = tx_date - timedelta(days=delta)
            break

    rest = NOISE_WORDS.sub(" ", rest)
    description = " ".join(rest.split())
    return amount, description, tx_date.isoformat()

# ============================================================
# HELPERS
# ============================================================

def money(val):
    val = float(val)
    text = f"{int(val):,}" if val.is_integer() else f"{val:,.2f}"
    return text.replace(",", " ") + " ₸"


MONTHS = {
    "ru": ["Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
           "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"],
    "en": ["January", "February", "March", "April", "May", "June",
           "July", "August", "September", "October", "November", "December"],
    "kk": ["Қаңтар", "Ақпан", "Наурыз", "Сәуір", "Мамыр", "Маусым",
           "Шілде", "Тамыз", "Қыркүйек", "Қазан", "Қараша", "Желтоқсан"],
}

EXTRA = {
    "ru": {"day": "День", "week": "Неделя", "month": "Месяц", "year": "Год",
           "no_data": "Данных за этот период нет. Первая операция: {d}.",
           "no_tx": "Операций пока нет. Добавь первую кнопкой ➖ Расход или ➕ Доход."},
    "en": {"day": "Day", "week": "Week", "month": "Month", "year": "Year",
           "no_data": "No data for this period. First transaction: {d}.",
           "no_tx": "No transactions yet. Add the first one with ➖ Expense or ➕ Income."},
    "kk": {"day": "Күн", "week": "Апта", "month": "Ай", "year": "Жыл",
           "no_data": "Бұл кезеңде дерек жоқ. Бірінші операция: {d}.",
           "no_tx": "Әзірге операция жоқ. Алғашқысын ➖ Шығыс немесе ➕ Кіріс батырмасымен қос."},
}


def monday_of(d):
    return d - timedelta(days=d.weekday())


def period_bounds(period, offset=0, today=None):
    today = today or datetime.now(TZ).date()

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


def min_offset(period, first, today=None):
    today = today or datetime.now(TZ).date()
    if period == "day":
        off = (first - today).days
    elif period == "week":
        off = (monday_of(first) - monday_of(today)).days // 7
    elif period == "month":
        off = (first.year * 12 + first.month) - (today.year * 12 + today.month)
    else:
        off = first.year - today.year
    return min(off, 0)


def period_title(lang, period, offset, start):
    t = T[lang]
    if offset == 0:
        tag = t["titles"][(period, False)]
    elif offset == -1:
        tag = t["titles"][(period, True)]
    else:
        tag = None

    if period == "day":
        return f"{tag} — {start:%d.%m.%Y}" if tag else f"{start:%d.%m.%Y}"
    if period == "week":
        return tag or EXTRA[lang]["week"]
    name = f"{MONTHS[lang][start.month - 1]} {start.year}" if period == "month" else str(start.year)
    return f"{tag} — {name}" if tag else name


def short_label(lang, period, start, end):
    if period == "day":
        return f"{start:%d.%m}"
    if period == "week":
        return f"{start:%d.%m}–{end:%d.%m}"
    if period == "month":
        return f"{MONTHS[lang][start.month - 1]} {start.year}"
    return str(start.year)


def format_report(lang, period, offset, start, end, rep):
    t = T[lang]
    if period == "day":
        header = f"📊 {period_title(lang, period, offset, start)}"
    else:
        header = (f"📊 {period_title(lang, period, offset, start)} "
                  f"({start:%d.%m.%Y} — {end:%d.%m.%Y})")
    lines = [
        header,
        "",
        f"➕ {t['income']}: {money(rep['income'])}",
        f"➖ {t['expense']}: {money(rep['expense'])}",
        f"💼 {t['balance']}: {money(rep['balance'])}",
        f"🧾 {t['count']}: {rep['count']}",
    ]
    if rep["top"]:
        lines += ["", t["top"]]
        lines += [f
