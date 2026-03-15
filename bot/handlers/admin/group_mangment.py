import io
import logging

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import CallbackQuery, Message, BufferedInputFile
from aiogram.utils.formatting import Text, Bold, as_list, Code

from bot.database.methods.delete import delete_group
from bot.database.methods.get import (
    get_all_groups,
    get_users_group,
    get_person_id,
    get_group, get_group_name, get_count_groups
)
from bot.database.methods.insert import add_group
from bot.database.methods.update import persons_add_group
from bot.handlers.admin.user_management import string_user
from bot.keyboards.inline.admin_inline import group_control
from bot.keyboards.reply.admin_reply import admin_group_menu, back_admin_menu
from bot.misc.callbackData import GroupAction
from bot.misc.language import Localization, get_lang
from bot.misc.loop import delete_key
from bot.misc.util import CONFIG

log = logging.getLogger(__name__)

_ = Localization.text
btn_text = Localization.get_reply_button

group_management = Router()


class GroupUser(StatesGroup):
    users_id_input = State()


class Group(StatesGroup):
    name_input = State()


class GroupActionName(StatesGroup):
    name_input = State()


@group_management.message(F.text.in_(btn_text('admin_groups_btn')))
async def group_panel(message: Message, state: FSMContext) -> None:
    lang = await get_lang(message.from_user.id, state)
    await message.answer(
        _('admin_group_control_message', lang),
        reply_markup=await admin_group_menu(lang)
    )
    await state.clear()


@group_management.message(F.text.in_(btn_text('admin_groups_show_btn')))
async def group_panel(message: Message, state: FSMContext) -> None:
    lang = await get_lang(message.from_user.id, state)
    groups = await get_all_groups()
    if len(groups) == 0:
        await message.answer(_('groups_counts_zero', lang))
        return
    await message.answer(_('admin_group_list_groups', lang))
    text = await groups_obj_list(groups)
    await message.answer(
        **text.as_kwargs(),
        reply_markup=await group_control(lang)
    )
    await state.clear()


async def groups_obj_list(groups):
    number_group = 1
    list_text = []
    for group in groups:
        text_obj = Text(
            number_group, ') ', Code(group['group'].name), ' -- ',
            Bold(group['count_user']), ' 👨‍💼  ',
            Bold(group['count_server']), '  🖥'
        )
        list_text.append(text_obj)
        number_group += 1
    return as_list(*list_text, sep='\n')


@group_management.callback_query(GroupAction.filter())
async def show_group_user(
        callback: CallbackQuery,
        state: FSMContext,
        callback_data: GroupActionName
):
    lang = await get_lang(callback.from_user.id, state)
    await state.update_data(action=callback_data.action)
    await callback.message.answer(_('group_input_name', lang))
    await state.set_state(GroupActionName.name_input)
    await callback.answer()


@group_management.message(GroupActionName.name_input)
async def choosing_action(message: Message, state: FSMContext) -> None:
    lang = await get_lang(message.from_user.id, state)
    group = await get_group_name(message.text.strip())
    if group is None:
        text = Text(
            _('group_name_not_found', lang).format(
                name=message.text.strip()
            )
        )
        await message.answer(
            **text.as_kwargs(),
        )
        return
    data = await state.get_data()
    action = data.get('action')
    await state.update_data(group_id=group.id)
    if action == 'show':
        await action_show_group_user(message, group.id, lang)
    elif action == 'delete':
        await action_delete_group(message, group.id, lang)
    elif action == 'add' or action == 'exclude':
        await action_update_users_group(message, state, lang)
    else:
        log.error('Action not found')


async def action_show_group_user(message: Message, id_group: int, lang: str):
    users = await get_users_group(id_group)
    if len(users) == 0:
        await message.answer(
            _('admin_group_list_groups_none', lang),
            show_alert=True
        )
        return
    str_user = ''
    count = 1
    for user in users:
        str_user += await string_user(user, count, lang)
        count += 1
    file_stream = io.BytesIO(str_user.encode()).getvalue()
    input_file = BufferedInputFile(file_stream, 'user_group.txt')
    try:
        await message.answer_document(
            input_file,
            caption=_('admin_group_list_groups_file', lang)
        )
    except Exception as e:
        await message.answer(
            _('error_list_of_all_users_file', lang)
        )
        log.error(e, 'error send file all_user.txt')


async def action_update_users_group(
        message: Message,
        state: FSMContext,
        lang: str
):
    await message.answer(
        _('admin_group_user_input_id', lang),
        reply_markup=await back_admin_menu(lang)
    )
    await state.set_state(GroupUser.users_id_input)


@group_management.message(GroupUser.users_id_input)
async def add_group_users(message: Message, state: FSMContext) -> None:
    lang = await get_lang(message.from_user.id, state)
    data = await state.get_data()
    group = await get_group(int(data['group_id']))
    users_id_str = message.text.strip().split(',')
    users_id_number = []
    for id_user in users_id_str:
        if id_user.isdigit():
            users_id_number.append(int(id_user))
    users = await get_person_id(users_id_number)
    users_id = []
    for user in users:
        if user.server is not None:
            await delete_key(user)
        users_id.append(user.tgid)
    if data['action'] == 'add':
        count_users = await persons_add_group(users_id, group.name)
        message_user = _('admin_group_user_add_success', lang)
    else:
        count_users = await persons_add_group(users_id)
        message_user = _('admin_group_user_exclude_success', lang)
    await message.answer(
        f'{message_user} {count_users}',
        reply_markup=await admin_group_menu(lang)
    )
    await state.clear()


async def action_delete_group(message: Message, id_group: int, lang: str):
    users = await get_users_group(id_group)
    for user in users:
        if user.server is not None:
            await delete_key(user)
    await delete_group(int(id_group))
    await message.answer(
        _('admin_group_delete_success', lang)
    )


@group_management.message(F.text.in_(btn_text('admin_groups_add_btn')))
async def group_panel(message: Message, state: FSMContext) -> None:
    lang = await get_lang(message.from_user.id, state)
    count_group = await get_count_groups()
    if count_group >= CONFIG.max_count_groups:
        await message.answer(
            _('groups_max_count', lang)
            .format(count=CONFIG.max_count_groups)
        )
        return
    await message.answer(
        _('admin_group_add_input_name', lang),
        reply_markup=await back_admin_menu(lang)
    )
    await state.set_state(Group.name_input)


@group_management.message(Group.name_input)
async def add_group_users(message: Message, state: FSMContext) -> None:
    lang = await get_lang(message.from_user.id, state)
    group_name = message.text.strip()
    try:
        await add_group(group_name)
        await message.answer(
            _('admin_group_add_success', lang),
            reply_markup=await admin_group_menu(lang)
        )
    except Exception as e:
        await message.answer(
            _('admin_group_add_error', lang),
            reply_markup=await admin_group_menu(lang)
        )
        log.info('error add group', e)
    finally:
        await state.clear()

