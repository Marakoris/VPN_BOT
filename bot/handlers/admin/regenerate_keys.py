import asyncio
import logging
import time
from typing import List, Dict

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State

from bot.filters.main import IsAdmin
from bot.database.methods.get import (
    get_all_server,
    get_server_id,
    get_users_by_server_and_vpn_type
)
from bot.keyboards.inline.admin_inline import (
    regenerate_server_selection_menu,
    regenerate_protocol_selection_menu,
    regenerate_confirm_menu
)
from bot.keyboards.reply.admin_reply import admin_menu
from bot.misc.VPN.ServerManager import ServerManager
from bot.misc.callbackData import (
    RegenerateKeys,
    RegenerateServerToggle,
    RegenerateProtocolToggle
)
from bot.misc.language import Localization, get_lang
from bot.misc.util import CONFIG

log = logging.getLogger(__name__)
_ = Localization.text

regenerate_router = Router()
regenerate_router.message.filter(IsAdmin())


class RegenerateKeysState(StatesGroup):
    """Состояния для процесса регенерации ключей"""
    selecting_servers = State()
    selecting_protocols = State()
    confirming = State()


async def regenerate_keys_for_users(
    users: List,
    servers_dict: Dict,
    bot,
    progress_message: Message,
    lang: str
):
    """
    Основная функция регенерации ключей

    Args:
        users: Список пользователей для регенерации
        servers_dict: Словарь серверов {server_id: server_object}
        bot: Telegram Bot instance
        progress_message: Сообщение для обновления прогресса
        lang: Язык пользователя

    Returns:
        Tuple (успешно, ошибки_список)
    """
    total = len(users)
    success_count = 0
    error_count = 0
    errors = []

    # Группируем пользователей по серверам для оптимизации
    users_by_server = {}
    for user in users:
        if user.server not in users_by_server:
            users_by_server[user.server] = []
        users_by_server[user.server].append(user)

    processed = 0
    start_time = time.time()

    for server_id, server_users in users_by_server.items():
        if server_id not in servers_dict:
            error_count += len(server_users)
            for user in server_users:
                errors.append({
                    'user': user,
                    'error': 'Сервер не найден'
                })
            continue

        server = servers_dict[server_id]

        try:
            # Подключаемся к серверу один раз для всех пользователей
            server_manager = ServerManager(server)
            await server_manager.login()

            for user in server_users:
                try:
                    # 1. Удаляем старого клиента
                    try:
                        await server_manager.delete_client(user.tgid)
                    except Exception as e:
                        log.warning(f"Could not delete old client for user {user.tgid}: {e}")
                        # Продолжаем даже если не удалось удалить

                    # 2. Создаем нового клиента
                    await server_manager.add_client(user.tgid)

                    # 3. Генерируем новый ключ
                    new_key = await server_manager.get_key(user.tgid, CONFIG.name)

                    if not new_key:
                        raise Exception("Не удалось сгенерировать ключ")

                    # 4. Отправляем пользователю новый ключ
                    vpn_type_name = ServerManager.VPN_TYPES.get(server.type_vpn).NAME_VPN
                    message_text = (
                        f"🔄 Обновление VPN соединения\n\n"
                        f"Произошло обновление сервера {server.name}. "
                        f"Ваш VPN ключ был обновлен.\n\n"
                        f"🔑 Новый ключ:\n"
                        f"<code>{new_key}</code>\n\n"
                        f"📱 Инструкция:\n"
                        f"1. Удалите старый ключ из приложения\n"
                        f"2. Добавьте новый ключ\n"
                        f"3. Подключитесь\n\n"
                        f"❓ Если возникли проблемы, напишите в поддержку"
                    )

                    try:
                        await bot.send_message(
                            user.tgid,
                            message_text,
                            parse_mode='HTML'
                        )
                        success_count += 1
                    except Exception as e:
                        log.warning(f"Could not send message to user {user.tgid}: {e}")
                        # Ключ создан, но сообщение не отправлено
                        errors.append({
                            'user': user,
                            'error': f'Ключ создан, но не отправлен: {str(e)}'
                        })
                        error_count += 1

                except Exception as e:
                    log.error(f"Failed to regenerate key for user {user.tgid}: {e}")
                    errors.append({
                        'user': user,
                        'error': str(e)
                    })
                    error_count += 1

                processed += 1

                # Обновляем прогресс каждые 10 пользователей или в конце
                if processed % 10 == 0 or processed == total:
                    percentage = int((processed / total) * 100)
                    progress_bar = '▓' * (percentage // 5) + '░' * (20 - percentage // 5)

                    elapsed_time = int(time.time() - start_time)
                    avg_time_per_user = elapsed_time / processed if processed > 0 else 0
                    remaining_time = int(avg_time_per_user * (total - processed))

                    try:
                        await progress_message.edit_text(
                            f"🔄 Регенерация ключей...\n\n"
                            f"📊 Прогресс:\n"
                            f"{progress_bar} {percentage}%\n\n"
                            f"✅ Обработано: {processed}/{total}\n"
                            f"⏳ Осталось: {total - processed}\n"
                            f"❌ Ошибок: {error_count}\n\n"
                            f"Текущий сервер: {server.name}\n"
                            f"⏱️ Осталось времени: ~{remaining_time // 60}м {remaining_time % 60}с"
                        )
                    except Exception as e:
                        log.warning(f"Could not update progress message: {e}")

                # Небольшая задержка, чтобы не перегружать API
                await asyncio.sleep(0.05)

        except Exception as e:
            log.error(f"Failed to connect to server {server.name}: {e}")
            error_count += len(server_users)
            for user in server_users:
                errors.append({
                    'user': user,
                    'error': f'Сервер недоступен: {str(e)}'
                })
            processed += len(server_users)

    return success_count, errors


@regenerate_router.callback_query(RegenerateKeys.filter(F.action == 'start'))
async def start_regenerate_keys(call: CallbackQuery, state: FSMContext):
    """Начало процесса регенерации ключей - выбор серверов"""
    lang = await get_lang(call.from_user.id, state)

    # Получаем все серверы
    all_servers = await get_all_server()

    # Фильтруем только Outline, Vless и Shadowsocks серверы
    available_servers = [s for s in all_servers if s.type_vpn in [0, 1, 2]]

    if not available_servers:
        await call.message.answer(
            "❌ Нет доступных серверов для регенерации.\n"
            "Регенерация доступна для Outline, Vless и Shadowsocks серверов."
        )
        await call.answer()
        return

    # Инициализируем состояние
    await state.update_data(
        selected_servers=[],
        selected_protocols=[]
    )
    await state.set_state(RegenerateKeysState.selecting_servers)

    # Показываем меню выбора серверов
    await call.message.answer(
        "🌍 Выберите серверы для регенерации ключей:\n\n"
        "Выберите один или несколько серверов, на которых нужно обновить ключи.",
        reply_markup=await regenerate_server_selection_menu(available_servers, [], lang)
    )
    await call.answer()


@regenerate_router.callback_query(RegenerateServerToggle.filter())
async def toggle_server_selection(
    call: CallbackQuery,
    callback_data: RegenerateServerToggle,
    state: FSMContext
):
    """Переключение выбора сервера"""
    lang = await get_lang(call.from_user.id, state)
    data = await state.get_data()
    selected_servers = data.get('selected_servers', [])

    # Переключаем выбор
    if callback_data.server_id in selected_servers:
        selected_servers.remove(callback_data.server_id)
    else:
        selected_servers.append(callback_data.server_id)

    await state.update_data(selected_servers=selected_servers)

    # Обновляем клавиатуру
    all_servers = await get_all_server()
    available_servers = [s for s in all_servers if s.type_vpn in [0, 1, 2]]

    await call.message.edit_reply_markup(
        reply_markup=await regenerate_server_selection_menu(available_servers, selected_servers, lang)
    )
    await call.answer()


@regenerate_router.callback_query(RegenerateKeys.filter(F.action == 'select_servers'))
async def back_to_server_selection(call: CallbackQuery, state: FSMContext):
    """Возврат к выбору серверов"""
    lang = await get_lang(call.from_user.id, state)
    data = await state.get_data()
    selected_servers = data.get('selected_servers', [])

    all_servers = await get_all_server()
    available_servers = [s for s in all_servers if s.type_vpn in [0, 1, 2]]

    await state.set_state(RegenerateKeysState.selecting_servers)

    await call.message.edit_text(
        "🌍 Выберите серверы для регенерации ключей:\n\n"
        "Выберите один или несколько серверов, на которых нужно обновить ключи.",
        reply_markup=await regenerate_server_selection_menu(available_servers, selected_servers, lang)
    )
    await call.answer()


@regenerate_router.callback_query(RegenerateKeys.filter(F.action == 'select_protocols'))
async def select_protocols(call: CallbackQuery, state: FSMContext):
    """Переход к выбору протоколов"""
    lang = await get_lang(call.from_user.id, state)
    data = await state.get_data()
    selected_servers = data.get('selected_servers', [])
    selected_protocols = data.get('selected_protocols', [])

    if not selected_servers:
        await call.answer("⚠️ Выберите хотя бы один сервер", show_alert=True)
        return

    # Подсчитываем пользователей по протоколам на выбранных серверах
    user_count_by_protocol = {0: 0, 1: 0, 2: 0}  # Outline, Vless, Shadowsocks

    for server_id in selected_servers:
        server = await get_server_id(server_id)
        if server:
            users = await get_users_by_server_and_vpn_type(server_id=server.id)
            # Фильтруем только активных
            active_users = [u for u in users if u.subscription and u.subscription > int(time.time()) and not u.banned]

            if server.type_vpn in user_count_by_protocol:
                user_count_by_protocol[server.type_vpn] += len(active_users)

    await state.update_data(user_count_by_protocol=user_count_by_protocol)
    await state.set_state(RegenerateKeysState.selecting_protocols)

    await call.message.edit_text(
        "📡 Выберите протоколы VPN:\n\n"
        "Выберите один или несколько протоколов для регенерации.",
        reply_markup=await regenerate_protocol_selection_menu(selected_protocols, user_count_by_protocol, lang)
    )
    await call.answer()


@regenerate_router.callback_query(RegenerateProtocolToggle.filter())
async def toggle_protocol_selection(
    call: CallbackQuery,
    callback_data: RegenerateProtocolToggle,
    state: FSMContext
):
    """Переключение выбора протокола"""
    try:
        log.info(f"=== Protocol toggle START ===")
        log.info(f"Received callback_data.protocol: {callback_data.protocol!r} (type: {type(callback_data.protocol)})")

        lang = await get_lang(call.from_user.id, state)
        data = await state.get_data()
        selected_protocols = data.get('selected_protocols', [])
        user_count_by_protocol = data.get('user_count_by_protocol', {0: 0, 1: 0, 2: 0})

        log.info(f"Before toggle - selected_protocols: {selected_protocols}")

        # Переключаем выбор (теперь работаем со строками: 'outline', 'vless', 'shadowsocks')
        protocol_key = callback_data.protocol
        if protocol_key in selected_protocols:
            selected_protocols.remove(protocol_key)
            log.info(f"Removed protocol: {protocol_key}")
        else:
            selected_protocols.append(protocol_key)
            log.info(f"Added protocol: {protocol_key}")

        log.info(f"After toggle - selected_protocols: {selected_protocols}")

        await state.update_data(selected_protocols=selected_protocols)

        # Генерируем новую клавиатуру
        log.info(f"Generating new keyboard with user_count: {user_count_by_protocol}")
        new_keyboard = await regenerate_protocol_selection_menu(selected_protocols, user_count_by_protocol, lang)

        log.info(f"Updating message reply markup...")
        await call.message.edit_reply_markup(reply_markup=new_keyboard)

        await call.answer()
        log.info(f"=== Protocol toggle END (success) ===")
    except Exception as e:
        log.error(f"=== Protocol toggle ERROR: {e} ===", exc_info=True)
        await call.answer(f"Ошибка: {e}", show_alert=True)


@regenerate_router.callback_query(RegenerateKeys.filter(F.action == 'confirm'))
async def confirm_regeneration(call: CallbackQuery, state: FSMContext):
    """Подтверждение регенерации"""
    lang = await get_lang(call.from_user.id, state)
    data = await state.get_data()
    selected_servers = data.get('selected_servers', [])
    selected_protocols = data.get('selected_protocols', [])

    if not selected_protocols:
        await call.answer("⚠️ Выберите хотя бы один протокол", show_alert=True)
        return

    # Конвертируем строковые ключи протоколов в числовые ID
    protocol_map = {'outline': 0, 'vless': 1, 'shadowsocks': 2}
    selected_protocol_ids = [protocol_map[p] for p in selected_protocols if p in protocol_map]

    # Подсчитываем общее количество пользователей
    total_users = 0
    servers_info = []
    servers_count = 0

    for server_id in selected_servers:
        server = await get_server_id(server_id)
        if server and server.type_vpn in selected_protocol_ids:
            servers_count += 1
            users = await get_users_by_server_and_vpn_type(server_id=server.id)
            active_users = [u for u in users if u.subscription and u.subscription > int(time.time()) and not u.banned]
            total_users += len(active_users)

            # Добавляем эмодзи VPN типа
            vpn_emojis = {0: '🪐', 1: '🐊', 2: '🦈'}
            vpn_emoji = vpn_emojis.get(server.type_vpn, '❓')
            servers_info.append(f"• {vpn_emoji} {server.name}: {len(active_users)} пользователей")

    if total_users == 0:
        await call.message.answer(
            "❌ Не найдено активных пользователей для выбранных параметров."
        )
        await call.answer()
        return

    protocol_names = {0: 'Outline 🪐', 1: 'Vless 🐊', 2: 'Shadowsocks 🦈'}
    selected_protocol_names = [protocol_names[pid] for pid in selected_protocol_ids]

    # Оценка времени (примерно 0.15 сек на пользователя + подключение к серверам)
    estimated_seconds = int(total_users * 0.15) + (servers_count * 2)  # +2 сек на подключение к каждому серверу
    estimated_minutes = estimated_seconds // 60
    estimated_seconds = estimated_seconds % 60

    # Если меньше 1 секунды, показываем хотя бы 1 сек
    if estimated_minutes == 0 and estimated_seconds == 0:
        estimated_seconds = 1

    confirm_text = (
        f"⚠️ ВНИМАНИЕ! Регенерация ключей\n\n"
        f"📊 Параметры:\n"
        f"• Серверов: {servers_count}\n"
        f"• Протоколы: {', '.join(selected_protocol_names)}\n"
        f"• Активных пользователей: {total_users}\n\n"
        f"🔄 Что будет сделано:\n"
        f"1️⃣ Удаление старых клиентов с серверов\n"
        f"2️⃣ Создание новых клиентов\n"
        f"3️⃣ Генерация новых ключей\n"
        f"4️⃣ Отправка сообщений пользователям\n\n"
        f"📋 Серверы:\n" + "\n".join(servers_info) + "\n\n"
        f"⏱️ Примерное время: ~{estimated_minutes}м {estimated_seconds}с\n\n"
        f"Вы уверены?"
    )

    await state.set_state(RegenerateKeysState.confirming)

    await call.message.edit_text(
        confirm_text,
        reply_markup=await regenerate_confirm_menu(lang)
    )
    await call.answer()


@regenerate_router.callback_query(RegenerateKeys.filter(F.action == 'execute'))
async def execute_regeneration(call: CallbackQuery, state: FSMContext):
    """Выполнение регенерации ключей"""
    lang = await get_lang(call.from_user.id, state)
    data = await state.get_data()
    selected_servers = data.get('selected_servers', [])
    selected_protocols = data.get('selected_protocols', [])

    # Конвертируем строковые ключи протоколов в числовые ID
    protocol_map = {'outline': 0, 'vless': 1, 'shadowsocks': 2}
    selected_protocol_ids = [protocol_map[p] for p in selected_protocols if p in protocol_map]

    # Собираем пользователей для регенерации
    users_to_regenerate = []
    servers_dict = {}

    for server_id in selected_servers:
        server = await get_server_id(server_id)
        if server and server.type_vpn in selected_protocol_ids:
            servers_dict[server.id] = server
            users = await get_users_by_server_and_vpn_type(server_id=server.id)
            # Фильтруем только активных
            active_users = [u for u in users if u.subscription and u.subscription > int(time.time()) and not u.banned]
            users_to_regenerate.extend(active_users)

    if not users_to_regenerate:
        await call.message.answer("❌ Не найдено активных пользователей для регенерации.")
        await call.answer()
        await state.clear()
        return

    # Создаем сообщение прогресса
    progress_message = await call.message.answer(
        "🔄 Начинаем регенерацию ключей...\n\n"
        f"Всего пользователей: {len(users_to_regenerate)}"
    )

    await call.answer()

    # Выполняем регенерацию
    start_time = time.time()
    success_count, errors = await regenerate_keys_for_users(
        users_to_regenerate,
        servers_dict,
        call.bot,
        progress_message,
        lang
    )

    elapsed_time = int(time.time() - start_time)

    # Формируем отчет
    result_text = (
        f"✅ Регенерация ключей завершена!\n\n"
        f"📊 Результаты:\n"
        f"• Всего пользователей: {len(users_to_regenerate)}\n"
        f"• ✅ Успешно: {success_count}\n"
        f"• ❌ Ошибок: {len(errors)}\n\n"
        f"⏱️ Время выполнения: {elapsed_time // 60}м {elapsed_time % 60}с"
    )

    # Если были ошибки, добавляем их в отчет
    if errors:
        result_text += "\n\n❌ Не удалось создать ключи:\n"
        # Ограничиваем до 10 ошибок в сообщении
        for error in errors[:10]:
            user = error['user']
            error_msg = error['error']
            username = f"@{user.username}" if user.username else f"ID: {user.tgid}"
            result_text += f"• {username} - {error_msg}\n"

        if len(errors) > 10:
            result_text += f"\n... и еще {len(errors) - 10} ошибок"

    await progress_message.edit_text(result_text)

    # Возвращаемся в админ меню
    await call.message.answer(
        "Готово! Регенерация завершена.",
        reply_markup=await admin_menu(lang)
    )

    await state.clear()


@regenerate_router.callback_query(RegenerateKeys.filter(F.action == 'cancel'))
async def cancel_regeneration(call: CallbackQuery, state: FSMContext):
    """Отмена регенерации"""
    lang = await get_lang(call.from_user.id, state)

    await call.message.edit_text("❌ Регенерация ключей отменена.")
    await call.answer()
    await state.clear()

    await call.message.answer(
        "Вы вернулись в главное меню.",
        reply_markup=await admin_menu(lang)
    )
