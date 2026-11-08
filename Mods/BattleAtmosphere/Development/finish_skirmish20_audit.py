"""Sequential owned regressions and verified installation; never stop user games."""
import json
import os
from pathlib import Path
import subprocess
import sys
import zipfile

DEV=Path(__file__).resolve().parent
ROOT=DEV.parents[2]
NATIVE=DEV/'native_bridge'

def idle():
    r=subprocess.run(['powershell','-NoProfile','-Command',
                      'Get-Process WARNO -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Id'],
                     capture_output=True,text=True)
    if r.stdout.strip():raise RuntimeError('WARNO is running; no user process will be stopped')

def run(name,script,*args,env=None):
    with (DEV/(name+'-driver.log')).open('w',encoding='utf-8') as output:
        subprocess.run([sys.executable,'-X','utf8',str(script)]+list(args),cwd=ROOT,
                       stdout=output,stderr=subprocess.STDOUT,env=env,check=True)
    print(name+' complete',flush=True)

def main():
    idle()
    # Preserve the intermediate candidate's results rather than presenting
    # them as evidence for the final build with atomic transport leases.
    archive=DEV/'archive/skirmish10.3-intermediate-9f82acb2.zip'
    if not archive.exists():
        with zipfile.ZipFile(archive,'x',zipfile.ZIP_DEFLATED) as z:
            paths=[NATIVE/'version.dll',DEV.parent/'Runtime/build-manifest.json']
            paths += [DEV/('skirmish10-'+n+'.json') for n in ('blackforest','hesse','disabled')]
            paths += [DEV/'skirmish20-transport.json']
            for p in paths:z.write(p,p.relative_to(ROOT).as_posix())
    run('skirmish20-final-build',NATIVE/'build_runtime.py')
    run('skirmish20-capacity',NATIVE/'run_capacity_harness.py','skirmish20-capacity-after.json')
    run('skirmish20-final-matrix',DEV/'run_skirmish10_validation.py')
    idle()
    run('skirmish20-transport',DEV/'run_python_probe.py','skirmish20-transport.json',
        '--stock-data','--autohook','--autoload','--fixture-camps','--activation-gate',
        '--front-fixture','transport','--timeout','330','--scenario','_2x3_BlackForestStorm_2vs2_CONQ',
        env=dict(os.environ,BA_LOBBY_TEST='1'))
    run('skirmish20-preinstall',NATIVE/'verify_runtime.py')
    idle()
    run('skirmish20-install',NATIVE/'install_runtime.py')
    run('skirmish10-installed',DEV/'run_python_probe.py','skirmish10-installed.json',
        '--stock-data','--autohook','--fixture-camps','--activation-gate','--installed-runtime',
        '--timeout','100','--scenario','_2x3_BlackForestStorm_2vs2_CONQ',
        env=dict(os.environ,BA_LOBBY_TEST='1'))
    run('skirmish20-postinstall',NATIVE/'verify_runtime.py','--installed')
    validation=json.loads((DEV.parent/'Runtime/validation.json').read_text(encoding='utf-8'))
    print(json.dumps({'status':'installed-and-native-verified',
                      'dll_sha256':validation['dll_sha256'],
                      'tests':list(validation['tests'])}),flush=True)

if __name__=='__main__':main()
