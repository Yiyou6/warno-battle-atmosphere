"""Reviewed procurement correction from preserved test3; no game launch/install."""
from pathlib import Path
import hashlib,json,re,uuid,zipfile,sys
from apply_profile import matching,object_span

ROOT=Path(__file__).resolve().parents[1]
MACROS='GameData/Gameplay/Skirmish/SkirmishMacros/SkirmishAttacks.ndf'
STRATEGY='GameData/Gameplay/Skirmish/Strategies/VeryHardSkirmishStrategy.ndf'

def transform_attack(text):
    for name,old,new in [('Tank',200,500),('Default',300,450),('Combined',300,450)]:
        pattern=r'(Budget_'+name+r'_Attack is MAP \[\(\$/GFX/Resources/Resource_CommandPoints, )'+str(old)+r'(\))'
        text,count=re.subn(pattern,lambda m:m[1]+str(new)+m[2],text)
        assert count==1,name
    # Each general corridor option now contains an early real tank opportunity.
    # Existing infantry, recon, AT and AA remain; only duplicate roles replaced.
    for name in ['Pool_Default_Attack_'+str(i) for i in (1,2,3)]:
        a,b=object_span(text,name);block=text[a:b]
        slots=[]
        for m in re.finditer(r'TPoolElement\s*\(',block):
            end=matching(block,block.index('(',m.start()))+1
            slots.append(block[m.start():end])
        assert len(slots)==6
        tank=next((i for i,s in enumerate(slots) if re.search(r'TagsPriority = \["Char_Standard"',s)),None)
        if tank is None:
            tank=3
            slots[tank]=re.sub(r'TagsPriority = \[[^\]]*\]',
                'TagsPriority = ["Char_Standard"]',slots[tank])
        slots[tank]=slots[tank].replace('EPriceComparatorType/Cheapest','EPriceComparatorType/Random')
        chosen=slots.pop(tank);slots.insert(1,chosen)
        begin=block.index('[',block.index('ModelList'))
        finish=matching(block,begin)
        block=block[:begin]+'[\n        '+',\n        '.join(slots)+',\n    ]'+block[finish+1:]
        text=text[:a]+block+text[b:]
    identifier=str(uuid.uuid5(uuid.NAMESPACE_URL,'BattleAtmosphere/combined-v5/armor-opportunity'))
    text+='''
// Distinct armor demand, alongside existing infantry/support requests.
// Budget is a cap, not a required bank balance; one optional tank, ASAP.
export Pool_BA_Armor_Opportunity is TPoolModel
(
    Budget = MAP [($/GFX/Resources/Resource_CommandPoints, 360), ($/GFX/Resources/Resource_Tickets, 20)]
    ModelList = [
        TPoolElement(
            DescriptorId = GUID:{%s}
            Required = false
            IndexPriorityOverPrice = true
            Nb = 1
            PriceComparisonMethod = EPriceComparatorType/Random
            TagsPriority = ["Char_Standard"]
        ),
    ]
)
private template Template_BA_Armor_Opportunity
[
    MinimumResourceForLaunch = MAP[],
]
is TMacroActionDescriptor_CorridorAttack_Specific
(
    ParametresDeMission = ~/Default_Support_Request_Attack_Settings + ~/Blitzkrieg_Attack_Settings + [
        TGenerationSettingHolder(GenerationType = TGenerationType_FixedSize NumberLaunchBasedOnGenerationType = 1 ConsiderOnlyAssignedCorridors = true),
        TMacroActionProductionSettingHolder(DisableReinforcement = true ProdProperties = [TProdProperty_LaunchAsSoonAsPossible] PoolModelList = [~/Pool_BA_Armor_Opportunity]),
        TAttackRatioSettingHolder(RatioMinimumPourAttaquer = 0.7 RatioPourAttaquerPerduAChaqueTick = 0.001),
        TMacroActionLifetimeSettingHolder(MinimumResourceForLaunch = <MinimumResourceForLaunch>),
        TForcedPlacementSettingHolder(ForceInAssignedCorridor = true),
        TCorridorPlacementSettingHolder(MargeDeRegroupementDepuisLaLigneDeFront = 1 ActiveComportementEnBoutDeCouloir = true),
    ]
)
export Attack_Armor_BA is Template_BA_Armor_Opportunity()
export Attack_Armor_BA_Autogen is Template_BA_Armor_Opportunity
(
    MinimumResourceForLaunch = ~/MinimumResourceForLaunch_Stage_1
)
'''%identifier
    return text

def transform_strategy(text):
    for phase in ['Deploiement','Command','LastHope']:
        a,b=object_span(text,'VHard_Phase_'+phase);block=text[a:b]
        block=block.replace('        ~/Attack_Frontage_BA,','        ~/Attack_Armor_BA,\n        ~/Attack_Frontage_BA,',1)
        occurrences=list(re.finditer(r'~/Attack_Frontage_Reinforce_BA,',block))
        assert len(occurrences)==3
        m=occurrences[1]
        block=block[:m.start()]+'~/Attack_Armor_BA_Autogen,'+block[m.end():]
        text=text[:a]+block+text[b:]
    return text

def main():
    write='--write' in sys.argv
    report=[]
    with zipfile.ZipFile(ROOT/'Development/archive/0.3.0-test3-source.zip') as archive:
        for name,fn in [(MACROS,transform_attack),(STRATEGY,transform_strategy)]:
            original=archive.read(name).decode('utf-8-sig').replace('\r\n','\n')
            expected=fn(original)
            path=ROOT/name;current=path.read_text(encoding='utf-8-sig')
            assert current in (original,expected),'Unreviewed edits: '+name
            if write:path.write_text(expected,encoding='utf-8',newline='\n')
            else:assert current==expected,'Not yet applied: '+name
            report.append({'path':name,'source_sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
    output={'status':'source-written-not-game-validated' if write else 'source-matches-reviewed-transform',
        'sources':report,'baseline':'0.3.0-test3-source.zip',
        'notes':['Existing support demands preserved; no funds changed.','Native selection still controls actual purchases; no fake live budget API.']}
    (ROOT/'Development/combined-profile-source.json').write_text(json.dumps(output,indent=2),encoding='utf-8')
    print(json.dumps(output,indent=2))

if __name__=='__main__':main()
