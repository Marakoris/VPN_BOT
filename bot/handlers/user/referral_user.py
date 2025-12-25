import asyncio
import logging

from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import Message, CallbackQuery, FSInputFile, InputMediaDocument, BufferedInputFile, ReplyKeyboardRemove
from aiogram.utils.deep_linking import create_start_link
from aiogram.utils.formatting import Text, Italic
from sqlalchemy.exc import InvalidRequestError

from bot.database.methods.get import (
    get_promo_code,
    get_person,
    get_count_referral_user, get_referral_balance, export_affiliate_statistics_to_excel,
    export_withdrawal_statistics_to_excel
)
from bot.database.methods.insert import add_withdrawal
from bot.database.methods.update import (
    add_pomo_code_person,
    reduce_referral_balance_person, add_time_person
)
from bot.keyboards.inline.user_inline import (
    share_link,
    promo_code_button,
    message_admin_user
)
from bot.keyboards.reply.user_reply import back_menu, user_menu
from bot.misc.language import Localization, get_lang
from bot.misc.util import CONFIG

log = logging.getLogger(__name__)

referral_router = Router()

_ = Localization.text
btn_text = Localization.get_reply_button


class ActivatePromocode(StatesGroup):
    input_promo = State()


class WithdrawalFunds(StatesGroup):
    input_amount = State()
    payment_method = State()
    communication = State()
    input_message_admin = State()


async def get_referral_link(message):
    return await create_start_link(
        message.bot,
        str(message.from_user.id),
        encode=True
    )


async def send_admins(bot: Bot, amount):
    for admin_id in CONFIG.admins_ids:
        text = _(
            'withdrawal_funds_has_been',
            await get_lang(admin_id)
        ).format(amount=amount)
        try:
            await bot.send_message(text=text,
                                   chat_id=admin_id,
                                   )
        except Exception as e:
            log.error(f"Can't send message to the admin with tg_id {admin_id}: {e}")

        await asyncio.sleep(0.01)


@referral_router.message(Command("bonus"))
@referral_router.message(F.text.in_(btn_text('bonus_btn')))
async def give_handler(m: Message, state: FSMContext) -> None:
    lang = await get_lang(m.from_user.id, state)
    link_ref = await get_referral_link(m)
    message_text = Text(
        _('your_referral_link', lang).format(link_ref=link_ref),
        _('referral_message', lang)
    )
    await m.answer(
        **message_text.as_kwargs(),
        reply_markup=await share_link(link_ref, lang)
    )
    await m.answer(
        _('referral_promo_code', lang),
        reply_markup=await promo_code_button(lang)
    )


@referral_router.message(Command("partnership"))
@referral_router.message(F.text.in_(btn_text('affiliate_btn')))
async def referral_system_handler(m: Message, state: FSMContext) -> None:
    lang = await get_lang(m.from_user.id, state)
    count_referral_user = await get_count_referral_user(m.from_user.id)
    balance = await get_referral_balance(m.from_user.id)
    link_ref = await get_referral_link(m)
    message_text = (
        _('referral_menu_text', lang)
        .format(
            link_ref=link_ref,
            referral_percent=CONFIG.referral_percent,
            minimum_amount=CONFIG.minimum_withdrawal_amount,
            count_referral_user=count_referral_user,
            balance=balance,
            link_referral_conditions="https://heavy-weight-a87.notion.site/NoBorderVPN-18d2ac7dfb078050a322df104dcaa4c2",
            link_free_promotion="https://heavy-weight-a87.notion.site/18e2ac7dfb0780728d6ddfa0c8f88410",
            link_paid_promotion="https://heavy-weight-a87.notion.site/NoBorderVPN-18e2ac7dfb078096a214cbe65782b386",
        )
    )
    await m.answer_photo(
        photo=FSInputFile('bot/img/referral_program.jpg'),
        caption=message_text,
        reply_markup=await share_link(link_ref, lang, balance)
    )


