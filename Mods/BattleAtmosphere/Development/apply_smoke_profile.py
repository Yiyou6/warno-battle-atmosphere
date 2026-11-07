"""Bounded burning smoke, isolated from ordinary shell/weapon smoke. No launch."""
from pathlib import Path
import argparse
import hashlib
import json
import re
import zipfile
from apply_profile import matching, object_span

DEV = Path(__file__).resolve().parent
MOD = DEV.parent
ROOT = MOD.parents[1]
BINDER = 'GameData/Fx/Bank/Basics/BANK_Binder_Fire.ndf'
FUEL = 'GameData/Fx/Bank/Basics/BANK_FuelFire.ndf'
OLD = '$/VFX_Bank/BANK_FuelSmoke'
NEW = '$/VFX_Bank/BA_BurningFuelSmoke'
VERSION = 'smoke-preview.2'
MULTIPLIER = 10
BACKUP = 'archive/smoke-preview2-before.zip'

def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def once(text, old, new):
    assert text.count(old) == 1, (old, text.count(old))
    return text.replace(old, new, 1)

def ground(text, multiplier=MULTIPLIER):
    start = text.index('Smoke is EvolverSpraySpawner')
    end = matching(text, text.index('(', start)) + 1
    block = text[start:end]
    changes = [
        ('Frequency = ParticleCustomFloat_7 * ParticleRemainingLifeRatio * 0.75',
         'Frequency = ParticleCustomFloat_7 * ParticleRemainingLifeRatio'),
        ('MaxSpawnedParticleLifetime = 4.9', 'MaxSpawnedParticleLifetime = 36'),
        ('ParticleLifetime = SpawningParticleCustomFloat_5 * RandomRange[0.5,2] * SpawningParticleCustomFloat_3',
         'ParticleLifetime = Min[36, Max[18, SpawningParticleCustomFloat_5 * RandomRange[0.5,2] * SpawningParticleCustomFloat_3]]'),
        ('+ SpawningParticleCustomFloat3_2) * SpawningParticleCustomFloat_6 + 2 * MapWind',
         '+ 0.2 * SpawningParticleCustomFloat3_2) * SpawningParticleCustomFloat_6 + float3[0,0,1000] + MapWind'),
        ('PhysicAccelerationField = float3[0.00, 0.00, 3.00] * sqr[ParticleRemainingLifeRatio]',
         'PhysicAccelerationField = float3[0.00, 0.00, 240.00] * (0.6 + 0.4 * ParticleRemainingLifeRatio)'),
        ('PhysicWindField = MapWind * lerp[ParticleCustomFloat_5, 6, 3]',
         'PhysicWindField = MapWind * lerp[ParticleCustomFloat_5, 2.0, 1.0]'),
        ('Opacity = AttackSustainDecay[ParticleLifeRatio, 0.1, 0.25] * ParticleCustomFloat_2',
         'Opacity = AttackSustainDecay[ParticleLifeRatio, 0.08, 0.65] * ParticleCustomFloat_2'),
        ('Size = ParticleCustomFloat_1 * (0.5 + 2.5 * ParticleLifeRatio)',
         'Size = Min[16000, ParticleCustomFloat_1 * (0.5 + 2.5 * ParticleLifeRatio)]'),
    ]
    if multiplier != 1:
        # Scale the entire bounded expression, so no caller/random sample loses
        # the requested increase to the preview.1 clamps.
        changes += [
            ('Frequency = ParticleCustomFloat_7 * ParticleRemainingLifeRatio',
             'Frequency = %s * (ParticleCustomFloat_7 * ParticleRemainingLifeRatio)' % multiplier),
            ('MaxSpawnedParticleLifetime = 36', 'MaxSpawnedParticleLifetime = %s' % (36 * multiplier)),
            ('ParticleLifetime = Min[36, Max[18, SpawningParticleCustomFloat_5 * RandomRange[0.5,2] * SpawningParticleCustomFloat_3]]',
             'ParticleLifetime = %s * Min[36, Max[18, SpawningParticleCustomFloat_5 * RandomRange[0.5,2] * SpawningParticleCustomFloat_3]]' % multiplier),
            # Keep the same absolute fade-in time despite the longer life.
            ('AttackSustainDecay[ParticleLifeRatio, 0.08, 0.65]',
             'AttackSustainDecay[ParticleLifeRatio, %s, 0.65]' % (0.08 / multiplier)),
        ]
    for old, new in changes:
        block = once(block, old, new)
    return text[:start] + block + text[end:]

