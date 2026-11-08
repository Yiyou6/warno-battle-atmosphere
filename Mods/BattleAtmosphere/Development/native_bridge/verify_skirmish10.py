"""Validate the pinned lobby hook and twenty-camp headless fixtures.

These are native calculation and simulation tests, not a rendered lobby click
test or a complete twenty-player battle / purchasing / performance benchmark.
"""
import ast
import hashlib
import json
import math
from pathlib import Path
import re
import zipfile

BASE=Path(__file__).resolve().parent
DEV=BASE.parent
MOD=DEV.parent
ROOT=MOD.parents[1]
STATUS='spatial-runtime-preview.6+vfx-budget.3+skirmish10.2'
AUTORUN='Mods/BattleAtmosphere/Runtime/Python/ba_autorun.py'
OBSERVER="        if native.fixture_mode()=='tenvten':\n            import ba_fixture\n            ba_fixture.tenvten_observe(controller.tick)\n"
PREVIOUS_EXIT_WARNING='[Game did not terminate properly.] Game did not terminate properly. Do you want to load the last known good configuration?\n[Game did not terminate properly.] Checking the integrity of the data files is recommended. This might take several minutes.\nCheck data integrity now?'

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def events(out,name):
    prefix='BA_BRIDGE '+name+' '
    return [ast.literal_eval(re.sub(r'(?<=\d)L\b','',line[len(prefix):]))
            for line in out.splitlines() if line.startswith(prefix)]

def preserved_sources():
    with zipfile.ZipFile(DEV/'archive/skirmish10-before.zip') as z:
        previous=json.loads(z.read('Mods/BattleAtmosphere/Runtime/build-manifest.json'))
        for name,digest in previous['source_sha256'].items():
            if Path(name).name in ('probe_bridge.c','embedded_python.h','ba_autorun.py','ba_fixture.py'):continue
            assert sha(ROOT/name)==digest,('Frozen input changed',name)
        old=z.read(AUTORUN).decode().replace('\r\n','\n')
        current=(ROOT/AUTORUN).read_text(encoding='utf-8')
        assert current.count(OBSERVER)==1
        assert current.replace(OBSERVER,'')==old,'Ordinary AI runtime changed'
        path='Mods/BattleAtmosphere/Development/native_bridge/probe_bridge.c'
        old=z.read(path).decode().replace('\r\n','\n')
        current=(ROOT/path).read_text(encoding='utf-8')
        additions=[
            '#ifdef BA_PROXY\nstatic void lobby_capacity_selftest(void);\n#endif\n',
            '    lobby_capacity_selftest();\n',
            '#include "skirmish_lobby.h"\n#include "lobby_selftest.h"\n',
            '    if (!lobby_capacity_install()) log_line("SKIRMISH_CAPACITY_HOOK_REFUSED");\n',
        ]
        for addition in additions:
            assert current.count(addition)==1,addition
            current=current.replace(addition,'')
        assert current==old,'Changes outside bounded lobby hook'
        transitions={
            'version.dll':{hashlib.sha256(z.read('version.dll')).hexdigest(),sha(BASE/'version.dll')},
            AUTORUN:{hashlib.sha256(z.read(AUTORUN)).hexdigest(),sha(ROOT/AUTORUN)},
        }
    release=json.loads((DEV/'smoke-release.json').read_text(encoding='utf-8'))
    assert release['version']=='smoke-preview.20'
    installed=Path.home()/'Saved Games/EugenSystems/WARNO/mod/BattleAtmosphere'
    for name,digest in release['outputs'].items():
        assert sha(installed/name)==digest,('Installed mod data changed',name)
    return transitions,len(release['outputs'])

