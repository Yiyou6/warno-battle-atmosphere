"""Preferred-tag screen candidates with transport costs; not native AI simulation."""
from pathlib import Path
import json
import re
import sys
import zipfile
sys.path.insert(0,str(Path(__file__).resolve().parent))
from apply_profile import ROOT, object_span, matching
from release_info import VERSION


def objects(text, typename):
    for m in re.finditer(r'(?m)^(?:export )?(\w+) is '+typename+r'\s*\(',text):
        a=text.index('(',m.start())
        yield m[1],text[m.start():matching(text,a)+1]


def audit_screen(archive, units):
    source=(ROOT/'GameData/Gameplay/Skirmish/SkirmishMacros/SkirmishDefenses.ndf').read_text(encoding='utf-8-sig')
    a,b=object_span(source,'Pool_BA_Frontage_Screen')
    slots=[re.findall(r'"(\w+)"',s) for s in re.findall(r'TagsPriority\s*=\s*\[([^\]]+)\]',source[a:b])]
    ceiling=int(re.search(r'Budget_BA_Frontage_Screen is MAP \[\(\$/GFX/Resources/Resource_CommandPoints, (\d+)\)',source)[1])
    packs={}
    for name,block in objects(archive.read('GameData/Generated/Gameplay/Decks/DeckPacks.ndf').decode('utf-8-sig'),'DeckPackDescriptor'):
        u=re.search(r'\bUnit = \$/GFX/Unit/(\w+)',block)
        t=re.search(r'\bTransport = \$/GFX/Unit/(\w+)',block)
        if u:packs[name]=(u[1],t[1] if t else None)
    rows=[]
    for name,block in objects(archive.read('GameData/Generated/Gameplay/Decks/Decks.ndf').decode('utf-8-sig'),'TDeckDescriptor'):
        if not name.endswith('_multi'):continue
        choices=[]
        for pk in re.findall(r'~/(Descriptor_Deck_Pack_\w+)',block):
            u,t=packs[pk]
            if units[u]['tags'] & {'InfmapCommander','Avion','Vehicule_Transport'}:continue
            choices.append((units[u]['cost']+(units[t]['cost'] if t else 0),u,t))
        chosen=[]
        for tags in slots:
            for tag in tags:
                valid=[x for x in choices if tag in units[x[1]]['tags']]
                if valid:
                    cost,u,t=min(valid,key=lambda x:(x[0],x[1],x[2] or ''))
                    chosen.append({'preferred_tag':tag,'unit':u,'transport':t,'cost':cost})
                    break
            else:chosen.append(None)
        rows.append({'deck':name,'preferred_candidates':chosen,
                     'combined_cp':sum(x['cost'] for x in chosen) if all(chosen) else None})
    assert len(rows)==70, 'Default-deck coverage changed; re-audit'
    missing=[x['deck'] for x in rows if x['combined_cp'] is None]
    above=[x['deck'] for x in rows if x['combined_cp'] is not None and x['combined_cp']>ceiling]
    assert not missing and not above, ('Screen candidate cost exceeds ceiling or missing role',missing,above)
    report={'version':VERSION,'kind':'STATIC_PREFERRED_CANDIDATES_NOT_NATIVE_PURCHASE_SIMULATION',
            'cp_ceiling':ceiling,'max_preferred_pair_cp':max(x['combined_cp'] for x in rows),
            'infantry_at_fallback_decks':[x['deck'] for x in rows if x['preferred_candidates'][1]['preferred_tag']!='Infanterie_AT'],
            'limitations':['Ignores card stock, runtime pricing, ownership, targets and transport assignment.',
                           'Two optional requested slots need not both be purchased; fallback infantry is not specialist AT.'],
            'decks':rows}
    (ROOT/'Development/frontage-screen-costs.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return {k:v for k,v in report.items() if k!='decks'}


if __name__=='__main__':
    from validate_profile import roster
    with zipfile.ZipFile(str(ROOT/'base.zip')) as archive:
        result=audit_screen(archive,roster(archive))
    print(json.dumps(result,ensure_ascii=False))
