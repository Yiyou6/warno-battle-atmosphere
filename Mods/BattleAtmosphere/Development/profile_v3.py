"""Front coverage and native anti-stacking; see FRONTAGE_ITERATION.md.

The second build failed the user's dispersion criterion. Keep its useful role
choices but replace repeated point-focused expansion with assigned-front tasks.
"""
import uuid
import profile_v2 as v2
from profile_v2 import MACROS, STRATEGIES, CONSTANTS, DISPATCH, INF, AT, RECON, AA
from release_info import VERSION

OPENING = [
    'CaptureOneObjectif', 'Reco', 'Defense_Corridor_AA', 'Supply_Skirmish',
    'Defense_Frontage_BA', 'Artillery_Support', 'Attack_Frontage_BA',
    'Attack_Main_BA', 'Airstrike_Offense', 'Attack_Objectives_BA',
    'CaptureHalfZoneObjectif_Ceil', 'Airstrike_AA', 'FOB_Skirmish',
    'Artillery_TriggerHappy', 'CaptureAllZoneObjectif', 'Airstrike_AirReco',
]
COMBAT = [
    'CaptureOneObjectif', 'Supply_Skirmish', 'Reco', 'Defense_Corridor_AA',
    'Defense_Frontage_BA', 'Artillery_Support', 'Attack_Frontage_BA',
    'Attack_Main_BA', 'Airstrike_Offense', 'Attack_Objectives_BA',
    'CaptureHalfZoneObjectif_Ceil', 'Artillery_TriggerHappy', 'Airstrike_AA',
    'Airstrike_SEAD', 'Attack_Helo', 'CaptureOneObjectifForAlliance',
    'Supply_Skirmish_Allied', 'Airstrike_Assault', 'CaptureAllZoneObjectif',
    'Airstrike_AirReco', 'Artillery_Sniper', 'Artillery_Expensive',
]
RECOVERY = [
    'CaptureOneObjectif', 'Supply_Skirmish', 'Reco', 'Defense_Corridor_AA',
    'Defense_Frontage_BA', 'Artillery_Support', 'Attack_Frontage_BA',
    'Attack_Main_BA', 'Airstrike_Offense', 'Attack_Objectives_BA',
    'Artillery_TriggerHappy', 'CaptureAllZoneObjectif', 'Airstrike_AA',
    'Airstrike_SEAD', 'Attack_Helo', 'Supply_Skirmish_Allied', 'Airstrike_Assault',
]
DEPLOY_SCALING = [
    'Supply_Skirmish_Autogen', 'Reco_Autogen', 'Defense_Corridor_AA_Autogen',
    'Attack_Frontage_Reinforce_BA', 'Artillery_Support_Autogen',
    'Airstrike_Offense_Autogen', 'Attack_Frontage_Reinforce_BA',
    'Attack_Objectives_BA_Autogen', 'Artillery_TriggerHappy_Autogen',
    'Airstrike_AA_Autogen', 'Attack_Frontage_Reinforce_BA',
]
COMBAT_SCALING = DEPLOY_SCALING + ['Airstrike_Assault_Autogen', 'Attack_Helo_Autogen']


def template_span(text, name, matching):
    start = text.index('private template ' + name + '\n')
    body = text.index('\nis ', start)
    opening = text.index('(', body)
    return start, matching(text, opening) + 1


