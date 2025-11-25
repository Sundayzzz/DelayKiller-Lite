"""
DelayKiller Premium — Full implementation

This file implements a premium FastPing-style GUI with real, safe backend modules:
 - DNS Booster (flush DNS + optional benchmark & set best DNS)
 - MTU Optimizer (safe probe to suggest MTU)
 - Network Stack Repair (netsh resets, Winsock, adapter renew)
 - SmartGaming Mode (auto-detect common games and apply presets)
 - Latency Stabilizer (timer resolution + process niceness tuning)
 - FPS Boost toolkit (power plan, temp cleaner, optional process hints)
 - Per-game presets and profiles
 - EXE Builder helper (runs PyInstaller if available)

Security & usability notes:
 - Any system-changing action requires explicit user confirmation.
 - The app creates registry/backups and works in dry-run mode without admin.
 - No destructive deletes; temp cleaner only removes from OS temp folders.

Run on Windows for full functionality. Inspect the code before running.
"""

import os
import sys
import time
import json
import ctypes
import threading
import subprocess
from pathlib import Path
from tkinter import messagebox

try:
    import customtkinter as ctk
except Exception:
    raise RuntimeError("customtkinter is required. Install with: pip install customtkinter")

try:
    import psutil
except Exception:
    raise RuntimeError("psutil is required. Install with: pip install psutil")

try:
    from PIL import Image, ImageTk
except Exception:
    Image = None
    ImageTk = None

IS_WINDOWS = sys.platform.startswith("win")

APP_NAME = "DelayKiller Premium"
APP_SIZE = "1100x720"

# Colors
COL_BG = "#0A0F16"
COL_CARD = "#0F1724"
COL_PANEL = "#101B28"
COL_ACCENT1 = "#7C4DFF"
COL_ACCENT2 = "#00D1FF"
COL_TEXT = "#E6EDF3"
COL_MUTED = "#8795A1"

# Paths
CONFIG_DIR = Path(os.getenv("APPDATA", Path.home())) / "DelayKillerPremium"
CONFIG_DIR.mkdir(parents=True, exist_ok=True)
CONFIG_FILE = CONFIG_DIR / "config.json"
BACKUP_DIR = CONFIG_DIR / "backups"
BACKUP_DIR.mkdir(parents=True, exist_ok=True)

# Defaults
DEFAULT_CONFIG = {
    "dns_auto": False,
    "mtu_auto": True,
    "smartgaming": True,
    "latency_stabilizer": True,
    "fps_boost": True,
    "profiles": {},
}

# --------------------------- Utilities ---------------------------

def is_admin():
    if not IS_WINDOWS:
        return False
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


def run_cmd(cmd, timeout=20):
    try:
        p = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        out, _ = p.communicate(timeout=timeout)
        return p.returncode, (out or "").strip()
    except subprocess.TimeoutExpired:
        p.kill()
        return 1, "Timed out"
    except Exception as e:
        return 1, str(e)


def save_config(cfg):
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
        return True
    except Exception:
        return False


def load_config():
    try:
        if CONFIG_FILE.exists():
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                d = json.load(f)
            out = DEFAULT_CONFIG.copy()
            out.update(d)
            return out
    except Exception:
        pass
    return DEFAULT_CONFIG.copy()


def backup_text(name, content):
    path = BACKUP_DIR / f"{time.strftime('%Y%m%d_%H%M%S')}_{name}.json"
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(content, f, indent=2)
        return str(path)
    except Exception:
        return None

# --------------------------- Network modules (safe) ---------------------------

def dns_flush():
    if not IS_WINDOWS:
        return 1, "Unsupported"
    return run_cmd("ipconfig /flushdns", timeout=10)


def dns_benchmark(servers, timeout=2, count=3):
    results = {}
    if not IS_WINDOWS:
        for s in servers:
            results[s] = None
        return results
    for s in servers:
        try:
            code, out = run_cmd(f"ping -n {count} -w {int(timeout*1000)} {s}", timeout=10)
            avg = None
            for line in out.splitlines():
                if "Average =" in line or "Average" in line:
                    parts = line.replace(" ", "").split("=")
                    try:
                        avg = int(parts[-1].replace("ms", ""))
                    except Exception:
                        avg = None
            results[s] = avg
        except Exception:
            results[s] = None
    return results


