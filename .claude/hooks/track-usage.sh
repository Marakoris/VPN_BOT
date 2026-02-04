#!/bin/bash

# Usage Tracking Script
# Tracks approximate usage locally for warnings

USAGE_DIR="/root/claude-docs/.usage"
SESSION_FILE="$USAGE_DIR/current-session.txt"
TODAY=$(date +%Y-%m-%d)
DAILY_LOG="$USAGE_DIR/$TODAY-usage.log"

# Ensure directory exists
mkdir -p "$USAGE_DIR"

# Initialize session file if doesn't exist
if [ ! -f "$SESSION_FILE" ]; then
    echo "0" > "$SESSION_FILE"  # Request count
fi

# Read current count
REQUEST_COUNT=$(cat "$SESSION_FILE" 2>/dev/null || echo "0")
REQUEST_COUNT=$((REQUEST_COUNT + 1))

# Save updated count
echo "$REQUEST_COUNT" > "$SESSION_FILE"

# Log to daily file
TIMESTAMP=$(date +%H:%M:%S)
echo "$TIMESTAMP | Request #$REQUEST_COUNT" >> "$DAILY_LOG"

# Estimate tokens (very rough approximation)
# Average: ~2000 tokens per request
ESTIMATED_TOKENS=$((REQUEST_COUNT * 2000))

# Rate limit: 50 requests/min, 30000 input tokens/min
# If we've made more than 40 requests in this session, warn
if [ "$REQUEST_COUNT" -gt 40 ]; then
    echo ""
    echo "⚠️  Warning: You've made $REQUEST_COUNT requests this session"
    echo "   You may be approaching rate limits"
    echo "   Estimated tokens: ~$ESTIMATED_TOKENS"
    echo "   Check with: /cost"
    echo ""
fi

# Check if rate limit might be hit (basic time-based check)
# Get requests in last minute
ONE_MIN_AGO=$(date -d '1 minute ago' +%Y-%m-%d\ %H:%M:%S 2>/dev/null)
if [ $? -eq 0 ]; then
    RECENT_REQUESTS=$(grep "$(date +%Y-%m-%d)" "$DAILY_LOG" 2>/dev/null | tail -50 | wc -l)
    if [ "$RECENT_REQUESTS" -gt 45 ]; then
        echo ""
        echo "🚨 CRITICAL: $RECENT_REQUESTS requests in recent period"
        echo "   Rate limit (50 req/min) may be close!"
        echo "   Consider waiting 30-60 seconds"
        echo ""
    fi
fi

exit 0
