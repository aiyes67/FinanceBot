import os
import re
import json
import urllib.request
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
    OWNER_ID = int(os.environ.get("OWNER_ID") or "0")      # 0 = Ð±Ð¾Ñ‚ Ð´Ð»Ñ Ð²ÑÐµÑ…
except ValueError:
    OWNER_ID = 0
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "")      # Ð½ÐµÐ¾Ð±ÑÐ·Ð°Ñ‚ÐµÐ»ÑŒÐ½Ð¾

try:
    TZ = ZoneInfo("Asia/Almaty")
except Exception:
    TZ = timezone(timedelta(hours=5))  # UTC+5, ÐµÑÐ»Ð¸ Ð² ÑÐ¸ÑÑ‚ÐµÐ¼Ðµ Ð½ÐµÑ‚ Ð±Ð°Ð·Ñ‹ Ñ‡Ð°ÑÐ¾Ð²Ñ‹Ñ… Ð¿Ð¾ÑÑÐ¾Ð²

LANGS = {"ru": "Ð ÑƒÑÑÐºÐ¸Ð¹", "en": "English", "kk": "ÒšÐ°Ð·Ð°Ò›ÑˆÐ°"}

# ============================================================
# TRANSLATIONS
# ============================================================

T = {
    "ru": {
        "help": (
            "ðŸ’° Ð¤Ð¸Ð½Ð°Ð½ÑÐ¾Ð²Ñ‹Ð¹ Ð¿Ð¾Ð¼Ð¾Ñ‰Ð½Ð¸Ðº\n\n"
            "ÐÐ°Ð¶Ð¼Ð¸ âž– Ð Ð°ÑÑ…Ð¾Ð´ Ð¸Ð»Ð¸ âž• Ð”Ð¾Ñ…Ð¾Ð´, Ð¿Ð¾Ñ‚Ð¾Ð¼ Ð½Ð°Ð¿Ð¸ÑˆÐ¸ ÑÑƒÐ¼Ð¼Ñƒ Ð¸ Ð¾Ð¿Ð¸ÑÐ°Ð½Ð¸Ðµ, Ð½Ð°Ð¿Ñ€Ð¸Ð¼ÐµÑ€: ÐºÐ¾Ñ„Ðµ 1500.\n"
            "Ð¡Ð»Ð¾Ð²Ð° Â«Ð²Ñ‡ÐµÑ€Ð°Â» Ð¸ Â«Ð¿Ð¾Ð·Ð°Ð²Ñ‡ÐµÑ€Ð°Â» Ñ‚Ð¾Ð¶Ðµ Ð¿Ð¾Ð½Ð¸Ð¼Ð°ÑŽ.\n\n"
            "ðŸ“Š ÐÐµÐ´ÐµÐ»Ñ / ÐœÐµÑÑÑ† / Ð“Ð¾Ð´ â€” Ð¾Ñ‚Ñ‡Ñ‘Ñ‚Ñ‹. ÐŸÑ€Ð¾ÑˆÐ»Ñ‹Ðµ Ð¿ÐµÑ€Ð¸Ð¾Ð´Ñ‹: /lastweek /lastmonth /lastyear\n"
            "ðŸŒ Ð¯Ð·Ñ‹Ðº â€” ÑÐ¼ÐµÐ½Ð¸Ñ‚ÑŒ ÑÐ·Ñ‹Ðº"
        ),
        "menu": {
            "add_expense": "âž– Ð Ð°ÑÑ…Ð¾Ð´", "add_income": "âž• Ð”Ð¾Ñ…Ð¾Ð´",
            "week": "ðŸ“Š ÐÐµÐ´ÐµÐ»Ñ", "month": "ðŸ“Š ÐœÐµÑÑÑ†", "year": "ðŸ“Š Ð“Ð¾Ð´",
            "lang": "ðŸŒ Ð¯Ð·Ñ‹Ðº",
        },
        "prompt_add_expense": "ÐÐ°Ð¿Ð¸ÑˆÐ¸ ÑÑƒÐ¼Ð¼Ñƒ Ð¸ Ð¾Ð¿Ð¸ÑÐ°Ð½Ð¸Ðµ Ñ€Ð°ÑÑ…Ð¾Ð´Ð°, Ð½Ð°Ð¿Ñ€Ð¸Ð¼ÐµÑ€: ÐºÐ¾Ñ„Ðµ 1500",
        "prompt_add_income": "ÐÐ°Ð¿Ð¸ÑˆÐ¸ ÑÑƒÐ¼Ð¼Ñƒ Ð¸ Ð¾Ð¿Ð¸ÑÐ°Ð½Ð¸Ðµ Ð´Ð¾Ñ…Ð¾Ð´Ð°, Ð½Ð°Ð¿Ñ€Ð¸Ð¼ÐµÑ€: Ð·Ð°Ñ€Ð¿Ð»Ð°Ñ‚Ð° 400000",
        "no_amount": "ÐÐµ Ð²Ð¸Ð¶Ñƒ ÑÑƒÐ¼Ð¼Ñƒ. ÐÐ°Ð¿Ð¸ÑˆÐ¸, Ð½Ð°Ð¿Ñ€Ð¸Ð¼ÐµÑ€: ÐºÐ¾Ñ„Ðµ 1500",
        "saved": "âœ… Ð—Ð°Ð¿Ð¸ÑÐ°Ð½Ð¾:",
        "cat_prompt": "ÐšÐ°Ñ‚ÐµÐ³Ð¾Ñ€Ð¸Ñ (Ð¿Ð¾ Ð¶ÐµÐ»Ð°Ð½Ð¸ÑŽ):",
        "denied": "Ð”Ð¾ÑÑ‚ÑƒÐ¿ Ð·Ð°ÐºÑ€Ñ‹Ñ‚.",
        "error": "ÐŸÑ€Ð¾Ð¸Ð·Ð¾ÑˆÐ»Ð° Ð¾ÑˆÐ¸Ð±ÐºÐ° Ð¿Ñ€Ð¸ Ð¾Ð±Ñ€Ð°Ð±Ð¾Ñ‚ÐºÐµ.",
        "lang_prompt": "Ð’Ñ‹Ð±ÐµÑ€Ð¸ ÑÐ·Ñ‹Ðº:",
        "lang_set": "Ð¯Ð·Ñ‹Ðº: Ð ÑƒÑÑÐºÐ¸Ð¹",
        "income": "Ð”Ð¾Ñ…Ð¾Ð´Ñ‹", "expense": "Ð Ð°ÑÑ…Ð¾Ð´Ñ‹", "balance": "Ð‘Ð°Ð»Ð°Ð½Ñ", "count": "ÐžÐ¿ÐµÑ€Ð°Ñ†Ð¸Ð¹",
        "top": "Ð¢Ð¾Ð¿ Ñ€Ð°ÑÑ…Ð¾Ð´Ð¾Ð² Ð¿Ð¾ ÐºÐ°Ñ‚ÐµÐ³Ð¾Ñ€Ð¸ÑÐ¼:", "no_category": "Ð‘ÐµÐ· ÐºÐ°Ñ‚ÐµÐ³Ð¾Ñ€Ð¸Ð¸",
        "cats": {"food": "Ð•Ð´Ð°", "transport": "Ð¢Ñ€Ð°Ð½ÑÐ¿Ð¾Ñ€Ñ‚", "home": "Ð–Ð¸Ð»ÑŒÑ‘", "shopping": "ÐŸÐ¾ÐºÑƒÐ¿ÐºÐ¸",
                 "health": "Ð—Ð´Ð¾Ñ€Ð¾Ð²ÑŒÐµ", "fun": "Ð”Ð¾ÑÑƒÐ³", "other": "Ð”Ñ€ÑƒÐ³Ð¾Ðµ",
                 "salary": "Ð—Ð°Ñ€Ð¿Ð»Ð°Ñ‚Ð°", "business": "Ð‘Ð¸Ð·Ð½ÐµÑ"},
        "titles": {
            ("week", False): "Ð¢ÐµÐºÑƒÑ‰Ð°Ñ Ð½ÐµÐ´ÐµÐ»Ñ", ("week", True): "ÐŸÑ€Ð¾ÑˆÐ»Ð°Ñ Ð½ÐµÐ´ÐµÐ»Ñ",
            ("month", False): "Ð¢ÐµÐºÑƒÑ‰Ð¸Ð¹ Ð¼ÐµÑÑÑ†", ("month", True): "ÐŸÑ€Ð¾ÑˆÐ»Ñ‹Ð¹ Ð¼ÐµÑÑÑ†",
            ("year", False): "Ð¢ÐµÐºÑƒÑ‰Ð¸Ð¹ Ð³Ð¾Ð´", ("year", True): "ÐŸÑ€Ð¾ÑˆÐ»Ñ‹Ð¹ Ð³Ð¾Ð´",
        },
    },
    "en": {
        "help": (
            "ðŸ’° Finance assistant\n\n"
            "Tap âž– Expense or âž• Income, then type the amount and a description, e.g.: coffee 1500.\n"
            "I also understand \"yesterday\".\n\n"
            "ðŸ“Š Week / Month / Year â€” reports. Past periods: /lastweek /lastmonth /lastyear\n"
            "ðŸŒ Language â€” change language"
        ),
        "menu": {
            "add_expense": "âž– Expense", "add_income": "âž• Income",
            "week": "ðŸ“Š Week", "month": "ðŸ“Š Month", "year": "ðŸ“Š Year",
            "lang": "ðŸŒ Language",
        },
        "prompt_add_expense": "Type the amount and a description of the expense, e.g.: coffee 1500",
        "prompt_add_income": "Type the amount and a description of the income, e.g.: salary 400000",
        "no_amount": "I can't see an amount. Try: coffee 1500",
        "saved": "âœ… Saved:",
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
            ("week", False): "This week", ("week", True): "Last week",
            ("month", False): "This month", ("month", True): "Last month",
            ("year", False): "This year", ("year", True): "Last year",
        },
    },
    "kk": {
        "help": (
            "ðŸ’° ÒšÐ°Ñ€Ð¶Ñ‹Ð»Ñ‹Ò› ÐºÓ©Ð¼ÐµÐºÑˆÑ–\n\n"
            "âž– Ð¨Ñ‹Ò“Ñ‹Ñ Ð½ÐµÐ¼ÐµÑÐµ âž• ÐšÑ–Ñ€Ñ–Ñ Ð±Ð°Ñ‚Ñ‹Ñ€Ð¼Ð°ÑÑ‹Ð½ Ð±Ð°ÑÑ‹Ð¿, ÑÐ¾Ð¼Ð°Ð½Ñ‹ Ð¶Ó™Ð½Ðµ ÑÐ¸Ð¿Ð°Ñ‚Ñ‚Ð°Ð¼Ð°Ð½Ñ‹ Ð¶Ð°Ð·, Ð¼Ñ‹ÑÐ°Ð»Ñ‹: ÐºÐ¾Ñ„Ðµ 1500.\n"
            "Â«ÐšÐµÑˆÐµÂ» Ð´ÐµÐ³ÐµÐ½ ÑÓ©Ð·Ð´Ñ– Ð´Ðµ Ñ‚Ò¯ÑÑ–Ð½ÐµÐ¼Ñ–Ð½.\n\n"
            "ðŸ“Š ÐÐ¿Ñ‚Ð° / ÐÐ¹ / Ð–Ñ‹Ð» â€” ÐµÑÐµÐ¿Ñ‚ÐµÑ€. Ó¨Ñ‚ÐºÐµÐ½ ÐºÐµÐ·ÐµÒ£Ð´ÐµÑ€: /lastweek /lastmonth /lastyear\n"
            "ðŸŒ Ð¢Ñ–Ð» â€” Ñ‚Ñ–Ð»Ð´Ñ– Ð°ÑƒÑ‹ÑÑ‚Ñ‹Ñ€Ñƒ"
        ),
        "menu": {
            "add_expense": "âž– Ð¨Ñ‹Ò“Ñ‹Ñ", "add_income": "âž• ÐšÑ–Ñ€Ñ–Ñ",
            "week": "ðŸ“Š ÐÐ¿Ñ‚Ð°", "month": "ðŸ“Š ÐÐ¹", "year": "ðŸ“Š Ð–Ñ‹Ð»",
            "lang": "ðŸŒ Ð¢Ñ–Ð»",
        },
        "prompt_add_expense": "Ð¨Ñ‹Ò“Ñ‹ÑÑ‚Ñ‹Ò£ ÑÐ¾Ð¼Ð°ÑÑ‹Ð½ Ð¶Ó™Ð½Ðµ ÑÐ¸Ð¿Ð°Ñ‚Ñ‚Ð°Ð¼Ð°ÑÑ‹Ð½ Ð¶Ð°Ð·, Ð¼Ñ‹ÑÐ°Ð»Ñ‹: ÐºÐ¾Ñ„Ðµ 1500",
        "prompt_add_income": "ÐšÑ–Ñ€Ñ–ÑÑ‚Ñ–Ò£ ÑÐ¾Ð¼Ð°ÑÑ‹Ð½ Ð¶Ó™Ð½Ðµ ÑÐ¸Ð¿Ð°Ñ‚Ñ‚Ð°Ð¼Ð°ÑÑ‹Ð½ Ð¶Ð°Ð·, Ð¼Ñ‹ÑÐ°Ð»Ñ‹: Ð¶Ð°Ð»Ð°Ò›Ñ‹ 400000",
        "no_amount": "Ð¡Ð¾Ð¼Ð°Ð½Ñ‹ ÐºÓ©Ñ€Ð¼ÐµÐ´Ñ–Ð¼. ÐœÑ‹ÑÐ°Ð»Ñ‹: ÐºÐ¾Ñ„Ðµ 1500",
        "saved": "âœ… Ð–Ð°Ð·Ñ‹Ð»Ð´Ñ‹:",
        "cat_prompt": "Ð¡Ð°Ð½Ð°Ñ‚ (Ò›Ð°Ð»Ð°ÑƒÑ‹Ò£ÑˆÐ°):",
        "denied": "ÒšÐ¾Ð»Ð¶ÐµÑ‚Ñ–Ð¼Ð´Ñ–Ð»Ñ–Ðº Ð¶Ð°Ð±Ñ‹Ò›.",
        "error": "Ó¨Ò£Ð´ÐµÑƒ ÐºÐµÐ·Ñ–Ð½Ð´Ðµ Ò›Ð°Ñ‚Ðµ ÑˆÑ‹Ò›Ñ‚Ñ‹.",
        "lang_prompt": "Ð¢Ñ–Ð»Ð´Ñ– Ñ‚Ð°Ò£Ð´Ð°:",
        "lang_set": "Ð¢Ñ–Ð»: ÒšÐ°Ð·Ð°Ò›ÑˆÐ°",
        "income": "ÐšÑ–Ñ€Ñ–Ñ", "expense": "Ð¨Ñ‹Ò“Ñ‹Ñ", "balance": "Ð‘Ð°Ð»Ð°Ð½Ñ", "count": "ÐžÐ¿ÐµÑ€Ð°Ñ†Ð¸ÑÐ»Ð°Ñ€",
        "top": "Ð¡Ð°Ð½Ð°Ñ‚Ñ‚Ð°Ñ€ Ð±Ð¾Ð¹Ñ‹Ð½ÑˆÐ° ÑˆÑ‹Ò“Ñ‹ÑÑ‚Ð°Ñ€ Ò¯Ð·Ð´Ñ–Ð³Ñ–:", "no_category": "Ð¡Ð°Ð½Ð°Ñ‚ÑÑ‹Ð·",
        "cats": {"food": "Ð¢Ð°Ð¼Ð°Ò›", "transport": "ÐšÓ©Ð»Ñ–Ðº", "home": "Ð¢Ò±Ñ€Ò“Ñ‹Ð½ Ò¯Ð¹", "shopping": "Ð¡Ð°Ñ‚Ñ‹Ð¿ Ð°Ð»Ñƒ",
                 "health": "Ð”ÐµÐ½ÑÐ°ÑƒÐ»Ñ‹Ò›", "fun": "Ð”ÐµÐ¼Ð°Ð»Ñ‹Ñ", "other": "Ð‘Ð°ÑÒ›Ð°",
                 "salary": "Ð–Ð°Ð»Ð°Ò›Ñ‹", "business": "Ð‘Ð¸Ð·Ð½ÐµÑ"},
        "titles": {
            ("week", False): "ÐžÑÑ‹ Ð°Ð¿Ñ‚Ð°", ("week", True): "Ó¨Ñ‚ÐºÐµÐ½ Ð°Ð¿Ñ‚Ð°",
            ("month", False): "ÐžÑÑ‹ Ð°Ð¹", ("month", True): "Ó¨Ñ‚ÐºÐµÐ½ Ð°Ð¹",
            ("year", False): "ÐžÑÑ‹ Ð¶Ñ‹Ð»", ("year", True): "Ó¨Ñ‚ÐºÐµÐ½ Ð¶Ñ‹Ð»",
        },
    },
}

