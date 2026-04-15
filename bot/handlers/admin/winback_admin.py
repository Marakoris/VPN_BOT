"""
Win-back промокоды - админ панель
Управление промокодами для возврата ушедших клиентов
"""
import logging
import os
from datetime import datetime
from zoneinfo import ZoneInfo

from aiogram import Router, F, Bot
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.filters import StateFilter

from bot.filters.main import IsAdmin
from bot.misc.callbackData import AdminMenuNav
from bot.database.methods.winback import (
    create_winback_promo,
    get_all_winback_promos,
    get_winback_promo,
    get_winback_promo_by_code,
    update_winback_promo,
    delete_winback_promo,
    toggle_winback_promo,
    get_promo_statistics,
    get_all_promos_statistics,
    get_churned_users_by_segment,
    get_churned_users_stats,
    create_promo_usage,
    get_users_for_autosend
)
from bot.misc.language import get_lang
from bot.misc.util import CONFIG

log = logging.getLogger(__name__)

winback_router = Router()
winback_router.message.filter(IsAdmin())
winback_router.callback_query.filter(IsAdmin())


# ============================================
# States
# ============================================

class WinbackStates(StatesGroup):
    """Состояния для создания/редактирования промокода"""
    enter_code = State()
    enter_discount = State()
    enter_min_days = State()
    enter_max_days = State()
    enter_valid_days = State()
    confirm_delete = State()
    edit_field = State()
    manual_send_confirm = State()


# ============================================
# Callback Data
# ============================================

# Простые строковые callback'и для навигации
WINBACK_PREFIX = "wb:"


# ============================================
# Keyboards
# ============================================

async def winback_main_menu() -> InlineKeyboardBuilder:
    """Главное меню win-back промокодов"""
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="📋 Список промокодов", callback_data=f"{WINBACK_PREFIX}list"))
    kb.row(InlineKeyboardButton(text="➕ Создать промокод", callback_data=f"{WINBACK_PREFIX}create"))
    kb.row(InlineKeyboardButton(text="📊 Статистика", callback_data=f"{WINBACK_PREFIX}stats"))
    kb.row(InlineKeyboardButton(text="📤 Ручная рассылка", callback_data=f"{WINBACK_PREFIX}manual_send"))
    kb.row(InlineKeyboardButton(text="⬅️ Назад", callback_data=AdminMenuNav(menu='main').pack()))
    return kb


async def promo_list_menu(promos: list) -> InlineKeyboardBuilder:
    """Меню списка промокодов"""
    kb = InlineKeyboardBuilder()
    for promo in promos:
        status = "✅" if promo.is_active else "❌"
        auto = "🔄" if promo.auto_send else ""
        kb.row(InlineKeyboardButton(
            text=f"{status} {promo.code} ({promo.discount_percent}%) {auto}",
            callback_data=f"{WINBACK_PREFIX}view:{promo.id}"
        ))
    kb.row(InlineKeyboardButton(text="➕ Создать", callback_data=f"{WINBACK_PREFIX}create"))
    kb.row(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"{WINBACK_PREFIX}menu"))
    return kb


async def promo_view_menu(promo_id: int) -> InlineKeyboardBuilder:
    """Меню просмотра промокода"""
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="✏️ Редактировать", callback_data=f"{WINBACK_PREFIX}edit:{promo_id}"))
    kb.row(
        InlineKeyboardButton(text="🔄 Вкл/Выкл", callback_data=f"{WINBACK_PREFIX}toggle:{promo_id}"),
        InlineKeyboardButton(text="📤 Авто", callback_data=f"{WINBACK_PREFIX}autotoggle:{promo_id}")
    )
    kb.row(InlineKeyboardButton(text="📊 Статистика", callback_data=f"{WINBACK_PREFIX}stat:{promo_id}"))
    kb.row(InlineKeyboardButton(text="📤 Разослать сейчас", callback_data=f"{WINBACK_PREFIX}send:{promo_id}"))
    kb.row(InlineKeyboardButton(text="🗑 Удалить", callback_data=f"{WINBACK_PREFIX}delete:{promo_id}"))
    kb.row(InlineKeyboardButton(text="⬅️ К списку", callback_data=f"{WINBACK_PREFIX}list"))
    return kb


async def promo_edit_menu(promo_id: int, promo_type: str = 'winback') -> InlineKeyboardBuilder:
    """Меню редактирования промокода"""
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="📝 Код", callback_data=f"{WINBACK_PREFIX}edit_field:{promo_id}:code"))
    kb.row(InlineKeyboardButton(text="💰 Скидка %", callback_data=f"{WINBACK_PREFIX}edit_field:{promo_id}:discount"))
    if promo_type == 'welcome':
        kb.row(InlineKeyboardButton(text="⏳ Задержка (дней)", callback_data=f"{WINBACK_PREFIX}edit_field:{promo_id}:delay_days"))
    else:
        kb.row(InlineKeyboardButton(text="📅 Мин. дней", callback_data=f"{WINBACK_PREFIX}edit_field:{promo_id}:min_days"))
        kb.row(InlineKeyboardButton(text="📅 Макс. дней", callback_data=f"{WINBACK_PREFIX}edit_field:{promo_id}:max_days"))
    kb.row(InlineKeyboardButton(text="⏰ Срок действия", callback_data=f"{WINBACK_PREFIX}edit_field:{promo_id}:valid_days"))
    kb.row(InlineKeyboardButton(text="💬 Шаблон сообщения", callback_data=f"{WINBACK_PREFIX}edit_field:{promo_id}:message"))
    kb.row(InlineKeyboardButton(text="👁 Предпросмотр", callback_data=f"{WINBACK_PREFIX}preview:{promo_id}"))
    kb.row(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"{WINBACK_PREFIX}view:{promo_id}"))
    return kb


