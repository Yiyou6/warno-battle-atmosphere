"""Check native map appearance, bounded lifecycle and single wreck routing."""
import json
import zipfile
from functools import lru_cache
from read_edat import Edat
from verify_smoke_profile import Cndf, paths, reachable, MOD, DEV, ROOT, BACKUP
from map_wreck_fire import MAP_FX, NEW_FX, NATIVE_BANK, NEW_BANK, WRECK_EXPORTS


def fingerprint(c, mode=''):
    imports={v:k for k,v in paths(c,'IMPR').items()}
    def alias(v,name):
        o=c.objects[v['ref']]
        assert o['class']=='TActionAlias' and o['properties']['_ShortDatabaseName']==name
    @lru_cache(None)
    def node(i):
        o=c.objects[i];cl=o['class'];p=dict(o['properties'])
        if mode=='bank':
            if cl=='TWaitInSec':
                alias(p['Duration'],'BA_SourceDuration')
                return ('TWaitForEver',())
            if 'InputParameters' in p:
                p['InputParameters']=[v for v in p['InputParameters'] if c.objects[v['ref']]['properties'].get('_ShortDatabaseName')!='BA_SourceDuration']
            if cl=='TActionCall':
                pairs=p['NamedParams']['map'];extra=[v for k,v in pairs if k=='BA_SourceDuration']
                assert len(extra)==1;alias(extra[0],'BA_SourceDuration')
                p['NamedParams']={'map':[[k,v] for k,v in pairs if k!='BA_SourceDuration']}
            if '_ShortDatabaseName' in p:
                p['_ShortDatabaseName']=p['_ShortDatabaseName'].replace('BA_UrbanFireAndDarkSmoke_Color_Table','FireAndDarkSmoke_Color_Table').replace('BA_UrbanFireAndDarkSmoke','AoA_FX_BANK_FireAndDarkSmoke')
        if mode in ('map_old','map_new'):
            if p.get('_ShortDatabaseName')==NEW_FX:
                assert cl=='TSimultaneousActionForActionCallTemplate'
                assert len(p['InputParameters'])==1;alias(p.pop('InputParameters')[0],'parDuration')
                cl='TSimultaneousAction';p['_ShortDatabaseName']=MAP_FX
            if cl=='TActionCall' and 'import_index' in p['Action']:
                action=imports[p['Action']['import_index']].rsplit('/',1)[-1]
                pairs=dict(p.get('NamedParams',{}).get('map',[]))
                if action==NEW_BANK:
                    alias(pairs.pop('BA_SourceDuration'),'parDuration')
                if action in ('BANK_FuelFire','BANK_FuelSmoke'):
                    duration=pairs.pop('parDuration')
                    if mode=='map_new':alias(duration,'parDuration')
                    else:assert c.objects[duration['ref']]['properties']['Value'] in (300,400,500,600)
                if action=='BANK_VerticalSmoke_Finite_Simple':
                    alias(pairs.pop('parDuration'),'parDuration')
                    pairs['parLifetime']=pairs.pop('parSmokeLifetime')
                if pairs:p['NamedParams']={'map':sorted(pairs.items())}
        return cl,value(p)
    def value(v):
        if isinstance(v,dict):
            if 'ref' in v:return node(v['ref'])
            if 'import_index' in v:
                path=imports[v['import_index']]
                if mode=='map_new':path=path.replace(NEW_BANK,NATIVE_BANK).replace('BANK_VerticalSmoke_Finite_Simple','BANK_VerticalSmoke_Simple')
                return ('import',path)
            return tuple((k,value(x)) for k,x in sorted(v.items()))
        if isinstance(v,(list,tuple)):return tuple(value(x) for x in v)
        return v
    return value


