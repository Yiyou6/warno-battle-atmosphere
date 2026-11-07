"""Preview.12: 60% emission, bounded twofold growth, faster and more tilted rise."""
import re
from apply_profile import matching

DARK = 'GameData/Fx/Bank/composite/BANK_DarkFire.ndf'
CADAVER = 'GameData/Gameplay/Gfx/CadaverConstants.ndf'
PLUME_SIZE = 'Min[30000, (Max[600, ParticleCustomFloat_1 * 0.5] + (220 + 120 * ParticleCustomFloat_5) * ParticleElapsedTime) * ParticleCustomFloat_2]'

# Small, differently sized puffs drift apart rather than all filling one sphere.
# sqrt(1+t/12)-1 has finite, slow initial growth and decreases in slope with age.
LOOK = {
    'ground': dict(life='RandomRange[45,80]', maximum=80, rate=2, cap=5000, spread=3000, growth=850, variation=350, alpha='0.45 * ParticleCustomFloat_2'),
    'fuel': dict(life='RandomRange[50,90]', maximum=90, rate=2, cap=4000, spread=2000, growth=650, variation=350, alpha='0.22 * ParticleCustomFloat_6 * ParticleCustomFloat_3'),
    'vehicle': dict(life='RandomRange[45,85]', maximum=85, rate=1.5, cap=4000, spread=2000, growth=650, variation=350, alpha='0.22 * ParticleCustomFloat_6'),
    'starter': dict(life='RandomRange[12,22]', maximum=22, rate=0.6, cap=1800, spread=1200, growth=350, variation=200, alpha='0.08 * ParticleCustomFloat_6'),
    'wisps': dict(life='RandomRange[10,18]', maximum=18, rate=0.6, cap=1600, spread=1000, growth=300, variation=200, alpha='0.07 * ParticleCustomFloat_6'),
}

