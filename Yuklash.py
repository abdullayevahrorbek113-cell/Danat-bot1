import logging
import sqlite3
import json
import os
import uuid
from aiogram import Bot, Dispatcher, F, types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from instagrapi import Client

API_TOKEN = "8751408493:AAHBAfbhvfst-FXdU9wXavdacZQEBe-anJk"

bot = Bot(token=API_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# --- BAZA ---
def init_db():
    conn = sqlite3.connect("bot_users.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            telegram_id INTEGER PRIMARY KEY,
            username TEXT,
            password TEXT,
            session TEXT
        )
    """)
    conn.commit()
    conn.close()

init_db()

def save_user_to_db(telegram_id, username, password, session):
    conn = sqlite3.connect("bot_users.db")
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO users (telegram_id, username, password, session)
        VALUES (?, ?, ?, ?)
    """, (telegram_id, username, password, json.dumps(session)))
    conn.commit()
    conn.close()

def get_user_from_db(telegram_id):
    conn = sqlite3.connect("bot_users.db")
    cursor = conn.cursor()
    cursor.execute("SELECT username, password, session FROM users WHERE telegram_id = ?", (telegram_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return {
            "username": row[0],
            "password": row[1],
            "session": json.loads(row[2]) if row[2] else None
        }
    return None

class InstaLogin(StatesGroup):
    waiting_for_username = State()
    waiting_for_password = State()

@dp.message(F.text == "/start")
async def cmd_start(message: types.Message):
    markup = types.ReplyKeyboardMarkup(
        keyboard=[
            [types.KeyboardButton(text="Instagram ulash 🔗")],
            [types.KeyboardButton(text="Holatim 📊")]
        ],
        resize_keyboard=True
    )
    await message.answer(
        "Salom! Bu bot orqali Instagram sahifangizga avtomatik Reels yuklashingiz mumkin.\n\n"
        "Boshlash uchun **'Instagram ulash 🔗'** tugmasini bosing.",
        reply_markup=markup
    )

@dp.message(F.text == "Instagram ulash 🔗")
async def start_linking(message: types.Message, state: FSMContext):
    await message.answer("Instagram hisobingiz **loginini** kiriting:")
    await state.set_state(InstaLogin.waiting_for_username)

@dp.message(InstaLogin.waiting_for_username)
async def process_username(message: types.Message, state: FSMContext):
    await state.update_data(username=message.text)
    await message.answer("Endi Instagram hisobingiz **parolini** kiriting:")
    await state.set_state(InstaLogin.waiting_for_password)

@dp.message(InstaLogin.waiting_for_password)
async def process_password(message: types.Message, state: FSMContext):
    data = await state.get_data()
    username = data.get("username")
    password = message.text
    
    wait_msg = await message.answer("🔄 Instagramga ulanmoqda, iltimos kuting...")
    
    try:
        cl = Client()
        cl.login(username, password)
        # Sessiya sozlamalarini olib, bazaga saqlaymiz
        session = cl.get_settings()
        
        save_user_to_db(message.from_user.id, username, password, session)
        
        await bot.delete_message(message.chat.id, wait_msg.message_id)
        await message.answer("✅ Akkaunt muvaffaqiyatli ulandi! Endi menga Reels uchun video yuboring.")
        await state.clear()
    except Exception as e:
        await bot.delete_message(message.chat.id, wait_msg.message_id)
        await message.answer(f"❌ Xatolik yuz berdi: `{e}`\nLogin yoki parolni tekshirib qaytadan urinib ko'ring.")
        await state.clear()

@dp.message(F.text == "Holatim 📊")
async def check_status(message: types.Message):
    user = get_user_from_db(message.from_user.id)
    if user:
        await message.answer(f"Sizning ulangan Instagram profilingiz: **@{user['username']}**\n✅ Akkaunt faol va saqlangan.")
    else:
        await message.answer("Siz hali Instagram akkauntingizni ulamagansiz.")

# Videoni qabul qilib, parol so'ramasdan (sessiya orqali) yuklash
@dp.message(F.video)
async def handle_video(message: types.Message):
    user = get_user_from_db(message.from_user.id)
    if not user:
        await message.answer("⚠️ Oldin o'z Instagram akkauntingizni ulang ('Instagram ulash 🔗').")
        return
    
    processing = await message.answer("📥 Video qabul qilindi, Instagramga yuklanmoqda...")
    
    os.makedirs("downloads", exist_ok=True)
    file_unique_name = f"downloads/{uuid.uuid4()}.mp4"
    
    file_info = await bot.get_file(message.video.file_id)
    await bot.download_file(file_info.file_path, destination=file_unique_name)
    
    caption = message.caption or ""
    
    try:
        cl = Client()
        # Oldindan saqlangan sessiyani yuklaymiz (Parol talab qilinmaydi!)
        cl.set_settings(user["session"])
        cl.username = user["username"]
        
        # Sessiya eskirgan bo'lsa yoki ishlamasa, avtomatik login qilish uchun zaxira usul
        try:
            cl.get_timeline_feed()
        except Exception:
            cl.login(user["username"], user["password"])
            # Yangilangan sessiyani bazaga qayta yozib qo'yamiz
            new_session = cl.get_settings()
            save_user_to_db(message.from_user.id, user["username"], user["password"], new_session)
        
        # Reels sifatida yuklash
        cl.clip_upload(path=file_unique_name, caption=caption)
        
        await bot.delete_message(message.chat.id, processing.message_id)
        await message.answer("✨ Video Instagram sahifangizga muvaffaqiyatli joylandi!")
    except Exception as e:
        await bot.delete_message(message.chat.id, processing.message_id)
        await message.answer(f"❌ Videoni yuklashda xatolik: `{e}`\nIltimos, qaytadan 'Instagram ulash 🔗' tugmasini bosib akkauntingizni yangilang.")
    finally:
        if os.path.exists(file_unique_name):
            os.remove(file_unique_name)

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
