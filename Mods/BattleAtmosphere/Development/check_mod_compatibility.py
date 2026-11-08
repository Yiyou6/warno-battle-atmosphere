"""Read native mod compatibility in a new headless child, never a user session."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import re
import subprocess
import time

ROOT=Path(__file__).resolve().parents[3]
DEV=Path(__file__).resolve().parent
BRIDGE=DEV/'native_bridge'
BOOT=ROOT/'Mods/BAScriptProbe/AutoloadBoot'
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--label',default='audit',choices=['audit','collision-before','collision-after','repeat','fixture-after','smoke21'])
args=parser.parse_args()
running=subprocess.run(['powershell','-NoProfile','-Command',
    'Get-Process WARNO -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Id'],
    capture_output=True,text=True)
if running.stdout.strip():raise RuntimeError('WARNO is running; no diagnostic started')
assert hashlib.sha256((BOOT/'WARNO.exe').read_bytes()).hexdigest()=='70f34d844ebf23eea92d535fad0fffb6e0bc60dd1f64cc80c2b903d06abab3a8'
tcc=Path(os.environ['TEMP'])/'codex-warno-compiler/tcc/tcc.exe'
previous_dll=(BOOT/'version.dll').read_bytes()
fixture_config=BOOT/'BattleAtmosphereProbeAutoFixture.ini'
previous_config=fixture_config.read_bytes() if fixture_config.exists() else None
try:
    subprocess.run([str(tcc),'-shared','-Wall','-DBA_EMBEDDED','-DBA_PROXY','-o',str(BOOT/'version.dll'),
                    str(BRIDGE/'mod_compat_probe.c'),str(BRIDGE/'version_proxy.c')],check=True)
    (BOOT/'ModRevisionList.ini').write_bytes((ROOT/'ModRevisionList.ini').read_bytes())
    fixture_config.write_bytes((Path.home()/'Saved Games/EugenSystems/WARNO/Option.ini').read_bytes())
    cmd=[str(BOOT/'WARNO.exe'),'-headless','-nodialogbox','-nocrashrpt','-c',str(fixture_config),
         '-noautologin','-ignorecloudfiles','-scenarioname','_2x3_BlackForestStorm_2vs2_CONQ',
         '-quitwhenmaploaded','-ialevel','3']
    # The private config filename opts into the bridge's empty-lobby fixture.
    # -config is documented by this exact executable's --help output.
    # Keep the real Saved Games mod inventory; no --local-path or -noMod.
    env=os.environ.copy()
    env['BA_VALIDATE_ACTIVATION']='1'
    start=time.monotonic()
    p=subprocess.Popen(cmd,cwd=BOOT,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=env)
    timeout=False
    try:out,err=p.communicate(timeout=85)
    except subprocess.TimeoutExpired:
        timeout=True;p.kill();out,err=p.communicate()
    result=dict(command=cmd,returncode=p.returncode,timeout=timeout,seconds=round(time.monotonic()-start,3),
                stdout=out.decode('utf-8','replace'),stderr=err.decode('utf-8','replace'),
                diagnostic_dll_sha256=hashlib.sha256((BOOT/'version.dll').read_bytes()).hexdigest(),
                diagnostic_source_sha256=hashlib.sha256((BRIDGE/'mod_compat_probe.c').read_bytes()).hexdigest())
finally:
    (BOOT/'version.dll').write_bytes(previous_dll)
    if previous_config is None:
        fixture_config.unlink(missing_ok=True)
    else:
        fixture_config.write_bytes(previous_config)
(DEV/('mod-compatibility-'+args.label+'.json')).write_text(json.dumps(result,indent=2)+'\n')
statuses=re.findall(r'MOD_AUDIT_ROOM selected=([^\s]*) native_status=(\d+)',result['stdout'])
valid=(result['returncode']==0 and not result['timeout'] and statuses==[('0/3','0')]
       and 'AUTO_PYTHON_STARTED' in result['stdout']
       and 'AUTOMATIC_SKIRMISH_STOP' in result['stdout'])
print(json.dumps(dict(returncode=result['returncode'],timeout=result['timeout'],
                     seconds=result['seconds'],room_checks=statuses,passed=valid,
                     receipt=str(DEV/('mod-compatibility-'+args.label+'.json'))),indent=2))
raise SystemExit(0 if valid else 1)