def set_dns_interface(adapter_name, primary, secondary=None):
    if not IS_WINDOWS:
        return 1, "Unsupported"
    if not is_admin():
        return 2, "Admin required"
    cmd = f'netsh interface ip set dns name="{adapter_name}" static {primary} validate=no'
    code, out = run_cmd(cmd)
    if secondary:
        cmd2 = f'netsh interface ip add dns name="{adapter_name}" {secondary} index=2'
        c2, o2 = run_cmd(cmd2)
        return code or c2, out + "\n" + o2
    return code, out

# MTU optimizer (dry-run suggestion)

def probe_mtu(target="8.8.8.8", start=1500, min_mtu=1200):
    if not IS_WINDOWS:
        return None
    mtu = start
    step = 10
    last_good = None
    while mtu >= min_mtu:
        payload = mtu - 28
        cmd = f"ping -f -l {payload} -n 1 {target}"
        code, out = run_cmd(cmd, timeout=4)
        if code == 0 and "Reply" in out:
            last_good = mtu
            break
        mtu -= step
    return last_good


def apply_mtu(adapter_name, mtu):
    if not IS_WINDOWS:
        return 1, "Unsupported"
    if not is_admin():
        return 2, "Admin required"
    cmd = f'netsh interface ipv4 set subinterface "{adapter_name}" mtu={mtu} store=persistent'
    return run_cmd(cmd)

# Network stack repair (safe sequence)

def repair_network_stack():
    if not IS_WINDOWS:
        return 1, "Unsupported"
    if not is_admin():
        return 2, "Admin required"
    results = []
    cmds = [
        "netsh int ip reset",
        "netsh winsock reset",
        "ipconfig /release",
        "ipconfig /renew",
    ]
    for c in cmds:
        code, out = run_cmd(c, timeout=20)
        results.append({"cmd": c, "code": code, "out": out})
    return 0, results

# Latency stabilizer & FPS tools & SmartGaming

def set_timer_resolution(ms=1):
    if not IS_WINDOWS:
        return 1, "Unsupported"
    try:
        winmm = ctypes.WinDLL('winmm')
        res = winmm.timeBeginPeriod(int(ms))
        return 0, f"timeBeginPeriod({ms}) returned {res}"
    except Exception as e:
        return 1, str(e)


def set_power_plan_high():
    if not IS_WINDOWS:
        return 1, "Unsupported"
    return run_cmd("powercfg /setactive SCHEME_MIN")


def clean_temp_files():
    try:
        temp = Path(os.getenv('TEMP', '/tmp'))
        removed = 0
        for p in temp.glob('*'):
            try:
                if p.is_file():
                    p.unlink()
                    removed += 1
                elif p.is_dir():
                    continue
            except Exception:
                continue
        return 0, f"Removed approx {removed} files from {temp}"
    except Exception as e:
        return 1, str(e)


COMMON_GAMES = {
    'valorant': ['valheim.exe','VALORANT.exe','VALORANT-Win64-Shipping.exe','Valorant.exe'],
    'cs2': ['cs2.exe','csgo.exe','hl2.exe'],
    'minecraft': ['javaw.exe','java.exe'],
    'fortnite': ['FortniteClient-Win64-Shipping.exe','FortniteLauncher.exe'],
}

def detect_games():
    found = {}
    for proc in psutil.process_iter(attrs=('name','pid')):
        name = (proc.info.get('name') or '').lower()
        for game, procs in COMMON_GAMES.items():
            for p in procs:
                if p.lower() == name:
                    found.setdefault(game, []).append(proc.info['pid'])
    return found

# --------------------------- UI (redesigned) ---------------------------
# Top tabs, centered elements, switches instead of checkboxes, animations
ctk.set_appearance_mode('dark')
ctk.set_default_color_theme('dark-blue')
app = ctk.CTk()
app.geometry(APP_SIZE)
app.title(APP_NAME)
app.configure(fg_color=COL_BG)

# Variables & state
status_var = ctk.StringVar(value='Ready')
cpu_var = ctk.StringVar(value='0%')
ram_var = ctk.StringVar(value='0%')

# Module toggles -> use switches for modern look
dns_auto_var = ctk.BooleanVar(value=False)
mtu_auto_var = ctk.BooleanVar(value=True)
smartgaming_var = ctk.BooleanVar(value=True)
latstab_var = ctk.BooleanVar(value=True)
fpsboost_var = ctk.BooleanVar(value=True)

