#!/bin/bash

# Combined ToolUse Hook
# Вызывает оба hook'а: checkpoint и usage reminder

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# 1. Create checkpoint (every 3 edits)
"$SCRIPT_DIR/create-checkpoint.sh"

# 2. Show usage reminder with real data (after each tool use)
"$SCRIPT_DIR/usage-reminder-v2.sh"

exit 0