MENU_ORDER = [["add_expense", "add_income"], ["week", "month", "year"], ["lang"]]
LABEL_TO_ACTION = {label: action for lang in T.values() for action, label in lang["menu"].items()}

COMMANDS = {
    "/week": "week", "/month": "month", "/year": "year",
    "/lastweek": "lastweek", "/lastmonth": "lastmonth", "/lastyear": "lastyear",
    "/expense": "add_expense", "/income": "add_income", "/lang": "lang",
}

CATEGORY_KEYS = {
    "add_expense": ["food", "transport", "home", "shopping", "health", "fun", "other"],
    "add_income": ["salary", "business", "other"],
}


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
    tg("sendMessage", payload)

# ============================================================
# DB
# ============================================================

@contextmanager
def db():
    # Ð’ serverless ÑÐ¾ÐµÐ´Ð¸Ð½ÐµÐ½Ð¸Ðµ Ð¾Ð±ÑÐ·Ð°Ñ‚ÐµÐ»ÑŒÐ½Ð¾ Ð·Ð°ÐºÑ€Ñ‹Ð²Ð°ÐµÐ¼ ÑÐ°Ð¼Ð¸
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    try:
        with conn.cursor() as cur:
            yield cur
        conn.commit()
    finally:
        conn.close()


def get_user(user_id):
    """Ð¯Ð·Ñ‹Ðº Ð¸ Ñ‚ÐµÐºÑƒÑ‰Ð¸Ð¹ Ñ€ÐµÐ¶Ð¸Ð¼ Ð²Ð²Ð¾Ð´Ð° Ð¾Ð´Ð½Ð¸Ð¼ Ð·Ð°Ð¿Ñ€Ð¾ÑÐ¾Ð¼. Ð ÐµÐ¶Ð¸Ð¼ Ð¶Ð¸Ð²Ñ‘Ñ‚ 30 Ð¼Ð¸Ð½ÑƒÑ‚."""
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
                INSERT INTO user_state (user_id, state, updated_at) VALUES (%s, %s, now())
                ON CONFLICT (user_id) DO UPDATE SET state = EXCLUDED.state, updated_at = now();
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


