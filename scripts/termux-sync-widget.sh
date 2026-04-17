#!/data/data/com.termux/files/usr/bin/bash
# LADA OAuth Sync Widget
# Syncs LADA tokens to LADA on l36 server
# Place in ~/.shortcuts/ on phone for Termux:Widget

termux-toast "Syncing LADA auth..."

# Run sync on l36 server
SERVER="${LADA_SERVER:-l36}"
RESULT=$(ssh "$SERVER" '/home/admin/lada/scripts/sync-lada-code-auth.sh' 2>&1)
EXIT_CODE=$?

if [ $EXIT_CODE -eq 0 ]; then
    # Extract expiry time from output
    EXPIRY=$(echo "$RESULT" | grep "Token expires:" | cut -d: -f2-)

    termux-vibrate -d 100
    termux-toast "LADA synced! Expires:${EXPIRY}"

    # Optional: restart lada service
    ssh "$SERVER" 'systemctl --user restart lada' 2>/dev/null
else
    termux-vibrate -d 300
    termux-toast "Sync failed: ${RESULT}"
fi

