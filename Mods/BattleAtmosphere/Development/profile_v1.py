"""BattleAtmosphere first playable candidate, rebuilt from the official baseline.

This module declares experiments, not verified runtime effects. Every change is
mapped to SKIRMISH_DESIGN.md in IMPLEMENTATION.md. No unit/weapon/economy edits.
"""
import re

VERSION = '0.2.0-test1'
MACROS = 'GameData/Gameplay/Skirmish/SkirmishMacros/'
STRATEGIES = 'GameData/Gameplay/Skirmish/Strategies/'
CONSTANTS = 'GameData/Gameplay/Constantes/IAStratConstantes.ndf'
DISPATCH = 'GameData/Gameplay/Skirmish/IASkirmishDescriptors.ndf'

# Role order matters under a finite pool budget. Ground formations do not use
# combat helicopters as substitutes. Dedicated tasks retain those aircraft.
INF = ['Infanterie_Standard', 'Infanterie_Spec_Attaque', 'Infanterie_noAT']
AT = ['Infanterie_AT', 'ChasseurDeChar_Standard', 'ChasseurDeChar', 'Char_Standard']
RECON = ['Infanterie_Reco', 'Vehicule_Reco', 'Char_Reco']
AA = ['Infanterie_AA', 'Canon_AA_Standard', 'Canon_AA_Porte', 'Canon_AA']
TANK = ['Char_Standard', 'Char', 'ChasseurDeChar_Standard', 'Vehicule_Appui', 'Infanterie_AT']
SUPPORT = ['Vehicule_Appui', 'Vehicule_Transport_Arme', 'Infanterie_Spec_Attaque', 'Infanterie_Standard']

OPENING = [
    'CaptureOneObjectif', 'Reco', 'Defense_Corridor_AA', 'Attack_Objectives',
    'Supply_Skirmish', 'Artillery_Support', 'Attack_Main', 'Airstrike_Offense',
    'Attack_Adaptive', 'CaptureHalfZoneObjectif_Ceil', 'Airstrike_AA',
    'FOB_Skirmish', 'Defense_Corridor_Adaptive', 'Artillery_TriggerHappy',
    'Attack_Filler', 'CaptureAllZoneObjectif', 'Airstrike_AirReco',
]
COMBAT = [
    'CaptureOneObjectif', 'Supply_Skirmish', 'Reco', 'Defense_Corridor_AA',
    'Attack_Objectives', 'Artillery_Support', 'Attack_Main', 'Airstrike_Offense',
    'Attack_Adaptive', 'Defense_Corridor_Adaptive', 'CaptureHalfZoneObjectif_Ceil',
    'Artillery_TriggerHappy', 'Airstrike_AA', 'Airstrike_SEAD',
    'Attack_Filler', 'Attack_Helo', 'Attack_Adaptive',
    'CaptureOneObjectifForAlliance', 'Supply_Skirmish_Allied',
    'Airstrike_Assault', 'CaptureAllZoneObjectif', 'Airstrike_AirReco',
    'Artillery_Sniper', 'Artillery_Expensive',
]
RECOVERY = [
    'CaptureOneObjectif', 'Supply_Skirmish', 'Reco', 'Defense_Corridor_AA',
    'Attack_Objectives', 'Artillery_Support', 'Attack_Main', 'Airstrike_Offense',
    'Attack_Adaptive', 'Defense_Corridor_Adaptive', 'Artillery_TriggerHappy',
    'CaptureAllZoneObjectif', 'Airstrike_AA', 'Airstrike_SEAD',
    'Attack_Filler', 'Attack_Helo', 'Attack_Adaptive',
    'Supply_Skirmish_Allied', 'Airstrike_Assault',
]
DEPLOY_SCALING = [
    'Supply_Skirmish_Autogen', 'Reco_Autogen', 'Defense_Corridor_AA_Autogen',
    'Attack_Adaptive_Autogen', 'Artillery_Support_Autogen', 'Attack_Main_Autogen',
    'Airstrike_Offense_Autogen', 'Attack_Objectives_Autogen',
    'Attack_Adaptive_Autogen', 'Artillery_TriggerHappy_Autogen', 'Airstrike_AA_Autogen',
]
COMBAT_SCALING = DEPLOY_SCALING + [
    'Attack_Objectives_Allied_Autogen', 'Airstrike_Assault_Autogen', 'Attack_Helo_Autogen',
]


