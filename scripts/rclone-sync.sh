#!/bin/bash

# ─── rclone-sync.sh ───────────────────────────────────
# Push/Pull/Bisync for all tracked Google Drive folders.
# Multi-account aware. Tracking file lines:
#     remote|type|name      (3-field, current)
#     type|name             (2-field, old — assumed remote=gdrive2)
# ──────────────────────────────────────────────────────

DEFAULT_REMOTE="gdrive2"
LOCAL_BASE="$HOME/GoogleDrive"
CONFIG_FILE="$HOME/.rclone-folders"
LOG_FILE="/tmp/rclone-bisync.log"

if [ ! -f "$CONFIG_FILE" ] || [ ! -s "$CONFIG_FILE" ]; then
  echo "No folders tracked yet."
  echo "Add a folder with: ~/rclone-add.sh \"Folder Name\""
  exit 1
fi

mapfile -t ENTRIES < "$CONFIG_FILE"

# Parse a tracking line into REMOTE / TYPE / NAME (handles both formats)
parse_entry() {
  local line="$1"
  local f1 f2 rest
  IFS='|' read -r f1 f2 rest <<< "$line"
  if [ -n "$rest" ]; then
    REMOTE="$f1"; TYPE="$f2"; NAME="$rest"
  else
    REMOTE="$DEFAULT_REMOTE"; TYPE="$f1"; NAME="$f2"
  fi
}

echo "================================"
echo " Rclone Sync"
echo "================================"
echo "Tracked folders:"
for i in "${!ENTRIES[@]}"; do
  parse_entry "${ENTRIES[$i]}"
  echo "  $((i+1))) $NAME  [$REMOTE · $TYPE]"
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

sync_folder() {
  local remote="$1"
  local type="$2"
  local name="$3"
  local action="$4"
  local local_folder="$LOCAL_BASE/$name"

  if [[ "$type" == "shared" ]]; then
    SHARED_FLAG="--drive-shared-with-me"
  else
    SHARED_FLAG=""
  fi

  echo ""
  echo "[$(date)] ── $name  [$remote] ──"

  case $action in
    1)
      echo "Pulling from Drive..."
      rclone copy "$remote:$name" "$local_folder" \
        $SHARED_FLAG --log-file "$LOG_FILE" --log-level INFO --verbose --progress
      echo "[$(date)] Pull complete!"
      ;;
    2)
      echo "Pushing to Drive..."
      rclone copy "$local_folder" "$remote:$name" \
        $SHARED_FLAG --log-file "$LOG_FILE" --log-level INFO --verbose --progress
      echo "[$(date)] Push complete!"
      ;;
    3)
      echo "Running bisync..."
      rclone bisync "$remote:$name" "$local_folder" \
        $SHARED_FLAG --log-file "$LOG_FILE" --log-level INFO --verbose
      echo "[$(date)] Bisync complete!"
      ;;
    *)
      echo "Invalid action."
      ;;
  esac
}

if [[ "$folder_choice" == "A" || "$folder_choice" == "a" ]]; then
  for entry in "${ENTRIES[@]}"; do
    parse_entry "$entry"
    sync_folder "$REMOTE" "$TYPE" "$NAME" "$action"
  done
else
  INDEX=$((folder_choice - 1))
  if [ -z "${ENTRIES[$INDEX]}" ]; then
    echo "Invalid choice."
    exit 1
  fi
  parse_entry "${ENTRIES[$INDEX]}"
  sync_folder "$REMOTE" "$TYPE" "$NAME" "$action"
fi

echo ""
echo "✅ All done! Log: $LOG_FILE"