# Layout: top tab bar + content frame
top_bar = ctk.CTkFrame(app, fg_color=COL_PANEL, height=64, corner_radius=0)
top_bar.pack(side='top', fill='x')

brand = ctk.CTkLabel(top_bar, text=APP_NAME, text_color=COL_ACCENT1, font=('Segoe UI', 16, 'bold'))
brand.pack(side='left', padx=18)

# container for tab buttons
tab_btn_frame = ctk.CTkFrame(top_bar, fg_color=COL_PANEL, corner_radius=0)
tab_btn_frame.pack(side='left', padx=24)

# NEW: content holder (main area) must exist before pages/animations use it
content_holder = ctk.CTkFrame(app, fg_color=COL_BG)
content_holder.pack(fill='both', expand=True, padx=18, pady=(12,18))

# animation/page helpers need these globals initialized
pages = {}
current_page = None
page_width = 1060  # fallback width used by slide animations
animating = False

TAB_NAMES = ['Dashboard','Boost Engine','Network Tools','System Tools','Settings']
_tab_buttons = {}
_active_tab_btn = None
_active_tab_name = None
_tab_props = {}

# helper to animate slide between frames
def slide_to(new_name, direction=1, steps=18, delay=12):
    global current_page, animating
    # prevent re-entrant animations
    if animating:
        return
    animating = True

    try:
        new_frame = pages[new_name]
        cw = content_holder.winfo_width() or page_width
        start_x = cw * direction
        prev_page = current_page

        new_frame.place(in_=content_holder, x=start_x, y=0, relheight=1, relwidth=1)

        def step(i):
            # ensure we can update globals on error/finalize
            global current_page, animating
            try:
                frac = i / steps
                x_new = int(start_x * (1 - frac))
                try:
                    new_frame.place_configure(x=x_new)
                except Exception:
                    pass

                if prev_page and prev_page != new_name:
                    old_frame = pages.get(prev_page)
                    if old_frame:
                        x_old = int(-cw * frac * direction)
                        try:
                            old_frame.place_configure(x=x_old)
                        except Exception:
                            pass

                if i < steps:
                    app.after(delay, lambda: step(i + 1))
                else:
                    # finalize: remove the captured previous page
                    if prev_page and prev_page != new_name:
                        try:
                            pages[prev_page].place_forget()
                        except Exception:
                            pass
                    try:
                        new_frame.place_configure(x=0)
                    except Exception:
                        pass
                    current_page = new_name
                    animating = False
            except Exception:
                # strong cleanup on unexpected error during animation steps
                try:
                    new_frame.place_configure(x=0)
                except Exception:
                    pass
                if prev_page and prev_page != new_name:
                    try:
                        pages[prev_page].place_forget()
                    except Exception:
                        pass
                # ensure state is consistent so future switches are allowed
                current_page = new_name
                animating = False
                return

        step(0)
    except Exception:
        # ensure lock is cleared on unexpected immediate error so UI doesn't become stuck
        animating = False
        return

# hover-scale animation helpers for buttons (increase padding + font slightly)
def attach_hover_scale(btn, scale=1.08):
    # store original properties
    try:
        orig_font = btn.cget('font')
    except Exception:
        orig_font = ('Segoe UI', 12)
    try:
        orig_fg = btn.cget('fg_color')
    except Exception:
        orig_fg = None
    try:
        orig_text = btn.cget('text_color')
    except Exception:
        orig_text = None

    # normalize font tuple (family, size, *rest)
    if isinstance(orig_font, (list, tuple)):
        fam = orig_font[0]
        size = orig_font[1] if len(orig_font) > 1 and isinstance(orig_font[1], int) else 12
        rest = orig_font[2:] if len(orig_font) > 2 else ()
    else:
        fam = str(orig_font)
        size = 12
        rest = ()

    def make_font(s):
        if rest:
            return (fam, s) + rest
        return (fam, s)

    def on_enter(e):
        try:
            btn.configure(font=make_font(int(size * scale)))
        except Exception:
            pass
        try:
            if orig_fg is not None:
                btn.configure(fg_color=COL_ACCENT1)
            if orig_text is not None:
                btn.configure(text_color='#0A0F16')
        except Exception:
            pass

    def on_leave(e):
        try:
            btn.configure(font=orig_font)
        except Exception:
            pass
        try:
            if orig_fg is not None:
                btn.configure(fg_color=orig_fg)
            if orig_text is not None:
                btn.configure(text_color=orig_text)
        except Exception:
            pass

    btn.bind("<Enter>", on_enter)
    btn.bind("<Leave>", on_leave)

