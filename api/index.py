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
            "📅 День / 📊 Неделя / Месяц / Год — отчёты, листай ◀️ ▶️.\n"
            "🧾 Транзакции — список операций, там же удаление.\n"
            "💼 Баланс — итог за всё время и очистка истории.\n"
            "🌐 Язык — сменить язык\n\n"
            "Если кнопки пропали или устарели — команда /menu."
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
            "📅 Day / 📊 Week / Month / Year — reports, browse with ◀️ ▶️.\n"
            "🧾 Transactions — list with delete.\n"
            "💼 Balance — all-time totals and history cleanup.\n"
            "🌐 Language — change language\n\n"
            "If the buttons are missing or outdated — use /menu."
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
            "📅 Күн / 📊 Апта / Ай / Жыл — есептер, ◀️ ▶️ арқылы ауыстыр.\n"
            "🧾 Транзакциялар — тізім және жою.\n"
            "💼 Баланс — жалпы қорытынды және тарихты тазалау.\n"
            "🌐 Тіл —
