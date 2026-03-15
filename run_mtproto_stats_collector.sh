#!/bin/bash
# MTProto Proxy Stats Collector Runner
# Runs the collector in a loop with configurable interval.

CHECK_INTERVAL=${MTPROTO_COLLECT_INTERVAL:-300}

echo "Starting MTProto Proxy Stats Collector"
echo "Collect interval: ${CHECK_INTERVAL} seconds ($(($CHECK_INTERVAL / 60)) minutes)"
echo "Server 1: ${MTPROTO_SSH_HOST:-not configured} (Frankfurt, Docker)"
echo "Server 2: ${MTPROTO_BYPASS1_HOST:-not configured} (Bypass-1, systemd)"
echo "============================================"

while true; do
    echo ""
    echo "[$(date)] Running MTProto stats collection..."

    python3 /app/mtproto_stats_collector.py

    EXIT_CODE=$?

    if [ $EXIT_CODE -eq 0 ]; then
        echo "[$(date)] Collection completed successfully"
    else
        echo "[$(date)] Collection failed with exit code $EXIT_CODE"
    fi

    echo "[$(date)] Sleeping for ${CHECK_INTERVAL} seconds..."
    sleep $CHECK_INTERVAL
done
