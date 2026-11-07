"""Route smoke-tailed warhead impacts to the existing five 122 mm HE variants."""
import json
import re
from collections import Counter,defaultdict
from pathlib import Path
from functools import lru_cache
from apply_profile import matching

MAPPING='GameData/Generated/Gameplay/Gfx/MimeticImpactMapping.ndf'
TARGET='FxImpactSolHE122Mm_'
TARGET_FX=['fx_impact_sol_HE_122mm_%d'%i for i in range(1,6)]


def definitions(text):
    end=text.index('unnamed TMimeticWorldHappeningRegistration')
    result={}
    for m in re.finditer(r'(?m)^(\w+) is \w+\s*\(',text[:end]):
        b=matching(text,text.index('(',m.start()))+1
        result[m[1]]=text[m.start():b]
    return result


def rows(text):
    for m in re.finditer(r"\('([^']+)', TImpactHappening\( Happenings = MAP\[",text):
        end=matching(text,text.index('[',m.start()))
        block=text[m.end():end]
        for line in re.finditer(r'\( EImpactSurface/(\w+)\s*,([^\n]+)',block):
            yield m[1],line[1],m.end()+line.start(2),m.end()+line.end(2),line[2]


def native_catalog(fx):
    from verify_smoke_profile import paths,reachable
    exports=paths(fx,'EXPR');imports={v:k for k,v in paths(fx,'IMPR').items()}
    evidence={};unknown=[];bank_counts=Counter()
    for name,root in exports.items():
        reasons=[]
        for o in reachable(fx,root):
            if o['class']!='TActionCall':continue
            p=o['properties'];target=imports.get(p['Action'].get('import_index'),'').rsplit('/',1)[-1]
            if not target:continue
            bank_counts[target]+=1
            params=dict(p.get('NamedParams',{}).get('map',[]))
            def number(key,default=0):
                if key not in params:return default
                n=fx.objects[params[key]['ref']]
                if n['class'] not in ('TConstantFloat','TConstantInteger'):
                    unknown.append((name,target,key,n['class']));return None
                return n['properties'].get('Value',0)
            if target.startswith('BANK_Rubble2'):
                counts={k:number(k) for k in ('parCountDebritsWithSmoke','parCountDebritsWithFire')}
                if any(v and v>0 for v in counts.values()) and number('parParticleOpacity',1)!=0:
                    reasons.append(dict(bank=target,counts=counts,reason='moving debris emits smoke trail; both smoke and burning debris have trailEvolverSmoke'))
            elif target in ('Smoke_Trail_Simple','Smoke_Trail_Continuous_Simple'):
                opacity=number('parOpacity',1)
                if opacity and opacity>0:
                    reasons.append(dict(bank=target,reason='explicit smoke-trail particle emitter'))
        if reasons:evidence[name.rsplit('/',1)[-1]]=reasons
    assert not unknown,unknown
    for name in TARGET_FX:assert name not in evidence,('122 mm donor has smoke trails',name)
    return evidence,bank_counts


def analyze(original,fx,ammo_texts):
    defs=definitions(original);evidence,counts=native_catalog(fx)
    @lru_cache(None)
    def fx_names(alias):
        block=defs[alias]
        direct=set(re.findall(r'\$/GFX/GameFx/(\w+)',block))
        for token in re.findall(r'\b\w+\b',block):
            if token!=alias and token in defs:direct.update(fx_names(token))
        return direct
    assert fx_names(TARGET)==set(TARGET_FX)
    affected={alias:sorted(fx_names(alias)&evidence.keys()) for alias in defs}
    affected={a:n for a,n in affected.items() if n}
    ammo=defaultdict(list)
    for label,text in ammo_texts.items():
        for m in re.finditer(r'(?m)^(\w+) is TAmmunitionDescriptor\s*\(',text):
            end=matching(text,text.index('(',m.start()))+1;block=text[m.start():end]
            hit=re.search(r"ImpactHappening\s*=\s*'([^']+)'",block)
            if hit:ammo[hit[1]].append(m[1])
    changes=[];preserved=[]
    for weapon,surface,a,b,line in rows(original):
        aliases=[t for t in re.findall(r'\b\w+\b',line) if t in affected]
        if not aliases:continue
        if weapon.startswith('DestructionUnite'):
            preserved.append(dict(weapon=weapon,surface=surface,aliases=aliases,reason='unit destruction: explicitly protected'))
            continue
        if surface in ('Ricochet','Missile') or 'Smoke' in weapon:
            preserved.append(dict(weapon=weapon,surface=surface,aliases=aliases,reason='ricochet/interception-only or tactical smoke ammunition'))
            continue
        if weapon.startswith(('Fusil','Fusile','Mitrailleuse')) or weapon in ('M134Gatling','YakBGatling'):
            preserved.append(dict(weapon=weapon,surface=surface,aliases=aliases,reason='small-arms bullet impact, not an explosive warhead'))
            continue
        # Only registrations actually used by ammunition descriptors are
        # warhead impacts. Destruction effects and scenic props are untouched.
        if weapon not in ammo:
            preserved.append(dict(weapon=weapon,surface=surface,aliases=aliases,reason='no ammunition descriptor reference'))
            continue
        for alias in set(aliases):
            changes.append(dict(weapon=weapon,surface=surface,alias=alias,target=TARGET,
                                affected_fx=affected[alias],ammo=ammo[weapon],a=a,b=b))
    assert any(r['weapon']=='CanonGrosHEM1Abrams' and r['surface']=='Ground' for r in changes)
    assert any(r['weapon']=='CanonGrosHET80' and r['surface']=='Ground' for r in changes)
    return dict(target=TARGET,target_fx=TARGET_FX,changes=changes,preserved=preserved,
                effect_evidence={n:evidence[n] for r in changes for n in r['affected_fx']},
                detected_aliases=affected,warhead_families=len({r['weapon'] for r in changes}),
                ammunition_descriptors=len({n for r in changes for n in r['ammo']}),
                scanned_bank_counts=dict(counts),rendered_appearance='unverified')


def apply(original,report):
    lines=defaultdict(dict)
    for r in report['changes']:lines[(r['a'],r['b'])][r['alias']]=TARGET
    for (a,b),aliases in sorted(lines.items(),reverse=True):
        changed=re.sub(r'\b\w+\b',lambda m:aliases.get(m[0],m[0]),original[a:b])
        assert changed!=original[a:b]
        original=original[:a]+changed+original[b:]
    return original


def extend_sources(z,before,after,reference_fx):
    original=z.read(MAPPING).decode('utf-8-sig').replace('\r\n','\n')
    ammo={n:z.read('GameData/Generated/Gameplay/Gfx/'+n+'.ndf').decode('utf-8-sig') for n in ('Ammunition','AmmunitionMissiles')}
    report=analyze(original,reference_fx,ammo)
    before[MAPPING]=original;after[MAPPING]=apply(original,report)
    return report


if __name__=='__main__':
    import zipfile
    from read_cndf import Cndf
    d=Path(__file__).resolve().parent;m=d.parent
    with zipfile.ZipFile(m/'base.zip') as z:
        report=extend_sources(z,{}, {},Cndf((m/'Gen/NDF/GFX/GameFx.ndfbin').read_bytes()))
    (d/'impact-visual-research.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:report[k] for k in ('warhead_families','ammunition_descriptors')},indent=2))
    print('Changed impact surface routes:',len(report['changes']))
