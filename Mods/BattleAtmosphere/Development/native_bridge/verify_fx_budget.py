"""Exact binary smoke-budget integration, preserving the preview.6 AI source.

Historical AI tests describe the prior DLL. This bounded check verifies the
unchanged AI code and a fresh native start/move/stop on the new DLL; it does not
claim the entire historical AI suite was rerun or that GPU visuals were tested.
"""
from pathlib import Path
import hashlib,json,re,zipfile

BASE=Path(__file__).resolve().parent
DEV=BASE.parent;MOD=DEV.parent;ROOT=MOD.parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def verify_fx_budget(installed=False):
    manifest=json.loads((MOD/'Runtime/build-manifest.json').read_text())
    assert sha(BASE/'version.dll')==manifest['dll_sha256']
    assert sha(ROOT/'WARNO.exe')==manifest['exe_sha256']
    for name,digest in manifest['source_sha256'].items():assert sha(ROOT/name)==digest,name
    with zipfile.ZipFile(DEV/'archive/smoke-preview8-before.zip') as z:
        old=json.loads(z.read('runtime/build-manifest.json'))
        for name,digest in old['source_sha256'].items():
            if name.endswith('probe_bridge.c'):continue
            assert sha(ROOT/name)==digest,('AI/build source changed',name)
        previous=z.read('native_bridge/probe_bridge.c').decode().replace('\r\n','\n')
        current=(BASE/'probe_bridge.c').read_text()
        current=current.replace('#include "fx_budget.h"\n\n','')
        current=current.replace('#ifdef BA_PROXY\n    if (!fx_budget_install()) log_line("FX_BUDGET_HOOK_REFUSED");\n#endif\n','')
        assert current==previous,'Unexpected change outside VFX hook'
    r=json.loads((DEV/'runtime-vfx-budget.json').read_text());out=r['stdout']
    assert r['returncode']==0 and not r['timeout'] and not r['stderr'].strip()
    assert r['autoload_sha256']==manifest['dll_sha256']
    assert r['activation_gate'] and r['bridge'] is None
    assert r['auxiliary_sha256'][str((BASE/'fx_budget.h').relative_to(ROOT))]==sha(BASE/'fx_budget.h')
    for marker in ('FX_BUDGET_APPLIED original=80000 max_particles=320000 quality_scaled=1 telemetry=1',
                   'AUTO_PYTHON_STARTED','AUTOMATIC_SKIRMISH_STOP','SPACE_ORDER','SPACE_REVISION combined-front-preview.6'):
        assert marker in out,marker
    assert not re.search('ERROR|Traceback|REFUSE|REJECT',out)
    status=re.findall(r'FX_BUDGET_STATUS particles=(\d+) effective_limit=(\d+) max_particles=320000',out)
    assert status and all(160000<=int(limit)<=320000 for count,limit in status)
    if installed:assert sha(ROOT/'version.dll')==manifest['dll_sha256']
    return dict(status='native-budget-and-AI-start-move-stop-passed; rendered-effect-unverified',
                dll_sha256=manifest['dll_sha256'],exe_sha256=manifest['exe_sha256'],
                native_receipt_sha256=sha(DEV/'runtime-vfx-budget.json'),ai_source_unchanged=True,
                particle_budget_multiplier=4,max_particles=320000,effective_limit=int(status[-1][1]),
                particle_counts_observed=[int(n) for n,_ in status],historical_full_AI_suite_rerun=False)

if __name__=='__main__':print(json.dumps(verify_fx_budget(),indent=2))
