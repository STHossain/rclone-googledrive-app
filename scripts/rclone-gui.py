#!/usr/bin/env python3
"""
Rclone Google Drive Sync — Simple GUI
A lightweight Tkinter interface for the rclone folder system.
Reads tracked folders from ~/.rclone-folders and lets you
Pull / Push / Bisync, or add a new Drive folder.
"""

import os
import shutil
import threading
import subprocess
import tkinter as tk
from tkinter import ttk, simpledialog, messagebox

# ─── Config ───────────────────────────────────────────
REMOTE = "gdrive2"
HOME = os.path.expanduser("~")
LOCAL_BASE = os.path.join(HOME, "GoogleDrive")
CONFIG_FILE = os.path.join(HOME, ".rclone-folders")
# ──────────────────────────────────────────────────────


def load_folders():
    """Read tracked folders from the config file. Returns list of (type, name)."""
    folders = []
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE) as f:
            for line in f:
                line = line.strip()
                if not line or "|" not in line:
                    continue
                ftype, name = line.split("|", 1)
                folders.append((ftype, name))
    return folders


def save_folder(ftype, name):
    """Append a new folder to the config file if not present."""
    existing = load_folders()
    if any(n == name for _, n in existing):
        return
    with open(CONFIG_FILE, "a") as f:
        f.write(f"{ftype}|{name}\n")


def remove_folder(name):
    """Remove a folder from the config file (keeps all others)."""
    existing = load_folders()
    remaining = [(t, n) for t, n in existing if n != name]
    with open(CONFIG_FILE, "w") as f:
        for t, n in remaining:
            f.write(f"{t}|{n}\n")


