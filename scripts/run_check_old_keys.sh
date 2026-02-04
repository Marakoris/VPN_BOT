#!/bin/bash
# Wrapper для check_old_keys.py
# Запускается по cron раз в неделю

cd /root/github_repos/VPN_BOT

# Загружаем переменные окружения
export $(grep -v '^#' .env | xargs)

# Для Docker окружения
export DB_HOST=localhost
export DB_PORT=5432

# Запускаем проверку
python3 scripts/check_old_keys.py >> /var/log/check_old_keys.log 2>&1
