"""Scale explosion presentation once at leaf bank calls; no gameplay edits."""
from pathlib import Path
import re
from apply_profile import matching

VISUAL_SCALE = 3  # Preview.15: previous 2x appearance multiplied by 1.5.

# Absolute visual dimensions only. Do not multiply both a base size and its
# existing scale factor. Positions, counts, lifetimes and physical/suppress
# radii retain their original values. Shared VFX banks are never rewritten.
SIZES = set('parSize parSize1 parSize2 parInitialSize parFinalSize parStartSize parEndSize parSizeEnd parSizeLBU parDustSize parMudSize parParticleSize parCloudsize parFireParticleStartSize parFireParticleEndSize parSmokeParticleStartSize parSmokeParticleEndSize parDebritSizeMul BANK_size'.split())
PERSISTENT = {'BA_BurningFuelSmoke', 'BANK_FuelFire',
              'FX_BANK_Binder_Fire', 'AoA_FX_BANK_FireAndDarkSmoke_Simple'}

def selected(name):
    s = Path(name).stem.lower()
    if name == 'GameData/Fx/Set/FX_Impact_Nuke.ndf': return True
    if not name.startswith('GameData/Fx/Generated/'): return False
    if any(x in s for x in ('balle', 'smoke', 'fumee')): return False
    return s.startswith(('fx_impact_', 'fx_destruction_', 'fx_batiment_explosion_',
                         'fx_crash_', 'fx_arret_missile_', 'fx_he_', 'fx_ouverture_')) or s in (
                             'fx_critique_ammo_explosion','fx_critique_fuel_explosion')

def action_params(text):
    """Yield each leaf call and exact top-level parameter expression spans."""
    for m in re.finditer(r'\b(?:TActionCall|Template_ActionCall)\s*\(', text):
        end = matching(text, text.index('(',m.start()))
        block = text[m.start():end]
        action = re.search(r'\bAction\s*=\s*([^\s\r\n]+)',block)
        params = re.search(r'\bNamedParam(?:s|eters)\s*=\s*MAP\s*\[',block)
        if not action or not params: continue
        begin = m.start()+params.end()-1
        limit = matching(text,begin)
        cursor=begin+1; values=[]
        while cursor<limit:
            if text.startswith('//',cursor):
                cursor=text.index('\n',cursor);continue
            if text[cursor]!='(': cursor+=1;continue
            close=matching(text,cursor)
            key=re.match(r"\(\s*'([^']+)'\s*,\s*",text[cursor:close])
            assert key, text[cursor:close]
            a=cursor+key.end(); b=close
            while text[b-1].isspace():b-=1
            values.append((key[1],a,b))
            cursor=close+1
        yield action[1].rsplit('/',1)[-1], values

def scale(text):
    edits=[]; report=[]
    for action, params in action_params(text):
        if action in PERSISTENT or action.startswith(('SFX','Shake','Destroy','Dummy','Propulsion','FX_BANK_')):continue
        for key,a,b in params:
            if key not in SIZES:continue
            expression=text[a:b]
            if re.fullmatch(r'0(?:\.0*)?',expression):continue
            edits.append((a,b,'%g * (' % VISUAL_SCALE+expression+')'))
            report.append(dict(action=action,parameter=key,before=expression))
    for a,b,value in reversed(edits):text=text[:a]+value+text[b:]
    return text,report

def extend_sources(z, before, after):
    records=[]
    for name in z.namelist():
        if not name.endswith('.ndf') or not selected(name):continue
        original=z.read(name).decode('utf-8-sig').replace('\r\n','\n')
        target,changes=scale(after.get(name,original))
        if not changes:continue
        before.setdefault(name,original);after[name]=target
        records.append(dict(path=name,changes=changes))
    assert len(records)>400, len(records)
    return records