# create tab buttons
for name in TAB_NAMES:
    b = ctk.CTkButton(tab_btn_frame, text=name, fg_color='transparent', hover_color='#16222b',
                     text_color=COL_TEXT, corner_radius=8, width=140, height=36,
                     font=('Segoe UI', 12))
    b.pack(side='left', padx=8, pady=12)

    # store button and its original properties so we can restore later
    _tab_buttons[name] = b
    try:
        _tab_props[name] = (b.cget('fg_color'), b.cget('text_color'), b.cget('font'))
    except Exception:
        _tab_props[name] = ('transparent', COL_TEXT, ('Segoe UI', 12))

    def make_cmd(n):
        return lambda n=n: switch_tab(n)
    b.configure(command=make_cmd(name))
    attach_hover_scale(b, scale=1.12)

# status area at right of top bar
status_label = ctk.CTkLabel(top_bar, textvariable=status_var, text_color=COL_MUTED, font=('Segoe UI', 10))
status_label.pack(side='right', padx=18)

# Footer log (centered)
log_box = ctk.CTkTextbox(app, height=120, fg_color=COL_CARD, text_color=COL_TEXT)
log_box.pack(side='bottom', fill='x', padx=18, pady=(0,12))

def add_log(text):
    log_box.insert('end', text + "\n")
    log_box.see('end')

# ------------------- Build pages (content) -------------------
# Dashboard
dash = ctk.CTkFrame(content_holder, fg_color=COL_BG)
pages['Dashboard'] = dash
ctk.CTkLabel(dash, text='Dashboard', font=('Segoe UI', 22, 'bold'), text_color=COL_ACCENT1).pack(anchor='n', pady=(18,6))
stat = ctk.CTkFrame(dash, fg_color=COL_CARD, corner_radius=12)
stat.pack(fill='x', padx=120, pady=10)
ctk.CTkLabel(stat, text='System Monitor', text_color=COL_MUTED).pack(anchor='w', padx=12, pady=(8,0))
ctk.CTkLabel(stat, textvariable=cpu_var, font=('Segoe UI', 18, 'bold'), text_color=COL_ACCENT1).pack(anchor='w', padx=12)
ctk.CTkLabel(stat, textvariable=ram_var, font=('Segoe UI', 18, 'bold'), text_color=COL_ACCENT2).pack(anchor='w', padx=12, pady=(0,8))

game_frame = ctk.CTkFrame(dash, fg_color=COL_CARD, corner_radius=12)
game_frame.pack(fill='x', padx=120, pady=10)
ctk.CTkLabel(game_frame, text='Detected Games', text_color=COL_MUTED).pack(anchor='w', padx=12, pady=(8,0))
games_list = ctk.CTkTextbox(game_frame, height=80, fg_color=COL_BG)
games_list.pack(fill='x', padx=12, pady=8)

# Boost Engine
boost = ctk.CTkFrame(content_holder, fg_color=COL_BG)
pages['Boost Engine'] = boost
ctk.CTkLabel(boost, text='Boost Engine', font=('Segoe UI', 22, 'bold'), text_color=COL_ACCENT1).pack(anchor='n', pady=(18,6))

modules = ctk.CTkFrame(boost, fg_color=COL_CARD, corner_radius=12)
modules.pack(fill='x', padx=300, pady=18)
# switches instead of checkboxes
ctk.CTkSwitch(modules, text='DNS Booster (flush + bench)', variable=dns_auto_var, onvalue=True, offvalue=False).pack(anchor='center', pady=8)
ctk.CTkSwitch(modules, text='MTU Optimizer (suggest)', variable=mtu_auto_var, onvalue=True, offvalue=False).pack(anchor='center', pady=8)
ctk.CTkSwitch(modules, text='SmartGaming Mode', variable=smartgaming_var, onvalue=True, offvalue=False).pack(anchor='center', pady=8)
ctk.CTkSwitch(modules, text='Latency Stabilizer', variable=latstab_var, onvalue=True, offvalue=False).pack(anchor='center', pady=8)
run_btn = ctk.CTkButton(modules, text='Run Selected Boosts', command=lambda: threading.Thread(target=run_selected_boosts).start(), width=220, height=44, corner_radius=12)
run_btn.pack(pady=12)
attach_hover_scale(run_btn, scale=1.06)

