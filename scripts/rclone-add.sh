#!/bin/bash

# ─── rclone-add.sh ────────────────────────────────────
# Usage: ~/rclone-add.sh "Folder Name"
# Adds a new Google Drive folder to bisync tracking
# ──────────────────────────────────────────────────────

REMOTE="gdrive2"
LOCAL_BASE="$HOME/GoogleDrive"
CONFIG_FILE="$HOME/.rclone-folders"

# Check folder name provided
if [ -z "$1" ]; then
  echo "Usage: ~/rclone-add.sh \"Folder Name\""
  echo "Example: ~/rclone-add.sh \"Documents 2025\""
  exit 1
fi

FOLDER_NAME="$1"
LOCAL_FOLDER="$LOCAL_BASE/$FOLDER_NAME"

echo "================================"
echo " Rclone Add Folder"
echo "================================"
echo "Folder : $FOLDER_NAME"
echo "Local  : $LOCAL_FOLDER"
echo "================================"

# Ask if shared or own
read -p "Is this a 'Shared with me' folder? [y/n]: " is_shared

if [[ "$is_shared" == "y" || "$is_shared" == "Y" ]]; then
  SHARED_FLAG="--drive-shared-with-me"
  FOLDER_TYPE="shared"
else
  SHARED_FLAG=""
  FOLDER_TYPE="own"
fi

# Create local folder
mkdir -p "$LOCAL_FOLDER"
echo "[$(date)] Local folder created: $LOCAL_FOLDER"

# Run initial resync
echo "[$(date)] Running initial bisync..."
rclone bisync "$REMOTE:$FOLDER_NAME" "$LOCAL_FOLDER" \
  $SHARED_FLAG \
  --resync \
  --verbose \
  --log-level INFO

# Check if bisync succeeded
if [ $? -eq 0 ]; then
  echo "[$(date)] Bisync successful!"

  # Save to config file (avoid duplicates)
  if grep -qF "$FOLDER_NAME" "$CONFIG_FILE" 2>/dev/null; then
    echo "[$(date)] Folder already in tracking list — skipping."
  else
    echo "$FOLDER_TYPE|$FOLDER_NAME" >> "$CONFIG_FILE"
    echo "[$(date)] Folder added to tracking: $CONFIG_FILE"
  fi

  echo ""
  echo "✅ Done! '$FOLDER_NAME' is now tracked."
  echo "Run ~/rclone-sync.sh to sync anytime."
else
  echo "[$(date)] Bisync failed. Folder NOT added to tracking."
  echo "Check if folder name is correct: rclone lsd gdrive2: --drive-shared-with-me"
fi
