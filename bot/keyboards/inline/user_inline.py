from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.database.methods.get import get_person, get_super_offer
from bot.database.models.main import SuperOffer
from bot.misc.callbackData import (
    ChoosingMonths,
    ChoosingPrise,
    ChoosingPayment,
    ChooseServer,
    MessageAdminUser, ChoosingLang, ChooseTypeVpn, ChoosedSuperOffer,
    DownloadClient, DownloadHiddify, MainMenuAction
)
from bot.misc.language import Localization
from bot.misc.util import CONFIG

_ = Localization.text


async def choosing_payment_option_keyboard(config, lang, price: int, days_count: int,
                                           price_on_db: int) -> InlineKeyboardMarkup:
    from bot.misc.callbackData import MainMenuAction

    kb = InlineKeyboardBuilder()
    if config.tg_wallet_token != "":
        kb.button(
            text='👛 Кошелёк                            ',
            callback_data=ChoosingPayment(payment='WalletPay', price=price, days_count=days_count,
                                          price_on_db=price_on_db))
    if config.yookassa_shop_id != "" and config.yookassa_secret_key != "":
        kb.button(
            text='🇷🇺 Юкасса                            ',
            callback_data=ChoosingPayment(payment='KassaSmart', price=price, days_count=days_count,
                                          price_on_db=price_on_db))
    if config.cryptomus_key != "" and config.cryptomus_uuid != "":
        kb.button(
            text='🎲 Cryptomus                         ',
            callback_data=ChoosingPayment(payment='Cryptomus', price=price, days_count=days_count,
                                          price_on_db=price_on_db))
    if config.crypto_bot_api != '':
        kb.button(
            text='🦋 CryptoBot                          ',
            callback_data=ChoosingPayment(payment='CryptoBot', price=price, days_count=days_count,
                                          price_on_db=price_on_db))
    if config.lava_token_secret != "" and config.lava_id_project != "":
        kb.button(
            text='🌋 Lava                                 ',
            callback_data=ChoosingPayment(payment='Lava', price=price, days_count=days_count, price_on_db=price_on_db)
        )
    if config.token_stars != 'off':
        kb.button(
            text='⭐️ Stars                                ',
            callback_data=ChoosingPayment(payment='Stars', price=price, days_count=days_count, price_on_db=price_on_db)
        )
    if (
            config.yookassa_shop_id == ""
            and config.tg_wallet_token == ""
            and config.lava_token_secret == ""
            and config.cryptomus_key == ""
            and config.crypto_bot_api == ""
            and config.token_stars == 'off'
    ):
        kb.button(text=_('payments_not_btn_1', lang), callback_data='none')
        kb.button(text=_('payments_not_btn_2', lang), callback_data='none')

    # Добавляем кнопку "Назад"
    kb.button(
        text="⬅️ Назад",
        callback_data=MainMenuAction(action='subscription')
    )

    kb.adjust(1)
    return kb.as_markup()

async def deposit_amount(CONGIG) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for deposit in CONGIG.deposit:
        kb.button(text=f'{deposit} ₽', callback_data='Rub')
    kb.adjust(1)
    return kb.as_markup()


async def choose_type_vpn() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text='Outline 🪐', callback_data=ChooseTypeVpn(type_vpn=0))
    kb.button(text='Vless 🐊', callback_data=ChooseTypeVpn(type_vpn=1))
    kb.button(text='ShadowSocks 🦈', callback_data=ChooseTypeVpn(type_vpn=2))
    kb.adjust(2)
    return kb.as_markup()


