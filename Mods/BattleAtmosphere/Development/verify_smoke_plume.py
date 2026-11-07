"""Inspect compiled bounded twofold smoke growth and preserve fire sources."""
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
        # CNDF omits the default Value=0 on numeric constants.
        if cls in ('TConstantFloat','TConstantInteger'):return p.get('Value',0)
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
        for name in ('Gen/NDF/GFX/Unit.ndfbin',):
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
    emission = {}
    for bound,minimum,maximum in ((18,0.15,0.3),(22,0.45,0.75),(85,1.2,1.8)):
        samples = [evaluate_scalar(bank,new[bound]['Frequency'],dict(CustomFloat_2=v)) for v in (0,0.1,1,2,4,8,20)]
        assert math.isclose(min(samples),minimum,rel_tol=1e-6) and math.isclose(max(samples),maximum,rel_tol=1e-6)
        emission[str(bound)] = dict(range_per_second=[minimum,maximum],samples=samples)
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
        color_nodes = [o for o in reachable(bank,evolvers['ColorModifier']['ref'])
                       if o['class']=='TIntrinsicCall_3Param' and
                       imports.get(o['properties']['Intrinsic'].get('import_index'))=='LinearColor']
        colors = sorted([[bank.objects[o['properties']['Param'+str(i)]['ref']]['properties'].get('Value',0)
                          for i in range(3)] for o in color_nodes])
        assert len(colors)==2,colors
        for actual,expected in zip(colors,(0.22,0.34)):
            assert all(math.isclose(v,expected,abs_tol=1e-6) for v in actual),colors
        # The final density factor has a visibility floor, tested independently
        # of the shader, source opacity and fade envelope.
        opacity = bank.objects[evolvers['Opacity']['ref']]['properties']['Param1']
        rows = []
        for seed in (0,0.5,1):
            fields = dict(CustomFloat_1=20000,CustomFloat_2=1,CustomFloat_3=1,CustomFloat_5=seed,CustomFloat_6=1,
                          CreationDate=0,DeathDate=limits[1],LifeRatio=0,Size=350)
            sizes = []
            for age in (0,10,20,30,60,90):
                fields['LifeRatio']=age/limits[1]
                size=evaluate_scalar(bank,evolvers['Size'],fields)
                assert 0 < size <= 9000
                fields['Size']=size; dilution=evaluate_scalar(bank,opacity,fields)
                assert 0.649999 <= dilution <= 1
                sizes.append(round(size,4))
            assert 810 <= sizes[0] <= 3741
            assert all(a <= b + 1e-4 for a,b in zip(sizes,sizes[1:])),sizes
            assert math.isclose(sizes[-1],2*sizes[0],abs_tol=1e-3),sizes
            assert all(s <= 2*sizes[0]+1e-3 for s in sizes),sizes
            # Dense sampling checks no overshoot or early abrupt inflation;
            # the cap must still hold beyond the longest supported lifetime.
            previous_size=sizes[0]
            for age in range(121):
                fields['LifeRatio']=age/limits[1]
                s=evaluate_scalar(bank,evolvers['Size'],fields)
                assert previous_size-1e-4 <= s <= 2*sizes[0]+1e-3,(age,s)
                if age==1:assert s/sizes[0] < 1.03,(age,s)
                previous_size=s
            alphas = []
            for ratio in (0,0.025,0.45,0.65,0.85,0.95,0.97,1):
                fields['LifeRatio'] = ratio
                fields['Size'] = evaluate_scalar(bank,evolvers['Size'],fields)
                alphas.append(evaluate_scalar(bank,evolvers['Opacity'],fields))
            assert alphas[0] == 0 and alphas[1] > 0
            assert all(0 <= b <= a + 1e-6 for a,b in zip(alphas[2:],alphas[3:]))
            assert alphas[5] < 0.003 and alphas[6] < 1e-12 and alphas[7] == 0
            rows.append(dict(variation=seed,sizes_at_0_10_20_30_60_90_seconds=sizes,
                             opacity_at_life_0_025_45_65_85_95_97_100=alphas))
        # Sample real stock vehicle birth sizes, not only oversized worst cases.
        typical = []
        for initial in (150,225,300):
            fields = dict(CustomFloat_1=initial,CustomFloat_2=1,CustomFloat_3=1,CustomFloat_5=0.5,
                          CustomFloat_6=1,CreationDate=0,DeathDate=limits[1],LifeRatio=0,Size=0)
            birth_size = evaluate_scalar(bank,evolvers['Size'],fields)
            assert birth_size >= (2199.99 if limits[1] >= 80 else 899.99)
            fields['Size'] = birth_size
            fields['LifeRatio'] = 0.35/limits[1]
            assert evaluate_scalar(bank,evolvers['Opacity'],fields) > 0.1
            fields['LifeRatio']=90/limits[1]
            maximum_size=evaluate_scalar(bank,evolvers['Size'],fields)
            assert math.isclose(maximum_size,2*birth_size,rel_tol=1e-6)
            typical.append(dict(stock_initial_size=initial,visible_birth_size=birth_size,maximum_size=maximum_size))
        samples.append(dict(lifetime_seconds=limits,curves=rows,typical_birth_sizes=typical,
                            neutral_gray_color_endpoints=colors))
    unit=Cndf((MOD/'Gen/NDF/GFX/Unit.ndfbin').read_bytes())
    vehicles=[o['properties'] for o in unit.objects if o['class']=='TCadaverModuleDescriptor' and o['properties'].get('CadaverDuration')==3000]
    assert vehicles and all(p['CadaverFireDurationMin']==10 and p['CadaverFireDurationMax']==1200 for p in vehicles)
    return dict(smoke_layers_verified=5,vehicle_layer_emission=emission,
                size_growth='smooth elapsed-time growth, capped at 2x unchanged birth size; varied growth time',
                compiled_curve_samples=samples,optical_density_floor=0.65,
                vehicle_burn_seconds=[10,1200],compiled_vehicle_cadaver_objects=len(vehicles),
                compiled_unique_vehicle_fuel_calls=receipt['plume']['compiled_unique_vehicle_fuel_calls'],
                vehicle_fuel_source_duration_multiplier=10,rendered_appearance='unverified')
