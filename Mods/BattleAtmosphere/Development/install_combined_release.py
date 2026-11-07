"""Install verified combined candidate and record exact local artifacts."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,subprocess,sys,zipfile
DEV=Path(__file__).resolve().parent;MOD=DEV.parent;ROOT=MOD.parents[1]
sys.path.insert(0,str(DEV/'native_bridge'))
from verify_runtime import verify,sha,check_local_mod_identity
def main():
    validated=verify()
    build=json.loads((DEV/'combined-ndf-build.json').read_text())
    assert sha(MOD/'Gen/NDF/GFX/Skirmish.ndfbin')==build['compiled']['file_sha256']
    for name,h in build['sources'].items():assert sha(MOD/name)==h
    saved=Path.home()/'Saved Games/EugenSystems/WARNO/mod/BattleAtmosphere'
    before=check_local_mod_identity();assert before['mod']['version']==3
    activation=saved.parent/'Config.ini';active_before=activation.read_bytes()
    subprocess.run([sys.executable,str(ROOT/'Mods/Utils/Scripts/CopyModGenData.py'),'WARNO','BattleAtmosphere'],cwd=MOD,check=True)
    assert sha(saved/'Gen/NDF/GFX/Skirmish.ndfbin')==build['compiled']['file_sha256']
    subprocess.run([sys.executable,str(DEV/'native_bridge/install_runtime.py')],cwd=ROOT,check=True)
    assert activation.read_bytes()==active_before
    outputs={str(ROOT/'version.dll'):sha(ROOT/'version.dll'),str(saved/'Config.ini'):sha(saved/'Config.ini')}
    for p in (saved/'Gen').rglob('*'):
        if p.is_file() and p.suffix!='.tag':outputs[str(p)]=sha(p)
    receipt=dict(version='combined-arms-preview.5',status='installed-native-regressions-passed-ordinary-battle-pending',
        installed_at=datetime.now(timezone.utc).isoformat(),runtime=validated,ndf=build,outputs=outputs,
        config_version=3,deck_format_version=1,income_settings_changed=False,
        baseline='Development/archive/accepted-preview4-20261106',
        limitations=['Role-based native procurement correction, not live funds/inventory allocator.',
                    'No ordinary-battle acceptance yet; no claim of full encirclement or new artillery order controller.'])
    (DEV/'combined-release.json').write_text(json.dumps(receipt,indent=2))
    print('INSTALLED',receipt['version'],outputs[str(ROOT/'version.dll')])
if __name__=='__main__':main()
