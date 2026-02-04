import asyncio
import sys
sys.path.insert(0, "/app")

from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from bot.misc.util import CONFIG
from bot.database.main import engine
from bot.database.models.main import Persons
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

async def send_promo_to_all():
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
    
    # Get users with 1 or 3 month subscriptions
    async with AsyncSession(autoflush=False, bind=engine()) as db:
        stmt = select(Persons).filter(
            Persons.subscription_active == True,
            Persons.subscription_months.in_([1, 3])
        )
        result = await db.execute(stmt)
        users = result.scalars().all()
    
    print(f"📤 Отправляем {len(users)} пользователям...")
    
    success = 0
    errors = 0
    
    for user in users:
        try:
            await bot.send_message(
                chat_id=user.tgid,
                text=text,
                reply_markup=keyboard,
                parse_mode="HTML"
            )
            success += 1
            print(f"✅ {success}/{len(users)} - Sent to {user.tgid}")
        except Exception as e:
            errors += 1
            print(f"❌ Error for {user.tgid}: {e}")
        
        # Delay to avoid flood
        await asyncio.sleep(0.1)
    
    await bot.session.close()
    
    print(f"\n📊 Результат:")
    print(f"✅ Отправлено: {success}")
    print(f"❌ Ошибок: {errors}")

if __name__ == "__main__":
    asyncio.run(send_promo_to_all())
