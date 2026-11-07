"""Check compiled 2x vertical motion against installed preview.14."""
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
        if name in ('getX','getY','getZ'):return v[0][{'getX':0,'getY':1,'getZ':2}[name]]
        if name=='sin':return math.sin(v[0])
        if name=='cross':
            a,b=v
            return [a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]]
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
        if cl=='TSpawnerAccessor':
            assert p['Field']=='Position';return fields['spawner_position']
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

def seed_initializers(c):
    exports=paths(c,'EXPR');imports={v:k for k,v in paths(c,'IMPR').items()};result={}
    for name in ('BA_BurningFuelSmoke','FX_BANK_Binder_Fire','BANK_DarkFireCompo'):
        for o in reachable(c,exports['$/VFX_Bank/'+name]):
            if o['class']!='TParticleEvolver_SpraySpawner':continue
            p=o['properties'];maximum=c.objects[p['MaxSpawnedParticleLifetime']['ref']]['properties'].get('Value')
            if maximum not in (18,22,80,85,90):continue
            initializers=[x['properties']['InitFunction'] for x in reachable(c,p['Spawner']['ref'])
                          if x['class']=='TParticleInitialiserWithEvaluable' and
                          imports.get(x['properties']['Field'].get('import_index'))=='$/Particle/CustomFloat3_4']
            assert len(initializers)==1,maximum
            result[maximum]=initializers[0]
    assert len(result)==5
    return result

def verify_motion(bank):
    with zipfile.ZipFile(DEV/'archive/smoke-preview15-before.zip') as z:
        previous=Cndf(z.read('installed/Gen/NDF/VFX_Bank.ndfbin'))
        # Explosion dimensions are validated separately by verify_explosions.
        # Unit fire timers and AI output must remain exact.
        for name in ('Gen/NDF/GFX/Unit.ndfbin','Gen/NDF/GFX/Skirmish.ndfbin'):
            assert (MOD/name).read_bytes()==z.read('installed/'+name),name
    old=layers(previous);new=layers(bank);initializers=seed_initializers(bank);rows=[]
    weather=[900,300,0];w2=weather[0]**2+weather[1]**2
    def heading(v):
        along=(v[0]*weather[0]+v[1]*weather[1])/w2
        across=(v[0]*weather[1]-v[1]*weather[0])/w2
        assert along>0,'Smoke reversed into the wind'
        return math.degrees(math.atan2(across,along))
    for life,(physics,speed) in new.items():
        prior,prior_speed=old[life]
        assert not any(o['class']=='TAparametricFunction' for o in reachable(bank,physics['WindField']['ref'])), 'Per-frame random draw'
        births=[];turns=[]
        for position in ([0,0,0],[120000,300000,0],[350000,150000,0],[600000,500000,0]):
            for seed in (0,.5,1):
                fields=dict(random=seed,weather=weather,spawner_position=position,CustomFloat_5=seed,CustomFloat3_2=[0,0,0],
                            CreationDate=0,DeathDate=life,LifeRatio=0)
                stored=evaluate(bank,initializers[life],fields)
                assert all(-1.000001<=v<=1.000001 for v in stored[:2]) and 0<=stored[2]<=6.283186
                assert stored==evaluate(bank,initializers[life],fields)
                near=dict(fields,spawner_position=[position[0]+5,position[1]+5,position[2]])
                neighbor=evaluate(bank,initializers[life],near)
                assert max(abs(a-b) for a,b in zip(stored[:2],neighbor[:2]))<0.001,'Nearby fire emitters diverged'
                fields['CustomFloat3_4']=stored
                a=evaluate(previous,prior_speed,fields);b=evaluate(bank,speed,fields)
                assert math.isclose(b[2],2*a[2],rel_tol=1e-6),(a,b)
                assert all(math.isclose(b[i],a[i],rel_tol=1e-6,abs_tol=1e-6) for i in (0,1)),(a,b)
                birth=heading(b);births.append(birth);winds=[]
                for age in (0,2,10,20,28,35,60):
                    fields['LifeRatio']=age/life
                    for prop in ('AccelerationField','WindField'):
                        a=evaluate(previous,prior[prop],fields);b=evaluate(bank,physics[prop],fields)
                        assert math.isclose(b[2],2*a[2],rel_tol=2e-6,abs_tol=1e-6),(prop,a,b)
                        assert all(math.isclose(b[i],a[i],rel_tol=1e-6,abs_tol=1e-6) for i in (0,1)),(prop,a,b)
                    winds.append(round(heading(b),4))
                turns.append(abs(winds[-1]-winds[0]))
                last=None
                for step in range(241):
                    fields['LifeRatio']=(step/4)/life
                    angle=heading(evaluate(bank,physics['WindField'],fields))
                    assert abs(angle)<45,angle
                    if last is not None:assert abs(angle-last)<2,'Wind changed abruptly'
                    last=angle
                rows.append(dict(lifetime=life,seed=seed,source_position=position,
                                 initial_heading_degrees_from_map_wind=round(birth,4),
                                 wind_heading_degrees_at_seconds_0_2_10_20_28_35_60=winds))
        assert max(births)-min(births)>15,'Initial headings too uniform'
        assert max(turns)>10,'No meaningful upper directional change'
    return dict(relative_to='smoke-preview.14',vertical_initial_velocity_multiplier=2,vertical_acceleration_multiplier=2,
                vertical_wind_multiplier=2,horizontal_motion_unchanged=True,source_coherent_spatial_variation=True,per_frame_random_draws=False,
                age_varying_direction=True,turn_transition_seconds=28,small_gust_period_seconds=round(2*math.pi/0.13,2),samples=rows,
                unit_and_AI_binaries_unchanged=True,rendered_curvature='unverified')