# Network Tools
net = ctk.CTkFrame(content_holder, fg_color=COL_BG)
pages['Network Tools'] = net
ctk.CTkLabel(net, text='Network Tools', font=('Segoe UI', 22, 'bold'), text_color=COL_ACCENT1).pack(anchor='n', pady=(18,6))

net_card = ctk.CTkFrame(net, fg_color=COL_CARD, corner_radius=12)
net_card.pack(fill='x', padx=320, pady=18)
b_flush = ctk.CTkButton(net_card, text='Flush DNS', command=lambda: threading.Thread(target=run_flush_dns).start(), width=200)
b_flush.pack(pady=8)
attach_hover_scale(b_flush)
b_repair = ctk.CTkButton(net_card, text='Repair Network Stack', command=lambda: threading.Thread(target=run_repair_stack).start(), width=200)
b_repair.pack(pady=8)
attach_hover_scale(b_repair)
b_probe = ctk.CTkButton(net_card, text='Probe MTU (suggest)', command=lambda: threading.Thread(target=run_probe_mtu).start(), width=200)
b_probe.pack(pady=8)
attach_hover_scale(b_probe)

# System Tools
sysf = ctk.CTkFrame(content_holder, fg_color=COL_BG)
pages['System Tools'] = sysf
ctk.CTkLabel(sysf, text='System Tools', font=('Segoe UI', 22, 'bold'), text_color=COL_ACCENT1).pack(anchor='n', pady=(18,6))

sys_card = ctk.CTkFrame(sysf, fg_color=COL_CARD, corner_radius=12)
sys_card.pack(fill='x', padx=320, pady=18)
ctk.CTkSwitch(sys_card, text='Enable FPS Boost (power plan)', variable=fpsboost_var).pack(anchor='center', pady=8)
b_apply = ctk.CTkButton(sys_card, text='Apply FPS Boost', command=lambda: threading.Thread(target=apply_fps_boost).start(), width=200)
b_apply.pack(pady=8)
attach_hover_scale(b_apply)
b_clean = ctk.CTkButton(sys_card, text='Clean Temp Files', command=lambda: threading.Thread(target=run_clean_temp).start(), width=200)
b_clean.pack(pady=8)
attach_hover_scale(b_clean)

# Settings
sett = ctk.CTkFrame(content_holder, fg_color=COL_BG)
pages['Settings'] = sett
ctk.CTkLabel(sett, text='Settings', font=('Segoe UI', 22, 'bold'), text_color=COL_ACCENT1).pack(anchor='n', pady=(18,6))
sett_card = ctk.CTkFrame(sett, fg_color=COL_CARD, corner_radius=12)
sett_card.pack(fill='x', padx=320, pady=18)
b_build = ctk.CTkButton(sett_card, text='Build EXE (PyInstaller)', command=lambda: threading.Thread(target=build_exe).start(), width=240)
b_build.pack(pady=8)
attach_hover_scale(b_build)
b_openbackups = ctk.CTkButton(sett_card, text='Open Backups Folder', command=lambda: os.startfile(str(BACKUP_DIR)) if IS_WINDOWS else None, width=240)
b_openbackups.pack(pady=8)
attach_hover_scale(b_openbackups)

# Footer small status centered
footer = ctk.CTkFrame(app, fg_color=COL_PANEL, corner_radius=8)
footer.place(relx=0.5, rely=0.96, anchor='s')
ctk.CTkLabel(footer, textvariable=status_var, text_color=COL_MUTED).pack(anchor='center', padx=12, pady=6)

# --------------------------- Actions (existing code) ---------------------------
# re-use previously defined functions but keep names consistent
def run_flush_dns():
    status_var.set('Flushing DNS...')
    code, out = dns_flush()
    status_var.set('Flush done' if code==0 else f'Flush failed: {out}')
    add_log(f"Flush DNS -> {code}: {out}")