async def confirm_menu(action: str, promo_id: int) -> InlineKeyboardBuilder:
    """Меню подтверждения"""
    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(text="✅ Да", callback_data=f"{WINBACK_PREFIX}{action}_confirm:{promo_id}"),
        InlineKeyboardButton(text="❌ Нет", callback_data=f"{WINBACK_PREFIX}view:{promo_id}")
    )
    return kb


async def back_to_menu_kb() -> InlineKeyboardBuilder:
    """Кнопка возврата в меню"""
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"{WINBACK_PREFIX}menu"))
    return kb


# ============================================
# Handlers - Главное меню
# ============================================

@winback_router.message(F.text == "🎁 Win-back промокоды")
async def winback_menu_handler(message: Message, state: FSMContext):
    """Вход в меню win-back промокодов"""
    await state.clear()
    kb = await winback_main_menu()

    # Получить статистику churned users
    stats = await get_churned_users_stats()

    text = (
        "🎁 <b>Win-back промокоды</b>\n\n"
        "Система возврата ушедших клиентов через персональные скидки.\n\n"
        f"👥 <b>Пользователи без подписки:</b> {stats['total']}\n"
        f"   • 0-7 дней: {stats['0-7']}\n"
        f"   • 7-30 дней: {stats['7-30']}\n"
        f"   • 30-90 дней: {stats['30-90']}\n"
        f"   • 90+ дней: {stats['90+']}"
    )

    await message.answer(
        text,
        reply_markup=kb.as_markup(),
        parse_mode="HTML"
    )


@winback_router.callback_query(F.data == f"{WINBACK_PREFIX}menu")
async def winback_menu_callback(callback: CallbackQuery, state: FSMContext):
    """Возврат в главное меню"""
    await state.clear()
    kb = await winback_main_menu()

    # Получить статистику churned users
    stats = await get_churned_users_stats()

    text = (
        "🎁 <b>Win-back промокоды</b>\n\n"
        "Система возврата ушедших клиентов через персональные скидки.\n\n"
        f"👥 <b>Пользователи без подписки:</b> {stats['total']}\n"
        f"   • 0-7 дней: {stats['0-7']}\n"
        f"   • 7-30 дней: {stats['7-30']}\n"
        f"   • 30-90 дней: {stats['30-90']}\n"
        f"   • 90+ дней: {stats['90+']}"
    )

    await callback.message.edit_text(
        text,
        reply_markup=kb.as_markup(),
        parse_mode="HTML"
    )
    await callback.answer()


# ============================================
# Handlers - Список промокодов
# ============================================

@winback_router.callback_query(F.data == f"{WINBACK_PREFIX}list")
async def list_promos(callback: CallbackQuery):
    """Показать список промокодов"""
    promos = await get_all_winback_promos()

    if not promos:
        kb = InlineKeyboardBuilder()
        kb.row(InlineKeyboardButton(text="➕ Создать первый", callback_data=f"{WINBACK_PREFIX}create"))
        kb.row(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"{WINBACK_PREFIX}menu"))
        await callback.message.edit_text(
            "📋 <b>Список промокодов</b>\n\n"
            "Пока нет ни одного win-back промокода.\n"
            "Создайте первый!",
            reply_markup=kb.as_markup(),
            parse_mode="HTML"
        )
    else:
        kb = await promo_list_menu(promos)
        text = "📋 <b>Список промокодов</b>\n\n"
        text += "✅ - активен | ❌ - неактивен | 🔄 - авторассылка\n\n"
        for promo in promos:
            status = "✅" if promo.is_active else "❌"
            auto = "🔄" if promo.auto_send else ""
            text += f"{status} <code>{promo.code}</code> - {promo.discount_percent}% ({promo.min_days_expired}-{promo.max_days_expired} дн.) {auto}\n"

        await callback.message.edit_text(
            text,
            reply_markup=kb.as_markup(),
            parse_mode="HTML"
        )

    await callback.answer()


# ============================================
# Handlers - Просмотр промокода
# ============================================

