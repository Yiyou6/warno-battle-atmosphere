"""Compare the copied bridge plume and all retained bank behavior after compilation."""
import json
import zipfile
from verify_smoke_profile import Cndf, paths, reachable, local_refs, DEV, MOD, BACKUP
from functools import lru_cache
from verify_map_wreck import fingerprint
from bridge_smoke import SMOKE_FX, SMOKE_BANK, FINITE_SMOKE, NATIVE_WIND


def verify_bridge(bank,fx):
    be,fe=paths(bank,'EXPR'),paths(fx,'EXPR')
    bv,fv=fingerprint(bank),fingerprint(fx)
    # Canonicalize only the public name. All native layer values and import
    # targets must otherwise compare exactly across the two compiled databases.
    copied=bv({'ref':be['$/VFX_Bank/'+SMOKE_BANK]})
    original=fv({'ref':fe['$/GFX/GameFx/'+SMOKE_FX]})
    def rename(x):
        if isinstance(x,tuple):return tuple(rename(v) for v in x)
        return SMOKE_FX if x==SMOKE_BANK else x
    def resolve_imports(x):
        if isinstance(x,tuple):
            if len(x)==2 and x[0]=='import' and x[1] in be:return bv({'ref':be[x[1]]})
            return tuple(resolve_imports(v) for v in x)
        return x
    assert rename(copied)==resolve_imports(original),'Copied plume differs from native bridge prop'
    imports={v:k for k,v in paths(bank,'IMPR').items()}
    # Resolve locally linked wind-bank calls and independently inspect the two
    # native parameter sets: no added upward acceleration or lifetime scaling.
    calls=[o for o in reachable(bank,be['$/VFX_Bank/'+SMOKE_BANK]) if o['class']=='TActionCall' and o['properties'].get('Action',{}).get('ref')==be['$/VFX_Bank/'+NATIVE_WIND]]
    assert len(calls)==2,len(calls)
    layers=[]
    for o in calls:
        params=dict(o['properties']['NamedParams']['map'])
        values={k:bank.objects[v['ref']]['properties'].get('Value',0) for k,v in params.items()}
        assert values['SmokeSpeed']==0 and values['SmokeWindFactor']==10
        assert values['FireCountMul']==0 and values['SparksCountMul']==0
        layers.append(values)
    assert sorted(x['SmokeDuration'] for x in layers)==[8,20]
    # Verify the finite wrapper only bounds source ownership, not particle age.
    finite=bank.objects[be['$/VFX_Bank/'+FINITE_SMOKE]]['properties']
    assert len(finite['InputParameters'])==1 and len(finite['Actions'])==1
    comp=bank.objects[finite['Actions'][0]['ref']];assert comp['class']=='TCompetitionAction'
    a,b=[bank.objects[v['ref']] for v in comp['properties']['Actions']]
    assert a['class']=='TActionCall' and a['properties']['Action']['ref']==be['$/VFX_Bank/'+SMOKE_BANK]
    assert b['class']=='TWaitInSec'
    assert bank.objects[b['properties']['Duration']['ref']]['properties']['_ShortDatabaseName']=='parDuration'
    # Fixed preview.18 baseline for the historical preview.19 smoke replacement.
    with zipfile.ZipFile(DEV/'archive/smoke-preview19-before.zip') as z:
        previous=Cndf(z.read('installed/Gen/NDF/VFX_Bank.ndfbin'))
    pe=paths(previous,'EXPR')
    assert set(be)-set(pe)=={'$/VFX_Bank/'+SMOKE_BANK,'$/VFX_Bank/'+FINITE_SMOKE}
    assert not set(pe)-set(be)
    deleted=set()
    for root,names in [('FX_BANK_Binder_Fire',{'Smoke'}),('BANK_DarkFireCompo',{'fumees_Starter','fumees','Flame_Starter_Dark'})]:
        found={o['id'] for o in reachable(previous,pe['$/VFX_Bank/'+root]) if o['properties'].get('_ShortDatabaseName') in names}
        assert len(found)==len(names),(root,len(found))
        deleted.update(found)
    added={o['id'] for o in bank.objects if o['class']=='TActionCall' and o['properties'].get('Action',{}).get('ref') in (be['$/VFX_Bank/'+SMOKE_BANK],be['$/VFX_Bank/'+FINITE_SMOKE])}
    ov,nv=fingerprint(previous,skip_ids=deleted),fingerprint(bank,skip_ids=added)
    for name in pe:
        if name=='$/VFX_Bank/BA_BurningFuelSmoke':continue
        assert ov({'ref':pe[name]})==nv({'ref':be[name]}),('Non-smoke bank behavior changed',name)
    old_adapter=previous.objects[pe['$/VFX_Bank/BA_BurningFuelSmoke']]['properties']
    adapter=bank.objects[be['$/VFX_Bank/BA_BurningFuelSmoke']]['properties']
    assert fingerprint(previous)(old_adapter['InputParameters'])==bv(adapter['InputParameters'])
    assert len(adapter['Actions'])==1
    adapter_call=bank.objects[adapter['Actions'][0]['ref']]
    assert adapter_call['properties']['Action']['ref']==be['$/VFX_Bank/'+FINITE_SMOKE]
    duration=dict(adapter_call['properties']['NamedParams']['map'])['parDuration']
    assert bank.objects[duration['ref']]['properties']['_ShortDatabaseName']=='parDuration'
    # Removal is physical: no old custom emitters remain in the active banks.
    for root in ('FX_BANK_Binder_Fire','BANK_DarkFireCompo','BA_BurningFuelSmoke'):
        graph=reachable(bank,be['$/VFX_Bank/'+root])
        assert any(o['id']==be['$/VFX_Bank/'+SMOKE_BANK] for o in graph),root
        assert not any(o['properties'].get('_ShortDatabaseName') in ('Smoke','fumees','fumees_Starter','Flame_Starter_Dark') for o in graph),root
    # Check every generated building/critical-fire attachment by occurrence,
    # including repeated references interned into a single compiled action.
    fi=paths(fx,'IMPR');target=fi['$/VFX_Bank/'+SMOKE_BANK]
    @lru_cache(None)
    def count(i):
        p=fx.objects[i]['properties']
        return int(p.get('Action',{}).get('import_index')==target)+sum(count(j) for j in local_refs(p))
    source=json.loads((DEV/'map-wreck-source.json').read_text())
    changed=source['additional_burning_sources']
    for path,expected in changed.items():
        root=fe['$/GFX/GameFx/'+path.rsplit('/',1)[-1][:-4]]
        assert count(root)==expected,(path,count(root),expected)
        for o in reachable(fx,root):
            if o['class']=='TActionCall' and o['properties']['Action'].get('import_index')==fi['$/VFX_Bank/AoA_FX_BANK_FireAndDarkSmoke_Simple']:
                p=dict(o['properties']['NamedParams']['map'])
                assert fx.objects[p['SmokeCountMul']['ref']]['properties'].get('Value',0)==0,path
    result=dict(native_smoke_fx=SMOKE_FX,compiled_copy_matches_native=True,layers=layers,
                old_custom_emitter_layers_removed=5,all_other_existing_bank_behavior_unchanged=True,
                checked_existing_bank_exports=len(pe),native_smoke_source_clock_preserved=True,
                additional_burning_fx=len(changed),replaced_mixed_burning_smoke_calls=sum(changed.values()),
                rendered_appearance='unverified')
    (DEV/'bridge-smoke-verification.json').write_text(json.dumps(result,indent=2)+'\n')
    return result
