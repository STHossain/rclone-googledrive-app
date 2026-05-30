#!/bin/bash

# ─── rclone-sync.sh ───────────────────────────────────
# Push/Pull/Bisync for all tracked Google Drive folders
# ──────────────────────────────────────────────────────

REMOTE="gdrive2"
LOCAL_BASE="$HOME/GoogleDrive"
CONFIG_FILE="$HOME/.rclone-folders"
LOG_FILE="/tmp/rclone-bisync.log"

# Check config file exists
if [ ! -f "$CONFIG_FILE" ] || [ ! -s "$CONFIG_FILE" ]; then
  echo "No folders tracked yet."
  echo "Add a folder with: ~/rclone-add.sh \"Folder Name\""
  exit 1
fi

# Load folders from config
mapfile -t ENTRIES < "$CONFIG_FILE"

echo "================================"
echo " Rclone Sync"
echo "================================"
echo "Tracked folders:"
for i in "${!ENTRIES[@]}"; do
  IFS='|' read -r type name <<< "${ENTRIES[$i]}"
  echo "  $((i+1))) $name [$type]"
done
echo "  A) All folders"
echo "================================"
read -p "Choose folder [1-${#ENTRIES[@]} or A]: " folder_choice

echo ""
echo "Sync options:"
echo "  1) Pull  (Drive → Local)"
echo "  2) Push  (Local → Drive)"
echo "  3) Bisync (Two-way)"
echo "================================"
read -p "Choose action [1/2/3]: " action

# Function to sync one folder
sync_folder() {
  local type="$1"
  local name="$2"
  local action="$3"
  local local_folder="$LOCAL_BASE/$name"

  if [[ "$type" == "shared" ]]; then
    SHARED_FLAG="--drive-shared-with-me"
  else
    SHARED_FLAG=""
  fi

  echo ""
  echo "[$(date)] ── $name ──"

  case $action in
    1)
      echo "Pulling from Drive..."
      rclone copy "$REMOTE:$name" "$local_folder" \
        $SHARED_FLAG \
        --log-file "$LOG_FILE" \
        --log-level INFO \
        --verbose \
        --progress
      echo "[$(date)] Pull complete!"
      ;;
    2)
      echo "Pushing to Drive..."
      rclone copy "$local_folder" "$REMOTE:$name" \
        $SHARED_FLAG \
        --log-file "$LOG_FILE" \
        --log-level INFO \
        --verbose \
        --progress
      echo "[$(date)] Push complete!"
      ;;
    3)
      echo "Running bisync..."
      rclone bisync "$REMOTE:$name" "$local_folder" \
        $SHARED_FLAG \
        --log-file "$LOG_FILE" \
        --log-level INFO \
        --verbose
      echo "[$(date)] Bisync complete!"
      ;;
    *)
      echo "Invalid action."
      ;;
  esac
}

# Run for selected folder(s)
if [[ "$folder_choice" == "A" || "$folder_choice" == "a" ]]; then
  for entry in "${ENTRIES[@]}"; do
    IFS='|' read -r type name <<< "$entry"
    sync_folder "$type" "$name" "$action"
  done
else
  INDEX=$((folder_choice - 1))
  if [ -z "${ENTRIES[$INDEX]}" ]; then
    echo "Invalid choice."
    exit 1
  fi
  IFS='|' read -r type name <<< "${ENTRIES[$INDEX]}"
  sync_folder "$type" "$name" "$action"
fi

echo ""
echo "✅ All done! Log: $LOG_FILE"
