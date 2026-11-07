"""Sequential owned headless regressions; no GUI and no user-process termination."""
from pathlib import Path
import hashlib,json,shutil,subprocess,sys
DEV=Path(__file__).resolve().parent;ROOT=DEV.parents[2]
def run(args):
    p=subprocess.run([sys.executable]+[str(x) for x in args],cwd=ROOT,capture_output=True,text=True,encoding='utf-8',errors='replace')
    if p.returncode:raise RuntimeError(p.stdout[-3000:]+p.stderr[-3000:])
    return p
def main():
    resume='--resume' in sys.argv
    if not resume:run([DEV/'native_bridge/build_runtime.py'])
    sys.path.insert(0,str(DEV/'native_bridge'))
    from verify_runtime import sha,stderr_ok
    manifest=json.loads((ROOT/'Mods/BattleAtmosphere/Runtime/build-manifest.json').read_text())
    assert sha(DEV/'native_bridge/version.dll')==manifest['dll_sha256']
    for source,digest in manifest['source_sha256'].items():assert sha(ROOT/source)==digest
    shutil.copy2(DEV/'native_bridge/version.dll',ROOT/'Mods/BAScriptProbe/AutoloadBoot/version.dll')
    p=run(['-m','unittest','discover','-s',DEV/'dispersion','-p','test_*.py'])
    sources=list((ROOT/'Mods/BattleAtmosphere/Runtime/Python').glob('*.py'))+list((DEV/'dispersion').glob('*.py'))
    (DEV/'continuous-offline-validation.json').write_text(json.dumps(dict(returncode=p.returncode,stdout=p.stdout,stderr=p.stderr,
        source_sha256={str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest() for f in sources}),indent=2))
    cases=[('combined-release-transport.json','transport','_2x3_BlackForestStorm_2vs2_CONQ',290),
           ('widefront-release-mass.json','mass','_2x3_BlackForestStorm_2vs2_CONQ',290),
           ('widefront-release-battle.json','battle','_2x2_Hesse_2vs2_DEST',290),
           ('runtime-auto-release-blackforest.json',None,'_2x3_BlackForestStorm_2vs2_CONQ',100),
           ('runtime-auto-release-hesse.json',None,'_2x2_Hesse_2vs2_DEST',100)]
    for name,mode,scenario,timeout in cases:
        existing=DEV/name
        if resume and existing.exists():
            prior=json.loads(existing.read_text())
            matched=all((prior['source_sha256'] if source.endswith('ba_autorun.py') else prior['auxiliary_sha256'].get(source))==digest for source,digest in manifest['source_sha256'].items())
            if prior['autoload_sha256']==manifest['dll_sha256'] and matched and prior['returncode']==0 and not prior['timeout'] and stderr_ok(prior) and prior['front_fixture']==mode:
                print('REUSE exact-binary completed case',name,flush=True);continue
        print('START',name,flush=True)
        args=[DEV/'run_python_probe.py',name,'--autoload','--stock-data','--autohook','--fixture-camps','--activation-gate','--scenario',scenario,'--timeout',timeout]
        if mode:args+=['--front-fixture',mode]
        run(args);r=json.loads((DEV/name).read_text())
        assert r['returncode']==0 and not r['timeout'] and stderr_ok(r),name
        print('EXIT OK',name,r['seconds'],flush=True)
    print('START cold registration',flush=True);print(run([DEV/'check_cold_start.py']).stdout,flush=True)
    print('START native immediate unload',flush=True);print(run([DEV/'check_transport_emergency.py']).stdout,flush=True)
    print('START swapped physical-side regressions',flush=True);print(run([DEV/'check_direction_runtime.py']).stdout,flush=True)
    print(run([DEV/'native_bridge/verify_runtime.py']).stdout,flush=True)
if __name__=='__main__':main()
