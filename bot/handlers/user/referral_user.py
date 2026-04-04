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


class WithdrawalReceipt(StatesGroup):
    """State for admin to upload payment receipt"""
    waiting_receipt = State()


async def get_referral_link(message):
    return await create_start_link(
        message.bot,
        str(message.from_user.id),
        encode=True
    )


async def send_admins(bot: Bot, amount, person, payment_info, communication, withdrawal_id: int):
    """Отправка уведомления админам о запросе на вывод средств"""
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from bot.misc.callbackData import WithdrawalConfirm

    username_str = f"@{person.username.replace('@', '')}" if person.username and person.username != '@None' else f"ID: {person.tgid}"

    text = (
        f"💸 <b>Запрос на вывод средств</b>\n\n"
        f"👤 <b>От кого:</b> {person.fullname} ({username_str})\n"
        f"🆔 <b>Telegram ID:</b> <code>{person.tgid}</code>\n"
        f"💰 <b>Сумма:</b> {amount} ₽\n\n"
        f"🏦 <b>Куда переводить:</b>\n{payment_info}\n\n"
        f"📞 <b>Связь:</b>\n{communication}\n\n"
        f"💼 <b>Остаток баланса:</b> {person.referral_balance - amount} ₽"
    )

    # Кнопка подтверждения выплаты
    kb = InlineKeyboardBuilder()
    kb.button(
        text="✅ Выплачено",
        callback_data=WithdrawalConfirm(action='confirm', withdrawal_id=withdrawal_id, user_tgid=person.tgid)
    )
    kb.adjust(1)

    for admin_id in CONFIG.admins_ids:
        try:
            await bot.send_message(
                chat_id=admin_id,
                text=text,
                parse_mode="HTML",
                reply_markup=kb.as_markup()
            )
        except Exception as e:
            log.error(f"Can't send message to the admin with tg_id {admin_id}: {e}")

        await asyncio.sleep(0.01)


@referral_router.message(Command("bonus"))
@referral_router.message(F.text.in_(btn_text('bonus_btn')))
async def give_handler(m: Message, state: FSMContext) -> None:
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from aiogram.types import InlineKeyboardButton
    from bot.misc.callbackData import MainMenuAction

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

    # Сразу показываем ввод промокода с кнопкой "Назад"
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(
        text="⬅️ Назад",
        callback_data=MainMenuAction(action='back_to_menu').pack()
    ))
    await m.answer(
        _('referral_promo_code', lang),
        reply_markup=kb.as_markup()
    )
    # Сразу устанавливаем state для ввода промокода
    await state.set_state(ActivatePromocode.input_promo)


@referral_router.message(Command("partnership"))
@referral_router.message(F.text.in_(btn_text('affiliate_btn')))
async def referral_system_handler(m: Message, state: FSMContext) -> None:
    lang = await get_lang(m.from_user.id, state)
    from urllib.parse import quote
    from aiogram.utils.keyboard import InlineKeyboardBuilder

    person = await get_person(m.from_user.id)
    balance = await get_referral_balance(m.from_user.id)
    count_referral_user = await get_count_referral_user(m.from_user.id)
    link_ref = await get_referral_link(m)

    kb = InlineKeyboardBuilder()

    # Ссылка на ЛК
    if person and person.subscription_token:
        dashboard_url = (
            f"{CONFIG.subscription_api_url}/dashboard/auth/token"
            f"?t={quote(person.subscription_token, safe='')}"
            f"&next=/dashboard/referral"
        )
        kb.button(text="📊 Открыть личный кабинет", url=dashboard_url)

    # Кнопка «Поделиться»
    share_url = f"https://t.me/share/url?url={link_ref}"
    kb.button(text=_('user_share_btn', lang), url=share_url)
    kb.adjust(1)

    await m.answer(
        f"👥 <b>Реферальная программа</b>\n\n"
        f"Ваша ссылка: <code>{link_ref}</code>\n"
        f"Приглашено: <b>{count_referral_user}</b> | Баланс: <b>{balance}₽</b>\n\n"
        f"Подробная статистика, воронка, UTM-метки и вывод средств — в личном кабинете 👇",
        reply_markup=kb.as_markup(),
        parse_mode="HTML"
    )