async def renew(CONFIG, lang, tg_id: int, payment_method_id) -> InlineKeyboardMarkup:
    from aiogram.types import InlineKeyboardButton
    import time
    kb = InlineKeyboardBuilder()
    user = await get_person(tg_id)
    time_now = int(time.time())

    # Кнопка пробного периода (для новых пользователей)
    if not user.free_trial_used and not user.banned and int(user.subscription) <= time_now:
        kb.button(
            text="🎁 3 дня бесплатно",
            callback_data=MainMenuAction(action='free_trial')
        )

    if user.subscription_price is None:
        supper_offer: SuperOffer = await get_super_offer()
        if supper_offer is not None:
            kb.button(
                text=_('to_super_offer_btn', lang)
                .format(count_days=supper_offer.days, price=supper_offer.price),
                callback_data=ChoosingMonths(
                    price=supper_offer.price,
                    days_count=supper_offer.days,
                    price_on_db=CONFIG.month_cost[0]
                )
            )
    months = {1: 0, 3: 1, 6: 2, 12: 3}
    for month, price_id in months.items():
        kb.button(
            text=_('to_extend_month_btn', lang)
            .format(count_month=month, price=CONFIG.month_cost[price_id]),
            callback_data=ChoosingMonths(
                price=CONFIG.month_cost[price_id],
                days_count=month * 31,
                price_on_db=CONFIG.month_cost[price_id]
            )
        )
    if payment_method_id is not None:
        kb.button(text="🔕 Отключить автооплату", callback_data='turn_off_autopay')
    # Кнопка промокода
    kb.button(text="🏷 У меня промокод", callback_data='enter_promo_code')
    # Кнопка оферты
    if CONFIG.offer_url:
        kb.row(InlineKeyboardButton(text="📋 Договор оферты", url=CONFIG.offer_url))
    kb.adjust(1)
    return kb.as_markup()


async def price_menu(CONGIG, payment) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for price in CONGIG.deposit:
        kb.button(
            text=f'{price} ₽',
            callback_data=ChoosingPrise(
                price=int(price),
                payment=payment
            )
        )
    kb.adjust(1)
    return kb.as_markup()


async def wallet_pay(order, lang) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text='👛 Pay via Wallet', url=order.pay_link)
    kb.button(
        text=_('instruction_payment_btn', lang),
        url=_('instruction_walletpay', lang)
    )
    kb.adjust(1)
    return kb.as_markup()


async def choosing_lang() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for lang, cls in Localization.ALL_Languages.items():
        kb.button(text=cls, callback_data=ChoosingLang(lang=lang))
    kb.adjust(1)
    return kb.as_markup()


async def pay_and_check(link_invoice: str, lang) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text=_('user_pay_sub_btn', lang), url=link_invoice)
    #kb.button(text=_('user_offer_agreement_btn', lang), url=CONFIG.offer_url)
    kb.adjust(1)
    return kb.as_markup()


async def instruction_manual(type_vpn, lang) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()

    # Добавить кнопки скачивания для Outline
    if type_vpn == 0:
        kb.button(text='📥 iPhone', callback_data=DownloadClient(platform='iphone'))
        kb.button(text='📥 Android', callback_data=DownloadClient(platform='android'))
        kb.button(text='📥 Windows', callback_data=DownloadClient(platform='windows'))
        kb.button(text='📥 Mac OS', callback_data=DownloadClient(platform='macos'))
        kb.button(text='📥 Linux', callback_data=DownloadClient(platform='linux'))
    # Добавить кнопки скачивания для VLESS и Shadowsocks (Hiddify)
    elif type_vpn == 1 or type_vpn == 2:
        kb.button(text='📥 iPhone', callback_data=DownloadHiddify(platform='iphone'))
        kb.button(text='📥 Android', callback_data=DownloadHiddify(platform='android'))
        kb.button(text='📥 Windows', callback_data=DownloadHiddify(platform='windows'))
        kb.button(text='📥 Mac OS', callback_data=DownloadHiddify(platform='macos'))
        kb.button(text='📥 Linux', callback_data=DownloadHiddify(platform='linux'))
    else:
        raise Exception(f'The wrong type VPN - {type_vpn}')

    kb.adjust(1)
    return kb.as_markup()


