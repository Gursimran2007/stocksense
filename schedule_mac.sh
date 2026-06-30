#!/bin/bash
# One-command scheduler for macOS (launchd). Runs the auto-sync every N hours.
# Usage:
#   ./schedule_mac.sh install      # start the schedule
#   ./schedule_mac.sh run-now      # trigger one sync immediately
#   ./schedule_mac.sh status       # is it loaded?
#   ./schedule_mac.sh uninstall    # stop the schedule
set -euo pipefail

LABEL="com.stocksense.sync"
PROJ_DIR="$(cd "$(dirname "$0")" && pwd)"
PY="/opt/anaconda3/bin/python3"                 # the working Python on this Mac
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
INTERVAL_HOURS="${INTERVAL_HOURS:-6}"           # override: INTERVAL_HOURS=1 ./schedule_mac.sh install
INTERVAL_SECONDS=$(( INTERVAL_HOURS * 3600 ))

write_plist() {
  mkdir -p "$HOME/Library/LaunchAgents" "$PROJ_DIR/inbox" "$PROJ_DIR/reports"
  cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
 "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>$PY</string>
    <string>$PROJ_DIR/automate.py</string>
  </array>
  <key>WorkingDirectory</key><string>$PROJ_DIR</string>
  <key>StartInterval</key><integer>$INTERVAL_SECONDS</integer>
  <key>RunAtLoad</key><true/>
  <key>StandardOutPath</key><string>$PROJ_DIR/launchd.out.log</string>
  <key>StandardErrorPath</key><string>$PROJ_DIR/launchd.err.log</string>
</dict>
</plist>
EOF
}

case "${1:-}" in
  install)
    write_plist
    launchctl unload "$PLIST" 2>/dev/null || true
    launchctl load "$PLIST"
    echo "✅ Scheduled: auto-sync every ${INTERVAL_HOURS}h."
    echo "   Drop billing exports into: $PROJ_DIR/inbox/"
    echo "   Reports appear in:         $PROJ_DIR/reports/buy_today.txt"
    ;;
  run-now)
    launchctl start "$LABEL" 2>/dev/null || "$PY" "$PROJ_DIR/automate.py"
    echo "▶️  Triggered a sync. See $PROJ_DIR/reports/buy_today.txt"
    ;;
  status)
    launchctl list | grep "$LABEL" || echo "Not loaded."
    ;;
  uninstall)
    launchctl unload "$PLIST" 2>/dev/null || true
    rm -f "$PLIST"
    echo "🛑 Schedule removed."
    ;;
  *)
    echo "Usage: $0 {install|run-now|status|uninstall}"
    echo "  INTERVAL_HOURS=1 $0 install   # change frequency"
    exit 1 ;;
esac
