#!/bin/bash
"""
Subscription Expiry Checker Runner

This script runs the subscription expiry checker in a loop with configurable interval.
Default: every 5 minutes
"""

# Check interval in seconds (default: 5 minutes = 300 seconds)
CHECK_INTERVAL=${SUBSCRIPTION_CHECK_INTERVAL:-300}

echo "Starting Subscription Expiry Checker"
echo "Check interval: ${CHECK_INTERVAL} seconds ($(($CHECK_INTERVAL / 60)) minutes)"
echo "============================================"

while true; do
    echo ""
    echo "[$(date)] Running subscription expiry check..."

    # Run the checker script
    python3 /app/subscription_expiry_checker.py

    EXIT_CODE=$?

    if [ $EXIT_CODE -eq 0 ]; then
        echo "[$(date)] Check completed successfully"
    else
        echo "[$(date)] Check failed with exit code $EXIT_CODE"
    fi

    echo "[$(date)] Sleeping for ${CHECK_INTERVAL} seconds..."
    sleep $CHECK_INTERVAL
done
