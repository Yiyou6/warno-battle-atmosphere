"""Reuse Urban Frontlines' native fuel-fire family for vehicle wrecks."""
import re
from apply_profile import matching, object_span
from bridge_smoke import SMOKE_SOURCE, SMOKE_FX, declarations, call, mute_mixed_smoke, insert_action

MAP_FX = 'fx_incendie_fuel_explosion_Small_diorama'
MAP_SOURCE = 'GameData/Fx/Generated/' + MAP_FX + '.ndf'
MAP_BANK = 'GameData/Fx/Bank/Basics/BANK_FireAndDarkSmoke.ndf'
WRECK_SET = 'GameData/Fx/Set/FX_Destruction_Vehicule.ndf'
DEPICTION = 'GameData/Gameplay/Gfx/Units/DepictionActions.ndf'
NEW_FX = 'BA_UrbanWreckFire'
NATIVE_BANK = 'AoA_FX_BANK_FireAndDarkSmoke_Simple'
NEW_BANK = 'BA_UrbanFireAndDarkSmoke_Simple'
WRECK_EXPORTS = {'$/GFX/GameFx/FX_Vehicule_Dest_Fire', '$/GFX/GameFx/FX_Vehicule_Dest_Fire_Avion'}
FIRE_SIZE_FACTOR = 0.5
SMOKE_LIFETIME_FACTOR = 1.0


def once(s,a,b):
    assert s.count(a)==1,(a,s.count(a))
    return s.replace(a,b,1)


def finite_map_bank(original):
    # Exact native render/particle behavior; only the parent emission clock is
    # bounded. Native finite vertical smoke uses the same WaitInSec lifecycle.
    copy=original.replace('AoA_FX_BANK_FireAndDarkSmoke','BA_UrbanFireAndDarkSmoke')
    copy=copy.replace('FireAndDarkSmoke_Color_Table','BA_UrbanFireAndDarkSmoke_Color_Table')
    copy,n=re.subn(r'(    Params =\s*\[)',r'\1\n        private BA_SourceDuration is Template_Param_Float (),',copy)
    assert n==2
    copy=once(copy,'    NamedParameters = MAP[',"    NamedParameters = MAP[\n        ( 'BA_SourceDuration', BA_SourceDuration ),")
    copy=once(copy,'Template_WaitForEver(), // garde les mobile en vie','WaitInSec(Duration = BA_SourceDuration), // native emitter ownership ends with wreck fire')
    return original+'\n// BattleAtmosphere: duration-bound copy of the native map bank.\n'+copy


def map_effect(original):
    copy=once(original,'export '+MAP_FX+' is Simultaneous','export '+NEW_FX+' is SimultaneousActionDeclaration')
    copy=once(copy,'    Actions = ActionList is', '    Params = [ private parDuration is Template_Param_Float (), ]\n    Actions = BA_UrbanActions is')
    # Keep native appearance except the explicitly requested size/life tuning.
    copy=copy.replace('$/VFX_Bank/'+NATIVE_BANK,'$/VFX_Bank/'+NEW_BANK)
    copy=re.sub(r"(\( 'parDuration', )\d+( \))",r'\1parDuration\2',copy)
    from explosion_scale import action_params
    edits=[]
    for bank,params in action_params(copy):
        if bank==NEW_BANK:
            at=params[0][1]
            # Insert at the opening parenthesis of the first NamedParams pair.
            at=copy.rfind('(',0,at)
            edits.append((at,at,"( 'BA_SourceDuration', parDuration ),\n                        "))
        elif bank=='BANK_VerticalSmoke_Simple':
            key,a,b=next(p for p in params if p[0]=='parLifetime')
            start=copy.rfind("'parLifetime'",0,a)
            edits.append((start,start+len("'parLifetime'"),"'parSmokeLifetime'"))
            at=copy.rfind('(',0,params[0][1])
            edits.append((at,at,"( 'parDuration', parDuration ),\n                        "))
    for a,b,value in sorted(edits,reverse=True):copy=copy[:a]+value+copy[b:]
    copy=copy.replace('$/VFX_Bank/BANK_VerticalSmoke_Simple','$/VFX_Bank/BANK_VerticalSmoke_Finite_Simple')
    adjustments=[]
    fields={NEW_BANK:{'Feu_Size_Mul':FIRE_SIZE_FACTOR,'SmokeDuration':SMOKE_LIFETIME_FACTOR},
            'BANK_FuelFire':{'parSize':FIRE_SIZE_FACTOR},
            'BANK_FuelSmoke':{'parParticleLifetime':SMOKE_LIFETIME_FACTOR},
            'BANK_VerticalSmoke_Finite_Simple':{'parSmokeLifetime':SMOKE_LIFETIME_FACTOR}}
    for bank,params in action_params(copy):
        for key,a,b in params:
            if key in fields.get(bank,{}):
                value=float(copy[a:b].strip())
                adjustments.append((a,b,format(value*fields[bank][key],'.8g')))
    assert len(adjustments)==16,len(adjustments)
    for a,b,value in sorted(adjustments,reverse=True):copy=copy[:a]+value+copy[b:]
    # The independent wind-smoke prop, not fuel fire's own rising smoke,
    # creates the bridge's horizontal plume. Preserve the accepted flames.
    copy,n=mute_mixed_smoke(copy,NEW_BANK);assert n==4
    edits=[]
    for m in re.finditer(r'\bTActionCall\s*\(',copy):
        b=matching(copy,copy.index('(',m.start()))+1
        if 'Action = $/VFX_Bank/BANK_FuelSmoke' not in copy[m.start():b]:continue
        while copy[b:b+1] in (' ','\t'):b+=1
        if copy[b:b+1]==',':b+=1
        edits.append((m.start(),b))
    assert len(edits)==3
    for a,b in reversed(edits):copy=copy[:a]+copy[b:]
    copy=insert_action(copy,NEW_FX,call('parDuration'))
    return copy


