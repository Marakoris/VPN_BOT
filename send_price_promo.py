import asyncio
import sys
sys.path.insert(0, "/app")

from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from bot.misc.util import CONFIG

async def send_promo_message(chat_id: int):
    bot = Bot(token=CONFIG.tg_token)
    
    text = """🎉 <b>Снизили цены на длинные подписки!</b>

Теперь выгоднее брать надолго:

📦 <b>6 месяцев — 600₽</b> <s>800₽</s>
   → 100₽/мес, экономия 200₽

📦 <b>12 месяцев — 999₽</b> <s>1600₽</s>
   → 83₽/мес, экономия 601₽

💡 При следующем продлении можете выбрать новый период — скидка применится автоматически.

Спасибо что с нами! 🚀"""

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Перейти к оплате", callback_data="main_menu:subscription_url")],
    ])
    
    try:
        await bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        print(f"✅ Message sent to {chat_id}")
    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        await bot.session.close()

if __name__ == "__main__":
    chat_id = int(sys.argv[1]) if len(sys.argv) > 1 else 870499087
    asyncio.run(send_promo_message(chat_id))
