# 🧪 ПЛАН РАБОТЫ С ТЕСТОВЫМ БОТОМ

## 📋 Текущая ситуация

### ✅ Что уже есть:
- Тестовая база с 9 тестовыми пользователями
- Отдельный токен бота (7501968261:AAFFQhRO8YLWB71rrm4zmCiixJgzy1zqwvU)
- Новый код с функциями disable/enable вместо delete
- 6 тестовых VPN серверов

### ⚠️ Проблемы в коде:
1. **VLESS:** Использует `expiryTime` вместо `expiry_time` - правильно! (не баг)
2. **Shadowsocks:** Добавляет суффикс `_ss` к email - старые ключи без суффикса не найдутся
3. **Тестовые серверы:** Нужно проверить что они доступны

---

## 🚀 ПЛАН ДЕЙСТВИЙ

### Шаг 1: Проверка тестовых серверов
```bash
cd /root/github_repos/VPN_BOT
docker compose up -d db_postgres
# Запустить скрипт проверки серверов
```

**Проверить:**
- Доступны ли тестовые VPN серверы?
- Есть ли на них панели управления?
- Работают ли они?

### Шаг 2: Решить с проблемой Shadowsocks суффикса

**Вариант А:** Удалить старые ключи без `_ss` в тестовой БД
```sql
-- Если в тесте есть старые ключи ShadowSocks без _ss
DELETE FROM users WHERE server IN (SELECT id FROM servers WHERE type_vpn = 2);
-- И создать заново с новым кодом
```

**Вариант Б:** Добавить миграцию/совместимость в код

### Шаг 3: Запуск тестового бота

```bash
cd /root/github_repos/VPN_BOT

# Проверить что БД запущена
docker compose ps

# Запустить бота
docker compose up -d vpn_hub_bot

# Проверить логи
docker compose logs -f vpn_hub_bot
```

### Шаг 4: Тестирование disable/enable функционала

**Тест-кейсы:**

1. **Создание нового пользователя:**
   - Зайти в бота от @test_outline_1
   - Создать подписку на Outline сервере
   - Проверить что ключ создался

2. **Истечение подписки (симуляция):**
   - Вручную в БД установить subscription в прошлое
   - Запустить process_subscriptions
   - Проверить что ключ disabled (не deleted!)

3. **Автопродление:**
   - Установить payment_method_id
   - Симулировать истечение
   - Проверить что ключ enabled обратно

4. **Проверка на всех типах VPN:**
   - Outline: disable/enable через data_limit
   - VLESS: disable/enable через enable=false/true
   - Shadowsocks: disable/enable через enable=false/true

### Шаг 5: Исправление багов (если найдены)

После тестирования:
1. Исправить найденные баги
2. Commit в github_repos/VPN_BOT
3. Push в Marakoris/VPN_BOT
4. Повторить тесты

### Шаг 6: Деплой на продакшн (когда всё работает)

```bash
# На продакшн сервере (193.124.182.161)
cd /root/VPNHubBot
git pull origin main  # или слить из Marakoris/VPN_BOT
docker compose down
docker compose build
docker compose up -d
docker compose logs -f vpn_hub_bot
```

---

## 🔧 ПОЛЕЗНЫЕ КОМАНДЫ

### Управление тестовым ботом:
```bash
cd /root/github_repos/VPN_BOT

# Запустить всё
docker compose up -d

# Запустить только БД
docker compose up -d db_postgres

# Остановить
docker compose down

# Логи бота
docker compose logs -f vpn_hub_bot

# Перезапустить с пересборкой
docker compose down
docker compose build
docker compose up -d
```

### Работа с тестовой БД:
```bash
# Подключиться к БД
docker exec -it postgres_db_container psql -U marakoris_test -d VPNHubBotDB_TEST

# Проверить пользователей
docker exec postgres_db_container psql -U marakoris_test -d VPNHubBotDB_TEST -c "SELECT tgid, username, server, subscription FROM users;"

# Проверить серверы
docker exec postgres_db_container psql -U marakoris_test -d VPNHubBotDB_TEST -c "SELECT id, name, type_vpn, ip FROM servers;"

# Симулировать истечение подписки
docker exec postgres_db_container psql -U marakoris_test -d VPNHubBotDB_TEST -c "UPDATE users SET subscription = EXTRACT(EPOCH FROM NOW() - INTERVAL '1 day')::bigint WHERE tgid = 1111111111;"
```

### Тестирование disable/enable:
```bash
# Запустить скрипт тестирования
cd /root/github_repos/VPN_BOT
docker compose up -d
docker exec vpn_hub_bot python -c "
from bot.misc.check_and_proceed_subscriptions import process_subscriptions
import asyncio
asyncio.run(process_subscriptions(None, None))
"
```

---

## ⚠️ ВАЖНЫЕ ЗАМЕЧАНИЯ

1. **НЕ ПУТАТЬ** с `/root/production_server/VPNHubBot_BACKUP_PROD_DO_NOT_USE/`
2. **ВСЕГДА** проверять `hostname` и `pwd` перед работой
3. **ДЕЛАТЬ КОММИТЫ** после успешных тестов
4. **НЕ ДЕПЛОИТЬ** на продакшн без полного тестирования

---

**Последнее обновление:** 22.11.2025
