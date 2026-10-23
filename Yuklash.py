import sqlite3
import json
import os
import uuid
import time
import telebot
from telebot import types
from instagrapi import Client
from apscheduler.schedulers.background import BackgroundScheduler

API_TOKEN = "8751408493:AAHBAfbhvfst-FXdU9wXavdacZQEBe-anJk"
bot = telebot.TeleBot(API_TOKEN)

# Schedulerni ishga tushiramiz
scheduler = BackgroundScheduler()
scheduler.start()

user_states = {}
user_data = {}
temp_videos = {}  # Vaqtinchalik video va tanlovlarni saqlash

# --- BAZA ---
def init_db():
    conn = sqlite3.connect("bot_users.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER,
            username TEXT,
            password TEXT,
            session TEXT
        )
    """)
    conn.commit()
    conn.close()

init_db()

def save_account_to_db(telegram_id, username, password, session):
    conn = sqlite3.connect("bot_users.db")
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO accounts (telegram_id, username, password, session)
        VALUES (?, ?, ?, ?)
    """, (telegram_id, username, password, json.dumps(session)))
    conn.commit()
    conn.close()

def get_user_accounts(telegram_id):
    conn = sqlite3.connect("bot_users.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id, username, password, session FROM accounts WHERE telegram_id = ?", (telegram_id,))
    rows = cursor.fetchall()
    conn.close()
    
    accounts = []
    for row in rows:
        accounts.append({
            "id": row[0],
            "username": row[1],
            "password": row[2],
            "session": json.loads(row[3]) if row[3] else None
        })
    return accounts

@bot.message_handler(commands=['start'])
def cmd_start(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(types.KeyboardButton("➕ Akkaunt qo'shish"))
    markup.add(types.KeyboardButton("📋 Akkauntlarim / Holat"))
    
    bot.send_message(
        message.chat.id,
        "Salom! Bu bot yordamida Instagram sahifalaringizga Reels yoki Story yuklashingiz va vaqt belgilashingiz mumkin.\n\n"
        "Boshlash uchun **'➕ Akkaunt qo'shish'** tugmasini bosing.",
        reply_markup=markup,
        parse_mode="Markdown"
    )

@bot.message_handler(func=lambda message: message.text == "➕ Akkaunt qo'shish")
def start_linking(message):
    user_states[message.from_user.id] = "waiting_for_username"
    bot.send_message(message.chat.id, "Instagram hisobingiz **loginini** kiriting:", parse_mode="Markdown")

@bot.message_handler(func=lambda message: message.text == "📋 Akkauntlarim / Holat")
def check_status(message):
    accounts = get_user_accounts(message.from_user.id)
    if accounts:
        text = "📋 Sizning ulangan Instagram akkauntlaringiz:\n\n"
        for acc in accounts:
            text += f"🔹 @{acc['username']}\n"
        bot.send_message(message.chat.id, text, parse_mode="Markdown")
    else:
        bot.send_message(message.chat.id, "Siz hali birorta ham Instagram akkaunt ulamagansiz.")

@bot.message_handler(func=lambda message: user_states.get(message.from_user.id) == "waiting_for_username")
def process_username(message):
    user_data[message.from_user.id] = {"username": message.text}
    user_states[message.from_user.id] = "waiting_for_password"
    bot.send_message(message.chat.id, "Endi Instagram hisobingiz **parolini** kiriting:", parse_mode="Markdown")

@bot.message_handler(func=lambda message: user_states.get(message.from_user.id) == "waiting_for_password")
def process_password(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    username = user_data.get(user_id, {}).get("username")
    password = message.text
    
    user_states.pop(user_id, None)
    wait_msg = bot.send_message(chat_id, "🔄 Instagramga ulanmoqda, iltimos kuting...")
    
    try:
        cl = Client()
        cl.login(username, password)
        session = cl.get_settings()
        
        save_account_to_db(user_id, username, password, session)
        
        bot.delete_message(chat_id, wait_msg.message_id)
        bot.send_message(chat_id, f"✅ @{username} akkaunti muvaffaqiyatli ulandi! Endi menga video yuboring.")
    except Exception as e:
        bot.delete_message(chat_id, wait_msg.message_id)
        bot.send_message(chat_id, f"❌ Xatolik yuz berdi: `{e}`", parse_mode="Markdown")

# 1-QADAM: Video kelganda Reels yoki Story ni tanlash
@bot.message_handler(content_types=['video'])
def handle_video(message):
    accounts = get_user_accounts(message.from_user.id)
    if not accounts:
        bot.send_message(message.chat.id, "⚠️ Oldin o'z Instagram akkauntingizni ulang ('➕ Akkaunt qo'shish').")
        return
    
    temp_videos[message.from_user.id] = {
        "file_id": message.video.file_id,
        "caption": message.caption or ""
    }
    
    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton(text="🎬 Reels'ga yuklash", callback_data="type_reels"),
        types.InlineKeyboardButton(text="📱 Story'ga yuklash", callback_data="type_story")
    )
    bot.send_message(message.chat.id, "Videoni qayerga yuklamoqchisiz?", reply_markup=markup)

# 2-QADAM: Akkauntni tanlash
@bot.callback_query_handler(func=lambda call: call.data in ["type_reels", "type_story"])
def callback_media_type(call):
    upload_type = "Reels" if call.data == "type_reels" else "Story"
    user_id = call.from_user.id
    
    accounts = get_user_accounts(user_id)
    markup = types.InlineKeyboardMarkup()
    for acc in accounts:
        markup.add(types.InlineKeyboardButton(
            text=f"@{acc['username']}", 
            callback_data=f"acc_{acc['id']}_{call.data}"
        ))
    
    bot.edit_message_text(f"Qaysi akkauntga **{upload_type}** sifatida yuklaymiz?", call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode="Markdown")

# 3-QADAM: Vaqt belgilash (Hozir yoki Keyin)
@bot.callback_query_handler(func=lambda call: call.data.startswith("acc_"))
def callback_account(call):
    parts = call.data.split("_")
    account_id = parts[1]
    upload_type = parts[2] # type_reels yoki type_story
    
    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton(text="🚀 Hozir yuklash", callback_data=f"time_now_{account_id}_{upload_type}"),
        types.InlineKeyboardButton(text="⏰ 1 soatdan keyin", callback_data=f"time_60_{account_id}_{upload_type}"),
        types.InlineKeyboardButton(text="🕒 5 daqiqadan keyin (Test)", callback_data=f"time_5_{account_id}_{upload_type}")
    )
    bot.edit_message_text("Vaqtni tanlang:", call.message.chat.id, call.message.message_id, reply_markup=markup)

