#!/bin/bash

# Parse Transcript for Real Cost Data
# Reads the Claude Code transcript JSONL file and extracts real token usage

# Hook input is passed via stdin as JSON
# It contains: transcript_path, tool_name, etc.

# Read the JSON input (if provided)
if [ -t 0 ]; then
    # Running manually (no stdin), use default path if exists
    TRANSCRIPT_PATH="${CLAUDE_SESSION_DIR:-$HOME/.claude}/transcript.jsonl"
else
    # Running from hook, parse JSON input
    INPUT=$(cat)
    TRANSCRIPT_PATH=$(echo "$INPUT" | jq -r '.transcript_path // empty' 2>/dev/null)
fi

# Fallback to common locations
if [ -z "$TRANSCRIPT_PATH" ] || [ ! -f "$TRANSCRIPT_PATH" ]; then
    # Try to find the latest session file
    LATEST_SESSION=$(ls -t "$HOME/.claude/projects/-root/"*.jsonl 2>/dev/null | grep -v "agent-" | head -1)

    if [ -n "$LATEST_SESSION" ] && [ -f "$LATEST_SESSION" ]; then
        TRANSCRIPT_PATH="$LATEST_SESSION"
    else
        # Try common locations
        for path in \
            "$HOME/.claude/transcript.jsonl" \
            "$HOME/.config/claude/transcript.jsonl" \
            "/tmp/claude-transcript.jsonl"
        do
            if [ -f "$path" ]; then
                TRANSCRIPT_PATH="$path"
                break
            fi
        done
    fi
fi

# If still no transcript, exit silently
if [ -z "$TRANSCRIPT_PATH" ] || [ ! -f "$TRANSCRIPT_PATH" ]; then
    exit 0
fi

# Parse transcript for API usage data
# Look for lines with "usage" field (API responses)
TOTAL_INPUT=0
TOTAL_OUTPUT=0
TOTAL_CACHE_READ=0
TOTAL_CACHE_CREATION=0
REQUEST_COUNT=0

# Process each line of JSONL
while IFS= read -r line; do
    # Check if line contains usage data
    if echo "$line" | grep -q '"usage"'; then
        # Extract token counts using jq (check both .usage and .message.usage)
        INPUT_TOKENS=$(echo "$line" | jq -r '(.message.usage.input_tokens // .usage.input_tokens // 0)' 2>/dev/null)
        OUTPUT_TOKENS=$(echo "$line" | jq -r '(.message.usage.output_tokens // .usage.output_tokens // 0)' 2>/dev/null)
        CACHE_READ=$(echo "$line" | jq -r '(.message.usage.cache_read_input_tokens // .usage.cache_read_input_tokens // 0)' 2>/dev/null)
        CACHE_CREATION=$(echo "$line" | jq -r '(.message.usage.cache_creation_input_tokens // .usage.cache_creation_input_tokens // 0)' 2>/dev/null)

        # Add to totals
        TOTAL_INPUT=$((TOTAL_INPUT + INPUT_TOKENS))
        TOTAL_OUTPUT=$((TOTAL_OUTPUT + OUTPUT_TOKENS))
        TOTAL_CACHE_READ=$((TOTAL_CACHE_READ + CACHE_READ))
        TOTAL_CACHE_CREATION=$((TOTAL_CACHE_CREATION + CACHE_CREATION))
        REQUEST_COUNT=$((REQUEST_COUNT + 1))
    fi
done < "$TRANSCRIPT_PATH"

# Calculate costs (approximate, based on Claude Sonnet 4.5 pricing)
# Input: $3 per million tokens
# Output: $15 per million tokens
# Cache read: $0.30 per million tokens
# Cache creation: $3.75 per million tokens

COST_INPUT=$(echo "scale=6; $TOTAL_INPUT * 3 / 1000000" | bc 2>/dev/null || echo "0")
COST_OUTPUT=$(echo "scale=6; $TOTAL_OUTPUT * 15 / 1000000" | bc 2>/dev/null || echo "0")
COST_CACHE_READ=$(echo "scale=6; $TOTAL_CACHE_READ * 0.30 / 1000000" | bc 2>/dev/null || echo "0")
COST_CACHE_CREATION=$(echo "scale=6; $TOTAL_CACHE_CREATION * 3.75 / 1000000" | bc 2>/dev/null || echo "0")

TOTAL_COST=$(echo "scale=6; $COST_INPUT + $COST_OUTPUT + $COST_CACHE_READ + $COST_CACHE_CREATION" | bc 2>/dev/null || echo "0")

# Format cost to 2 decimal places
TOTAL_COST=$(printf "%.2f" "$TOTAL_COST" 2>/dev/null || echo "0.00")

# Export data for other scripts to use
echo "TRANSCRIPT_REQUESTS=$REQUEST_COUNT"
echo "TRANSCRIPT_INPUT_TOKENS=$TOTAL_INPUT"
echo "TRANSCRIPT_OUTPUT_TOKENS=$TOTAL_OUTPUT"
echo "TRANSCRIPT_CACHE_READ=$TOTAL_CACHE_READ"
echo "TRANSCRIPT_CACHE_CREATION=$TOTAL_CACHE_CREATION"
echo "TRANSCRIPT_TOTAL_COST=$TOTAL_COST"

exit 0
