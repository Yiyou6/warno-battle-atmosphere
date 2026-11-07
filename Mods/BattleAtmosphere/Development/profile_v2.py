"""Dispersion/role experiment layered on the user-tested first build.

Native movement effects are hypotheses until a new battle is observed.
See TACTICS_ITERATION.md for evidence, coupled risks and preservation controls.
"""
import re
import profile_v1 as v1
from profile_v1 import MACROS, STRATEGIES, CONSTANTS, DISPATCH, INF, AT, RECON, AA, TANK, SUPPORT
from release_info import VERSION

ASSAULT = ['Infanterie_Spec_Attaque', 'Infanterie_Standard', 'Infanterie_noAT']

# Distinct slot content, not three copies of the same pool under new names.
# Existing budgets, optional roles and immediate production are retained.
ROLE_VARIANTS = {
    'Default': [
        [INF, RECON, AT, AA, TANK, SUPPORT],
        [AT, INF, RECON, AT, AA, SUPPORT],
        [RECON, INF, AT, INF, SUPPORT, AA],
    ],
    'Infantry': [
        [ASSAULT, INF, AT, RECON, AA, SUPPORT],
        [AT, INF, RECON, AT, AA, INF],
        [RECON, INF, AT, SUPPORT, INF, AA],
    ],
    'Combined': [
        [INF, RECON, AT, TANK, AA, SUPPORT, INF],
        [AT, INF, RECON, AT, AA, SUPPORT, TANK],
        [RECON, INF, AT, SUPPORT, INF, AA, TANK],
    ],
    'Tank': [
        [TANK, RECON, INF, AA, AT, TANK],
        [AT, TANK, RECON, INF, AA, SUPPORT],
        [RECON, TANK, INF, AT, SUPPORT, AA],
    ],
}


def replace_second(tasks, old, new):
    result = list(tasks)
    indices = [i for i, task in enumerate(result) if task == old]
    if len(indices) != 2:
        raise ValueError('Expected two tasks: ' + old)
    result[indices[1]] = new
    return result


def make_profile(base, helpers):
    replace, edit_object, object_span, phase, pool, matching = helpers
    result = v1.make_profile(base, helpers)
    path = STRATEGIES + 'VeryHardSkirmishStrategy.ndf'
    # One lateral mission replaces one repeated adaptive mission. In scaling,
    # move the existing other-corridor role earlier, retaining task counts.
    scaling = replace_second(v1.COMBAT_SCALING, 'Attack_Adaptive_Autogen', 'Attack_Objectives_Lateral_Autogen')
    scaling[scaling.index('Attack_Objectives_Allied_Autogen')] = 'Attack_Adaptive_Autogen'
    strategy = base[path]
    for name, tasks, expansion in [
        ('Deploiement', v1.OPENING, v1.DEPLOY_SCALING),
        ('Command', replace_second(v1.COMBAT, 'Attack_Adaptive', 'Attack_Objectives_Lateral'), scaling),
        ('LastHope', replace_second(v1.RECOVERY, 'Attack_Adaptive', 'Attack_Objectives_Lateral'), scaling),
    ]:
        strategy = phase(strategy, 'VHard_Phase_' + name, tasks, expansion)
    result[path] = strategy

    path = MACROS + 'SkirmishAttacks.ndf'
    text = result[path]
    for family, variants in ROLE_VARIANTS.items():
        for index, roles in enumerate(variants, 1):
            name = 'Pool_' + family + '_Attack_' + str(index)
            a, b = object_span(text, name)
            old = text[a:b]
            guids = re.findall(r'DescriptorId\s*=\s*GUID:\{([^}]+)\}', old)
            budget = re.search(r'Budget = ~/(\w+)', old).group(1)
            if len(roles) != len(guids):
                raise ValueError('Role count changed unexpectedly: ' + name)
            slots = [(guid, tags, 1, 'Cheapest') for guid, tags in zip(guids, roles)]
            text = text[:a] + pool(name, budget, slots) + text[b:]

    text = replace(text, '    SupportingStatus = ESupportingStatus/NeedSupport,\n',
                   '    SupportingStatus = ESupportingStatus/NeedSupport,\n'
                   '    PrioritizeTaggedCorridors:bool = true,\n')
    text = replace(text, 'PrioritizeCorridorsForTaggedPoolModels = true',
                   'PrioritizeCorridorsForTaggedPoolModels = <PrioritizeTaggedCorridors>', 2)
    text = edit_object(text, 'Attack_Main_Autogen', lambda block: replace(block,
        '    MinimumResourceForLaunch = ~/MinimumResourceForLaunch_Stage_1',
        '    MinimumResourceForLaunch = ~/MinimumResourceForLaunch_Stage_1\n'
        '    PrioritizeTaggedCorridors = false'))

    # Existing native objective-selection settings from Allied_Autogen, with a
    # recon/infantry pool and the main attack's nonblocking ratio decay.
    text += '''
// Secondary enemy objectives: a preference, not scripted flanking or a timer.
private template Template_BA_Lateral_Attack
[
    MinimumResourceForLaunch = MAP[],
]
is TMacroActionDescriptor_ObjectiveAttack_Specific
(
    ParametresDeMission =
    ~/Default_Support_Request_Attack_Settings
    + ~/Blitzkrieg_Attack_Settings
    + [
        TGenerationSettingHolder(GenerationType = TGenerationType_FixedSize NumberLaunchBasedOnGenerationType = 1),
        TMacroActionProductionSettingHolder(ProdProperties = [TProdProperty_LaunchAsSoonAsPossible] PoolModelList = [~/Pool_Default_Attack_3]),
        TAttackRatioSettingHolder(RatioMinimumPourAttaquer = 0.7 RatioPourAttaquerPerduAChaqueTick = 0.00084),
        TMacroActionLifetimeSettingHolder(MinimumResourceForLaunch = <MinimumResourceForLaunch>),
        TObjectiveRequiresEnnemiesPossessionSettingHolder(),
        TObjectiveAttackSetting(ZoneSources = [EMapSlicingZoneSource/ScenarioIAStrat, EMapSlicingZoneSource/ScenarioCommand] PriorizeObjectiveNotInMyCorridor = true),
    ]
)

export Attack_Objectives_Lateral is Template_BA_Lateral_Attack
(
)

export Attack_Objectives_Lateral_Autogen is Template_BA_Lateral_Attack
(
    MinimumResourceForLaunch = ~/MinimumResourceForLaunch_Stage_1
)
'''
    result[path] = text
    text = result[CONSTANTS]
    for old, new in [
        ('MergeGroupDistInPolygon = 2.0', 'MergeGroupDistInPolygon = 1.0'),
        ('AddToGroupDistInPolygon = 1.5', 'AddToGroupDistInPolygon = 0.75'),
        ('BlitzkriegMultiplierForTacticalPathInCover = 4.0', 'BlitzkriegMultiplierForTacticalPathInCover = 2.0'),
    ]:
        text = replace(text, old, new)
    result[CONSTANTS] = text
    return result
