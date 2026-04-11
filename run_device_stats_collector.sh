#!/bin/bash
# Device Stats Collector Runner

CHECK_INTERVAL=${DEVICE_COLLECT_INTERVAL:-600}

echo "Starting Device Stats Collector"
echo "Collect interval: ${CHECK_INTERVAL}s ($(($CHECK_INTERVAL / 60)) min)"
echo "Servers: ${DEVICE_SERVERS:-not configured}"
echo "============================================"

while true; do
    echo ""
    echo "[$(date)] Running device stats collection..."
    python3 /app/device_stats_collector.py
    EXIT_CODE=$?
    if [ $EXIT_CODE -eq 0 ]; then
        echo "[$(date)] Done"
    else
        echo "[$(date)] Failed (exit $EXIT_CODE)"
    fi
    echo "[$(date)] Sleeping ${CHECK_INTERVAL}s..."
    sleep $CHECK_INTERVAL
done
