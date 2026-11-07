"""Bounded burning smoke, isolated from ordinary shell/weapon smoke. No launch."""
from pathlib import Path
import argparse
import hashlib
import json
import re
import zipfile
from apply_profile import matching, object_span
from smoke_plume import DARK, CADAVER, cadaver_duration, vehicle_fuel_durations
from bridge_smoke import ground as bridge_ground, fuel as bridge_fuel, dark as bridge_dark, extend_buildings

DEV = Path(__file__).resolve().parent
MOD = DEV.parent
ROOT = MOD.parents[1]
BINDER = 'GameData/Fx/Bank/Basics/BANK_Binder_Fire.ndf'
FUEL = 'GameData/Fx/Bank/Basics/BANK_FuelFire.ndf'
OLD = '$/VFX_Bank/BANK_FuelSmoke'
NEW = '$/VFX_Bank/BA_BurningFuelSmoke'
VERSION = 'smoke-preview.20'
MULTIPLIER = 10
BACKUP = 'archive/smoke-preview20-before.zip'

def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def once(text, old, new):
    assert text.count(old) == 1, (old, text.count(old))
    return text.replace(old, new, 1)

def expected_files():
    with zipfile.ZipFile(MOD / 'base.zip') as z:
        def read(name):
            return z.read(name).decode('utf-8-sig').replace('\r\n', '\n')
        before = {n: read(n) for n in (BINDER, FUEL, DARK, CADAVER)}
        after = {BINDER: bridge_ground(before[BINDER]), FUEL: bridge_fuel(before[FUEL]),
                 DARK: bridge_dark(before[DARK]), CADAVER: cadaver_duration(before[CADAVER])}
        callers = []
        excluded = []
        for name in z.namelist():
            if not name.startswith('GameData/Fx/Generated/') or not name.endswith('.ndf'):
                continue
            text = read(name)
            if OLD not in text:
                continue
            stem = Path(name).stem
            if stem.startswith(('fx_destruction_', 'fx_impact_destruction_unite_')):
                before[name] = text
                after[name] = text.replace(OLD, NEW)
                if stem.startswith('fx_impact_destruction_unite_'):
                    after[name], duration_changes = vehicle_fuel_durations(after[name])
                    assert duration_changes, 'Vehicle fuel duration calls not found: ' + name
                callers.append({'path': name, 'calls': text.count(OLD)})
            else:
                excluded.append(name)
        from explosion_scale import extend_sources, VISUAL_SCALE
        explosions = extend_sources(z, before, after)
        from map_wreck_fire import extend_sources as map_sources
        map_report = map_sources(z,before,after)
        map_report['additional_burning_sources'] = extend_buildings(z,before,after)
        (DEV/'map-wreck-source.json').write_text(json.dumps(map_report,indent=2)+'\n')
        from impact_visuals import extend_sources as impact_sources
        from read_cndf import Cndf
        with zipfile.ZipFile(DEV/BACKUP) as saved:
            reference=Cndf(saved.read('installed/Gen/NDF/GFX/GameFx.ndfbin'))
        impact_report=impact_sources(z,before,after,reference)
        (DEV/'impact-visual-source.json').write_text(json.dumps(impact_report,indent=2)+'\n')
        for name in excluded:
            # Explosion-selected files can still carry the previously installed
            # scale during migration. main() validates those against the exact
            # archived/source/target versions; untouched files must stay stock.
            if name not in after:
                assert (MOD/name).read_text(encoding='utf-8-sig') == read(name), name
    (DEV/'explosion-source.json').write_text(json.dumps(dict(version=VERSION,visual_scale=VISUAL_SCALE,files=explosions),indent=2)+'\n')
    assert len(callers) == 22, len(callers)
    return before, after, callers, excluded

def protected_files():
    manifest = json.loads((DEV / 'manifest.json').read_text())
    files = [MOD / r['path'] for r in manifest['files']]
    files += list((MOD / 'Runtime/Python').glob('*.py'))
    files += [ROOT / 'version.dll', ROOT / 'WARNO.exe',
              MOD / 'GameData/Generated/Gameplay/Gfx/FireDescriptor.ndf',
              MOD / 'GameData/Generated/Gameplay/Gfx/SmokeDescriptor.ndf',
              MOD / 'CommonData/Gameplay/Unit/TemplateDescriptorFireAndSmoke.ndf']
    return {p.relative_to(ROOT).as_posix(): sha(p) for p in files}

def protected_match(a,b):
    if a==b:return True
    # The only allowed protected-file transition is the separately validated
    # VFX-budget loader. All AI Python/NDF, gameplay and original EXE stay exact.
    from native_bridge.verify_fx_budget import verify_fx_budget
    validated=verify_fx_budget()
    with zipfile.ZipFile(DEV/BACKUP) as z:old=json.loads(z.read('protected.json'))['version.dll']
    allowed={old,validated['dll_sha256']}
    return (a.get('version.dll') in allowed and b.get('version.dll') in allowed and
            {k:v for k,v in a.items() if k!='version.dll'}=={k:v for k,v in b.items() if k!='version.dll'})

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write', action='store_true')
    args = parser.parse_args()
    before, after, callers, excluded = expected_files()
    with zipfile.ZipFile(DEV/BACKUP) as z:
        archived = {name:z.read('source/'+name).decode('utf-8-sig').replace('\r\n','\n')
                    for name in after if 'source/'+name in z.namelist()}
    for name, target in after.items():
        current = (MOD / name).read_text(encoding='utf-8-sig')
        previous = archived.get(name,target)
        assert current in (before[name], previous, target), 'Unreviewed edits: ' + name
        if not args.write:
            assert current == target, 'Source not yet applied: ' + name
    protected = protected_files()
    archive = DEV / BACKUP
    if args.write and not archive.exists():
        archive.parent.mkdir(exist_ok=True)
        saved = Path.home() / 'Saved Games/EugenSystems/WARNO/mod/BattleAtmosphere'
        with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as z:
            for name in before:
                z.write(MOD / name, 'source/' + name)
            for p in saved.rglob('*'):
                if p.is_file():
                    z.write(p, 'installed/' + p.relative_to(saved).as_posix())
            for pattern in ('*smoke*.py', 'smoke-*.json'):
                for p in DEV.glob(pattern):
                    z.write(p, 'development/' + p.name)
            z.writestr('protected.json', json.dumps(protected, indent=2))
    if args.write:
        for name, target in after.items():
            (MOD / name).write_text(target, encoding='utf-8', newline='\n')
    assert protected_match(protected_files(), protected)
    report = dict(version=VERSION, status='source-verified; visual-unverified',
                  relative_to='smoke-preview.19', appearance='Smoke-trailed warhead impact routes use the existing five 122 mm HE variants; destruction, bullet hits, tactical smoke, projectile flight and all existing FX graphs unchanged',
                  vehicle_burn_seconds=[10,1200], map_wreck_fire=True,
                  sources={n: sha(MOD / n) for n in after}, protected=protected,
                  burning_callers=callers, unchanged_shared_smoke_callers=excluded,
                  backup=archive.relative_to(MOD).as_posix())
    if archive.exists():
        with zipfile.ZipFile(archive) as z:
            assert protected_match(json.loads(z.read('protected.json')), protected), 'Protected inputs changed since smoke work began'
    (DEV / 'smoke-source.json').write_text(json.dumps(report, indent=2) + '\n')
    print('PASS: %d source files, %d burning callers, %d shared-smoke bank references preserved; AI/gameplay unchanged' % (len(after), len(callers), len(excluded)))

if __name__ == '__main__':
    main()