def validate_receipt(name,scenario,manifest,enabled=True,twenty=True,installed=False):
    path=DEV/name
    r=json.loads(path.read_text(encoding='utf-8'));out=r['stdout']
    assert r['returncode']==0 and not r['timeout'],name
    stderr=r['stderr'].replace('\r','').strip()
    assert stderr in ('',PREVIOUS_EXIT_WARNING),(name,stderr)
    assert r['autoload_sha256']==manifest['dll_sha256']
    assert r['activation_gate'] and r['bridge'] is None
    assert r['installed_runtime']==installed
    assert r['command'][r['command'].index('-scenarioname')+1]==scenario
    assert Path(r['command'][0]).resolve()==(ROOT/'WARNO.exe' if installed else ROOT/'Mods/BAScriptProbe/AutoloadBoot/WARNO.exe')
    for source,digest in manifest['source_sha256'].items():
        observed=r['source_sha256'] if source.endswith('ba_autorun.py') else r['auxiliary_sha256'].get(source)
        assert observed==digest,('Receipt build input',source)
    assert not re.search(r'ERROR|Traceback|REFUSE|REJECT',out),name
    pattern=r'LOBBY_CAPACITY_TEST site=(\d+) case=(\d+) network=(\d+) host=(\d+) stock=(\d+) actual=(\d+) expected=(\d+) pass=(\d+)'
    cases=[tuple(map(int,row)) for row in re.findall(pattern,out)]
    assert len(cases)==12 and {(r[0],r[1]) for r in cases}=={(a,b) for a in range(2) for b in range(6)}
    for site,case,network,host,stock,actual,expected,passed in cases:
        assert stock==(8 if case<4 else 20)
        assert actual==expected==(20 if enabled and case<2 else stock) and passed==1
    settings=[tuple(map(int,row)) for row in re.findall(
        r'LOBBY_SETTINGS_TEST case=(\d+) network=(\d+) capacity=(\d+) expected=(\d+) counts_preserved=(\d+) pass=(\d+)',out)]
    visibility=[tuple(map(int,row)) for row in re.findall(
        r'LOBBY_VISIBLE_TEST case=(\d+) network=(\d+) stock_hidden=(\d+) actual_hidden=(\d+) expected=(\d+) pass=(\d+)',out)]
    assert len(settings)==len(visibility)==6
    assert {r[0] for r in settings}=={r[0] for r in visibility}==set(range(6))
    for case,network,capacity,expected,counts,passed in settings:
        assert network==int(case>=3)
        assert capacity==expected==(20 if (enabled and not network) or case%3==2 else 8)
        assert counts==passed==1
    for case,network,stock,actual,expected,passed in visibility:
        assert network==int(case>=3) and stock==(12,19,0)[case%3]
        assert actual==expected==(0 if enabled and not network else stock) and passed==1
    result=dict(receipt_sha256=sha(path),scenario=scenario,normal_exit=True,
                native_capacity_cases=len(cases),native_settings_cases=len(settings),
                native_visibility_cases=len(visibility),prior_exit_warning=bool(stderr))
    if not enabled:
        assert 'LOBBY_CAPACITY_TEST_ONLY_COMPLETE' in out
        assert 'AUTO_PYTHON_STARTED' not in out and 'SPACE_ORDER' not in out
        assert 'FX_BUDGET_APPLIED' not in out
        result['scope']='native-lobby-calculation-only; exits before empty-world loading'
        return result
    for marker in ('SKIRMISH_CAPACITY_HOOK_READY local_slots=20 original_slots=8 network_branch=stock',
                   'SKIRMISH_UI_HOOK_READY restored_capacity=20 open_seats=20',
                   'FX_BUDGET_APPLIED original=80000 max_particles=200000 quality_scaled=1 telemetry=1',
                   'SPACE_REVISION combined-front-preview.6'):
        assert marker in out,marker
    assert out.count('AUTO_PYTHON_STARTED')==1 and out.count('AUTOMATIC_SKIRMISH_STOP')==1
    assert events(out,'SPACE_ORDER')
    budget=re.findall(r'FX_BUDGET_STATUS particles=(\d+) effective_limit=(\d+) max_particles=200000',out)
    assert budget and all(100000<=int(limit)<=200000 for count,limit in budget)
    result.update(max_particles=200000,headless_particle_counts=sorted({int(c) for c,l in budget}),
                  effective_limits=sorted({int(l) for c,l in budget}))
    if twenty:
        assert r['front_fixture']=='tenvten'
        snapshots=events(out,'TENVTEN_ROSTER');assert len(snapshots)>=16
        first={row[0]:row for row in snapshots[0][1]}
        last={row[0]:row for row in snapshots[-1][1]}
        assert len(first)==80 and len(last)==80
        owners={row[1] for row in first.values()}
        assert len(owners)==20
        assert all(len({row[1] for row in first.values() if row[2]==side})==10 for side in (0,1))
        ai={row[1] for row in first.values() if row[3]==6};assert len(ai)==19
        human={row[0] for row in first.values() if row[3]==7};assert len(human)==4
        moved={row[1] for uid,row in last.items() if uid in first and row[3]==6 and
               math.hypot(row[4]-first[uid][4],row[5]-first[uid][5])>25*215}
        assert moved==ai,'Some AI camps have no observed movement'
        assert not human.intersection(row[0] for row in events(out,'SPACE_ORDER'))
        result.update(camps=20,camps_per_side=10,ai_camps=19,units=80,moving_ai_camps=len(moved),
                      snapshots=len(snapshots),last_tick=snapshots[-1][0],human_units_ordered=0)
    return result

def verify_skirmish10(installed=False):
    manifest=json.loads((MOD/'Runtime/build-manifest.json').read_text())
    assert manifest['status']==STATUS
    assert sha(ROOT/'WARNO.exe')==manifest['exe_sha256']
    assert sha(BASE/'version.dll')==manifest['dll_sha256']
    for name,digest in manifest['source_sha256'].items():assert sha(ROOT/name)==digest,name
    transitions,files=preserved_sources()
    tests={}
    for name,scenario,enabled in (
        ('blackforest','_2x3_BlackForestStorm_2vs2_CONQ',True),
        ('hesse','_2x2_Hesse_2vs2_DEST',True),
        ('disabled','_2x3_BlackForestStorm_2vs2_CONQ',False)):
        tests[name]=validate_receipt('skirmish10-'+name+'.json',scenario,manifest,enabled)
    if installed:
        if __package__:
            from .verify_runtime import check_local_mod_identity
        else:
            from verify_runtime import check_local_mod_identity
        check_local_mod_identity()
        assert sha(ROOT/'version.dll')==manifest['dll_sha256']
        tests['installed']=validate_receipt('skirmish10-installed.json','_2x3_BlackForestStorm_2vs2_CONQ',
                                           manifest,twenty=False,installed=True)
    return dict(status='native-capacity-visibility-and-20-camp-fixtures-passed; ordinary-lobby-and-battle-unverified',
                dll_sha256=manifest['dll_sha256'],exe_sha256=manifest['exe_sha256'],
                tests=tests,max_particles=200000,ai_algorithm_unchanged=True,
                test_only_observer_added=True,installed_mod_files_unchanged=files,
                historical_full_AI_suite_rerun=False,
                allowed_protected_transitions={k:sorted(v) for k,v in transitions.items()})

if __name__=='__main__':print(json.dumps(verify_skirmish10(),indent=2))