class RcloneGUI:
    def __init__(self, root):
        self.root = root
        root.title("Google Drive Sync")
        root.geometry("680x520")
        root.minsize(560, 420)

        # ── Top: folder list ──
        top = ttk.Frame(root, padding=10)
        top.pack(fill="x")

        ttk.Label(top, text="Tracked Folders", font=("", 12, "bold")).pack(anchor="w")

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

        # ── Secondary buttons ──
        btns2 = ttk.Frame(root, padding=(10, 0))
        btns2.pack(fill="x")

        ttk.Button(btns2, text="⬇ Add Folder from Drive", command=self.add_folder).pack(side="left", padx=2)
        ttk.Button(btns2, text="⬆ Push New Local Folder", command=self.push_local_folder).pack(side="left", padx=2)
        ttk.Button(btns2, text="↻ Refresh List", command=self.refresh).pack(side="left", padx=2)

        # ── Remove buttons (right side) ──
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

    def refresh(self):
        self.folders = load_folders()
        self.listbox.delete(0, "end")
        for ftype, name in self.folders:
            self.listbox.insert("end", f"{name}   [{ftype}]")
        if self.folders:
            self.listbox.selection_set(0)
        self.set_status(f"{len(self.folders)} folder(s) tracked")

    def selected_folder(self):
        sel = self.listbox.curselection()
        if not sel:
            messagebox.showwarning("No selection", "Please select a folder first.")
            return None
        return self.folders[sel[0]]

    # ── Actions ──
    def run_action(self, action):
        folder = self.selected_folder()
        if not folder:
            return
        ftype, name = folder
        shared_flag = ["--drive-shared-with-me"] if ftype == "shared" else []
        local_folder = os.path.join(LOCAL_BASE, name)
        os.makedirs(local_folder, exist_ok=True)

        if action == "pull":
            cmd = ["rclone", "copy", f"{REMOTE}:{name}", local_folder] + shared_flag
        elif action == "push":
            cmd = ["rclone", "copy", local_folder, f"{REMOTE}:{name}"] + shared_flag
        elif action == "bisync":
            cmd = ["rclone", "bisync", f"{REMOTE}:{name}", local_folder] + shared_flag
        else:
            return
        cmd += ["--verbose", "--progress"]

        self.log(f"\n{'='*50}\n{action.upper()}: {name}\n{'='*50}\n")
        self.set_buttons(False)
        self.set_status(f"Running {action} on '{name}'...")
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

    def add_folder(self):
        name = simpledialog.askstring("Add Drive Folder",
                                      "Enter the exact Google Drive folder name:")
        if not name:
            return
        is_shared = messagebox.askyesno("Folder Type",
                                        "Is this a 'Shared with me' folder?")
        ftype = "shared" if is_shared else "own"
        shared_flag = ["--drive-shared-with-me"] if is_shared else []
        local_folder = os.path.join(LOCAL_BASE, name)
        os.makedirs(local_folder, exist_ok=True)

        cmd = ["rclone", "bisync", f"{REMOTE}:{name}", local_folder,
               "--resync", "--verbose"] + shared_flag

        self.log(f"\n{'='*50}\nADD + RESYNC: {name}\n{'='*50}\n")
        self.set_buttons(False)
        self.set_status(f"Adding '{name}'...")

        def worker():
            try:
                proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                        stderr=subprocess.STDOUT, text=True, bufsize=1)
                for line in proc.stdout:
                    self.root.after(0, self.log, line)
                proc.wait()
                if proc.returncode == 0:
                    save_folder(ftype, name)
                    self.root.after(0, self.log, f"\n✅ '{name}' added and tracked!\n")
                    self.root.after(0, self.refresh)
                else:
                    self.root.after(0, self.log,
                                    f"\n❌ Failed. Check the folder name is exact.\n")
            except FileNotFoundError:
                self.root.after(0, self.log, "\n❌ 'rclone' not found.\n")
            finally:
                self.root.after(0, self.set_buttons, True)

        threading.Thread(target=worker, daemon=True).start()

    def push_local_folder(self):
        """Push an existing LOCAL folder up to Drive, then track it for bisync."""
        # Find local folders in ~/GoogleDrive that aren't tracked yet
        tracked = {n for _, n in load_folders()}
        try:
            entries = sorted(
                d for d in os.listdir(LOCAL_BASE)
                if os.path.isdir(os.path.join(LOCAL_BASE, d)) and d not in tracked
            )
        except FileNotFoundError:
            messagebox.showerror("Error", f"{LOCAL_BASE} does not exist.")
            return

        if not entries:
            messagebox.showinfo("No new folders",
                                "No untracked folders found in ~/GoogleDrive.\n\n"
                                "Create a folder there first, then try again.")
            return

        # Simple picker dialog
        picker = tk.Toplevel(self.root)
        picker.title("Push New Local Folder")
        picker.geometry("420x320")
        picker.transient(self.root)
        picker.grab_set()

        ttk.Label(picker, text="Select a local folder to push to Drive:",
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
            self._do_push_local(name)

        btnrow = ttk.Frame(picker, padding=10)
        btnrow.pack(fill="x")
        ttk.Button(btnrow, text="Push to Drive", command=confirm).pack(side="left")
        ttk.Button(btnrow, text="Cancel", command=picker.destroy).pack(side="right")

    def _do_push_local(self, name):
        local_folder = os.path.join(LOCAL_BASE, name)

        # Step 1: push local -> drive, then Step 2: resync baseline
        push_cmd = ["rclone", "copy", local_folder, f"{REMOTE}:{name}",
                    "--verbose", "--progress"]
        resync_cmd = ["rclone", "bisync", f"{REMOTE}:{name}", local_folder,
                      "--resync", "--verbose"]

        self.log(f"\n{'='*50}\nPUSH LOCAL → DRIVE: {name}\n{'='*50}\n")
        self.set_buttons(False)
        self.set_status(f"Pushing '{name}' to Drive...")

        def worker():
            try:
                # Push up
                p1 = subprocess.Popen(push_cmd, stdout=subprocess.PIPE,
                                      stderr=subprocess.STDOUT, text=True, bufsize=1)
                for line in p1.stdout:
                    self.root.after(0, self.log, line)
                p1.wait()
                if p1.returncode != 0:
                    self.root.after(0, self.log,
                                    "\n❌ Push failed (is the folder empty? add a file first).\n")
                    return

                # Establish bisync baseline
                self.root.after(0, self.log, "\n— Establishing bisync baseline —\n")
                p2 = subprocess.Popen(resync_cmd, stdout=subprocess.PIPE,
                                      stderr=subprocess.STDOUT, text=True, bufsize=1)
                for line in p2.stdout:
                    self.root.after(0, self.log, line)
                p2.wait()
                if p2.returncode == 0:
                    save_folder("own", name)
                    self.root.after(0, self.log, f"\n✅ '{name}' pushed and tracked!\n")
                    self.root.after(0, self.refresh)
                else:
                    self.root.after(0, self.log, "\n⚠️ Pushed, but baseline setup failed.\n")
            except FileNotFoundError:
                self.root.after(0, self.log, "\n❌ 'rclone' not found.\n")
            finally:
                self.root.after(0, self.set_buttons, True)

        threading.Thread(target=worker, daemon=True).start()

    def untrack_folder(self):
        """Stop tracking the selected folder. Keeps both local and Drive copies."""
        folder = self.selected_folder()
        if not folder:
            return
        ftype, name = folder
        confirm = messagebox.askyesno(
            "Untrack Folder",
            f"Stop tracking '{name}'?\n\n"
            "This only removes it from the sync list.\n"
            "Your LOCAL files and your GOOGLE DRIVE files are NOT deleted.\n\n"
            "You can re-add it later anytime."
        )
        if not confirm:
            return
        remove_folder(name)
        self.log(f"\n✕ Untracked '{name}' (files kept on both sides).\n")
        self.set_status(f"Untracked: {name}")
        self.refresh()

    def remove_and_untrack(self):
        """Delete the LOCAL folder and stop tracking it. Drive copy is NOT touched."""
        folder = self.selected_folder()
        if not folder:
            return
        ftype, name = folder
        local_folder = os.path.join(LOCAL_BASE, name)

        confirm = messagebox.askyesno(
            "Remove Folder & Untrack",
            f"⚠️ Permanently DELETE the local folder?\n\n"
            f"   {local_folder}\n\n"
            "This deletes the LOCAL copy and removes it from tracking.\n"
            "Your GOOGLE DRIVE copy is NOT affected.\n\n"
            "This cannot be undone. Continue?",
            icon="warning"
        )
        if not confirm:
            return

        # Delete local folder if it exists
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

        remove_folder(name)
        self.log(f"✕ Untracked '{name}'.\n✅ Done. (Google Drive copy left untouched.)\n")
        self.set_status(f"Removed & untracked: {name}")
        self.refresh()


if __name__ == "__main__":
    root = tk.Tk()
    app = RcloneGUI(root)
    root.mainloop()
