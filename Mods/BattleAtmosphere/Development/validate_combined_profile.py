"""Exact reviewed delta plus deck feasibility; not a purchase simulation."""
from pathlib import Path
import collections,hashlib,json,re,subprocess,sys,zipfile
from apply_combined_profile import ROOT,MACROS,STRATEGY,transform_attack,transform_strategy
from validate_profile import roster,objects,obj,refs

def main():
    subprocess.run([sys.executable,str(ROOT/'Development/apply_combined_profile.py')],check=True,capture_output=True)
    baseline=ROOT/'Development/archive/0.3.0-test3-source.zip'
    with zipfile.ZipFile(baseline) as z:
        protected=[]
        for name in z.namelist():
            if name.endswith('.ndf') and name not in (MACROS,STRATEGY):
                assert (ROOT/name).read_text(encoding='utf-8-sig')==z.read(name).decode('utf-8-sig').replace('\r\n','\n'),name
                protected.append(name)
    attacks=(ROOT/MACROS).read_text();strategy=(ROOT/STRATEGY).read_text()
    macro_dir=ROOT/'GameData/Gameplay/Skirmish/SkirmishMacros'
    all_macros='\n'.join(p.read_text(encoding='utf-8-sig') for p in macro_dir.glob('*.ndf'))
    defined=set(re.findall(r'(?m)^(?:export )?(\w+) is ',all_macros));phases={}
    for phase in ('Deploiement','Command','LastHope'):
        block=obj(strategy,'VHard_Phase_'+phase);initial=refs(block,'GeneratorList');scaling=refs(block,'ScalingGeneratorList')
        assert set(initial+scaling)<=defined
        assert initial.count('Attack_Armor_BA')==1 and scaling.count('Attack_Armor_BA_Autogen')==1
        assert scaling.count('Attack_Frontage_Reinforce_BA')==2
        assert initial.index('Defense_Corridor_AA')<initial.index('Attack_Armor_BA')
        assert all(t in scaling for t in ('Supply_Skirmish_Autogen','Artillery_Support_Autogen'))
        assert not any(t.startswith('Defense_') and 'AA' not in t for t in scaling)
        if phase=='Deploiement':assert not any('Attack_Helo' in t for t in initial+scaling)
        phases[phase]=dict(initial=initial,scaling=scaling)
    for i in (1,2,3):
        block=obj(attacks,'Pool_Default_Attack_'+str(i))
        priorities=re.findall(r'TagsPriority = \[([^\]]*)\]',block)
        assert '"Char_Standard"' in priorities[1] and len(priorities)==6
        assert 'Required = true' not in block
    single=obj(attacks,'Pool_BA_Armor_Opportunity')
    assert single.count('Nb = 1')==1 and 'Required = false' in single
    assert set(re.findall(r'"(\w+)"',single))=={'Char_Standard'}
    with zipfile.ZipFile(ROOT/'base.zip') as z:
        units=roster(z);tanks={n:u for n,u in units.items() if 'Char_Standard' in u['tags']}
        assert tanks and max(u['cost'] for u in tanks.values())<=360
        packs={}
        for n,b in objects(z.read('GameData/Generated/Gameplay/Decks/DeckPacks.ndf').decode('utf-8-sig'),'DeckPackDescriptor'):
            m=re.search(r'\bUnit = \$/GFX/Unit/(\w+)',b)
            if m:packs[n]=m[1]
        decks=[]
        for n,b in objects(z.read('GameData/Generated/Gameplay/Decks/Decks.ndf').decode('utf-8-sig'),'TDeckDescriptor'):
            if not n.endswith('_multi'):continue
            available={packs[p] for p in re.findall(r'~/(Descriptor_Deck_Pack_\w+)',b)}
            available_tanks=sorted(available&tanks.keys())
            decks.append(dict(deck=n,tank_options=len(available_tanks),tank_max_cost=max([tanks[u]['cost'] for u in available_tanks] or [0])))
        assert len(decks)>=60
    ids=re.findall(r'DescriptorId\s*=\s*GUID:\{([^}]+)\}',all_macros)
    oldids=[]
    with zipfile.ZipFile(baseline) as z:
        for n in z.namelist():
            if n.startswith('GameData/Gameplay/Skirmish/SkirmishMacros/') and n.endswith('.ndf'):
                oldids+=re.findall(r'DescriptorId\s*=\s*GUID:\{([^}]+)\}',z.read(n).decode('utf-8-sig'))
    previous=collections.Counter(oldids)
    # Full macro directory can contain unchanged stock identities outside archive.
    new_id=re.search(r'DescriptorId\s*=\s*GUID:\{([^}]+)\}',single)[1]
    assert ids.count(new_id)==1
    report=dict(kind='static-feasibility-not-live-procurement',baseline_sha256=hashlib.sha256(baseline.read_bytes()).hexdigest(),
        protected=protected,phases=phases,default_decks=decks,tank_descriptors=len(tanks),
        tanks_over_old_200_cap=sum(u['cost']>200 for u in tanks.values()),max_tank_cost=max(u['cost'] for u in tanks.values()),
        no_income_changes=True,sources={n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in (MACROS,STRATEGY)})
    (ROOT/'Development/combined-static-validation.json').write_text(json.dumps(report,indent=2))
    print('PASS',len(decks),'default decks;',len(tanks),'tank descriptors;',report['tanks_over_old_200_cap'],'over previous cap')
    print('No tank card:',[d['deck'] for d in decks if not d['tank_options']])
if __name__=='__main__':main()
