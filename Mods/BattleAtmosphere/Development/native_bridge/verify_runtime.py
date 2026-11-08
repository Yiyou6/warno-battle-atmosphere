"""Verify the exact runtime binary against two owned headless game receipts."""
import ast
import configparser
import hashlib
import json
from pathlib import Path
import re
import sys

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[3]
RUNTIME = ROOT / 'Mods/BattleAtmosphere/Runtime'
CASES = {
    'runtime-auto-release-blackforest.json': '_2x3_BlackForestStorm_2vs2_CONQ',
    'runtime-auto-release-hesse.json': '_2x2_Hesse_2vs2_DEST',
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def stderr_ok(receipt):
    # A deliberately stopped OWNED fixture sets the isolated profile's
    # previous-exit flag. Preserve its exact startup warning in the receipt;
    # it is not a current crash (exit 0 and clean teardown are still required).
    known='[Game did not terminate properly.] Game did not terminate properly. Do you want to load the last known good configuration?\n[Game did not terminate properly.] Checking the integrity of the data files is recommended. This might take several minutes.\nCheck data integrity now?'
    value=receipt['stderr'].replace('\r\n','\n').strip()
    return not value or (value==known and receipt.get('activation_gate') and receipt.get('front_fixture')=='transport'
                         and receipt['returncode']==0 and 'AUTOMATIC_SKIRMISH_STOP' in receipt['stdout'])


def events(output, name):
    prefix = 'BA_BRIDGE ' + name + ' '
    return [ast.literal_eval(re.sub(r'(?<=\d)L\b', '', line[len(prefix):]))
            for line in output.splitlines() if line.startswith(prefix)]


def check_local_mod_identity(mod_root=None):
    """The native lobby searches ALL local mods by ID before comparing version.

    An inactive research Config.ini can shadow an active ID=0 local mod.
    Do not fabricate workshop IDs or rewrite metadata to hide this collision.
    """
    mod_root = mod_root or Path.home() / 'Saved Games/EugenSystems/WARNO/mod'
    records = []
    for path in sorted(mod_root.glob('*/Config.ini')):
        config = configparser.ConfigParser(inline_comment_prefixes=(';',))
        config.read(path, encoding='utf-8-sig')
        if config.has_section('Properties'):
            records.append(dict(folder=path.parent.name,
                                id=config.getint('Properties', 'ID', fallback=0),
                                version=config.getint('Properties', 'Version', fallback=0)))
    selected = next((row for row in records if row['folder'] == 'BattleAtmosphere'), None)
    if selected is None:
        raise RuntimeError('BattleAtmosphere is missing from the installed local mod directory')
    conflicts = [row for row in records if row is not selected and row['id'] == selected['id']]
    if conflicts:
        raise RuntimeError('Local mod ID collision in native lobby, including inactive mods: '
                           + repr([selected] + conflicts))
    return dict(status='unique-local-mod-id', mod=selected)


def verify(include_installed=False):
    manifest = json.loads((RUNTIME / 'build-manifest.json').read_text())
    if manifest['status']=='spatial-runtime-preview.6+vfx-budget.3+skirmish10.2':
        from verify_skirmish10 import verify_skirmish10
        return verify_skirmish10(include_installed)
    if manifest['status']=='spatial-runtime-preview.6+vfx-budget.3':
        from verify_fx_budget import verify_fx_budget
        return verify_fx_budget(include_installed)
    assert sha(ROOT / 'WARNO.exe') == manifest['exe_sha256'], 'Game executable changed'
    assert sha(BASE / 'version.dll') == manifest['dll_sha256'], 'Runtime binary changed'
    for name, digest in manifest['source_sha256'].items():
        assert sha(ROOT / name) == digest, 'Build input changed: ' + name
    offline_path=BASE.parent/'continuous-offline-validation.json'
    if manifest['status'] in ('spatial-runtime-preview.4','spatial-runtime-preview.5','spatial-runtime-preview.6'):
        offline=json.loads(offline_path.read_text())
        assert offline['returncode']==0 and 'OK' in offline['stderr'], 'Offline regression failed'
        for source,digest in offline['source_sha256'].items():
            assert sha(ROOT/source)==digest,'Offline regression input changed: '+source
    if manifest['status'] in ('spatial-runtime-preview.2','spatial-runtime-preview.3','spatial-runtime-preview.4','spatial-runtime-preview.5','spatial-runtime-preview.6'):
        cold_path = BASE.parent / 'runtime-native-cold-start.json'
        cold = json.loads(cold_path.read_text())
        assert cold['returncode'] == 0 and not cold['timeout'], 'Cold start failed'
        assert cold['autoload_sha256'] == sha(BASE / 'cold_start_probe.dll'), 'Cold probe binary changed'
        assert cold['activation_gate'] and cold['bridge'] is None
        if manifest['status'] in ('spatial-runtime-preview.3','spatial-runtime-preview.4','spatial-runtime-preview.5','spatial-runtime-preview.6'):
            pointer_events=events(cold['stdout'],'FIXTURE_ROOT_POINTER')
            assert len(pointer_events)==1 and pointer_events[0][0]==pointer_events[0][1], 'Cold fixture pointer conversion'
        wrapper = str((BASE / 'cold_start_probe.c').relative_to(ROOT))
        assert cold['auxiliary_sha256'][wrapper] == sha(BASE / 'cold_start_probe.c')
        for source, digest in manifest['source_sha256'].items():
            observed = (cold['source_sha256'] if source.endswith('ba_autorun.py')
                        else cold['auxiliary_sha256'].get(source))
            assert observed == digest, 'Cold test build input changed: ' + source
        prefix, separator, tail = cold['stdout'].partition('COLD_START_NO_NATIVE_MODULE')
        assert separator and tail.count('MODULE_REGISTERED') == 1
        assert tail.index('MODULE_REGISTERED') < tail.index('ba_allocator') < tail.index('ba_space') < tail.index('AUTO_PYTHON_STARTED')
        assert 'AUTOMATIC_SKIRMISH_STOP' in tail and 'ERROR' not in tail
        assert 'SPACE_STATUS (80,' in tail and events(cold['stdout'], 'SPACE_ORDER')
        assert not cold['stderr'].strip(), 'Cold test stderr'
    results = []
    cases = dict(CASES)
    if include_installed:
        check_local_mod_identity()
        cases['runtime-installed-root.json'] = '_2x3_BlackForestStorm_2vs2_CONQ'
        assert sha(ROOT / 'version.dll') == manifest['dll_sha256'], 'Installed DLL changed'
    for name, scenario in cases.items():
        path = BASE.parent / name
        receipt = json.loads(path.read_text())
        assert receipt['returncode'] == 0 and not receipt['timeout'], name
        assert receipt['autoload_sha256'] == manifest['dll_sha256'], 'Different test binary'
        assert receipt['activation_gate'] and receipt['bridge'] is None
        command = receipt['command']
        if name == 'runtime-installed-root.json':
            assert receipt['installed_runtime']
            assert Path(command[0]).resolve() == ROOT / 'WARNO.exe'
        assert '-rootdata' not in command and '-uselocaldata' not in command
        assert command[command.index('-scenarioname') + 1] == scenario
        for source, digest in manifest['source_sha256'].items():
            observed = (receipt['source_sha256'] if source.endswith('ba_autorun.py')
                        else receipt['auxiliary_sha256'].get(source))
            assert observed == digest, 'Test input does not match build: ' + source
        output = receipt['stdout']
        if manifest['status'] in ('spatial-runtime-preview.3','spatial-runtime-preview.4','spatial-runtime-preview.5','spatial-runtime-preview.6'):
            pointer_events=events(output,'FIXTURE_ROOT_POINTER')
            assert len(pointer_events)==1 and pointer_events[0][0]==pointer_events[0][1], 'Fixture pointer conversion'
        for marker in ['AUTOMATIC_SKIRMISH_ENTRY', 'AUTO_PYTHON_STARTED',
                       'UPDATE_ATTACHED_TO_EXISTING_WORLD', 'AUTO_PYTHON_CLEANUP',
                       'AUTOMATIC_SKIRMISH_STOP']:
            assert output.count(marker) == 1, (name, marker)
        assert not receipt['stderr'].strip(), name + ': stderr'
        assert not re.search(r'ERROR|Traceback|REJECT|REFUSE', output), name + ': runtime error'
        guards = set(events(output, 'IDENTITY_GUARD'))
        assert {(0, -3), (7, -3)} <= guards, 'Human/script ownership guard failed'
        plans = events(output, 'SPACE_PLAN')
        orders = events(output, 'SPACE_ORDER')
        positions = events(output, 'SPACE_POSITIONS')
        returns = events(output, 'SPACE_RETURN')
        assert plans and plans[0][0] <= 5, 'Correction waited for a complete cluster'
        assert orders and all(order[3] == 1 for order in orders)
        first = {row[0]: row for row in positions[0]}
        last = {row[0]: row for row in positions[-1]}
        assert all(first[order[0]][2] == 6 for order in orders), 'Order sent to non-AI'
        moved = [uid for uid in first if first[uid][2] == 6 and uid in last and
                 ((first[uid][3] - last[uid][3])**2 +
                  (first[uid][4] - last[uid][4])**2)**.5 > 25 * 215]
        assert len(moved) >= 6, 'Not enough real movement'
        arrivals=events(output,'FRONT_ARRIVAL') if manifest['status'] in ('spatial-runtime-preview.4','spatial-runtime-preview.5','spatial-runtime-preview.6') else [(uid,0,0) for uid,reason in returns if reason=='arrived']
        assert arrivals, 'No completed movement'
        directional={}
        if manifest['status'] in ('spatial-runtime-preview.3','spatial-runtime-preview.4','spatial-runtime-preview.5','spatial-runtime-preview.6'):
            routes=events(output,'SPACE_ROUTE'); waypoints=events(output,'SPACE_WAYPOINT')
            continuous=manifest['status'] in ('spatial-runtime-preview.4','spatial-runtime-preview.5','spatial-runtime-preview.6')
            assert ((('SPACE_REVISION combined-front-preview.6' if manifest['status']=='spatial-runtime-preview.6' else 'SPACE_REVISION combined-front-preview.5') if manifest['status'] in ('spatial-runtime-preview.5','spatial-runtime-preview.6') else 'SPACE_REVISION continuous-front-preview.4') if continuous else 'SPACE_REVISION directional-frontage-preview.3') in output and routes
            for uid,phase,side,lane,count,start_depth,end_depth,start_lateral,end_lateral in routes:
                gain=end_depth-start_depth; spread=end_lateral-start_lateral
                assert gain+1e-4>=max(65 if continuous else 60,abs(spread)*(.35 if continuous else .65)) and gain<=(1000.001 if continuous else 420.001), 'Non-forward route'
                if phase=='expand' and not continuous: assert side*spread>=39.999, 'Wing crosses inward'
            assert waypoints and all(event[3]==1 for event in waypoints), 'No accepted waypoint chain'
            frames=dict((a,f) for a,h,f in events(output,'SPACE_FRAME'))
            advanced=[uid for uid in moved if
                      sum((last[uid][3+k]-first[uid][3+k])*frames[first[uid][1]][k] for k in range(2))>25*215]
            assert len(advanced)>=6, 'Insufficient real forward movement'
            widths=[]; nearby_pairs=[]
            for snapshot in (first,last):
                across=[(-frames[row[1]][1]*row[3]+frames[row[1]][0]*row[4])/215
                        for row in snapshot.values() if row[2]==6]
                widths.append(round(max(across)-min(across),3))
                ground=[row for row in snapshot.values() if row[2]==6]
                nearby_pairs.append(sum(a[1]==b[1] and
                    ((a[3]-b[3])**2+(a[4]-b[4])**2)**.5<120*215
                    for i,a in enumerate(ground) for b in ground[i+1:]))
            directional=dict(waypoint_orders=len(waypoints),forward_over_25m=len(advanced),
                             fixture_width_metres_before_after=widths,
                             fixture_pairs_within_120m_before_after=nearby_pairs,
                             outward_routes=sum(r[1]=='expand' for r in routes),
                             advance_routes=sum(r[1]=='advance' for r in routes))
        results.append(dict(receipt=name, receipt_sha256=sha(path), scenario=scenario,
                            wall_seconds=receipt['seconds'], first_plan_tick=plans[0][0],
                            orders=len(orders), moved_over_25m=len(moved),
                            arrived=len(arrivals),
                            identity_guards=sorted(guards), directional=directional,exit_code=0))
    combined=verify_combined(manifest) if manifest['status'] in ('spatial-runtime-preview.5','spatial-runtime-preview.6') else None
    long_tests=verify_continuous(manifest) if manifest['status'] in ('spatial-runtime-preview.4','spatial-runtime-preview.5','spatial-runtime-preview.6') else []
    return dict(status='headless-integration-passed; full-battle-unverified',
                continuous_tests=long_tests, combined=combined,
                orientation_tests=verify_orientation(manifest) if manifest['status']=='spatial-runtime-preview.6' else [],
                offline_receipt_sha256=sha(offline_path) if manifest['status'] in ('spatial-runtime-preview.4','spatial-runtime-preview.5','spatial-runtime-preview.6') else None,
                dll_sha256=manifest['dll_sha256'], exe_sha256=manifest['exe_sha256'],
                cold_start_receipt_sha256=sha(BASE.parent / 'runtime-native-cold-start.json')
                    if manifest['status'] in ('spatial-runtime-preview.2','spatial-runtime-preview.3','spatial-runtime-preview.4','spatial-runtime-preview.5','spatial-runtime-preview.6') else None,
                tests=results)


def verify_continuous(manifest):
    import math
    results=[]
    for name,mode,scenario in [('widefront-release-battle.json','battle','_2x2_Hesse_2vs2_DEST'),
                               ('widefront-release-mass.json','mass','_2x3_BlackForestStorm_2vs2_CONQ')]:
        path=BASE.parent/name; receipt=json.loads(path.read_text());out=receipt['stdout']
        assert receipt['returncode']==0 and not receipt['timeout'] and not receipt['stderr'].strip(),name
        assert receipt['autoload_sha256']==manifest['dll_sha256'],name+': binary mismatch'
        assert receipt['activation_gate'] and receipt['bridge'] is None and receipt['front_fixture']==mode
        assert receipt['command'][receipt['command'].index('-scenarioname')+1]==scenario
        for source,digest in manifest['source_sha256'].items():
            observed=receipt['source_sha256'] if source.endswith('ba_autorun.py') else receipt['auxiliary_sha256'].get(source)
            assert observed==digest,name+': source mismatch '+source
        assert not re.search(r'ERROR|Traceback|REJECT|REFUSE',out),name
        for marker in ['AUTOMATIC_SKIRMISH_ENTRY','AUTO_PYTHON_STARTED','AUTOMATIC_SKIRMISH_STOP','AUTO_PYTHON_CLEANUP']:
            assert out.count(marker)==1,(name,marker)
        positions=events(out,'SPACE_POSITIONS');stats=events(out,'SPACE_STATUS');activity=events(out,'FRONT_ACTIVITY')
        telemetry=events(out,'FRONT_METRICS');assert telemetry, 'Missing normal-game density telemetry'
        assert stats[-1][0]>=480 and max(s[1] for s in stats)>=80, 'Not a long reinforcement fixture'
        assert all(o[3]==1 for o in events(out,'SPACE_ORDER'))
        assert all(o[3]==1 for o in events(out,'SPACE_WAYPOINT'))
        frames=dict((a,(h,f)) for a,h,f in events(out,'SPACE_FRAME'))
        widths=[];nearby=[];lanes=[]
        for snapshot in positions:
            own=[r for r in snapshot if r[1]==1 and r[2]==6]; h,f=frames[1]
            ls=sorted((-(r[3]-h[0])*f[1]+(r[4]-h[1])*f[0])/215 for r in own)
            widths.append(ls[int(len(ls)*.9)]-ls[int(len(ls)*.1)])
            nearby.append(sum(math.hypot(a[3]-b[3],a[4]-b[4])<120*215 for i,a in enumerate(own) for b in own[i+1:]))
            lanes.append(len(set(int(l/260) for l in ls)))
        unique=set(r[0] for snapshot in positions for r in snapshot)
        last=set(r[0] for r in positions[-1]);dead=len(unique-last)
        arrivals=events(out,'FRONT_ARRIVAL');completed={}
        for uid,tick,legs in arrivals:completed[uid]=max(completed.get(uid,0),legs)
        penultimate=dict((r[0],r) for r in positions[-13])
        late_forward=sum(sum((r[3+k]-penultimate[r[0]][3+k])*frames[r[1]][1][k] for k in range(2))>25*215 for r in positions[-1] if r[2]==6 and r[0] in penultimate)
        if mode in ('long','mass'):
            assert min(widths[-12:])>1500 and widths[-1]>2500,'Front reconverged or never widened'
            assert nearby[-1]<nearby[0]*.25,'Concentrated artillery exposure remains'
            assert sum(n>=2 for n in completed.values())>=(140 if mode=='mass' else 30),'No sustained route continuation'
            assert late_forward>=len(last)*.8,'Late battle stopped advancing after expansion'
            assert stats[-1][3]>=(230 if mode=='mass' else 65),'Too few sustained assignments'
            final_metrics=dict(telemetry[-1][1])[1]
            assert final_metrics['rear_idle_30s']<10,'Idle rear mass remains'
            assert final_metrics['largest_200m_cluster']<max(16,len(last)*.1),'Large clump remains'
            assert final_metrics['front_band_lanes']>=15 and final_metrics['empty_internal_lanes']<=2,'Fragmented front'
        else:
            assert dead>=5,'No real engagement losses in opposing-force fixture'
            assert any(flag&32 for values in activity for uid,flag in values),'Native combat category never observed'
            assert sum(n>=2 for n in completed.values())>=10,'No continuation during opposing-force fixture'
            assert widths[-1]>1500,'No broad front under opposing fire'
            assert dict(telemetry[-1][1])[1]['largest_200m_cluster']<20,'Combat froze an oversized clump'
        results.append(dict(receipt=name,receipt_sha256=sha(path),mode=mode,
            simulation_seconds=stats[-1][0]*.5,unique_units=len(unique),disappeared_units=dead,
            width_80_percent_initial_final=[round(widths[0],1),round(widths[-1],1)],
            width_80_percent_min_last_minute=round(min(widths[-12:]),1),
            pairs_120m_initial_final=[nearby[0],nearby[-1]],
            active_claims_final=stats[-1][3],late_minute_forward_over_25m=late_forward,units_completed_3_legs=sum(n>=3 for n in completed.values()),
            combat_state_observations=sum(bool(flag&32) for values in activity for uid,flag in values),
            final_metrics=dict(telemetry[-1][1]),
            max_sampled_planning_ms=max(s[-1] for s in stats)))
    return results


def verify_orientation(manifest):
    results=[]
    for name,transport in [('direction-urban-swapped.json',False),('direction-hesse-swapped.json',False),('direction-transport-swapped.json',True)]:
        path=BASE.parent/name;r=json.loads(path.read_text());out=r['stdout']
        assert r['returncode']==0 and not r['timeout'] and not r['stderr'].strip(),name
        assert r['autoload_sha256']==manifest['dll_sha256'],name+': binary changed'
        assert r['activation_gate'] and r['bridge'] is None
        assert r['front_fixture']==('transport_swapped' if transport else 'swapped')
        for source,digest in manifest['source_sha256'].items():
            observed=r['source_sha256'] if source.endswith('ba_autorun.py') else r['auxiliary_sha256'].get(source)
            assert observed==digest,name+': input changed '+source
        assert not re.search(r'ERROR|Traceback|REJECT|REFUSE',out),name
        assert out.count('AUTOMATIC_SKIRMISH_STOP')==1
        expected=dict((a,(h,f)) for a,h,f in events(out,'FIXTURE_EXPECTED_FRAME'))
        actual=dict((a,(h,f)) for a,h,f in events(out,'SPACE_FRAME'))
        assert 1 in actual
        for a,(home,f) in actual.items():
            # Hesse has several deployment zones per side. The controller
            # uses their centre; the independently placed fixture may start
            # in a flank zone. Both must face the same enemy hemisphere,
            # but their headings need not be numerically identical.
            assert sum(f[k]*expected[a][1][k] for k in range(2))>.7,'Physical attack axis reversed or transverse'
        positions=events(out,'SPACE_POSITIONS');first={u[0]:u for u in positions[0]};last={u[0]:u for u in positions[-1]}
        gains=[sum((u[3+k]-first[uid][3+k])*expected[u[1]][1][k] for k in range(2))/215 for uid,u in last.items() if uid in first and u[2]==6]
        assert len(gains)>=12 and sum(g>25 for g in gains)>=len(gains)*.85,'Army did not advance toward physical opponent'
        assert not any(g < -70 for g in gains),'Army physically retreated'
        if transport:
            delivered=events(out,'TRANSPORT_DELIVERED')
            assert len(delivered)==8 and all(d[2]<75 and d[3]=='delivery' for d in delivered),'Swapped-side transport failed'
        results.append(dict(receipt=name,sha256=sha(path),units=len(gains),physical_forward_over_25m=sum(g>25 for g in gains),physical_backward_over_70m=sum(g<-70 for g in gains),min_forward_m=round(min(gains),1),axis_faces_independent_opponent=True,
            normal_deliveries=len(events(out,'TRANSPORT_DELIVERED')) if transport else None,
            detours_preserved=len(events(out,'TRANSPORT_DETOUR_PROGRESS')) if transport else None))
    return results


def verify_combined(manifest):
    path=BASE.parent/'combined-release-transport.json'
    r=json.loads(path.read_text());out=r['stdout']
    assert r['returncode']==0 and not r['timeout'] and stderr_ok(r)
    assert r['autoload_sha256']==manifest['dll_sha256'] and r['front_fixture']=='transport'
    for source,digest in manifest['source_sha256'].items():
        observed=r['source_sha256'] if source.endswith('ba_autorun.py') else r['auxiliary_sha256'].get(source)
        assert observed==digest,'Transport input changed: '+source
    assert not re.search(r'ERROR|Traceback|REJECT|REFUSE',out)
    routes=events(out,'TRANSPORT_ROUTE');deliveries=events(out,'TRANSPORT_DELIVERED')
    assert len(routes)==8 and len(deliveries)==8,'Not all paired transports delivered'
    assert all(d[1] and d[2]<75 and d[3]=='delivery' for d in deliveries),'Early/emergency delivery in safe fixture'
    assert all(200<=r[2]-r[3]<=551 for r in routes),'Wrong delivery band'
    positions=events(out,'SPACE_POSITIONS');last={r[0]:r for r in positions[-1]}
    frame=dict((a,(h,f)) for a,h,f in events(out,'SPACE_FRAME'))[1]
    continued=[]
    for carrier,passengers,front,depth,target in routes:
        for uid in [carrier]+passengers:
            row=last[uid]
            gain=sum((row[3+k]-target[k])*frame[1][k] for k in range(2))/215
            if gain>25:continued.append(uid)
    assert len(continued)>=14,'Dismount created stationary rear groups'
    emergency_path=BASE.parent/'combined-emergency-native.json'
    er=json.loads(emergency_path.read_text());eo=er['stdout']
    assert er['returncode']==0 and not er['timeout'] and not er['stderr'].strip()
    assert er['diagnostic_source_sha256']==sha(BASE/'transport_emergency_probe.c')
    assert er['autoload_sha256']==sha(BASE/'transport_emergency_probe.dll')
    for source,digest in manifest['source_sha256'].items():
        observed=er['source_sha256'] if source.endswith('ba_autorun.py') else er['auxiliary_sha256'].get(source)
        assert observed==digest,'Emergency probe input changed: '+source
    emergency_orders=events(eo,'EMERGENCY_NATIVE_ORDER');states=events(eo,'EMERGENCY_NATIVE_STATE')
    assert len(emergency_orders)==8 and all(result==1 for uid,result in emergency_orders)
    assert any(20<s[0]<=30 and s[1:]==(8,[]) for s in states)
    assert not re.search(r'ERROR|Traceback|REJECT|REFUSE',eo)
    return dict(receipt=path.name,sha256=sha(path),paired_deliveries=len(deliveries),
                startup_warning=r['stderr'].strip() or None,
                forward_after_unload_over_25m=len(continued),
                emergency_orders_in_safe_delivery_test=len(events(out,'TRANSPORT_EMERGENCY')),
                immediate_unload_commands=len(emergency_orders),
                emergency_receipt_sha256=sha(emergency_path))


if __name__ == '__main__':
    result = verify(include_installed='--installed' in sys.argv)
    (RUNTIME / 'validation.json').write_text(json.dumps(result, indent=2) + '\n')
    if '--installed' in sys.argv:
        installation_path = RUNTIME / 'installation.json'
        installation = json.loads(installation_path.read_text())
        tests = result.get('tests')
        installation['post_install_validation'] = (tests['installed'] if isinstance(tests, dict)
                                                   else tests[-1] if tests else result)
        installation_path.write_text(json.dumps(installation, indent=2) + '\n')
    print(json.dumps(result, indent=2))