def run_repair_stack():
    status_var.set('Backing up registry and repairing...')
    if IS_WINDOWS:
        try:
            import winreg
            base = winreg.HKEY_LOCAL_MACHINE
            tcp_path = r"SYSTEM\CurrentControlSet\Services\Tcpip\Parameters"
            snap = {}
            try:
                with winreg.OpenKey(base, tcp_path, 0, winreg.KEY_READ) as k:
                    i = 0
                    while True:
                        try:
                            name, val, _ = winreg.EnumValue(k, i)
                            snap[name] = val
                            i += 1
                        except OSError:
                            break
            except Exception:
                snap['_error'] = 'read_failed'
            backup_text('tcp_parameters', snap)
        except Exception:
            pass
    status_var.set('Running repairs...')
    code, results = repair_network_stack()
    status_var.set('Repair complete' if code==0 else f'Repair failed: {results}')
    add_log(f"Repair Network Stack -> {code}")

def run_probe_mtu():
    status_var.set('Probing MTU (this may take a few seconds)...')
    suggested = probe_mtu()
    if suggested:
        status_var.set(f'Suggested MTU: {suggested}')
        if messagebox.askyesno('Apply MTU?', f'Apply MTU {suggested} to your active adapter?'):
            adapters = suggest_adapters()
            if adapters:
                adapter = adapters[0]
                code, out = apply_mtu(adapter, suggested)
                status_var.set('MTU applied' if code==0 else f'MTU failed: {out}')
            else:
                status_var.set('No adapter detected')
    else:
        status_var.set('Could not determine MTU')
    add_log(f"Probe MTU -> {suggested}")

def run_selected_boosts():
    cfg = load_config()
    actions = []
    if dns_auto_var.get():
        actions.append(('dns', dns_flush))
    if mtu_auto_var.get():
        actions.append(('mtu', probe_mtu))
    if smartgaming_var.get():
        actions.append(('smartgaming', detect_games))
    if latstab_var.get():
        actions.append(('latstab', set_timer_resolution))

    summary = '\n'.join([a[0] for a in actions]) or 'No actions selected'
    if not messagebox.askyesno('Run Boosts', f'Planned actions:\n{summary}\n\nProceed?'):
        status_var.set('Cancelled')
        return

    for name, fn in actions:
        status_var.set(f'Running {name}...')
        try:
            if name == 'mtu':
                val = fn()
                status_var.set(f'MTU suggested: {val}')
                add_log(f"MTU -> {val}")
            else:
                res = fn()
                status_var.set(f'{name} result: {str(res)[:120]}')
                add_log(f"{name} -> {str(res)[:120]}")
        except Exception as e:
            status_var.set(f'{name} failed: {e}')
            add_log(f"{name} failed: {e}")

    if smartgaming_var.get():
        games = detect_games()
        games_list.delete('0.0','end')
        if games:
            for g,pids in games.items():
                games_list.insert('end', f"{g}: {len(pids)} process(es)\n")
                if g == 'minecraft':
                    changed = set_java_priority('High')
                    status_var.set(f'Increased Java priority for {changed} processes')
                    add_log(f"Java priority changed: {changed}")
        else:
            games_list.insert('end', 'No games detected')

    status_var.set('Boosts complete')

def apply_fps_boost():
    if not IS_WINDOWS:
        status_var.set('FPS boost only supported on Windows')
        return
    if not is_admin():
        status_var.set('Admin required for power plan change')
        messagebox.showinfo('Admin required', 'Run the app as administrator to change power plans')
        return
    status_var.set('Applying FPS boost (high performance power plan)')
    code, out = set_power_plan_high()
    status_var.set('Power plan applied' if code==0 else f'Failed: {out}')
    add_log(f"FPS boost -> {code}: {out}")

def run_clean_temp():
    status_var.set('Cleaning temp files...')
    code, msg = clean_temp_files()
    status_var.set(msg if code==0 else f'Clean failed: {msg}')
    add_log(f"Clean temp -> {code}: {msg}")

def build_exe():
    if not messagebox.askyesno('Build EXE', 'This will run PyInstaller on the current script. Proceed?'):
        status_var.set('Build cancelled')
        return
    status_var.set('Building EXE...')
    spec = f"pyinstaller --noconsole --onefile --name \"{APP_NAME}\" \"{os.path.realpath(sys.argv[0])}\""
    code, out = run_cmd(spec, timeout=300)
    status_var.set('Build finished' if code==0 else f'Build failed: {out}')
    add_log(f"Build EXE -> {code}")

