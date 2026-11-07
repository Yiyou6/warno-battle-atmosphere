"""Record native Urban Frontlines placement and same-family effect references."""
import hashlib
import json
from read_edat import Edat
from verify_smoke_profile import Cndf, paths, reachable, ROOT, DEV


def main():
    placement='Data/PC/169425/Maps/_3x3_UrbanFrontlines_Details.dat'
    raw=Edat(ROOT/placement).read('Items.sav')
    c=Cndf(raw)
    fires=[o for o in c.objects if o['properties'].get('SceneryDescriptor')=='FX_Fire_Fuel_Explosion_Small_RandomDuration']
    bridges=[o for o in c.objects if o['properties'].get('SceneryDescriptor','').startswith('Bridge_') and '_Dest' in o['properties']['SceneryDescriptor']]
    assert len(fires)==2
    near=[]
    for fire in fires:
        p=fire['properties']['AxeT']
        bridge=min(bridges,key=lambda o:sum((x-y)**2 for x,y in zip(p,o['properties']['AxeT'])))
        near.append(dict(fire=fire,nearest_destroyed_bridge=bridge))
    scenery='Data/PC/201602/DecorsSets/Fulda_Definition.dat'
    sr=Edat(ROOT/scenery).read('NDF/DecorsSets/Scenery/Fulda.ndfbin',max_bytes=64000000)
    s=Cndf(sr);e=paths(s,'EXPR');im={v:k for k,v in paths(s,'IMPR').items()}
    family={}
    for size in ('Small','Big'):
        name='$/Scenery/FX_Fire_Fuel_Explosion_'+size+'_RandomDuration'
        calls=[o for o in reachable(s,e[name]) if o['class']=='TActionCall']
        assert len(calls)==1
        family[size]=dict(descriptor=name,fx=im[calls[0]['properties']['Action']['import_index']])
    smoke_props=[]
    for o in c.objects:
        descriptor=o['properties'].get('SceneryDescriptor','')
        if descriptor not in ('FX_fumee_blanche_petite_RandomDuration','FX_fumee_blanche_tres_petite_RandomDuration','FX_fumee_blanche_brume_sol_RandomDuration'):continue
        calls=[n for n in reachable(s,e['$/Scenery/'+descriptor]) if n['class']=='TActionCall']
        assert len(calls)==1
        fire=min(fires,key=lambda f:sum((x-y)**2 for x,y in zip(o['properties']['AxeT'],f['properties']['AxeT'])))
        delta=[x-y for x,y in zip(o['properties']['AxeT'],fire['properties']['AxeT'])]
        smoke_props.append(dict(placement=o,native_fx=im[calls[0]['properties']['Action']['import_index']],
                                nearest_fire_id=fire['id'],relative_offset=delta,distance=sum(v*v for v in delta)**.5))
    selected=min(smoke_props,key=lambda o:o['distance'])
    assert selected['native_fx']=='$/GFX/GameFx/fx_Small_White_Smoke_Wind_diorama'
    assert selected['placement']['id']==10064 and selected['nearest_fire_id']==10062
    result=dict(placement_pack=placement,placement_entry='Items.sav',placement_sha256=hashlib.sha256(raw).hexdigest(),
                placements=near,scenery_pack=scenery,scenery_entry_sha256=hashlib.sha256(sr).hexdigest(),
                family=family,selected='Small fire + separate Small White Smoke Wind',smoke_placements=smoke_props,selected_smoke=selected,
                qualification='The earlier investigation omitted separate scenery smoke props. The nearest independent smoke prop is about 396 game units from fire 10062; resolve its Scenery import, not a similarly named generated FX file. Copy the two native wind-smoke layers, preserving all particle parameters.',
                runtime_map_coordinates_used=False)
    (DEV/'map-wreck-research.json').write_text(json.dumps(result,indent=2)+'\n')
    print('PASS: bridge fire and independent wind smoke mapped through actual placed Scenery imports')


if __name__=='__main__':main()