@winback_router.callback_query(F.data.startswith(f"{WINBACK_PREFIX}view:"))
async def view_promo(callback: CallbackQuery):
    """Просмотр промокода"""
    promo_id = int(callback.data.split(":")[-1])
    promo = await get_winback_promo(promo_id)

    if not promo:
        await callback.answer("Промокод не найден", show_alert=True)
        return

    status = "✅ Активен" if promo.is_active else "❌ Неактивен"
    auto = "✅ Включена" if promo.auto_send else "❌ Выключена"
    promo_type = getattr(promo, 'promo_type', 'winback') or 'winback'
    delay_days = getattr(promo, 'delay_days', 0) or 0

    type_label = "🆕 Welcome (новые)" if promo_type == 'welcome' else "🔄 Winback (ушедшие)"

    text = f"🎁 <b>Промокод: {promo.code}</b>\n\n"
    text += f"📊 Статус: {status}\n"
    text += f"🏷 Тип: {type_label}\n"
    text += f"💰 Скидка: <b>{promo.discount_percent}%</b>\n"

    if promo_type == 'welcome':
        text += f"⏳ Задержка: {delay_days} дней после регистрации\n"
    else:
        text += f"📅 Сегмент: {promo.min_days_expired}-{promo.max_days_expired} дней без подписки\n"

    text += f"⏰ Срок действия: {promo.valid_days} дней\n"
    text += f"🔄 Авторассылка: {auto}\n"

    # Показать шаблон если есть
    if promo.message_template:
        text += f"\n💬 Шаблон: <i>настроен</i>"
    else:
        text += f"\n💬 Шаблон: <i>стандартный</i>"

    if promo.created_at:
        text += f"\n📆 Создан: {promo.created_at.strftime('%d.%m.%Y %H:%M')}"

    kb = await promo_view_menu(promo_id)
    await callback.message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="HTML")
    await callback.answer()


# ============================================
# Handlers - Создание промокода
# ============================================

@winback_router.callback_query(F.data == f"{WINBACK_PREFIX}create")
async def create_promo_start(callback: CallbackQuery, state: FSMContext):
    """Начало создания промокода"""
    await state.set_state(WinbackStates.enter_code)
    kb = await back_to_menu_kb()
    await callback.message.edit_text(
        "➕ <b>Создание промокода</b>\n\n"
        "Введите код промокода (например: HOT10, WARM20, COLD30):\n\n"
        "💡 Код будет автоматически переведён в верхний регистр",
        reply_markup=kb.as_markup(),
        parse_mode="HTML"
    )
    await callback.answer()


@winback_router.message(StateFilter(WinbackStates.enter_code))
async def create_promo_code(message: Message, state: FSMContext):
    """Ввод кода промокода"""
    code = message.text.strip().upper()

    # Проверить уникальность
    existing = await get_winback_promo_by_code(code)
    if existing:
        await message.answer(
            f"❌ Код <code>{code}</code> уже существует!\n"
            "Введите другой код:",
            parse_mode="HTML"
        )
        return

    await state.update_data(code=code)
    await state.set_state(WinbackStates.enter_discount)
    kb = await back_to_menu_kb()
    await message.answer(
        f"✅ Код: <code>{code}</code>\n\n"
        "Введите процент скидки (1-90):",
        reply_markup=kb.as_markup(),
        parse_mode="HTML"
    )


@winback_router.message(StateFilter(WinbackStates.enter_discount))
async def create_promo_discount(message: Message, state: FSMContext):
    """Ввод процента скидки"""
    try:
        discount = int(message.text.strip())
        if discount < 1 or discount > 90:
            raise ValueError()
    except ValueError:
        await message.answer("❌ Введите число от 1 до 90:")
        return

    await state.update_data(discount=discount)
    await state.set_state(WinbackStates.enter_min_days)
    kb = await back_to_menu_kb()
    await message.answer(
        f"✅ Скидка: {discount}%\n\n"
        "Введите <b>минимальное</b> количество дней без подписки:\n"
        "(например: 0 для hot leads, 7 для warm, 30 для cold)",
        reply_markup=kb.as_markup(),
        parse_mode="HTML"
    )


@winback_router.message(StateFilter(WinbackStates.enter_min_days))
async def create_promo_min_days(message: Message, state: FSMContext):
    """Ввод минимального количества дней"""
    try:
        min_days = int(message.text.strip())
        if min_days < 0:
            raise ValueError()
    except ValueError:
        await message.answer("❌ Введите число >= 0:")
        return

    await state.update_data(min_days=min_days)
    await state.set_state(WinbackStates.enter_max_days)
    kb = await back_to_menu_kb()
    await message.answer(
        f"✅ Мин. дней: {min_days}\n\n"
        "Введите <b>максимальное</b> количество дней без подписки:\n"
        "(например: 7 для hot, 30 для warm, 90 для cold)",
        reply_markup=kb.as_markup(),
        parse_mode="HTML"
    )