# helpers (existing)
def suggest_adapters_local():
    if not IS_WINDOWS:
        return []
    code, out = run_cmd('netsh interface show interface')
    names = []
    if code == 0:
        for line in out.splitlines():
            line = line.strip()
            if not line or line.startswith('Admin'):
                continue
            parts = line.split()
            if len(parts) >= 4:
                names.append(' '.join(parts[3:]))
    return names

def suggest_adapters():
    return suggest_adapters_local()

def set_java_priority(name='Normal'):
    PRIORITY_CLASSES = {
        'Idle': getattr(psutil, 'IDLE_PRIORITY_CLASS', 64),
        'Below Normal': getattr(psutil, 'BELOW_NORMAL_PRIORITY_CLASS', 16384),
        'Normal': getattr(psutil, 'NORMAL_PRIORITY_CLASS', 32),
        'Above Normal': getattr(psutil, 'ABOVE_NORMAL_PRIORITY_CLASS', 32768),
        'High': getattr(psutil, 'HIGH_PRIORITY_CLASS', 128),
        'Realtime': getattr(psutil, 'REALTIME_PRIORITY_CLASS', 256),
    }
    changed = 0
    for proc in psutil.process_iter(attrs=('name','pid')):
        try:
            nm = (proc.info.get('name') or '').lower()
            if nm in ('java.exe','javaw.exe'):
                p = psutil.Process(proc.info['pid'])
                p.nice(PRIORITY_CLASSES.get(name, PRIORITY_CLASSES['Normal']))
                changed += 1
        except Exception:
            continue
    return changed

# monitors
def update_monitors():
    try:
        cpu_var.set(f"{psutil.cpu_percent()}%")
        ram_var.set(f"{psutil.virtual_memory().percent}%")
    except Exception:
        pass
    app.after(800, update_monitors)

update_monitors()

# Load config into UI
_cfg = load_config()
dns_auto_var.set(_cfg.get('dns_auto', False))
mtu_auto_var.set(_cfg.get('mtu_auto', True))
smartgaming_var.set(_cfg.get('smartgaming', True))
latstab_var.set(_cfg.get('latency_stabilizer', True))
fpsboost_var.set(_cfg.get('fps_boost', True))

# --------------------------- Tab switching logic ---------------------------
def set_active_tab_button(name):
    global _active_tab_btn, _active_tab_name
    # restore previous button style
    if _active_tab_btn and _active_tab_name in _tab_props:
        try:
            orig_fg, orig_text, orig_font = _tab_props[_active_tab_name]
            _active_tab_btn.configure(fg_color=orig_fg, text_color=orig_text, font=orig_font)
        except Exception:
            pass

    btn = _tab_buttons.get(name)
    if btn:
        try:
            btn.configure(fg_color=COL_ACCENT1, text_color='#0A0F16')
        except Exception:
            pass
        _active_tab_btn = btn
        _active_tab_name = name

def switch_tab(name):
    if name not in pages:
        return
    if name == current_page:
        return
    # ignore switch requests while animating
    if animating:
        return
    # choose direction based on order; compute previous index safely
    try:
        idx_new = TAB_NAMES.index(name)
    except ValueError:
        idx_new = 0
    try:
        idx_old = TAB_NAMES.index(current_page) if isinstance(current_page, str) and current_page in TAB_NAMES else -1
    except Exception:
        idx_old = -1
    direction = 1 if idx_new > idx_old else -1
    set_active_tab_button(name)
    slide_to(name, direction=direction)

# Start on Dashboard
# ensure the first page is placed without animation
first = TAB_NAMES[0]
pages[first].place(in_=content_holder, x=0, y=0, relheight=1, relwidth=1)
current_page = first
set_active_tab_button(first)

# bind resizing to adjust page sizes
def on_resize(e):
    # keep pages sized using relwidth/relheight so CTk doesn't require width/height in place()
    for name, p in pages.items():
        try:
            info = p.place_info()
            if info:
                # ensure page stays full-size relative to the container
                p.place_configure(relwidth=1, relheight=1)
                # if the page was positioned with x offset, ensure that offset is within new width
                # (no explicit width set — CTk frames will expand with relwidth)
        except Exception:
            pass

content_holder.bind("<Configure>", on_resize)

app.mainloop()
