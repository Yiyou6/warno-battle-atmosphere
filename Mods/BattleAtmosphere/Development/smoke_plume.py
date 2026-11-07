"""Preview.3 plume and wreck-source changes; no global weapon/fire changes."""
import re
from apply_profile import matching

DARK = 'GameData/Fx/Bank/composite/BANK_DarkFire.ndf'
CADAVER = 'GameData/Gameplay/Gfx/CadaverConstants.ndf'
PLUME_SIZE = 'Min[30000, (Max[600, ParticleCustomFloat_1 * 0.5] + (220 + 120 * ParticleCustomFloat_5) * ParticleElapsedTime) * ParticleCustomFloat_2]'

def once(text, old, new):
    assert text.count(old) == 1, (old, text.count(old))
    return text.replace(old, new, 1)

def section(text, marker, change):
    a = text.index(marker)
    b = matching(text, text.index('(', a)) + 1
    return text[:a] + change(text[a:b]) + text[b:]

def ground_plume(text):
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
        return s
    return section(text, 'Smoke is EvolverSpraySpawner', change)

def fuel_plume(text):
    def change(s):
        s = once(s, 'Speed = float3[0,0,1600] + 0.4 * SpawningParticleRemainingLifeRatio * ( ParticleCustomFloat3_3 * RandomRange[0.5, 1.5] + $/VFX_Bank/MinusOneToOneRandomHemisphereVolume * 500 )',
                 'Speed = GenFloat3[RandomRange[-60,60], RandomRange[-60,60], RandomRange[120,220]] + 0.15 * MapWind')
        s = once(s, 'FluidFriction = 0.12', 'FluidFriction = 0.18')
        s = once(s, 'float3[0.00, 0.00, 240.00]', 'float3[0.00, 0.00, 35.00]')
        s = once(s, 'PhysicWindField = 0.5 * ParticleCustomFloat3_3', 'PhysicWindField = 0.35 * MapWind')
        s = once(s, 'Size = Min[16000, ( ParticleCustomFloat_1 + ( lerp[ParticleCustomFloat_5, 300, 100] * ParticleElapsedTime ) ) * ParticleCustomFloat_2]', 'Size = ' + PLUME_SIZE)
        return s
    return section(text, 'export BA_BurningFuelSmoke is', change)

def dark_plume(text):
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
            return s
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