def verify_depiction():
    archive=Edat(ROOT/'Data/PC/201602/Glad.dat')
    old=Cndf(archive.read('NDF/GFX/Depiction.ndfbin',max_bytes=64*1024*1024))
    new=Cndf((MOD/'Gen/NDF/GFX/Depiction.ndfbin').read_bytes())
    ov,nv=fingerprint(old),fingerprint(new)
    changed=set()
    @lru_cache(None)
    def node(i,j):
        a,b=old.objects[i],new.objects[j];p,q=a['properties'],b['properties']
        if a['class']=='TCompositeHappening' and b['class']=='TIntroduceMobileHappening':
            assert set(p)=={'SubHappenings'}
            children=p['SubHappenings'];assert len(children)==3
            first,second,sound=[old.objects[v['ref']] for v in children]
            assert first['properties']['Anchor']=='fx_stress_01' and second['properties']['Anchor']=='fx_stress_02'
            assert '/Sound_Incendie' in repr(ov(children[2]))
            assert '/FX_Vehicule_Dest_Fire' in repr(ov(children[0]))
            assert ov(children[0])==nv({'ref':j})
            changed.add(i);return
        assert a['class']==b['class'],(a['class'],b['class'])
        compare(p,q)
    def compare(a,b):
        if isinstance(a,dict):
            if 'ref' in a:node(a['ref'],b['ref']);return
            if 'import_index' in a:assert ov(a)==nv(b);return
            assert a.keys()==b.keys()
            for k in a:compare(a[k],b[k])
        elif isinstance(a,list):
            assert len(a)==len(b)
            for x,y in zip(a,b):compare(x,y)
        else:assert a==b,(a,b)
    oe,ne=paths(old,'EXPR'),paths(new,'EXPR');assert oe.keys()==ne.keys()
    for name in oe:node(oe[name],ne[name])
    # Depiction descriptors are native top-level records, not public exports.
    od=[o for o in old.objects if o['class']=='TDepictionDescriptor']
    nd=[o for o in new.objects if o['class']=='TDepictionDescriptor']
    assert len(od)==len(nd)
    for a,b in zip(od,nd):node(a['id'],b['id'])
    assert len(changed)==2,len(changed)
    return dict(checked_exports=len(oe),checked_depiction_descriptors=len(od),replaced_ground_air_composites=len(changed),source_count_per_wreck=1,other_depiction_properties_unchanged=True)


def verify_map_wreck(bank,fx):
    be,fe=paths(bank,'EXPR'),paths(fx,'EXPR')
    # The entire native appearance graph must match, including source positions,
    # particle counts, colors, random expressions, texture/material and sound.
    assert fingerprint(fx,'map_old')({'ref':fe['$/GFX/GameFx/'+MAP_FX]})==fingerprint(fx,'map_new')({'ref':fe['$/GFX/GameFx/'+NEW_FX]})
    assert fingerprint(bank)({'ref':be['$/VFX_Bank/'+NATIVE_BANK]})==fingerprint(bank,'bank')({'ref':be['$/VFX_Bank/'+NEW_BANK]})
    with zipfile.ZipFile(DEV/BACKUP) as z:
        old=Cndf(z.read('installed/Gen/NDF/VFX_Bank.ndfbin'))
        for name in ('Gen/NDF/GFX/Unit.ndfbin','Gen/NDF/GFX/Skirmish.ndfbin'):
            assert (MOD/name).read_bytes()==z.read('installed/'+name),name
    oe=paths(old,'EXPR');ov,nv=fingerprint(old),fingerprint(bank)
    assert set(be)-set(oe)=={'$/VFX_Bank/'+NEW_BANK}
    assert not set(oe)-set(be)
    for name in oe:assert ov({'ref':oe[name]})==nv({'ref':be[name]}),name
    fv=fingerprint(fx)
    for name in WRECK_EXPORTS:
        root=fx.objects[fe[name]];p=root['properties'];assert len(p['Actions'])==1
        comp=fx.objects[p['Actions'][0]['ref']];assert comp['class']=='TCompetitionAction'
        actions=[fx.objects[v['ref']] for v in comp['properties']['Actions']];assert len(actions)==2
        call,wait=actions;assert call['class']=='TActionCall' and wait['class']=='TWaitInSec'
        assert call['properties']['Action']['ref']==fe['$/GFX/GameFx/'+NEW_FX]
        duration=dict(call['properties']['NamedParams']['map'])['parDuration']
        assert fv(duration)==fv(wait['properties']['Duration'])
        expr=fx.objects[duration['ref']];assert expr['class']=='TFunctionCall'
        params=expr['properties']['EffectiveParams'];assert len(params)==3
        assert [fx.objects[x['ref']]['properties']['Value'] for x in params[1:]]==[10,1200]
    depiction=verify_depiction()
    result=dict(native_map_family=MAP_FX,native_appearance_graph_equal=True,finite_bank_particle_graph_equal=True,
                existing_bank_exports_unchanged=len(oe),depiction=depiction,vehicle_burn_seconds=[10,1200],
                unit_and_ai_binary_unchanged=True,rendered_appearance='unverified')
    (DEV/'map-wreck-verification.json').write_text(json.dumps(result,indent=2)+'\n')
    return result


if __name__=='__main__':
    print(json.dumps(verify_map_wreck(Cndf((MOD/'Gen/NDF/VFX_Bank.ndfbin').read_bytes()),Cndf((MOD/'Gen/NDF/GFX/GameFx.ndfbin').read_bytes())),indent=2))
