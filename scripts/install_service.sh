#!/bin/bash
# Ставит сервис в автозапуск через launchd: он поднимется при входе в систему
# и переживёт перезагрузку. Снять — scripts/uninstall_service.sh
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LABEL="com.local.workflow"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
PYTHON="$PROJECT_DIR/.venv/bin/python"

if [ ! -x "$PYTHON" ]; then
  echo "Не найден $PYTHON. Сначала создай окружение: python3 -m venv .venv" >&2
  exit 1
fi

mkdir -p "$HOME/Library/LaunchAgents" "$PROJECT_DIR/data/logs"

cat > "$PLIST" <<PLISTEOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>$LABEL</string>
    <key>ProgramArguments</key>
    <array>
        <string>$PYTHON</string>
        <string>$PROJECT_DIR/main.py</string>
    </array>
    <key>WorkingDirectory</key><string>$PROJECT_DIR</string>
    <key>RunAtLoad</key><true/>
    <key>KeepAlive</key>
    <dict><key>SuccessfulExit</key><false/></dict>
    <key>StandardOutPath</key><string>$PROJECT_DIR/data/logs/service.out.log</string>
    <key>StandardErrorPath</key><string>$PROJECT_DIR/data/logs/service.err.log</string>
    <key>ProcessType</key><string>Background</string>
    <key>EnvironmentVariables</key>
    <dict><key>PATH</key><string>$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string></dict>
</dict>
</plist>
PLISTEOF

launchctl unload "$PLIST" 2>/dev/null || true
launchctl load "$PLIST"
echo "Сервис установлен: $LABEL"
echo "Панель: http://127.0.0.1:8765"
echo "Логи:   $PROJECT_DIR/data/logs/"
