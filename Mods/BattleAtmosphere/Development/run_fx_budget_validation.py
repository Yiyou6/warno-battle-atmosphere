"""Run the exact candidate in the isolated existing headless fixture."""
from pathlib import Path
import subprocess,sys
DEV=Path(__file__).resolve().parent;ROOT=DEV.parents[2]
BOOT=ROOT/'Mods/BAScriptProbe/AutoloadBoot'
running=subprocess.run(['powershell','-NoProfile','-Command','Get-Process WARNO -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Id'],capture_output=True,text=True)
assert not running.stdout.strip(),'A game is running; no child started'
previous=(BOOT/'version.dll').read_bytes()
try:
    (BOOT/'version.dll').write_bytes((DEV/'native_bridge/version.dll').read_bytes())
    subprocess.run([sys.executable,str(DEV/'run_python_probe.py'),'runtime-vfx-budget.json',
                    '--autoload','--stock-data','--autohook','--fixture-camps','--activation-gate',
                    '--timeout','100'],cwd=ROOT,check=True,stdout=subprocess.DEVNULL)
finally:
    (BOOT/'version.dll').write_bytes(previous)
subprocess.run([sys.executable,str(DEV/'native_bridge/verify_fx_budget.py')],check=True)