def get_report(user_id, start, end):
    """Ð’ÑÐµ ÑÑƒÐ¼Ð¼Ñ‹ ÑÑ‡Ð¸Ñ‚Ð°ÑŽÑ‚ÑÑ Ð² SQL, Ð±ÐµÐ· Ð»Ð¸Ð¼Ð¸Ñ‚Ð¾Ð² Ð½Ð° ÐºÐ¾Ð»Ð¸Ñ‡ÐµÑÑ‚Ð²Ð¾ ÑÑ‚Ñ€Ð¾Ðº."""
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
    count = sum(r["cnt"] for r in totals.values())
    return {"income": income, "expense": expense, "balance": income - expense,
            "count": count, "top": top}

# ============================================================
# PARSING (Ð±ÐµÐ· Ð˜Ð˜: ÑÑƒÐ¼Ð¼Ð° = Ð¿Ð¾ÑÐ»ÐµÐ´Ð½ÐµÐµ Ñ‡Ð¸ÑÐ»Ð¾ Ð² ÑÐ¾Ð¾Ð±Ñ‰ÐµÐ½Ð¸Ð¸)
# ============================================================

AMOUNT_RE = re.compile(
    r"(\d{1,3}(?:[ \u00a0]\d{3})+(?:[.,]\d+)?|\d+(?:[.,]\d+)?)\s*(Ð¼Ð¸Ð»Ð»Ð¸Ð¾Ð½\w*|million|Ð¼Ð»Ð½|Ñ‚Ñ‹Ñ\w*|Ð¼Ñ‹Ò£|Ðº|k|m)?(?=\s|$|[^\w])",
    re.IGNORECASE,
)