@winback_router.message(StateFilter(WinbackStates.enter_max_days))
async def create_promo_max_days(message: Message, state: FSMContext):
    """Ввод максимального количества дней"""
    data = await state.get_data()
    try:
        max_days = int(message.text.strip())
        if max_days <= data['min_days']:
            await message.answer(f"❌ Должно быть больше {data['min_days']}:")
            return
    except ValueError:
        await message.answer("❌ Введите положительное число:")
        return

    await state.update_data(max_days=max_days)
    await state.set_state(WinbackStates.enter_valid_days)
    kb = await back_to_menu_kb()
    await message.answer(
        f"✅ Макс. дней: {max_days}\n\n"
        "Введите срок действия промокода (дней):\n"
        "(сколько дней у пользователя будет на использование после отправки)",
        reply_markup=kb.as_markup(),
        parse_mode="HTML"
    )


@winback_router.message(StateFilter(WinbackStates.enter_valid_days))
async def create_promo_valid_days(message: Message, state: FSMContext):
    """Ввод срока действия и создание промокода"""
    try:
        valid_days = int(message.text.strip())
        if valid_days < 1:
            raise ValueError()
    except ValueError:
        await message.answer("❌ Введите число >= 1:")
        return

    data = await state.get_data()

    # Создаём промокод
    promo = await create_winback_promo(
        code=data['code'],
        discount_percent=data['discount'],
        min_days_expired=data['min_days'],
        max_days_expired=data['max_days'],
        valid_days=valid_days,
        auto_send=False
    )

    await state.clear()

    if promo:
        kb = await promo_view_menu(promo.id)
        await message.answer(
            f"✅ <b>Промокод создан!</b>\n\n"
            f"📝 Код: <code>{promo.code}</code>\n"
            f"💰 Скидка: {promo.discount_percent}%\n"
            f"📅 Сегмент: {promo.min_days_expired}-{promo.max_days_expired} дней\n"
            f"⏰ Срок действия: {promo.valid_days} дней\n\n"
            f"🔄 Авторассылка выключена. Включите если нужно.",
            reply_markup=kb.as_markup(),
            parse_mode="HTML"
        )
    else:
        kb = await winback_main_menu()
        await message.answer(
            "❌ Не удалось создать промокод. Возможно, код уже существует.",
            reply_markup=kb.as_markup()
        )


# ============================================
# Handlers - Управление промокодом
# ============================================

@winback_router.callback_query(F.data.startswith(f"{WINBACK_PREFIX}toggle:"))
async def toggle_promo(callback: CallbackQuery):
    """Включить/выключить промокод"""
    promo_id = int(callback.data.split(":")[-1])
    new_state = await toggle_winback_promo(promo_id)

    if new_state is None:
        await callback.answer("Промокод не найден", show_alert=True)
        return

    status = "активирован ✅" if new_state else "деактивирован ❌"
    await callback.answer(f"Промокод {status}")

    # Обновить сообщение
    promo = await get_winback_promo(promo_id)
    if promo:
        status_text = "✅ Активен" if promo.is_active else "❌ Неактивен"
        auto = "✅ Включена" if promo.auto_send else "❌ Выключена"

        text = f"🎁 <b>Промокод: {promo.code}</b>\n\n"
        text += f"📊 Статус: {status_text}\n"
        text += f"💰 Скидка: <b>{promo.discount_percent}%</b>\n"
        text += f"📅 Сегмент: {promo.min_days_expired}-{promo.max_days_expired} дней\n"
        text += f"⏰ Срок действия: {promo.valid_days} дней\n"
        text += f"🔄 Авторассылка: {auto}"

        kb = await promo_view_menu(promo_id)
        await callback.message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="HTML")


@winback_router.callback_query(F.data.startswith(f"{WINBACK_PREFIX}autotoggle:"))
async def toggle_auto_send(callback: CallbackQuery):
    """Включить/выключить авторассылку"""
    promo_id = int(callback.data.split(":")[-1])
    promo = await get_winback_promo(promo_id)

    if not promo:
        await callback.answer("Промокод не найден", show_alert=True)
        return

    new_state = not promo.auto_send
    await update_winback_promo(promo_id, auto_send=new_state)

    status = "включена ✅" if new_state else "выключена ❌"
    await callback.answer(f"Авторассылка {status}")

    # Обновить сообщение
    promo = await get_winback_promo(promo_id)
    status_text = "✅ Активен" if promo.is_active else "❌ Неактивен"
    auto = "✅ Включена" if promo.auto_send else "❌ Выключена"

    text = f"🎁 <b>Промокод: {promo.code}</b>\n\n"
    text += f"📊 Статус: {status_text}\n"
    text += f"💰 Скидка: <b>{promo.discount_percent}%</b>\n"
    text += f"📅 Сегмент: {promo.min_days_expired}-{promo.max_days_expired} дней\n"
    text += f"⏰ Срок действия: {promo.valid_days} дней\n"
    text += f"🔄 Авторассылка: {auto}"

    kb = await promo_view_menu(promo_id)
    await callback.message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="HTML")


@winback_router.callback_query(F.data.startswith(f"{WINBACK_PREFIX}delete:"))
async def delete_promo_confirm(callback: CallbackQuery):
    """Подтверждение удаления"""
    promo_id = int(callback.data.split(":")[-1])
    promo = await get_winback_promo(promo_id)

    if not promo:
        await callback.answer("Промокод не найден", show_alert=True)
        return

    kb = await confirm_menu("delete", promo_id)
    await callback.message.edit_text(
        f"🗑 <b>Удалить промокод {promo.code}?</b>\n\n"
        "⚠️ Это действие необратимо!\n"
        "Вся статистика использования будет удалена.",
        reply_markup=kb.as_markup(),
        parse_mode="HTML"
    )
    await callback.answer()


