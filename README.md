# Rclone + Google Drive on Manjaro — Complete Guide

A full, from-scratch setup for two-way Google Drive sync on Manjaro Linux, with helper scripts, an automatic folder watcher, and a simple GUI app that supports multiple Google accounts.

---

## Table of Contents

**Setup (do once)**
1. [Install Rclone & Dependencies](#part-1--install-rclone--dependencies)
2. [Connect Your Google Account](#part-2--connect-your-google-account)
3. [Install the Scripts & GUI](#part-3--install-the-scripts--gui)
4. [Enable the Folder Watcher (optional)](#part-4--enable-the-folder-watcher-optional)

**Concepts**
5. [How the System Works](#part-5--how-the-system-works)
6. [Shared Folders](#part-6--shared-folders)
7. [Multiple Google Accounts](#part-7--multiple-google-accounts)
8. [Push / Pull / Bisync Explained](#part-8--push--pull--bisync-explained)

**Using It**
9. [The GUI App](#part-9--the-gui-app)
10. [Daily Usage](#part-10--daily-usage)

**Reference**
11. [Security Notes](#part-11--security-notes)
12. [Troubleshooting](#part-12--troubleshooting)
- [Quick Reference](#quick-reference)
- [Files in This Bundle](#files-in-this-bundle)

---

## Objectives

This setup achieves four goals:

1. **Connect Google Drive** (one or more accounts) to your Manjaro machine using rclone — open source, secure OAuth.
2. **Add any existing Drive folder** (your own or "Shared with me") to local two-way sync.
3. **Auto-detect new local folders** — create a folder in `~/GoogleDrive/` and it is pushed to Drive and bisync-enabled automatically.
4. **Control sync on demand** via a clean GUI (or scripts) — pull, push, or two-way sync any folder, instead of forced background syncing.

A single tracking file (`~/.rclone-folders`) keeps every tool consistent.

> **About rclone:** it's an open-source tool that transfers files directly between your machine and Google over TLS (nothing passes through rclone's servers). It uses OAuth 2.0, so your Google password is never stored — only a revocable access token. In this guide the first remote is named **`gdrive2`**; substitute your own name where it differs.

---

# Setup

## Part 1 — Install Rclone & Dependencies

```bash
sudo pacman -S rclone fuse3 inotify-tools tk
```

| Package | Why |
|---------|-----|
| `rclone` | the core sync tool |
| `fuse3` | needed for mounting drives |
| `inotify-tools` | lets the watcher detect new folders |
| `tk` | Tkinter — needed for the GUI app |

Verify:

```bash
rclone version
```

---

## Part 2 — Connect Your Google Account

Start the interactive setup:

```bash
rclone config
```

Follow the prompts:

```
n) New remote               → n
name>                       → gdrive2
Storage>                    → drive          (type "drive")
client_id>                  → (leave blank, Enter)
client_secret>              → (leave blank, Enter)
scope>                      → 1              (Full access)
root_folder_id>             → (Enter)
service_account_file>       → (Enter)
Edit advanced config?       → n
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

> **Optional — your own API keys:** leaving `client_id` blank uses rclone's shared credentials, which Google occasionally rate-limits. For a private connection, create OAuth credentials at <https://console.cloud.google.com> (enable the Google Drive API, make OAuth 2.0 credentials) and paste your own `client_id` / `client_secret` during config.

### Reconnecting an expired token

If you later see `invalid_grant: maybe token expired`, refresh it:

```bash
rclone config reconnect gdrive2:
```

Answer `y` to refresh, `y` to use the browser, complete the sign-in, and `n` to the Team Drive question. Then `rclone ls gdrive2:` to confirm.

> Adding **more** accounts is covered in [Part 7](#part-7--multiple-google-accounts).

---

## Part 3 — Install the Scripts & GUI

All scripts are in the `scripts/` folder of this bundle. Copy them to your home directory:

```bash
cp scripts/rclone-add.sh   ~/rclone-add.sh
cp scripts/rclone-sync.sh  ~/rclone-sync.sh
cp scripts/rclone-watch.sh ~/rclone-watch.sh
cp scripts/rclone-gui.py   ~/rclone-gui.py
```

Make them executable:

```bash
chmod +x ~/rclone-add.sh ~/rclone-sync.sh ~/rclone-watch.sh ~/rclone-gui.py
```

If you previously ran an old auto-sync cron job, remove it (this system uses the watcher + manual sync instead):

```bash
crontab -r
```

### Register your first folder

For a folder that already exists on Drive:

```bash
~/rclone-add.sh "Folder Name"
```

It asks whether the folder is shared, creates the local copy, runs the initial `--resync`, and adds it to tracking.

> If a folder was already synced before this system existed, you don't need to resync — just add its tracking line directly:
> ```bash
> echo "gdrive2|shared|Folder Name" >> ~/.rclone-folders
> ```

> **Note:** This step is manual on purpose — the GUI runs *from* these files, so it can't install itself. The GUI *can*, however, set up the watcher service for you (Part 4) and add extra accounts (Part 7).

---

## Part 4 — Enable the Folder Watcher (optional)

The watcher monitors `~/GoogleDrive/`. When you create a new top-level folder there, it automatically pushes it to Drive (account `gdrive2`), runs the initial bisync, adds it to tracking, and shows a desktop notification.

### Easiest: from the GUI

Open the GUI (`python3 ~/rclone-gui.py`) → click **⚙ Watcher… → Install & Enable**. It writes the watcher script and systemd unit (auto-filling your home path and user ID) and starts it. Done.

### Manual alternative (terminal)

```bash
mkdir -p ~/.config/systemd/user
cp scripts/rclone-watch.service ~/.config/systemd/user/
```

> The bundled service file uses generic paths and user ID `1000` as a placeholder. Check yours with `whoami` and `id -u`, and edit `~/.config/systemd/user/rclone-watch.service` if they differ (the `ExecStart` path and the `DBUS_SESSION_BUS_ADDRESS` number). The user-ID only affects desktop notifications; sync works regardless. *(The GUI's Install & Enable avoids this by filling both in automatically.)*

Enable and start:

```bash
systemctl --user daemon-reload
systemctl --user enable --now rclone-watch.service
systemctl --user status rclone-watch.service
```

Look for `active (running)`. Test it:

```bash
mkdir ~/GoogleDrive/TestFolder    # put a file inside — empty folders don't upload
```

---

# Concepts

## Part 5 — How the System Works

Everything revolves around one tracking file, `~/.rclone-folders`. Each line records the account, type, and folder name:

```
remote|type|name
```

For example:

```
gdrive2|shared|My Shared Project
gdrive_personal|own|Photos
```

(Older 2-field lines like `shared|Folder Name` still work and are treated as belonging to `gdrive2`.)

Three scripts plus the GUI all read and write this single list:

```
                    ~/.rclone-folders   (single tracking list)
                  ▲          ▲          ▲          ▲
                  │          │          │          │
          rclone-add.sh  rclone-watch.sh  rclone-sync.sh  rclone-gui.py
          (existing       (new local      (manual CLI     (manual GUI
           Drive folder)   folder)         sync)           sync + setup)
```

The local mirror lives at `~/GoogleDrive/<folder name>`.

---

## Part 6 — Shared Folders

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

The scripts track whether each folder is `shared` or `own` and apply the flag automatically.

> Pushing changes *to* a shared folder only works if you have **edit permission** on it. Deleting items in a shared folder you don't own may only remove them from your view, not actually delete them — see [Part 8](#part-8--push--pull--bisync-explained).

---

## Part 7 — Multiple Google Accounts

Each Google account is a separate rclone **remote**.

### Add another account

**From the GUI (easiest):** click **+ Add Google Account**, enter a remote name (e.g. `gdrive_personal`), and complete the Google sign-in in the browser that opens.

**From the terminal:**

```bash
rclone config
```
`n` (new remote) → name it → `drive` → blanks → scope `1` → authenticate with the **second** account → `n` for Team Drive → `y` → `q`.

List all configured accounts:

```bash
rclone listremotes
```

### How accounts are handled

- The **tracking file** records each folder's account (`remote|type|name`).
- In the **GUI**, the *Account* dropdown picks the remote you're working with. Add/Push go to the selected account; the list filters to it (or shows all). Use *↻ Reload* after adding a new remote.
- In the **terminal menu** (`rclone-sync.sh`), each folder shows its account tag and syncs against the right remote automatically.

> **Local name collisions:** the local mirror is flat at `~/GoogleDrive/<folder>`. If two accounts each have a folder with the *same name*, they map to the same local path and clash. Give such folders distinct names.

> **The watcher** pushes brand-new local folders to one account only (`gdrive2`). For other accounts, add folders through the GUI where you can choose the account.

---

## Part 8 — Push / Pull / Bisync Explained

The verbs resemble git, but this is a **file mirror**, not version control.

| Action | Direction | Adds / updates | Deletes removed files |
|--------|-----------|:---:|:---:|
| **Pull** (`rclone copy`) | Drive → Local | ✅ | ❌ |
| **Push** (`rclone copy`) | Local → Drive | ✅ | ❌ |
| **Bisync** (`rclone bisync`) | Both ways | ✅ | ✅ |

### Pull and Push never delete

They use `rclone copy`, which only **adds or updates** files — never deletes. This is a safety feature, but it means **deletions don't propagate** with Pull/Push. Delete a file on Drive, click Pull, and the local copy stays.

### Bisync mirrors deletions

Bisync is two-way with **no fixed direction**. It compares both sides against a remembered snapshot (the baseline from the last `--resync`) and applies whatever changed, in whichever direction it happened:

| Change since last sync | Bisync does |
|---|---|
| New file on Drive | copy down to Local |
| New file locally | copy up to Drive |
| File deleted on Drive | delete it locally too |
| File deleted locally | delete it on Drive too |
| File changed one side | update the other side |
| Same file changed **both** sides | conflict — keeps both, renamed `..path1` / `..path2` |

So use **Bisync** to make a deletion take effect on both sides.

### `--resync` is the baseline

The first `--resync` on a folder creates the snapshot bisync compares against; later runs update it. If bisync reports *"must run --resync to recover,"* re-run with `--resync` once.

### Two important edge cases

- **Deleting a whole tracked folder** (not files inside it): the sync root disappears and bisync aborts with `directory not found` ("too dangerous to continue"). Clean up with the GUI's **🗑 Remove Folder & Untrack** (removes local + tracking, leaves Drive alone), or re-push with `rclone copy` + `--resync` to restore.
- **Deleting in a shared folder you don't own:** your "delete" may only remove it from your view; the owner still has it, so rclone still sees it and bisync reports *"No changes found."* That's correct from rclone's side.

### How it differs from git

No version history or rollback (beyond Drive's own Trash), no staging/commits, and bisync is file-level — it does not merge file *contents* line-by-line. Great for documents, PDFs, and images across machines; not a substitute for git when you need rollback or simultaneous co-editing of one file.

---

# Using It

## Part 9 — The GUI App

A lightweight Tkinter window that reads the same tracking file and runs the same rclone commands.

### What it offers

- An **Account** dropdown listing every configured account, plus an *All accounts* view. The selected account is where new folders are added; the list filters to it.
- **+ Add Google Account** — add an account with browser sign-in (see Part 7).
- **⚙ Watcher…** — install / start / stop the auto-sync watcher and see its status (see Part 4).
- A list of tracked folders, each tagged with account and type, e.g. `Reports   [gdrive2 · own]`.
- **Pull**, **Push**, **Bisync** for the selected folder (uses that folder's account automatically).
- **⬇ Add Folder from Drive** — register a folder that exists *on Drive*. It fetches and lists your untracked folders (both your own and *Shared with me*, each tagged), so you just pick one — no typing exact names. A *Type name manually…* fallback is available for nested or deeply-buried folders. Runs `--resync` and tracks it.
- **⬆ Push New Local Folder** — register a folder that exists *locally* but not on Drive yet: pick from a list of untracked local folders; pushes it up, runs `--resync`, tracks it as `own`.
- **✕ Untrack (keep files)** — removes a folder from the sync list only. Nothing is deleted on either side.
- **🗑 Remove Folder & Untrack** — permanently deletes the **local** folder and untracks it. The Drive copy is **not** touched. Asks for confirmation.
- A live output console; sync runs in a background thread so the window never freezes.

> The GUI does **not** install the helper scripts — that's a one-time manual step (Part 3), since the GUI runs from those files.

### Run it

```bash
python3 ~/rclone-gui.py
```

### Add it to your application menu (optional)

```bash
cp scripts/rclone-gui.desktop ~/.local/share/applications/
update-desktop-database ~/.local/share/applications/
```

> The `.desktop` file automatically uses your home directory. Check `~/.local/share/applications/rclone-gui.desktop` if you need to verify or update the `Exec=` line.

---

## Part 10 — Daily Usage

| What you want | Do this |
|---------------|---------|
| Add a folder that exists **on Drive** | `~/rclone-add.sh "Folder Name"` **or** GUI → *⬇ Add Folder from Drive* |
| Push a folder you made **locally** | GUI → *⬆ Push New Local Folder* |
| Add a brand-new folder automatically | `mkdir ~/GoogleDrive/Name` + put a file in it — the watcher pushes it |
| Sync on demand (terminal) | `~/rclone-sync.sh` → pick folder → pick pull/push/bisync |
| Sync on demand (GUI) | open app → select folder → click Pull / Push / Bisync |
| Add another Google account | GUI → *+ Add Google Account* (or `rclone config`) |
| See tracked folders | `cat ~/.rclone-folders` |

> **Empty folders don't upload.** rclone never creates an empty folder on Drive. If a new folder won't push, put at least one file inside first.

---

# Reference

## Part 11 — Security Notes

- **Protect the config file** (it holds your OAuth tokens):
  ```bash
  chmod 600 ~/.config/rclone/rclone.conf
  ```
- **Optionally encrypt it:** `rclone config` → `s` (Set configuration password).
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
| Deleted a file but Pull didn't remove it locally | expected — Pull/Push never delete. Use **Bisync** |
| Deleted on a shared folder but Bisync says "No changes found" | your delete only removed it from your view; the owner still has it |
| Deleted the **whole** tracked folder → Bisync errors `directory not found` | use GUI **🗑 Remove Folder & Untrack** to clean up locally, or re-push with `copy` + `--resync` |
| New folder won't upload | rclone skips empty folders — put a file inside, then push |
| GUI won't open / `no module named tkinter` | `sudo pacman -S tk` |
| Watcher gives no notifications | check `id -u` matches the number in the service file (or reinstall via GUI) |
| Check what happened | `cat /tmp/rclone-bisync.log` or `cat /tmp/rclone-watch.log` |

---

## Quick Reference

```bash
# Connection & accounts
rclone ls gdrive2:                                   # test connection
rclone config reconnect gdrive2:                     # refresh expired token
rclone listremotes                                   # list all accounts
rclone lsd gdrive2: --drive-shared-with-me           # list shared folders

# Add folders
~/rclone-add.sh "Folder Name"                        # add existing Drive folder
mkdir ~/GoogleDrive/Name                             # add new folder (watcher auto-handles)

# Sync
~/rclone-sync.sh                                     # terminal menu
python3 ~/rclone-gui.py                              # GUI app

# Tracking & logs
cat ~/.rclone-folders                                # tracked folders
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
    ├── rclone-add.sh              ← add existing Drive folder (CLI)
    ├── rclone-sync.sh             ← terminal pull/push/bisync menu
    ├── rclone-watch.sh            ← background new-folder watcher
    ├── rclone-gui.py              ← GUI app (sync + add accounts + watcher setup)
    ├── rclone-watch.service       ← systemd unit for the watcher
    └── rclone-gui.desktop         ← app-menu launcher
```

*Remember to verify user ID with `id -u` when setting up the systemd service — it's usually `1000` but may differ on your system. The GUI's watcher installer fills this in automatically.*