# 4-QADAM: Yuklashni bajarish yoki rejalashtirish
@bot.callback_query_handler(func=lambda call: call.data.startswith("time_"))
def callback_time(call):
    parts = call.data.split("_")
    delay_minutes = int(parts[1]) # 0 (hozir), 60 yoki 5
    account_id = int(parts[2])
    upload_type = parts[3]
    
    user_id = call.from_user.id
    video_info = temp_videos.get(user_id)
    
    if not video_info:
        bot.answer_callback_query(call.id, "Video topilmadi, qaytadan yuboring.")
        return
    
    conn = sqlite3.connect("bot_users.db")
    cursor = conn.cursor()
    cursor.execute("SELECT username, password, session FROM accounts WHERE id = ?", (account_id,))
    row = cursor.fetchone()
    conn.close()
    
    account = {
        "username": row[0],
        "password": row[1],
        "session": json.loads(row[2]) if row[2] else None
    }
    
    type_name = "Reels" if upload_type == "type_reels" else "Story"
    
    if delay_minutes == 0:
        bot.answer_callback_query(call.id, "Darhol yuklanmoqda...")
        bot.edit_message_text(f"📥 Video @{account['username']} sahifasiga {type_name} bo'lib yuklanmoqda...", call.message.chat.id, call.message.message_id)
        upload_worker(call.message.chat.id, user_id, account, upload_type, video_info)
    else:
        bot.answer_callback_query(call.id, f"{delay_minutes} daqiqadan keyinga rejalashtirildi!")
        bot.edit_message_text(f"⏰ Muvaffaqiyatli! Video **{delay_minutes} daqiqadan so'ng** @{account['username']} sahifasiga {type_name} sifatida avtomatik yuklanadi.", call.message.chat.id, call.message.message_id, parse_mode="Markdown")
        
        # Scheduler orqali vaqtga qo'yish
        scheduler.add_job(
            upload_worker, 
            'interval', 
            minutes=delay_minutes, 
            args=[call.message.chat.id, user_id, account, upload_type, video_info],
            max_instances=1,
            next_run_time=datetime_in_future(delay_minutes)
        )

import datetime
def datetime_in_future(minutes):
    return datetime.datetime.now() + datetime.timedelta(minutes=minutes)

def upload_worker(chat_id, user_id, account, upload_type, video_info):
    os.makedirs("downloads", exist_ok=True)
    file_unique_name = f"downloads/{uuid.uuid4()}.mp4"
    
    try:
        file_info = bot.get_file(video_info["file_id"])
        downloaded_file = bot.download_file(file_info.file_path)
        
        with open(file_unique_name, 'wb') as new_file:
            new_file.write(downloaded_file)
        
        cl = Client()
        cl.set_settings(account["session"])
        cl.username = account["username"]
        
        try:
            cl.get_timeline_feed()
        except Exception:
            cl.login(account["username"], account["password"])
            new_session = cl.get_settings()
            save_account_to_db(user_id, account["username"], account["password"], new_session)
        
        if upload_type == "type_reels":
            cl.clip_upload(path=file_unique_name, caption=video_info["caption"])
            type_name = "Reels"
        else:
            cl.video_upload_to_story(path=file_unique_name, caption=video_info["caption"])
            type_name = "Story"
        
        bot.send_message(chat_id, f"✨ Rejalashtirilgan video @{account['username']} sahifasiga {type_name} sifatida muvaffaqiyatli joylandi!")
    except Exception as e:
        bot.send_message(chat_id, f"❌ Xatolik (@{account['username']}): `{e}`", parse_mode="Markdown")
    finally:
        if os.path.exists(file_unique_name):
            os.remove(file_unique_name)
        temp_videos.pop(user_id, None)

if __name__ == "__main__":
    print("Bot vaqt belgilash funksiyasi bilan ishga tushdi...")
    bot.infinity_polling()
