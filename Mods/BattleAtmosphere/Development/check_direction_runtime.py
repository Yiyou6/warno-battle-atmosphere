"""Owned native side-swap regressions; no UI or user-process attachment."""
import json,subprocess,sys
from pathlib import Path
DEV=Path(__file__).resolve().parent
CASES=[('direction-urban-swapped.json','swapped','_3x3_UrbanFrontlines_10vs10_CONQ',100),
       ('direction-hesse-swapped.json','swapped','_2x2_Hesse_2vs2_DEST',100),
       ('direction-transport-swapped.json','transport_swapped','_2x3_BlackForestStorm_2vs2_CONQ',290)]
def main():
    for name,mode,scenario,timeout in CASES:
        print('START',name,flush=True)
        p=subprocess.run([sys.executable,str(DEV/'run_python_probe.py'),name,'--autoload','--stock-data','--autohook','--fixture-camps','--activation-gate','--front-fixture',mode,'--scenario',scenario,'--timeout',str(timeout)],capture_output=True,text=True,encoding='utf-8',errors='replace')
        if p.returncode:raise RuntimeError(p.stdout[-2000:]+p.stderr[-2000:])
        r=json.loads((DEV/name).read_text());assert r['returncode']==0 and not r['timeout'] and not r['stderr'].strip(),name
        print('EXIT OK',name,r['seconds'],flush=True)
    sys.path.insert(0,str(DEV/'native_bridge'))
    from verify_runtime import verify_orientation
    m=json.loads((DEV.parent/'Runtime/build-manifest.json').read_text())
    print(json.dumps(verify_orientation(m),indent=2),flush=True)
if __name__=='__main__':main()
