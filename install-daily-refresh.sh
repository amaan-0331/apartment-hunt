#!/bin/bash
# Run local-refresh.sh every day at 12:00 on this Mac (launchd).
# If the Mac is asleep at 12:00, it runs when the Mac wakes.
#   Install:   ./install-daily-refresh.sh
#   Remove:    ./install-daily-refresh.sh --uninstall
#   Log:       ~/Library/Logs/apartment-hunt.log
set -euo pipefail
LABEL=com.apartment-hunt.refresh
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"

launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
if [ "${1:-}" = "--uninstall" ]; then
  rm -f "$PLIST"; echo "Removed."; exit 0
fi

DIR="$(cd "$(dirname "$0")" && pwd)"
# launchd starts with a bare PATH, so keep the one python3/git are found on now.
mkdir -p "$HOME/Library/LaunchAgents" "$HOME/Library/Logs"
cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key>
  <array><string>/bin/bash</string><string>$DIR/local-refresh.sh</string></array>
  <key>EnvironmentVariables</key>
  <dict><key>PATH</key><string>$PATH</string></dict>
  <key>StartCalendarInterval</key>
  <dict><key>Hour</key><integer>12</integer><key>Minute</key><integer>0</integer></dict>
  <key>StandardOutPath</key><string>$HOME/Library/Logs/apartment-hunt.log</string>
  <key>StandardErrorPath</key><string>$HOME/Library/Logs/apartment-hunt.log</string>
</dict>
</plist>
EOF
launchctl bootstrap "gui/$(id -u)" "$PLIST"
echo "Installed: daily at 12:00. Run now with:  launchctl kickstart gui/$(id -u)/$LABEL"