def fuel(text, multiplier=MULTIPLIER):
    a, b = object_span(text, 'BANK_FuelSmoke')
    block = text[a:b]
    changes = [
        ('export BANK_FuelSmoke is', 'export BA_BurningFuelSmoke is'),
        ('Frequency = 5', 'Frequency = Min[4, Max[1.5, ParticleCustomFloat_2]]'),
        ('MaxSpawnedParticleLifetime = 20', 'MaxSpawnedParticleLifetime = 36'),
        ('ParticleLifetime = SpawningParticleCustomFloat_6 * (1.4 + SpawningParticleCustomFloat_3)',
         'ParticleLifetime = Min[36, Max[24, SpawningParticleCustomFloat_6 * (1.4 + SpawningParticleCustomFloat_3)]]'),
        ('Speed = SpawningParticleRemainingLifeRatio * ( ParticleCustomFloat3_3 * RandomRange[0.5, 1.5] + $/VFX_Bank/MinusOneToOneRandomHemisphereVolume * 500 )',
         'Speed = float3[0,0,1600] + 0.4 * SpawningParticleRemainingLifeRatio * ( ParticleCustomFloat3_3 * RandomRange[0.5, 1.5] + $/VFX_Bank/MinusOneToOneRandomHemisphereVolume * 500 )'),
        ('FluidFriction = 0.75', 'FluidFriction = 0.12'),
        ('PhysicAccelerationField = float3[0.00, 0.00, 200.00]',
         'PhysicAccelerationField = float3[0.00, 0.00, 240.00]'),
        ('PhysicWindField = ParticleCustomFloat3_3', 'PhysicWindField = 0.5 * ParticleCustomFloat3_3'),
        ('Size = ( ParticleCustomFloat_1 + ( lerp[ParticleCustomFloat_5, 300, 100] * ParticleElapsedTime ) ) * ParticleCustomFloat_2',
         'Size = Min[16000, ( ParticleCustomFloat_1 + ( lerp[ParticleCustomFloat_5, 300, 100] * ParticleElapsedTime ) ) * ParticleCustomFloat_2]'),
    ]
    if multiplier != 1:
        changes += [
            ('Frequency = Min[4, Max[1.5, ParticleCustomFloat_2]]',
             'Frequency = %s * Min[4, Max[1.5, ParticleCustomFloat_2]]' % multiplier),
            ('MaxSpawnedParticleLifetime = 36', 'MaxSpawnedParticleLifetime = %s' % (36 * multiplier)),
            ('ParticleLifetime = Min[36, Max[24, SpawningParticleCustomFloat_6 * (1.4 + SpawningParticleCustomFloat_3)]]',
             'ParticleLifetime = %s * Min[36, Max[24, SpawningParticleCustomFloat_6 * (1.4 + SpawningParticleCustomFloat_3)]]' % multiplier),
        ]
    for old, new in changes:
        block = once(block, old, new)
    # Keep the original public bank byte-for-byte (after newline decoding).
    return text + '\n// BattleAtmosphere: burning wrecks only; weapons retain BANK_FuelSmoke.\n' + block + '\n'

def expected_files():
    with zipfile.ZipFile(MOD / 'base.zip') as z:
        def read(name):
            return z.read(name).decode('utf-8-sig').replace('\r\n', '\n')
        before = {BINDER: read(BINDER), FUEL: read(FUEL)}
        after = {BINDER: ground(before[BINDER]), FUEL: fuel(before[FUEL])}
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
                callers.append({'path': name, 'calls': text.count(OLD)})
            else:
                assert (MOD / name).read_text(encoding='utf-8-sig') == text, name
                excluded.append(name)
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

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write', action='store_true')
    args = parser.parse_args()
    before, after, callers, excluded = expected_files()
    for name, target in after.items():
        current = (MOD / name).read_text(encoding='utf-8-sig')
        previous = ground(before[name], 1) if name == BINDER else fuel(before[name], 1) if name == FUEL else target
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
    assert protected_files() == protected
    report = dict(version=VERSION, status='source-verified; visual-unverified',
                  relative_to='smoke-preview.1', lifetime_multiplier=MULTIPLIER,
                  emission_multiplier=MULTIPLIER,
                  sources={n: sha(MOD / n) for n in after}, protected=protected,
                  burning_callers=callers, unchanged_shared_smoke_callers=excluded,
                  backup=archive.relative_to(MOD).as_posix())
    if archive.exists():
        with zipfile.ZipFile(archive) as z:
            assert json.loads(z.read('protected.json')) == protected, 'Protected inputs changed since smoke work began'
    (DEV / 'smoke-source.json').write_text(json.dumps(report, indent=2) + '\n')
    print('PASS: %d source files, %d burning callers, %d shared-smoke callers unchanged; AI/gameplay/DLL unchanged' % (len(after), len(callers), len(excluded)))

if __name__ == '__main__':
    main()
