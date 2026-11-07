"""Source safety and deck-cost feasibility checks; this is not an AI simulation."""
from pathlib import Path
import collections
import json
import re
import subprocess
import sys
import zipfile
sys.path.insert(0, str(Path(__file__).resolve().parent))
from apply_profile import ROOT, object_span, matching
from profile_v3 import MACROS, STRATEGIES, CONSTANTS, DISPATCH, INF, AT, RECON, AA, VERSION


def require(ok, message):
    if not ok:
        raise AssertionError(message)


def read(path):
    return (ROOT / path).read_text(encoding='utf-8-sig')


def obj(text, name):
    a, b = object_span(text, name)
    return text[a:b]


def refs(block, field):
    m = re.search(r'\b' + field + r'\s*=\s*\[', block)
    require(m is not None, 'Missing list: ' + field)
    a = block.index('[', m.start())
    return re.findall(r'~/([A-Za-z_0-9]+)', block[a:matching(block, a) + 1])


def objects(text, typename):
    starts = list(re.finditer(r'(?m)^(?:export )?(\w+) is ' + typename + r'\s*\(', text))
    for i, m in enumerate(starts):
        yield m.group(1), text[m.start():starts[i+1].start() if i+1 < len(starts) else len(text)]


def roster(archive):
    text = '\n'.join(archive.read('GameData/Generated/Gameplay/Gfx/' + name).decode('utf-8-sig')
                     for name in ['UniteDescriptor.ndf', 'BuildingDescriptors.ndf'])
    units = {}
    shared = archive.read('GameData/Gameplay/Unit/Tactic/ModulesStandard.ndf').decode('utf-8-sig')
    building_tags = re.search(r'TagSet\s*=\s*\[(.*?)\]', obj(shared, 'BuildingDescriptorTagsModuleDescriptor'), re.S)
    for name, block in objects(text, 'TEntityDescriptor'):
        tags = re.search(r'TTagsModuleDescriptor\s*\(\s*TagSet\s*=\s*\[(.*?)\]', block, re.S)
        cost = re.search(r'\(\$/GFX/Resources/Resource_CommandPoints,\s*(\d+(?:\.\d+)?)\)', block)
        tickets = re.search(r'\(\$/GFX/Resources/Resource_Tickets,\s*(\d+(?:\.\d+)?)\)', block)
        if not tags and '~/BuildingDescriptorTagsModuleDescriptor' in block:
            tags = building_tags
        if tags and cost:
            units[name] = {'tags': set(re.findall(r'"([^"]+)"', tags.group(1))), 'cost': float(cost.group(1)),
                           'tickets': float(tickets.group(1)) if tickets else None}
    return units


def deck_audit(archive, units):
    packs = {}
    text = archive.read('GameData/Generated/Gameplay/Decks/DeckPacks.ndf').decode('utf-8-sig')
    for name, block in objects(text, 'DeckPackDescriptor'):
        unit = re.search(r'\bUnit = \$/GFX/Unit/(\w+)', block)
        transport = re.search(r'\bTransport = \$/GFX/Unit/(\w+)', block)
        if unit:
            packs[name] = (unit.group(1), transport.group(1) if transport else None)
    text = archive.read('GameData/Generated/Gameplay/Decks/Decks.ndf').decode('utf-8-sig')
    rows = []
    for name, block in objects(text, 'TDeckDescriptor'):
        if not name.endswith('_multi'):
            continue
        candidates = []
        for pack in re.findall(r'~/(Descriptor_Deck_Pack_\w+)', block):
            require(pack in packs, 'Unknown default-deck pack: ' + pack)
            unit, transport = packs[pack]
            require(unit in units and (not transport or transport in units), 'Missing unit/transport tags or cost: ' + pack)
            ticket_parts = [units[unit]['tickets']] + ([units[transport]['tickets']] if transport else [])
            ticket_cost = sum(ticket_parts) if all(x is not None for x in ticket_parts) else None
            candidates.append((unit, units[unit]['cost'] + (units[transport]['cost'] if transport else 0), ticket_cost))
        costs = {}
        ticket_costs = {}
        for role, tags in [('infantry', INF), ('anti_tank', AT), ('recon', RECON), ('air_defense', AA)]:
            hits = [(cost, unit) for unit, cost, tickets in candidates if units[unit]['tags'] & set(tags)]
            costs[role] = min(hits) if hits else None
            hits = [(tickets, unit) for unit, cost, tickets in candidates if tickets is not None and units[unit]['tags'] & set(tags)]
            ticket_costs[role] = min(hits) if hits else None
        core = [costs[x] for x in ['infantry', 'anti_tank', 'recon']]
        ticket_core = [ticket_costs[x] for x in ['infantry', 'anti_tank', 'recon']]
        dedicated_at = any(units[unit]['tags'] & set(AT[:-1]) for unit,cost,tickets in candidates)
        rows.append({'deck': name, 'cheapest_roles_including_transport': costs,
                     'has_dedicated_anti_tank': dedicated_at,
                     'core_cost_lower_bound': sum(x[0] for x in core) if all(core) else None,
                     'ticket_core_cost_lower_bound': sum(x[0] for x in ticket_core) if all(ticket_core) else None,
                     'cheapest_ticket_roles_including_transport': ticket_costs,
                     'missing_roles': [role for role, value in costs.items() if value is None]})
    require(len(rows) >= 20, 'Implausibly few parsed default decks')
    return rows


