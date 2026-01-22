# VPN Bot - Project Memory

Этот файл автоматически загружается при каждом запуске Claude Code и содержит ключевую информацию о проекте.

---

## 🚨🚨🚨 КРИТИЧЕСКИ ВАЖНО - ЧИТАЙ ПЕРЕД РАБОТОЙ! 🚨🚨🚨

### ⚠️ ПРОДАКШН СЕРВЕР - АКТУАЛЬНЫЙ КОД

```
Сервер: 193.124.182.161
Порт SSH: 2222
Путь: /root/VPNHubBot/
Доступ: sshpass -f /root/.ssh/.prod_password ssh -p 2222 root@193.124.182.161
```

### ⚠️ ПЕРЕД КОПИРОВАНИЕМ ФАЙЛОВ НА ПРОД:

1. **ВСЕГДА проверяй git status на ПРОДЕ** - там могут быть незакоммиченные изменения!
2. **ВСЕГДА делай бэкап перед копированием!**
3. **НЕТ volume mount на проде** - нужен `docker compose build` после изменений!

```bash
# Проверить статус на проде
sshpass -f /root/.ssh/.prod_password ssh -p 2222 root@193.124.182.161 "cd /root/VPNHubBot && git status"

# Сделать бэкап
sshpass -f /root/.ssh/.prod_password ssh -p 2222 root@193.124.182.161 "cp -r /root/VPNHubBot/bot /root/bot_backup_$(date +%Y%m%d_%H%M)"
```

**Подробнее**: `/root/claude-docs/knowledge/repository-locations.md`

---

## 🎯 О проекте

**VPN Bot** - Telegram бот для управления VPN подписками и серверами

- **Технологии**: Python, aiogram 3.x, PostgreSQL 16, Docker, FastAPI
- **Тип**: Production-ready VPN management bot
- **GitHub**: https://github.com/Marakoris/VPN_BOT

## 📁 Расположение

- **Тест репозиторий**: `/root/github_repos/VPN_BOT/` (основная работа здесь)
- **Продакшн (reference)**: `/root/production_server/VPNHubBot/`
- **Документация**: `/root/claude-docs/`

## 🏗️ Архитектура

### Основные компоненты

```
VPN_BOT/
├── bot/                          # Telegram бот
│   ├── handlers/                 # Обработчики команд
│   │   ├── user/                 # Пользовательские хендлеры
│   │   │   └── subscription_user.py  # Subscription UI
│   │   └── admin/                # Админ хендлеры
│   │       ├── main.py           # Рассылки, статистика
│   │       └── state_servers.py  # Управление серверами
│   ├── keyboards/                # Клавиатуры
│   ├── misc/                     # Утилиты
│   │   ├── subscription.py       # Логика подписок (Stages 1, 7)
│   │   └── VPN/                  # VPN интеграции
│   │       ├── Xui/              # VLESS + Shadowsocks
│   │       │   ├── Vless.py
│   │       │   └── Shadowsocks.py
│   │       └── Outline.py
│   └── database/methods/         # Методы работы с БД
├── subscription_api/             # FastAPI для подписок
│   ├── main.py                   # API endpoints (Stage 2)
│   ├── config_generators.py      # Генераторы конфигов (Stage 3)
│   └── security.py               # Security & rate limiting (Stage 6)
├── subscription_expiry_checker.py  # Cronjob (Stage 5)
├── tests/                        # Тесты
└── docker-compose.yml            # Deployment
```

### Docker контейнеры

| Контейнер | Назначение | Порт |
|-----------|------------|------|
| `vpn_bot-vpn_hub_bot-1` | Telegram бот | - |
| `subscription_api_container` | Subscription API | 8003 |
| `subscription_checker_container` | Cronjob (каждые 5 мин) | - |
| `postgres_db_container` | PostgreSQL 16 | 5432 |
| `pgadmin_container` | pgAdmin | 5050 |

## 🔑 Ключевые возможности

### 1. Subscription System (Stages 0-7 ✅)
- **Unified подписки** для VLESS + Shadowsocks серверов
- **Автоматическая активация/деактивация** ключей
- **API endpoint**: `http://185.58.204.196:8003/sub/{token}`
- **Security**: Rate limiting, brute-force protection
- **Cronjob**: Автоматическая проверка истечений каждые 5 минут

### 2. Поддерживаемые VPN протоколы
- **VLESS Reality** (type_vpn=1) - в подписках ✅
- **Shadowsocks 2022** (type_vpn=2) - в подписках ✅
- **Outline** (type_vpn=0) - НЕ в подписках (отдельная система)

### 3. Админ панель
- Управление серверами (добавление, удаление, редактирование)
- Рассылки с фильтрами (по VPN типу, по серверу, по статусу подписки)
- Статистика пользователей
- Автоматическое создание ключей для новых серверов (Stage 7)

## ⚡ Быстрые команды

### Перезапуск бота (3-5 секунд)
```bash
docker restart vpn_bot-vpn_hub_bot-1
```

### Логи в реальном времени
```bash
docker logs -f vpn_bot-vpn_hub_bot-1
```

### Git workflow
```bash
cd /root/github_repos/VPN_BOT
git status
git add .
git commit -m "Description"
git push
```

### База данных
```bash
# Подключение к PostgreSQL
docker exec -it postgres_db_container psql -U postgres -d vpn_hub

# Быстрый запрос
docker exec postgres_db_container psql -U postgres -d vpn_hub -c "SELECT * FROM users WHERE subscription_active = true;"
```

