from aiogram.fsm.state import StatesGroup, State
from aiogram.types import User, Message, CallbackQuery
from aiogram_dialog import Dialog, Window, DialogManager
from aiogram_dialog.widgets.input import TextInput, ManagedTextInput
from aiogram_dialog.widgets.kbd import SwitchTo, Row, Button, Cancel
from aiogram_dialog.widgets.text import Const, Format

from bot.database.methods.delete import delete_supper_offer
from bot.database.methods.get import get_super_offer
from bot.database.methods.update import update_super_offer
from bot.misc.language import Localization, get_lang

_ = Localization.text


class SuperOfferSG(StatesGroup):
    TEXT = State()
    DAYS = State()
    PRICE = State()


async def get_offer_text(dialog_manager: DialogManager, event_from_user: User, **kwargs):
    super_offer = await get_super_offer()
    lang = await get_lang(event_from_user.id)
    if super_offer is None:
        days = dialog_manager.dialog_data.get('days', '#')
        price = dialog_manager.dialog_data.get('price', '#')
        text = _('to_super_offer_btn', lang).format(count_days=days, price=price)
    else:
        days = dialog_manager.dialog_data.get('days', super_offer.days)
        price = dialog_manager.dialog_data.get('price', super_offer.price)
        text = _('to_super_offer_btn', lang).format(count_days=days, price=price)
    return {
        'supper_offer': text
    }


async def correct_days_handler(
        message: Message,
        widget: ManagedTextInput,
        dialog_manager: DialogManager,
        text: int) -> None:
    dialog_manager.dialog_data['days'] = text
    await dialog_manager.switch_to(SuperOfferSG.TEXT)


async def correct_price_handler(
        message: Message,
        widget: ManagedTextInput,
        dialog_manager: DialogManager,
        text: int) -> None:
    dialog_manager.dialog_data['price'] = text
    await dialog_manager.switch_to(SuperOfferSG.TEXT)

async def save_offer_handler(callback: CallbackQuery, button: Button, dialog_manager: DialogManager):
    super_offer = await get_super_offer()
    if super_offer is None:
        days = dialog_manager.dialog_data.get('days', None)
        price = dialog_manager.dialog_data.get('price', None)
        if days is not None and price is not None:
            await update_super_offer(days, price)
        else:
            await callback.message.answer(f"Не хватает данных\n Дней - {str(days)}, Цена - {str(price)}")
    else:
        days = dialog_manager.dialog_data.get('days', None)
        price = dialog_manager.dialog_data.get('price', None)
        await update_super_offer(days if days is not None else super_offer.days,
                                 price if price is not None else super_offer.price)

    await dialog_manager.done()
    await callback.message.answer("Данные успешно сохранены")


async def delete_offer_handler(callback: CallbackQuery, button: Button, dialog_manager: DialogManager):
    await delete_supper_offer()
    await callback.message.answer("Спец предложение удалено")


dialog = Dialog(
    Window(
        Const("Текущее супер-предложение: "),
        Format("{supper_offer}"),
        Row(
            SwitchTo(Const("🗓 Изменить число дней"), id='change_days', state=SuperOfferSG.DAYS),
            SwitchTo(Const("💲 Изменить цену"), id='change_price', state=SuperOfferSG.PRICE),
        ),
        Button(Const("✅ Сохранить"), id='save_offer', on_click=save_offer_handler),
        Button(Const("❌ Удалить"), id='delete_offer', on_click=delete_offer_handler),

        state=SuperOfferSG.TEXT,
        getter=get_offer_text
    ),
    Window(
        Const("Введите количество дней"),
        TextInput(
            id='days_input',
            type_factory=int,
            on_success=correct_days_handler,
        ),
        state=SuperOfferSG.DAYS,
    ),
    Window(
        Const("Введите цену"),
        TextInput(
            id='price_input',
            type_factory=int,
            on_success=correct_price_handler,
        ),
        state=SuperOfferSG.PRICE,
    )
)