def main():
    subprocess.run([sys.executable, str(ROOT/'Development/apply_profile.py'), '--check'], check=True)
    macros = '\n'.join(p.read_text(encoding='utf-8-sig') for p in (ROOT/MACROS).glob('*.ndf'))
    defined = set(re.findall(r'(?m)^(?:export )?(\w+) is ', macros))
    strategy = read(STRATEGIES+'VeryHardSkirmishStrategy.ndf')
    phase_report = {}
    for phase in ['Deploiement','Command','LastHope']:
        block = obj(strategy,'VHard_Phase_'+phase)
        tasks, scaling = refs(block,'GeneratorList'), refs(block,'ScalingGeneratorList')
        require(set(tasks+scaling) <= defined, 'Unresolved macro in '+phase)
        require(tasks.count('Defense_Corridor_Adaptive') <= 1, 'Repeated static ground defenders')
        require('Defense_Corridor_Adaptive_Autogen' not in scaling, 'Repeated static-defense expansion')
        require('Defense_Objectif' not in tasks, 'Per-objective backline garrisons reintroduced')
        require(tasks.index('Defense_Corridor_AA') < tasks.index('Attack_Main_BA'), 'AA priority starved')
        require('Supply_Skirmish_Autogen' in scaling and 'Artillery_Support_Autogen' in scaling, 'Support replenishment missing')
        if phase == 'Deploiement':
            require(not any('Attack_Helo' in t for t in tasks+scaling), 'Opening combat-helicopter task leak')
        phase_report[phase] = {'tasks':tasks,'scaling':scaling}
    dispatch = read(DISPATCH)
    regions = [dispatch.split('IAStrategyConfiguration = MAP',1)[1].split('IAStrategyOverrideByMap',1)[0],
               dispatch.split('IAStrategyOverrideForTicketsEconomy = MAP',1)[1]]
    for region in regions:
        require(re.search(r'EIADifficulty/PlusDifficile, MAP\s*\[.*?EDeploymentMode/NotSpecified, ~/VeryHardStrategyList',region,re.S), 'Highest-difficulty route missing')
    attacks = read(MACROS+'SkirmishAttacks.ndf')
    ground = ['Pool_Main_Attack','Pool_Objective_Attack'] + ['Pool_'+role+'_Attack_'+str(i)
        for role in ['Default','Infantry','Combined','Tank'] for i in (1,2,3)]
    for name in ground:
        block = obj(attacks,name)
        require('Required = true' not in block, 'Mandatory missing-role risk: '+name)
        require(not re.search(r'"Helo_(AT|Gunship|Transport_Arme)"',block), 'Combat helicopter in ground pool: '+name)
        require('"Infanterie_AT"' in block, 'No explicit AT option: '+name)
    require('ProdProperties = [TProdProperty_LaunchAsSoonAsPossible],' in attacks, 'Unvalidated production delay')
    require('RatioMinimumPourAttaquer = 0.7,' in attacks, 'Main attack ratio changed')
    aa = obj(read(MACROS+'SkirmishDefenses.ndf'),'Pool_AA_Defense')
    require('Required = true' not in aa and 'ProductionFallback' not in aa, 'AA mandatory/non-AA fallback')
    require(set(re.findall(r'"(\w+)"',aa)) <= set(AA), 'Non-AA tag in dedicated pool')
    constants = read(CONSTANTS)
    for setting in ['CanSelectTransportUnits = true','CanRequestTransportProduction = false','ForceSelectCurrentTransporter = true']:
        require(setting in constants,'Transport invariant missing: '+setting)
    for mission in ['Attack','Defense','CorridorAttack','CorridorDefense','CorridorDynamicDefense','ObjectiveAttack']:
        require(re.search(r'EMacroActionMissionType/'+mission+r', \[[^\]]*\x27Vehicule_Transport\x27',constants),'Unarmed combat exclusion missing')
    with zipfile.ZipFile(str(ROOT/'base.zip')) as archive:
        units = roster(archive)
        used_tags = set(AA)
        for name in ground:
            used_tags.update(re.findall(r'"(\w+)"',obj(attacks,name)))
        counts = {tag:sum(tag in u['tags'] for u in units.values()) for tag in sorted(used_tags)}
        require(all(counts.values()),'Tag has no matching unit: '+str([t for t,n in counts.items() if not n]))
        require(not [n for n,u in units.items() if {'Vehicule_Transport','Vehicule_Transport_Arme'} <= u['tags']], 'Armed and unarmed tags overlap')
        pattern = r'DescriptorId\s*=\s*GUID:\{([^}]+)\}'
        original = '\n'.join(archive.read(n).decode('utf-8-sig') for n in archive.namelist()
            if n.startswith(MACROS) and '/' not in n[len(MACROS):] and n.endswith('.ndf'))
        before,after = collections.Counter(re.findall(pattern,original)),collections.Counter(re.findall(pattern,macros))
        require(not [key for key,n in after.items() if n>max(1,before[key])],'New pool-identity collision')
        for path in ['GameData/Gameplay/Constantes/GDConstants.ndf','GameData/Generated/Gameplay/Gfx/UniteDescriptor.ndf',
                     'GameData/Generated/Gameplay/Gfx/Ammunition.ndf',STRATEGIES+'GenericSkirmishStrategy.ndf',STRATEGIES+'HardSkirmishStrategy.ndf']:
            require((ROOT/path).read_bytes()==archive.read(path),'Protected/rejected file changed: '+path)
        decks = deck_audit(archive,units)
        from audit_screen import audit_screen
        screen_costs = audit_screen(archive,units)
    from validate_frontage import check_frontage
    tactics = check_frontage()
    report = {'version':VERSION,'kind':'STATIC_ONLY_NOT_RUNTIME','phase_tasks':phase_report,'tag_matches':counts,
              'tactics_preservation':tactics,
              'frontage_screen_costs':screen_costs,
              'default_decks':decks,'limitations':['Cost lower bounds ignore native priority selection, card stock and timing.',
              'These checks do not prove mission execution, passenger safety or carrier reuse.']}
    (ROOT/'Development/static-validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    expensive = [d['deck'] for d in decks if d['core_cost_lower_bound'] is not None and d['core_cost_lower_bound']>300]
    missing = [(d['deck'],d['missing_roles']) for d in decks if d['missing_roles']]
    print('PASS: references, routes, identities, role tags, transport exclusions and protected baseline.')
    print('Default decks:',len(decks),'core minimum over 300:',len(expensive),'missing-role decks:',len(missing))
    print('Decks needing tank fallback for AT:',[d['deck'] for d in decks if not d['has_dedicated_anti_tank']])
    print('Higher-cost cores:',expensive)
    print('Ticket core maximum:',max(d['ticket_core_cost_lower_bound'] or 0 for d in decks))
    print('Ticket core unavailable:',[d['deck'] for d in decks if d['ticket_core_cost_lower_bound'] is None])
    print('Missing roles:',missing)
    print('Runtime battle behavior remains UNVERIFIED.')


if __name__ == '__main__':
    main()
