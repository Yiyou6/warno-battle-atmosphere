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
    result=dict(placement_pack=placement,placement_entry='Items.sav',placement_sha256=hashlib.sha256(raw).hexdigest(),
                placements=near,scenery_pack=scenery,scenery_entry_sha256=hashlib.sha256(sr).hexdigest(),
                family=family,selected='Big',qualification='Map places Small twice at unit scale; chosen Big is the larger native variant of the same fuel-fire family, not a literal Big bridge placement.',
                runtime_map_coordinates_used=False)
    (DEV/'map-wreck-research.json').write_text(json.dumps(result,indent=2)+'\n')
    print('PASS: two native fire placements by destroyed bridge; Small and Big references resolved')


if __name__=='__main__':main()