@referral_router.callback_query(F.data == 'promo_code')
async def successful_payment(call: CallbackQuery, state: FSMContext):
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from aiogram.types import InlineKeyboardButton
    from bot.misc.callbackData import MainMenuAction

    lang = await get_lang(call.from_user.id, state)

    # Скрываем старую reply клавиатуру
    hide_msg = await call.message.answer("⏳", reply_markup=ReplyKeyboardRemove())
    await hide_msg.delete()

    # Создаем inline клавиатуру с кнопкой "Назад"
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(
        text="⬅️ Назад",
        callback_data=MainMenuAction(action='bonus').pack()
    ))

    await call.message.answer(
        _('input_promo_user', lang),
        reply_markup=kb.as_markup()
    )
    await call.answer()
    await state.set_state(ActivatePromocode.input_promo)


@referral_router.callback_query(F.data == 'withdrawal_of_funds')
async def withdrawal_of_funds(call: CallbackQuery, state: FSMContext):
    lang = await get_lang(call.from_user.id, state)
    await call.message.answer(
        _('input_amount_withdrawal_min', lang)
        .format(minimum_amount=CONFIG.minimum_withdrawal_amount),
        reply_markup=await back_menu(lang)
    )
    await call.answer()
    await state.set_state(WithdrawalFunds.input_amount)


@referral_router.message(WithdrawalFunds.input_amount)
async def payment_method(message: Message, state: FSMContext):
    lang = await get_lang(message.from_user.id, state)
    amount = message.text.strip()
    try:
        amount = int(amount)
    except Exception as e:
        log.info(e, 'incorrect amount')
    balance = await get_referral_balance(message.from_user.id)
    if (
            type(amount) is not int or
            CONFIG.minimum_withdrawal_amount > amount or
            amount > balance
    ):
        await message.answer(_('error_incorrect', lang))
        return
    await state.update_data(amount=amount)
    await message.answer(_('where_transfer_funds', lang))
    await state.set_state(WithdrawalFunds.payment_method)


@referral_router.message(WithdrawalFunds.payment_method)
async def choosing_connect(message: Message, state: FSMContext):
    lang = await get_lang(message.from_user.id, state)
    await state.update_data(payment_info=message.text.strip())
    await message.answer(_('how_i_contact_you', lang))
    await state.set_state(WithdrawalFunds.communication)


@referral_router.message(WithdrawalFunds.communication)
async def save_payment_method(message: Message, state: FSMContext):
    lang = await get_lang(message.from_user.id, state)
    communication = message.text.strip()
    data = await state.get_data()
    payment_info = data['payment_info']
    amount = data['amount']
    person = await get_person(message.from_user.id)
    try:
        await add_withdrawal(
            amount=amount,
            payment_info=payment_info,
            tgid=message.from_user.id,
            communication=communication
        )
    except Exception as e:
        log.error(e, 'error add withdrawal')
        await message.answer(_('error_send_admin', lang))
        await state.clear()
    if await reduce_referral_balance_person(amount, message.from_user.id):
        await message.answer(
            _('referral_system_success', lang),
            reply_markup=await user_menu(person, lang)
        )
        await send_admins(message.bot, amount)
    else:
        await message.answer(
            _('error_withdrawal_funds_not_balance', lang),
            reply_markup=await user_menu(person, lang)
        )
    await state.clear()


@referral_router.message(ActivatePromocode.input_promo)
async def promo_check(message: Message, state: FSMContext):
    from bot.keyboards.inline.user_inline import user_menu_inline
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from aiogram.types import InlineKeyboardButton
    from bot.misc.callbackData import MainMenuAction

    lang = await get_lang(message.from_user.id, state)
    text_promo = message.text.strip()
    person = await get_person(message.from_user.id)
    promo_code = await get_promo_code(text_promo)

    if promo_code is not None:
        try:
            add_days_number = promo_code.add_days
            await add_pomo_code_person(
                message.from_user.id,
                promo_code
            )
            await add_time_person(person.tgid, add_days_number * CONFIG.COUNT_SECOND_DAY)
            await message.answer(
                _('promo_success_user', lang).format(amount=add_days_number),
                reply_markup=await user_menu_inline(person, lang, message.bot)
            )
            await state.clear()
        except InvalidRequestError:
            # Промокод уже использован - предлагаем попробовать другой
            kb = InlineKeyboardBuilder()
            kb.row(InlineKeyboardButton(
                text="🔄 Попробовать другой промокод",
                callback_data='promo_code'
            ))
            kb.row(InlineKeyboardButton(
                text="⬅️ Назад в меню",
                callback_data=MainMenuAction(action='back_to_menu').pack()
            ))

            await message.answer(
                _('uses_promo_user', lang),
                reply_markup=kb.as_markup()
            )
            # НЕ очищаем state, чтобы пользователь мог повторить попытку
    else:
        # Промокод не найден - предлагаем попробовать снова
        kb = InlineKeyboardBuilder()
        kb.row(InlineKeyboardButton(
            text="🔄 Попробовать снова",
            callback_data='promo_code'
        ))
        kb.row(InlineKeyboardButton(
            text="⬅️ Назад в меню",
            callback_data=MainMenuAction(action='back_to_menu').pack()
        ))

        await message.answer(
            _('referral_promo_code_none', lang),
            reply_markup=kb.as_markup()
        )
        # НЕ очищаем state, чтобы пользователь мог повторить попытку


