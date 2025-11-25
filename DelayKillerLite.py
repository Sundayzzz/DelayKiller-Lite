# DelayKiller Lite - Safe Optimizer
# Rewritten and improved version
# Made safer: no unsafe undocumented tweaks, reversible, with proper error handling
# GUI styled similarly to original FastPing Lite Shoutout to them for the inspiration!

import ctypes, sys, os, subprocess, json, webbrowser, shutil, traceback
from pathlib import Path
from PIL import Image, ImageTk
import customtkinter as ctk
from tkinter import messagebox
import re

# ------------------------------------------------------------
# Helpers & Environment
# ------------------------------------------------------------
def is_windows():
    return sys.platform.startswith("win")

# Only attempt elevation on Windows
def run_as_admin():
    if not is_windows():
        return False
    try:
        if hasattr(ctypes, "windll") and ctypes.windll.shell32.IsUserAnAdmin():
            return True
    except Exception:
        pass
    try:
        python_exe = sys.executable
        script = os.path.abspath(sys.argv[0])
        params = " ".join([f'"{arg}"' for arg in sys.argv[1:]])
        # ShellExecuteW runs the process elevated
        ctypes.windll.shell32.ShellExecuteW(None, "runas", python_exe, f'"{script}" {params}', None, 1)
        sys.exit(0)
    except Exception:
        return False

# Try to elevate (harmless on non-Windows)
run_as_admin()

def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS  # type: ignore
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

# ------------------------------------------------------------
# Paths & Logging
# ------------------------------------------------------------
CONFIG_DIR = Path(os.getenv("APPDATA", "")) / "DelayKillerLite" / "config"
CONFIG_DIR.mkdir(parents=True, exist_ok=True)
CONFIG_FILE = CONFIG_DIR / "settings.json"
LOG_FILE = CONFIG_DIR / "app.log"
BACKUP_FILE = CONFIG_DIR / "backup.json"

def log(msg):
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(msg.rstrip() + "\n")
    except Exception:
        pass

# ------------------------------------------------------------
# Backup / Restore (safe, best-effort)
# ------------------------------------------------------------
def get_tcp_globals():
    """Query netsh for relevant TCP global settings and return a dict (best-effort)."""
    if not is_windows():
        return {}
    code, out = run_netsh("netsh interface tcp show global")
    if code != 0 or not out:
        return {}
    vals = {}
    # Normalize output lines and search for expected keys
    lines = out.splitlines()
    text = "\n".join(lines)
    # Map friendly keys -> regex to find values
    patterns = {
        "autotuninglevel": r"(Receive Window Auto-Tuning Level\s*:\s*)(.+)",
        "ecncapability": r"(ECN Capability\s*:\s*)(.+)",
        "rss": r"(Receive-Side Scaling State\s*:\s*)(.+)|(\brss\b\s*:\s*(.+))",
        "chimney": r"(Chimney Offload State\s*:\s*)(.+)|(\bchimney\b\s*:\s*(.+))",
        "congestionprovider": r"(Add-On Congestion Control Provider\s*:\s*)(.+)",
        "timestamps": r"(RFC 1323 Timestamps\s*:\s*)(.+)|(\btimestamps\b\s*:\s*(.+))",
    }
    for k, pat in patterns.items():
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            # take the last captured non-empty group
            for g in m.groups()[1:]:
                if g and isinstance(g, str) and g.strip():
                    vals[k] = g.strip()
                    break
        else:
            vals[k] = None
    return vals

def get_dns_info(iface):
    """Return dict {dhcp: bool, servers: [ips]} for interface (best-effort)."""
    if not is_windows():
        return {"dhcp": False, "servers": []}
    code, out = run_netsh(f'netsh interface ipv4 show dns name="{iface}"')
    if code != 0 or not out:
        return {"dhcp": False, "servers": []}
    # Find all IPv4 addresses
    servers = re.findall(r'\b\d{1,3}(?:\.\d{1,3}){3}\b', out)
    dhcp = bool(re.search(r'\b(DHCP|dhcp)\b', out))
    return {"dhcp": dhcp, "servers": servers}

