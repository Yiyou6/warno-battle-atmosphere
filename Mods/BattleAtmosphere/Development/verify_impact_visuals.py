"""Audit compiled warhead routing and preserve destruction/weapon behavior."""
import json
import re
import zipfile
from collections import Counter
from read_cndf import Cndf
from apply_smoke_profile import MOD,DEV,BACKUP,sha
from verify_map_wreck import fingerprint


def verify_impacts():
    report=json.loads((DEV/'impact-visual-source.json').read_text())
    enums=(MOD/'CommonData/Gameplay/Constantes/Enumerations/ImpactSurface.ndf').read_text(encoding='utf-8-sig')
    surfaces={n:int(v) for n,v in re.findall(r'(?m)^\s*(\w+)\s+is\s+(\d+)\s*$',enums)}
    assert surfaces==dict(Ground=0,Water=1,Air=2,Wall=3,Vehicle=4,FlyingVehicle=5,Missile=6,Ricochet=7)
    changes={(r['weapon'],surfaces[r['surface']]):r for r in report['changes']}
    assert len(changes)==len(report['changes'])
    with zipfile.ZipFile(DEV/BACKUP) as z:
        old=Cndf(z.read('installed/Gen/NDF/GFX/Depiction.ndfbin'))
        frozen=('Gen/NDF/GFX/GameFx.ndfbin','Gen/NDF/VFX_Bank.ndfbin',
                'Gen/NDF/GFX/Unit.ndfbin','Gen/NDF/GFX/Skirmish.ndfbin')
        for name in frozen:assert (MOD/name).read_bytes()==z.read('installed/'+name),name
    new=Cndf((MOD/'Gen/NDF/GFX/Depiction.ndfbin').read_bytes())
    ov,nv=fingerprint(old),fingerprint(new)
    def registrations(c):
        return {tuple(k for k,v in o['properties']['Happenings']['map']):o
                for o in c.objects if o['class']=='TMimeticWorldHappeningRegistration'}
    a,b=registrations(old),registrations(new);assert a.keys()==b.keys() and len(a)==3
    def get_visual(c,happening):
        obj=c.objects[happening['ref']]
        if obj['class']=='TCompositeHappening':return obj['properties']['SubHappenings'][0]
        return happening
    protected_destruction=0;unchanged=0;replaced=0
    for key in a:
        p,q=a[key]['properties'],b[key]['properties']
        assert ov({k:v for k,v in p.items() if k!='Happenings'})==nv({k:v for k,v in q.items() if k!='Happenings'})
        if 'CanonGrosHEM1Abrams' not in key:
            assert ov(p)==nv(q)
            continue
        oh,nh=dict(p['Happenings']['map']),dict(q['Happenings']['map']);assert oh.keys()==nh.keys()
        donor_old=dict(old.objects[oh['Artillerie2A18122Mm']['ref']]['properties']['Happenings']['map'])[0]
        donor_new=dict(new.objects[nh['Artillerie2A18122Mm']['ref']]['properties']['Happenings']['map'])[0]
        donor_old,donor_new=get_visual(old,donor_old),get_visual(new,donor_new)
        assert ov(donor_old)==nv(donor_new)
        assert new.objects[donor_new['ref']]['class']=='TRandomHappening'
        assert len(new.objects[donor_new['ref']]['properties']['Alternatives'])==5
        for weapon in oh:
            oo,no=old.objects[oh[weapon]['ref']],new.objects[nh[weapon]['ref']]
            assert oo['class']==no['class']=='TImpactHappening'
            op,np=dict(oo['properties']['Happenings']['map']),dict(no['properties']['Happenings']['map'])
            assert op.keys()==np.keys()
            for surface in op:
                before,after=op[surface],np[surface]
                if (weapon,surface) not in changes:
                    assert ov(before)==nv(after),(weapon,surface,'unexpected change')
                    unchanged+=1
                    if weapon.startswith('DestructionUnite'):protected_destruction+=1
                    continue
                assert surface not in (6,7) and not weapon.startswith('DestructionUnite')
                assert nv(get_visual(new,after))==ov(donor_old),(weapon,surface,'wrong replacement')
                old_surface=old.objects[before['ref']]
                if old_surface['class']=='TCompositeHappening':
                    new_surface=new.objects[after['ref']];assert new_surface['class']=='TCompositeHappening'
                    old_parts=old_surface['properties']['SubHappenings'];new_parts=new_surface['properties']['SubHappenings']
                    assert len(old_parts)==len(new_parts) and len(old_parts)>=2
                    assert ov(old_parts[1:])==nv(new_parts[1:]),(weapon,surface,'sound/other happenings changed')
                    assert {k for k in old_surface['properties']}=={'SubHappenings'}
                else:
                    assert nv(after)==ov(donor_old)
                replaced+=1
    assert replaced==len(changes) and protected_destruction>=64
    result=dict(status='compiled-routing-and-frozen-FX-passed; visual-unverified',
                replacement='existing 122 mm HE impact; five native random variants; installed 3x dimensions/3.3x spread',
                changed_routes=replaced,warhead_families=report['warhead_families'],
                ammunition_descriptors=report['ammunition_descriptors'],
                surfaces=dict(Counter(r['surface'] for r in report['changes'])),
                unchanged_routes=unchanged,protected_destruction_routes=protected_destruction,
                sound_happenings_unchanged=True,other_mimetic_registrations_unchanged=True,
                frozen_outputs={n:sha(MOD/n) for n in frozen},
                gameplay_and_projectile_flight_unchanged=True,rendered_appearance='unverified')
    (DEV/'impact-visual-verification.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    return result


if __name__=='__main__':print(json.dumps(verify_impacts(),indent=2))
