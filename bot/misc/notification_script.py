from datetime import datetime, date
from zoneinfo import ZoneInfo

from aiogram import Bot
from aiogram.types import InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.database.methods.get import get_all_user
from bot.misc.language import Localization, get_lang

_ = Localization.text


def subscription_button(lang):
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(
        text=_('renew_subscription_btn', lang),
        callback_data='buy_subscription'
    ))
    return builder.as_markup()


async def notify(bot: Bot):
    users = await get_all_user()
    moscow_tz = ZoneInfo('Europe/Moscow')
    today = datetime.now(moscow_tz).date()

    for user in users:
        # Пропускаем пользователей с активными платежами или без подписки
        if user.payment_method_id is not None or user.subscription is None:
            continue

        try:
            end_date = datetime.fromtimestamp(user.subscription, moscow_tz).date()
            days_left = (end_date - today).days

            if days_left == 1:
                lang = await get_lang(user.tgid)
                await bot.send_message(
                    user.tgid,
                    _('alert_to_renew_sub_in_one_day', lang),
                    reply_markup=subscription_button(lang)
                )
            elif days_left == 2:
                lang = await get_lang(user.tgid)
                await bot.send_message(
                    user.tgid,
                    _('alert_to_renew_sub_in_two_days', lang),
                    reply_markup=subscription_button(lang)
                )
            elif days_left == 3:
                lang = await get_lang(user.tgid)
                await bot.send_message(
                    user.tgid,
                    _('alert_to_renew_sub_in_three_days', lang),
                    reply_markup=subscription_button(lang)
                )

        except Exception as e:
            print(f"Error processing user {user.tgid}: {e}")
            continue