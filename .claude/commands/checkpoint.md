---
description: View checkpoints and work history
---

# 🔍 View Checkpoints

## Последний checkpoint

!`cat /root/claude-docs/checkpoints/latest-checkpoint.md 2>/dev/null || echo "❌ Checkpoint'ов пока нет"`

## Сегодняшний work log

!`if [ -f /root/claude-docs/checkpoints/$(date +%Y-%m-%d)-work-log.md ]; then cat /root/claude-docs/checkpoints/$(date +%Y-%m-%d)-work-log.md; else echo "❌ Сегодня checkpoint'ы ещё не создавались"; fi`

## Все checkpoints за последние 7 дней

!`ls -lht /root/claude-docs/checkpoints/*-work-log.md 2>/dev/null | head -7 | awk '{print $NF}' | xargs -I {} sh -c 'echo "---"; echo "📅 $(basename {} .md)"; head -5 {}'`

## Статистика

- **Счётчик изменений**: !`cat /root/claude-docs/.checkpoint-counter 2>/dev/null || echo "0"`/3
- **Текущая задача**: !`cat /root/claude-docs/.current-task 2>/dev/null || echo "не установлена"`
- **Следующий checkpoint**: Через !`echo $((3 - $(cat /root/claude-docs/.checkpoint-counter 2>/dev/null || echo 0)))` изменений

---

**Справка:**
- Checkpoint создаётся каждые 3 изменения кода (Edit/Write)
- Автоматически сохраняется git статус и список изменённых файлов
- Используйте `/task` для установки текущей задачи
