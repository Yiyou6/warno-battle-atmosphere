"""Validate the headless native-script entry experiment, never install it.

The marker is a harmless initialization cluster. Resolving/executing it proves
the generated package entered the native object database, not that an in-battle
GD action, the spatial allocator, or a unit order has run.
"""
from pathlib import Path
import hashlib
import json
import sys

from read_cndf import Cndf

HERE = Path(__file__).resolve().parent
MOD = HERE.parent
PROBE = MOD.parent / 'BAScriptProbe'
INSTALLED = Path.home() / 'Saved Games/EugenSystems/WARNO/mod/BattleAtmosphere'
EXPECTED = 'e394c13ed8d95a94d7179dbac8d41232ac71a2508d1174566b53952d24ee7bc6'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    receipt = json.loads((HERE / 'late-script-probe.json').read_text())
    assert receipt['exit_code'] == 0 and not receipt.get('timed_out')
    path = PROBE / 'Gen/NDF/BattleAtmosphere/ScriptProbe.ndfbin'
    graph = Cndf(path.read_bytes())
    driver = Cndf((PROBE / 'Gen/NDF/BAProbeDriver.ndfbin').read_bytes())
    assert all(x in graph.trans for x in ['GDScript', 'RootDescriptor', 'BA_ENTRY_PROBE_20261106'])
    assert any(o['class'] == 'TGDDescriptorLaunchEffetStandard' for o in graph.objects)
    assert any(o['class'] == 'TClusterStartNamedCluster' and
               o['properties'].get('SubClusterName') == '$/GDScript/BA_ENTRY_PROBE_20261106'
               for o in driver.objects)
    assert any(o['class'] == 'TNDFTransaction' and
               o['properties'].get('BaseName') == 'BattleAtmosphere/ScriptProbe' and
               o['properties'].get('NameSpace') == 'GDScript'
               for o in driver.objects)
    installed_sha = sha(INSTALLED / 'Gen/NDF/GFX/Skirmish.ndfbin')
    assert installed_sha == EXPECTED, 'Installed gameplay package changed unexpectedly'
    activation = (INSTALLED.parent / 'Config.ini').read_text(encoding='utf-8-sig')
    assert 'BAScriptProbe' not in activation
    result = {
        'date': '2026-11-06',
        'headless_native_entry': 'PASS',
        'native_exit_code': receipt['exit_code'],
        'native_elapsed_seconds': receipt['seconds'],
        'package_sha256': sha(path),
        'source_sha256': {
            n: sha(PROBE / n) for n in [
                'CommonData/BAProbeDriver.ndf',
                'CommonData/Gameplay/GDScripts/EffetMapSkirmish.ndf']},
        'installed_skirmish_sha256': installed_sha,
        'installed_version': '0.3.0-test3 (unchanged)',
        'probe_activated': False,
        'in_battle_gd_action_executed': False,
        'spatial_allocator_connected': False,
        'unit_position_query_verified': False,
        'unit_orders_verified': False,
        'playable_update_delivered': False,
    }
    (HERE / 'native-script-probe-validation.json').write_text(
        json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print('PASS: native package entry resolved; headless process exited 0.')
    print('Installed test3 unchanged; no in-battle algorithm or orders claimed.')


if __name__ == '__main__':
    main()
