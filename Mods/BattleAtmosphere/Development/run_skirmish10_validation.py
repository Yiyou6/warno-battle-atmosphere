"""Run sequential owned/headless fixtures; never control an existing game."""
from pathlib import Path
import argparse,json,os,shutil,subprocess,sys

DEV=Path(__file__).resolve().parent;ROOT=DEV.parents[2]
BOOT=ROOT/'Mods/BAScriptProbe/AutoloadBoot'

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case',choices=['blackforest','hesse','disabled'])
    args=parser.parse_args()
    probe=subprocess.run(['powershell','-NoProfile','-Command',
        'Get-Process WARNO -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Id'],capture_output=True,text=True)
    assert not probe.stdout.strip(),'Exit WARNO before isolated verification'
    shutil.copy2(DEV/'native_bridge/version.dll',BOOT/'version.dll')
    config=BOOT/'Mods/BattleAtmosphere/Runtime/runtime.ini';previous=config.read_bytes()
    try:
        for name,scenario,enabled in (
            ('blackforest','_2x3_BlackForestStorm_2vs2_CONQ',True),
            ('hesse','_2x2_Hesse_2vs2_DEST',True),
            ('disabled','_2x3_BlackForestStorm_2vs2_CONQ',False)):
            if args.case and args.case!=name:continue
            config.write_text('[Runtime]\nEnabled=%d\n'%enabled,encoding='ascii')
            command=[sys.executable,'-X','utf8',str(DEV/'run_python_probe.py'),
                'skirmish10-'+name+'.json','--stock-data','--autohook','--autoload',
                '--fixture-camps','--activation-gate','--front-fixture','tenvten','--timeout','180',
                '--scenario',scenario]
            with (DEV/('skirmish10-'+name+'-driver.log')).open('w',encoding='utf-8') as output:
                subprocess.run(command,stdout=output,stderr=subprocess.STDOUT,
                    env=dict(os.environ,BA_LOBBY_TEST='1' if enabled else '2'),check=True)
            r=json.loads((DEV/('skirmish10-'+name+'.json')).read_text(encoding='utf-8'))
            print(name,{k:r[k] for k in ('returncode','seconds','timeout')},flush=True)
            assert r['returncode']==0 and not r['timeout'],name
    finally:config.write_bytes(previous)

if __name__=='__main__':main()
