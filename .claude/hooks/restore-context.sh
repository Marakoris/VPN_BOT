#!/bin/bash

# SessionStart Hook - Автоматическое восстановление контекста
# Запускается при каждом старте Claude Code
# Updated: 2026-01-19 - Added git sync check

# Determine environment early for env vars
early_detect_env() {
  LOCAL_IP=$(hostname -I 2>/dev/null | awk '{print $1}')

  # Check by IP first (most reliable)
  if [ "$LOCAL_IP" = "109.69.56.185" ]; then
    echo "PRODUCTION"
  elif [ "$LOCAL_IP" = "185.58.204.196" ]; then
    echo "TEST"
  # Fallback: check by directory structure
  elif [ -d "/root/VPNHubBot" ] && [ ! -d "/root/github_repos" ]; then
    echo "PRODUCTION"
  else
    echo "TEST"
  fi
}

EARLY_ENV=$(early_detect_env)

# Persist environment variables for the session
if [ -n "$CLAUDE_ENV_FILE" ]; then
  echo "export ENVIRONMENT=$EARLY_ENV" >> "$CLAUDE_ENV_FILE"

  if [ "$EARLY_ENV" = "PRODUCTION" ]; then
    echo "export PROJECT_DIR=/root/VPNHubBot" >> "$CLAUDE_ENV_FILE"
    echo "export DOCKER_CONTAINER=vpnhubbot-vpn_hub_bot-1" >> "$CLAUDE_ENV_FILE"
    echo "export DOCKER_DB_CONTAINER=postgres_db_container" >> "$CLAUDE_ENV_FILE"
    echo "export DB_USER=marakoris" >> "$CLAUDE_ENV_FILE"
    echo "export DB_NAME=VPNHubBotDB" >> "$CLAUDE_ENV_FILE"
  else
    echo "export PROJECT_DIR=/root/github_repos/VPN_BOT" >> "$CLAUDE_ENV_FILE"
    echo "export DOCS_DIR=/root/claude-docs" >> "$CLAUDE_ENV_FILE"
    echo "export DOCKER_CONTAINER=vpn_bot-vpn_hub_bot-1" >> "$CLAUDE_ENV_FILE"
    echo "export DOCKER_DB_CONTAINER=postgres_db_container" >> "$CLAUDE_ENV_FILE"
    echo "export DB_USER=marakoris_test" >> "$CLAUDE_ENV_FILE"
    echo "export DB_NAME=VPNHubBotDB_TEST" >> "$CLAUDE_ENV_FILE"
    echo "export PRODUCTION_DIR=/root/production_server/VPNHubBot" >> "$CLAUDE_ENV_FILE"
  fi
fi

# Determine environment (test/prod)
detect_environment() {
  LOCAL_IP=$(hostname -I 2>/dev/null | awk '{print $1}')

  # Check by IP first (most reliable)
  if [ "$LOCAL_IP" = "109.69.56.185" ]; then
    echo "PRODUCTION"
  elif [ "$LOCAL_IP" = "185.58.204.196" ]; then
    echo "TEST"
  # Fallback: check by directory structure
  elif [ -d "/root/VPNHubBot" ] && [ ! -d "/root/github_repos" ]; then
    echo "PRODUCTION"
  elif [ -d "/root/github_repos/VPN_BOT" ]; then
    echo "TEST"
  else
    echo "UNKNOWN"
  fi
}

ENVIRONMENT=$(detect_environment)

# Inject context about the project
if [ "$ENVIRONMENT" = "PRODUCTION" ]; then
cat << 'EOF'

# 🔴 PRODUCTION SERVER - VPN Bot

## ⚠️ ВНИМАНИЕ: ЭТО ПРОДАКШН!
Все изменения влияют на реальных пользователей.

## 📍 Текущий проект
**VPN Bot** - Telegram бот для управления VPN подписками
- **Продакшн директория**: /root/VPNHubBot
- **База данных**: VPNHubBotDB (marakoris)

EOF
else
cat << 'EOF'

# 🟢 TEST SERVER - VPN Bot Project

## ⚠️ ВАЖНО: СМОТРИ ДОКУМЕНТАЦИЮ ПЕРВЫМ ДЕЛОМ!
При работе с проектом **СНАЧАЛА читай документацию**, а не гадай:
- **@/root/claude-docs/projects/vpn-bot/VPN-SUPPORT-CONTEXT.md** — поддержка клиентов, серверы, credentials
- **@/root/github_repos/VPN_BOT/.claude/CLAUDE.md** — продакшн доступы, архитектура

## 📍 Текущий проект
**VPN Bot** - Telegram бот для управления VPN подписками
- **Тест репозиторий**: /root/github_repos/VPN_BOT
- **Продакшн (reference)**: /root/production_server/VPNHubBot
- **Документация**: /root/claude-docs/

EOF
fi

echo "## 📊 Статус проекта"

# Show current branch and recent activity
if [ "$ENVIRONMENT" = "PRODUCTION" ]; then
  cd /root/VPNHubBot 2>/dev/null
else
  cd /root/github_repos/VPN_BOT 2>/dev/null
fi

