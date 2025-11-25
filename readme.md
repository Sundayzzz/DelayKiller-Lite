# DelayKiller V2 (DelayKiller Premium)

Short description
A small Windows-focused network/latency utility GUI written in Python. It bundles a PyInstaller build in `build/DelayKiller Premium/`. This repository contains the source UI script [b.py](b.py) and packaging spec [DelayKiller Premium.spec](DelayKiller Premium.spec).

Motive
This project was created as an educational test using AI assistance. It's fully open source and provided for learning, experimentation and improvement.

How it works (high level)
- The GUI and main logic live in [b.py](b.py).
- UI toggles and variables like [`dns_auto_var`](b.py), [`mtu_auto_var`](b.py), [`smartgaming_var`](b.py) and [`latstab_var`](b.py) control which actions run.
- The "Run Boosts" workflow is implemented in the [`run_selected_boosts`](b.py) function: it collects selected actions (DNS flush, MTU probe, game detection, timer resolution tweak), asks for confirmation, and executes them in sequence while updating [`status_var`](b.py) and logs.
- A PyInstaller spec is included: [DelayKiller Premium.spec](DelayKiller Premium.spec). The packaged output lives under [build/DelayKiller Premium/](build/DelayKiller Premium/), including the embedded archive [build/DelayKiller Premium/PYZ-00.pyz](build/DelayKiller Premium/PYZ-00.pyz) and cross-reference HTML [build/DelayKiller Premium/xref-DelayKiller Premium.html](build/DelayKiller Premium/xref-DelayKiller Premium.html).

Files to know
- Source/UI: [b.py](b.py) — main GUI and logic (see `run_selected_boosts`).
- Packaging: [DelayKiller Premium.spec](DelayKiller Premium.spec) — PyInstaller spec producing the bundled exe.
- Build artifacts: [build/DelayKiller Premium/PYZ-00.pyz](build/DelayKiller Premium/PYZ-00.pyz) and [build/DelayKiller Premium/xref-DelayKiller Premium.html](build/DelayKiller Premium/xref-DelayKiller Premium.html).
- Dependencies: [requirements.txt](requirements.txt)

Quick start (run from source)
1. Create a virtualenv and install deps:
```sh
python -m venv .venv
source .venv/Scripts/activate      # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r [requirements.txt](http://_vscodecontentref_/0)