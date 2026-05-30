#!/usr/bin/env python3
"""
Rclone Google Drive Sync — Simple GUI (multi-account)
A lightweight Tkinter interface for the rclone folder system.

Tracks folders across multiple Google Drive accounts (rclone remotes).
Tracking file format (~/.rclone-folders):
    remote|type|name      e.g.  gdrive2|shared|My Folder
Older 2-field lines (type|name) are still read and assumed to belong
to DEFAULT_REMOTE for backward compatibility.
"""

import os
import shutil
import threading
import subprocess
import tkinter as tk
from tkinter import ttk, simpledialog, messagebox

# ─── Config ───────────────────────────────────────────
DEFAULT_REMOTE = "gdrive2"          # fallback for old-format lines
HOME = os.path.expanduser("~")
LOCAL_BASE = os.path.join(HOME, "GoogleDrive")
CONFIG_FILE = os.path.join(HOME, ".rclone-folders")
ALL_ACCOUNTS = "— All accounts —"

WATCHER_PATH = os.path.join(HOME, "rclone-watch.sh")
SERVICE_DIR = os.path.join(HOME, ".config", "systemd", "user")
SERVICE_PATH = os.path.join(SERVICE_DIR, "rclone-watch.service")

# Watcher script written by the GUI when setting up auto-detection.
WATCHER_SCRIPT = r'''#!/bin/bash
# rclone-watch.sh — auto-detect new local folders and push to Drive.
WATCH_DIR="$HOME/GoogleDrive"
REMOTE="gdrive2"
CONFIG_FILE="$HOME/.rclone-folders"
LOG_FILE="/tmp/rclone-watch.log"

echo "[$(date)] Watching $WATCH_DIR for new folders..."

inotifywait -m -e create --format '%f' "$WATCH_DIR" | while read FOLDER_NAME; do
  FULL_PATH="$WATCH_DIR/$FOLDER_NAME"
  [ -d "$FULL_PATH" ] || continue
  echo "[$(date)] New folder detected: $FOLDER_NAME"
  if grep -qF "$FOLDER_NAME" "$CONFIG_FILE" 2>/dev/null; then
    echo "[$(date)] Already tracked, skipping."
    continue
  fi
  notify-send "Rclone Watcher" "Pushing '$FOLDER_NAME' to Drive..." 2>/dev/null
  rclone copy "$FULL_PATH" "$REMOTE:$FOLDER_NAME" \
    --log-file "$LOG_FILE" --log-level INFO --verbose
  if [ $? -eq 0 ]; then
    rclone bisync "$REMOTE:$FOLDER_NAME" "$FULL_PATH" \
      --resync --log-file "$LOG_FILE" --log-level INFO --verbose
    if [ $? -eq 0 ]; then
      echo "gdrive2|own|$FOLDER_NAME" >> "$CONFIG_FILE"
      notify-send "Rclone Watcher" "✅ '$FOLDER_NAME' synced & tracked!" 2>/dev/null
    else
      notify-send "Rclone Watcher" "⚠️ '$FOLDER_NAME' pushed but bisync failed." 2>/dev/null
    fi
  else
    notify-send "Rclone Watcher" "❌ Failed to push '$FOLDER_NAME'." 2>/dev/null
  fi
done
'''
# ──────────────────────────────────────────────────────


def service_file_text():
    """Generate the systemd unit with the correct home path and user ID."""
    uid = os.getuid()
    return (
        "[Unit]\n"
        "Description=Rclone Folder Watcher\n"
        "After=network-online.target\n\n"
        "[Service]\n"
        "Type=simple\n"
        f"ExecStart={WATCHER_PATH}\n"
        "Restart=on-failure\n"
        "RestartSec=5\n"
        "Environment=DISPLAY=:0\n"
        f"Environment=DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/{uid}/bus\n\n"
        "[Install]\n"
        "WantedBy=default.target\n"
    )


def list_remotes():
    """Return configured rclone remotes (names without trailing colon)."""
    try:
        out = subprocess.run(["rclone", "listremotes"],
                             capture_output=True, text=True, timeout=10)
        remotes = [r.strip().rstrip(":") for r in out.stdout.splitlines() if r.strip()]
        return remotes or [DEFAULT_REMOTE]
    except Exception:
        return [DEFAULT_REMOTE]