@referral_router.callback_query(F.data == 'promo_code')
async def successful_payment(call: CallbackQuery, state: FSMContext):
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from aiogram.types import InlineKeyboardButton
    from bot.misc.callbackData import MainMenuAction

    lang = await get_lang(call.from_user.id, state)

    # Создаем inline клавиатуру с кнопкой "Назад"
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(
        text="⬅️ Назад",
        callback_data=MainMenuAction(action='bonus').pack()
    ))

    # Редактируем текущее сообщение, убирая кнопку "Ввести промокод"
    await call.message.edit_text(
        _('referral_promo_code', lang),
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
    withdrawal_id = None
    try:
        withdrawal_id = await add_withdrawal(
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
        await send_admins(message.bot, amount, person, payment_info, communication, withdrawal_id)
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

    from datetime import datetime

    lang = await get_lang(message.from_user.id, state)
    text_promo = message.text.strip()
    person = await get_person(message.from_user.id)
    promo_code = await get_promo_code(text_promo)

    if promo_code is not None:
        # Проверяем срок действия промокода
        if promo_code.expires_at and promo_code.expires_at < datetime.now():
            kb = InlineKeyboardBuilder()
            kb.row(InlineKeyboardButton(
                text="🔄 Попробовать другой",
                callback_data='promo_code'
            ))
            kb.row(InlineKeyboardButton(
                text="⬅️ Назад в меню",
                callback_data=MainMenuAction(action='back_to_menu').pack()
            ))
            await message.answer(
                "❌ Срок действия этого промокода истёк",
                reply_markup=kb.as_markup()
            )
            return

        try:
            add_days_number = promo_code.add_days
            await add_pomo_code_person(
                message.from_user.id,
                promo_code
            )
            await add_time_person(person.tgid, add_days_number * CONFIG.COUNT_SECOND_DAY)

            # Активируем подписку автоматически
            from bot.misc.subscription import activate_subscription
            try:
                await activate_subscription(person.tgid, include_outline=True)
            except Exception as e:
                log.warning(f"Failed to activate subscription after promo: {e}")

            # Уведомляем админов об использовании промокода
            username_str = f"@{person.username}" if person.username else f"ID:{person.tgid}"
            admin_text = (
                f"🎟 <b>Использован промокод</b>\n\n"
                f"👤 Пользователь: {username_str}\n"
                f"📝 Промокод: <code>{text_promo}</code>\n"
                f"📅 Дней: +{add_days_number}"
            )
            for admin_id in CONFIG.admins_ids:
                try:
                    await message.bot.send_message(admin_id, admin_text, parse_mode="HTML")
                except Exception as e:
                    log.error(f"Can't notify admin {admin_id} about promo usage: {e}")

            # Компактное меню после активации промокода
            from aiogram.utils.keyboard import InlineKeyboardBuilder
            from bot.misc.callbackData import MainMenuAction
            kb = InlineKeyboardBuilder()
            kb.button(
                text="🔑 Подключить VPN",
                callback_data=MainMenuAction(action='my_keys')
            )
            kb.button(
                text="📋 Главное меню",
                callback_data=MainMenuAction(action='back_to_menu')
            )
            kb.adjust(1)

            await message.answer(
                _('promo_success_user', lang).format(amount=add_days_number),
                reply_markup=kb.as_markup()
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


# ==================== ADMIN: WITHDRAWAL CONFIRMATION ====================

@referral_router.callback_query(lambda c: c.data and c.data.startswith('withdrawal:'))
async def withdrawal_confirm_callback(call: CallbackQuery, state: FSMContext):
    """Админ нажал кнопку 'Выплачено' - сразу подтверждаем"""
    from bot.misc.callbackData import WithdrawalConfirm

    # Проверяем что это админ
    if call.from_user.id not in CONFIG.admins_ids:
        await call.answer("❌ Только для администраторов", show_alert=True)
        return

    # Парсим callback data
    data = WithdrawalConfirm.unpack(call.data)
    withdrawal_id = data.withdrawal_id
    user_tgid = data.user_tgid

    try:
        from sqlalchemy.ext.asyncio import AsyncSession
        from sqlalchemy import select, update
        from bot.database.main import engine
        from bot.database.models.main import WithdrawalRequests
        from datetime import datetime

        async with AsyncSession(autoflush=False, bind=engine()) as db:
            stmt = select(WithdrawalRequests).filter(WithdrawalRequests.id == withdrawal_id)
            result = await db.execute(stmt)
            withdrawal = result.scalar_one_or_none()

            if not withdrawal:
                await call.answer("❌ Заявка не найдена", show_alert=True)
                return

            if withdrawal.check_payment:
                await call.answer("⚠️ Уже подтверждено ранее", show_alert=True)
                return

            amount = withdrawal.amount

            # Отмечаем выплату как выполненную
            stmt = update(WithdrawalRequests).where(
                WithdrawalRequests.id == withdrawal_id
            ).values(
                check_payment=True,
                payment_date=datetime.now()
            )
            await db.execute(stmt)
            await db.commit()

        # Уведомляем пользователя
        try:
            await call.bot.send_message(
                chat_id=user_tgid,
                text=(
                    f"✅ <b>Выплата выполнена!</b>\n\n"
                    f"💰 Сумма: {amount} ₽\n\n"
                    f"Спасибо за участие в партнёрской программе! 🎉"
                ),
                parse_mode="HTML"
            )
        except Exception as e:
            log.error(f"Failed to send notification to user {user_tgid}: {e}")

        # Обновляем сообщение админу — убираем кнопку, добавляем отметку
        try:
            original_text = call.message.text or call.message.caption or ""
            await call.message.edit_text(
                text=original_text + "\n\n✅ <b>Выплачено</b>",
                parse_mode="HTML",
                reply_markup=None
            )
        except Exception:
            pass

        await call.answer("✅ Выплата подтверждена!", show_alert=True)

    except Exception as e:
        log.error(f"Error processing withdrawal confirmation: {e}")
        await message.answer(f"❌ Ошибка при обработке: {e}")

    await state.clear()


@referral_router.message(WithdrawalReceipt.waiting_receipt)
async def withdrawal_receipt_wrong_format(message: Message, state: FSMContext):
    """Админ прислал не фото"""
    await message.answer(
        "⚠️ Пожалуйста, отправьте <b>фото</b> чека об оплате.\n\n"
        "Или напишите /cancel для отмены.",
        parse_mode="HTML"
    )
