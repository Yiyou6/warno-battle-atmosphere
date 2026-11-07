"""Third iteration: native field evidence, coverage task graph and regressions."""
import hashlib
import json
import re
import zipfile
import difflib
from apply_profile import ROOT, object_span, matching
from profile_v3 import MACROS, STRATEGIES, CONSTANTS, template_span


def check_frontage():
    def need(ok,msg):
        if not ok: raise AssertionError(msg)
    def obj(text,name):
        a,b=object_span(text,name);return text[a:b]
    def template(text,name):
        a,b=template_span(text,name,matching);return text[a:b]
    def refs(text,field):
        m=re.search(r'\b'+field+r'\s*=\s*\[',text);a=text.index('[',m.start())
        return re.findall(r'~/([\w]+)',text[a:matching(text,a)+1])
    snapshot=ROOT/'Development/archive/0.2.1-test2-source.zip'
    need(hashlib.sha256(snapshot.read_bytes()).hexdigest()=='c2800697b2a59fdd1adc12c1ed32d0cecdb9b98a49da72a0129e628854189117','Test2 snapshot changed')
    with zipfile.ZipFile(str(snapshot)) as z:
        prior={n:z.read(n).decode('utf-8-sig').replace('\r\n','\n') for n in z.namelist() if n.endswith('.ndf')}
    current={n:(ROOT/n).read_text(encoding='utf-8-sig') for n in prior}
    allowed={CONSTANTS,STRATEGIES+'VeryHardSkirmishStrategy.ndf',MACROS+'SkirmishAttacks.ndf',MACROS+'SkirmishDefenses.ndf'}
    for name in prior.keys()-allowed:
        need(current[name]==prior[name],'Protected support/dispatch changed: '+name)
    constants=current[CONSTANTS]
    reduced=re.sub(r'    // Native TIAStratConstantesDescriptor fields; absent in the shipped NDF\.\n'
                   r'    UseAntiStackingForVehicles = true\n    UseAntiStackingForInfantry = true\n', '', constants)
    reduced=reduced.replace('MaxNumberOfStackingUnits = 1','MaxNumberOfStackingUnits = 2')
    need(reduced==prior[CONSTANTS],'Unreviewed AI global change beyond anti-stacking')
    for field in ['UseAntiStackingForVehicles = true','UseAntiStackingForInfantry = true','MaxNumberOfStackingUnits = 1']:
        need(constants.count(field)==1,'Missing native setting: '+field)

    attacks=current[MACROS+'SkirmishAttacks.ndf'];old=prior[MACROS+'SkirmishAttacks.ndf']
    # Keep all previously shipped combat pools, ceilings, tags and quantities.
    for name in re.findall(r'(?m)^export (Pool_\w+) is TPoolModel',old):
        need(obj(attacks,name)==obj(old,name),'Existing combat pool changed: '+name)
    need(re.findall(r'(?m)^Budget_.*$',attacks)==re.findall(r'(?m)^Budget_.*$',old),'Existing attack budgets changed')
    front=template(attacks,'Template_BA_Frontage_Attack')
    for token in ['GenerationType = TGenerationType_BasedOnNumberOfCorridors',
                  'ConsiderOnlyAssignedCorridors = true','ForceInAssignedCorridor = true',
                  'DisableReinforcement = true','TProdProperty_LaunchAsSoonAsPossible',
                  'RatioMinimumPourAttaquer:float = 0.7','RatioPourAttaquerPerduAChaqueTick = 0.001']:
        need(token in front,'Front pressure missing control: '+token)
    need('AvoidFillerCorridors' not in front,'Front pressure still excludes secondary corridors')
    for name in ['Attack_Main_BA','Attack_Objectives_BA','Attack_Objectives_BA_Autogen']:
        b=obj(attacks,name)
        need('DisableReinforcement = true' in b and 'ForceInAssignedCorridor = true' in b,'Finite local attack missing: '+name)
    reinf=obj(attacks,'Attack_Frontage_Reinforce_BA')
    need('GenerationType = TGenerationType_FixedSize' in reinf and 'MinimumResourceForLaunch_Stage_1' in reinf,
         'Scaling must add one task, not a full corridor fan-out each time')

    defenses=current[MACROS+'SkirmishDefenses.ndf'];screen=obj(defenses,'Defense_Frontage_BA')
    for token in ['TGenerationType_BasedOnNumberOfCorridors','ConsiderOnlyAssignedCorridors = true',
                  'ForceInAssignedCorridor = true','DisableReinforcement = true',
                  'DontUseRegroupPoint = true','DisableAttackDuringZoneDefense = false',
                  'EDefensePointPositioningType/Offensive','DistanceMarginGRU, 177','DistanceDecayLengthGRU, 353']:
        need(token in screen,'Front screen missing control: '+token)
    pool=obj(defenses,'Pool_BA_Frontage_Screen')
    tags=set(re.findall(r'"(\w+)"',pool))
    need(pool.count('TPoolElement(')==2 and pool.count('Nb = 1')==2,'Screen must remain thin')
    need('Required = true' not in pool and all(t.startswith('Infanterie_') for t in tags),'Screen must be optional infantry')
    need('Defense_Frontage_BA_Autogen' not in defenses,'Screen must not have an unbounded expansion variant')
    need(defenses.startswith(prior[MACROS+'SkirmishDefenses.ndf']),'Existing defense/AA settings changed')
    strategy=current[STRATEGIES+'VeryHardSkirmishStrategy.ndf']
    phases={}
    for name in ['Deploiement','Command','LastHope']:
        b=obj(strategy,'VHard_Phase_'+name);tasks=refs(b,'GeneratorList');scaling=refs(b,'ScalingGeneratorList')
        need(tasks.count('Defense_Frontage_BA')==1 and tasks.count('Attack_Frontage_BA')==1,'Coverage generator missing or duplicated')
        need(tasks.index('Defense_Frontage_BA')<tasks.index('Attack_Main_BA'),'Mass assault scheduled before screen')
        need(tasks.index('Attack_Frontage_BA')<tasks.index('Attack_Main_BA'),'Main attack starves front coverage')
        need(not any(t in tasks+scaling for t in ['Attack_Main_Autogen','Attack_Objectives_Lateral','Attack_Objectives_Lateral_Autogen','Defense_Objectif','Attack_Filler']),
             'Repeated main assault, cross-sector convergence or redundant filler returned')
        need(not any(t.startswith('Defense_') and 'AA' not in t for t in scaling),'Ground defense expanded without bound')
        need(scaling.count('Attack_Frontage_Reinforce_BA')==3,'Front reinforcement priorities lost')
        phases[name]={'tasks':tasks,'scaling':scaling}
    audit=json.loads((ROOT/'Development/native-field-audit.json').read_text(encoding='utf-8'))
    need(len(audit['fields'])==3,'Native availability audit incomplete')
    delta=[]
    for name in sorted(allowed):
        delta.extend(difflib.unified_diff(prior[name].splitlines(True),current[name].splitlines(True),
                                         fromfile='test2/'+name,tofile='test3/'+name))
    (ROOT/'Development/test2-to-test3.diff').write_text(''.join(delta),encoding='utf-8')
    return {'baseline_version':'0.2.1-test2','changed_since_test2':sorted(allowed),'phases':phases,
            'native_fields':audit['fields'],'screen_max_requested_infantry_per_task':2,
            'preserved':'Existing combat pools, air/artillery/transport/supply and recovery thresholds',
            'limits':'Corridor counts and force-assignment do not prove evenly spaced units; runtime coverage still required.'}