def layered_smoke(block, kind, look=12):
    """Apply to one spray only. Parent fire timing remains untouched."""
    cfg = dict(LOOK[kind])
    if look >= 6:
        cfg['rate'] *= 2
    if look >= 10:
        cfg['rate'] *= 0.5
    if look >= 11:
        cfg['rate'] *= 0.5
    if look >= 12:
        cfg['rate'] *= 0.6
    block, n = re.subn(r'(?m)^(\s*Frequency = )10 \* ', r'\g<1>%s * ' % cfg['rate'], block); assert n == 1
    if look >= 7 and kind in ('vehicle','starter','wisps'):
        # Absolute emission floors bypass the two compounded distance/quality cuts.
        frequency = {'vehicle': 'Min[12,Max[8,2 * ParticleCustomFloat_2]]',
                     'starter': 'Min[5,Max[3,2 * ParticleCustomFloat_2]]',
                     'wisps': 'Min[2,Max[1,ParticleCustomFloat_2]]'}[kind]
        if look >= 10:
            frequency = ('0.15' if look >= 12 else '0.25' if look >= 11 else '0.5') + ' * (' + frequency + ')'
        block, n = re.subn(r'(?m)^(\s*Frequency = ).+$',r'\g<1>'+frequency,block); assert n == 1
    block, n = re.subn(r'MaxSpawnedParticleLifetime = \d+', 'MaxSpawnedParticleLifetime = %s' % cfg['maximum'], block); assert n == 1
    block, n = re.subn(r'(?m)^(\s*ParticleLifetime = ).+$', r'\g<1>' + cfg['life'], block); assert n == 1
    # Freeze drift direction and variation at birth; no random draws per frame.
    block, n = re.subn(r'(?m)^(\s*CustomFloat_5 = ).+$', r'\g<1>RandomUnit', block); assert n == 1
    if re.search(r'(?m)^\s*CustomFloat3_2 = ', block):
        block, n = re.subn(r'(?m)^(\s*CustomFloat3_2 = ).+$', r'\g<1>MinusOneToOneRandomDisc', block); assert n == 1
    else:
        block = once(block, 'CustomFloat_5 = RandomUnit', 'CustomFloat_5 = RandomUnit\n                                                                CustomFloat3_2 = MinusOneToOneRandomDisc')
    block, n = re.subn(r'(?m)^(\s*PhysicWindField = ).+$',
        r'\g<1>MapWind * (0.35 + 0.25 * ParticleCustomFloat_5) + ParticleCustomFloat3_2 * (30 + 70 * MapToLinearSmoothStep[ParticleElapsedTime, 6,45])', block); assert n == 1
    size = ('Min[%s + %s * ParticleCustomFloat_5, Min[1400,Max[350,ParticleCustomFloat_1 * 0.4]] + '
            '(%s + %s * ParticleCustomFloat_5) * (sqrt[1 + ParticleElapsedTime div 12] - 1)]' %
            (cfg['cap'], cfg['spread'], cfg['growth'], cfg['variation']))
    if look >= 6:
        size = size.replace('Min[1400,Max[350,ParticleCustomFloat_1 * 0.4]]',
                            'Min[2400,Max[700,ParticleCustomFloat_1 * 0.8]]')
    if look >= 7:
        # Stock vehicle CustomFloat_1 is only 150-300: raising the previous
        # 2400 ceiling never made a normal vehicle puff larger than its 700 floor.
        birth = {'ground': (2200,3400), 'fuel': (2200,3400),
                 'vehicle': (2200,3400), 'starter': (1200,2000), 'wisps': (900,1600)}[kind]
        cap, spread = (6500,2500) if kind in ('ground','fuel','vehicle') else (3600,1000)
        size = ('Min[%s + %s * ParticleCustomFloat_5, '
                'Min[%s,Max[%s,ParticleCustomFloat_1 * 0.8]] * (0.9 + 0.2 * ParticleCustomFloat_5) + '
                '(%s + %s * ParticleCustomFloat_5) * (sqrt[1 + ParticleElapsedTime div 12] - 1)]' %
                (cap,spread,birth[1],birth[0],cfg['growth'],cfg['variation']))
        block = block.replace('MapWind * (0.35 + 0.25 * ParticleCustomFloat_5) + ParticleCustomFloat3_2 * (30 + 70 * MapToLinearSmoothStep[ParticleElapsedTime, 6,45])',
                              'MapWind * (0.2 + 0.1 * ParticleCustomFloat_5) + ParticleCustomFloat3_2 * (10 + 35 * MapToLinearSmoothStep[ParticleElapsedTime, 10,45])')
        block = block.replace('GenFloat3[RandomRange[-60,60], RandomRange[-60,60], RandomRange[120,220]]',
                              'GenFloat3[RandomRange[-20,20], RandomRange[-20,20], RandomRange[120,220]]')
    if look >= 9:
        # Double every vertical driver while leaving drag unchanged. Project
        # wind into horizontal/vertical components so increasing the bend does
        # not also accelerate the rise. Age is a monotonic proxy for ascent.
        block = once(block,
            'Speed = GenFloat3[RandomRange[-20,20], RandomRange[-20,20], RandomRange[120,220]] + 0.15 * MapWind',
            'Speed = GenFloat3[RandomRange[-20,20], RandomRange[-20,20], RandomRange[240,440]] + MapWind * float3[0.05,0.05,0.30]')
        block,n = re.subn(r'(?m)^(\s*PhysicAccelerationField = )(.+)$',r'\g<1>2 * (\g<2>)',block);assert n==1
        bend = 'MapToLinearSmoothStep[ParticleElapsedTime,2,35]'
        block,n = re.subn(r'(?m)^(\s*PhysicWindField = ).+$',
            r'\g<1>MapWind * float3[1,1,0] * (0.08 + 0.62 * sqr['+bend+'] * (3 - 2 * '+bend+')) * (0.8 + 0.4 * ParticleCustomFloat_5) + MapWind * float3[0,0,2] * (0.2 + 0.1 * ParticleCustomFloat_5) + ParticleCustomFloat3_2 * (10 + 35 * MapToLinearSmoothStep[ParticleElapsedTime,10,45])',block);assert n==1
    if look >= 11:
        # Birth velocity must already point downwind; stronger later wind alone
        # leaves the base vertical. Preserve vertical speed and the upper wind.
        block = once(block, 'MapWind * float3[0.05,0.05,0.30]',
                     'MapWind * float3[0.30,0.30,0.30]')
        block = once(block, '(0.08 + 0.62 * sqr[', '(0.30 + 0.40 * sqr[')
        block = block.replace('MapToLinearSmoothStep[ParticleElapsedTime,2,35]',
                              'MapToLinearSmoothStep[ParticleElapsedTime,0,35]')
    if look >= 12:
        # Keep birth size; ease into a hard 2x limit. Age follows ascent without
        # using world height, so mountain maps do not start with enlarged smoke.
        birth_size = ('Min[%s,Max[%s,ParticleCustomFloat_1 * 0.8]] * '
                      '(0.9 + 0.2 * ParticleCustomFloat_5)' % (birth[1],birth[0]))
        growth_time = '30 + 12 * ParticleCustomFloat_5' if kind in ('ground','fuel','vehicle') else '10 + 6 * ParticleCustomFloat_5'
        progress = 'Min[1,Max[0,ParticleElapsedTime div (' + growth_time + ')]]'
        size = '(' + birth_size + ') * (1 + sqr[' + progress + '] * (3 - 2 * ' + progress + '))'
        # Horizontal wind grows faster than vertical drivers, preserving the
        # requested stronger lean despite the 1.5x increase in ascent speed.
        block = once(block, 'RandomRange[240,440]', 'RandomRange[360,660]')
        block = once(block, 'MapWind * float3[0.30,0.30,0.30]',
                     'MapWind * float3[0.54,0.54,0.45]')
        block,n = re.subn(r'(?m)^(\s*PhysicAccelerationField = )2 \* ',r'\g<1>3 * ',block);assert n==1
        block = once(block, '(0.30 + 0.40 * sqr[', '(0.54 + 0.72 * sqr[')
        block = once(block, 'MapWind * float3[0,0,2]', 'MapWind * float3[0,0,3]')
    block, n = re.subn(r'(?m)^(\s*Size = )Min\[30000,.+$', r'\g<1>' + size, block); assert n == 1
    # Preview.4 combined low base alpha, early fade and inverse-area dilution.
    # Restore visible density without changing particle count or growth.
    opacity = ('AttackSustainDecay[ParticleLifeRatio,0.035,0.32] * (%s) * '
               'Min[1,900000 div Max[900000,sqr[ParticleSize]]]' % cfg['alpha'])
    if look >= 5:
        alpha = {'ground': '0.85 * ParticleCustomFloat_2',
                 'fuel': '0.60 * ParticleCustomFloat_6 * ParticleCustomFloat_3',
                 'vehicle': '0.60 * ParticleCustomFloat_6',
                 'starter': '0.18 * ParticleCustomFloat_6',
                 'wisps': '0.16 * ParticleCustomFloat_6'}[kind]
        opacity = ('AttackSustainDecay[ParticleLifeRatio,0.015,0.65] * (%s) * '
                   'Max[0.65,Min[1,2500000 div Max[2500000,sqr[ParticleSize]]]]' % alpha)
    if look >= 6:
        # Fade from 45% life, reaching zero at 97% before engine expiry.
        # Explicit bounded arithmetic avoids relying on an opaque fade intrinsic.
        opacity = opacity.replace('AttackSustainDecay[ParticleLifeRatio,0.015,0.65]',
            'Min[1,Max[0,ParticleLifeRatio div 0.025]] * sqr[Min[1,Max[0,(0.97 - ParticleLifeRatio) div 0.52]]]')
    if look >= 7:
        opacity = opacity.replace('ParticleLifeRatio div 0.025','ParticleElapsedTime div 0.35')
        opacity = opacity.replace('0.18 * ParticleCustomFloat_6','0.32 * ParticleCustomFloat_6')
    block, n = re.subn(r'(?m)^(\s*Opacity = )AttackSustainDecay\[.+$', r'\g<1>' + opacity, block); assert n == 1
    color = 'ColorModifier = lerp[MapToLinearSmoothStep[ParticleElapsedTime,6,50], LinearColor[0.14,0.15,0.16], LinearColor[0.34,0.35,0.36]] * (0.85 + 0.3 * ParticleCustomFloat_5)'
    if look >= 7:
        color = color.replace('LinearColor[0.14,0.15,0.16], LinearColor[0.34,0.35,0.36]',
                              'LinearColor[0.32,0.33,0.34], LinearColor[0.50,0.51,0.52]')
    if look >= 11:
        color = color.replace('LinearColor[0.32,0.33,0.34], LinearColor[0.50,0.51,0.52]',
                              'LinearColor[0.22,0.22,0.22], LinearColor[0.34,0.34,0.34]')
    # Replace the evolver color only; ground smoke previously had no evolver.
    block, n = re.subn(r'(?m)^(\s*)ColorModifier = (?:lerp\[ParticleLifeRatio|ParticleRemainingLifeRatio).+$', r'\g<1>' + color, block)
    if n == 0:
        block = once(block, 'Opacity = ' + opacity, color + '\n                                                                Opacity = ' + opacity)
    else:
        assert n == 1
    return block