def load_folders():
    """Read tracked folders. Returns list of (remote, ftype, name)."""
    folders = []
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE) as f:
            for line in f:
                line = line.strip()
                if not line or "|" not in line:
                    continue
                parts = line.split("|")
                if len(parts) >= 3:
                    remote, ftype, name = parts[0], parts[1], "|".join(parts[2:])
                else:  # old 2-field format: type|name
                    remote, ftype, name = DEFAULT_REMOTE, parts[0], parts[1]
                folders.append((remote, ftype, name))
    return folders


def save_folder(remote, ftype, name):
    """Append a folder if that (remote, name) pair isn't already tracked."""
    existing = load_folders()
    if any(r == remote and n == name for r, _, n in existing):
        return
    with open(CONFIG_FILE, "a") as f:
        f.write(f"{remote}|{ftype}|{name}\n")


def remove_folder(remote, name):
    """Remove a (remote, name) folder; keep all others. Rewrites in 3-field form."""
    existing = load_folders()
    remaining = [(r, t, n) for r, t, n in existing if not (r == remote and n == name)]
    with open(CONFIG_FILE, "w") as f:
        for r, t, n in remaining:
            f.write(f"{r}|{t}|{n}\n")


class RcloneGUI:
    def __init__(self, root):
        self.root = root
        root.title("Google Drive Sync")
        root.geometry("720x580")
        root.minsize(600, 460)

        self.remotes = list_remotes()

        # ── Account selector ──
        acct = ttk.Frame(root, padding=(10, 10, 10, 0))
        acct.pack(fill="x")
        ttk.Label(acct, text="Account:", font=("", 10, "bold")).pack(side="left")
        self.account_var = tk.StringVar(value=ALL_ACCOUNTS)
        self.account_combo = ttk.Combobox(
            acct, textvariable=self.account_var, state="readonly",
            values=[ALL_ACCOUNTS] + self.remotes, width=28
        )
        self.account_combo.pack(side="left", padx=6)
        self.account_combo.bind("<<ComboboxSelected>>", lambda e: self.refresh())
        ttk.Button(acct, text="↻ Reload", command=self.reload_accounts).pack(side="left", padx=2)
        ttk.Button(acct, text="+ Add Google Account", command=self.add_account).pack(side="left", padx=2)
        ttk.Button(acct, text="⚙ Watcher…", command=self.watcher_dialog).pack(side="left", padx=2)

        # ── Folder list ──
        ttk.Label(root, text="Tracked Folders", font=("", 12, "bold"),
                  padding=(10, 8, 0, 0)).pack(anchor="w")
        list_frame = ttk.Frame(root, padding=(10, 0))
        list_frame.pack(fill="both", expand=False)

        self.listbox = tk.Listbox(list_frame, height=7, activestyle="dotbox")
        self.listbox.pack(side="left", fill="both", expand=True)
        scroll = ttk.Scrollbar(list_frame, command=self.listbox.yview)
        scroll.pack(side="right", fill="y")
        self.listbox.config(yscrollcommand=scroll.set)

        # ── Action buttons ──
        btns = ttk.Frame(root, padding=10)
        btns.pack(fill="x")
        self.pull_btn = ttk.Button(btns, text="⬇ Pull (Drive → Local)", command=lambda: self.run_action("pull"))
        self.pull_btn.pack(side="left", expand=True, fill="x", padx=2)
        self.push_btn = ttk.Button(btns, text="⬆ Push (Local → Drive)", command=lambda: self.run_action("push"))
        self.push_btn.pack(side="left", expand=True, fill="x", padx=2)
        self.bisync_btn = ttk.Button(btns, text="⇅ Bisync (Two-way)", command=lambda: self.run_action("bisync"))
        self.bisync_btn.pack(side="left", expand=True, fill="x", padx=2)

        # ── Add / push buttons ──
        btns2 = ttk.Frame(root, padding=(10, 0))
        btns2.pack(fill="x")
        ttk.Button(btns2, text="⬇ Add Folder from Drive", command=self.add_folder).pack(side="left", padx=2)
        ttk.Button(btns2, text="⬆ Push New Local Folder", command=self.push_local_folder).pack(side="left", padx=2)
        ttk.Button(btns2, text="↻ Refresh List", command=self.refresh).pack(side="left", padx=2)

        # ── Remove buttons ──
        btns3 = ttk.Frame(root, padding=(10, 4))
        btns3.pack(fill="x")
        ttk.Button(btns3, text="✕ Untrack (keep files)", command=self.untrack_folder).pack(side="left", padx=2)
        ttk.Button(btns3, text="🗑 Remove Folder & Untrack", command=self.remove_and_untrack).pack(side="left", padx=2)

        # ── Output console ──
        ttk.Label(root, text="Output", font=("", 10, "bold"), padding=(10, 8, 0, 0)).pack(anchor="w")
        out_frame = ttk.Frame(root, padding=(10, 0, 10, 10))
        out_frame.pack(fill="both", expand=True)
        self.output = tk.Text(out_frame, height=10, bg="#1e1e1e", fg="#d4d4d4",
                              insertbackground="#d4d4d4", wrap="word")
        self.output.pack(side="left", fill="both", expand=True)
        out_scroll = ttk.Scrollbar(out_frame, command=self.output.yview)
        out_scroll.pack(side="right", fill="y")
        self.output.config(yscrollcommand=out_scroll.set, state="disabled")

        # ── Status bar ──
        self.status = ttk.Label(root, text="Ready", relief="sunken", anchor="w", padding=4)
        self.status.pack(fill="x", side="bottom")

        self.folders = []
        self.refresh()

    # ── Helpers ──
    def log(self, text):
        self.output.config(state="normal")
        self.output.insert("end", text)
        self.output.see("end")
        self.output.config(state="disabled")

    def set_status(self, text):
        self.status.config(text=text)

    def set_buttons(self, enabled):
        state = "normal" if enabled else "disabled"
        for b in (self.pull_btn, self.push_btn, self.bisync_btn):
            b.config(state=state)

    def reload_accounts(self):
        self.remotes = list_remotes()
        self.account_combo.config(values=[ALL_ACCOUNTS] + self.remotes)
        self.log(f"\nAccounts: {', '.join(self.remotes)}\n")
        self.refresh()

    def current_account(self):
        """The account chosen in the dropdown, or None if 'All accounts'."""
        val = self.account_var.get()
        return None if val == ALL_ACCOUNTS else val

    def refresh(self):
        all_folders = load_folders()
        acct = self.current_account()
        if acct:
            self.folders = [f for f in all_folders if f[0] == acct]
        else:
            self.folders = all_folders
        self.listbox.delete(0, "end")
        for remote, ftype, name in self.folders:
            self.listbox.insert("end", f"{name}   [{remote} · {ftype}]")
        if self.folders:
            self.listbox.selection_set(0)
        scope = acct if acct else "all accounts"
        self.set_status(f"{len(self.folders)} folder(s) tracked ({scope})")

    def selected_folder(self):
        sel = self.listbox.curselection()
        if not sel:
            messagebox.showwarning("No selection", "Please select a folder first.")
            return None
        return self.folders[sel[0]]

    def require_account(self):
        """For add/push: need a specific account chosen, not 'All'."""
        acct = self.current_account()
        if not acct:
            messagebox.showinfo("Pick an account",
                                "Choose a specific account in the dropdown first,\n"
                                "so the folder is added to the right Drive.")
            return None
        return acct

    # ── Sync actions ──
    def run_action(self, action):
        folder = self.selected_folder()
        if not folder:
            return
        remote, ftype, name = folder
        shared_flag = ["--drive-shared-with-me"] if ftype == "shared" else []
        local_folder = os.path.join(LOCAL_BASE, name)
        os.makedirs(local_folder, exist_ok=True)

        if action == "pull":
            cmd = ["rclone", "copy", f"{remote}:{name}", local_folder] + shared_flag
        elif action == "push":
            cmd = ["rclone", "copy", local_folder, f"{remote}:{name}"] + shared_flag
        elif action == "bisync":
            cmd = ["rclone", "bisync", f"{remote}:{name}", local_folder] + shared_flag
        else:
            return
        cmd += ["--verbose", "--progress"]

        self.log(f"\n{'='*50}\n{action.upper()}: {name}  [{remote}]\n{'='*50}\n")
        self.set_buttons(False)
        self.set_status(f"Running {action} on '{name}' [{remote}]...")
        threading.Thread(target=self._run_cmd, args=(cmd, action, name), daemon=True).start()

    def _run_cmd(self, cmd, action, name):
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, text=True, bufsize=1)
            for line in proc.stdout:
                self.root.after(0, self.log, line)
            proc.wait()
            ok = proc.returncode == 0
            msg = f"\n✅ {action} complete!\n" if ok else f"\n❌ {action} failed (code {proc.returncode}).\n"
            self.root.after(0, self.log, msg)
            self.root.after(0, self.set_status, f"{action} {'done' if ok else 'failed'}: {name}")
        except FileNotFoundError:
            self.root.after(0, self.log, "\n❌ 'rclone' not found. Is it installed?\n")
            self.root.after(0, self.set_status, "Error: rclone not found")
        finally:
            self.root.after(0, self.set_buttons, True)

    # ── Add from Drive (with folder picker) ──
    def add_folder(self):
        remote = self.require_account()
        if not remote:
            return

        picker = tk.Toplevel(self.root)
        picker.title(f"Add Folder from Drive → {remote}")
        picker.geometry("480x420")
        picker.transient(self.root)
        picker.grab_set()

        ttk.Label(picker, padding=10,
                  text=f"Account: {remote}\nLoading folders from Drive…").pack(anchor="w")
        info = picker.winfo_children()[-1]

        lb = tk.Listbox(picker, activestyle="dotbox")
        lb.pack(fill="both", expand=True, padx=10)

        btnrow = ttk.Frame(picker, padding=10)
        btnrow.pack(fill="x")
        add_btn = ttk.Button(btnrow, text="Add Selected", state="disabled")
        add_btn.pack(side="left")
        ttk.Button(btnrow, text="Type name manually…",
                   command=lambda: (picker.destroy(), self._add_folder_manual(remote))).pack(side="left", padx=4)
        ttk.Button(btnrow, text="Cancel", command=picker.destroy).pack(side="right")

        entries = []  # list of (name, ftype)

        def lsf(extra):
            try:
                r = subprocess.run(["rclone", "lsf", "--dirs-only", f"{remote}:"] + extra,
                                   capture_output=True, text=True, timeout=60)
                if r.returncode != 0:
                    return []
                return [ln.rstrip("/").strip() for ln in r.stdout.splitlines() if ln.strip()]
            except Exception:
                return []

        def load():
            tracked = {(rr, nn) for rr, _, nn in load_folders()}
            own = lsf([])
            shared = lsf(["--drive-shared-with-me"])
            seen = set()
            result = []
            for n in own:
                if (remote, n) not in tracked and n not in seen:
                    result.append((n, "own")); seen.add(n)
            for n in shared:
                if (remote, n) not in tracked and n not in seen:
                    result.append((n, "shared")); seen.add(n)
            self.root.after(0, populate, result)

        def populate(result):
            entries.clear()
            entries.extend(result)
            lb.delete(0, "end")
            if not entries:
                info.config(text=f"Account: {remote}\nNo untracked folders found on Drive.")
                return
            for name, ftype in entries:
                lb.insert("end", f"{name}   [{ftype}]")
            lb.selection_set(0)
            info.config(text=f"Account: {remote}\nSelect a folder to track "
                             f"({len(entries)} available):")
            add_btn.config(state="normal")

        def confirm():
            sel = lb.curselection()
            if not sel:
                return
            name, ftype = entries[sel[0]]
            picker.destroy()
            self._do_add_from_drive(remote, ftype, name)

        add_btn.config(command=confirm)
        threading.Thread(target=load, daemon=True).start()

    def _add_folder_manual(self, remote):
        """Fallback: type the folder name by hand (e.g. for nested folders)."""
        name = simpledialog.askstring(
            "Add Drive Folder",
            f"Account: {remote}\n\nEnter the exact Google Drive folder name:")
        if not name:
            return
        is_shared = messagebox.askyesno("Folder Type", "Is this a 'Shared with me' folder?")
        self._do_add_from_drive(remote, "shared" if is_shared else "own", name)

    def _do_add_from_drive(self, remote, ftype, name):
        shared_flag = ["--drive-shared-with-me"] if ftype == "shared" else []
        local_folder = os.path.join(LOCAL_BASE, name)
        os.makedirs(local_folder, exist_ok=True)

        cmd = ["rclone", "bisync", f"{remote}:{name}", local_folder,
               "--resync", "--verbose"] + shared_flag

        self.log(f"\n{'='*50}\nADD + RESYNC: {name}  [{remote} · {ftype}]\n{'='*50}\n")
        self.set_buttons(False)
        self.set_status(f"Adding '{name}' [{remote}]...")

        def worker():
            try:
                proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                        stderr=subprocess.STDOUT, text=True, bufsize=1)
                for line in proc.stdout:
                    self.root.after(0, self.log, line)
                proc.wait()
                if proc.returncode == 0:
                    save_folder(remote, ftype, name)
                    self.root.after(0, self.log, f"\n✅ '{name}' added and tracked on {remote}!\n")
                    self.root.after(0, self.refresh)
                else:
                    self.root.after(0, self.log, "\n❌ Failed. Check the folder name / sharing type.\n")
            except FileNotFoundError:
                self.root.after(0, self.log, "\n❌ 'rclone' not found.\n")
            finally:
                self.root.after(0, self.set_buttons, True)

        threading.Thread(target=worker, daemon=True).start()

    # ── Push new local folder ──
    def push_local_folder(self):
        remote = self.require_account()
        if not remote:
            return
        tracked = {(r, n) for r, _, n in load_folders()}
        try:
            entries = sorted(
                d for d in os.listdir(LOCAL_BASE)
                if os.path.isdir(os.path.join(LOCAL_BASE, d)) and (remote, d) not in tracked
            )
        except FileNotFoundError:
            messagebox.showerror("Error", f"{LOCAL_BASE} does not exist.")
            return

        if not entries:
            messagebox.showinfo("No new folders",
                                f"No untracked local folders to push to {remote}.\n\n"
                                "Create a folder in ~/GoogleDrive first.")
            return

        picker = tk.Toplevel(self.root)
        picker.title(f"Push New Local Folder → {remote}")
        picker.geometry("440x340")
        picker.transient(self.root)
        picker.grab_set()

        ttk.Label(picker, text=f"Push to account: {remote}\n\nSelect a local folder:",
                  padding=10).pack(anchor="w")
        lb = tk.Listbox(picker, activestyle="dotbox")
        lb.pack(fill="both", expand=True, padx=10)
        for e in entries:
            lb.insert("end", e)
        lb.selection_set(0)

        def confirm():
            sel = lb.curselection()
            if not sel:
                return
            name = entries[sel[0]]
            picker.destroy()
            self._do_push_local(remote, name)

        btnrow = ttk.Frame(picker, padding=10)
        btnrow.pack(fill="x")
        ttk.Button(btnrow, text="Push to Drive", command=confirm).pack(side="left")
        ttk.Button(btnrow, text="Cancel", command=picker.destroy).pack(side="right")

    def _do_push_local(self, remote, name):
        local_folder = os.path.join(LOCAL_BASE, name)
        push_cmd = ["rclone", "copy", local_folder, f"{remote}:{name}", "--verbose", "--progress"]
        resync_cmd = ["rclone", "bisync", f"{remote}:{name}", local_folder, "--resync", "--verbose"]

        self.log(f"\n{'='*50}\nPUSH LOCAL → DRIVE: {name}  [{remote}]\n{'='*50}\n")
        self.set_buttons(False)
        self.set_status(f"Pushing '{name}' to {remote}...")

        def worker():
            try:
                p1 = subprocess.Popen(push_cmd, stdout=subprocess.PIPE,
                                      stderr=subprocess.STDOUT, text=True, bufsize=1)
                for line in p1.stdout:
                    self.root.after(0, self.log, line)
                p1.wait()
                if p1.returncode != 0:
                    self.root.after(0, self.log,
                                    "\n❌ Push failed (is the folder empty? add a file first).\n")
                    return
                self.root.after(0, self.log, "\n— Establishing bisync baseline —\n")
                p2 = subprocess.Popen(resync_cmd, stdout=subprocess.PIPE,
                                      stderr=subprocess.STDOUT, text=True, bufsize=1)
                for line in p2.stdout:
                    self.root.after(0, self.log, line)
                p2.wait()
                if p2.returncode == 0:
                    save_folder(remote, "own", name)
                    self.root.after(0, self.log, f"\n✅ '{name}' pushed and tracked on {remote}!\n")
                    self.root.after(0, self.refresh)
                else:
                    self.root.after(0, self.log, "\n⚠️ Pushed, but baseline setup failed.\n")
            except FileNotFoundError:
                self.root.after(0, self.log, "\n❌ 'rclone' not found.\n")
            finally:
                self.root.after(0, self.set_buttons, True)

        threading.Thread(target=worker, daemon=True).start()

    # ── Remove / untrack ──
    def untrack_folder(self):
        folder = self.selected_folder()
        if not folder:
            return
        remote, ftype, name = folder
        if not messagebox.askyesno(
            "Untrack Folder",
            f"Stop tracking '{name}' [{remote}]?\n\n"
            "This only removes it from the sync list.\n"
            "Your LOCAL files and your GOOGLE DRIVE files are NOT deleted.\n\n"
            "You can re-add it later anytime."
        ):
            return
        remove_folder(remote, name)
        self.log(f"\n✕ Untracked '{name}' [{remote}] (files kept on both sides).\n")
        self.set_status(f"Untracked: {name}")
        self.refresh()

    def remove_and_untrack(self):
        folder = self.selected_folder()
        if not folder:
            return
        remote, ftype, name = folder
        local_folder = os.path.join(LOCAL_BASE, name)
        if not messagebox.askyesno(
            "Remove Folder & Untrack",
            f"⚠️ Permanently DELETE the local folder?\n\n   {local_folder}\n\n"
            "This deletes the LOCAL copy and removes it from tracking.\n"
            f"Your GOOGLE DRIVE copy on '{remote}' is NOT affected.\n\n"
            "This cannot be undone. Continue?",
            icon="warning"
        ):
            return
        try:
            if os.path.isdir(local_folder):
                shutil.rmtree(local_folder)
                self.log(f"\n🗑 Deleted local folder: {local_folder}\n")
            else:
                self.log(f"\n(Local folder didn't exist: {local_folder})\n")
        except Exception as e:
            self.log(f"\n❌ Could not delete local folder: {e}\n")
            messagebox.showerror("Error", f"Could not delete folder:\n{e}")
            return
        remove_folder(remote, name)
        self.log(f"✕ Untracked '{name}' [{remote}].\n✅ Done. (Drive copy left untouched.)\n")
        self.set_status(f"Removed & untracked: {name}")
        self.refresh()

    # ── Add a Google account (rclone remote) ──
    def add_account(self):
        name = simpledialog.askstring(
            "Add Google Account",
            "Name for this account's remote (letters/numbers/underscore):\n"
            "e.g. gdrive_personal, gdrive_work"
        )
        if not name:
            return
        name = name.strip().rstrip(":")
        if not name or " " in name:
            messagebox.showerror("Invalid name", "Use a single word, no spaces.")
            return
        if name in self.remotes:
            messagebox.showinfo("Exists", f"'{name}' is already configured.")
            return

        messagebox.showinfo(
            "Browser sign-in",
            "A browser window will open. Log in to the Google account you want "
            "to add and click Allow.\n\nIf no browser opens, copy the link from the "
            "Output panel into your browser."
        )

        cmd = ["rclone", "config", "create", name, "drive", "scope=drive"]
        self.log(f"\n{'='*50}\nADD ACCOUNT: {name}\n{'='*50}\n")
        self.set_status(f"Authorizing '{name}' — complete sign-in in your browser...")

        def worker():
            try:
                proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                        stderr=subprocess.STDOUT, text=True, bufsize=1)
                for line in proc.stdout:
                    self.root.after(0, self.log, line)
                proc.wait()
                if proc.returncode == 0:
                    self.root.after(0, self.log, f"\n✅ Account '{name}' added!\n")
                    self.root.after(0, self.reload_accounts)
                    self.root.after(0, lambda: self.account_var.set(name))
                    self.root.after(0, self.refresh)
                else:
                    self.root.after(0, self.log, "\n❌ Could not add account (sign-in cancelled or failed).\n")
            except FileNotFoundError:
                self.root.after(0, self.log, "\n❌ 'rclone' not found.\n")

        threading.Thread(target=worker, daemon=True).start()

    # ── Watcher service control ──
    def _svc(self, *args):
        """Run a systemctl --user command and return (rc, output)."""
        try:
            r = subprocess.run(["systemctl", "--user", *args],
                               capture_output=True, text=True, timeout=15)
            return r.returncode, (r.stdout + r.stderr).strip()
        except Exception as e:
            return 1, str(e)

    def watcher_dialog(self):
        dlg = tk.Toplevel(self.root)
        dlg.title("Auto-sync Watcher")
        dlg.geometry("460x300")
        dlg.transient(self.root)
        dlg.grab_set()

        ttk.Label(dlg, padding=10, justify="left",
                  text="The watcher auto-pushes any NEW folder you create in\n"
                       "~/GoogleDrive to Drive (account: gdrive2) and tracks it.").pack(anchor="w")

        status_lbl = ttk.Label(dlg, text="Checking status...", padding=(10, 0))
        status_lbl.pack(anchor="w")

        def update_status():
            rc, _ = self._svc("is-active", "rclone-watch.service")
            active = (rc == 0)
            installed = os.path.exists(SERVICE_PATH)
            if not installed:
                status_lbl.config(text="Status: not installed")
            else:
                status_lbl.config(text=f"Status: {'🟢 running' if active else '🔴 stopped'}")

        def install():
            try:
                with open(WATCHER_PATH, "w") as f:
                    f.write(WATCHER_SCRIPT)
                os.chmod(WATCHER_PATH, 0o755)
                os.makedirs(SERVICE_DIR, exist_ok=True)
                with open(SERVICE_PATH, "w") as f:
                    f.write(service_file_text())
                self._svc("daemon-reload")
                rc, out = self._svc("enable", "--now", "rclone-watch.service")
                self.log(f"\n[watcher] install: {out or 'enabled & started'}\n")
                messagebox.showinfo("Watcher", "Watcher installed and started.")
            except Exception as e:
                messagebox.showerror("Error", str(e))
            update_status()

        def start():
            rc, out = self._svc("start", "rclone-watch.service")
            self.log(f"\n[watcher] start: {out or 'started'}\n")
            update_status()

        def stop():
            rc, out = self._svc("stop", "rclone-watch.service")
            self.log(f"\n[watcher] stop: {out or 'stopped'}\n")
            update_status()

        def show_status():
            rc, out = self._svc("status", "rclone-watch.service")
            self.log(f"\n[watcher status]\n{out}\n")

        row = ttk.Frame(dlg, padding=10)
        row.pack(fill="x")
        ttk.Button(row, text="Install & Enable", command=install).pack(side="left", padx=2)
        ttk.Button(row, text="Start", command=start).pack(side="left", padx=2)
        ttk.Button(row, text="Stop", command=stop).pack(side="left", padx=2)

        row2 = ttk.Frame(dlg, padding=(10, 0))
        row2.pack(fill="x")
        ttk.Button(row2, text="Show full status in Output", command=show_status).pack(side="left", padx=2)
        ttk.Button(row2, text="Close", command=dlg.destroy).pack(side="right", padx=2)

        update_status()


if __name__ == "__main__":
    root = tk.Tk()
    app = RcloneGUI(root)
    root.mainloop()
