# Rclone + Google Drive on Manjaro — Complete Guide

A full, from-scratch setup for two-way Google Drive sync on Manjaro Linux, with helper scripts, an automatic folder watcher, and a simple GUI app.

---

## Table of Contents

1. [Objectives](#objectives)
2. [What is Rclone?](#what-is-rclone)
3. [Part 1 — Install Rclone & Dependencies](#part-1--install-rclone--dependencies)
4. [Part 2 — Configure Google Drive](#part-2--configure-google-drive)
5. [Part 3 — Reconnect an Expired Token](#part-3--reconnect-an-expired-token)
6. [Part 4 — Understanding "Shared with me" Folders](#part-4--understanding-shared-with-me-folders)
7. [Part 5 — How the System Works](#part-5--how-the-system-works)
8. [Part 6 — Install the Scripts](#part-6--install-the-scripts)
9. [Part 7 — The Folder Watcher Service](#part-7--the-folder-watcher-service)
10. [Part 8 — The GUI App](#part-8--the-gui-app)
11. [Part 9 — Daily Usage](#part-9--daily-usage)
12. [Part 10 — Push / Pull / Bisync Explained](#part-10--push--pull--bisync-explained)
13. [Part 11 — Security Notes](#part-11--security-notes)
14. [Part 12 — Troubleshooting](#part-12--troubleshooting)
15. [Quick Reference](#quick-reference)

---

## Objectives

This setup achieves four goals:

1. **Connect Google Drive** to your Manjaro machine using rclone (open source, secure OAuth).
2. **Add any existing Drive folder** (your own or "Shared with me") to local two-way sync with one command.
3. **Auto-detect new local folders** — create a folder inside `~/GoogleDrive/` and it is automatically pushed to Drive and bisync-enabled.
4. **Control sync manually** via a clean GUI (or scripts) — pull, push, or two-way sync any folder on demand, instead of forced background syncing.

A single tracking file (`~/.rclone-folders`) keeps every tool consistent.

---

## What is Rclone?

Rclone is a command-line program to manage files on cloud storage. It is:

- **Open source** — auditable, trusted by sysadmins and enterprises.
- **Direct** — files transfer straight between your machine and Google over TLS; nothing passes through rclone's servers.
- **Secure** — uses OAuth 2.0; your Google password is never stored, only a revocable access token.

In this guide the remote is named **`gdrive2`**. If yours has a different name, substitute it everywhere.

---

## Part 1 — Install Rclone & Dependencies

Install everything needed in one go:

```bash
sudo pacman -S rclone fuse3 inotify-tools tk
```

| Package | Why |
|---------|-----|
| `rclone` | the core sync tool |
| `fuse3` | needed for mounting drives |
| `inotify-tools` | lets the watcher detect new folders |
| `tk` | Tkinter — needed for the GUI app |

Verify rclone:

```bash
rclone version
```

Load the FUSE module (for mounting, if you use it):

```bash
sudo modprobe fuse
```

---

## Part 2 — Configure Google Drive

Start the interactive setup:

```bash
rclone config
```

Follow the prompts:

```
n) New remote                → n
name>                        → gdrive2
Storage>                     → drive          (type "drive")
client_id>                   → (leave blank, press Enter)
client_secret>               → (leave blank, press Enter)
scope>                       → 1              (Full access)
root_folder_id>              → (press Enter)
service_account_file>        → (press Enter)
Edit advanced config?        → n
Use web browser to authenticate? → y
```

A browser opens — **log in to Google and click Allow**.

```
Configure as Shared Drive (Team Drive)? → n
Is this OK?                              → y
Quit config                              → q
```

Test it:

```bash
rclone ls gdrive2:
```

If your files list, the connection works.

> **Tip — your own API keys (optional but better):** leaving `client_id` blank uses rclone's shared credentials, which Google occasionally rate-limits. For a private, dedicated connection, create OAuth credentials at <https://console.cloud.google.com> (enable the Google Drive API, make OAuth 2.0 credentials) and paste your own `client_id` / `client_secret` during config.

---

## Part 3 — Reconnect an Expired Token

If you see an error like `invalid_grant: maybe token expired`, refresh it:

```bash
rclone config reconnect gdrive2:
```

Answer the prompts:

```
Already have a token - refresh?           → y
Use web browser to authenticate?          → y
(browser opens — log in and Allow)
Configure as Shared Drive (Team Drive)?   → n
```

Then test again:

```bash
rclone ls gdrive2:
```

---

## Part 4 — Understanding "Shared with me" Folders

Folders in Google Drive's **"Shared with me"** section are **not** accessed by default. Any rclone command touching them needs the flag:

```
--drive-shared-with-me
```

List shared folders:

```bash
rclone lsd gdrive2: --drive-shared-with-me
```

List your own folders:

```bash
rclone lsd gdrive2:
```

The scripts in this guide track whether each folder is `shared` or `own` and apply the flag automatically.

> **Note:** Pushing changes *to* a shared folder only works if you have **edit permission** on it.

---

## Part 5 — How the System Works

Everything revolves around one tracking file, `~/.rclone-folders`, where each line is:

```
type|folder name
```

For example:

```
shared|My Shared Project
own|Documents 2025
```

Three scripts plus a GUI all read and write this single list:

```
                    ~/.rclone-folders   (single tracking list)
                  ▲          ▲          ▲          ▲
                  │          │          │          │
          rclone-add.sh  rclone-watch.sh  rclone-sync.sh  rclone-gui.py
          (existing       (new local      (manual CLI     (manual GUI
           Drive folder)   folder)         sync)           sync)
```

- **`rclone-add.sh`** — register an existing Drive folder.
- **`rclone-watch.sh`** — background watcher; auto-handles new local folders.
- **`rclone-sync.sh`** — terminal menu for pull/push/bisync.
- **`rclone-gui.py`** — the same controls in a window.

The local mirror lives at `~/GoogleDrive/<folder name>`.

---

## Part 6 — Install the Scripts

All scripts are in the `scripts/` folder of this bundle. Copy them to your home directory:

```bash
cp scripts/rclone-add.sh   ~/rclone-add.sh
cp scripts/rclone-watch.sh ~/rclone-watch.sh
cp scripts/rclone-sync.sh  ~/rclone-sync.sh
cp scripts/rclone-gui.py   ~/rclone-gui.py
```

Make the shell scripts and GUI executable:

```bash
chmod +x ~/rclone-add.sh ~/rclone-watch.sh ~/rclone-sync.sh ~/rclone-gui.py
```

Remove any old auto-sync cron job (we use the watcher + manual sync instead):

```bash
crontab -r
```

### Register an existing folder

```bash
~/rclone-add.sh "My Shared Project"
```

It asks whether the folder is shared, creates the local copy, runs the initial `--resync`, and adds it to tracking.

> If a folder was already synced before this system existed, you don't need to resync it — just add its line to the tracking file directly:
> ```bash
> echo "shared|My Shared Project" >> ~/.rclone-folders
> ```

---

## Part 7 — The Folder Watcher Service

The watcher monitors `~/GoogleDrive/` and, whenever you create a new top-level folder there, automatically pushes it to Drive, runs the initial bisync, adds it to tracking, and shows a desktop notification.

### Install as a background service

Copy the service file (first confirm your user ID with `id -u` — usually 1000):

```bash
mkdir -p ~/.config/systemd/user
cp scripts/rclone-watch.service ~/.config/systemd/user/
```

> If `id -u` is **not** 1000, edit `~/.config/systemd/user/rclone-watch.service` and update the number in the `DBUS_SESSION_BUS_ADDRESS` line. This only affects pop-up notifications; sync works regardless.

Enable and start it:

```bash
systemctl --user daemon-reload
systemctl --user enable --now rclone-watch.service
systemctl --user status rclone-watch.service
```

You should see `active (running)`.

### Test it

```bash
mkdir ~/GoogleDrive/TestFolder
```

Within a moment you should get a notification and `TestFolder` appears in Drive and in `~/.rclone-folders`.

---

## Part 8 — The GUI App

A lightweight Tkinter window that reads the same tracking file and runs the same rclone commands.

### What it offers

- A list of all tracked folders with their `shared`/`own` tag.
- **Pull**, **Push**, **Bisync** buttons for the selected folder.
- Three management buttons:
  - **⬇ Add Folder from Drive** — register a folder that already exists *on Drive* (pulls it down and tracks it). You type the exact Drive folder name and answer the shared yes/no.
  - **⬆ Push New Local Folder** — register a folder that exists *locally* in `~/GoogleDrive/` but isn't on Drive yet. It shows a picker of untracked local folders, pushes the one you choose up to Drive, runs the `--resync` baseline, and tracks it as `own`.
  - **↻ Refresh List** — reload the tracked-folder list.
- Two removal buttons:
  - **✕ Untrack (keep files)** — stops tracking the selected folder for sync. **Nothing is deleted** — both your local copy and the Drive copy stay. Use this when you just want it out of the sync list.
  - **🗑 Remove Folder & Untrack** — permanently deletes the **local** folder and removes it from tracking. **Your Google Drive copy is NOT touched.** Use this for cleanup (e.g. after deleting a whole folder on Drive, which makes bisync abort — see Troubleshooting). Asks for confirmation first.
- A live output console showing rclone progress.
- Runs sync in a background thread so the window never freezes.

> **Two directions, two buttons.** "Add Folder from Drive" is for folders that live on Drive already. "Push New Local Folder" is for folders you created locally. They're opposites — pick the one matching where the folder currently exists.

### Run it

```bash
python3 ~/rclone-gui.py
```

### Add it to your application menu (optional)

```bash
cp scripts/rclone-gui.desktop ~/.local/share/applications/
update-desktop-database ~/.local/share/applications/
```

> The `.desktop` file automatically uses your home directory path. If you need to manually verify or update it, check `~/.local/share/applications/rclone-gui.desktop` and ensure the `Exec=` line points to your `rclone-gui.py` location.

"Google Drive Sync" will then appear in your app launcher.

---

## Part 9 — Daily Usage

| What you want | Do this |
|---------------|---------|
| Add a folder that exists **on Drive** | `~/rclone-add.sh "Folder Name"` **or** GUI → *⬇ Add Folder from Drive* |
| Push a folder you made **locally** | GUI → *⬆ Push New Local Folder* (or just `mkdir` it — see below) |
| Add a brand-new folder automatically | `mkdir ~/GoogleDrive/Name` and put a file in it — the watcher pushes it |
| Sync on demand (terminal) | `~/rclone-sync.sh` → pick folder → pick pull/push/bisync |
| Sync on demand (GUI) | open the app → select folder → click Pull / Push / Bisync |
| See tracked folders | `cat ~/.rclone-folders` |

> **Empty folders don't upload.** rclone never creates an empty folder on Drive. If a new folder won't push (via the watcher or the GUI), put at least one file inside it first.

---

## Part 10 — Push / Pull / Bisync Explained

The verbs resemble git, but this is a **file mirror**, not version control.

| Action | Direction | Adds / updates files | Deletes removed files |
|--------|-----------|:---:|:---:|
| **Pull** (`rclone copy`) | Drive → Local | ✅ | ❌ |
| **Push** (`rclone copy`) | Local → Drive | ✅ | ❌ |
| **Bisync** (`rclone bisync`) | Both ways | ✅ | ✅ |

### The key behavior: Pull and Push never delete

Pull and Push use `rclone copy`, which **only adds or updates** files at the destination — it never deletes. This is a safety feature: a wrong-direction click can't wipe your files. The trade-off is that **deletions do not propagate** with Pull/Push.

**Example:** if you delete a file on Drive and then click **Pull**, the file stays on your local copy. Pull only brought down "what's new," and a deletion isn't "new."

### Bisync is the one that mirrors deletions

**Bisync** is two-way and has **no fixed direction**. It compares both sides against a remembered snapshot (the baseline from the last `--resync`), works out *what changed on each side*, and applies those changes the other way:

| What changed since last sync | What bisync does |
|---|---|
| New file on Drive | copy it down to Local |
| New file locally | copy it up to Drive |
| File deleted on Drive | delete it locally too |
| File deleted locally | delete it on Drive too |
| File changed on one side | update the other side |
| Same file changed on **both** sides | conflict — keeps both, renamed `..path1` / `..path2` |

So to make a deletion take effect on both sides, use **Bisync**, not Pull/Push.

> **Deleting a whole synced folder is different from deleting files inside it.** Bisync mirrors changes *inside* a tracked folder. If you delete the **entire tracked folder** on one side, the sync root disappears and bisync aborts with `directory not found` ("too dangerous to continue"). To clean that up, use the GUI's **🗑 Remove Folder & Untrack** (removes local + tracking, leaves Drive alone), or re-push with `rclone copy` followed by `--resync` to restore it.

### `--resync` is the baseline

The first `--resync` you run on a folder creates the snapshot that bisync compares against. Every later bisync updates it. If bisync ever reports *"must run --resync to recover,"* re-run the command with `--resync` once to rebuild the baseline.

### How it differs from git

- **No version history** — rclone mirrors current state; no commit log or rollback (beyond Google Drive's own Trash/version history).
- **No staging or commits** — actions apply to the whole folder's current contents immediately.
- **Bisync is file-level, not a content merge** — if the same file changed on both sides it's a conflict; the file contents are not merged line-by-line the way git does.

Great for documents, PDFs, and images across machines. Not a substitute for git when you need rollback or simultaneous co-editing of one file.

### ⚠️ Special note for "Shared with me" folders

If a folder is **shared with you but owned by someone else**, your "delete" in the Drive web interface may only **remove it from your view** rather than truly delete the file (the owner still has it). In that case rclone still sees the file on Drive, so bisync reports *"No changes found"* and nothing is removed locally — which is correct from rclone's perspective. True deletion of shared content usually requires the owner, or you needing edit/delete rights on it.

---

## Part 11 — Security Notes

- **Protect the config file** (it holds your OAuth token):
  ```bash
  chmod 600 ~/.config/rclone/rclone.conf
  ```
- **Optionally encrypt the config** with a password: `rclone config` → `s` (Set configuration password).
- **Review or revoke access** anytime at <https://myaccount.google.com/permissions>.
- All transfers use **TLS**; your Google password is never stored by rclone.

---

## Part 12 — Troubleshooting

| Problem | Fix |
|---------|-----|
| `invalid_grant: token expired` | `rclone config reconnect gdrive2:` |
| `directory not found` on a shared folder | add `--drive-shared-with-me`; confirm exact name with `rclone lsd gdrive2: --drive-shared-with-me` |
| `daemon exited with error code 1` on mount | `fusermount -u ~/GoogleDrive` then `pkill rclone` and retry |
| Folder name has spaces | always wrap in quotes: `"My Folder"` |
| `bisync aborted. Must run --resync` | re-run the same command adding `--resync` once |
| Deleted a file but Pull didn't remove it locally | expected — Pull/Push never delete. Use **Bisync** to mirror deletions |
| Deleted on a shared folder but Bisync says "No changes found" | your delete only removed it from your view; the owner still has it, so it's still on Drive |
| Deleted the **whole synced folder** on Drive → Bisync errors `directory not found` / aborts | bisync can't sync when a root is gone. In the GUI use **🗑 Remove Folder & Untrack** to clean up locally, or re-push with `rclone copy` + `--resync` to restore it |
| New folder won't upload | rclone skips empty folders — put a file inside, then push |
| GUI won't open / `no module named tkinter` | `sudo pacman -S tk` |
| Watcher gives no notifications | check `id -u` matches the number in the service file |
| Check what happened | `cat /tmp/rclone-bisync.log` or `cat /tmp/rclone-watch.log` |

---

## Quick Reference

```bash
# Connection
rclone ls gdrive2:                                   # test connection
rclone config reconnect gdrive2:                     # refresh expired token
rclone lsd gdrive2: --drive-shared-with-me           # list shared folders

# Add folders
~/rclone-add.sh "Folder Name"                        # add existing Drive folder
mkdir ~/GoogleDrive/Name                             # add new folder (watcher auto-handles)

# Sync
~/rclone-sync.sh                                     # terminal menu
python3 ~/rclone-gui.py                              # GUI app

# Tracking & logs
cat ~/.rclone-folders                                # list tracked folders
cat /tmp/rclone-bisync.log                           # sync log
cat /tmp/rclone-watch.log                            # watcher log

# Watcher service
systemctl --user status rclone-watch.service         # check
systemctl --user restart rclone-watch.service        # restart
systemctl --user stop rclone-watch.service           # stop
systemctl --user disable rclone-watch.service        # disable autostart
```

---

## Files in This Bundle

```
rclone-drive-sync/
├── README.md                      ← this guide
└── scripts/
    ├── rclone-add.sh              ← add existing Drive folder
    ├── rclone-watch.sh            ← background new-folder watcher
    ├── rclone-sync.sh             ← terminal pull/push/bisync menu
    ├── rclone-gui.py              ← GUI app
    ├── rclone-watch.service       ← systemd unit for the watcher
    └── rclone-gui.desktop         ← app-menu launcher
```

*Remember to verify user ID with `id -u` when setting up the systemd service — it's usually `1000` but may differ on your system.*