@referral_router.callback_query(F.data == 'message_admin')
async def message_admin(callback_query: CallbackQuery, state: FSMContext):
    lang = await get_lang(callback_query.from_user.id, state)
    await callback_query.message.answer(
        _('input_message_user_admin', lang),
        reply_markup=await back_menu(lang)
    )
    await state.set_state(WithdrawalFunds.input_message_admin)
    await callback_query.answer()


@referral_router.message(WithdrawalFunds.input_message_admin)
async def input_message_admin(message: Message, state: FSMContext):
    lang = await get_lang(message.from_user.id, state)
    person = await get_person(message.from_user.id)
    try:
        text = Text(
            _('message_user_admin', lang)
            .format(
                fullname=person.fullname,
                username=person.username,
                telegram_id=person.tgid
            ),
            Italic(message.text.strip())
        )

        for admin_id in CONFIG.admins_ids:
            try:
                await message.bot.send_message(
                    admin_id, **text.as_kwargs(),
                    reply_markup=await message_admin_user(person.tgid, lang)
                )
            except Exception as e:
                log.error(f"Can't send message to the admin with tg_id {admin_id}: {e}")

            await asyncio.sleep(0.01)

        await message.answer(
            _('message_user_admin_success', lang),
            reply_markup=await user_menu(person, lang)
        )
    except Exception as e:
        await message.answer(
            _('error_message_user_admin_success', lang),
            reply_markup=await user_menu(person, lang)
        )
        log.error(e, 'Error admin message')
    await state.clear()


@referral_router.callback_query(F.data == 'download_affiliate_stats')
async def download_affiliate_statistics(call: CallbackQuery):
    """Скачать статистику по привлечённым клиентам"""
    await call.answer("⏳ Генерирую файл...")

    try:
        # Генерируем Excel файл со статистикой
        affiliate_clients = await export_affiliate_statistics_to_excel(call.from_user.id)
        doc = BufferedInputFile(
            file=affiliate_clients.getvalue(),
            filename="affiliate_clients.xlsx"
        )

        # Отправляем файл
        await call.message.answer_document(
            document=doc,
            caption="📊 <b>Статистика по привлечённым клиентам</b>\n\n"
                    "В файле содержится информация о ваших рефералах",
            parse_mode="HTML"
        )
    except Exception as e:
        log.error(f"Error generating affiliate stats: {e}")
        await call.message.answer("❌ Ошибка при генерации файла. Попробуйте позже.")


@referral_router.callback_query(F.data == 'download_withdrawal_stats')
async def download_withdrawal_statistics(call: CallbackQuery):
    """Скачать статистику по выплатам"""
    await call.answer("⏳ Генерирую файл...")

    try:
        # Генерируем Excel файл со статистикой
        withdrawals = await export_withdrawal_statistics_to_excel(call.from_user.id)
        doc = BufferedInputFile(
            file=withdrawals.getvalue(),
            filename="withdrawals.xlsx"
        )

        # Отправляем файл
        await call.message.answer_document(
            document=doc,
            caption="💰 <b>Статистика по выплатам</b>\n\n"
                    "В файле содержится история ваших выплат",
            parse_mode="HTML"
        )
    except Exception as e:
        log.error(f"Error generating withdrawal stats: {e}")
        await call.message.answer("❌ Ошибка при генерации файла. Попробуйте позже.")
