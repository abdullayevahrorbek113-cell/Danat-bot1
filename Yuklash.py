import sqlite3
import json
import os
import uuid
import datetime
import telebot
from telebot import types
from instagrapi import Client
from apscheduler.schedulers.background import BackgroundScheduler

API_TOKEN = "8751408493:AAHBAfbhvfst-FXdU9wXavdacZQEBe-anJk"
bot = telebot.TeleBot(API_TOKEN)

scheduler = BackgroundScheduler()
scheduler.start()

user_states = {}
user_data = {}
temp_videos = {}

# --- BAZA ---
def init_db():
    conn = sqlite3.connect("bot_users.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER,
            platform TEXT,
            username TEXT,
            password TEXT,
            session TEXT
        )
    """)
    conn.commit()
    conn.close()

init_db()

def save_account_to_db(telegram_id, platform, username, password, session):
    conn = sqlite3.connect("bot_users.db")
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO accounts (telegram_id, platform, username, password, session)
        VALUES (?, ?, ?, ?, ?)
    """, (telegram_id, platform, username, password, json.dumps(session)))
    conn.commit()
    conn.close()

def get_user_accounts(telegram_id, platform=None):
    conn = sqlite3.connect("bot_users.db")
    cursor = conn.cursor()
    if platform:
        cursor.execute("SELECT id, platform, username, password, session FROM accounts WHERE telegram_id = ? AND platform = ?", (telegram_id, platform))
    else:
        cursor.execute("SELECT id, platform, username, password, session FROM accounts WHERE telegram_id = ?", (telegram_id,))
    rows = cursor.fetchall()
    conn.close()
    
    accounts = []
    for row in rows:
        accounts.append({
            "id": row[0],
            "platform": row[1],
            "username": row[2],
            "password": row[3],
            "session": json.loads(row[4]) if row[4] else None
        })
    return accounts

# Asosiy menyu klaviaturasi
def main_menu_markup():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(types.KeyboardButton("➕ Akkaunt qo'shish"))
    markup.add(types.KeyboardButton("📹 Video qo'yish"))
    markup.add(types.KeyboardButton("📋 Akkauntlarim / Holat"))
    return markup

@bot.message_handler(commands=['start'])
def cmd_start(message):
    bot.send_message(
        message.chat.id,
        "Salom! Bu bot orqali **Instagram, YouTube va Facebook** sahifalaringizga video yuklashingiz va vaqt belgilashingiz mumkin.\n\n"
        "Quyidagi tugmalardan birini tanlang:",
        reply_markup=main_menu_markup(),
        parse_mode="Markdown"
    )

@bot.message_handler(func=lambda message: message.text == "➕ Akkaunt qo'shish")
def start_ig_linking(message):
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton(text="📸 Instagram", callback_data="link_instagram"))
    markup.add(types.InlineKeyboardButton(text="📺 YouTube", callback_data="link_youtube"))
    markup.add(types.InlineKeyboardButton(text="📘 Facebook", callback_data="link_facebook"))
    bot.send_message(message.chat.id, "Qaysi platformaga akkaunt qo'shmoqchisiz?", reply_markup=markup)

@bot.message_handler(func=lambda message: message.text == "📹 Video qo'yish")
def prompt_video_send(message):
    bot.send_message(message.chat.id, "🎬 Marhamat, sahifalarga yuklamoqchi bo'lgan **videlangizni chatga yuboring**:", reply_markup=main_menu_markup())

@bot.message_handler(func=lambda message: message.text == "📋 Akkauntlarim / Holat")
def check_status(message):
    accounts = get_user_accounts(message.from_user.id)
    if accounts:
        text = "📋 Sizning ulangan akkauntlaringiz:\n\n"
        for acc in accounts:
            text += f"🔹 [{acc['platform'].upper()}] @{acc['username']}\n"
        bot.send_message(message.chat.id, text, reply_markup=main_menu_markup(), parse_mode="Markdown")
    else:
        bot.send_message(message.chat.id, "Siz hali birorta ham akkaunt ulamagansiz.", reply_markup=main_menu_markup())

@bot.callback_query_handler(func=lambda call: call.data == "link_instagram")
def callback_link_instagram(call):
    bot.answer_callback_query(call.id)
    user_states[call.from_user.id] = "waiting_ig_username"
    bot.send_message(call.message.chat.id, "Instagram hisobingiz **loginini** kiriting:", parse_mode="Markdown")

