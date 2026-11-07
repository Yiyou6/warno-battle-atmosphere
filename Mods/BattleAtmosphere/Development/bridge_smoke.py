"""Reuse the independent wind-smoke prop actually placed beside the bridge fire."""
import re
from apply_profile import matching, object_span
from explosion_scale import action_params

SMOKE_FX = 'fx_Small_White_Smoke_Wind_diorama'
SMOKE_SOURCE = 'GameData/Fx/Generated/' + SMOKE_FX + '.ndf'
SMOKE_BANK = 'BA_BridgeWindSmoke'
FINITE_SMOKE = SMOKE_BANK + '_Finite'
NATIVE_WIND = 'AoA_FX_BANK_FireAndDarkSmoke_with_wind_simple'


def call(duration=None):
    if duration is None:
        return 'Template_ActionCall(Action = $/VFX_Bank/%s)' % SMOKE_BANK
    return "Template_ActionCall(Action = $/VFX_Bank/%s NamedParameters = MAP[('parDuration', %s),])" % (FINITE_SMOKE,duration)


def declarations(native):
    # Copy both native layers verbatim, including motion, texture, size, opacity,
    # lifetime and wind. Only the export name changes. A separate wrapper owns
    # emission time; no changes to the native 666-second parent particle clock.
    native=native.replace('export '+SMOKE_FX+' is','export '+SMOKE_BANK+' is',1)
    return native+'''
export %s is SimultaneousActionDeclaration
(
    Params = [ private parDuration is Template_Param_Float(), ]
    Actions = [ Competition(Actions = [
        %s,
        WaitInSec(Duration = parDuration),
    ]), ]
)
''' % (FINITE_SMOKE,call())


def remove_named(text,name):
    a,b=named_span(text,name)
    # object_span includes a declaration prefix but not the list separator.
    while b<len(text) and text[b] in ' \t':b+=1
    if text[b:b+1]==',':b+=1
    return text[:a]+text[b:]


def insert_action(text,name,action):
    a,b=named_span(text,name)
    m=re.search(r'\bActions\s*=\s*(?:\w+\s+is\s*)?\[',text[a:b]);assert m,name
    at=a+m.end()
    return text[:at]+'\n        '+action+',\n'+text[at:]


def named_span(text,name):
    matches=list(re.finditer(r'(?m)^\s*(?:(?:export|private|public) )?'+re.escape(name)+r' is \w+\s*\(',text))
    assert len(matches)==1,(name,len(matches))
    a=matches[0].start();return a,matching(text,text.index('(',a))+1


def ground(text):
    text=remove_named(text,'Smoke')
    return insert_action(text,'FX_BANK_Binder_Fire',call())


def dark(text):
    for name in ('fumees_Starter','fumees','Flame_Starter_Dark'):
        text=remove_named(text,name)
    return insert_action(text,'BANK_DarkFire_AD',call('Duration'))


def fuel(text):
    a,b=object_span(text,'BANK_FuelSmoke');copy=text[a:b]
    copy=copy.replace('export BANK_FuelSmoke is','export BA_BurningFuelSmoke is',1)
    m=re.search(r'\bActions\s*=\s*\[',copy);assert m
    opening=m.end()-1;end=matching(copy,opening)+1
    copy=copy[:opening]+'[\n        '+call('parDuration')+',\n    ]'+copy[end:]
    return text+'\n// Burning-only adapter; ordinary explosion smoke remains native.\n'+copy+'\n'


def mute_mixed_smoke(text,bank):
    edits=[]
    for action,params in action_params(text):
        if action!=bank:continue
        for key,a,b in params:
            if key=='SmokeCountMul':edits.append((a,b,'0'))
    for a,b,value in reversed(edits):text=text[:a]+value+text[b:]
    return text,len(edits)


def building_fire(text):
    # Retain each fire action, local attachment and every non-smoke parameter.
    # Insert smoke on that same mobile, only when the original emits smoke.
    edits=[];count=0
    for m in re.finditer(r'\b(?:TActionCall|Template_ActionCall)\s*\(',text):
        b=matching(text,text.index('(',m.start()))+1;block=text[m.start():b]
        actions=list(action_params(block))
        if not actions or actions[0][0]!='AoA_FX_BANK_FireAndDarkSmoke_Simple':continue
        params={k:block[a:e].strip() for k,a,e in actions[0][1]}
        if float(params.get('SmokeCountMul','0'))==0:continue
        muted,n=mute_mixed_smoke(block,'AoA_FX_BANK_FireAndDarkSmoke_Simple');assert n==1
        edits.append((m.start(),b,muted+',\n                '+call()))
        count+=1
    for a,b,value in reversed(edits):text=text[:a]+value+text[b:]
    return text,count


def extend_buildings(z,before,after):
    changed={}
    for name in z.namelist():
        if not name.startswith('GameData/Fx/Generated/') or not name.endswith('.ndf'):continue
        stem=name.rsplit('/',1)[-1].lower()
        if 'diorama' in stem or not stem.startswith(('fx_destruction_','fx_incendie_','fx_critique_incendie','fx_fireandsmoke_','fx_fireanddarksmoke_')):continue
        original=z.read(name).decode('utf-8-sig').replace('\r\n','\n')
        updated,count=building_fire(after.get(name,original))
        if count:
            before.setdefault(name,original);after[name]=updated;changed[name]=count
    assert changed
    return changed
