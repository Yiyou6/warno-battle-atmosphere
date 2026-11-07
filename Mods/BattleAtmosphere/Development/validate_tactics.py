"""Cross-version controls: do not silently discard the user-confirmed baseline."""
from pathlib import Path
import difflib
import hashlib
import re
import zipfile

from apply_profile import ROOT, object_span, matching
from profile_v1 import MACROS, STRATEGIES, CONSTANTS, INF, AT, RECON

SNAPSHOT_SHA = 'ad9cb498253deb08ecc32ce0130986c3a6950eb53c8edd10070ea674f164e766'


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def block(text, name):
    a, b = object_span(text, name)
    return text[a:b]


def task_refs(text, field):
    found = re.search(r'\b' + field + r'\s*=\s*\[', text)
    a = text.index('[', found.start())
    return re.findall(r'~/([\w]+)', text[a:matching(text, a)+1])


def template(text, name):
    start = text.index('private template ' + name + '\n')
    body = re.search(r'\bis\s+T\w+\s*\(', text[start:])
    a = text.index('(', start + body.start())
    return text[start:matching(text, a)+1]


def check_tactics():
    path = ROOT/'Development/archive/0.2.0-test1-source.zip'
    require(hashlib.sha256(path.read_bytes()).hexdigest() == SNAPSHOT_SHA, 'User-tested source snapshot changed')
    with zipfile.ZipFile(str(path)) as archive:
        prior = {n: archive.read(n).decode('utf-8-sig').replace('\r\n','\n')
                 for n in archive.namelist() if n.endswith('.ndf')}
    current = {n:(ROOT/n).read_text(encoding='utf-8-sig') for n in prior}

    changed = {MACROS+'SkirmishAttacks.ndf', STRATEGIES+'VeryHardSkirmishStrategy.ndf', CONSTANTS}
    for name in prior.keys() - changed:
        require(prior[name] == current[name], 'First-build support/defense/dispatch changed: '+name)

    name = STRATEGIES+'VeryHardSkirmishStrategy.ndf'
    for phase in ['Deploiement','Command','LastHope']:
        old, new = [block(x[name], 'VHard_Phase_'+phase) for x in [prior,current]]
        for field in ['GeneratorList','ScalingGeneratorList']:
            before, after = task_refs(old,field), task_refs(new,field)
            require(len(before)==len(after), 'Mission count changed: '+phase+'/'+field)
        if phase=='Deploiement':
            require(old == new, 'Initial strategy priorities changed')
        else:
            tasks = task_refs(new,'GeneratorList')
            require(tasks.count('Attack_Adaptive')==1 and tasks.count('Attack_Objectives_Lateral')==1,
                    'Lateral role must replace, not add to repeated adaptive task')
            scaling = task_refs(new,'ScalingGeneratorList')
            require(scaling.count('Attack_Objectives_Lateral_Autogen')==1,
                    'Lateral expansion missing or duplicated')
            require('Attack_Objectives_Allied_Autogen' not in scaling,'Two cross-corridor objective expanders')

    name = MACROS+'SkirmishAttacks.ndf'
    old, new = prior[name],current[name]
    require(re.findall(r'(?m)^Budget_.*$',old)==re.findall(r'(?m)^Budget_.*$',new),
            'Existing purchase budget changed')
    family_report = {}
    reconstructed = new
    for family in ['Default','Infantry','Combined','Tank']:
        signatures=[]
        for i in [1,2,3]:
            poolname = f'Pool_{family}_Attack_{i}'
            b = block(new,poolname)
            tags = [re.findall(r'"(\w+)"',s) for s in re.findall(r'TagsPriority\s*=\s*\[([^\]]+)\]', b)]
            require('Required = true' not in b,'New mandatory ground role')
            require(all(re.findall(r'Nb = (\d+)',b)) and set(re.findall(r'Nb = (\d+)',b))=={'1'},
                    'Unexpected slot size')
            for role in [INF,AT,RECON]:
                require(any(set(t)==set(role) for t in tags),'Missing core role in '+poolname)
            signatures.append(tuple(tuple(t) for t in tags))
            a,z = object_span(reconstructed,poolname)
            reconstructed = reconstructed[:a]+block(old,poolname)+reconstructed[z:]
        require(len(set(signatures))==3,'Three identical tactical variants: '+family)
        # Compare membership as well as ordering; avoid claiming shuffled labels
        # provide different roles when their composition is identical.
        bags={tuple(sorted(s)) for s in signatures}
        require(len(bags)>=2,'Only purchase ordering changed: '+family)
        family_report[family]={'distinct_ordered_pools':len(set(signatures)), 'distinct_compositions':len(bags)}

    lateral = template(new,'Template_BA_Lateral_Attack')
    for required in ['TProdProperty_LaunchAsSoonAsPossible','Pool_Default_Attack_3',
                     'TObjectiveRequiresEnnemiesPossessionSettingHolder',
                     'PriorizeObjectiveNotInMyCorridor = true',
                     'RatioMinimumPourAttaquer = 0.7 RatioPourAttaquerPerduAChaqueTick = 0.00084',
                     'Default_Support_Request_Attack_Settings']:
        require(required in lateral,'Lateral mission missing behavior: '+required)
    require('ForcedCorridor' not in lateral and 'TCoordinationSettingHolder' not in lateral,
            'Hardcoded route or new support prerequisite')
    require('PrioritizeTaggedCorridors = false' in block(new,'Attack_Main_Autogen'),
            'Reinforcements still force main-tag preference')
    require('PrioritizeTaggedCorridors:bool = true' in template(new,'Template_Main_Attack'),
            'Initial main attack default lost')

    # Outside pools, the optional main-route parameter and the new objective
    # template, the entire first-build attack file must stay byte-equivalent.
    reconstructed = reconstructed.split('\n// Secondary enemy objectives:',1)[0]
    reconstructed = reconstructed.replace('    PrioritizeTaggedCorridors:bool = true,\n','')
    reconstructed = reconstructed.replace('PrioritizeCorridorsForTaggedPoolModels = <PrioritizeTaggedCorridors>',
                                          'PrioritizeCorridorsForTaggedPoolModels = true')
    reconstructed = reconstructed.replace('\n    PrioritizeTaggedCorridors = false','')
    require(reconstructed==old,'Unexpected change to attack ratios, production, initial forces or filler')

    restored=current[CONSTANTS]
    for newval,oldval in [
        ('MergeGroupDistInPolygon = 1.0','MergeGroupDistInPolygon = 2.0'),
        ('AddToGroupDistInPolygon = 0.75','AddToGroupDistInPolygon = 1.5'),
        ('BlitzkriegMultiplierForTacticalPathInCover = 2.0','BlitzkriegMultiplierForTacticalPathInCover = 4.0'),
    ]:
        require(restored.count(newval)==1,'Dispersion setting not unique: '+newval)
        restored=restored.replace(newval,oldval)
    require(restored==prior[CONSTANTS], 'Unreviewed global AI change, possibly affecting participation')

    delta=[]
    for name in sorted(changed):
        delta.extend(difflib.unified_diff(prior[name].splitlines(True),current[name].splitlines(True),
                                         fromfile='test1/'+name,tofile='test2/'+name))
    (ROOT/'Development/test1-to-test2.diff').write_text(''.join(delta),encoding='utf-8')
    return {'baseline_version':'0.2.0-test1','baseline_snapshot_sha256':SNAPSHOT_SHA,
            'changed_since_test1':sorted(changed),'variants':family_report,
            'preserved':'Opening priorities, task counts, budgets, launch/retreat timing, transport, AA, artillery and air settings',
            'runtime':'New dispersion and tactical effects not yet battle-validated'}