@winback_router.callback_query(F.data.startswith(f"{WINBACK_PREFIX}delete_confirm:"))
async def delete_promo_execute(callback: CallbackQuery):
    """Удаление промокода"""
    promo_id = int(callback.data.split(":")[-1])
    promo = await get_winback_promo(promo_id)
    code = promo.code if promo else "?"

    result = await delete_winback_promo(promo_id)

    if result:
        kb = await promo_list_menu(await get_all_winback_promos())
        await callback.message.edit_text(
            f"✅ Промокод <code>{code}</code> удалён",
            reply_markup=kb.as_markup(),
            parse_mode="HTML"
        )
    else:
        await callback.answer("Не удалось удалить", show_alert=True)


# ============================================
# Handlers - Редактирование
# ============================================

@winback_router.callback_query(F.data.startswith(f"{WINBACK_PREFIX}edit:"))
async def edit_promo_menu_handler(callback: CallbackQuery):
    """Меню редактирования"""
    promo_id = int(callback.data.split(":")[-1])
    promo = await get_winback_promo(promo_id)

    if not promo:
        await callback.answer("Промокод не найден", show_alert=True)
        return

    promo_type = getattr(promo, 'promo_type', 'winback') or 'winback'
    kb = await promo_edit_menu(promo_id, promo_type)
    await callback.message.edit_text(
        f"✏️ <b>Редактирование: {promo.code}</b>\n\n"
        "Выберите что изменить:",
        reply_markup=kb.as_markup(),
        parse_mode="HTML"
    )
    await callback.answer()


@winback_router.callback_query(F.data.startswith(f"{WINBACK_PREFIX}edit_field:"))
async def edit_promo_field(callback: CallbackQuery, state: FSMContext):
    """Редактирование поля"""
    # callback.data = "wb:edit_field:4:code"
    parts = callback.data.split(":")
    promo_id = int(parts[2])  # parts[0]=wb, parts[1]=edit_field, parts[2]=promo_id
    field = parts[3]  # parts[3]=field

    promo = await get_winback_promo(promo_id)
    if not promo:
        await callback.answer("Промокод не найден", show_alert=True)
        return

    await state.update_data(edit_promo_id=promo_id, edit_field=field)
    await state.set_state(WinbackStates.edit_field)

    delay_days = getattr(promo, 'delay_days', 0) or 0
    message_template = getattr(promo, 'message_template', None)

    field_names = {
        'code': ('код', promo.code),
        'discount': ('процент скидки', f"{promo.discount_percent}%"),
        'min_days': ('мин. дней', str(promo.min_days_expired)),
        'max_days': ('макс. дней', str(promo.max_days_expired)),
        'valid_days': ('срок действия', f"{promo.valid_days} дней"),
        'delay_days': ('задержка после регистрации', f"{delay_days} дней"),
        'message': ('шаблон сообщения', message_template[:50] + '...' if message_template and len(message_template) > 50 else (message_template or 'не задан'))
    }

    name, current = field_names.get(field, ('поле', '?'))

    kb = InlineKeyboardBuilder()
    if field == 'message':
        kb.row(InlineKeyboardButton(text="🗑 Сбросить на стандартный", callback_data=f"{WINBACK_PREFIX}reset_message:{promo_id}"))
    kb.row(InlineKeyboardButton(text="❌ Отмена", callback_data=f"{WINBACK_PREFIX}edit:{promo_id}"))

    if field == 'message':
        text = (
            f"✏️ <b>Редактирование: {name}</b>\n\n"
            f"Текущее значение:\n<code>{current}</code>\n\n"
            f"Введите новый шаблон сообщения.\n\n"
            f"<b>Доступные переменные:</b>\n"
            f"<code>{{code}}</code> - код промокода\n"
            f"<code>{{discount}}</code> - процент скидки\n"
            f"<code>{{valid_days}}</code> - срок действия\n\n"
            f"Пример:\n"
            f"<i>🎁 Ваш промокод: {{code}} со скидкой {{discount}}%!</i>"
        )
    else:
        text = f"✏️ <b>Редактирование: {name}</b>\n\nТекущее значение: <code>{current}</code>\n\nВведите новое значение:"

    await callback.message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="HTML")
    await callback.answer()


