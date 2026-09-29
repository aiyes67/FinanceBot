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
        lines += [f"• {cat_label(lang, r['category'])}: {money(r['total'])}" for r in rep["top"]]
    return "\n".join(lines)


def report_view(user_id, lang, period, offset):
    first = first_transaction_date(user_id)
    min_off = min_offset(period, first) if first else 0
    if offset < min_off or offset > 0:
        return None
    start, end = period_bounds(period, offset)
    rep = get_report(user_id, start, end)
    return (format_report(lang, period, offset, start, end, rep),
            report_keyboard(lang, period, offset, min_off))


def send_report(chat_id, user_id, lang, period, offset=0):
    view = report_view(user_id, lang, period, offset)
    if view:
        send_message(chat_id, view[0], reply_markup=view[1])
        return
    first = first_transaction_date(user_id)
    extra = EXTRA[lang]
    send_message(chat_id,
                 extra["no_data"].format(d=f"{first:%d.%m.%Y}") if first else extra["no_tx"])


def send_transactions_list(chat_id, user_id, lang, page=0):
    t = T[lang]
    rows, total = list_transactions(user_id, page)
    if total == 0:
        send_message(chat_id, t["tx_empty"])
        return
    total_pages = max(1, (total + TX_PER_PAGE - 1) // TX_PER_PAGE)
    if page >= total_pages:
        page = total_pages - 1
        rows, total = list_transactions(user_id, page)
    text = f"{t['tx_title']}\n{t['tx_page'].format(n=page + 1, total=total_pages)}"
    send_message(chat_id, text,
                 reply_markup=transactions_keyboard(lang, rows, page, total_pages))


def send_balance(chat_id, user_id, lang):
    t = T[lang]
    b = get_balance(user_id)
    if b["count"] == 0:
        send_message(chat_id, t["tx_empty"])
        return
    lines = [
        t["balance_title"],
        "",
        f"➕ {t['income']}: {money(b['income'])}  ({b['income_cnt']})",
        f"➖ {t['expense']}: {money(b['expense'])}  ({b['expense_cnt']})",
        f"💼 {t['balance']}: {money(b['balance'])}",
        f"🧾 {t['count']}: {b['count']}",
        "",
        f"{t['first_tx']}: {b['first']:%d.%m.%Y}",
        f"{t['last_tx']}: {b['last']:%d.%m.%Y}",
    ]
    send_message(chat_id, "\n".join(lines), reply_markup=balance_keyboard(lang))


def send_delete_confirm(chat_id, user_id, lang, tx_id, message_id=None):
    t = T[lang]
    rows, _ = list_transactions(user_id, 0)
    target = None
    with db() as cur:
        cur.execute(
            "SELECT id, type, amount, description, transaction_date "
            "FROM transactions WHERE id = %s AND user_id = %s",
            (tx_id, user_id),
        )
        target = cur.fetchone()
    if not target:
        if message_id:
            try:
                tg("editMessageText", {"chat_id": chat_id, "message_id": message_id,
                                       "text": t["tx_empty"]})
            except Exception:
                pass
        return
    icon = "➖" if target["type"] == "expense" else "➕"
    line = f"{icon} {money(target['amount'])} — {target['description'] or ''} ({target['transaction_date']:%d.%m})"
    text = f"{t['del_confirm']}\n\n{line}"
    if message_id:
        try:
            tg("editMessageText", {"chat_id": chat_id, "message_id": message_id,
                                   "text": text,
                                   "reply_markup": delete_confirm_keyboard(lang, tx_id)})
            return
        except Exception:
            pass
    send_message(chat_id, text, reply_markup=delete_confirm_keyboard(lang, tx_id))


def send_clear_menu(chat_id, lang, message_id=None):
    t = T[lang]
    text = t["clear_choose"]
    kb = clear_menu_keyboard(lang)
    if message_id:
        try:
            tg("editMessageText", {"chat_id": chat_id, "message_id": message_id,
                                   "text": text, "reply_markup": kb})
            return
        except Exception:
            pass
    send_message(chat_id, text, reply_markup=kb)


def send_clear_confirm(chat_id, lang, mode, message_id=None):
    t = T[lang]
    what = {"expense": t["clear_expenses_what"],
            "income": t["clear_incomes_what"],
            "all": t["clear_all_what"]}[mode]
    text = t["clear_confirm"].format(what=what)
    kb = clear_confirm_keyboard(lang, mode)
    if message_id:
        try:
            tg("editMessageText", {"chat_id": chat_id, "message_id": message_id,
                                   "text": text, "reply_markup": kb})
            return
        except Exception:
            pass
    send_message(chat_id, text, reply_markup=kb)


# ============================================================
# ACTIONS
# ============================================================

def is_allowed(user_id):
    return OWNER_ID == 0 or user_id == OWNER_ID


def run_action(action, chat_id, user_id, lang):
    t = T[lang]

    if action in ("add_expense", "add_income"):
        set_state(user_id, action)
        send_message(chat_id, t[f"prompt_{action}"])

    elif action == "lang":
        set_state(user_id, None)
        keyboard = {"inline_keyboard": [[
            {"text": name, "callback_data": f"lang:{code}"} for code, name in LANGS.items()
        ]]}
        send_message(chat_id, t["lang_prompt"], reply_markup=keyboard)

    elif action in REPORT_PERIODS:
        set_state(user_id, None)
        send_report(chat_id, user_id, lang, action, 0)

    elif action == "yesterday":
        set_state(user_id, None)
        send_report(chat_id, user_id, lang, "day", -1)

    elif action in ("lastweek", "lastmonth", "lastyear"):
        set_state(user_id, None)
        send_report(chat_id, user_id, lang, action[4:], -1)

    elif action == "transactions":
        set_state(user_id, None)
        send_transactions_list(chat_id, user_id, lang, 0)

    elif action == "balance":
        set_state(user_id, None)
        send_balance(chat_id, user_id, lang)


# ============================================================
# UPDATE PROCESSOR
# ============================================================

def process_callback(cb):
    user_id = cb["from"]["id"]
    chat_id = cb["message"]["chat"]["id"]
    message_id = cb["message"]["message_id"]
    data = cb.get("data", "")
    stored_lang, _ = get_user(user_id)
    lang = stored_lang if stored_lang in LANGS else "ru"

    if not is_allowed(user_id):
        tg("answerCallbackQuery", {"callback_query_id": cb["id"]})
        return

    if data == "noop":
        tg("answerCallbackQuery", {"callback_query_id": cb["id"]})
        return

    if data.startswith("lang:") and data[5:] in LANGS:
        lang = data[5:]
        set_lang(user_id, lang)
        tg("answerCallbackQuery", {"callback_query_id": cb["id"]})
        tg("editMessageReplyMarkup", {"chat_id": chat_id, "message_id": message_id,
                                      "reply_markup": {"inline_keyboard": []}})
        send_message(chat_id, T[lang]["lang_set"] + "\n\n" + T[lang]["help"],
                     reply_markup=menu_markup(lang))

    elif data.startswith("cat:"):
        _, tx_id, key = data.split(":", 2)
        set_category(user_id, int(tx_id), key)
        tg("answerCallbackQuery", {"callback_query_id": cb["id"],
                                   "text": "✅ " + cat_label(lang, key)})
        tg("editMessageReplyMarkup", {"chat_id": chat_id, "message_id": message_id,
                                      "reply_markup": {"inline_keyboard": []}})

    elif data.startswith("rep:"):
        tg("answerCallbackQuery", {"callback_query_id": cb["id"]})
        try:
            _, period, off = data.split(":")
            offset = int(off)
        except ValueError:
            return
        if period not in REPORT_PERIODS:
            return
        view = report_view(user_id, lang, period, offset)
        if view:
            try:
                tg("editMessageText", {"chat_id": chat_id, "message_id": message_id,
                                       "text": view[0], "reply_markup": view[1]})
            except Exception:
                pass

    elif data.startswith("txp:"):
        tg("answerCallbackQuery", {"callback_query_id": cb["id"]})
        try:
            page = int(data[4:])
        except ValueError:
            return
        rows, total = list_transactions(user_id, page)
        if total == 0:
            return
        total_pages = max(1, (total + TX_PER_PAGE - 1) // TX_PER_PAGE)
        if page >= total_pages:
            page = total_pages - 1
            rows, total = list_transactions(user_id, page)
        text = f"{T[lang]['tx_title']}\n{T[lang]['tx_page'].format(n=page + 1, total=total_pages)}"
        try:
            tg("editMessageText", {"chat_id": chat_id, "message_id": message_id,
                                   "text": text,
                                   "reply_markup": transactions_keyboard(lang, rows, page, total_pages)})
        except Exception:
            pass

    elif data.startswith("delok:"):
        try:
            tx_id = int(data[6:])
        except ValueError:
            tg("answerCallbackQuery", {"callback_query_id": cb["id"]})
            return
        ok = delete_transaction(user_id, tx_id)
        tg("answerCallbackQuery", {"callback_query_id": cb["id"],
                                   "text": T[lang]["tx_deleted"] if ok else "—"})
        rows, total = list_transactions(user_id, 0)
        if total == 0:
            try:
                tg("editMessageText", {"chat_id": chat_id, "message_id": message_id,
                                       "text": T[lang]["tx_empty"]})
            except Exception:
                pass
            return
        total_pages = max(1, (total + TX_PER_PAGE - 1) // TX_PER_PAGE)
        text = f"{T[lang]['tx_title']}\n{T[lang]['tx_page'].format(n=1, total=total_pages)}"
        try:
            tg("editMessageText", {"chat_id": chat_id, "message_id": message_id,
                                   "text": text,
                                   "reply_markup": transactions_keyboard(lang, rows, 0, total_pages)})
        except Exception:
            pass

    elif data.startswith("del:"):
        tg("answerCallbackQuery", {"callback_query_id": cb["id"]})
        try:
            tx_id = int(data[4:])
        except ValueError:
            return
        send_delete_confirm(chat_id, user_id, lang, tx_id, message_id)

    elif data == "delno":
        tg("answerCallbackQuery", {"callback_query_id": cb["id"]})
        rows, total = list_transactions(user_id, 0)
        if total == 0:
            try:
                tg("editMessageText", {"chat_id": chat_id, "message_id": message_id,
                                       "text": T[lang]["tx_empty"]})
            except Exception:
                pass
            return
        total_pages = max(1, (total + TX_PER_PAGE - 1) // TX_PER_PAGE)
        text = f"{T[lang]['tx_title']}\n{T[lang]['tx_page'].format(n=1, total=total_pages)}"
        try:
            tg("editMessageText", {"chat_id": chat_id, "message_id": message_id,
                                   "text": text,
                                   "reply_markup": transactions_keyboard(lang, rows, 0, total_pages)})
        except Exception:
            pass

    elif data == "clear:menu":
        tg("answerCallbackQuery", {"callback_query_id": cb["id"]})
        send_clear_menu(chat_id, lang, message_id)

    elif data in ("clear:expense", "clear:income", "clear:all"):
        tg("answerCallbackQuery", {"callback_query_id": cb["id"]})
        mode = data.split(":")[1]
        send_clear_confirm(chat_id, lang, mode, message_id)

    elif data == "clear:cancel":
        tg("answerCallbackQuery", {"callback_query_id": cb["id"]})
        try:
            tg("editMessageReplyMarkup", {"chat_id": chat_id, "message_id": message_id,
                                          "reply_markup": {"inline_keyboard": []}})
        except Exception:
            pass
        send_balance(chat_id, user_id, lang)

    elif data.startswith("clearok:"):
        mode = data.split(":", 1)[1]
        tg("answerCallbackQuery", {"callback_query_id": cb["id"]})
        n = clear_transactions(user_id, mode)
        try:
            tg("editMessageReplyMarkup", {"chat_id": chat_id, "message_id": message_id,
                                          "reply_markup": {"inline_keyboard": []}})
        except Exception:
            pass
        send_message(chat_id, T[lang]["clear_done"].format(n=n))
        send_balance(chat_id, user_id, lang)

    else:
        tg("answerCallbackQuery", {"callback_query_id": cb["id"]})


def process_message(message):
    if not message.get("text"):
        return

    chat_id = message["chat"]["id"]
    user_id = message["from"]["id"]
    text = message["text"].strip()
    if not text:
        return

    stored_lang, state = get_user(user_id)
    if stored_lang in LANGS:
        lang = stored_lang
    else:
        lang = {"kk": "kk", "en": "en"}.get(
            (message["from"].get("language_code") or "")[:2], "ru")
    t = T[lang]

    if not is_allowed(user_id):
        send_message(chat_id, t["denied"])
        return

    first = text.split()[0].split("@")[0].lower()

    if first in ("/start", "/help"):
        set_state(user_id, None)
        send_message(chat_id, t["help"], reply_markup=menu_markup(lang))
        return

    action = LABEL_TO_ACTION.get(text) or COMMANDS.get(first)
    if action:
        run_action(action, chat_id, user_id, lang)
        return

    if state in ("add_expense", "add_income"):
        entry = parse_entry(text)
        if not entry:
            send_message(chat_id, t["no_amount"])
            return
        amount, description, tx_date = entry
        tx_type = "expense" if state == "add_expense" else "income"
        tx_id = add_transaction(user_id, tx_type, amount, description, tx_date)
        set_state(user_id, None)
        sign = "-" if tx_type == "expense" else "+"
        lines = [t["saved"], f"{sign}{money(amount)}"]
        if description:
            lines.append(description)
        lines += ["", t["cat_prompt"]]
        send_message(chat_id, "\n".join(lines),
                     reply_markup=category_keyboard(state, tx_id, lang))
        return

    return


def process_update(update):
    if update.get("callback_query"):
        process_callback(update["callback_query"])
    elif update.get("message"):
        process_message(update["message"])


# ============================================================
# VERCEL HANDLER (функция, а не класс)
# ============================================================

def _read_body(req):
    try:
        length = int(req.headers.get("content-length", 0) or 0)
        if length <= 0:
            return b""
        return req.rfile.read(length)
    except Exception:
        return b""


def _json_response(obj, status=200):
    return status, {"Content-Type": "application/json"}, json.dumps(obj).encode("utf-8")


def _text_response(text, status=200):
    return status, {"Content-Type": "text/plain; charset=utf-8"}, text.encode("utf-8")


def handler(req):
    """Точка входа для Vercel Python runtime: handler(request) -> (status, headers, body)."""
    try:
        method = req.method
        headers = req.headers

        # --- POST: Telegram webhook ---
        if method == "POST":
            if WEBHOOK_SECRET and headers.get("X-Telegram-Bot-Api-Secret-Token") != WEBHOOK_SECRET:
                return _json_response({"ok": False, "error": "forbidden"}, 403)

            update = {}
            try:
                raw = _read_body(req)
                update = json.loads(raw.decode("utf-8")) if raw else {}
                process_update(update)
            except Exception as e:
                print("Error:", repr(e))
                try:
                    src = update.get("message") or update.get("callback_query") or {}
                    chat_id = (src.get("chat") or {}).get("id")
                    user_id = (src.get("from") or {}).get("id")
                    if chat_id and user_id:
                        l, _ = get_user(user_id)
                        send_message(chat_id, T[l if l in LANGS else "ru"]["error"])
                except Exception as e2:
                    print("Error handler failed:", repr(e2))

            return _json_response({"ok": True})

        # --- GET: диагностика ---
        lines = ["Bot is alive!"]
        missing = [n for n in ("TELEGRAM_TOKEN", "DATABASE_URL") if not os.environ.get(n)]
        if missing:
            lines.append("Missing env vars: " + ", ".join(missing))
        else:
            try:
                with db() as cur:
                    cur.execute(
                        "SELECT to_regclass('public.transactions') AS a, "
                        "to_regclass('public.user_settings') AS b, "
                        "to_regclass('public.user_state') AS c"
                    )
                    row = cur.fetchone()
                lines.append("Table transactions: " + ("OK" if row["a"] else "MISSING"))
                lines.append("Table user_settings: " + ("OK" if row["b"] else "MISSING"))
                lines.append("Table user_state: " + ("OK" if row["c"] else "MISSING"))
            except Exception as e:
                lines.append("Database error: " + type(e).__name__ + " — " + str(e)[:200])

        path = getattr(req, "path", "/") or "/"
        key = parse_qs(urlparse(path).query).get("key", [""])[0]
        if not missing and (not WEBHOOK_SECRET or key == WEBHOOK_SECRET):
            try:
                url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getMe"
                data = json.loads(urllib.request.urlopen(url, timeout=10).read())["result"]
                lines.append("Telegram token: OK, bot @" + str(data.get("username")))
            except Exception as e:
                lines.append("Telegram getMe error: " + type(e).__name__)
            try:
                url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getWebhookInfo"
                data = json.loads(urllib.request.urlopen(url, timeout=10).read())["result"]
                lines.append("Webhook url: " + (data.get("url") or "NOT SET"))
                lines.append("Webhook pending: " + str(data.get("pending_update_count")))
                lines.append("Webhook last error: " + str(data.get("last_error_message") or "none"))
            except Exception as e:
                lines.append("Telegram getWebhookInfo error: " + type(e).__name__)

        return _text_response("\n".join(lines))

    except Exception as e:
        print("Top-level handler error:", repr(e))
        return _json_response({"ok": False, "error": type(e).__name__}, 500)
