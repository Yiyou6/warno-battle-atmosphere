"""Split shared impact registrations by caliber and actual helicopter users.

All edits are visual routing. Native damage, flight, sound and destruction
remain unchanged. A helicopter-only ammunition copy isolates shared plane ammo.
"""
import re
import uuid
from collections import defaultdict
from apply_profile import matching
from impact_visuals import MAPPING, TARGET, definitions, rows

PREFIX = 'GameData/Generated/Gameplay/Gfx/'
AMMO = PREFIX + 'Ammunition.ndf'
WEAPONS = PREFIX + 'WeaponDescriptor.ndf'
UNITS = PREFIX + 'UniteDescriptor.ndf'
ROCKET_DONOR = 'Ammo_RocketArt_D3_300mm_x10'


def objects(text, kind):
    return {m[1]: (m.start(), matching(text, text.index('(', m.start())) + 1)
            for m in re.finditer(r'(?m)^(?:export )?(\w+) is ' + kind + r'\s*\(', text)}


def field(block, name):
    m = re.search(r'(?m)^\s*' + name + r'\s*=\s*([^\n]+)', block)
    return m[1].strip().strip("'") if m else None


def caliber(name, block):
    # Source identifier and literal Caliber values, not weapon-family labels.
    literal = field(block, 'Caliber') or ''
    m = re.match(r'(\d+(?:[._]\d+)?)mm', literal)
    if m:
        return float(m[1].replace('_', '.'))
    m = re.search(r'(?:^|_)(14_5|12_7|7_62|5_56|5_45|72_5|127_2)mm', name)
    if m:
        return float(m[1].replace('_', '.'))
    m = re.search(r'(\d+)_?mm', name, re.I)
    if m:
        # The source identifier has a missing decimal; the same Caliber token
        # is also used by HVAR_127mm. This does not affect the 80 mm boundary.
        return 127.2 if 'Zuni_1272mm' in name else float(m[1])
    return None


def registration(text, name):
    begin = text.index("('" + name + "', TImpactHappening(")
    end = matching(text, begin) + 1
    return begin, end, text[begin:end]


def patch_spans(text, changes):
    for a, b, value in sorted(changes, reverse=True):
        text = text[:a] + value + text[b:]
    return text


