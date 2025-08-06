# bot_referral.py
import asyncio
import json
import os
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, F
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    FSInputFile
)
from aiogram.filters import CommandStart, Command

load_dotenv()
API_TOKEN = os.getenv("BOT_TOKEN")
if not API_TOKEN:
    raise RuntimeError("BOT_TOKEN not found in environment. Put it into .env file as BOT_TOKEN=...")

# Konfiguratsiya
REQUIRED_CHANNELS = [
    "@talkmorespeakingclub",
    "@listeninghubn1",
    "@speakingsaidbek"
]
MIN_REFERRALS = 2
REFERRAL_REWARD = "https://t.me/+bFZqr1KhvmlkNTRi"

DATA_FILE = "data.json"
PHOTO_PATH = "obuna_rasmi.jpg"

# Bot va dispatcher
bot = Bot(token=API_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

# Cache va in-memory data
bot_username = None
user_data = {}  # structure: {user_id: {"referrals": int, "got_reward": bool, "invited_by": int|None, "credited": bool, "is_subscribed": bool}}

# --- Data persistence helpers ---
def load_data():
    global user_data
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                user_data = json.load(f)
                # keys in JSON are strings, convert to int keys
                user_data = {int(k): v for k, v in user_data.items()}
        except Exception as e:
            print("Data load error:", e)
            user_data = {}
    else:
        user_data = {}

def save_data():
    try:
        # convert keys to str for JSON
        serializable = {str(k): v for k, v in user_data.items()}
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(serializable, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print("Data save error:", e)

# --- Utility functions ---
async def ensure_bot_username():
    global bot_username
    if not bot_username:
        me = await bot.get_me()
        bot_username = me.username or ""
    return bot_username

def ensure_user_record(user_id: int):
    if user_id not in user_data:
        user_data[user_id] = {
            "referrals": 0,
            "got_reward": False,
            "invited_by": None,
            "credited": False,       # whether inviter has been credited for this user
            "is_subscribed": False   # last known subscription status
        }
        save_data()

async def check_subscriptions(user_id: int) -> bool:
    """
    Tekshiradi: foydalanuvchi REQUIRED_CHANNELS ga obuna bo'lganmi.
    Agar bot kanallarda yetarli huquqqa ega bo'lmasa yoki boshqa xato bo'lsa False qaytaradi.
    """
    for channel in REQUIRED_CHANNELS:
        try:
            member = await bot.get_chat_member(chat_id=channel, user_id=user_id)
            if member.status not in ['member', 'creator', 'administrator']:
                return False
        except Exception as e:
            # Odatda xato bo'lsa (masalan bot kanal admin emas yoki private), False qaytaramiz
            print(f"Error checking membership for {channel}: {e}")
            return False
    return True

# --- Handlers ---
@dp.message(CommandStart())
async def start_handler(message: Message):
    user_id = message.from_user.id
    args = message.text.split()

    # Ensure user record exists
    ensure_user_record(user_id)

    # If started with a referral param, store inviter
    if len(args) > 1 and args[1].startswith("ref"):
        try:
            referrer_id = int(args[1][3:])
            if referrer_id != user_id:
                # if inviter absent in our DB, ensure their record exists (so they can get credit later)
                ensure_user_record(referrer_id)
                # only set invited_by if not set already (do not overwrite)
                if user_data[user_id]["invited_by"] is None:
                    user_data[user_id]["invited_by"] = referrer_id
                    save_data()
        except ValueError as e:
            print("Invalid referral id:", e)

    await show_main_menu(message, user_id)

async def show_main_menu(message_or_cb_message, user_id: int):
    """
    message_or_cb_message can be Message or CallbackQuery.message
    """
    # Ensure user exists
    ensure_user_record(user_id)

    is_subscribed = await check_subscriptions(user_id)
    # If subscription status changed from False->True, try credit the inviter
    prev_status = user_data[user_id].get("is_subscribed", False)
    if not prev_status and is_subscribed:
        # mark and credit inviter if applicable
        inviter = user_data[user_id].get("invited_by")
        if inviter and not user_data[user_id].get("credited", False):
            ensure_user_record(inviter)
            user_data[inviter]["referrals"] += 1
            user_data[user_id]["credited"] = True
            save_data()
            # Notify inviter
            try:
                await bot.send_message(
                    chat_id=inviter,
                    text=f"🎉 Yangi referal! Sizning referalingiz ({user_id}) kanallarga obuna bo'ldi.\n"
                         f"📊 Hoziqgi referallar: {user_data[inviter]['referrals']}/{MIN_REFERRALS}"
                )
                # Reward if reached
                if user_data[inviter]["referrals"] >= MIN_REFERRALS and not user_data[inviter]["got_reward"]:
                    await bot.send_message(
                        chat_id=inviter,
                        text=f"🎊 Tabriklaymiz! Siz {MIN_REFERRALS} ta referal to'pladingiz.\n\n"
                             f"Maxfiy kanal linki: {REFERRAL_REWARD}"
                    )
                    user_data[inviter]["got_reward"] = True
                    save_data()
            except Exception as e:
                print("Could not notify inviter:", e)

    # update stored subscription state
    user_data[user_id]["is_subscribed"] = is_subscribed
    save_data()

    # Build appropriate UI
    if not is_subscribed:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="1️⃣ TalkMore", url=f"https://t.me/{REQUIRED_CHANNELS[0][1:]}")],
            [InlineKeyboardButton(text="2️⃣ Listening Hub", url=f"https://t.me/{REQUIRED_CHANNELS[1][1:]}")],
            [InlineKeyboardButton(text="3️⃣ Speaking Saidbek", url=f"https://t.me/{REQUIRED_CHANNELS[2][1:]}")],
            [InlineKeyboardButton(text="✅ Obuna bo'ldim", callback_data="check_subs")]
        ])
        caption = "🎙 21 KUNLIK SPEAKING CHALLENGE 🎯\n\nQuyidagi 3 ta kanalga obuna bo'ling:"
        try:
            if isinstance(message_or_cb_message, Message):
                if os.path.exists(PHOTO_PATH):
                    await message_or_cb_message.answer_photo(photo=FSInputFile(PHOTO_PATH), caption=caption, reply_markup=keyboard)
                else:
                    await message_or_cb_message.answer(text=caption, reply_markup=keyboard)
            else:
                # callback.message
                if os.path.exists(PHOTO_PATH):
                    await message_or_cb_message.answer_photo(photo=FSInputFile(PHOTO_PATH), caption=caption, reply_markup=keyboard)
                else:
                    await message_or_cb_message.answer(text=caption, reply_markup=keyboard)
        except Exception as e:
            print("Error sending menu:", e)
            # fallback
            try:
                await message_or_cb_message.answer(text=caption, reply_markup=keyboard)
            except Exception as e2:
                print("Fallback send failed:", e2)
    else:
        # subscribed
        if user_id not in user_data:
            ensure_user_record(user_id)

        text = (f"✅ Siz barcha kanallarga obuna bo'lgansiz!\n\n"
                f"📊 Referallar: {user_data[user_id]['referrals']}/{MIN_REFERRALS}\n\n"
                f"{MIN_REFERRALS} ta do'stingizni taklif qiling va maxfiy kanal linkini oling!")

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📢 Referal havola olish", callback_data="get_referral")],
            [InlineKeyboardButton(text="✅ Referallarni tekshirish", callback_data="check_reward")]
        ])

        try:
            await message_or_cb_message.answer(text, reply_markup=keyboard)
        except Exception as e:
            print("Error sending subscribed menu:", e)

