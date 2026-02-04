---
description: Manually save checkpoint with current progress
---

# 💾 Manual Checkpoint Save

Создать checkpoint вручную прямо сейчас (без ожидания 3 изменений).

## Сохраняю checkpoint...

!`bash $CLAUDE_PROJECT_DIR/.claude/hooks/create-checkpoint.sh && echo "0" > /root/claude-docs/.checkpoint-counter && echo "✅ Checkpoint сохранён!" || echo "❌ Ошибка при сохранении"`

## Последний checkpoint

!`cat /root/claude-docs/checkpoints/latest-checkpoint.md 2>/dev/null`

---

**Совет:** Используйте эту команду:
- Перед долгим перерывом
- После завершения важного этапа
- Перед экспериментальными изменениями
- Когда хотите зафиксировать текущее состояние