def once(text, old, new):
    assert text.count(old) == 1, (old, text.count(old))
    return text.replace(old, new, 1)

def section(text, marker, change):
    a = text.index(marker)
    b = matching(text, text.index('(', a)) + 1
    return text[:a] + change(text[a:b]) + text[b:]

def ground_plume(text, look=12):
    def change(s):
        s = once(s,
            'Speed = ( GenFloat3[0.00, 0.00, RandomRange[0.5, 1.5] + 1.5 * SpawningParticleCustomFloat_3] + 0.2 * SpawningParticleCustomFloat3_2) * SpawningParticleCustomFloat_6 + float3[0,0,1000] + MapWind',
            'Speed = GenFloat3[RandomRange[-60,60], RandomRange[-60,60], RandomRange[120,220]] + 0.15 * MapWind')
        s = once(s, 'FluidFriction = 0.075', 'FluidFriction = 0.18')
        s = once(s, 'float3[0.00, 0.00, 240.00]', 'float3[0.00, 0.00, 35.00]')
        s = once(s, 'PhysicWindField = MapWind * lerp[ParticleCustomFloat_5, 2.0, 1.0]',
                 'PhysicWindField = MapWind * lerp[ParticleCustomFloat_5, 0.45, 0.25]')
        # Random size/growth is fixed at birth, avoiding frame-to-frame flicker.
        s = once(s, 'CustomFloat_5 = SpawningParticleCustomFloat_9', 'CustomFloat_5 = RandomUnit')
        s = once(s, 'Size = Min[16000, ParticleCustomFloat_1 * (0.5 + 2.5 * ParticleLifeRatio)]',
                 'Size = Min[30000, Max[600, ParticleCustomFloat_1 * 0.5] + (220 + 120 * ParticleCustomFloat_5) * ParticleElapsedTime]')
        return layered_smoke(s, 'ground', look) if look >= 4 else s
    return section(text, 'Smoke is EvolverSpraySpawner', change)