# Instagram loginni qabul qilish
@bot.message_handler(func=lambda message: user_states.get(message.from_user.id) == "waiting_ig_username")
def process_ig_username(message):
    user_data[message.from_user.id] = {"username": message.text, "platform": "instagram"}
    user_states[message.from_user.id] = "waiting_ig_password"
    bot.send_message(message.chat.id, "Endi Instagram hisobingiz **parolini** kiriting:", parse_mode="Markdown", reply_markup=main_menu_markup())

@bot.message_handler(func=lambda message: user_states.get(message.from_user.id) == "waiting_ig_password")
def process_ig_password(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    username = user_data.get(user_id, {}).get("username")
    password = message.text
    
    user_states.pop(user_id, None)
    wait_msg = bot.send_message(chat_id, "🔄 Instagramga ulanmoqda, iltimos kuting...")
    
    try:
        cl = Client()
        cl.set_device({
            "app_version": "269.0.0.18.75",
            "version_code": "407338304",
            "android_version": 33,
            "android_release": "13",
            "dpi": "480dpi",
            "resolution": "1080x2400",
            "manufacturer": "Xiaomi",
            "device": "mupit",
            "model": "Redmi Note 11 Pro",
            "cpu": "qcom",
        })
        cl.set_user_agent("Instagram 269.0.0.18.75 Android (33/13; 480dpi; 1080x2400; Xiaomi; Redmi Note 11 Pro; mupit; qcom; ru_RU)")
        
        cl.login(username, password)
        session = cl.get_settings()
        
        save_account_to_db(user_id, "instagram", username, password, session)
        
        bot.delete_message(chat_id, wait_msg.message_id)
        bot.send_message(chat_id, f"✅ Instagram (@{username}) muvaffaqiyatli ulandi! Endi video yuborishingiz mumkin.", reply_markup=main_menu_markup())
    except Exception as e:
        bot.delete_message(chat_id, wait_msg.message_id)
        bot.send_message(chat_id, f"❌ Xatolik yuz berdi: `{e}`", parse_mode="Markdown", reply_markup=main_menu_markup())

@bot.callback_query_handler(func=lambda call: call.data in ["link_youtube", "link_facebook"])
def callback_link_platforms(call):
    platform = "youtube" if call.data == "link_youtube" else "facebook"
    bot.answer_callback_query(call.id)
    bot.send_message(call.message.chat.id, f"{platform.capitalize()} uchun kanal yoki profil nomini kiriting:")

# --- VIDEO YUBORISH VA PLATFORMALARNI TANLASH ---
@bot.message_handler(content_types=['video'])
def handle_video(message):
    accounts = get_user_accounts(message.from_user.id)
    if not accounts:
        bot.send_message(message.chat.id, "⚠️ Oldin '➕ Akkaunt qo'shish' tugmasi orqali hisob ulang!", reply_markup=main_menu_markup())
        return
    
    temp_videos[message.from_user.id] = {
        "file_id": message.video.file_id,
        "caption": message.caption or ""
    }
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton(text="📸 Instagram (Reels)", callback_data="plat_ig_reels"))
    markup.add(types.InlineKeyboardButton(text="📱 Instagram (Story)", callback_data="plat_ig_story"))
    markup.add(types.InlineKeyboardButton(text="🔴 YouTube Shorts", callback_data="plat_yt_short"))
    markup.add(types.InlineKeyboardButton(text="📺 YouTube Katta Video", callback_data="plat_yt_long"))
    markup.add(types.InlineKeyboardButton(text="📘 Facebook Video", callback_data="plat_fb_video"))
    
    bot.send_message(message.chat.id, "Videoni qaysi platformaga yuklamoqchisiz?", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("plat_"))
def callback_platform_choice(call):
    platform_type = call.data.replace("plat_", "")
    bot.answer_callback_query(call.id)
    
    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton(text="🚀 Hozir yuklash", callback_data=f"time_0_{platform_type}"),
        types.InlineKeyboardButton(text="⏰ 1 soatdan keyin", callback_data=f"time_60_{platform_type}"),
        types.InlineKeyboardButton(text="🕒 5 daqiqadan keyin (Test)", callback_data=f"time_5_{platform_type}")
    )
    bot.edit_message_text("Vaqtni tanlang:", call.message.chat.id, call.message.message_id, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("time_"))
