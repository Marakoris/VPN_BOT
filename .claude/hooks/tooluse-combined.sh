#!/bin/bash

# Combined ToolUse Hook
# Вызывает оба hook'а: checkpoint и usage reminder

# 1. Create checkpoint (every 3 edits)
$CLAUDE_PROJECT_DIR/.claude/hooks/create-checkpoint.sh

# 2. Show usage reminder with real data (after each tool use)
$CLAUDE_PROJECT_DIR/.claude/hooks/usage-reminder-v2.sh

exit 0
