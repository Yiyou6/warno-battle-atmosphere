"""Check source scope and compiled CNDF references, not rendered smoke quality."""
from pathlib import Path
import json
import struct
import subprocess
import sys
from read_cndf import Cndf
from apply_smoke_profile import DEV, MOD, ROOT, OLD, NEW, sha, protected_files

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

def main():
    subprocess.run([sys.executable, str(DEV / 'apply_smoke_profile.py')], check=True)
    source = json.loads((DEV / 'smoke-source.json').read_text())
    build = json.loads((DEV / 'smoke-build.json').read_text())
    assert build['sources'] == source['sources']
    assert build['protected'] == protected_files()
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
    for name, minimum in ((NEW, 24), ('$/VFX_Bank/FX_BANK_Binder_Fire', 18)):
        graph = reachable(bank, exports[name])
        constants = [o['properties'].get('Value') for o in graph
                     if o['class'] in ('TConstantFloat', 'TConstantInteger')]
        assert minimum in constants and 36 in constants and 16000 in constants, name
        spawners = [o for o in graph if o['class'] == 'TParticleEvolver_SpraySpawner']
        maxima = [bank.objects[o['properties']['MaxSpawnedParticleLifetime']['ref']]['properties'].get('Value')
                  for o in spawners if 'ref' in o['properties'].get('MaxSpawnedParticleLifetime', {})]
        assert 36 in maxima, name
    result = dict(version='smoke-preview.1', status='source-and-compiled-references-passed; visual-unverified',
                  compiled_calls=calls, protected=build['protected'], sources=build['sources'],
                  outputs=build['outputs'], bank_objects=len(bank.objects), fx_objects=len(fx.objects))
    (DEV / 'smoke-verification.json').write_text(json.dumps(result, indent=2) + '\n')
    print('PASS: 64 burning placements use dedicated bank; 193 other placements retain stock bank; lifetime/size bounds compiled')

if __name__ == '__main__':
    main()
