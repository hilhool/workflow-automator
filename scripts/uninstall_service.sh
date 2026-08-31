#!/bin/bash
# Убирает сервис из автозапуска. Данные и настройки остаются на месте.
set -euo pipefail

LABEL="com.local.workflow"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"

launchctl unload "$PLIST" 2>/dev/null || true
rm -f "$PLIST"
echo "Сервис снят с автозапуска."