DATE_WORDS = [
    (re.compile(r"\b(?:Ð¿Ð¾Ð·Ð°Ð²Ñ‡ÐµÑ€Ð°|day before yesterday)\b", re.IGNORECASE), 2),
    (re.compile(r"\b(?:Ð²Ñ‡ÐµÑ€Ð°|yesterday|ÐºÐµÑˆÐµ)\b", re.IGNORECASE), 1),
    (re.compile(r"\b(?:ÑÐµÐ³Ð¾Ð´Ð½Ñ|today|Ð±Ò¯Ð³Ñ–Ð½)\b", re.IGNORECASE), 0),
]


def parse_entry(text):
    matches = list(AMOUNT_RE.finditer(text))
    if not matches:
        return None
    m = matches[-1]

    try:
        amount = float(m.group(1).replace(" ", "").replace(",", "."))
    except ValueError:
        return None
    suffix = (m.group(2) or "").lower()
    if suffix:
        big = suffix.startswith(("Ð¼Ð¸Ð»Ð»Ð¸Ð¾Ð½", "million", "Ð¼Ð»Ð½", "m"))
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

    description = " ".join(rest.split())
    return amount, description, tx_date.isoformat()

# ============================================================
# HELPERS
# ============================================================

def money(val):
    val = float(val)
    text = f"{int(val):,}" if val.is_integer() else f"{val:,.2f}"
    return text.replace(",", " ") + " â‚¸"