def make_profile(base, helpers):
    replace, edit_object, object_span, phase, pool, matching = helpers
    result = {}
    path = STRATEGIES + 'VeryHardSkirmishStrategy.ndf'
    text = base[path]
    for name, tasks, scaling in [
        ('Deploiement', OPENING, DEPLOY_SCALING),
        ('Command', COMBAT, COMBAT_SCALING),
        ('LastHope', RECOVERY, COMBAT_SCALING),
    ]:
        text = phase(text, 'VHard_Phase_' + name, tasks, scaling)
    result[path] = text

    # Highest difficulty must not fall back to the vanilla generic strategy when
    # a non-breakthrough tickets-economy override applies. Do not change BKT.
    text = base[DISPATCH]
    anchor = '    IAStrategyOverrideForTicketsEconomy = MAP\n    [\n'
    entry = ('        (EIADifficulty/PlusDifficile, MAP\n'
             '        [\n'
             '            (EDeploymentMode/Breakthrough, ~/BKTDefaultStrategyList),\n'
             '            (EDeploymentMode/NotSpecified, ~/VeryHardStrategyList),\n'
             '        ]),\n')
    result[DISPATCH] = replace(text, anchor, anchor + entry)

    path = MACROS + 'SkirmishMisc.ndf'
    # Ground support requests use actual unit tags. Other supply thresholds and
    # retreat/recovery timing remain vanilla to avoid new backline waiting.
    result[path] = replace(base[path],
        '["Avion_Assaut", "Chasseur_Bombardier", "Bombardier",]',
        '["Avion_Bombardier", "Avion_AT", "Avion_Napalm",]')

    path = MACROS + 'SkirmishAttacks.ndf'
    text = base[path]

    def rewrite_pool(name, roles, quantities=None, random_roles=()):
        nonlocal text
        a, b = object_span(text, name)
        old = text[a:b]
        guids = re.findall(r'DescriptorId\s*=\s*GUID:\{([^}]+)\}', old)
        budget = re.search(r'Budget = ~/(\w+)', old).group(1)
        if len(roles) > len(guids):
            raise ValueError('Insufficient existing identities: ' + name)
        quantities = quantities or [1] * len(roles)
        slots = [(guids[i], tags, quantities[i], 'Random' if i in random_roles else 'Cheapest')
                 for i, tags in enumerate(roles)]
        text = text[:a] + pool(name, budget, slots) + text[b:]

    # Seven original main slots; keep its original 600-point ceiling and ASAP.
    # Infantry and AT precede the optional expensive tank, rather than two
    # MostExpensive tanks consuming the budget before infantry is considered.
    rewrite_pool('Pool_Main_Attack', [INF, AT, RECON, INF, AA, TANK, SUPPORT], random_roles=(5,))
    rewrite_pool('Pool_Objective_Attack', [INF, AT, RECON, TANK], random_roles=(3,))
    for i in (1, 2, 3):
        rewrite_pool('Pool_Default_Attack_' + str(i), [INF, AT, RECON, AA, TANK, SUPPORT])
        rewrite_pool('Pool_Infantry_Attack_' + str(i), [INF, AT, RECON, AA, INF, SUPPORT])
        rewrite_pool('Pool_Combined_Attack_' + str(i), [INF, AT, RECON, TANK, AA, INF, SUPPORT])
        # Preserve an armoured leading role on tank corridors, then support it.
        rewrite_pool('Pool_Tank_Attack_' + str(i), [TANK, RECON, INF, AA, AT, TANK])
    rewrite_pool('Pool_Attack_Helo', [['Helo_AT', 'Helo_Gunship']])
    # The 70-deck audit found 13 three-role cores above 200 CP including
    # transport, with a 275 CP maximum before tank fallback. Use the existing
    # objective-group 300 CP ceiling for mixed groups. ASAP/optional slots stay
    # enabled; this is a ceiling, not a newly imposed gather/wait requirement.
    for budget, old in [('Infantry', 160), ('Default', 200), ('Combined', 200)]:
        text = replace(text,
            'Budget_' + budget + '_Attack is MAP [($/GFX/Resources/Resource_CommandPoints, ' + str(old) + ')',
            'Budget_' + budget + '_Attack is MAP [($/GFX/Resources/Resource_CommandPoints, 300)')
    # The ticket audit finds up to 10 explicitly priced tickets for the core;
    # match the existing default/combined ticket cap, instead of leaving 4.
    text = replace(text,
        'Budget_Infantry_Attack is MAP [($/GFX/Resources/Resource_CommandPoints, 300) , ($/GFX/Resources/Resource_Tickets, 4)]',
        'Budget_Infantry_Attack is MAP [($/GFX/Resources/Resource_CommandPoints, 300) , ($/GFX/Resources/Resource_Tickets, 10)]')
    # Original filler groups have a fixed 1.75 ratio with no decay. Use an
    # initially even engagement threshold and the existing main-attack decay.
    text = edit_object(text, 'Attack_Filler', lambda block: replace(block,
        'TAttackRatioSettingHolder(RatioMinimumPourAttaquer = 1.75)',
        'TAttackRatioSettingHolder(RatioMinimumPourAttaquer = 1.0 RatioPourAttaquerPerduAChaqueTick = 0.00084)'))
    text = edit_object(text, 'Pool_Attack_Filler', lambda block: replace(block,
        '"Vehicule_Appui",', '"Vehicule_Appui",\n                "Vehicule_Transport_Arme",'))
    result[path] = text

    path = MACROS + 'SkirmishDefenses.ndf'
    def aa_pool(block):
        block = replace(block, 'Required = true', 'Required = false')
        block = replace(block, 'IndexPriorityOverPrice = false', 'IndexPriorityOverPrice = true')
        block = replace(block, 'EPriceComparatorType/Random', 'EPriceComparatorType/Cheapest')
        block = replace(block, '"Helo_AA",', '"Infanterie_AA",\n                "Canon_AA",')
        return replace(block, '            +~/ProductionFallback\n', '')
    text = edit_object(base[path], 'Pool_AA_Defense', aa_pool)
    # Reuse the vanilla recon placement settings for a front-oriented defensive
    # task. Only adaptive ground defense uses this, not all AA/supply/capture.
    start = base[MACROS + 'SkirmishMisc.ndf'].index('        TDefenseBehaviorSettingHolder(')
    source = base[MACROS + 'SkirmishMisc.ndf'][start:]
    opening = source.index('(')
    setting = source[:matching(source, opening) + 1]
    setting = replace(setting, 'DisableAttackDuringZoneDefense = true', 'DisableAttackDuringZoneDefense = false')
    text = replace(text, '    UseTaggedPool:bool = true\n', '    UseTaggedPool:bool = true,\n    AdditionnalParameter = []\n')
    anchor = '        TMacroActionLifetimeSettingHolder(MinimumResourceForLaunch = <MinimumResourceForLaunch>),\n    ]\n)'
    text = replace(text, anchor, anchor[:-2] + '\n    + <AdditionnalParameter>\n)')
    text = edit_object(text, 'Defense_Corridor_Adaptive', lambda block: replace(block,
        '(\n)', '(\n    AdditionnalParameter = [\n' + setting + ',\n    ]\n)'))
    result[path] = text

    path = MACROS + 'SkirmishArtillery.ndf'
    text = replace(base[path], 'DifficultyList = [EIADifficulty/TresDifficile]',
        'DifficultyList = [EIADifficulty/TresDifficile, EIADifficulty/PlusDifficile]', 3)
    a, b = object_span(text, 'Artillery_Support')
    support = replace(text[a:b], 'export Artillery_Support is', 'export Artillery_Support_Autogen is')
    support = replace(support, '        TArtilleryMoveAfterShootSettingHolder(),',
        '        TMacroActionLifetimeSettingHolder(MinimumResourceForLaunch = ~/MinimumResourceForLaunch_Stage_1),\n'
        '        TArtilleryMoveAfterShootSettingHolder(),')
    result[path] = text + '\n// Coordinated support remains available to reinforcement priorities.\n' + support + '\n'

    path = MACROS + 'SkirmishAirstrike.ndf'
    text = base[path]
    for name in ['Airstrike_Assault', 'Airstrike_Assault_Autogen']:
        text = edit_object(text, name, lambda block: replace(block,
            '    PoolModel = ~/Pool_Airstrike_Assault\n',
            '    PoolModel = ~/Pool_Airstrike_Assault\n    AnnulerSupportSiAttaqueEchoue = true\n'))
    # No increase in danger tolerance. Failed assault support uses the same
    # cancellation option as vanilla offensive support; no invented timeout.
    result[path] = text

    text = replace(base[CONSTANTS], 'CanSelectTransportUnits = false', 'CanSelectTransportUnits = true')
    # Allow existing armed carriers to be considered without enabling requests
    # for extra transports. Keep current passenger/transporter association.
    # Explicitly exclude the unarmed ground-transport tag from combat tasks.
    for mission in ['Attack', 'Defense', 'CorridorAttack', 'CorridorDefense',
                    'CorridorDynamicDefense', 'ObjectiveAttack']:
        pat = r'(\(EMacroActionMissionType/' + mission + r', \[)([^\]]+)(\])'
        text, count = re.subn(pat, lambda m: m[1] + m[2] + ",'Vehicule_Transport'" + m[3], text)
        if count != 1:
            raise ValueError('Expected combat transport exclusion for ' + mission)
    result[CONSTANTS] = text
    return result
