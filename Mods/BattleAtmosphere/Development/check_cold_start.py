"""Regression: remove fixture preregistration before the production startup.

Uses a new bounded headless child and a diagnostic DLL in AutoloadBoot only.
The user must close WARNO first; the game allows only one running instance.
"""
from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess
import sys

DEV=Path(__file__).resolve().parent
ROOT=DEV.parents[2]
BRIDGE=DEV/'native_bridge'
BOOT=ROOT/'Mods/BAScriptProbe/AutoloadBoot'
target=BOOT/'version.dll'
previous=target.read_bytes()
tcc=Path(os.environ['TEMP'])/'codex-warno-compiler/tcc/tcc.exe'
diagnostic=BRIDGE/'cold_start_probe.dll'
receipt=DEV/'runtime-native-cold-start.json'
subprocess.run([str(tcc),'-shared','-Wall','-DBA_EMBEDDED','-DBA_PROXY',
                '-o',str(diagnostic),str(BRIDGE/'cold_start_probe.c'),
                str(BRIDGE/'version_proxy.c')],check=True)
try:
    shutil.copy2(diagnostic,target)
    # The wrapper calls the very same automatic_start compiled into production.
    # Native lobby provisioning is retained; sys.modules and module_ready are
    # cleared for _ba_native before the production startup is invoked.
    proc=subprocess.run([sys.executable,str(DEV/'run_python_probe.py'),receipt.name,
                         '--scenario','_2x2_Hesse_1vs1_CONQ_DUEL','--autoload',
                         '--stock-data','--autohook','--fixture-camps',
                         '--activation-gate','--timeout','85'],
                        stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    if proc.returncode:
        raise RuntimeError(proc.stderr.decode('utf-8','replace'))
finally:
    target.write_bytes(previous)
data=json.loads(receipt.read_text())
assert data['autoload_sha256']==hashlib.sha256(diagnostic.read_bytes()).hexdigest()
output=data['stdout']
prefix,separator,tail=output.partition('COLD_START_NO_NATIVE_MODULE')
valid=(data['returncode']==0 and not data['timeout'] and bool(separator)
       and tail.count('MODULE_REGISTERED')==1 and 'AUTO_PYTHON_STARTED' in tail
       and 'AUTOMATIC_SKIRMISH_STOP' in tail and 'SPACE_STATUS (80,' in tail
       and 'SPACE_ORDER' in tail and 'ERROR' not in tail
       and not data['stderr'].strip())
if valid:
    valid=tail.index('MODULE_REGISTERED')<tail.index('ba_allocator')<tail.index('ba_space')<tail.index('AUTO_PYTHON_STARTED')
print(json.dumps(dict(passed=valid,exit_code=data['returncode'],timeout=data['timeout'],
                     seconds=data['seconds'],receipt=str(receipt)),indent=2))
if not valid:
    print(output)
    print(data['stderr'])
raise SystemExit(0 if valid else 1)