@winback_router.message(StateFilter(WinbackStates.edit_field))
async def save_edited_field(message: Message, state: FSMContext):
    """Сохранение отредактированного поля"""
    data = await state.get_data()
    promo_id = data['edit_promo_id']
    field = data['edit_field']
    value = message.text.strip()

    try:
        if field == 'code':
            update_data = {'code': value.upper()}
        elif field == 'discount':
            discount = int(value)
            if discount < 1 or discount > 90:
                raise ValueError("1-90")
            update_data = {'discount_percent': discount}
        elif field == 'min_days':
            min_days = int(value)
            if min_days < 0:
                raise ValueError(">= 0")
            update_data = {'min_days_expired': min_days}
        elif field == 'max_days':
            max_days = int(value)
            if max_days < 1:
                raise ValueError(">= 1")
            update_data = {'max_days_expired': max_days}
        elif field == 'valid_days':
            valid_days = int(value)
            if valid_days < 1:
                raise ValueError(">= 1")
            update_data = {'valid_days': valid_days}
        elif field == 'delay_days':
            delay_days = int(value)
            if delay_days < 0:
                raise ValueError(">= 0")
            update_data = {'delay_days': delay_days}
        elif field == 'message':
            # Шаблон сообщения - сохраняем как есть
            update_data = {'message_template': value}
        else:
            raise ValueError("Unknown field")

        await update_winback_promo(promo_id, **update_data)
        await state.clear()

        promo = await get_winback_promo(promo_id)
        promo_type = getattr(promo, 'promo_type', 'winback') or 'winback'
        delay_days = getattr(promo, 'delay_days', 0) or 0

        kb = await promo_view_menu(promo_id)

        if promo_type == 'welcome':
            segment_text = f"⏳ Задержка: {delay_days} дней"
        else:
            segment_text = f"📅 Сегмент: {promo.min_days_expired}-{promo.max_days_expired} дней"

        await message.answer(
            f"✅ Изменено!\n\n"
            f"🎁 <b>Промокод: {promo.code}</b>\n"
            f"💰 Скидка: {promo.discount_percent}%\n"
            f"{segment_text}\n"
            f"⏰ Срок действия: {promo.valid_days} дней",
            reply_markup=kb.as_markup(),
            parse_mode="HTML"
        )
    except ValueError as e:
        await message.answer(f"❌ Неверное значение: {e}\nПопробуйте ещё раз:")


# ============================================
# Handlers - Статистика
# ============================================

@winback_router.callback_query(F.data == f"{WINBACK_PREFIX}stats")
async def show_all_stats(callback: CallbackQuery):
    """Общая статистика по всем промокодам"""
    stats = await get_all_promos_statistics()

    if not stats:
        kb = await winback_main_menu()
        await callback.message.edit_text(
            "📊 <b>Статистика</b>\n\n"
            "Нет данных. Создайте промокоды и начните рассылку.",
            reply_markup=kb.as_markup(),
            parse_mode="HTML"
        )
        await callback.answer()
        return

    text = "📊 <b>Статистика Win-back</b>\n\n"

    total_sent = 0
    total_used = 0
    total_revenue = 0
    total_discount = 0

    for stat in stats:
        total_sent += stat['sent_count']
        total_used += stat['used_count']
        total_revenue += stat['total_revenue']
        total_discount += stat['total_discount']

        text += f"<b>{stat['code']}</b> ({stat['discount_percent']}%)\n"
        text += f"  📤 Отправлено: {stat['sent_count']}\n"
        text += f"  ✅ Использовано: {stat['used_count']}\n"
        text += f"  📈 Конверсия: {stat['conversion_rate']}%\n"
        text += f"  💰 Выручка: {stat['total_revenue']}₽\n\n"

    total_conversion = (total_used / total_sent * 100) if total_sent > 0 else 0

    text += "━━━━━━━━━━━━━━━━━━━━\n"
    text += f"<b>ИТОГО:</b>\n"
    text += f"📤 Отправлено: {total_sent}\n"
    text += f"✅ Использовано: {total_used}\n"
    text += f"📈 Общая конверсия: {total_conversion:.1f}%\n"
    text += f"💰 Выручка: {total_revenue}₽\n"
    text += f"🏷 Скидки: {total_discount}₽"

    kb = await winback_main_menu()
    await callback.message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="HTML")
    await callback.answer()


@winback_router.callback_query(F.data.startswith(f"{WINBACK_PREFIX}stat:"))
async def show_promo_stats(callback: CallbackQuery):
    """Статистика по конкретному промокоду"""
    promo_id = int(callback.data.split(":")[-1])
    stat = await get_promo_statistics(promo_id)

    if not stat:
        await callback.answer("Промокод не найден", show_alert=True)
        return

    text = f"📊 <b>Статистика: {stat['code']}</b>\n\n"
    text += f"💰 Скидка: {stat['discount_percent']}%\n"
    text += f"📅 Сегмент: {stat['segment']}\n\n"
    text += f"📤 Отправлено: {stat['sent_count']}\n"
    text += f"✅ Использовано: {stat['used_count']}\n"
    text += f"📈 Конверсия: {stat['conversion_rate']}%\n\n"
    text += f"💰 Выручка со скидкой: {stat['total_revenue']}₽\n"
    text += f"🏷 Сумма скидок: {stat['total_discount']}₽"

    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="⬅️ К промокоду", callback_data=f"{WINBACK_PREFIX}view:{promo_id}"))
    kb.row(InlineKeyboardButton(text="📊 Общая статистика", callback_data=f"{WINBACK_PREFIX}stats"))

    await callback.message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="HTML")
    await callback.answer()


