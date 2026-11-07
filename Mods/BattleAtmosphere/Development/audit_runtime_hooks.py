"""Read-only runtime-extension investigation, not a script loader or game adapter.

Uses pefile/xdis installed in a separate TEMP research directory. XYZ payloads
are decompressed and disassembled as data; never exec/import game bytecode.
"""
from pathlib import Path
import hashlib
import json
import os
import sys
import zlib

HERE = Path(__file__).resolve().parent
GAME = HERE.parents[2]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(Path(os.environ['TEMP']) / 'codex-warno-nativeaudit'))
from read_edat import Edat
import pefile
from xdis.unmarshal import load_code


def sha(data):
    return hashlib.sha256(data).hexdigest()


def describe_code(code):
    result = {'name': code.co_name, 'line': code.co_firstlineno,
              'arguments': list(code.co_varnames[:code.co_argcount]),
              'names': list(code.co_names)}
    children = [describe_code(c) for c in code.co_consts if hasattr(c, 'co_code')]
    if children:
        result['children'] = children
    return result


def main():
    dll_path = GAME / 'ExternalApi.dll'
    pe = pefile.PE(str(dll_path), fast_load=True)
    pe.parse_data_directories(directories=[0, 1])
    exports = sorted(s.name.decode() for s in pe.DIRECTORY_ENTRY_EXPORT.symbols if s.name)
    imports = sorted(m.dll.decode() for m in pe.DIRECTORY_ENTRY_IMPORT)
    sources = {}
    packs = sorted((GAME / 'Data').rglob('ZZ_5.dat'), key=lambda p: int(p.parent.name))
    suffixes = ['Eugen/effetmapmultiplayer.xyz', 'Eugen/leveldesign/launcher.xyz',
                'Eugen/leveldesign/descriptor.xyz', 'EugenSolo/leveldesignsolo/units.xyz',
                'EugenSolo/leveldesignsolo_specific/units.xyz',
                'EugenSolo/leveldesignsolo_specific/missions.xyz']
    # Overlay order here follows increasing directory revision. This is an
    # inventory of observed packs, not a claim about final engine mount order.
    for path in packs:
        archive = Edat(path)
        for name in archive.files:
            if '/F1/Python/' not in name or not any(name.endswith(s) for s in suffixes):
                continue
            data = archive.read(name)
            if data[:4] != b'XYZ0':
                raise ValueError('Unexpected script envelope')
            payload = zlib.decompress(data[28:])
            # Store the envelope verbatim; no format-writing assumptions.
            code = load_code(payload, 62131, code_objects={})  # CPython 2.5 marshal
            sources[name] = {
                'pack': path.relative_to(GAME).as_posix(),
                'packed_sha256': sha(data), 'packed_bytes': len(data),
                'envelope_hex': data[:28].hex(),
                'uncompressed_bytes': len(payload), 'source_filename': code.co_filename,
                'symbols': describe_code(code),
            }
    common = Edat(GAME / 'Data/PC/169425/DataCommon.dat')
    cluster_evidence = []
    for name in common.files:
        if not name.endswith('.ndf'):
            continue
        data = common.read(name)
        if b'TClusterAddPythonPath' in data:
            text = data.decode('utf-8')
            at = text.index('TClusterAddPythonPath')
            cluster_evidence.append({'entry': name, 'sha256': sha(data),
                                     'excerpt': text[at:at+440]})
    result = {
        'date': '2026-11-06',
        'scope': 'read-only local binary/data inspection; no runtime execution',
        'game_sha256': sha((GAME / 'WARNO.exe').read_bytes()),
        'external_api': {'sha256': sha(dll_path.read_bytes()),
                         'imports': imports, 'exports': exports,
                         'finding': 'Steam integration; no verified unit-control export'},
        'scanned_script_packs': [p.relative_to(GAME).as_posix() for p in packs],
        'cluster_python_path_evidence': cluster_evidence,
        'script_symbol_evidence': sources,
        'capabilities': {
            'internal_python_and_native_descriptor_graph': 'confirmed in shipped data',
            'native_move_group_and_give_order_descriptors': 'confirmed symbols/setters',
            'custom_mod_code_loaded_in_standard_skirmish': 'NOT VERIFIED',
            'periodic_custom_python_callback': 'NOT FOUND in inspected entry points',
            'authoritative_live_unit_positions_to_custom_solver': 'NOT VERIFIED',
            'navigation_and_tactical_slot_generation': 'NOT IMPLEMENTED',
            'exclusive_orders_without_native_AI_overwrite': 'NOT VERIFIED',
            'save_load_and_deterministic_runtime_execution': 'NOT VERIFIED',
        },
        'conclusion': 'Promising internal scripting evidence, but no verified full '
                      'integration path. Python authoring of native descriptors '
                      'is not proof of a runtime Python AI callback.',
        'reference': 'https://github.com/kilivan4iK/moddingSuite/blob/master/'
                     'moddingSuite/BL/EdataManager.cs',
    }
    target = HERE / 'runtime-hook-audit.json'
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'report': str(target), 'packs': len(packs), 'modules': len(sources),
                      'runtime_adapter_verified': False}, ensure_ascii=False))


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    main()