@dp.callback_query(F.data == "check_subs")
async def check_subscription_callback(callback: CallbackQuery):
    user_id = callback.from_user.id
    is_subscribed = await check_subscriptions(user_id)

    # If they just subscribed, credit inviter (handled in show_main_menu), so call that
    if is_subscribed:
        await callback.answer("✅ Siz barcha kanallarga obuna bo'lgansiz!", show_alert=True)
        await show_main_menu(callback.message, user_id)
    else:
        await callback.answer("❗ Iltimos, avval barcha kanallarga obuna bo'ling!", show_alert=True)

@dp.callback_query(F.data == "get_referral")
async def get_referral_handler(callback: CallbackQuery):
    user_id = callback.from_user.id
    ensure_user_record(user_id)
    username = await ensure_bot_username()
    referral_link = f"https://t.me/{username}?start=ref{user_id}"

    text = (f"🔗 Sizning referal havolangiz:\n{referral_link}\n\n"
            f"📊 Joriy referallar: {user_data[user_id]['referrals']}/{MIN_REFERRALS}\n\n"
            f"Do'stlaringiz ushbu havola orqali kirib, kanallarga obuna bo'lishlari kerak.")

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Havolani nusxalash", callback_data="copy_ref")],
        [InlineKeyboardButton(text="📤 Do'stlarga ulashish", switch_inline_query=f"Qo'shiling! {referral_link}")],
        [InlineKeyboardButton(text="🔙 Orqaga", callback_data="main_menu")]
    ])

    try:
        await callback.message.edit_text(text, reply_markup=keyboard)
    except Exception:
        # sometimes edit_text fails (e.g. message too old), fallback to send
        await callback.message.answer(text, reply_markup=keyboard)

