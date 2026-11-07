"""Scale explosion presentation once at leaf bank calls; no gameplay edits."""
from pathlib import Path
import re
from apply_profile import matching

VISUAL_SCALE = 2
SPATIAL_SCALE = 2

# Absolute visual dimensions only. Do not multiply both a base size and its
# existing scale factor. Counts, lifetimes and physical/suppress radii retain
# their original values. Shared VFX banks are never rewritten.
SIZES = set('parSize parSize1 parSize2 parInitialSize parFinalSize parStartSize parEndSize parSizeEnd parSizeLBU parDustSize parMudSize parParticleSize parCloudsize parFireParticleStartSize parFireParticleEndSize parSmokeParticleStartSize parSmokeParticleEndSize parDebritSizeMul BANK_size'.split())
PERSISTENT = {'BA_BurningFuelSmoke', 'BANK_FuelFire',
              'FX_BANK_Binder_Fire', 'AoA_FX_BANK_FireAndDarkSmoke_Simple'}

# Reviewed against bank initializers: dimensional scatter / initial movement,
# not direction cones, scale ratios, gravity, trail density or damage radii.
SPATIAL = {
    'BANK_WasteGroundDustStickOnGround_Simple': {'parStartRandomRadius','parStartSpeed'},
    'BANK_WasteGroundDust_Simple': {'parRandomInitPosRadius','parStartSpeed3D'},
    'DarkSmoke_Simple': {'parRandomPosition','parSpawnerSpeed'},
    'Small_ground_Impact_Simple': {'parRandomPosition'},
    'BANK_Bomb_NewSparks_Simple': {'parPositionRadius','parSpeedMin','parSpeedMax'},
    'BANK_Bomb_NewSparks_Omni_Simple': {'parPositionRadius','parSpeedMin','parSpeedMax'},
    'BANK_Bomb_NewSparks_Simple_Reverse': {'parPositionRadius','parSpeedMin','parSpeedMax'},
    'BANK_Bomb_NewSparks': {'parSpeed'},
    'BANK_Bomb_Sparks_Simple': {'parSpeed'},
    'BANK_Bomb_Sparks_2_Simple': {'parSpeed'},
    'BANK_Bomb_Smoke_MGS_homogeneous_Simple': {'parSpeed'},
    'BANK_Rubble2_Simple': {'parDispersion','parSpeed'},
    'BANK_Rubble2_Oriented_Simple': {'parDispersion','parSpeed'},
    'BANK_Rubble2_Oriented_Simple_Reverse': {'parDispersion','parSpeed'},
    'BANK_FireBalls_Simple': {'parDispersion','parDeltaPositionMobileDirection'},
    'BANK_FireBalls_Alt_Simple': {'parDispersion'},
    'BANK_FireBalls_HQTex_Simple': {'parStartPosition','parSpeed'},
    'BANK_FireBalls_HQTex_Orientable_Simple': {'parStartPosition','parSpeed'},
    'SmokeCircle_Simple': {'parSpawnRadius','parSpeed'},
    'FireCircle_Simple': {'parSpawnRadius','parSpeed'},
    'Smoky_Dust_Projections_Simple': {'parRadius','parInitSpeed'},
    'DirectedFireAnim_Simple': {'parSpawnRadius'},
    'ClusterMunitionAnim_Simple': {'parSpawnRadius'},
    'ClusterMunitionAnimOnPosition_Simple': {'parSpawnRadius'},
    'Smoke_Trail_Simple': {'parDispersion'},
}
# These expressions may contain the event's parPosition anchor. Multiply only
# literal local float3 offsets, never the anchor or the entire expression.
OFFSETS = {
    'BANK_Bomb_Flash': {'parPositionRelative'},
    'BANK_Bomb_NewSparks_Simple': {'parPositionRelative'},
    'BANK_Bomb_NewSparks_Omni_Simple': {'parPositionRelative'},
    'BANK_Bomb_NewSparks_Simple_Reverse': {'parPositionRelative'},
    'BANK_Dynamic_Flash_Simple': {'Position'},
    'BANK_Dynamic_Flash_Only_Two_Simple': {'Position'},
    'BANK_FireBalls_Simple': {'parDeltaPositionAdditif'},
    'BANK_FireBalls_HQTex_Simple': {'parDeltaPosition'},
    'BANK_FireBalls_HQTex_Orientable_Simple': {'parDeltaPosition'},
}

def offset_scale(expression):
    form=re.sub(r'float3\[[^]]+\]','VECTOR',expression)
    assert form in ('VECTOR','VECTOR + parPosition','parPosition','0'),expression
    def vector(m):
        values=[float(v) for v in m[1].split(',')]
        assert len(values)==3
        if not any(values):return m[0]
        return 'float3['+','.join('%g'%(SPATIAL_SCALE*v) for v in values)+']'
    return re.sub(r'float3\[([^]]+)\]',vector,expression)

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
            expression=text[a:b]
            if key in OFFSETS.get(action,set()):
                result=offset_scale(expression);kind='local_offset'
            elif key in SIZES or key in SPATIAL.get(action,set()):
                if re.fullmatch(r'0(?:\.0*)?|float3\[0(?:\.0*)?,\s*0(?:\.0*)?,\s*0(?:\.0*)?\]',expression):continue
                kind='size' if key in SIZES else 'spatial'
                factor=VISUAL_SCALE if kind=='size' else SPATIAL_SCALE
                result='%g * ('%factor+expression+')'
            else:continue
            if result==expression:continue
            edits.append((a,b,result))
            report.append(dict(action=action,parameter=key,before=expression,kind=kind))
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