# ============================================
# Handlers - Ручная рассылка
# ============================================

@winback_router.callback_query(F.data.startswith(f"{WINBACK_PREFIX}send:"))
async def send_promo_confirm(callback: CallbackQuery):
    """Подтверждение ручной рассылки промокода"""
    promo_id = int(callback.data.split(":")[-1])
    promo = await get_winback_promo(promo_id)

    if not promo:
        await callback.answer("Промокод не найден", show_alert=True)
        return

    promo_type = getattr(promo, 'promo_type', 'winback') or 'winback'
    delay_days = getattr(promo, 'delay_days', 0) or 0

    # Получить пользователей для рассылки в зависимости от типа
    if promo_type == 'welcome':
        from bot.database.methods.winback import get_new_users_for_welcome_promo
        users = await get_new_users_for_welcome_promo(
            exclude_already_sent_promo_id=promo.id,
            delay_days=delay_days
        )
        segment_text = f"🆕 Новые пользователи (задержка: {delay_days} дн.)"
    else:
        users = await get_churned_users_by_segment(
            min_days=promo.min_days_expired,
            max_days=promo.max_days_expired,
            exclude_already_sent_promo_id=promo.id
        )
        segment_text = f"📅 Сегмент: {promo.min_days_expired}-{promo.max_days_expired} дней без подписки"

    if not users:
        await callback.answer("Нет пользователей для рассылки", show_alert=True)
        return

    kb = await confirm_menu("send", promo_id)
    await callback.message.edit_text(
        f"📤 <b>Рассылка промокода {promo.code}</b>\n\n"
        f"👥 Получателей: <b>{len(users)}</b>\n"
        f"{segment_text}\n"
        f"💰 Скидка: {promo.discount_percent}%\n\n"
        f"Отправить?",
        reply_markup=kb.as_markup(),
        parse_mode="HTML"
    )
    await callback.answer()


@winback_router.callback_query(F.data.startswith(f"{WINBACK_PREFIX}send_confirm:"))
async def send_promo_execute(callback: CallbackQuery, bot: Bot):
    """Выполнение рассылки"""
    from bot.misc.winback_sender import send_winback_promo_to_user

    promo_id = int(callback.data.split(":")[-1])
    promo = await get_winback_promo(promo_id)

    if not promo:
        await callback.answer("Промокод не найден", show_alert=True)
        return

    promo_type = getattr(promo, 'promo_type', 'winback') or 'winback'
    delay_days = getattr(promo, 'delay_days', 0) or 0

    # Получить пользователей в зависимости от типа
    if promo_type == 'welcome':
        from bot.database.methods.winback import get_new_users_for_welcome_promo
        users = await get_new_users_for_welcome_promo(
            exclude_already_sent_promo_id=promo.id,
            delay_days=delay_days
        )
    else:
        users = await get_churned_users_by_segment(
            min_days=promo.min_days_expired,
            max_days=promo.max_days_expired,
            exclude_already_sent_promo_id=promo.id
        )

    if not users:
        await callback.answer("Нет пользователей для рассылки", show_alert=True)
        return

    await callback.message.edit_text(
        f"📤 Рассылка промокода {promo.code}...\n\n"
        f"Отправляю {len(users)} пользователям...",
        parse_mode="HTML"
    )

    success_count = 0
    error_count = 0

    for user in users:
        try:
            # Создать запись об отправке
            usage = await create_promo_usage(promo.id, user.tgid, promo.valid_days)
            if not usage:
                continue  # Уже отправляли

            # Используем централизованную функцию отправки
            success = await send_winback_promo_to_user(
                bot=bot,
                user_tgid=user.tgid,
                promo_code=promo.code,
                discount_percent=promo.discount_percent,
                valid_days=promo.valid_days,
                message_template=promo.message_template,
                promo_type=promo_type
            )

            if success:
                success_count += 1
            else:
                error_count += 1

        except Exception as e:
            log.error(f"Failed to send promo to {user.tgid}: {e}")
            error_count += 1

    kb = await promo_view_menu(promo_id)
    await callback.message.edit_text(
        f"✅ <b>Рассылка завершена!</b>\n\n"
        f"📤 Отправлено: {success_count}\n"
        f"❌ Ошибок: {error_count}",
        reply_markup=kb.as_markup(),
        parse_mode="HTML"
    )


@winback_router.callback_query(F.data == f"{WINBACK_PREFIX}manual_send")
async def manual_send_menu(callback: CallbackQuery):
    """Меню ручной рассылки - выбор промокода"""
    promos = await get_all_winback_promos(active_only=True)

    if not promos:
        await callback.answer("Нет активных промокодов", show_alert=True)
        return

    kb = InlineKeyboardBuilder()
    for promo in promos:
        # Подсчитать пользователей в сегменте
        users = await get_churned_users_by_segment(
            promo.min_days_expired,
            promo.max_days_expired,
            exclude_already_sent_promo_id=promo.id
        )
        kb.row(InlineKeyboardButton(
            text=f"{promo.code} - {len(users)} чел.",
            callback_data=f"{WINBACK_PREFIX}send:{promo.id}"
        ))

    kb.row(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"{WINBACK_PREFIX}menu"))

    await callback.message.edit_text(
        "📤 <b>Ручная рассылка</b>\n\n"
        "Выберите промокод для рассылки.\n"
        "Показано количество пользователей, которые ещё не получали этот промокод.",
        reply_markup=kb.as_markup(),
        parse_mode="HTML"
    )
    await callback.answer()


