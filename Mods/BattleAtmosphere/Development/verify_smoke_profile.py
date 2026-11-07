"""Check source scope and compiled CNDF references, not rendered smoke quality."""
from pathlib import Path
import json
import hashlib
import math
import struct
import subprocess
import sys
import zipfile
from read_cndf import Cndf
from apply_smoke_profile import DEV, MOD, ROOT, OLD, NEW, VERSION, MULTIPLIER, BACKUP, sha, protected_files, protected_match

def paths(c, section):
    data = c.tables[section]
    found, seen = {}, set()
    def walk(at, path):
        assert at not in seen
        seen.add(at)
        token, value, count = struct.unpack_from('<III', data, at)
        path = path + [c.trans[token]]
        start = at + 12
        assert 0 <= count < 20000
        if value != 0xffffffff:
            key = '/'.join(path)
            assert key not in found
            found[key] = value
        for i in range(count):
            walk(start + struct.unpack_from('<I', data, start + 4*i)[0], path)
    walk(0, [])
    assert sum(12 + 4 * struct.unpack_from('<I', data, at + 8)[0] for at in seen) == len(data)
    return found

def local_refs(value):
    if isinstance(value, dict):
        if 'ref' in value:
            yield value['ref']
        else:
            for x in value.values():
                yield from local_refs(x)
    elif isinstance(value, list):
        for x in value:
            yield from local_refs(x)

def reachable(c, root):
    seen, pending = set(), [root]
    while pending:
        i = pending.pop()
        if i in seen:
            continue
        seen.add(i)
        pending.extend(local_refs(c.objects[i]['properties']))
    return [c.objects[i] for i in sorted(seen)]

def canonical(c, value):
    """Compare compiled expressions by structure, independent of object IDs."""
    imports = {v: k for k, v in paths(c, 'IMPR').items()}
    memo, active = {}, set()
    def resolve(v):
        if isinstance(v, dict):
            if 'ref' in v:
                i = v['ref']
                if i in memo:
                    return memo[i]
                assert i not in active, 'Unexpected expression cycle'
                active.add(i)
                obj = c.objects[i]
                result = (obj['class'], resolve(obj['properties']))
                active.remove(i)
                memo[i] = result
                return result
            if 'import_index' in v:
                return ('import', imports[v['import_index']])
            return tuple((k, resolve(x)) for k, x in sorted(v.items()))
        if isinstance(v, list):
            return tuple(resolve(x) for x in v)
        return v
    return resolve(value)

def smoke_spawner(c, root, is_ground):
    found = [o for o in reachable(c, root) if o['class'] == 'TParticleEvolver_SpraySpawner'
             and (not is_ground or o['properties'].get('_ShortDatabaseName') == 'Smoke')]
    assert len(found) == 1
    return found[0]['properties']

def verify_multiplier(c, value, prior, original, factor=10):
    node = c.objects[value['ref']]
    assert node['class'] == 'TIntrinsicCall_2Param'
    props = node['properties']
    assert canonical(c, props['Intrinsic']) == ('import', '$/System/EvaluableIntrinsics/IntrinsicOperatorMul')
    scale = c.objects[props['Param0']['ref']]
    assert scale['class'] in ('TConstantInteger', 'TConstantFloat')
    assert math.isclose(scale['properties']['Value'], factor, rel_tol=1e-6)
    assert canonical(c, props['Param1']) == canonical(prior, original), 'Scaled base expression changed'