def fuel_plume(text, look=12):
    def change(s):
        s = once(s, 'Speed = float3[0,0,1600] + 0.4 * SpawningParticleRemainingLifeRatio * ( ParticleCustomFloat3_3 * RandomRange[0.5, 1.5] + $/VFX_Bank/MinusOneToOneRandomHemisphereVolume * 500 )',
                 'Speed = GenFloat3[RandomRange[-60,60], RandomRange[-60,60], RandomRange[120,220]] + 0.15 * MapWind')
        s = once(s, 'FluidFriction = 0.12', 'FluidFriction = 0.18')
        s = once(s, 'float3[0.00, 0.00, 240.00]', 'float3[0.00, 0.00, 35.00]')
        s = once(s, 'PhysicWindField = 0.5 * ParticleCustomFloat3_3', 'PhysicWindField = 0.35 * MapWind')
        s = once(s, 'Size = Min[16000, ( ParticleCustomFloat_1 + ( lerp[ParticleCustomFloat_5, 300, 100] * ParticleElapsedTime ) ) * ParticleCustomFloat_2]', 'Size = ' + PLUME_SIZE)
        return section(s, 'EvolverSpraySpawner', lambda b: layered_smoke(b, 'fuel', look)) if look >= 4 else s
    return section(text, 'export BA_BurningFuelSmoke is', change)