### Docker полезности
```bash
# Статус всех контейнеров
docker ps

# Перезапустить все сервисы
cd /root/github_repos/VPN_BOT && docker-compose restart

# Логи subscription API
docker logs -f subscription_api_container

# Логи cronjob checker
docker logs -f subscription_checker_container
```

## 🗂️ Важная документация

Используйте `@` для быстрого доступа:

### Основная документация
- **@/root/claude-docs/QUICK_START.md** - Быстрый старт для новой сессии
- **@/root/claude-docs/STATUS.md** - Полный статус проекта (все этапы, проблемы, решения)
- **@/root/claude-docs/README.md** - Обзор системы документации

### База знаний
- **@/root/claude-docs/knowledge/vpn-bot-structure.md** - Детальная структура проекта
- **@/root/claude-docs/knowledge/subscription-system-implementation-complete.md** - Полная документация Stages 0-5
- **@/root/claude-docs/knowledge/subscription-algorithm.md** - Алгоритм работы подписок
- **@/root/claude-docs/knowledge/outline-vs-vless-shadowsocks.md** - Сравнение протоколов

### История сессий
- **@/root/claude-docs/sessions/** - Все прошлые сессии с решёнными проблемами

### Checkpoints
- **@/root/claude-docs/checkpoints/** - Важные вехи разработки

## 🔧 Workflow разработки

1. **Редактирование кода**
   - Изменения в `/root/github_repos/VPN_BOT/bot/`
   - Файлы монтируются как volume, изменения видны сразу

2. **Тестирование**
   - `docker restart vpn_bot-vpn_hub_bot-1` (3-5 секунд)
   - Проверить логи: `docker logs --tail=50 vpn_bot-vpn_hub_bot-1`
   - Тестировать в Telegram

3. **Коммит**
   ```bash
   git add .
   git commit -m "Description"
   git push
   ```

## 🚨 Важные замечания

### При работе с подписками
- Outline серверы **НЕ включены** в subscription систему (архитектурное решение)
- Только VLESS (type_vpn=1) и Shadowsocks (type_vpn=2) в подписках
- Токены подписок используют HMAC подпись с `SUBSCRIPTION_SECRET_KEY` из `.env`

### При добавлении новых серверов
- Stage 7 автоматически создаёт ключи для всех активных подписок
- Работает только для VLESS и Shadowsocks серверов
- Админ получает детальный отчёт после добавления

### При отладке проблем
1. Проверить логи бота: `docker logs --tail=100 vpn_bot-vpn_hub_bot-1`
2. Проверить логи API: `docker logs --tail=100 subscription_api_container`
3. Проверить логи cronjob: `docker logs --tail=100 subscription_checker_container`
4. Проверить БД: `docker exec postgres_db_container psql -U postgres -d vpn_hub -c "SELECT * FROM users WHERE telegram_id=123456;"`

## 🔐 Environment Variables

Основные переменные в `.env`:

```env
# Database
POSTGRES_DB=VPNHubBotDB_TEST
POSTGRES_USER=marakoris_test
POSTGRES_PASSWORD=[см. .env файл]

# Bot
TG_TOKEN=[см. .env файл]

# Subscription API
SUBSCRIPTION_API_URL=http://185.58.204.196:8003
SUBSCRIPTION_SECRET_KEY=[см. .env файл]

# Cronjob
SUBSCRIPTION_CHECK_INTERVAL=300
```

## 🔒 Безопасность credentials

### SOPS + age шифрование
Файлы с паролями зашифрованы с помощью SOPS + age:
- `projects/vpn-servers/vpn-servers-credentials.enc.md` — доступы к VPN серверам
- `projects/infrastructure/server-connections.enc.md` — SSH доступы

**Расшифровка** (ключ должен быть в `~/.config/sops/age/keys.txt`):
```bash
sops -d /root/claude-docs/projects/vpn-servers/vpn-servers-credentials.enc.md
```

### ⚠️ ПРАВИЛА работы с credentials
1. **НЕ копировать пароли в сессии** — писать `см. credentials файл`
2. **НЕ показывать пароли в чате** — использовать ссылки на файлы
3. **При необходимости доступа** — расшифровать файл через `sops -d`
4. **Случайно попал пароль в сессию** — немедленно удалить из файла

## 📊 Текущий статус

- **Subscription System**: ✅ Полностью реализована (Stages 0-7)
- **Docker**: ✅ Все контейнеры работают
- **Тесты**: ✅ 23/27 passed (4 теста требуют БД подключения)
- **Production ready**: ✅ Да

### Известные проблемы
- ✅ VLESS Reality не работает в v2rayN - решено (используйте Hiddify)
- Все остальные проблемы решены

## 🎓 Соглашения проекта

### Коммиты
- Используйте осмысленные сообщения
- Формат: `[Component] Description` (например: `[Subscription] Add rate limiting`)

### Код
- Python: PEP8, type hints где возможно
- Async/await для всех IO операций
- Логирование важных событий

### Документация
- Все сессии документируются в `/root/claude-docs/sessions/`
- Используйте шаблон: `/root/claude-docs/templates/session-template.md`
- Checkpoints для важных вех: `/root/claude-docs/checkpoints/`

---

**Последнее обновление**: 2026-01-19
**Версия проекта**: 2.0 (Subscription System Complete)
