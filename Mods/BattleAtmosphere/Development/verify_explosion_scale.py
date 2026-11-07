"""Compare the entire compiled GameFx graph against preview.7.

Only 2x expressions on reviewed visual dimensions/spatial fields may differ. All other
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
from explosion_scale import SIZES,PERSISTENT,VISUAL_SCALE,SPATIAL_SCALE,SPATIAL,OFFSETS

def verify_explosions(current):
    with zipfile.ZipFile(DEV/BACKUP) as z:
        installed=json.loads(z.read('development/smoke-release.json'))
        assert installed['version']=='smoke-preview.15'
        assert installed['explosions']['visual_scale']==3
        assert hashlib.sha256(z.read('installed/Gen/NDF/GFX/GameFx.ndfbin')).hexdigest()==installed['outputs']['Gen/NDF/GFX/GameFx.ndfbin']
    assert VISUAL_SCALE==2 and SPATIAL_SCALE==2
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
    changed=set();affected={};spatial=set();offsets=set()
    def scaled(a,b,factor=VISUAL_SCALE):
        n=current.objects[b['ref']];p=n['properties']
        if n['class']=='TIntrinsicCall_2Param':
            return (newvalue(p['Intrinsic'])==('import','$/System/EvaluableIntrinsics/IntrinsicOperatorMul')
                    and current.objects[p['Param0']['ref']]['properties'].get('Value')==factor
                    and newvalue(p['Param1'])==oldvalue(a))
        o=previous.objects[a['ref']]
        if n['class']==o['class'] and n['class'] in ('TConstantInteger','TConstantFloat'):
            return math.isclose(p.get('Value',0),factor*o['properties'].get('Value',0),rel_tol=1e-6)
        if n['class']==o['class']=='TConstantFloat3':
            return all(math.isclose(y,factor*x,rel_tol=1e-6,abs_tol=1e-6) for x,y in
                       zip(o['properties'].get('Value',[0,0,0]),p.get('Value',[0,0,0])))
        return False
    def offset_scaled(a,b):
        if oldvalue(a)==newvalue(b):return True
        if not (isinstance(a,dict) and isinstance(b,dict) and 'ref' in a and 'ref' in b):return False
        o,n=previous.objects[a['ref']],current.objects[b['ref']]
        if o['class']==n['class']=='TConstantFloat3':return scaled(a,b,SPATIAL_SCALE)
        if o['class']==n['class']=='TIntrinsicCall_2Param':
            p,q=o['properties'],n['properties']
            return (oldvalue(p['Intrinsic'])==newvalue(q['Intrinsic'])==('import','$/System/EvaluableIntrinsics/IntrinsicOperatorAdd')
                    and offset_scaled(p['Param0'],q['Param0']) and offset_scaled(p['Param1'],q['Param1']))
        # Template parameters (including the world/event anchor) must be exact.
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
                    assert bank not in PERSISTENT,(name,bank)
                    assert not bank.startswith(('SFX','Shake','Destroy','Dummy','Propulsion','FX_BANK_')),bank
                    if name in SIZES:
                        assert scaled(left[name],right[name]),('Size not exactly 2x',name,bank)
                    elif name in SPATIAL.get(bank,set()):
                        assert scaled(left[name],right[name],SPATIAL_SCALE),('Spread not exactly 2x',name,bank)
                        spatial.add((j,name))
                    elif name in OFFSETS.get(bank,set()):
                        assert offset_scaled(left[name],right[name]),('Offset/anchor mismatch',name,bank)
                        offsets.add((j,name))
                    else:raise AssertionError(('Unreviewed parameter',name,bank))
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
    assert len(spatial)>1000 and len(offsets)>100
    result=dict(visual_scale=VISUAL_SCALE,relative_to='smoke-preview.15',relative_multiplier=2/3,
                previous_visual_scale=3,spatial_scale=SPATIAL_SCALE,source_files=len(source['files']),
                source_dimensions=sum(len(f['changes']) for f in source['files']),
                unique_compiled_dimensions=len(changed),affected_exports=len(affected),
                compiled_spatial_parameters=len(spatial),compiled_local_offsets=len(offsets),event_anchors_unchanged=True,
                checked_exports=len(old_exports),other_properties_unchanged=True,
                fire_source_durations_unchanged=True,rendered_appearance='unverified')
    (DEV/'explosion-verification.json').write_text(json.dumps(result,indent=2)+'\n')
    return result

if __name__=='__main__':
    print(json.dumps(verify_explosions(Cndf((MOD/'Gen/NDF/GFX/GameFx.ndfbin').read_bytes())),indent=2))