def get_active_power_guid():
    code, out = run_cmd("powercfg /getactivescheme", timeout=4)
    if code != 0 or not out:
        return None
    m = re.search(r'([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})', out)
    return m.group(1) if m else None

def backup_settings(iface=None):
    """Save current relevant settings to BACKUP_FILE (best-effort)."""
    try:
        tcp = get_tcp_globals()
        iface = iface or (iface_var.get() if 'iface_var' in globals() else "Ethernet")
        dns = {iface: get_dns_info(iface)}
        power = get_active_power_guid()
        data = {"tcp_globals": tcp, "dns": dns, "power": power, "timestamp": int(Path(LOG_FILE).stat().st_mtime) if LOG_FILE.exists() else None}
        with open(BACKUP_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        log("Backup saved: " + json.dumps({"tcp": tcp, "dns": dns, "power": power}))
        return True
    except Exception as e:
        log("Backup failed: " + str(e))
        return False

def restore_from_backup():
    """Restore settings from BACKUP_FILE (best-effort)."""
    if not BACKUP_FILE.exists():
        log("No backup file to restore from")
        return False
    try:
        with open(BACKUP_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        tcp = data.get("tcp_globals", {})
        # Restore TCP globals (call set for known keys)
        mapping = {
            "autotuninglevel": lambda v: f'netsh interface tcp set global autotuninglevel={v}',
            "ecncapability": lambda v: f'netsh interface tcp set global ecncapability={v}',
            "rss": lambda v: f'netsh interface tcp set global rss={v}',
            "chimney": lambda v: f'netsh interface tcp set global chimney={v}',
            "congestionprovider": lambda v: f'netsh interface tcp set global congestionprovider={v}',
            "timestamps": lambda v: f'netsh interface tcp set global timestamps={v if v else "enabled"}',
        }
        for k, v in tcp.items():
            if v:
                cmd = mapping.get(k)
                if cmd:
                    run_netsh(cmd(v))
        # Restore DNS
        dns = data.get("dns", {})
        for iface, info in dns.items():
            if not iface:
                continue
            if info.get("dhcp", False):
                run_netsh(f'netsh interface ipv4 set dns name="{iface}" source=dhcp')
            else:
                servers = info.get("servers", [])
                if servers:
                    run_netsh(f'netsh interface ipv4 set dns name="{iface}" static {servers[0]} primary')
                    for idx, s in enumerate(servers[1:], start=2):
                        run_netsh(f'netsh interface ipv4 add dns name="{iface}" {s} index={idx}')
        # Restore power
        power = data.get("power")
        if power:
            run_cmd(f'powercfg /setactive {power}', timeout=6)
        log("Restored settings from backup")
        return True
    except Exception as e:
        log("Restore failed: " + str(e))
        return False

# ------------------------------------------------------------
# Optimizations (Safe & Reversible)
# ------------------------------------------------------------
def apply_tcp_tweaks(enable, backup=True):
    if not is_windows(): return 1, "Unsupported"
    try:
        if backup:
            backup_settings()
        # These are safe Microsoft-supported settings
        if enable:
            run_netsh("netsh interface tcp set global autotuninglevel=normal")
            run_netsh("netsh interface tcp set global ecncapability=enabled")
            run_netsh("netsh interface tcp set global rss=enabled")
            run_netsh("netsh interface tcp set global chimney=disabled")  # modern Windows often prefers chimney disabled
        else:
            # Try restore from backup if available, otherwise set sensible defaults
            if BACKUP_FILE.exists():
                if restore_from_backup():
                    return 0, "TCP tweaks restored from backup"
            run_netsh("netsh interface tcp set global autotuninglevel=normal")
            run_netsh("netsh interface tcp set global ecncapability=default")
            run_netsh("netsh interface tcp set global rss=default")
            run_netsh("netsh interface tcp set global chimney=disabled")
        return 0, "TCP tweaks applied"
    except Exception as e:
        return 1, str(e)

def set_low_latency_mode(enable, backup=True):
    if not is_windows(): return 1, "Unsupported"
    try:
        if backup:
            backup_settings()
        if enable:
            run_netsh("netsh interface tcp set global congestionprovider=ctcp")
            run_netsh("netsh interface tcp set global timestamps=disabled")
        else:
            # prefer restore from backup if possible
            if BACKUP_FILE.exists():
                with open(BACKUP_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                tcp = data.get("tcp_globals", {})
                cp = tcp.get("congestionprovider")
                ts = tcp.get("timestamps")
                if cp:
                    run_netsh(f'netsh interface tcp set global congestionprovider={cp}')
                if ts:
                    run_netsh(f'netsh interface tcp set global timestamps={ts}')
                return 0, "Low latency settings restored"
            run_netsh("netsh interface tcp set global congestionprovider=none")
            run_netsh("netsh interface tcp set global timestamps=enabled")
        return 0, "Low latency applied"
    except Exception as e:
        return 1, str(e)

def apply_dns_mode(enable, iface):
    if not is_windows():
        return 1, "Unsupported"
    try:
        name = iface or "Ethernet"
        # Backup current DNS for interface
        backup_settings(iface=name)
        # Prefer ipv4 explicit command; some Windows accept both
        if enable:
            run_netsh(f'netsh interface ipv4 set dns name="{name}" static 8.8.8.8 primary')
            run_netsh(f'netsh interface ipv4 add dns name="{name}" 8.8.4.4 index=2')
            run_netsh('ipconfig /flushdns')
        else:
            # restore from backup if available
            if BACKUP_FILE.exists():
                with open(BACKUP_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                dns = data.get("dns", {}).get(name)
                if dns:
                    if dns.get("dhcp", False):
                        run_netsh(f'netsh interface ipv4 set dns name="{name}" source=dhcp')
                    else:
                        servers = dns.get("servers", [])
                        if servers:
                            run_netsh(f'netsh interface ipv4 set dns name="{name}" static {servers[0]} primary')
                            for idx, s in enumerate(servers[1:], start=2):
                                run_netsh(f'netsh interface ipv4 add dns name="{name}" {s} index={idx}')
                    run_netsh('ipconfig /flushdns')
                    return 0, "DNS restored from backup"
            # fallback
            run_netsh(f'netsh interface ipv4 set dns name="{name}" source=dhcp')
            run_netsh('ipconfig /flushdns')
        return 0, "DNS mode applied"
    except Exception as e:
        return 1, str(e)

def set_power_plan(high_perf):
    if not is_windows():
        return 1, "Unsupported"
    try:
        # Backup current power plan
        backup_settings()
        guid = HIGH_PERF_GUID if high_perf else BALANCED_GUID
        code, out = run_cmd(f'powercfg /setactive {guid}', timeout=6)
        return (0, "Power plan set") if code == 0 else (1, out)
    except Exception as e:
        return 1, str(e)

# ------------------------------------------------------------
# Configuration
# ------------------------------------------------------------
def save_config():
    cfg = {
        "low_latency": bool(low_latency_var.get()),
        "dns_mode": bool(dns_var.get()),
        "power_high": bool(power_var.get()),
        "interface": iface_var.get()
    }
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
        status_var.set("Settings saved")
        log("Config saved: " + json.dumps(cfg))
    except Exception as e:
        status_var.set("Save failed")
        log("Save failed: " + str(e))

def load_config():
    try:
        if CONFIG_FILE.exists():
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            low_latency_var.set(bool(data.get("low_latency", False)))
            dns_var.set(bool(data.get("dns_mode", False)))
            power_var.set(bool(data.get("power_high", False)))
            iface = data.get("interface", "")
            if iface and iface in iface_list:
                iface_var.set(iface)
            status_var.set("Config loaded")
    except Exception as e:
        status_var.set("Config load failed")
        log("Load config failed: " + str(e))

# ------------------------------------------------------------
# Button Handlers
# ------------------------------------------------------------
def apply_all():
    try:
        save_config()
        log("Apply started")
        # create a backup before making any changes
        backup_settings(iface=iface_var.get())
        r1, o1 = apply_tcp_tweaks(True, backup=False)
        r2, o2 = set_low_latency_mode(low_latency_var.get(), backup=False)
        r3, o3 = apply_dns_mode(dns_var.get(), iface_var.get())
        r4, o4 = set_power_plan(power_var.get())
        status_var.set("Optimized Successfully")
        msg = "\n".join([f"TCP: {o1}", f"Latency: {o2}", f"DNS: {o3}", f"Power: {o4}"])
        log("Apply results: " + msg.replace("\n", " | "))
        messagebox.showinfo("DelayKiller Lite", "Optimizations Applied!\n\n" + msg)
    except Exception as e:
        status_var.set("Apply failed")
        log("Apply failed: " + traceback.format_exc())
        messagebox.showerror("DelayKiller Lite", "Apply failed:\n" + str(e))

def reset_all():
    try:
        log("Reset started")
        # Prefer restoring from backup
        if BACKUP_FILE.exists():
            ok = restore_from_backup()
            if ok:
                status_var.set("Settings Restored from backup")
                messagebox.showinfo("DelayKiller Lite", "Settings Restored from backup")
                return
        # Fallback: apply safe defaults
        apply_tcp_tweaks(False, backup=False)
        set_low_latency_mode(False, backup=False)
        apply_dns_mode(False, iface_var.get())
        set_power_plan(False)
        status_var.set("Settings Reset")
        messagebox.showinfo("DelayKiller Lite", "Settings Restored")
    except Exception as e:
        status_var.set("Reset failed")
        log("Reset failed: " + traceback.format_exc())
        messagebox.showerror("DelayKiller Lite", "Reset failed:\n" + str(e))

def open_discord():
    webbrowser.open("https://discord.gg/T8GFc6ryGy")

def show_help():
    txt = (
        "DelayKiller Lite - Safe Optimizer\n\n"
        "- Low Latency Mode: enables CTCP and disables timestamps (reversible).\n"
        "- DNS Performance Mode: sets DNS to Google (applies to selected interface).\n"
        "- High Performance Power Plan: switches Windows power plan for lower latency.\n\n"
        "All changes are reversible via Reset Settings. Use with admin privileges."
    )
    messagebox.showinfo("Help - DelayKiller Lite", txt)

# ---------------------------
# Added: command helpers, interface listing, defaults
# ---------------------------
def run_cmd(cmd, timeout=10):
    """Run shell command and return (returncode, stdout)."""
    try:
        proc = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        out = (proc.stdout or "").strip()
        # include stderr when stdout empty to aid debugging
        if not out and proc.stderr:
            out = proc.stderr.strip()
        return proc.returncode, out
    except subprocess.TimeoutExpired:
        return 124, ""
    except Exception as e:
        return 1, str(e)

def run_netsh(cmd):
    """Convenience wrapper for netsh commands that returns (code, output). Accepts either full command or args."""
    # Accept either "netsh ..." or just the args
    full = cmd if cmd.strip().lower().startswith("netsh") else f"netsh {cmd}"
    return run_cmd(full, timeout=8)

def list_interfaces():
    """Return list of network interface names (best-effort)."""
    if not is_windows():
        return []
    code, out = run_netsh("interface show interface")
    if code != 0 or not out:
        # Try 'netsh interface ipv4 show interfaces' as fallback
        code, out = run_netsh("interface ipv4 show interfaces")
        if code != 0 or not out:
            return []
    names = []
    # Try to parse lines that contain the interface name at the end
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        # Patterns: 'Enabled    Connected   Dedicated    Ethernet' or 'Idx     Met         MTU          Name'
        m = re.search(r'\b([^\r\n]{3,})$', line)
        if m:
            candidate = m.group(1).strip()
            # Filter out header lines
            if candidate.lower() not in ("admin state", "state", "name", "idx", "interface"):
                # avoid repeated entries
                if candidate not in names:
                    names.append(candidate)
    return names

# sensible defaults & fallbacks for resources and UI constants (prevents NameError)
LOGO_PATH = resource_path("logo.ico") if 'resource_path' in globals() else ""
BG = "#07111A" if "BG" not in globals() else BG
CARD = "#0c1a22" if "CARD" not in globals() else CARD
ACCENT = "#1fb6ff" if "ACCENT" not in globals() else ACCENT
TEXT = "#e6f0f6" if "TEXT" not in globals() else TEXT
SUBTEXT = "#9fb6c9" if "SUBTEXT" not in globals() else SUBTEXT
BUTTON_BG = "#0f262f" if "BUTTON_BG" not in globals() else BUTTON_BG
BUTTON_HOVER = "#13333d" if "BUTTON_HOVER" not in globals() else BUTTON_HOVER
FONT_LARGE = ("Segoe UI", 16, "bold") if "FONT_LARGE" not in globals() else FONT_LARGE
FONT_MED = ("Segoe UI", 11) if "FONT_MED" not in globals() else FONT_MED
FONT_SMALL = ("Segoe UI", 10) if "FONT_SMALL" not in globals() else FONT_SMALL

# power plan GUIDs commonly used on Windows
HIGH_PERF_GUID = "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c"
BALANCED_GUID = "381b4222-f694-41f0-9685-ff5bb260df2e"

# ------------------------------------------------------------
# GUI
# ------------------------------------------------------------
app = ctk.CTk()
app.geometry("640x460")
app.title("DelayKiller Lite")
if LOGO_PATH and os.path.exists(LOGO_PATH) and is_windows():
    try:
        app.iconbitmap(LOGO_PATH)
    except Exception:
        pass
app.configure(fg_color=BG)

# Variables (ensure defined before load_config)
low_latency_var = ctk.BooleanVar(value=False)
dns_var = ctk.BooleanVar(value=False)
power_var = ctk.BooleanVar(value=False)
status_var = ctk.StringVar(value="Ready")
iface_list = list_interfaces()
iface_var = ctk.StringVar(value=iface_list[0] if iface_list else "")

# Main layout
main = ctk.CTkFrame(app, fg_color=BG, corner_radius=0)
main.pack(fill="both", expand=True, padx=18, pady=12)

header = ctk.CTkFrame(main, fg_color=CARD, corner_radius=12)
header.pack(fill="x", padx=8, pady=(10, 12))

header_left = ctk.CTkFrame(header, fg_color=CARD, corner_radius=0)
header_left.pack(side="left", padx=12, pady=12)

# Logo
try:
    if LOGO_PATH and os.path.exists(LOGO_PATH):
        logo_img = Image.open(LOGO_PATH).resize((76, 76))
        logo = ImageTk.PhotoImage(logo_img)
        ctk.CTkLabel(header_left, image=logo, text="", fg_color=CARD).pack()
    else:
        ctk.CTkLabel(header_left, text="DK", font=("Segoe UI", 28, "bold"), text_color=ACCENT, fg_color=CARD).pack()
except Exception:
    ctk.CTkLabel(header_left, text="DK", font=("Segoe UI", 28, "bold"), text_color=ACCENT, fg_color=CARD).pack()

title_frame = ctk.CTkFrame(header, fg_color=CARD, corner_radius=0)
title_frame.pack(side="left", padx=(6,24), pady=12, anchor="w")
ctk.CTkLabel(title_frame, text="DelayKiller Lite", font=FONT_LARGE, text_color=TEXT, fg_color=CARD).pack(anchor="w")
ctk.CTkLabel(title_frame, text="Safe Optimizer Edition — reversible tweaks", font=FONT_MED, text_color=SUBTEXT, fg_color=CARD).pack(anchor="w", pady=(4,0))

# Controls card
card = ctk.CTkFrame(main, fg_color="#07111A", corner_radius=12)
card.pack(fill="both", expand=True, padx=8, pady=(0, 12))

# Left column (toggles)
left_col = ctk.CTkFrame(card, fg_color="transparent")
left_col.pack(side="left", padx=18, pady=14, fill="y")

ctk.CTkLabel(left_col, text="Optimizations", font=("Segoe UI", 14, "bold"), text_color=TEXT).pack(anchor="w", pady=(0,8))
ctk.CTkCheckBox(left_col, text="Low Latency Mode", variable=low_latency_var, text_color=TEXT).pack(anchor="w", pady=6)
ctk.CTkCheckBox(left_col, text="DNS Performance Mode", variable=dns_var, text_color=TEXT).pack(anchor="w", pady=6)
ctk.CTkCheckBox(left_col, text="High Performance Power Plan", variable=power_var, text_color=TEXT).pack(anchor="w", pady=6)

# Interface selector
ctk.CTkLabel(left_col, text="Network Interface:", font=FONT_SMALL, text_color=SUBTEXT).pack(anchor="w", pady=(12,4))
iface_menu = ctk.CTkOptionMenu(left_col, values=iface_list, variable=iface_var, dropdown_hover_color=BUTTON_HOVER, button_color=BUTTON_BG, text_color=TEXT)
iface_menu.pack(anchor="w", pady=(0,10))

# Right column (buttons + status)
right_col = ctk.CTkFrame(card, fg_color="transparent")
right_col.pack(side="right", padx=18, pady=14, fill="both", expand=True)

ctk.CTkLabel(right_col, text="Actions", font=("Segoe UI", 14, "bold"), text_color=TEXT).pack(anchor="w", pady=(0,8))

button_style = {"corner_radius": 10, "height": 46, "fg_color": ACCENT, "hover_color": "#57a0ff", "text_color": "#0b1220", "font": ("Segoe UI", 13, "bold")}

ctk.CTkButton(right_col, text="Apply Optimizations", command=apply_all, **button_style).pack(fill="x", pady=6)
ctk.CTkButton(right_col, text="Reset Settings", command=reset_all, fg_color=BUTTON_BG, hover_color=BUTTON_HOVER, text_color=TEXT).pack(fill="x", pady=6)
ctk.CTkButton(right_col, text="Discord", command=open_discord, fg_color=BUTTON_BG, hover_color=BUTTON_HOVER, text_color=TEXT).pack(fill="x", pady=6)
ctk.CTkButton(right_col, text="Help", command=show_help, fg_color=BUTTON_BG, hover_color=BUTTON_HOVER, text_color=TEXT).pack(fill="x", pady=(6,0))

# Status bar
status_frame = ctk.CTkFrame(main, height=36, fg_color=CARD, corner_radius=8)
status_frame.pack(fill="x", padx=8, pady=(0,8))
ctk.CTkLabel(status_frame, textvariable=status_var, text_color=SUBTEXT, font=FONT_SMALL).pack(side="left", padx=12)
ctk.CTkButton(status_frame, text="Open Log", width=100, height=26, fg_color=BUTTON_BG, hover_color=BUTTON_HOVER, text_color=TEXT,
              command=lambda: os.startfile(LOG_FILE) if os.path.exists(LOG_FILE) else messagebox.showinfo("Log", "No log yet.")).pack(side="right", padx=12)

# Load config and start
try:
    load_config()
    app.mainloop()
except Exception:
    # Ensure the error is logged for inspection
    try:
        log("Fatal startup error:\n" + traceback.format_exc())
    except Exception:
        pass
    # Show a dialog (if GUI partially available) and keep console open when double-clicked
    try:
        messagebox.showerror("DelayKiller Lite - Startup Error", "An error occurred during startup. See log for details.")
    except Exception:
        pass
    # Print traceback to the console so running from cmd shows it, and pause so window doesn't immediately close
    print("Fatal startup error:\n")
    traceback.print_exc()
    try:
        input("Press Enter to exit...")
    except Exception:
        pass
    sys.exit(1)
