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
    kb = InlineKeyboardBuilder()
    if config.tg_wallet_token != "":
        kb.button(
            text=_('payments_wallet_pay_btn', lang),
            callback_data=ChoosingPayment(payment='WalletPay', price=price, days_count=days_count,
                                          price_on_db=price_on_db))
    if config.yookassa_shop_id != "" and config.yookassa_secret_key != "":
        kb.button(
            text=_('payments_yookassa_btn', lang),
            callback_data=ChoosingPayment(payment='KassaSmart', price=price, days_count=days_count,
                                          price_on_db=price_on_db))
    if config.cryptomus_key != "" and config.cryptomus_uuid != "":
        kb.button(
            text=_('payments_cryptomus_btn', lang),
            callback_data=ChoosingPayment(payment='Cryptomus', price=price, days_count=days_count,
                                          price_on_db=price_on_db))
    if config.crypto_bot_api != '':
        kb.button(
            text='🦋 CryptoBot',
            callback_data=ChoosingPayment(payment='CryptoBot', price=price, days_count=days_count,
                                          price_on_db=price_on_db))
    if config.lava_token_secret != "" and config.lava_id_project != "":
        kb.button(
            text=_('payments_lava_btn', lang),
            callback_data=ChoosingPayment(payment='Lava', price=price, days_count=days_count, price_on_db=price_on_db)
        )
    if config.token_stars != 'off':
        kb.button(
            text='Stars ⭐️',
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
    kb = InlineKeyboardBuilder()
    user = await get_person(tg_id)
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
        kb.button(text=_('turn_off_autopay_btn', lang), callback_data='turn_off_autopay')
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
    kb.button(
        text=_('write_the_admin_btn', lang),
        callback_data='message_admin'
    )
    kb.adjust(1)
    return kb.as_markup()


async def promo_code_button(lang) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text=_('write_the_promo_btn', lang), callback_data='promo_code')
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


async def user_menu_inline(person, lang) -> InlineKeyboardMarkup:
    """
    Inline-версия главного меню (кнопки в окне сообщения)
    """
    import time
    from datetime import datetime

    kb = InlineKeyboardBuilder()
    time_sub = datetime.utcfromtimestamp(
        int(person.subscription) + CONFIG.UTC_time * 3600).strftime(
        '%d.%m.%Y %H:%M')
    time_now = int(time.time())

    # 1. Subscription info
    if int(person.subscription) >= time_now:
        kb.button(
            text=_('subscription_time_btn', lang).format(time=time_sub),
            callback_data='subscription_info'
        )
    else:
        kb.button(
            text=_('subscription_not_time_btn', lang).format(time=time_sub),
            callback_data='subscription_info'
        )

    # 2. Main connection buttons
    kb.button(
        text="📲 Subscription URL",
        callback_data=MainMenuAction(action='subscription_url')
    )
    kb.button(
        text="🔑 Outline VPN",
        callback_data=MainMenuAction(action='outline')
    )

    # 3. Subscription management
    kb.button(
        text=_('subscription_btn', lang),
        callback_data=MainMenuAction(action='subscription')
    )

    # 4. Referral and bonus
    kb.button(
        text=_('affiliate_btn', lang),
        callback_data=MainMenuAction(action='referral')
    )
    kb.button(
        text=_('bonus_btn', lang),
        callback_data=MainMenuAction(action='bonus')
    )

    # 5. Info and settings
    kb.button(
        text=_('about_vpn_btn', lang),
        callback_data=MainMenuAction(action='about')
    )
    kb.button(
        text=_('language_btn', lang),
        callback_data=MainMenuAction(action='language')
    )

    # 6. Help
    kb.button(
        text=_('help_btn', lang),
        callback_data=MainMenuAction(action='help')
    )

    # 7. Admin panel
    if person.tgid in CONFIG.admins_ids:
        kb.button(
            text=_('admin_panel_btn', lang),
            callback_data=MainMenuAction(action='admin')
        )

    kb.adjust(1)
    return kb.as_markup()
