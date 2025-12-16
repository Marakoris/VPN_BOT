#!/bin/bash

# SessionEnd Hook - Финальное сохранение при завершении сессии

DOCS_DIR="/root/claude-docs"
CHECKPOINT_DIR="$DOCS_DIR/checkpoints"
CURRENT_TASK_FILE="$DOCS_DIR/.current-task"
TODAY=$(date +%Y-%m-%d)
TIMESTAMP=$(date +%H:%M)
WORK_LOG="$CHECKPOINT_DIR/$TODAY-work-log.md"

# Ensure directories exist
mkdir -p "$CHECKPOINT_DIR"

# Get current task
if [ -f "$CURRENT_TASK_FILE" ]; then
    CURRENT_TASK=$(cat "$CURRENT_TASK_FILE")
else
    CURRENT_TASK="Session work"
fi

# Create work log if doesn't exist
if [ ! -f "$WORK_LOG" ]; then
    cat > "$WORK_LOG" << EOF
# Work Log - $TODAY

---

EOF
fi

# Get git status
cd /root/github_repos/VPN_BOT 2>/dev/null
GIT_STATUS=$(git status --short 2>/dev/null | head -10 | sed 's/^/- /')
GIT_BRANCH=$(git branch --show-current 2>/dev/null || echo 'unknown')
LAST_COMMITS=$(git log --oneline -3 2>/dev/null | sed 's/^/- /')

# Create session summary
SESSION_SUMMARY="
## 📝 Session End - $TIMESTAMP

### Task: $CURRENT_TASK

**Git Status:**
$GIT_STATUS

**Recent Commits:**
$LAST_COMMITS

**Branch:** $GIT_BRANCH

**Session ended:** $TODAY $TIMESTAMP

---
"

# Append to work log
echo "$SESSION_SUMMARY" >> "$WORK_LOG"

# Output to Claude (informational)
cat << EOF

# 💾 Session Saved

Your work has been automatically saved to:
- **Work Log**: $WORK_LOG
- **Task**: $CURRENT_TASK

To restore in next session:
- SessionStart hook will load automatically
- Or use: /restore command

EOF

exit 0