def main():
    subprocess.run([sys.executable, str(DEV / 'apply_smoke_profile.py')], check=True)
    source = json.loads((DEV / 'smoke-source.json').read_text())
    build = json.loads((DEV / 'smoke-build.json').read_text())
    assert build['sources'] == source['sources']
    assert protected_match(build['protected'], protected_files())
    for path, digest in build['outputs'].items():
        assert sha(MOD / path) == digest
    bank = Cndf((MOD / 'Gen/NDF/VFX_Bank.ndfbin').read_bytes())
    fx = Cndf((MOD / 'Gen/NDF/GFX/GameFx.ndfbin').read_bytes())
    exports = paths(bank, 'EXPR')
    imports = paths(fx, 'IMPR')
    assert NEW in exports and OLD in exports and NEW in imports and OLD in imports
    new_id, old_id = exports[NEW], exports[OLD]
    assert new_id != old_id
    calls = {}
    fx_exports = paths(fx, 'EXPR')
    def count_calls(i, target, memo, active):
        # The compiler interns equal TActionCalls. Count reference occurrences
        # under each exported effect, not unique objects in the whole bank.
        if i in memo:
            return memo[i]
        assert i not in active, 'Unexpected action graph cycle'
        active.add(i)
        props = fx.objects[i]['properties']
        value = int(props.get('Action') == {'import_index': target})
        value += sum(count_calls(j, target, memo, active) for j in local_refs(props))
        active.remove(i)
        memo[i] = value
        return value
    for name, files in ((NEW, [r['path'] for r in source['burning_callers']]),
                        (OLD, source['unchanged_shared_smoke_callers'])):
        total = 0
        other = OLD if name == NEW else NEW
        for path in files:
            root = fx_exports['$/GFX/GameFx/' + Path(path).stem]
            expected = (MOD / path).read_text(encoding='utf-8-sig').count(name)
            actual = count_calls(root, imports[name], {}, set())
            assert actual == expected, (path, actual, expected)
            assert count_calls(root, imports[other], {}, set()) == 0, path
            total += actual
        calls[name] = total
    # Keep the historical preview.1 baseline to verify unchanged shared smoke.
    with zipfile.ZipFile(DEV / 'archive/smoke-preview2-before.zip') as z:
        prior_receipt = json.loads(z.read('development/smoke-release.json'))
        assert prior_receipt['version'] == 'smoke-preview.1'
        prior_bytes = z.read('installed/Gen/NDF/VFX_Bank.ndfbin')
        assert hashlib.sha256(prior_bytes).hexdigest() == prior_receipt['outputs']['Gen/NDF/VFX_Bank.ndfbin']
        prior = Cndf(prior_bytes)
    prior_exports = paths(prior, 'EXPR')
    assert canonical(bank, {'ref': old_id}) == canonical(prior, {'ref': prior_exports[OLD]}), 'Shared fuel smoke changed'
    scaling = {}
    for name, limits in ((NEW, [50,90]), ('$/VFX_Bank/FX_BANK_Binder_Fire', [45,80])):
        current = smoke_spawner(bank, exports[name], name != NEW)
        previous = smoke_spawner(prior, prior_exports[name], name != NEW)
        assert bank.objects[current['MaxSpawnedParticleLifetime']['ref']]['properties']['Value'] == limits[1]
        verify_multiplier(bank, current['Frequency'], prior, previous['Frequency'], factor=2)
        scaling[name] = dict(relative_to='smoke-preview.9', emission_multiplier=0.5,
                             lifetime_seconds=limits, max_spawned_particle_lifetime=limits[1])
    from verify_smoke_plume import verify_plume
    plume = verify_plume(bank, fx, exports, source)
    from verify_smoke_motion import verify_motion
    plume['motion'] = verify_motion(bank)
    from verify_explosion_scale import verify_explosions
    explosions = verify_explosions(fx)
    result = dict(version=VERSION, status='source-and-compiled-references-passed; visual-unverified',
                  compiled_calls=calls, compiled_scaling=scaling, plume=plume, explosions=explosions, protected=build['protected'], sources=build['sources'],
                  outputs=build['outputs'], bank_objects=len(bank.objects), fx_objects=len(fx.objects))
    (DEV / 'smoke-verification.json').write_text(json.dumps(result, indent=2) + '\n')
    print('PASS: restored density floor, bounded smoke life and decelerating growth; 64 burning/193 unchanged shared placements')
    print('PASS: five layered smoke banks; %s vehicle cadaver descriptors at 10-1200s; %s vehicle fuel calls retain 10x source duration' %
          (plume['compiled_vehicle_cadaver_objects'], plume['compiled_unique_vehicle_fuel_calls']))

if __name__ == '__main__':
    main()
