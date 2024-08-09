import telebot
import requests
from bs4 import BeautifulSoup
import schedule
import time
import sqlite3
import os
import semver

API_TOKEN = os.getenv("API_TOKEN")
bot = telebot.TeleBot(API_TOKEN)

def db_cursor():
    conn = sqlite3.connect('users.db')
    c = conn.cursor()

    return conn, c

_, c = db_cursor()
c.execute('''CREATE TABLE IF NOT EXISTS users
                (chat_id INTEGER PRIMARY KEY, last_version TEXT)''')

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

    latest_version = max(versions, key=semver.Version.parse)

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

schedule.every().day.at("09:00").do(check_all_users)

while True:
    bot.polling()
    schedule.run_pending()
    time.sleep(1)
