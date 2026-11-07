"""Compare the entire compiled GameFx graph against preview.7.

Only a 3x expression on reviewed visual dimensions may differ. All other
properties, including fire-source duration, counts, damage-related parameters,
sounds, persistent smoke calls and camera shake must remain identical.
"""
from functools import lru_cache
import json
import hashlib
import math
import zipfile
from read_cndf import Cndf
from verify_smoke_profile import paths
from apply_smoke_profile import DEV,MOD,BACKUP
from explosion_scale import SIZES,PERSISTENT,VISUAL_SCALE

def verify_explosions(current):
    with zipfile.ZipFile(DEV/BACKUP) as z:
        installed=json.loads(z.read('development/smoke-release.json'))
        assert installed['version']=='smoke-preview.14'
        assert installed['explosions']['visual_scale']==2
        assert hashlib.sha256(z.read('installed/Gen/NDF/GFX/GameFx.ndfbin')).hexdigest()==installed['outputs']['Gen/NDF/GFX/GameFx.ndfbin']
    assert VISUAL_SCALE==3 and VISUAL_SCALE/installed['explosions']['visual_scale']==1.5
    with zipfile.ZipFile(DEV/'archive/smoke-preview8-before.zip') as z:
        previous=Cndf(z.read('installed/Gen/NDF/GFX/GameFx.ndfbin'))
        assert json.loads(z.read('development/smoke-release.json'))['version']=='smoke-preview.7'
    old_import={i:p for p,i in paths(previous,'IMPR').items()}
    new_import={i:p for p,i in paths(current,'IMPR').items()}
    def fingerprint(c,imports):
        @lru_cache(None)
        def node(i):
            o=c.objects[i];return (o['class'],value(o['properties']))
        def value(v):
            if isinstance(v,dict):
                if 'ref' in v:return node(v['ref'])
                if 'import_index' in v:return ('import',imports[v['import_index']])
                return tuple((k,value(x)) for k,x in sorted(v.items()))
            if isinstance(v,list):return tuple(value(x) for x in v)
            return v
        return value
    oldvalue=fingerprint(previous,old_import);newvalue=fingerprint(current,new_import)
    changed=set();affected={}
    def scaled(a,b):
        n=current.objects[b['ref']];p=n['properties']
        if n['class']=='TIntrinsicCall_2Param':
            return (newvalue(p['Intrinsic'])==('import','$/System/EvaluableIntrinsics/IntrinsicOperatorMul')
                    and current.objects[p['Param0']['ref']]['properties'].get('Value')==VISUAL_SCALE
                    and newvalue(p['Param1'])==oldvalue(a))
        o=previous.objects[a['ref']]
        if n['class']==o['class'] and n['class'] in ('TConstantInteger','TConstantFloat'):
            return math.isclose(p.get('Value',0),VISUAL_SCALE*o['properties'].get('Value',0),rel_tol=1e-6)
        if n['class']==o['class']=='TConstantFloat3':
            return all(math.isclose(y,VISUAL_SCALE*x,rel_tol=1e-6,abs_tol=1e-6) for x,y in
                       zip(o['properties'].get('Value',[0,0,0]),p.get('Value',[0,0,0])))
        return False
    @lru_cache(None)
    def compare_node(i,j):
        a,b=previous.objects[i],current.objects[j]
        assert a['class']==b['class'],(a['class'],b['class'])
        p,q=a['properties'],b['properties'];assert p.keys()==q.keys()
        count=0
        for k in p:
            if a['class']=='TActionCall' and k=='NamedParams':
                left,right=dict(p[k]['map']),dict(q[k]['map']);assert left.keys()==right.keys()
                for name in left:
                    if oldvalue(left[name])==newvalue(right[name]):continue
                    action=oldvalue(p['Action'])
                    bank=action[1].rsplit('/',1)[-1] if action[0]=='import' else ''
                    # Handmade local bank calls are verified by the unchanged
                    # Action graph below; all modifications still require 3x.
                    assert name in SIZES and bank not in PERSISTENT,(name,bank)
                    assert not bank.startswith(('SFX','Shake','Destroy','Dummy','Propulsion','FX_BANK_')),bank
                    assert scaled(left[name],right[name]),('Not exactly 3x',name,bank)
                    changed.add((j,name));count+=1
            else:count+=compare(p[k],q[k])
        return count
    def compare(a,b):
        if isinstance(a,dict) and 'ref' in a:
            assert isinstance(b,dict) and 'ref' in b
            return compare_node(a['ref'],b['ref'])
        if isinstance(a,dict) and 'import_index' in a:
            assert oldvalue(a)==newvalue(b);return 0
        if isinstance(a,dict):
            assert a.keys()==b.keys();return sum(compare(a[k],b[k]) for k in a)
        if isinstance(a,list):
            assert len(a)==len(b);return sum(compare(x,y) for x,y in zip(a,b))
        assert a==b,(a,b);return 0
    old_exports=paths(previous,'EXPR');new_exports=paths(current,'EXPR')
    assert old_exports.keys()==new_exports.keys()
    for path in old_exports:
        count=compare_node(old_exports[path],new_exports[path])
        if count:affected[path]=count
    source=json.loads((DEV/'explosion-source.json').read_text())
    import re
    for item in source['files']:
        names=re.findall(r'(?m)^export\s+(\w+)\s+is', (MOD/item['path']).read_text(encoding='utf-8'))
        assert names and all('$/GFX/GameFx/'+n in affected for n in names),item['path']
    result=dict(visual_scale=VISUAL_SCALE,relative_to='smoke-preview.14',relative_multiplier=1.5,
                previous_visual_scale=2,source_files=len(source['files']),
                source_dimensions=sum(len(f['changes']) for f in source['files']),
                unique_compiled_dimensions=len(changed),affected_exports=len(affected),
                checked_exports=len(old_exports),other_properties_unchanged=True,
                fire_source_durations_unchanged=True,rendered_appearance='unverified')
    (DEV/'explosion-verification.json').write_text(json.dumps(result,indent=2)+'\n')
    return result

if __name__=='__main__':
    print(json.dumps(verify_explosions(Cndf((MOD/'Gen/NDF/GFX/GameFx.ndfbin').read_bytes())),indent=2))
