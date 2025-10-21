#!/bin/bash

# Uninstall RSS Reader Background Fetch Service

set -e

PLIST_NAME="com.user.rss-reader"
PLIST_PATH="$HOME/Library/LaunchAgents/${PLIST_NAME}.plist"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Uninstalling RSS Reader background service..."

# Unload the service
if [ -f "$PLIST_PATH" ]; then
    launchctl unload "$PLIST_PATH" 2>/dev/null || true
    echo "✓ Service unloaded"
else
    echo "✓ Service not currently loaded"
fi

# Remove plist file
if [ -f "$PLIST_PATH" ]; then
    rm "$PLIST_PATH"
    echo "✓ Removed plist: $PLIST_PATH"
else
    echo "✓ Plist already removed"
fi

# Ask about logs
if [ -d "$SCRIPT_DIR/logs" ]; then
    echo ""
    read -p "Remove logs directory? [y/N] " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        rm -rf "$SCRIPT_DIR/logs"
        echo "✓ Removed logs directory"
    else
        echo "✓ Kept logs directory"
    fi
fi

echo ""
echo "✓ Background service uninstalled successfully!"
echo ""
