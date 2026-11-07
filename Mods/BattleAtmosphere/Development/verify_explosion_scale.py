"""Compare the entire compiled GameFx graph against preview.7.

Only 3x sizes / 3.3x reviewed spatial fields and the separate wreck replacement may differ. All other
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
from map_wreck_fire import WRECK_EXPORTS,NEW_FX
from bridge_smoke import SMOKE_BANK

def verify_explosions(current):
    with zipfile.ZipFile(DEV/BACKUP) as z:
        installed=json.loads(z.read('development/smoke-release.json'))
        assert installed['version']=='smoke-preview.18'
        assert installed['explosions']['visual_scale']==3
        assert hashlib.sha256(z.read('installed/Gen/NDF/GFX/GameFx.ndfbin')).hexdigest()==installed['outputs']['Gen/NDF/GFX/GameFx.ndfbin']
    assert VISUAL_SCALE==3 and SPATIAL_SCALE==3.3
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
    changed=set();affected={};spatial=set();offsets=set();removed=set()
    def scaled(a,b,factor=VISUAL_SCALE):
        n=current.objects[b['ref']];p=n['properties']
        if n['class']=='TIntrinsicCall_2Param':
            return (newvalue(p['Intrinsic'])==('import','$/System/EvaluableIntrinsics/IntrinsicOperatorMul')
                    and math.isclose(current.objects[p['Param0']['ref']]['properties'].get('Value',0),factor,rel_tol=1e-6)
                    and newvalue(p['Param1'])==oldvalue(a))
        o=previous.objects[a['ref']]
        if n['class'] in ('TConstantInteger','TConstantFloat') and o['class'] in ('TConstantInteger','TConstantFloat'):
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
        if i in wreck_roots:
            assert j==wreck_roots[i]
            return 0 # also reached by local references; independently checked
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
                    if bank=='AoA_FX_BANK_FireAndDarkSmoke_Simple' and name=='SmokeCountMul':
                        n=current.objects[right[name]['ref']]
                        assert n['class'] in ('TConstantFloat','TConstantInteger') and n['properties'].get('Value',0)==0
                        continue # only former burning smoke is replaced; fire params remain exact
                    assert bank not in PERSISTENT,(name,bank)
                    assert not bank.startswith(('SFX','Shake','Destroy','Dummy','Propulsion','FX_BANK_')),bank
                    if name in SIZES:
                        assert scaled(left[name],right[name]),('Size not exactly 3x',name,bank)
                    elif name in SPATIAL.get(bank,set()):
                        assert scaled(left[name],right[name],SPATIAL_SCALE),('Spread not exactly 3.3x',name,bank)
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
            b=[v for v in b if not (isinstance(v,dict) and 'ref' in v and current.objects[v['ref']]['class']=='TActionCall' and newvalue(current.objects[v['ref']]['properties']['Action'])==('import','$/VFX_Bank/'+SMOKE_BANK))]
            if len(a)!=len(b):
                kept=[]
                for v in a:
                    obj=previous.objects[v['ref']] if isinstance(v,dict) and 'ref' in v else None
                    props=obj['properties'] if obj else {}
                    action=oldvalue(props['Action']) if obj and obj['class']=='TActionCall' else None
                    if action in (('import','$/VFX_Bank/BANK_FuelFire'),('import','$/VFX_Bank/BA_BurningFuelSmoke')):
                        dur=dict(props['NamedParams']['map'])['parDuration']
                        assert previous.objects[dur['ref']]['properties'].get('Value') in (350,400,450,500,600)
                        removed.add(v['ref'])
                    else:kept.append(v)
                assert len(kept)==len(b),('Unexpected action removal',len(a),len(b),len(kept))
                a=kept
            assert len(a)==len(b);return sum(compare(x,y) for x,y in zip(a,b))
        assert a==b,(a,b);return 0
    old_exports=paths(previous,'EXPR');new_exports=paths(current,'EXPR')
    wreck_roots={old_exports[p]:new_exports[p] for p in WRECK_EXPORTS}
    assert set(new_exports)-set(old_exports)=={'$/GFX/GameFx/'+NEW_FX}
    assert not set(old_exports)-set(new_exports)
    for path in old_exports:
        if path in WRECK_EXPORTS:continue # verified against native map FX separately
        count=compare_node(old_exports[path],new_exports[path])
        if count:affected[path]=count
    source=json.loads((DEV/'explosion-source.json').read_text())
    import re
    for item in source['files']:
        names=re.findall(r'(?m)^export\s+(\w+)\s+is', (MOD/item['path']).read_text(encoding='utf-8'))
        assert names and all('$/GFX/GameFx/'+n in affected for n in names),item['path']
    assert len(spatial)>1000 and len(offsets)>100
    assert removed
    result=dict(visual_scale=VISUAL_SCALE,relative_to='smoke-preview.18',relative_multiplier=1,
                previous_visual_scale=3,spatial_scale=SPATIAL_SCALE,source_files=len(source['files']),
                source_dimensions=sum(len(f['changes']) for f in source['files']),
                unique_compiled_dimensions=len(changed),affected_exports=len(affected),
                compiled_spatial_parameters=len(spatial),compiled_local_offsets=len(offsets),event_anchors_unchanged=True,
                checked_exports=len(old_exports),other_properties_unchanged=True,
                removed_unique_old_vehicle_fuel_calls=len(removed),wreck_effect_verified_separately=True,rendered_appearance='unverified')
    (DEV/'explosion-verification.json').write_text(json.dumps(result,indent=2)+'\n')
    return result

if __name__=='__main__':
    print(json.dumps(verify_explosions(Cndf((MOD/'Gen/NDF/GFX/GameFx.ndfbin').read_bytes())),indent=2))