def period_range(period, previous=False):
    today = datetime.now(TZ).date()

    if period == "week":
        start = today - timedelta(days=today.weekday())  # Ð¿Ð¾Ð½ÐµÐ´ÐµÐ»ÑŒÐ½Ð¸Ðº
        if previous:
            start -= timedelta(days=7)
            return start, start + timedelta(days=6)
        return start, today

    if period == "month":
        start = today.replace(day=1)
        if previous:
            end = start - timedelta(days=1)
            return end.replace(day=1), end
        return start, today

    if previous:
        y = today.year - 1
        return date(y, 1, 1), date(y, 12, 31)
    return date(today.year, 1, 1), today


def format_report(lang, period, previous, start, end, rep):
    t = T[lang]
    lines = [
        f"ðŸ“Š {t['titles'][(period, previous)]} ({start:%d.%m.%Y} â€” {end:%d.%m.%Y})",
        "",
        f"âž• {t['income']}: {money(rep['income'])}",
        f"âž– {t['expense']}: {money(rep['expense'])}",
        f"ðŸ’¼ {t['balance']}: {money(rep['balance'])}",
        f"ðŸ§¾ {t['count']}: {rep['count']}",
    ]
    if rep["top"]:
        lines += ["", t["top"]]
        lines += [f"â€¢ {cat_label(lang, r['category'])}: {money(r['total'])}" for r in rep["top"]]
    return "\n".join(lines)


