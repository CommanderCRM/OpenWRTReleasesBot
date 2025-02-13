import telebot
import requests
from bs4 import BeautifulSoup
import schedule
import time
import sqlite3
import os
import re
from typing import Optional, Tuple
from semver import Version
from packaging.utils import canonicalize_version

API_TOKEN = os.getenv("API_TOKEN")
bot = telebot.TeleBot(API_TOKEN)

def db_cursor():
    conn = sqlite3.connect('users.db')
    c = conn.cursor()

    return conn, c

_, c = db_cursor()
c.execute('''CREATE TABLE IF NOT EXISTS users
                (chat_id INTEGER PRIMARY KEY, last_version TEXT)''')

BASEVERSION = re.compile(
    r"""[vV]?
        (?P<major>0|[1-9]\d*)
        (\.
        (?P<minor>0|[1-9]\d*)
        (\.
            (?P<patch>0|[1-9]\d*)
        )?
        )?
    """,
    re.VERBOSE,
)

def coerce(version: str) -> Tuple[Version, Optional[str]]:
    """
    Convert an incomplete version string into a semver-compatible Version
    object

    * Tries to detect a "basic" version string (``major.minor.patch``).
    * If not enough components can be found, missing components are
        set to zero to obtain a valid semver version.

    :param str version: the version string to convert
    :return: a tuple with a :class:`Version` instance (or ``None``
        if it's not a version) and the rest of the string which doesn't
        belong to a basic version.
    :rtype: tuple(:class:`Version` | None, str)
    """
    match = BASEVERSION.search(version)
    if not match:
        return (None, version)

    ver = {
        key: 0 if value is None else value for key, value in match.groupdict().items()
    }
    ver = Version(**ver)
    rest = match.string[match.end() :]  # noqa:E203
    return ver, rest

def get_latest_openwrt_version():
    url = 'https://downloads.openwrt.org/releases/'
    response = requests.get(url, timeout=90)
    soup = BeautifulSoup(response.text, 'html.parser')

    versions = []
    for link in soup.find_all('a'):
        href = link.get('href')
        if href and href.endswith('/'): # "23.05.4/ etc"
            version = href.strip('/')
            # not append -rc, faillogs, packages (everything that is not a "true" version)
            if version and all(part.isdigit() for part in version.split('.')):
                versions.append(version)

    # OpenWRT uses "XX.YY.Z" versioning scheme where first Y is usually 0.
    # First we need to canonicalize it, result will be XX.Y.
    # Then the result is transformed into XX.Y.Z via coerce().
    versions = [coerce(canonicalize_version(v))[0] for v in versions]
    latest_version = max(versions)

    return latest_version

@bot.message_handler(commands=['start'])
def send_welcome(message):
    chat_id = message.chat.id

    conn, c = db_cursor()

    c.execute("INSERT OR IGNORE INTO users (chat_id, last_version) VALUES (?, ?)", (chat_id, None))
    conn.commit()

    bot.reply_to(message, "This bot can check for new OpenWRT versions. Your ID is now in the DB, the bot will notify you.")

def check_all_users():
    conn, c = db_cursor()
    latest_version = get_latest_openwrt_version()
    c.execute("SELECT chat_id, last_version FROM users")
    users = c.fetchall()

    for user_chat_id, last_version in users:
        bot.send_message(chat_id=user_chat_id, text=f"Latest OpenWRT version: {latest_version}")
        if last_version != latest_version:
            bot.send_message(chat_id=user_chat_id, text=f"New OpenWRT version available: {latest_version}")
            c.execute("UPDATE users SET last_version = ? WHERE chat_id = ?", (latest_version, user_chat_id))

    conn.commit()
    conn.close()

schedule.every().day.at("05:00").do(check_all_users)

while True:
    bot.polling()
    schedule.run_pending()
    time.sleep(1)
