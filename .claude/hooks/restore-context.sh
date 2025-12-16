#!/bin/bash

# SessionStart Hook - Автоматическое восстановление контекста
# Запускается при каждом старте Claude Code

# Persist environment variables for the session
if [ -n "$CLAUDE_ENV_FILE" ]; then
  echo "export PROJECT_DIR=/root/github_repos/VPN_BOT" >> "$CLAUDE_ENV_FILE"
  echo "export DOCS_DIR=/root/claude-docs" >> "$CLAUDE_ENV_FILE"
  echo "export DOCKER_CONTAINER=vpn_bot-vpn_hub_bot-1" >> "$CLAUDE_ENV_FILE"
  echo "export DOCKER_DB_CONTAINER=postgres_db_container" >> "$CLAUDE_ENV_FILE"
  echo "export PRODUCTION_DIR=/root/production_server/VPNHubBot" >> "$CLAUDE_ENV_FILE"
fi

# Inject context about the project
cat << 'EOF'

# 🚀 Сессия восстановлена - VPN Bot Project

## 📍 Текущий проект
**VPN Bot** - Telegram бот для управления VPN подписками
- **Тест репозиторий**: /root/github_repos/VPN_BOT
- **Продакшн (reference)**: /root/production_server/VPNHubBot
- **Документация**: /root/claude-docs/

## 📊 Статус проекта
EOF

# Show current branch and recent activity
cd /root/github_repos/VPN_BOT 2>/dev/null
if [ -d ".git" ]; then
  CURRENT_BRANCH=$(git branch --show-current 2>/dev/null || echo 'unknown')
  echo "- **Git ветка**: $CURRENT_BRANCH"
  echo ""
  echo "### Последние коммиты:"
  git log --oneline -3 2>/dev/null | sed 's/^/  - /'
fi

echo ""
echo "### Статус Docker контейнеров:"
docker ps --format "  - {{.Names}}: {{.Status}}" | grep -E "(vpn_bot|postgres|subscription)" 2>/dev/null || echo "  - (не удалось получить статус)"

# Show the latest session from documentation
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

# Show quick access commands
cat << 'EOF'

## ⚡ Быстрые команды

### Перезапуск бота (3-5 секунд)
```bash
docker restart $DOCKER_CONTAINER
```

### Проверка логов
```bash
docker logs --tail=50 $DOCKER_CONTAINER
docker logs -f $DOCKER_CONTAINER  # real-time
```

### Git операции
```bash
cd $PROJECT_DIR
git status
git log --oneline -5
```

### База данных
```bash
docker exec $DOCKER_DB_CONTAINER psql -U postgres -d vpn_hub -c "SELECT * FROM users LIMIT 5;"
```

## 📚 Доступная документация

Используйте `@` для быстрого доступа к файлам:
- **@/root/claude-docs/QUICK_START.md** - Быстрый старт
- **@/root/claude-docs/STATUS.md** - Полный статус проекта
- **@/root/claude-docs/sessions/** - История всех сессий
- **@/root/claude-docs/knowledge/** - База знаний

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

exit 0