async def share_link(ref_link, lang, ref_balance=None) -> InlineKeyboardMarkup:
    link = f'https://t.me/share/url?url={ref_link}'
    kb = InlineKeyboardBuilder()
    kb.button(text=_('user_share_btn', lang), url=link)
    if ref_balance is not None:
        if ref_balance >= CONFIG.minimum_withdrawal_amount:
            kb.button(
                text=_('withdraw_funds_btn', lang),
                callback_data='withdrawal_of_funds'
            )
        else:
            kb.button(
                text=_('enough_funds_withdraw_btn', lang),
                callback_data='none'
            )

    # Кнопки для скачивания статистики
    kb.button(
        text="📊 Скачать статистику по клиентам",
        callback_data='download_affiliate_stats'
    )
    kb.button(
        text="💰 Скачать статистику по выплатам",
        callback_data='download_withdrawal_stats'
    )

    # Кнопка с документацией
    kb.button(
        text="📖 Условия реферальной программы",
        url="https://heavy-weight-a87.notion.site/NoBorderVPN-18d2ac7dfb078050a322df104dcaa4c2"
    )

    kb.button(
        text="💬 Написать в поддержку",
        url="https://t.me/VPN_YouSupport_bot"
    )

    # Добавляем кнопку "Назад"
    from bot.misc.callbackData import MainMenuAction
    kb.button(
        text="⬅️ Назад",
        callback_data=MainMenuAction(action='bonuses').pack()
    )

    kb.adjust(1)
    return kb.as_markup()


async def promo_code_button(lang) -> InlineKeyboardMarkup:
    from bot.misc.callbackData import MainMenuAction

    kb = InlineKeyboardBuilder()
    kb.button(text=_('write_the_promo_btn', lang), callback_data='promo_code')

    # Добавляем кнопку "Назад"
    kb.button(
        text="⬅️ Назад",
        callback_data=MainMenuAction(action='bonuses').pack()
    )

    kb.adjust(1)
    return kb.as_markup()


async def choose_server(
        all_server,
        active_server_id,
        lang
) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for server in all_server:
        text_button = \
            f'🟢{server.name}🟢' \
                if server.id == active_server_id \
                else server.name
        kb.button(
            text=text_button,
            callback_data=ChooseServer(id_server=server.id)
        )
    kb.button(
        text=_('back_type_vpn', lang),
        callback_data='back_type_vpn'
    )
    kb.adjust(1)
    return kb.as_markup()


async def message_admin_user(tgid_user, lang) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(
        text=_('admin_user_send_reply_btn', lang),
        callback_data=MessageAdminUser(id_user=tgid_user)
    )
    kb.adjust(1)
    return kb.as_markup()


async def user_menu_inline(person, lang, bot=None) -> InlineKeyboardMarkup:
    """
    Inline-версия главного меню (кнопки в окне сообщения)
    """
    import time
    from datetime import datetime
    from aiogram.utils.deep_linking import create_start_link
    from urllib.parse import quote

    kb = InlineKeyboardBuilder()
    time_now = int(time.time())

    # 0. Admin panel (в начале для админов)
    if person.tgid in CONFIG.admins_ids:
        kb.button(
            text="⚙️ Админ панель",
            callback_data=MainMenuAction(action='admin')
        )

    # 1. Оплатить VPN
    kb.button(
        text="💳 Оплатить VPN",
        callback_data=MainMenuAction(action='subscription')
    )

    # 3. Подключить VPN
    kb.button(
        text="🔑 Подключить VPN",
        callback_data=MainMenuAction(action='my_keys')
    )

    # 4. Бонусы и друзья (объединили referral + bonus)
    kb.button(
        text="💰 Бонусы и друзья",
        callback_data=MainMenuAction(action='bonuses')
    )

    # 5. Помощь
    kb.button(
        text="❓ Помощь и поддержка",
        url="https://t.me/VPN_YouSupport_bot"
    )

    # 6. Пригласить друга (реферальная ссылка)
    if bot is not None:
        try:
            referral_link = await create_start_link(bot, str(person.tgid), encode=True)
            share_text = "🔒 Лучший VPN для обхода блокировок! Попробуй:"
            share_url = f"https://t.me/share/url?url={quote(referral_link)}&text={quote(share_text)}"
            kb.button(
                text="💸 Делись — получай 50%",
                url=share_url
            )
        except Exception:
            pass  # Если не удалось создать ссылку - не показываем кнопку

    kb.adjust(1)
    return kb.as_markup()