def dark_plume(text, look=12):
    # Three smoke layers, scoped so neither of the two flame layers is edited.
    layers = [
        ('private fumees_Starter is ParticleBombSpawner', 80,
         'RandomRange[5, 8]', '0.33', '0.033'),
        ('public fumees is ParticleBombSpawner', 1250,
         'SpawningParticleCustomFloat_3 * 20 + RandomRange[3, 7] * 15', None, None),
        ('private Flame_Starter_Dark is ParticleBombSpawner', 60,
         'RandomRange[1, 3] * 2', '0.1', '0.01'),
    ]
    for marker, maximum, life, attack, new_attack in layers:
        def change(s):
            # Only the spray's frequency is scaled, not its parent's lifetime.
            s, n = re.subn(r'(?m)^(\s*Frequency = )(.+)$', r'\g<1>10 * (\g<2>)', s)
            assert n == 1
            s, n = re.subn(r'MaxSpawnedParticleLifetime = \d+', 'MaxSpawnedParticleLifetime = %s' % maximum, s)
            assert n == 1
            s = once(s, 'ParticleLifetime = ' + life, 'ParticleLifetime = 10 * (' + life + ')')
            s, n = re.subn(r'(?m)^(\s*Speed = ).+$', r'\g<1>GenFloat3[RandomRange[-60,60], RandomRange[-60,60], RandomRange[120,220]] + 0.15 * MapWind', s)
            assert n == 1
            s, n = re.subn(r'FluidFriction = [0-9.]+', 'FluidFriction = 0.18', s); assert n == 1
            s, n = re.subn(r'(?m)^(\s*PhysicAccelerationField = ).+$', r'\g<1>float3[0,0,35] * (0.6 + 0.4 * ParticleRemainingLifeRatio)', s); assert n == 1
            s, n = re.subn(r'(?m)^(\s*PhysicWindField = ).+$', r'\g<1>0.35 * MapWind', s); assert n == 1
            # Source shutdown fade must not use a smoke particle's new long life.
            s = once(s, 'SpawningParticleDuration - ParticleDuration * 2', 'Max[0, SpawningParticleDuration - 8]')
            old_size = ('( ParticleCustomFloat_1 + ( lerp[ParticleCustomFloat_5, 300, 100] * ParticleElapsedTime ) ) * ParticleCustomFloat_2'
                        if maximum == 1250 else '( ParticleCustomFloat_1 + ( 200 * ParticleElapsedTime ) ) * ParticleCustomFloat_2')
            s = once(s, 'Size = ' + old_size, 'Size = ' + PLUME_SIZE)
            if attack:
                s = once(s, 'AttackSustainDecay[ParticleLifeRatio, ' + attack + ',', 'AttackSustainDecay[ParticleLifeRatio, ' + new_attack + ',')
            else:
                s = once(s, 'AttackSustainDecay[ParticleLifeRatio, ParticleCustomFloat_4,', 'AttackSustainDecay[ParticleLifeRatio, ParticleCustomFloat_4 * 0.1,')
            kind = {80: 'starter', 1250: 'vehicle', 60: 'wisps'}[maximum]
            return section(s, 'EvolverSpraySpawner', lambda b: layered_smoke(b, kind, look)) if look >= 4 else s
        text = section(text, marker, change)
    return text

def cadaver_duration(text):
    text = once(text, 'export CadaverPeriodeEnFeu_Minimum is 1\n', 'export CadaverPeriodeEnFeu_Minimum is 10\n')
    return once(text, 'export CadaverPeriodeEnFeu_Maximum is 120\n', 'export CadaverPeriodeEnFeu_Maximum is 1200\n')

def vehicle_fuel_durations(text):
    """Extend only fuel fire/smoke calls in vehicle explosion files, not flashes."""
    changes, records = [], []
    for m in re.finditer(r'(?:Template_ActionCall|TActionCall)\s*\(', text):
        end = matching(text, text.index('(', m.start())) + 1
        block = text[m.start():end]
        action = re.search(r'Action = (\$/VFX_Bank/(?:BANK_FuelFire|BA_BurningFuelSmoke))\s', block)
        if not action:
            continue
        pattern = r"(\(\s*'parDuration'\s*,\s*)([0-9.]+)(\s*\))"
        duration = re.search(pattern, block)
        assert duration, action.group(1)
        seconds = float(duration.group(2))
        new, n = re.subn(pattern, lambda m: m.group(1) + ('%g' % (10 * seconds)) + m.group(3), block)
        assert n == 1
        changes.append((m.start(), end, new))
        records.append(dict(action=action.group(1), before=seconds, after=seconds * 10))
    for a, b, new in reversed(changes):
        text = text[:a] + new + text[b:]
    return text, records
