#!/bin/bash

# Usage Reminder v2 - With Real Transcript Data
# Показывает реальные данные об использовании из transcript

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

USAGE_DIR="/root/claude-docs/.usage"
SESSION_FILE="$USAGE_DIR/current-session.txt"
REMINDER_INTERVAL=10
WARNING_THRESHOLD=35

# Ensure directory exists
mkdir -p "$USAGE_DIR"

# Initialize session file
if [ ! -f "$SESSION_FILE" ]; then
    echo "0" > "$SESSION_FILE"
fi

# Increment counter
REQUEST_COUNT=$(cat "$SESSION_FILE" 2>/dev/null || echo "0")
REQUEST_COUNT=$((REQUEST_COUNT + 1))
echo "$REQUEST_COUNT" > "$SESSION_FILE"

# Try to get real data from transcript
REAL_DATA_AVAILABLE=false
if command -v jq >/dev/null 2>&1; then
    # Parse transcript for real cost data
    TRANSCRIPT_DATA=$("$SCRIPT_DIR/parse-transcript-cost.sh" 2>/dev/null)

    if [ $? -eq 0 ] && [ -n "$TRANSCRIPT_DATA" ]; then
        # Extract values
        eval "$TRANSCRIPT_DATA"

        if [ "$TRANSCRIPT_INPUT_TOKENS" -gt 0 ] || [ "$TRANSCRIPT_OUTPUT_TOKENS" -gt 0 ]; then
            REAL_DATA_AVAILABLE=true
            TOTAL_TOKENS=$((TRANSCRIPT_INPUT_TOKENS + TRANSCRIPT_OUTPUT_TOKENS))
            COST_USD=$TRANSCRIPT_TOTAL_COST
        fi
    fi
fi

# Fallback to estimates if real data not available
if [ "$REAL_DATA_AVAILABLE" = false ]; then
    TOTAL_TOKENS=$((REQUEST_COUNT * 2000))
    COST_USD=$(echo "scale=2; $REQUEST_COUNT * 0.01" | bc 2>/dev/null || echo "~0.01")
    DATA_SOURCE="оценка"
else
    DATA_SOURCE="реальные данные"
fi

# Format numbers with commas for readability
FORMATTED_TOKENS=$(printf "%'d" "$TOTAL_TOKENS" 2>/dev/null || echo "$TOTAL_TOKENS")

# Calculate percentage of rate limit
PERCENTAGE=$((REQUEST_COUNT * 100 / 50))

# Determine what to show based on count
if [ "$REQUEST_COUNT" -ge "$WARNING_THRESHOLD" ]; then
    # CRITICAL WARNING
    cat << EOF

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🚨 БЛИЗКО К ЛИМИТУ!
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 Запросов: $REQUEST_COUNT / 50 (лимит)
📈 Использование: $PERCENTAGE%
🎯 Токены: $FORMATTED_TOKENS ($DATA_SOURCE)
💰 Стоимость: \$$COST_USD
EOF

    if [ "$REAL_DATA_AVAILABLE" = true ]; then
        cat << EOF

📥 Input: $(printf "%'d" "$TRANSCRIPT_INPUT_TOKENS") токенов
📤 Output: $(printf "%'d" "$TRANSCRIPT_OUTPUT_TOKENS") токенов
⚡ Cache read: $(printf "%'d" "$TRANSCRIPT_CACHE_READ") токенов
EOF
    fi

    cat << EOF

⏸️  РЕКОМЕНДУЕТСЯ:
   1. Проверить: /cost
   2. Подождать 60 секунд
   3. Открыть: https://console.anthropic.com/settings/usage

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

EOF

elif [ $((REQUEST_COUNT % REMINDER_INTERVAL)) -eq 0 ]; then
    # Periodic detailed reminder
    cat << EOF

┌─────────────────────────────────────────────┐
│ 💰 Usage Check ($DATA_SOURCE)              │
├─────────────────────────────────────────────┤
│ Запросов: $REQUEST_COUNT                                 │
│ Токены: $FORMATTED_TOKENS                              │
│ Стоимость: \$$COST_USD                              │
EOF

    if [ "$REAL_DATA_AVAILABLE" = true ]; then
        cat << EOF
│ ┌─────────────────────────────────────────┐ │
│ │ 📥 Input: $(printf "%'d" "$TRANSCRIPT_INPUT_TOKENS") токенов            │ │
│ │ 📤 Output: $(printf "%'d" "$TRANSCRIPT_OUTPUT_TOKENS") токенов          │ │
│ │ ⚡ Cache: $(printf "%'d" "$TRANSCRIPT_CACHE_READ") токенов             │ │
│ └─────────────────────────────────────────┘ │
EOF
    fi

    cat << EOF
│                                             │
│ Точная проверка: /cost                      │
└─────────────────────────────────────────────┘

EOF

else
    # Compact reminder
    if [ "$REAL_DATA_AVAILABLE" = true ]; then
        echo ""
        echo "💡 $REQUEST_COUNT запросов | $FORMATTED_TOKENS токенов | \$$COST_USD | /cost"
        echo ""
    else
        echo ""
        echo "💡 $REQUEST_COUNT запросов | ~$FORMATTED_TOKENS токенов (оценка) | /cost"
        echo ""
    fi
fi

exit 0