@dp.callback_query(F.data == "check_reward")
async def check_reward_handler(callback: CallbackQuery):
    user_id = callback.from_user.id
    ensure_user_record(user_id)

    if user_data[user_id]["referrals"] >= MIN_REFERRALS:
        if not user_data[user_id]["got_reward"]:
            await bot.send_message(chat_id=user_id, text=f"🎊 Tabriklaymiz! Siz {MIN_REFERRALS} ta referal to'pladingiz.\n\nMaxfiy kanal linki: {REFERRAL_REWARD}")
            user_data[user_id]["got_reward"] = True
            save_data()
            await callback.answer("Maxfiy kanal linki yuborildi!", show_alert=True)
        else:
            await callback.answer("Siz allaqachon maxfiy kanal linkini olgansiz!", show_alert=True)
    else:
        await callback.answer(
            f"Sizda hali {user_data[user_id]['referrals']}/{MIN_REFERRALS} referal bor. "
            f"Yana {MIN_REFERRALS - user_data[user_id]['referrals']} ta do'stingizni taklif qiling!",
            show_alert=True
        )

@dp.callback_query(F.data == "copy_ref")
async def copy_referral_handler(callback: CallbackQuery):
    user_id = callback.from_user.id
    username = await ensure_bot_username()
    referral_link = f"https://t.me/{username}?start=ref{user_id}"
    await callback.answer(f"Havola nusxalandi: {referral_link}", show_alert=True)

@dp.callback_query(F.data == "main_menu")
async def back_to_main_menu(callback: CallbackQuery):
    await show_main_menu(callback.message, callback.from_user.id)

# Optional admin command to view a user's data (for debugging). Protect in production.
@dp.message(Command(commands=["debug"]))
async def debug_cmd(message: Message):
    # only allow yourself? For demo, allow chat id check (replace 12345678 with your id)
    allowed_admin = int(os.getenv("ADMIN_ID") or "0")
    if allowed_admin and message.from_user.id != allowed_admin:
        return
    await message.answer(f"Current data keys: {len(user_data)}")
    # send small sample
    sample = list(user_data.items())[:10]
    await message.answer(str(sample))

# --- Startup / main ---
async def on_startup():
    load_data()
    await ensure_bot_username()
    print("Bot started. Username:", bot_username)

async def main():
    await on_startup()
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())
