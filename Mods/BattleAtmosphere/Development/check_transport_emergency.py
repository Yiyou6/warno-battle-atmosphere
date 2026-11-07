"""Execute actual unload-now opcode in eight loaded AI pairs; owned child only."""
from pathlib import Path
import hashlib,json,os,shutil,subprocess,sys
DEV=Path(__file__).resolve().parent;ROOT=DEV.parents[2];B=DEV/'native_bridge'
sys.path.insert(0,str(B));from verify_runtime import events
def main():
    target=ROOT/'Mods/BAScriptProbe/AutoloadBoot/version.dll';previous=target.read_bytes()
    dll=B/'transport_emergency_probe.dll';source=B/'transport_emergency_probe.c'
    subprocess.run([str(Path(os.environ['TEMP'])/'codex-warno-compiler/tcc/tcc.exe'),'-shared','-Wall','-DBA_EMBEDDED','-DBA_PROXY','-o',str(dll),str(source),str(B/'version_proxy.c')],check=True)
    try:
        shutil.copy2(dll,target)
        p=subprocess.run([sys.executable,str(DEV/'run_python_probe.py'),'combined-emergency-native.json','--autoload','--stock-data','--autohook','--fixture-camps','--activation-gate','--front-fixture','transport_api','--timeout','150'],capture_output=True)
        if p.returncode:raise RuntimeError(p.stderr.decode('utf-8','replace'))
    finally:target.write_bytes(previous)
    path=DEV/'combined-emergency-native.json';r=json.loads(path.read_text());out=r['stdout']
    orders=events(out,'EMERGENCY_NATIVE_ORDER');states=events(out,'EMERGENCY_NATIVE_STATE')
    assert r['returncode']==0 and not r['timeout'] and not r['stderr'].strip()
    assert len(orders)==8 and all(result==1 for uid,result in orders)
    assert states[-1][1:]==(8,[])
    assert any(20<s[0]<=30 and s[1:]==(8,[]) for s in states),'No prompt unloading while leases suppress native strategic AI'
    assert 'REJECT' not in out and 'ERROR' not in out
    r['diagnostic_source_sha256']=hashlib.sha256(source.read_bytes()).hexdigest()
    path.write_text(json.dumps(r,indent=2));print('PASS 8 native unload-now commands; all eight carriers empty')
if __name__=='__main__':main()