def extend(z, before, after, legacy):
    read = lambda p: z.read(p).decode('utf-8-sig').replace('\r\n', '\n')
    original = read(MAPPING)
    ammo_text, weapon_text, unit_text = read(AMMO), read(WEAPONS), read(UNITS)
    aa = objects(ammo_text, 'TAmmunitionDescriptor')
    ww = objects(weapon_text, 'TWeaponManagerModuleDescriptor')
    uu = objects(unit_text, 'TEntityDescriptor')
    blocks = {n: ammo_text[a:b] for n, (a, b) in aa.items()}
    calibers = {n: caliber(n, b) for n, b in blocks.items()}
    # A few identifiers omit caliber. Infer only when all explicit source
    # identifiers sharing that localization token agree (e.g. AGS17/LAG40).
    tokens = defaultdict(set)
    for n, b in blocks.items():
        if calibers[n] is not None:
            tokens[field(b, 'Caliber')].add(calibers[n])
    for n, b in blocks.items():
        values = tokens[field(b, 'Caliber')]
        if calibers[n] is None and len(values) == 1:
            calibers[n] = next(iter(values))

    by_impact = defaultdict(list)
    for n, b in blocks.items():
        if field(b, 'ImpactHappening'):
            by_impact[field(b, 'ImpactHappening')].append(n)
    small = {n for n, mm in calibers.items() if mm is not None and mm < 80}
    revised = after[MAPPING]
    extra = []
    restored = {}
    clones = {}
    ammo_routes = {}
    native_small_corrections = {}
    affected = {r['weapon'] for r in legacy['changes']}
    # Restore the entire native surface table, including its audio and anchors.
    # Mixed families get a separate native route so 90+ mm users keep 122 mm.
    for impact, users in sorted(by_impact.items()):
        subset = sorted(set(users) & small)
        if not subset or impact not in affected:
            continue
        _, _, stock = registration(original, impact)
        if TARGET in stock:
            # Native ZiS-3 76 mm itself borrows the 122 mm table. The user's
            # strict 80 mm threshold therefore needs a genuine 76 mm donor,
            # rather than a blind native restoration for this shared family.
            assert impact == 'Artillerie2A18122Mm'
            donor = 'CanonMoyenHEPT76'
            defs = definitions(original)
            donor_rows = {s:line for w,s,a,b,line in rows(original) if w==donor}
            edits = []
            for w,s,a,b,line in rows(stock):
                if TARGET in line:
                    aliases = [n for n in re.findall(r'\b\w+\b',donor_rows[s]) if n in defs]
                    assert len(aliases)==1
                    edits.append((a,b,line.replace(TARGET,aliases[0])))
            stock = patch_spans(stock,edits)
            native_small_corrections['BA_Small_'+impact] = donor
        if len(subset) == len(users):
            a, b, _ = registration(revised, impact)
            revised = revised[:a] + stock + revised[b:]
            restored[impact] = subset
        else:
            key = 'BA_Small_' + impact
            extra.append(stock.replace("('" + impact + "'", "('" + key + "'", 1))
            clones[key] = dict(parent=impact, mode='native-small-caliber')
            ammo_routes.update({n: key for n in subset})

    weapon_users = defaultdict(list)
    for n, (a, b) in uu.items():
        block = unit_text[a:b]
        for ref in re.findall(r'\$/GFX/Weapon/(WeaponDescriptor_\w+)', block):
            weapon_users[ref].append((n, '"Helo"' in block))
    helicopter_weapons = {w for w, users in weapon_users.items() if any(h for n, h in users)}
    assert all(all(h for n, h in weapon_users[w]) for w in helicopter_weapons)
    helo_ammo = set()
    weapon_replacements = {}
    for w in sorted(helicopter_weapons):
        a, b = ww[w]
        refs = set(re.findall(r'Ammunition\s*=\s*\$/GFX/Weapon/(\w+)', weapon_text[a:b]))
        selected = {n for n in refs if n in blocks and n.startswith('Ammo_RocketAir_')
                    and field(blocks[n], 'MinMaxCategory') == 'MinMax_Roquette_AS'
                    and field(blocks[n], 'ProjectileType') == 'EProjectileType/Obus'}
        if selected:
            weapon_replacements[w] = {n: 'BA_Helo_' + n for n in sorted(selected)}
            helo_ammo.update(selected)
    assert len(helo_ammo) == 19, sorted(helo_ammo)

    candidates = {n: calibers[n] for n, b in blocks.items()
                  if field(b, 'MinMaxCategory') == 'MinMax_MLRS'
                  and 'Family=DamageFamily_howz ' in b
                  and "'HE'" in b and field(b, 'SmokeDescriptor') == 'nil'
                  and 'thermobaric' not in n.lower() and calibers[n] is not None}
    assert max(candidates, key=candidates.get) == ROCKET_DONOR
    donor_impact = field(blocks[ROCKET_DONOR], 'ImpactHappening')
    defs = definitions(original)
    donor_rows = {surface: line for w, surface, a, b, line in rows(original) if w == donor_impact}
    donor_visuals = {}
    for surface, line in donor_rows.items():
        names = [t for t in re.findall(r'\b\w+\b', line) if t in defs]
        if surface not in ('Missile', 'Ricochet'):
            assert len(names) == 1, (surface, names)
            donor_visuals[surface] = names[0]
    from heli_rocket_scale import extend as scale_helo_visuals
    scaled_visuals, declarations, scaled_exports = scale_helo_visuals(z, before, after, defs, donor_visuals)
    revised = declarations + '\n\n' + revised
    for impact in sorted({field(blocks[n], 'ImpactHappening') for n in helo_ammo}):
        _, _, stock = registration(original, impact)
        edits = []
        for w, surface, a, b, line in rows(stock):
            if surface not in donor_visuals:
                continue
            aliases = [t for t in re.findall(r'\b\w+\b', line) if t in defs]
            assert len(aliases) == 1, (impact, surface, aliases)
            edits.append((a, b, re.sub(r'\b' + aliases[0] + r'\b', scaled_visuals[surface], line)))
        key = 'BA_HeloRocket_' + impact
        extra.append(patch_spans(stock, edits).replace("('" + impact + "'", "('" + key + "'", 1))
        clones[key] = dict(parent=impact, mode='helicopter-rocket', donor=donor_impact)
    insertion = revised.index("('YakBGatling', TImpactHappening(")
    revised = revised[:insertion] + (',\n        '.join(extra) + ',\n        ') + revised[insertion:]

    edits = []
    for n, route in sorted(ammo_routes.items()):
        a, b = aa[n]
        edits.append((a, b, re.sub(r"(ImpactHappening\s*=\s*)'[^']+'", r"\g<1>'" + route + "'", blocks[n])))
    new_ammo = patch_spans(ammo_text, edits)
    for n in sorted(helo_ammo):
        name = 'BA_Helo_' + n
        clone = blocks[n].replace(n + ' is ', 'export ' + name + ' is ', 1)
        clone = re.sub(r'DescriptorId\s*=\s*GUID:\{[^}]+\}',
                       'DescriptorId = GUID:{' + str(uuid.uuid5(uuid.NAMESPACE_URL, 'BattleAtmosphere/' + name)) + '}', clone)
        clone = re.sub(r"(ImpactHappening\s*=\s*)'[^']+'", r"\g<1>'BA_HeloRocket_" + field(blocks[n], 'ImpactHappening') + "'", clone)
        new_ammo += '\n\n' + clone + '\n'
    edits = []
    for w, replacements in weapon_replacements.items():
        a, b = ww[w]
        block = re.sub(r'(Ammunition\s*=\s*\$/GFX/Weapon/)(\w+)',
                       lambda m: m[1] + replacements.get(m[2], m[2]), weapon_text[a:b])
        edits.append((a, b, block))
    before.update({AMMO: ammo_text, WEAPONS: weapon_text})
    after.update({MAPPING: revised, AMMO: new_ammo, WEAPONS: patch_spans(weapon_text, edits)})
    legacy['changes'] = [r for r in legacy['changes'] if r['weapon'] not in restored]
    legacy['caliber_policy'] = dict(minimum_122_mm=80, measured_calibers=calibers,
        restored_families=restored, small_ammo_redirects=ammo_routes,
        protected_small_ammo=sorted(small & {n for users in by_impact.values() for n in users}),
        new_registrations=clones, helicopter_ammo=sorted(helo_ammo),
        helicopter_weapon_replacements=weapon_replacements,
        donor_ammo=ROCKET_DONOR, donor_impact=donor_impact, donor_caliber_mm=300,
        donor_native_visuals=donor_visuals, ordinary_he_mlrs_candidates=candidates,
        helicopter_visual_scale=1.5, helicopter_spatial_scale=1.5, helicopter_scaled_exports=scaled_exports,
        native_small_corrections=native_small_corrections,
        missiles_unchanged=True, non_helicopter_weapon_references_unchanged=True)
    return legacy
