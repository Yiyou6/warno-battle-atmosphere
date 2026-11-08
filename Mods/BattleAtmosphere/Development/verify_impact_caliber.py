"""Compare every compiled impact surface and weapon property to its baseline."""
import json
import re
import zipfile
from collections import Counter
from functools import lru_cache
from pathlib import Path
from read_cndf import Cndf
from read_edat import Edat
from apply_smoke_profile import MOD, DEV, ROOT, BACKUP, sha
from verify_smoke_profile import paths
from verify_map_wreck import fingerprint
from impact_caliber import AMMO, WEAPONS, objects, field


def verify_weapons(policy):
    # The formerly unmodified Weapon cluster is read directly from the game.
    original = Cndf(Edat(ROOT/'Data/PC/201602/Glad.dat').read('NDF/GFX/Weapon.ndfbin', max_bytes=64*1024*1024))
    current = Cndf((MOD/'Gen/NDF/GFX/Weapon.ndfbin').read_bytes())
    oe, ne = paths(original, 'EXPR'), paths(current, 'EXPR')
    old = fingerprint(original)
    ni = {v: k for k, v in paths(current, 'IMPR').items()}
    additions = {'$/GFX/Weapon/BA_Helo_' + n: '$/GFX/Weapon/' + n for n in policy['helicopter_ammo']}
    assert set(ne)-set(oe) == set(additions), ('unexpected weapon exports', set(ne)-set(oe))
    assert set(oe).issubset(ne)
    redirects = {'$/GFX/Weapon/' + n: key for n, key in policy['small_ammo_redirects'].items()}
    # Most native ammunition is embedded and has no public EXPR name. Match its
    # immutable DescriptorId; checking exports alone misses those weapons.
    source = (MOD/AMMO).read_text(encoding='utf-8-sig')
    spans = objects(source, 'TAmmunitionDescriptor')
    guids = {n: re.search(r'GUID:\{([^}]+)\}', source[a:b])[1].replace('-', '')
             for n,(a,b) in spans.items()}
    original_ammo = {o['properties']['DescriptorId']['hex']:o for o in original.objects if o['class']=='TAmmunitionDescriptor'}
    names_by_guid = {guids[n.rsplit('/',1)[1]]:n for n in redirects | additions}
    ammo_ids = {o['id']:names_by_guid[o['properties']['DescriptorId']['hex']]
                for o in current.objects if o['class']=='TAmmunitionDescriptor'
                and o['properties']['DescriptorId']['hex'] in names_by_guid}
    # Normalize only the two approved ammunition properties. Everything else,
    # including all weapon/module/critical/damage graph nodes, must equal stock.
    @lru_cache(None)
    def node(i):
        obj = current.objects[i]
        props = dict(obj['properties'])
        if i in ammo_ids:
            name = ammo_ids[i]
            parent = additions.get(name, name)
            base = original_ammo[guids[parent.rsplit('/',1)[1]]]['properties']
            assert obj['class'] == 'TAmmunitionDescriptor'
            if name in additions:
                assert props['DescriptorId'] != base['DescriptorId']
                assert props['ImpactHappening'].startswith('BA_HeloRocket_')
                props['DescriptorId'] = base['DescriptorId']
            else:
                assert props['ImpactHappening'] == redirects[name]
            props['ImpactHappening'] = base['ImpactHappening']
        return obj['class'], value(props)
    def value(v):
        if isinstance(v, dict):
            if 'ref' in v:
                return node(v['ref'])
            if 'import_index' in v:
                return 'import', ni[v['import_index']]
            return tuple((k, value(x)) for k, x in sorted(v.items()))
        if isinstance(v, (list, tuple)):
            return tuple(value(x) for x in v)
        return v
    for name, idx in oe.items():
        assert old({'ref': idx}) == value({'ref': ne[name]}), ('weapon gameplay changed', name)
    for name, parent in additions.items():
        base = original_ammo[guids[parent.rsplit('/',1)[1]]]
        assert old({'ref':base['id']}) == value({'ref': ne[name]}), ('clone gameplay changed', name)
    # Independently check which exported weapon managers reference the clones.
    actual = {}
    reverse = {idx: n for n, idx in ne.items()}
    def refs(v):
        if isinstance(v, dict):
            if 'ref' in v:
                yield v['ref']
            else:
                for x in v.values():
                    yield from refs(x)
        elif isinstance(v, (list, tuple)):
            for x in v:
                yield from refs(x)
    for name, idx in ne.items():
        if not name.startswith('$/GFX/Weapon/WeaponDescriptor_'):
            continue
        pending = [idx]; seen = set(); found = set()
        while pending:
            i = pending.pop()
            if i in seen:
                continue
            seen.add(i)
            if i in reverse and reverse[i] in additions:
                found.add(reverse[i].rsplit('/', 1)[1])
            pending.extend(refs(current.objects[i]['properties']))
        if found:
            actual[name.rsplit('/', 1)[1]] = found
    expected = {name: set(rows.values()) for name, rows in policy['helicopter_weapon_replacements'].items()}
    assert actual == expected, 'Helicopter-only weapon isolation failed'
    guids = [o['properties']['DescriptorId'] for o in current.objects
             if o['class'] == 'TAmmunitionDescriptor']
    assert len(guids) == len({repr(x) for x in guids}), 'Ammunition GUID collision'
    return dict(compared_original_exports=len(oe), isolated_heli_ammo=len(additions),
                helicopter_weapon_managers=len(actual), all_other_weapon_properties_equal=True,
                all_nonhelicopter_weapon_references_equal=True, unique_ammunition_ids=True)