def send_report(chat_id, user_id, lang, period, previous=False):
    start, end = period_range(period, previous)
    rep = get_report(user_id, start, end)
    send_message(chat_id, format_report(lang, period, previous, start, end, rep))

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

    elif action in ("week", "month", "year"):
        set_state(user_id, None)
        send_report(chat_id, user_id, lang, action)

    elif action in ("lastweek", "lastmonth", "lastyear"):
        set_state(user_id, None)
        send_report(chat_id, user_id, lang, action[4:], previous=True)


def category_keyboard(state, tx_id, lang):
    buttons = [
        {"text": T[lang]["cats"][k], "callback_data": f"cat:{tx_id}:{k}"}
        for k in CATEGORY_KEYS[state]
    ]
    return {"inline_keyboard": [buttons[i:i + 3] for i in range(0, len(buttons), 3)]}

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

    if data.startswith("lang:") and data[5:] in LANGS:
        lang = data[5:]
        set_lang(user_id, lang)
        tg("answerCallbackQuery", {"callback_query_id": cb["id"]})
        tg("editMessageReplyMarkup", {"chat_id": chat_id, "message_id": message_id,
                                      "reply_markup": {"inline_keyboard": []}})
        send_message(chat_id, T[lang]["lang_set"] + "\n\n" + T[lang]["help"], reply_markup=menu_markup(lang))

    elif data.startswith("cat:"):
        _, tx_id, key = data.split(":", 2)
        set_category(user_id, int(tx_id), key)
        tg("answerCallbackQuery", {"callback_query_id": cb["id"], "text": "âœ… " + cat_label(lang, key)})
        tg("editMessageReplyMarkup", {"chat_id": chat_id, "message_id": message_id,
                                      "reply_markup": {"inline_keyboard": []}})
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
        lang = {"kk": "kk", "en": "en"}.get((message["from"].get("language_code") or "")[:2], "ru")
    t = T[lang]

    if not is_allowed(user_id):
        send_message(chat_id, t["denied"])
        return

    first = text.split()[0].split("@")[0].lower()

    # 1. Ð¡Ñ‚Ð°Ñ€Ñ‚ Ð¸ ÑÐ¿Ñ€Ð°Ð²ÐºÐ°
    if first in ("/start", "/help"):
        set_state(user_id, None)
        send_message(chat_id, t["help"], reply_markup=menu_markup(lang))
        return

    # 2. ÐšÐ½Ð¾Ð¿ÐºÐ¸ Ð¿Ð°Ð½ÐµÐ»Ð¸ Ð¸ ÐºÐ¾Ð¼Ð°Ð½Ð´Ñ‹
    action = LABEL_TO_ACTION.get(text) or COMMANDS.get(first)
    if action:
        run_action(action, chat_id, user_id, lang)
        return

    # 3. Ð’Ð²Ð¾Ð´ Ð¿Ð¾ÑÐ»Ðµ Ð½Ð°Ð¶Ð°Ñ‚Ð¸Ñ ÐºÐ½Ð¾Ð¿ÐºÐ¸
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
        send_message(chat_id, "\n".join(lines), reply_markup=category_keyboard(state, tx_id, lang))
        return

    # 4. ÐžÐ±Ñ‹Ñ‡Ð½Ð¾Ðµ ÑÐ¾Ð¾Ð±Ñ‰ÐµÐ½Ð¸Ðµ Ð²Ð½Ðµ Ñ€ÐµÐ¶Ð¸Ð¼Ð° â€” Ð¼Ð¾Ð»Ñ‡Ð¸Ð¼
    return


