#!/bin/bash

# Install RSS Reader Background Fetch Service
# Uses launchd to run background analysis every 30 minutes

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLIST_NAME="com.user.rss-reader"
PLIST_PATH="$HOME/Library/LaunchAgents/${PLIST_NAME}.plist"

# Get absolute path to Python
PYTHON_PATH=$(which python3)
if [ -z "$PYTHON_PATH" ]; then
    echo "Error: python3 not found in PATH"
    exit 1
fi

# Check if virtual environment exists
if [ ! -d "$SCRIPT_DIR/venv" ]; then
    echo "Error: Virtual environment not found at $SCRIPT_DIR/venv"
    echo "Please run: python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt"
    exit 1
fi

VENV_PYTHON="$SCRIPT_DIR/venv/bin/python"

echo "Installing RSS Reader background service..."
echo "Script directory: $SCRIPT_DIR"
echo "Python: $VENV_PYTHON"

# Create LaunchAgents directory if it doesn't exist
mkdir -p "$HOME/Library/LaunchAgents"

# Create plist file
cat > "$PLIST_PATH" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>${PLIST_NAME}</string>

    <key>ProgramArguments</key>
    <array>
        <string>${VENV_PYTHON}</string>
        <string>${SCRIPT_DIR}/main.py</string>
        <string>background</string>
    </array>

    <key>WorkingDirectory</key>
    <string>${SCRIPT_DIR}</string>

    <key>StartInterval</key>
    <integer>1800</integer>

    <key>RunAtLoad</key>
    <true/>

    <key>StandardOutPath</key>
    <string>${SCRIPT_DIR}/logs/background.log</string>

    <key>StandardErrorPath</key>
    <string>${SCRIPT_DIR}/logs/background.error.log</string>

    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/usr/bin:/bin:/opt/homebrew/bin</string>
    </dict>
</dict>
</plist>
EOF

# Create logs directory
mkdir -p "$SCRIPT_DIR/logs"

# Load the service
launchctl unload "$PLIST_PATH" 2>/dev/null || true
launchctl load "$PLIST_PATH"

echo ""
echo "✓ Background service installed successfully!"
echo ""
echo "The service will:"
echo "  - Run every 30 minutes (1800 seconds)"
echo "  - Fetch new RSS articles"
echo "  - Analyze unanalyzed articles via Claude Code SDK (free!)"
echo "  - Log to: $SCRIPT_DIR/logs/"
echo ""
echo "Service name: ${PLIST_NAME}"
echo ""
echo "Commands:"
echo "  View status:  launchctl list | grep ${PLIST_NAME}"
echo "  View logs:    tail -f logs/background.log"
echo "  View errors:  tail -f logs/background.error.log"
echo "  Uninstall:    ./uninstall_scheduler.sh"
echo ""
