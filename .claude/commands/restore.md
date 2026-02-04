---
description: Restore session context and recent work
---

# 🔄 Восстановление контекста сессии

Показываю последние сессии и текущий статус проекта.

## 📝 Последние сессии

!`ls -lt /root/claude-docs/sessions/*.md 2>/dev/null | head -5 | while read -r line; do file=$(echo "$line" | awk '{print $NF}'); echo "---"; echo "### $(basename "$file" .md)"; head -20 "$file" | grep -E "^\*\*|^#" | head -8; done`

## 📊 Текущий статус проекта

### Git статус
!`cd /root/github_repos/VPN_BOT && echo "Branch: $(git branch --show-current)" && echo "" && echo "Recent commits:" && git log --oneline -5`

### Docker контейнеры
!`docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" | grep -E "NAME|vpn_bot|postgres|subscription"`

### Последняя активность
!`cd /root/github_repos/VPN_BOT && echo "Last modified files:" && git status --short | head -10`

## 📚 Быстрый доступ к документации

- **Быстрый старт**: @/root/claude-docs/QUICK_START.md
- **Полный статус**: @/root/claude-docs/STATUS.md
- **Структура проекта**: @/root/claude-docs/knowledge/vpn-bot-structure.md
- **Последняя сессия**: @!`ls -t /root/claude-docs/sessions/*.md 2>/dev/null | head -1`

## 💡 Полезные команды

```bash
# Перезапуск бота
docker restart vpn_bot-vpn_hub_bot-1

# Логи
docker logs -f vpn_bot-vpn_hub_bot-1

# База данных
docker exec postgres_db_container psql -U postgres -d vpn_hub

# Git
cd /root/github_repos/VPN_BOT && git status
```

---

✅ **Контекст восстановлен!** Готов продолжить работу.
