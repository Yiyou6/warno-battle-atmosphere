"""Inspect preview.3 compiled smoke fields and live wreck-source durations."""
from collections import defaultdict
import hashlib
import json
import math
import zipfile
from verify_smoke_profile import Cndf, paths, reachable, canonical, smoke_spawner, verify_multiplier
from apply_smoke_profile import MOD, DEV, BACKUP, NEW

def verify_plume(bank, fx, exports, source):
    with zipfile.ZipFile(DEV / BACKUP) as z:
        receipt = json.loads(z.read('development/smoke-release.json'))
        assert receipt['version'] == 'smoke-preview.2'
        data = z.read('installed/Gen/NDF/VFX_Bank.ndfbin')
        assert hashlib.sha256(data).hexdigest() == receipt['outputs']['Gen/NDF/VFX_Bank.ndfbin']
        prior = Cndf(data)
        prior_fx = Cndf(z.read('installed/Gen/NDF/GFX/GameFx.ndfbin'))
    old_exports = paths(prior, 'EXPR')
    dark = '$/VFX_Bank/BANK_DarkFireCompo'
    def dark_smoke(c, root):
        found = {}
        for o in reachable(c, root):
            if o['class'] != 'TParticleEvolver_SpraySpawner':
                continue
            props = o['properties']
            sp = c.objects[props['Spawner']['ref']]['properties']
            if sp.get('_ShortDatabaseName') == 'Fumees_Dark':
                bound = c.objects[props['MaxSpawnedParticleLifetime']['ref']]['properties']['Value']
                assert bound not in found
                found[bound] = props
        assert len(found) == 3
        return found
    old, new = dark_smoke(prior, old_exports[dark]), dark_smoke(bank, exports[dark])
    for before, after in ((6, 60), (8, 80), (14, 1250)):
        verify_multiplier(bank, new[after]['Frequency'], prior, old[before]['Frequency'])
        current_life = bank.objects[new[after]['Spawner']['ref']]['properties']['ParticleLifetime']
        old_life = prior.objects[old[before]['Spawner']['ref']]['properties']['ParticleLifetime']
        verify_multiplier(bank, current_life, prior, old_life)
    all_smoke = list(new.values()) + [smoke_spawner(bank, exports[NEW], False),
                                     smoke_spawner(bank, exports['$/VFX_Bank/FX_BANK_Binder_Fire'], True)]
    imports = {v: k for k, v in paths(bank, 'IMPR').items()}
    for spray in all_smoke:
        spawner = bank.objects[spray['Spawner']['ref']]['properties']
        graph = reachable(bank, spawner['ParticleDescriptor']['ref'])
        physics = [o['properties'] for o in graph if o['class'] == 'TParticleEvolver_Physics']
        assert len(physics) == 1
        friction = bank.objects[physics[0]['FluidFriction']['ref']]['properties']['Value']
        assert math.isclose(friction, 0.18, rel_tol=1e-6)
        acceleration = reachable(bank, physics[0]['AccelerationField']['ref'])
        assert any(o['class'] == 'TConstantFloat3' and o['properties'].get('Value') == [0.0, 0.0, 35.0] for o in acceleration)
        sizes = [o['properties']['EvolveFunction'] for o in graph if o['class'] == 'TVersatileParticleEvolver'
                 and imports[o['properties']['Field']['import_index']] == '$/Particle/Size']
        assert len(sizes) == 1
        size_graph = reachable(bank, sizes[0]['ref'])
        values = [o['properties'].get('Value') for o in size_graph if o['class'] in ('TConstantFloat', 'TConstantInteger')]
        assert all(v in values for v in (30000, 600, 220, 120))
        fields = {imports[o['properties']['Field']['import_index']] for o in size_graph if o['class'] == 'TParticleAccessor'}
        # ParticleElapsedTime compiles to LifeRatio * (DeathDate - CreationDate).
        assert {'$/Particle/DeathDate', '$/Particle/CreationDate'} <= fields

    unit = Cndf((MOD / 'Gen/NDF/GFX/Unit.ndfbin').read_bytes())
    cadavers = [o['properties'] for o in unit.objects if o['class'] == 'TCadaverModuleDescriptor']
    vehicles = [p for p in cadavers if p.get('CadaverDuration') == 3000]
    assert vehicles and all(p['CadaverFireDurationMin'] == 10 and p['CadaverFireDurationMax'] == 1200 for p in vehicles)
    buildings = [p for p in cadavers if p.get('CadaverDuration') == 36000]
    assert buildings and all(p['CadaverFireDurationMin'] == 10 and p['CadaverFireDurationMax'] == 60 for p in buildings)

    def fuel_calls(c, path):
        imports = {v: k for k, v in paths(c, 'IMPR').items()}
        root = paths(c, 'EXPR')['$/GFX/GameFx/' + path.rsplit('/', 1)[1][:-4]]
        found = defaultdict(list)
        for o in reachable(c, root):
            p = o['properties']
            action = imports.get(p.get('Action', {}).get('import_index'))
            if action not in (NEW, '$/VFX_Bank/BANK_FuelFire'):
                continue
            params = dict(p['NamedParams']['map'])
            duration = c.objects[params.pop('parDuration')['ref']]['properties']['Value']
            found[(action, canonical(c, params))].append(duration)
        return found
    fuel_count = 0
    for row in source['burning_callers']:
        if not row['path'].rsplit('/', 1)[1].startswith('fx_impact_destruction_unite_'):
            continue
        old_calls, new_calls = fuel_calls(prior_fx, row['path']), fuel_calls(fx, row['path'])
        assert old_calls.keys() == new_calls.keys()
        for signature, durations in old_calls.items():
            assert sorted(d * 10 for d in durations) == sorted(new_calls[signature])
            fuel_count += len(durations)
    assert fuel_count > 0
    return dict(smoke_layers_verified=5, dark_smoke_emission_and_lifetime_multiplier=10,
                size_growth='elapsed seconds, random birth variation, cap 30000',
                vehicle_burn_seconds=[10, 1200], compiled_vehicle_cadaver_objects=len(vehicles),
                compiled_unique_vehicle_fuel_calls=fuel_count, vehicle_fuel_source_duration_multiplier=10,
                rendered_appearance='unverified')