if [ -d ".git" ]; then
  CURRENT_BRANCH=$(git branch --show-current 2>/dev/null || echo 'unknown')
  echo "- **Git ветка**: $CURRENT_BRANCH"
  echo ""
  echo "### Последние коммиты:"
  git log --oneline -3 2>/dev/null | sed 's/^/  - /'

  echo ""
  echo "### 🔄 Синхронизация с GitHub:"

  # Fetch latest from origin (silent)
  git fetch origin 2>/dev/null

  # Check for uncommitted changes
  UNCOMMITTED=$(git status --porcelain 2>/dev/null | wc -l)

  # Check ahead/behind status
  AHEAD=$(git rev-list --count origin/main..HEAD 2>/dev/null)
  BEHIND=$(git rev-list --count HEAD..origin/main 2>/dev/null)
  AHEAD=${AHEAD:-0}
  BEHIND=${BEHIND:-0}

  if [ "$UNCOMMITTED" -gt 0 ]; then
    echo "  - ⚠️ **Незакоммиченные изменения: $UNCOMMITTED файлов**"
    echo "    → Не забудь: \`git add . && git commit && git push\`"
  fi

  if [ "$BEHIND" -gt 0 ]; then
    echo "  - ⚠️ **Отстаёшь от origin на $BEHIND коммитов**"
    echo "    → Сначала выполни: \`git pull origin main\`"
  fi

  if [ "$AHEAD" -gt 0 ]; then
    echo "  - 📤 **Впереди origin на $AHEAD коммитов (не запушено)**"
    echo "    → Не забудь: \`git push origin main\`"
  fi

  if [ "$UNCOMMITTED" -eq 0 ] && [ "$BEHIND" -eq 0 ] && [ "$AHEAD" -eq 0 ]; then
    echo "  - ✅ **Синхронизировано с GitHub**"
  fi
fi

echo ""
echo "### Статус Docker контейнеров:"
docker ps --format "  - {{.Names}}: {{.Status}}" | grep -E "(vpn|postgres|subscription)" 2>/dev/null || echo "  - (не удалось получить статус)"

# Show the latest session from documentation (only on test server)
if [ "$ENVIRONMENT" = "TEST" ]; then
  echo ""
  echo "## 📝 Последняя сессия"

  LATEST_SESSION=$(ls -t /root/claude-docs/sessions/*.md 2>/dev/null | head -1)
  if [ -n "$LATEST_SESSION" ]; then
    SESSION_NAME=$(basename "$LATEST_SESSION" .md)
    echo "**Файл**: $SESSION_NAME"
    echo ""

    # Extract first few lines after the title
    echo "**Краткое содержание:**"
    grep -A 3 "^**Тема:**\|^**Проблема:**\|^**Статус:**" "$LATEST_SESSION" 2>/dev/null | head -10 | sed 's/^/  /'
  fi
fi

# Show quick access commands based on environment
echo ""
echo "## ⚡ Быстрые команды"
echo ""
echo "### Перезапуск бота (3-5 секунд)"
echo '```bash'
echo 'docker restart $DOCKER_CONTAINER'
echo '```'
echo ""
echo "### Проверка логов"
echo '```bash'
echo 'docker logs --tail=50 $DOCKER_CONTAINER'
echo 'docker logs -f $DOCKER_CONTAINER  # real-time'
echo '```'
echo ""
echo "### Git операции"
echo '```bash'
echo 'cd $PROJECT_DIR'
echo 'git status'
echo 'git log --oneline -5'
echo '```'
echo ""
echo "### База данных"
echo '```bash'
echo 'docker exec $DOCKER_DB_CONTAINER psql -U $DB_USER -d $DB_NAME -c "SELECT * FROM users LIMIT 5;"'
echo '```'

if [ "$ENVIRONMENT" = "TEST" ]; then
cat << 'EOF'

## 📚 Доступная документация

Используйте `@` для быстрого доступа к файлам:
- **@/root/claude-docs/projects/vpn-bot/VPN-SUPPORT-CONTEXT.md** - 🆘 Поддержка клиентов (приложения, серверы, диагностика)
- **@/root/claude-docs/QUICK_START.md** - Быстрый старт
- **@/root/claude-docs/STATUS.md** - Полный статус проекта
- **@/root/claude-docs/sessions/** - История всех сессий
- **@/root/claude-docs/knowledge/** - База знаний

## 🔐 Зашифрованные пароли (SOPS + age)

Все credentials хранятся в зашифрованных файлах:
- `projects/infrastructure/server-connections.enc.md` — SSH доступы (MikroTik, Proxmox, Ubuntu)
- `projects/vpn-servers/vpn-servers-credentials.enc.md` — Доступы к VPN серверам

**Расшифровка:**
\`\`\`bash
cd /root/claude-docs && sops -d projects/infrastructure/server-connections.enc.md
\`\`\`

## 🔧 Полезные slash команды
- **/restore** - Восстановить контекст вручную (показать последние сессии)
- **/limits** - Проверить использование API и лимиты
- **/checkpoint** - Просмотр checkpoint'ов
- **/cost** - Точная статистика токенов (встроенная команда)

## 💰 Мониторинг лимитов
- Проверить использование: `/cost` или `/limits`
- Консоль: https://console.anthropic.com/settings/usage

---

✅ **Контекст загружен!** Готов продолжить работу над проектом.

EOF
else
cat << 'EOF'

## ⚠️ Продакшн команды

### Подключение к тестовому серверу (для разработки)
```bash
sshpass -f /root/.ssh/.test_password ssh -o StrictHostKeyChecking=no root@185.58.204.196
```

---

🔴 **PRODUCTION MODE** - Будьте осторожны с изменениями!

EOF
fi

exit 0
