"""Check compiled birth lean, increasing wind and preserved vertical motion."""
import math,zipfile
from verify_smoke_profile import Cndf,paths,reachable,MOD,DEV

def evaluate(c,root,fields):
    imports={v:k.rsplit('/',1)[-1] for k,v in paths(c,'IMPR').items()}
    def binary(fn,a,b):
        if isinstance(a,list) or isinstance(b,list):
            if not isinstance(a,list):a=[a]*len(b)
            if not isinstance(b,list):b=[b]*len(a)
            return [fn(x,y) for x,y in zip(a,b)]
        return fn(a,b)
    def intrinsic(name,v):
        if name=='GenFloat3':return list(v)
        if name=='RandomUnit':return fields['random']
        f={'IntrinsicOperatorAdd':lambda a,b:a+b,'IntrinsicOperatorSub':lambda a,b:a-b,
           'IntrinsicOperatorMul':lambda a,b:a*b,'IntrinsicOperatorDiv':lambda a,b:a/b,
           'min':min,'max':max}
        if name in f:return binary(f[name],*v)
        if name=='sqr':return binary(lambda a,b:a*b,v[0],v[0])
        raise AssertionError(('Unknown motion intrinsic',name))
    def read(v,bindings):
        if 'import_index' in v:raise AssertionError(('Unexpected imported value',imports[v['import_index']]))
        i=v['ref']
        if i in bindings:return bindings[i]
        o=c.objects[i];p=o['properties'];cl=o['class']
        if cl in ('TConstantInteger','TConstantFloat'):return p.get('Value',0)
        if cl=='TConstantFloat3':return p.get('Value',[0,0,0])
        if cl=='TVariable':
            assert p['PropertyName']=='ActiveWindMovementForFx';return fields['weather']
        if cl=='TParticleAccessor':return fields[imports[p['Field']['import_index']]]
        if cl=='TAparametricFunction':
            assert p['Function']=='UnitRand';return fields['random']
        if cl.startswith('TIntrinsicCall_'):
            return intrinsic(imports[p['Intrinsic']['import_index']],[read(p[k],bindings) for k in sorted(p) if k.startswith('Param')])
        if cl=='TFunctionCall':
            f=c.objects[p['Function']['ref']]['properties'];values=[read(x,bindings) for x in p['EffectiveParams']]
            if 'Intrinsic' in f:return intrinsic(imports[f['Intrinsic']['import_index']],values)
            env=dict(bindings);env.update((a['ref'],value) for a,value in zip(f['Params'],values))
            return read(f['Code'],env)
        raise AssertionError(('Unknown motion value',cl,p))
    return read(root,{})

def layers(c):
    e=paths(c,'EXPR');imports={v:k for k,v in paths(c,'IMPR').items()};result={}
    for bank in ('BA_BurningFuelSmoke','FX_BANK_Binder_Fire','BANK_DarkFireCompo'):
        for o in reachable(c,e['$/VFX_Bank/'+bank]):
            if o['class']!='TParticleEvolver_SpraySpawner':continue
            p=o['properties'];sp=c.objects[p['Spawner']['ref']]
            maximum=c.objects[p['MaxSpawnedParticleLifetime']['ref']]['properties'].get('Value')
            if maximum not in (18,22,80,85,90):continue
            physics=[v['properties'] for v in reachable(c,sp['id']) if v['class']=='TParticleEvolver_Physics'];assert len(physics)==1
            speed=[v['properties']['InitFunction'] for v in reachable(c,sp['id'])
                   if v['class']=='TParticleInitialiserWithEvaluable' and imports.get(v['properties']['Field'].get('import_index'))=='$/Particle/Speed']
            assert len(speed)==1
            result[maximum]=(physics[0],speed[0])
    assert len(result)==5
    return result

def verify_motion(bank):
    with zipfile.ZipFile(DEV/'archive/smoke-preview9-before.zip') as z:
        previous=Cndf(z.read('installed/Gen/NDF/VFX_Bank.ndfbin'))
        # Explosion size, unit fire timers and AI output must remain exact.
        for name in ('Gen/NDF/GFX/GameFx.ndfbin','Gen/NDF/GFX/Unit.ndfbin','Gen/NDF/GFX/Skirmish.ndfbin'):
            assert (MOD/name).read_bytes()==z.read('installed/'+name),name
    old=layers(previous);new=layers(bank);rows=[]
    for life,(physics,speed) in new.items():
        prior,prior_speed=old[life]
        for seed in (0,.5,1):
            fields=dict(random=seed,weather=[900,300,0],CustomFloat_5=seed,CustomFloat3_2=[0,0,0],
                        CreationDate=0,DeathDate=life,LifeRatio=0)
            a=evaluate(previous,prior_speed,fields);b=evaluate(bank,speed,fields)
            assert math.isclose(b[2],2*a[2],rel_tol=1e-6),(a,b)
            # Same random spread as preview.8, but horizontal weather weight
            # is now 0.30 instead of 0.15; the rise remains exactly doubled.
            for axis in (0,1):
                assert math.isclose(b[axis]-a[axis],0.15*fields['weather'][axis],rel_tol=1e-6),(a,b)
            initial_angle=math.degrees(math.atan2(math.hypot(*b[:2]),b[2]))
            assert 25 < initial_angle < 50,initial_angle
            winds=[]
            for age in (0,2,10,20,35,60):
                fields['LifeRatio']=age/life
                for prop in ('AccelerationField','WindField'):
                    a=evaluate(previous,prior[prop],fields);b=evaluate(bank,physics[prop],fields)
                    assert math.isclose(b[2],2*a[2],rel_tol=2e-6,abs_tol=1e-6),(prop,a,b)
                winds.append(round(b[0]/900,6))
            for age,actual in zip((0,2,10,20,35,60),winds):
                t=min(1,age/35)
                expected=(0.30+0.40*t*t*(3-2*t))*(0.8+0.4*seed)
                assert math.isclose(actual,expected,abs_tol=1e-6),(age,actual,expected)
            assert all(a<=b for a,b in zip(winds,winds[1:])) and winds[-1]>winds[0]*2
            rows.append(dict(lifetime=life,seed=seed,initial_angle_degrees_at_test_wind=round(initial_angle,3),
                             horizontal_wind_coefficients_at_seconds_0_2_10_20_35_60=winds))
    return dict(vertical_initial_velocity_multiplier=2,vertical_acceleration_multiplier=2,
                vertical_wind_multiplier=2,progressive_horizontal_wind=True,birth_horizontal_wind_coefficient=0.30,
                lower_upper_horizontal_wind_coefficients=[0.30,0.70],samples=rows,
                explosion_unit_and_AI_binaries_unchanged=True,rendered_curvature='unverified')