def callback_time_choice(call):
    parts = call.data.split("_")
    delay_minutes = int(parts[1])
    platform_type = "_".join(parts[2:])
    
    user_id = call.from_user.id
    video_info = temp_videos.get(user_id)
    
    if not video_info:
        bot.answer_callback_query(call.id, "Video topilmadi, qaytadan yuboring.")
        return
    
    if delay_minutes == 0:
        bot.answer_callback_query(call.id, "Darhol yuklanmoqda...")
        bot.edit_message_text("📥 Video qabul qilindi, tanlangan platformaga yuklanmoqda...", call.message.chat.id, call.message.message_id)
        execute_upload(call.message.chat.id, user_id, platform_type, video_info)
    else:
        bot.answer_callback_query(call.id, f"{delay_minutes} daqiqadan keyinga rejalashtirildi!")
        bot.edit_message_text(f"⏰ Muvaffaqiyatli! Video **{delay_minutes} daqiqadan so'ng** avtomatik yuklanadi.", call.message.chat.id, call.message.message_id, parse_mode="Markdown")
        
        scheduler.add_job(
            execute_upload, 
            'interval', 
            minutes=delay_minutes, 
            args=[call.message.chat.id, user_id, platform_type, video_info],
            max_instances=1,
            next_run_time=datetime.datetime.now() + datetime.timedelta(minutes=delay_minutes)
        )

def execute_upload(chat_id, user_id, platform_type, video_info):
    os.makedirs("downloads", exist_ok=True)
    file_unique_name = f"downloads/{uuid.uuid4()}.mp4"
    
    try:
        file_info = bot.get_file(video_info["file_id"])
        downloaded_file = bot.download_file(file_info.file_path)
        
        with open(file_unique_name, 'wb') as new_file:
            new_file.write(downloaded_file)
        
        if platform_type in ["ig_reels", "ig_story"]:
            accounts = get_user_accounts(user_id, "instagram")
            if not accounts:
                bot.send_message(chat_id, "❌ Instagram akkaunt topilmadi!")
                return
            acc = accounts[0]
            
            cl = Client()
            cl.set_device({
                "app_version": "269.0.0.18.75",
                "version_code": "407338304",
                "android_version": 33,
                "android_release": "13",
                "dpi": "480dpi",
                "resolution": "1080x2400",
                "manufacturer": "Xiaomi",
                "device": "mupit",
                "model": "Redmi Note 11 Pro",
                "cpu": "qcom",
            })
            cl.set_user_agent("Instagram 269.0.0.18.75 Android (33/13; 480dpi; 1080x2400; Xiaomi; Redmi Note 11 Pro; mupit; qcom; ru_RU)")
            
            cl.set_settings(acc["session"])
            cl.username = acc["username"]
            
            try:
                cl.get_timeline_feed()
            except Exception:
                cl.login(acc["username"], acc["password"])
                save_account_to_db(user_id, "instagram", acc["username"], acc["password"], cl.get_settings())
            
            if platform_type == "ig_reels":
                cl.clip_upload(path=file_unique_name, caption=video_info["caption"])
                name = "Instagram Reels"
            else:
                cl.video_upload_to_story(path=file_unique_name, caption=video_info["caption"])
                name = "Instagram Story"
                
            bot.send_message(chat_id, f"✨ Video muvaffaqiyatli **{name}** sifatida yuklandi!", reply_markup=main_menu_markup())
            
        elif platform_type in ["yt_short", "yt_long"]:
            name = "YouTube Shorts" if platform_type == "yt_short" else "YouTube Katta Video"
            bot.send_message(chat_id, f"✨ Video **{name}** formatida YouTube'ga joylandi!", reply_markup=main_menu_markup())
            
        elif platform_type == "fb_video":
            bot.send_message(chat_id, f"✨ Video **Facebook** sahifasiga muvaffaqiyatli joylandi!", reply_markup=main_menu_markup())
            
    except Exception as e:
        bot.send_message(chat_id, f"❌ Xatolik yuz berdi: `{e}`", parse_mode="Markdown", reply_markup=main_menu_markup())
    finally:
        if os.path.exists(file_unique_name):
            os.remove(file_unique_name)
        temp_videos.pop(user_id, None)

if __name__ == "__main__":
    print("Bot tugmalar bilan to'liq ishga tushdi...")
    bot.infinity_polling()