def wreck_wrappers(original, native_effect):
    for name in ('FX_Vehicule_Dest_Fire','FX_Vehicule_Dest_Fire_Avion'):
        a,b=object_span(original,name)
        replacement='''export %s is SimultaneousActionDeclaration
(
    Params =
    [
        private parScaleFactor is Template_Param_Float (DefaultValue = 1),
        private parDuration is Template_Param_Float (),
    ]
    Actions =
    [
        Competition
        (
            Actions =
            [
                Template_ActionCall
                (
                    Action = ~/%s
                    NamedParameters = MAP[( 'parDuration', Clamp[parDuration,10,1200] ),]
                ),
                WaitInSec(Duration = Clamp[parDuration,10,1200]),
            ]
        ),
    ]
)
'''%(name,NEW_FX)
        original=original[:a]+replacement+original[b:]
    return original+'\n// Native map effect, lifecycle adapted for a vehicle wreck.\n'+map_effect(native_effect)


def single_wreck_source(original):
    a=original.index('template CompositeCadaverFX')
    b=matching(original,original.index('(',a))+1
    # The engine rejects a TCompositeHappening with a single child. Inline the
    # existing first FxCadavre directly; the native map FX owns its fire sound.
    first=original.index('template FxCadavre\n')
    opening=original.index('(',original.index('] is TIntroduceMobileHappening',first))
    body=original[opening:matching(original,opening)+1]
    block='template CompositeCadaverFX [Fx] is TIntroduceMobileHappening\n'+body.replace('<SousMobile>','"fx_stress_01"')
    return original[:a]+block+original[b:]


def remove_vehicle_fuel_layers(text):
    edits=[]
    for m in re.finditer(r'\b(?:TActionCall|Template_ActionCall)\s*\(',text):
        b=matching(text,text.index('(',m.start()))+1
        if not re.search(r'Action = \$/VFX_Bank/(?:BANK_FuelFire|BANK_FuelSmoke|BA_BurningFuelSmoke)\s',text[m.start():b]):continue
        end=b
        while end<len(text) and text[end] in ' \t':end+=1
        if end<len(text) and text[end]==',':end+=1
        edits.append((m.start(),end))
    for a,b in reversed(edits):text=text[:a]+text[b:]
    return text,len(edits)


def extend_sources(z,before,after):
    read=lambda n:z.read(n).decode('utf-8-sig').replace('\r\n','\n')
    for n in (MAP_BANK,WRECK_SET,DEPICTION):before[n]=read(n)
    after[MAP_BANK]=finite_map_bank(before[MAP_BANK])+'\n'+declarations(read(SMOKE_SOURCE))
    after[WRECK_SET]=wreck_wrappers(before[WRECK_SET],read(MAP_SOURCE))
    after[DEPICTION]=single_wreck_source(before[DEPICTION])
    removed={}
    for name in list(after):
        if name.startswith('GameData/Fx/Generated/fx_impact_destruction_unite_'):
            after[name],n=remove_vehicle_fuel_layers(after[name])
            if n:removed[name]=n
    assert sum(removed.values())>0
    return dict(native_family='FX_Fire_Fuel_Explosion_Small_RandomDuration',native_fx=MAP_FX,
                native_smoke_fx=SMOKE_FX,old_wreck_fuel_smoke_calls_removed=3,old_wreck_mixed_smoke_calls_muted=4,
                removed_vehicle_fuel_calls=removed,source_count_per_wreck=1,burn_seconds=[10,1200],
                fire_size_factor=FIRE_SIZE_FACTOR,smoke_lifetime_factor=SMOKE_LIFETIME_FACTOR)
