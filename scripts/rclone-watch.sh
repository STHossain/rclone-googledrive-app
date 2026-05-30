#!/bin/bash

# ─── rclone-watch.sh ──────────────────────────────────
# Watches ~/GoogleDrive for new folders
# Auto pushes to Google Drive + enables bisync
# ──────────────────────────────────────────────────────

WATCH_DIR="$HOME/GoogleDrive"
REMOTE="gdrive2"
CONFIG_FILE="$HOME/.rclone-folders"
LOG_FILE="/tmp/rclone-watch.log"

echo "[$(date)] Watching $WATCH_DIR for new folders..."
echo "[$(date)] Press Ctrl+C to stop."

inotifywait -m -e create --format '%f' "$WATCH_DIR" | while read FOLDER_NAME; do

  FULL_PATH="$WATCH_DIR/$FOLDER_NAME"

  # Only process directories (not files)
  if [ ! -d "$FULL_PATH" ]; then
    continue
  fi

  echo "[$(date)] New folder detected: $FOLDER_NAME"

  # Skip if already tracked
  if grep -qF "$FOLDER_NAME" "$CONFIG_FILE" 2>/dev/null; then
    echo "[$(date)] Already tracked, skipping: $FOLDER_NAME"
    continue
  fi

  # Notify user on desktop
  notify-send "Rclone Watcher" "New folder detected: '$FOLDER_NAME' — pushing to Drive..." 2>/dev/null

  # Push local folder to Google Drive
  echo "[$(date)] Pushing '$FOLDER_NAME' to Google Drive..."
  rclone copy "$FULL_PATH" "$REMOTE:$FOLDER_NAME" \
    --log-file "$LOG_FILE" \
    --log-level INFO \
    --verbose

  if [ $? -eq 0 ]; then

    # Run initial bisync to establish baseline
    echo "[$(date)] Setting up bisync for '$FOLDER_NAME'..."
    rclone bisync "$REMOTE:$FOLDER_NAME" "$FULL_PATH" \
      --resync \
      --log-file "$LOG_FILE" \
      --log-level INFO \
      --verbose

    if [ $? -eq 0 ]; then
      # Add to tracking list as own folder
      echo "own|$FOLDER_NAME" >> "$CONFIG_FILE"
      echo "[$(date)] '$FOLDER_NAME' is now tracked in $CONFIG_FILE"

      # Success notification
      notify-send "Rclone Watcher" "✅ '$FOLDER_NAME' synced and bisync enabled!" 2>/dev/null
      echo "[$(date)] Done! '$FOLDER_NAME' is fully set up."
    else
      echo "[$(date)] Bisync setup failed for: $FOLDER_NAME"
      notify-send "Rclone Watcher" "⚠️ '$FOLDER_NAME' pushed but bisync failed. Run rclone-add.sh manually." 2>/dev/null
    fi

  else
    echo "[$(date)] Push failed for: $FOLDER_NAME"
    notify-send "Rclone Watcher" "❌ Failed to push '$FOLDER_NAME' to Drive." 2>/dev/null
    echo "[$(date)] Check log: $LOG_FILE"
  fi

done