def process_update(update):
    if update.get("callback_query"):
        process_callback(update["callback_query"])
    elif update.get("message"):
        process_message(update["message"])

# ============================================================
# VERCEL HANDLER
# ============================================================

class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        if WEBHOOK_SECRET and self.headers.get("X-Telegram-Bot-Api-Secret-Token") != WEBHOOK_SECRET:
            self.send_response(403)
            self.end_headers()
            return

        update = {}
        try:
            length = int(self.headers.get("content-length", 0))
            update = json.loads(self.rfile.read(length).decode("utf-8"))
            process_update(update)
        except Exception as e:
            print("Error:", repr(e))
            try:
                msg = update.get("message") or update["callback_query"]["message"]
                user = update["message"]["from"] if update.get("message") else update["callback_query"]["from"]
                lang, _ = get_user(user["id"])
                send_message(msg["chat"]["id"], T[lang if lang in LANGS else "ru"]["error"])
            except Exception:
                pass

        # Ð’ÑÐµÐ³Ð´Ð° 200, Ð¸Ð½Ð°Ñ‡Ðµ Telegram Ð±ÑƒÐ´ÐµÑ‚ Ð±ÐµÑÐºÐ¾Ð½ÐµÑ‡Ð½Ð¾ Ñ€ÐµÑ‚Ñ€Ð°Ð¸Ñ‚ÑŒ Ð°Ð¿Ð´ÐµÐ¹Ñ‚
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"ok": true}')

    def do_GET(self):
        lines = ["Bot is alive!"]
        missing = [n for n in ("TELEGRAM_TOKEN", "DATABASE_URL") if not os.environ.get(n)]
        if missing:
            lines.append("Missing env vars: " + ", ".join(missing))
        else:
            try:
                with db() as cur:
                    cur.execute("SELECT count(*) AS n FROM transactions")
                    cur.fetchone()
                lines.append("Database: OK")
            except Exception as e:
                lines.append("Database error: " + type(e).__name__)
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write("\n".join(lines).encode("utf-8"))
