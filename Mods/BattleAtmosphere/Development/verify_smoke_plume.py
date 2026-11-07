"""Inspect compiled preview.5 shape curves and preserve long-burning sources."""
from collections import defaultdict
import hashlib
import json
import math
import zipfile
from verify_smoke_profile import Cndf, paths, reachable, canonical, smoke_spawner, verify_multiplier
from apply_smoke_profile import MOD, DEV, BACKUP, NEW


def evaluate_scalar(c, value, fields):
    """Evaluate only deterministic scalar CNDF math. Unknown operations fail."""
    imports = {v: k.rsplit('/',1)[1] for k,v in paths(c, 'IMPR').items()}
    def intrinsic(index, values):
        name = imports[index]
        functions = {
            'IntrinsicOperatorAdd': lambda a,b:a+b, 'IntrinsicOperatorSub': lambda a,b:a-b,
            'IntrinsicOperatorMul': lambda a,b:a*b, 'IntrinsicOperatorDiv': lambda a,b:a/b,
            'min':min, 'max':max, 'sqrt':math.sqrt, 'sqr':lambda a:a*a,
        }
        assert name in functions, ('Unsupported curve intrinsic',name)
        return functions[name](*values)
    def read(v):
        obj = c.objects[v['ref']]; p = obj['properties']; cls = obj['class']
        if cls in ('TConstantFloat','TConstantInteger'):return p['Value']
        if cls == 'TParticleAccessor':return fields[imports[p['Field']['import_index']]]
        if cls.startswith('TIntrinsicCall_'):
            values = [read(p[k]) for k in sorted(p) if k.startswith('Param')]
            return intrinsic(p['Intrinsic']['import_index'],values)
        if cls == 'TFunctionCall':
            fn = c.objects[p['Function']['ref']]['properties']
            assert 'Intrinsic' in fn, ('Non-intrinsic curve function',fn)
            return intrinsic(fn['Intrinsic']['import_index'],[read(v) for v in p['EffectiveParams']])
        raise AssertionError(('Unsupported curve class',cls))
    return read(value)


def verify_plume(bank, fx, exports, source):
    with zipfile.ZipFile(DEV / 'archive/smoke-preview4-before.zip') as z:
        receipt = json.loads(z.read('development/smoke-release.json'))
        assert receipt['version'] == 'smoke-preview.3'
        data = z.read('installed/Gen/NDF/VFX_Bank.ndfbin')
        assert hashlib.sha256(data).hexdigest() == receipt['outputs']['Gen/NDF/VFX_Bank.ndfbin']
        prior = Cndf(data)
        # Source fire timers and unit burning state are preserved byte for byte.
        for name in ('Gen/NDF/GFX/Unit.ndfbin','Gen/NDF/GFX/GameFx.ndfbin'):
            assert hashlib.sha256((MOD/name).read_bytes()).hexdigest() == receipt['outputs'][name], name
    def dark_smoke(c, root):
        found = {}
        for o in reachable(c, root):
            if o['class'] != 'TParticleEvolver_SpraySpawner':continue
            props = o['properties']; sp = c.objects[props['Spawner']['ref']]['properties']
            if sp.get('_ShortDatabaseName') == 'Fumees_Dark':
                bound = c.objects[props['MaxSpawnedParticleLifetime']['ref']]['properties']['Value']
                assert bound not in found
                found[bound] = props
        assert len(found) == 3
        return found
    dark = '$/VFX_Bank/BANK_DarkFireCompo'
    old = dark_smoke(prior,paths(prior,'EXPR')[dark]); new = dark_smoke(bank,exports[dark])
    for before,after,factor in ((60,18,0.6),(80,22,0.6),(1250,85,1.5)):
        # Both versions wrap the same stock expression: strip preview.3's 10x.
        base = prior.objects[old[before]['Frequency']['ref']]['properties']['Param1']
        verify_multiplier(bank,new[after]['Frequency'],prior,base,factor=factor)
    layers = [(new[18],[10,18]),(new[22],[12,22]),(new[85],[45,85]),
              (smoke_spawner(bank,exports[NEW],False),[50,90]),
              (smoke_spawner(bank,exports['$/VFX_Bank/FX_BANK_Binder_Fire'],True),[45,80])]
    imports = {v:k.rsplit('/',1)[1] for k,v in paths(bank,'IMPR').items()}
    samples = []
    for spray, limits in layers:
        spawner = bank.objects[spray['Spawner']['ref']]['properties']
        life = bank.objects[spawner['ParticleLifetime']['ref']]['properties']
        assert bank.objects[life['Function']['ref']]['properties']['_ShortDatabaseName'] == 'RandomRange'
        assert [bank.objects[v['ref']]['properties']['Value'] for v in life['EffectiveParams']] == limits
        graph = reachable(bank,spawner['ParticleDescriptor']['ref'])
        physics = [o['properties'] for o in graph if o['class']=='TParticleEvolver_Physics'];assert len(physics)==1
        assert math.isclose(bank.objects[physics[0]['FluidFriction']['ref']]['properties']['Value'],0.18,rel_tol=1e-6)
        evolvers = {imports[o['properties']['Field']['import_index']]:o['properties']['EvolveFunction']
                    for o in graph if o['class']=='TVersatileParticleEvolver'}
        assert {'Size','Opacity','ColorModifier'} <= evolvers.keys()
        # The final density factor has a visibility floor, tested independently
        # of the shader, source opacity and fade envelope.
        opacity = bank.objects[evolvers['Opacity']['ref']]['properties']['Param1']
        rows = []
        for seed in (0,0.5,1):
            fields = dict(CustomFloat_1=20000,CustomFloat_2=1,CustomFloat_5=seed,
                          CreationDate=0,DeathDate=limits[1],LifeRatio=0,Size=350)
            sizes = []
            for age in (0,10,20,30,60,90):
                fields['LifeRatio']=age/limits[1]
                size=evaluate_scalar(bank,evolvers['Size'],fields)
                assert 0 < size <= 8000
                fields['Size']=size; dilution=evaluate_scalar(bank,opacity,fields)
                assert 0.649999 <= dilution <= 1
                sizes.append(round(size,4))
            assert sizes[0] <= 1400 and sizes[-1] < 3700
            assert 0 <= sizes[2]-sizes[1] <= sizes[1]-sizes[0] <= 500
            assert 0 <= sizes[3]-sizes[2] <= sizes[2]-sizes[1]
            rows.append(dict(variation=seed,sizes_at_0_10_20_30_60_90_seconds=sizes))
        samples.append(dict(lifetime_seconds=limits,curves=rows))
    unit=Cndf((MOD/'Gen/NDF/GFX/Unit.ndfbin').read_bytes())
    vehicles=[o['properties'] for o in unit.objects if o['class']=='TCadaverModuleDescriptor' and o['properties'].get('CadaverDuration')==3000]
    assert vehicles and all(p['CadaverFireDurationMin']==10 and p['CadaverFireDurationMax']==1200 for p in vehicles)
    return dict(smoke_layers_verified=5,emission_relative_to_preview3=[0.06,0.06,0.15,0.2,0.2],
                size_growth='decelerating square-root of elapsed seconds, varied bounds',
                compiled_curve_samples=samples,optical_density_floor=0.65,
                vehicle_burn_seconds=[10,1200],compiled_vehicle_cadaver_objects=len(vehicles),
                compiled_unique_vehicle_fuel_calls=receipt['plume']['compiled_unique_vehicle_fuel_calls'],
                vehicle_fuel_source_duration_multiplier=10,rendered_appearance='unverified')
