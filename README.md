# DelayKiller Lite — Safe Optimizer

DelayKiller Lite is a small Windows GUI tool that applies reversible, Microsoft-supported networking and power tweaks to reduce latency for interactive applications. The app is intentionally conservative and includes best-effort backup/restore logic.

Purpose
- Provide safe, easy-to-use performance tweaks (TCP, DNS, power) for Windows.
- Make changes reversible and logged.
- Educational project: built to learn AI-assisted development and Python GUI tooling.

Key features
- Low-latency mode (CTCP + timestamps toggle)
- DNS Performance Mode (set Google DNS for selected interface)
- Switch to High Performance power plan
- Backup and restore of TCP/DNS/power settings (best-effort)
- Simple, single-file implementation using customtkinter and Pillow

Requirements
- Windows 10/11 (tool uses netsh, powercfg, ipconfig)
- Python 3.8+
- Dependencies:
  - pillow
  - customtkinter

Quick start (developer)
1. Create and activate a Python virtualenv:
   ```sh
   python -m venv .venv
   .venv\Scripts\activate
   ```
2. Install dependencies:
   ```sh
   pip install pillow customtkinter
   ```
3. Run:
   ```sh
   python "DelayKillerLite.py"
   ```
4. Run the program as Administrator for changes to apply. The app will attempt to elevate on startup.

Usage (end user)
- Toggle the options (Low Latency, DNS, Power) and select the target network interface.
- Click "Apply Optimizations" to apply the selected changes.
- Use "Reset Settings" to restore from the app's backup or apply safe defaults.

Safety notes
- The application attempts best-effort backups to revert changes. Keep that backup file safe:
  - Backup path: `%APPDATA%\DelayKillerLite\config\backup.json`
- The app will attempt to elevate to Admin on Windows; run as Administrator if elevation fails.
- Use only on systems you control; network/power changes can affect connectivity.

Contributing
- This project is Open-Source and welcome to contributions. Keep changes explicit and tested on Windows.

License
- See LICENSE (MIT).

Made with AI for my personal education and learning of AI and Coding. Open-Source and made to be easy-to-use.
