"""Rebuild the reviewed first-version AI profile from the verified official baseline.

Run with the game's bundled Python from any directory. Existing manual edits are
protected. --check validates the expected source tree without writing anything.
The official GenerateMod.py remains the authority for NDF compilation.
"""
from pathlib import Path
import argparse
import difflib
import hashlib
import json
import re
import sys
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parent))

ROOT = Path(__file__).resolve().parents[1]
BASE_SHA256 = '422528b6895c4185a2585667faeb45465f4ec8415bbc4f5b2b41df967edc4e3f'
MACROS = 'GameData/Gameplay/Skirmish/SkirmishMacros/'
STRATEGIES = 'GameData/Gameplay/Skirmish/Strategies/'
from release_info import VERSION


def sha(data):
    return hashlib.sha256(data).hexdigest()


def replace(text, old, new, count=1):
    actual = text.count(old)
    if actual != count:
        raise ValueError(f'Expected {count} occurrences, got {actual}: {old!r}')
    return text.replace(old, new)


def matching(text, start):
    """Find a balanced NDF delimiter, ignoring strings and comments."""
    pairs = {'[': ']', '(': ')', '{': '}'}
    stack = [pairs[text[start]]]
    i = start + 1
    while i < len(text):
        if text.startswith('//', i):
            pos = text.find('\n', i)
            i = len(text) if pos < 0 else pos + 1
            continue
        if text.startswith('/*', i):
            pos = text.find('*/', i + 2)
            if pos < 0:
                raise ValueError('Unterminated comment')
            i = pos + 2
            continue
        char = text[i]
        if char in "\"'":
            quote = char
            i += 1
            while i < len(text) and text[i] != quote:
                i += 2 if text[i] == '\\' else 1
        elif char in pairs:
            stack.append(pairs[char])
        elif char in ']})':
            if not stack or char != stack.pop():
                raise ValueError(f'Mismatched delimiter at {i}')
            if not stack:
                return i
        i += 1
    raise ValueError('Unterminated block')


def object_span(text, name):
    found = list(re.finditer(r'(?m)^(?:export )?' + re.escape(name) + r' is [A-Za-z_][A-Za-z_0-9]*\s*\(', text))
    if len(found) != 1:
        raise ValueError(f'Expected exactly one object: {name}')
    start = found[0].start()
    opening = text.index('(', found[0].start())
    return start, matching(text, opening) + 1


def edit_object(text, name, edit):
    a, b = object_span(text, name)
    return text[:a] + edit(text[a:b]) + text[b:]


def list_value(text, field, entries):
    m = re.search(r'\b' + re.escape(field) + r'\s*=\s*\[', text)
    if not m:
        raise ValueError(f'List not found: {field}')
    start = text.index('[', m.start())
    end = matching(text, start) + 1
    # Remove the old appended shuffle too, or late vanilla tasks get duplicated.
    suffix = re.match(r'\s*\+\s*~/\w+', text[end:])
    if suffix:
        end += suffix.end()
    value = '[\n' + ''.join(f'        ~/{e},\n' for e in entries) + '    ]'
    return text[:start] + value + text[end:]


def phase(text, name, generators, scaling):
    def update(block):
        block = list_value(block, 'GeneratorList', generators)
        m = re.search(r'ScalingGeneratorList\s*=\s*~/\w+', block)
        if not m:
            raise ValueError('Scaling reference not found: ' + name)
        value = 'ScalingGeneratorList = [\n' + ''.join(f'        ~/{e},\n' for e in scaling) + '    ]'
        return block[:m.start()] + value + block[m.end():]
    return edit_object(text, name, update)


