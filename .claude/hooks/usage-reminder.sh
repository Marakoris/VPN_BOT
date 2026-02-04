#!/bin/bash

# Usage Reminder Hook
# Показывает напоминание о проверке usage после каждого ответа

USAGE_DIR="/root/claude-docs/.usage"
SESSION_FILE="$USAGE_DIR/current-session.txt"
REMINDER_INTERVAL=10  # Показывать детальное напоминание каждые 10 запросов
WARNING_THRESHOLD=35  # Предупреждение при 35+ запросах

# Ensure directory exists
mkdir -p "$USAGE_DIR"

# Initialize session file if doesn't exist
if [ ! -f "$SESSION_FILE" ]; then
    echo "0" > "$SESSION_FILE"
fi

# Read and increment counter
REQUEST_COUNT=$(cat "$SESSION_FILE" 2>/dev/null || echo "0")
REQUEST_COUNT=$((REQUEST_COUNT + 1))
echo "$REQUEST_COUNT" > "$SESSION_FILE"

# Calculate estimated tokens (rough approximation)
ESTIMATED_TOKENS=$((REQUEST_COUNT * 2000))
PERCENTAGE=$((REQUEST_COUNT * 100 / 50))  # 50 = rate limit per minute

# Determine what to show based on count
if [ "$REQUEST_COUNT" -ge "$WARNING_THRESHOLD" ]; then
    # CRITICAL WARNING - approaching limits
    cat << EOF

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🚨 БЛИЗКО К ЛИМИТУ!
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 Запросов в сессии: $REQUEST_COUNT / 50 (лимит)
📈 Использование: $PERCENTAGE%
⚠️  Примерно токенов: ~$ESTIMATED_TOKENS

⏸️  РЕКОМЕНДУЕТСЯ:
   1. Проверить точную статистику: /cost
   2. Подождать 60 секунд перед следующим запросом
   3. Открыть: https://console.anthropic.com/settings/usage

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

EOF

elif [ $((REQUEST_COUNT % REMINDER_INTERVAL)) -eq 0 ]; then
    # Periodic reminder every N requests
    cat << EOF

┌────────────────────────────────────────┐
│ 💰 Usage Check (каждые $REMINDER_INTERVAL запросов)  │
├────────────────────────────────────────┤
│ Запросов: $REQUEST_COUNT                         │
│ Примерно токенов: ~$ESTIMATED_TOKENS             │
│ Проверить точно: /cost            │
└────────────────────────────────────────┘

EOF

else
    # Compact reminder after each response
    echo ""
    echo "💡 Сессия: $REQUEST_COUNT запросов | ~$ESTIMATED_TOKENS токенов | Проверить: /cost"
    echo ""
fi

exit 0