def make_profile(base, helpers):
    replace, edit_object, object_span, phase, pool, matching = helpers
    result = v2.make_profile(base, helpers)
    path = STRATEGIES + 'VeryHardSkirmishStrategy.ndf'
    strategy = base[path]
    for name, tasks, scaling in [('Deploiement', OPENING, DEPLOY_SCALING),
                                 ('Command', COMBAT, COMBAT_SCALING),
                                 ('LastHope', RECOVERY, COMBAT_SCALING)]:
        strategy = phase(strategy, 'VHard_Phase_' + name, tasks, scaling)
    result[path] = strategy

    text = result[CONSTANTS]
    text = replace(text, '    MaxNumberOfStackingUnits = 2',
        '    // Native TIAStratConstantesDescriptor fields; absent in the shipped NDF.\n'
        '    UseAntiStackingForVehicles = true\n'
        '    UseAntiStackingForInfantry = true\n'
        '    MaxNumberOfStackingUnits = 1')
    result[CONSTANTS] = text

    path = MACROS + 'SkirmishAttacks.ndf'
    text = result[path]
    # Extend existing templates with unchanged defaults. Only the new highest-
    # difficulty variants forbid reinforcement into an already running mission.
    for name in ['Template_Main_Attack', 'Template_Objective_Attack']:
        a, b = template_span(text, name, matching)
        chunk = text[a:b]
        chunk = replace(chunk, '    AdditionnalParameter = [],',
                        '    AdditionnalParameter = [],\n    DisableReinforcement:bool = false,')
        chunk = replace(chunk, 'TMacroActionProductionSettingHolder(',
                        'TMacroActionProductionSettingHolder(DisableReinforcement = <DisableReinforcement> ',
                        2 if name=='Template_Main_Attack' else 1)
        text = text[:a] + chunk + text[b:]

    a, b = template_span(text, 'Template_Attack_Corridor', matching)
    frontage = text[a:b]
    frontage = replace(frontage, 'Template_Attack_Corridor', 'Template_BA_Frontage_Attack')
    frontage = replace(frontage, '    MinimumResourceForLaunch = MAP[],',
                        '    MinimumResourceForLaunch = MAP[],\n'
                        '    GenerationType = TGenerationType_BasedOnNumberOfCorridors,')
    frontage = replace(frontage, '    ~/AvoidFillerCorridors_Attack_Settings\n    +\n', '')
    frontage = replace(frontage,
        'TGenerationSettingHolder(GenerationType = TGenerationType_FixedSize NumberLaunchBasedOnGenerationType = 1)',
        'TGenerationSettingHolder(GenerationType = <GenerationType> NumberLaunchBasedOnGenerationType = 1 ConsiderOnlyAssignedCorridors = true)')
    frontage = replace(frontage, 'TMacroActionProductionSettingHolder(ProdProperties',
        'TMacroActionProductionSettingHolder(DisableReinforcement = true ProdProperties')
    frontage = replace(frontage, '        TCorridorPlacementSettingHolder(',
        '        TForcedPlacementSettingHolder(ForceInAssignedCorridor = true),\n'
        '        TCorridorPlacementSettingHolder(')
    text += '\n// Assigned front coverage: keep local pressure without an endless large assault pool.\n' + frontage + '''

export Attack_Frontage_BA is Template_BA_Frontage_Attack
(
)

export Attack_Frontage_Reinforce_BA is Template_BA_Frontage_Attack
(
    GenerationType = TGenerationType_FixedSize
    MinimumResourceForLaunch = ~/MinimumResourceForLaunch_Stage_1
)

export Attack_Main_BA is Template_Main_Attack
(
    DisableReinforcement = true
    AdditionnalParameter = [TForcedPlacementSettingHolder(ForceInAssignedCorridor = true)]
)

export Attack_Objectives_BA is Template_Objective_Attack
(
    DisableReinforcement = true
    AdditionnalParameter = [TForcedPlacementSettingHolder(ForceInAssignedCorridor = true)]
)

export Attack_Objectives_BA_Autogen is Template_Objective_Attack
(
    DisableReinforcement = true
    MinimumResourceForLaunch = ~/MinimumResourceForLaunch_Stage_1
    AdditionnalParameter = [TForcedPlacementSettingHolder(ForceInAssignedCorridor = true)]
)
'''
    result[path] = text

    path = MACROS + 'SkirmishDefenses.ndf'
    text = result[path]
    # The v1 offensive scoring already follows the front. Restrict this thin
    # screen to infantry so tank/TD tag overrides cannot pull it far backwards.
    a, b = object_span(text, 'Defense_Corridor_Adaptive')
    old = text[a:b]
    start = old.index('TDefenseBehaviorSettingHolder(')
    opening = old.index('(', start)
    behavior = old[start:matching(old,opening)+1]
    behavior = replace(behavior, 'TDefenseBehaviorSettingHolder(',
                       'TDefenseBehaviorSettingHolder(\n            DontUseRegroupPoint = true')
    screen_tags = [INF, ['Infanterie_AT', 'Infanterie_Standard', 'Infanterie_Spec_Attaque']]
    slots = [(str(uuid.uuid5(uuid.NAMESPACE_URL, 'BattleAtmosphere/FrontageScreen/'+str(i))), tags, 1, 'Cheapest')
             for i,tags in enumerate(screen_tags)]
    text += '''
// A thin forward screen, maintained by assigned-corridor count; no scaling version.
Budget_BA_Frontage_Screen is MAP [($/GFX/Resources/Resource_CommandPoints, 225), ($/GFX/Resources/Resource_Tickets, 10)]
'''
    text += pool('Pool_BA_Frontage_Screen', 'Budget_BA_Frontage_Screen', slots)
    text += '''

export Defense_Frontage_BA is TMacroActionDescriptor_CorridorDefense_Specific
(
    ParametresDeMission = [
        TGenerationSettingHolder(GenerationType = TGenerationType_BasedOnNumberOfCorridors NumberLaunchBasedOnGenerationType = 1 ConsiderOnlyAssignedCorridors = true),
        TAirStrikeSettingHolder(Setting = ~/BasicAirstrikeSupport),
        TArtilleryAmountSettingHolder(ArtilleryAmount = 1),
        TMacroActionProductionSettingHolder(ProdProperties = [TProdProperty_LaunchAsSoonAsPossible] PoolModelList = [~/Pool_BA_Frontage_Screen] DisableReinforcement = true),
        TForcedPlacementSettingHolder(ForceInAssignedCorridor = true),
        ''' + behavior + ''',
    ]
)
'''
    result[path] = text
    return result