def pool(name, budget, slots):
    """Reuse existing slot GUIDs; no new pool element identities are introduced."""
    output = f'export {name} is TPoolModel\n(\n    Budget = ~/{budget}\n    ModelList = [\n'
    for guid, tags, quantity, price in slots:
        output += ('        TPoolElement(\n'
                   f'            DescriptorId = GUID:{{{guid}}}\n'
                   '            Required = false\n'
                   '            IndexPriorityOverPrice = true\n'
                   f'            Nb = {quantity}\n'
                   f'            PriceComparisonMethod = EPriceComparatorType/{price}\n'
                   '            TagsPriority = [' + ', '.join(f'"{tag}"' for tag in tags) + ']\n'
                   '        ),\n')
    return output + '    ]\n)'


def make_profile(base):
    from profile_v3 import make_profile as build
    return build(base, (replace, edit_object, object_span, phase, pool, matching))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    if not args.check and (ROOT / 'Development/FROZEN.txt').exists():
        raise SystemExit('Draft frozen. Complete SKIRMISH_DESIGN.md decisions before applying gameplay changes.')
    archive = ROOT / 'base.zip'
    if sha(archive.read_bytes()) != BASE_SHA256:
        raise SystemExit('Baseline changed: audit the new game version before applying this profile.')
    if sha((ROOT.parent / 'ModData/base.zip').read_bytes()) != BASE_SHA256:
        raise SystemExit('Official template updated: rebase and review before building.')
    with zipfile.ZipFile(str(archive)) as z:
        original = {n: z.read(n) for n in z.namelist() if n.endswith('.ndf')}
    base = {n: data.decode('utf-8-sig').replace('\r\n', '\n') for n, data in original.items()}
    profile = make_profile(base)
    manifest_path = ROOT / 'Development/manifest.json'
    previous = json.loads(manifest_path.read_text(encoding='utf-8')) if manifest_path.exists() else {}
    old_outputs = {x['path']: x['modified_sha256'] for x in previous.get('files', [])}
    # Validate the entire tracked source tree before any writes. Do not silently
    # overwrite user changes, whether inside or outside our intended file set.
    for name, original_bytes in original.items():
        current = (ROOT / name).read_bytes()
        expected = profile.get(name, base[name])
        if args.check:
            if current.decode('utf-8-sig').replace('\r\n', '\n') != expected:
                raise SystemExit('Unexpected source difference: ' + name)
        elif sha(current) not in (sha(original_bytes), old_outputs.get(name), sha(expected.encode('utf-8'))):
            raise SystemExit('Manual source edit protected: ' + name)
    # The corrected support request must match actual unit tags in this build.
    units = base['GameData/Generated/Gameplay/Gfx/UniteDescriptor.ndf']
    tag_counts = {tag: len(re.findall(r'"' + tag + r'"', units))
                  for tag in ['Avion_Bombardier', 'Avion_AT', 'Avion_Napalm']}
    if not all(tag_counts.values()):
        raise SystemExit('Support request contains a tag with no static unit match.')
    manifest = {'version': VERSION, 'baseline_sha256': BASE_SHA256,
                'support_tag_static_matches': tag_counts, 'files': []}
    changes = []
    for name, modified in profile.items():
        data = modified.encode('utf-8')
        manifest['files'].append({'path': name, 'baseline_sha256': sha(original[name]),
                                  'modified_sha256': sha(data)})
        changes.extend(difflib.unified_diff(base[name].splitlines(True), modified.splitlines(True),
                                           fromfile='vanilla/' + name, tofile='BattleAtmosphere/' + name))
        if not args.check:
            (ROOT / name).write_bytes(data)
    if not args.check:
        # Remove rejected experiments too, but only after the full-tree guard.
        for name in old_outputs:
            if name not in profile:
                (ROOT / name).write_bytes(original[name])
        manifest_path.write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
        (ROOT / 'Development/profile.diff').write_text(''.join(changes), encoding='utf-8')
    print(f'{"Verified" if args.check else "Applied"} {VERSION}: {len(profile)} changed NDF files; '
          f'{len(original)} baseline source files checked.')
    print('Actual static aircraft tag matches:', tag_counts)


if __name__ == '__main__':
    main()
