#!/bin/bash

# Auto-Checkpoint Creation Script
# Вызывается при каждом изменении кода (Edit/Write)

DOCS_DIR="/root/claude-docs"
CHECKPOINT_DIR="$DOCS_DIR/checkpoints"
COUNTER_FILE="$DOCS_DIR/.checkpoint-counter"
CURRENT_TASK_FILE="$DOCS_DIR/.current-task"
TODAY=$(date +%Y-%m-%d)
WORK_LOG="$CHECKPOINT_DIR/$TODAY-work-log.md"
LATEST_CHECKPOINT="$CHECKPOINT_DIR/latest-checkpoint.md"

# Ensure directories exist
mkdir -p "$CHECKPOINT_DIR"

# Initialize counter if doesn't exist
if [ ! -f "$COUNTER_FILE" ]; then
    echo "0" > "$COUNTER_FILE"
fi

# Read current counter
COUNTER=$(cat "$COUNTER_FILE")

# Increment counter
COUNTER=$((COUNTER + 1))
echo "$COUNTER" > "$COUNTER_FILE"

# If counter reaches 3, create checkpoint
if [ "$COUNTER" -ge 3 ]; then
    TIMESTAMP=$(date +%H:%M)

    # Get current task from file or use default
    if [ -f "$CURRENT_TASK_FILE" ]; then
        CURRENT_TASK=$(cat "$CURRENT_TASK_FILE")
    else
        CURRENT_TASK="Working on VPN Bot"
    fi

    # Create work log if doesn't exist
    if [ ! -f "$WORK_LOG" ]; then
        cat > "$WORK_LOG" << EOF
# Work Log - $TODAY

Auto-generated checkpoints for tracking progress throughout the day.

---

EOF
    fi

    # Get recent git changes
    cd /root/github_repos/VPN_BOT 2>/dev/null
    RECENT_FILES=$(git status --short 2>/dev/null | head -5 | sed 's/^/- /')
    if [ -z "$RECENT_FILES" ]; then
        RECENT_FILES="- (no git changes detected)"
    fi

    # Create checkpoint entry
    CHECKPOINT_ENTRY="
## 🕐 Checkpoint $TIMESTAMP

### Задача: $CURRENT_TASK

**Изменения:**
$RECENT_FILES

**Статус:** In progress

**Git branch:** $(git branch --show-current 2>/dev/null || echo 'unknown')

---
"

    # Append to work log
    echo "$CHECKPOINT_ENTRY" >> "$WORK_LOG"

    # Update latest checkpoint
    cat > "$LATEST_CHECKPOINT" << EOF
# Latest Checkpoint - $TODAY $TIMESTAMP

## Current Task
$CURRENT_TASK

## Recent Changes
$RECENT_FILES

## Git Status
- Branch: $(git branch --show-current 2>/dev/null || echo 'unknown')
- Last commit: $(git log --oneline -1 2>/dev/null || echo 'no commits')

## Docker Status
$(docker ps --format "- {{.Names}}: {{.Status}}" | grep -E "(vpn_bot|postgres|subscription)" 2>/dev/null || echo "- (docker not available)")

---
**Auto-saved:** $TODAY $TIMESTAMP
EOF

    # Reset counter
    echo "0" > "$COUNTER_FILE"

    # Output notification (will be visible in Claude's context if hook allows output)
    echo "[Auto-Checkpoint] Saved checkpoint $TIMESTAMP to $WORK_LOG"
fi

# Exit successfully
exit 0
