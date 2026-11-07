"""Install the direction fix after exact-binary native regressions; no UI."""
from pathlib import Path
from datetime import datetime,timezone
import json,subprocess,sys,zipfile
DEV=Path(__file__).resolve().parent;ROOT=DEV.parents[2];RUNTIME=DEV.parent/'Runtime'
sys.path.insert(0,str(DEV/'native_bridge'))
from verify_runtime import verify,sha,check_local_mod_identity

def main():
    active=subprocess.run(['powershell','-NoProfile','-Command',"Get-Process WARNO -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Id"],capture_output=True,text=True)
    if active.stdout.strip():raise RuntimeError('WARNO is still running; installation has not started')
    tested=verify();assert tested['orientation_tests']
    saved=Path.home()/'Saved Games/EugenSystems/WARNO/mod/BattleAtmosphere'
    installed_ndf=saved/'Gen/NDF/GFX/Skirmish.ndfbin'
    before=sha(installed_ndf);check_local_mod_identity()
    old_receipt=DEV/'combined-release.json'
    historical=DEV/'archive/combined-release-preview5-before-direction-fix.json'
    if not historical.exists():historical.write_bytes(old_receipt.read_bytes())
    subprocess.run([sys.executable,str(DEV/'native_bridge/install_runtime.py')],cwd=ROOT,check=True)
    subprocess.run([sys.executable,str(DEV/'run_python_probe.py'),'runtime-installed-root.json',
        '--installed-runtime','--stock-data','--autohook','--fixture-camps','--activation-gate',
        '--scenario','_2x3_BlackForestStorm_2vs2_CONQ','--timeout','100'],cwd=ROOT,check=True,capture_output=True)
    validated=verify(include_installed=True)
    assert sha(installed_ndf)==before,'Unexpected procurement change'
    (RUNTIME/'validation.json').write_text(json.dumps(validated,indent=2)+'\n')
    installation=json.loads((RUNTIME/'installation.json').read_text())
    installation['post_install_validation']=validated['tests'][-1]
    (RUNTIME/'installation.json').write_text(json.dumps(installation,indent=2)+'\n')
    receipt=dict(version='combined-arms-preview.6',status='installed; native direction regressions passed; ordinary battle pending',
        installed_at=datetime.now(timezone.utc).isoformat(),runtime=validated,ndf_sha256_unchanged=before,
        root_dll_sha256=sha(ROOT/'version.dll'),failure_evidence_sha256=sha(DEV/'direction-regression-evidence.json'),
        previous_backup='archive/preview5-before-direction-fix.zip',income_changed=False)
    (DEV/'direction-release.json').write_text(json.dumps(receipt,indent=2)+'\n')
    old=json.loads(old_receipt.read_text());old['status']='historical-preview.5; ordinary-battle-direction-regression-confirmed; superseded-by-preview.6'
    old['superseded_by']='direction-release.json';old_receipt.write_text(json.dumps(old,indent=2)+'\n')
    print('INSTALLED',receipt['version'],receipt['root_dll_sha256'])

if __name__=='__main__':main()