def verify(report):
    policy = report['caliber_policy']
    # .19 is the exact native impact routing baseline. .20 contains the overly
    # broad replacements being corrected, so cannot prove a native restoration.
    with zipfile.ZipFile(DEV/'archive/smoke-preview20-before.zip') as z:
        old = Cndf(z.read('installed/Gen/NDF/GFX/Depiction.ndfbin'))
    with zipfile.ZipFile(DEV/BACKUP) as z:
        frozen = ('Gen/NDF/VFX_Bank.ndfbin',
                  'Gen/NDF/GFX/Unit.ndfbin', 'Gen/NDF/GFX/Skirmish.ndfbin')
        for name in frozen:
            assert (MOD/name).read_bytes() == z.read('installed/' + name), name
    new = Cndf((MOD/'Gen/NDF/GFX/Depiction.ndfbin').read_bytes())
    ov, nv = fingerprint(old), fingerprint(new)
    def normalized_helo(value):
        if isinstance(value,tuple):return tuple(normalized_helo(v) for v in value)
        if isinstance(value,str):
            return value.replace('$/GFX/GameFx/BA_HeloSmall_', '$/GFX/GameFx/')
        return value
    def tables(c):
        return [o for o in c.objects if o['class'] == 'TMimeticWorldHappeningRegistration']
    ot, nt = tables(old), tables(new)
    assert len(ot) == len(nt) == 3
    op = next(o for o in ot if 'CanonGrosHEM1Abrams' in dict(o['properties']['Happenings']['map']))
    np = next(o for o in nt if 'CanonGrosHEM1Abrams' in dict(o['properties']['Happenings']['map']))
    for a in ot:
        if a is op:
            continue
        assert any(ov(a['properties']) == nv(b['properties']) for b in nt)
    assert ov({k:v for k,v in op['properties'].items() if k!='Happenings'}) == nv({k:v for k,v in np['properties'].items() if k!='Happenings'})
    oh, nh = dict(op['properties']['Happenings']['map']), dict(np['properties']['Happenings']['map'])
    clones = policy['new_registrations']
    assert set(nh) == set(oh) | set(clones)
    def surfaces(c, ref):
        obj = c.objects[ref['ref']]
        assert obj['class'] == 'TImpactHappening'
        return dict(obj['properties']['Happenings']['map'])
    def visual(c, ref):
        if not isinstance(ref,dict) or 'ref' not in ref:
            return ref
        obj = c.objects[ref['ref']]
        return obj['properties']['SubHappenings'][0] if obj['class']=='TCompositeHappening' else ref
    nums = dict(Ground=0, Water=1, Air=2, Wall=3, Vehicle=4, FlyingVehicle=5, Missile=6, Ricochet=7)
    changes = {(r['weapon'], nums[r['surface']]) for r in report['changes']}
    target = visual(old, surfaces(old, oh['Artillerie2A18122Mm'])[0])
    rocket = surfaces(old, oh[policy['donor_impact']])
    checked = Counter()
    for name, ref in nh.items():
        origin = clones.get(name, {}).get('parent', name)
        mode = clones.get(name, {}).get('mode')
        a, b = surfaces(old, oh[origin]), surfaces(new, ref)
        assert a.keys() == b.keys()
        for surface in a:
            desired = None
            if name in policy['native_small_corrections'] and ov(visual(old,a[surface]))==ov(target):
                donor=policy['native_small_corrections'][name]
                desired=visual(old,surfaces(old,oh[donor])[surface]);checked['native_76_corrections']+=1
            elif mode == 'helicopter-rocket' and surface < 6:
                desired = visual(old, rocket[surface]); checked['rocket_routes'] += 1
            elif (name, surface) in changes:
                desired = target; checked['retained_122_routes'] += 1
            if desired is None:
                assert ov(a[surface]) == nv(b[surface]), (name, surface, 'unexpected native-route change')
                checked['native_routes'] += 1
            else:
                actual=nv(visual(new,b[surface]))
                if mode=='helicopter-rocket' and surface<6:
                    assert 'BA_HeloSmall_' in repr(actual)
                    actual=normalized_helo(actual)
                assert ov(desired) == actual, (name, surface, 'wrong donor visual')
                x, y = old.objects[a[surface]['ref']], new.objects[b[surface]['ref']]
                if x['class'] == 'TCompositeHappening':
                    assert y['class'] == 'TCompositeHappening'
                    assert ov(x['properties']['SubHappenings'][1:]) == nv(y['properties']['SubHappenings'][1:]), (name, surface, 'audio changed')
                else:
                    assert actual == ov(desired)
            if name.startswith('DestructionUnite'):
                checked['protected_destruction_routes'] += 1
    assert checked['retained_122_routes'] == len(changes)
    assert checked['protected_destruction_routes'] == 80
    # Verify every below-80 mm ammo resolves to its native surface table.
    text = (MOD/AMMO).read_text(encoding='utf-8-sig')
    aa = objects(text, 'TAmmunitionDescriptor')
    with zipfile.ZipFile(MOD/'base.zip') as z:
        stock = z.read(AMMO).decode('utf-8-sig'); sa = objects(stock, 'TAmmunitionDescriptor')
    count = 0
    for name in policy['protected_small_ammo']:
        a, b = aa[name]; c, d = sa[name]
        current = field(text[a:b], 'ImpactHappening'); parent = field(stock[c:d], 'ImpactHappening')
        if parent not in oh:
            continue
        if current not in policy['native_small_corrections']:
            assert ov(oh[parent]) == nv(nh[current]), ('small caliber not restored', name)
        count += 1
    assert count > 100
    weapons = verify_weapons(policy)
    # Check the active compiled ammo, not only the source-name grouping. The
    # native ZiS-3 76 mm howitzer itself borrows 122 mm; its special correction
    # must pass the same active-ammunition restriction as every other weapon.
    compiled = Cndf((MOD/'Gen/NDF/GFX/Weapon.ndfbin').read_bytes())
    by_guid = {re.search(r'GUID:\{([^}]+)\}', text[a:b])[1].replace('-', ''): name
               for name,(a,b) in aa.items() if not name.startswith('BA_Helo_')}
    active_small = 0
    for obj in compiled.objects:
        if obj['class'] != 'TAmmunitionDescriptor':
            continue
        p = obj['properties']; name = by_guid.get(p['DescriptorId']['hex'])
        if name not in policy['protected_small_ammo']:
            continue
        hit = p.get('ImpactHappening')
        if hit in nh:
            assert 'fx_impact_sol_HE_122mm' not in repr(nv(nh[hit])), ('active sub-80 mm uses 122 mm',name)
            active_small += 1
    assert active_small > 100
    result = dict(status='compiled-caliber-routing-and-weapon-isolation-passed; visual-unverified',
        replacement='Native small-caliber impacts; helicopter rockets retain L10D3 HE at native 1.5x size',
        helicopter_visual_scale=1.5,
        changed_routes=len(changes)+checked['rocket_routes']+checked['native_76_corrections'], retained_122_routes=len(changes),
        native_small_ammo_checked=count, active_small_ammo_without_122mm=active_small,
        protected_destruction_routes=checked['protected_destruction_routes'],
        route_counts=dict(checked), weapons=weapons, sound_happenings_unchanged=True,
        frozen_outputs={n:sha(MOD/n) for n in frozen}, gameplay_and_projectile_flight_unchanged=True,
        rendered_appearance='unverified')
    (DEV/'impact-visual-verification.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    return result