# ============================================
# Handlers - Шаблоны и предпросмотр
# ============================================

@winback_router.callback_query(F.data.startswith(f"{WINBACK_PREFIX}reset_message:"))
async def reset_message_template(callback: CallbackQuery, state: FSMContext):
    """Сброс шаблона на стандартный"""
    promo_id = int(callback.data.split(":")[-1])

    await update_winback_promo(promo_id, message_template=None)
    await state.clear()

    promo = await get_winback_promo(promo_id)
    kb = await promo_view_menu(promo_id)

    await callback.message.edit_text(
        f"✅ Шаблон сброшен на стандартный!\n\n"
        f"🎁 <b>Промокод: {promo.code}</b>",
        reply_markup=kb.as_markup(),
        parse_mode="HTML"
    )
    await callback.answer()


@winback_router.callback_query(F.data.startswith(f"{WINBACK_PREFIX}preview:"))
async def preview_message(callback: CallbackQuery, bot: Bot):
    """Предпросмотр сообщения"""
    promo_id = int(callback.data.split(":")[-1])
    promo = await get_winback_promo(promo_id)

    if not promo:
        await callback.answer("Промокод не найден", show_alert=True)
        return

    promo_type = getattr(promo, 'promo_type', 'winback') or 'winback'
    message_template = getattr(promo, 'message_template', None)

    # Генерируем превью сообщения
    if message_template:
        try:
            preview_text = message_template.format(
                code=promo.code,
                discount=promo.discount_percent,
                valid_days=promo.valid_days
            )
        except KeyError as e:
            preview_text = f"❌ Ошибка в шаблоне: неизвестная переменная {e}"
    elif promo_type == 'welcome':
        preview_text = (
            f"🎁 <b>Персональная скидка для вас!</b>\n\n"
            f"Вы зарегистрировались в нашем VPN-сервисе, "
            f"но ещё не попробовали его в деле.\n\n"
            f"Специально для вас — скидка на первую покупку:\n\n"
            f"🏷 Промокод: <code>{promo.code}</code>\n"
            f"💰 Скидка: <b>{promo.discount_percent}%</b>\n"
            f"⏰ Действует: <b>{promo.valid_days} дней</b>\n\n"
            f"<b>Что вы получите:</b>\n"
            f"✅ {os.getenv('TRAFFIC_LIMIT_GB', '300')} ГБ трафика\n"
            f"✅ 5+ серверов в разных странах\n"
            f"✅ Работает в России и за рубежом\n"
            f"✅ Поддержка 24/7\n\n"
            f"Чтобы воспользоваться скидкой:\n"
            f"1. Нажмите кнопку ниже\n"
            f"2. Выберите тариф\n"
            f"3. Нажмите «У меня промокод» и введите код\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🔄 <b>Уже используете другой VPN?</b>\n\n"
            f"Пришлите скриншот оплаты — мы зачтём эти дни "
            f"<b>БЕСПЛАТНО</b> к вашей подписке!\n\n"
            f"👉 Напишите: @VPN_YouSupport_bot"
        )
    else:
        preview_text = (
            f"🎁 <b>Специальное предложение для вас!</b>\n\n"
            f"Мы заметили, что вы давно не пользовались нашим VPN. "
            f"Возвращайтесь! Для вас персональная скидка:\n\n"
            f"🏷 Промокод: <code>{promo.code}</code>\n"
            f"💰 Скидка: <b>{promo.discount_percent}%</b>\n"
            f"⏰ Действует: <b>{promo.valid_days} дней</b>\n\n"
            f"Чтобы воспользоваться скидкой:\n"
            f"1. Нажмите кнопку ниже\n"
            f"2. Выберите тариф\n"
            f"3. Нажмите «У меня промокод» и введите код\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🔄 <b>Перешли на другой VPN-сервис?</b>\n\n"
            f"Пришлите скриншот оплаты конкурента — "
            f"мы зачтём эти дни <b>БЕСПЛАТНО</b> к вашей подписке!\n\n"
            f"👉 Напишите: @VPN_YouSupport_bot"
        )

    # Отправляем превью как новое сообщение
    await bot.send_message(
        chat_id=callback.from_user.id,
        text=f"👁 <b>ПРЕДПРОСМОТР СООБЩЕНИЯ</b>\n\n"
             f"━━━━━━━━━━━━━━━━━━━━\n\n"
             f"{preview_text}",
        parse_mode="HTML"
    )

    await callback.answer("Предпросмотр отправлен ⬇️")
