# Empty-headless-lobby fixture only. Never installed or used in real skirmish.
import _ba_native as native
import _ndf
import sip
import _gd_object_specific as specific
import _gd_variable as var
import _gd_descriptor as gd
import _gd_tag as tag
import struct
import _front_game_rules_specific as rules
keep = []
def prepare():
    base = _ndf.Database.GetObject('$/GDScript/RootDescriptor')
    native.log('FIXTURE_ROOT_TYPE '+str(type(base)))
    root_address=long(sip.unwrapinstance(base))-16
    root = native.fixture_wrap_root(struct.pack('<Q',root_address))
    if root is None: raise RuntimeError('fixture root wrapper rejected')
    native.log('FIXTURE_ROOT_POINTER '+repr((root_address,long(sip.unwrapinstance(root)))))
    if long(sip.unwrapinstance(root))!=root_address:
        raise RuntimeError('fixture root wrapper address changed')
    raw_mode=native.fixture_mode()
    mode=raw_mode.replace('_swapped','') if isinstance(raw_mode,str) else raw_mode
    camps = [var.TGDVariableCamp() for i in range(20 if mode=='tenvten' else 6 if mode=='mass' else 5 if mode=='battle' else 4)]
    for i,c in enumerate(camps): c.SetAlliance((1 if i>=10 else 0) if mode=='tenvten' else (1 if i in ((1,2,4,5) if mode=='mass' else (1,2)) else 0))
    settings = rules.TGDSpecificTacticalGameRules()
    settings.SetCheckEndGame(False)
    root.SetCampList(camps)
    root.SetGameRules(settings)
    marks=native.world_landmarks()
    deploy=[struct.unpack('<i3fii6f',marks[i:i+48]) for i in range(0,len(marks),48)]
    deploy=[r for r in deploy if r[0]==2]
    by_alliance=dict((r[4],(r[1],r[2])) for r in deploy)
    if raw_mode in ('swapped','transport_swapped','mass_swapped'):
        by_alliance={0:by_alliance[1],1:by_alliance[0]}
    for alliance in (0,1):
        home=by_alliance[alliance];away=by_alliance[1-alliance]
        length=((away[0]-home[0])**2+(away[1]-home[1])**2)**.5
        native.log('FIXTURE_EXPECTED_FRAME '+repr((alliance,home,((away[0]-home[0])/length,(away[1]-home[1])/length))))
    actions=[]
    for camp in (camps[1:] if mode=='tenvten' else [camps[1],camps[2],camps[4],camps[5]] if mode=='mass' else [camps[1],camps[2],camps[4]] if mode=='battle' else camps[1:3]):
        ai=gd.TGDDescriptorIASkirmish()
        ai.SetCamp(camp); ai.SetDifficulty(6)
        actions.append(ai);keep.append(ai)
    def spawn_at(i,camp,x,y,typename,transporter=None):
        if transporter:
            spawn_at(i,camp,x,y,typename)
            spawn_at(i,camp,x+3000,y,transporter)
            return
        unit_type=_ndf.Database.GetObject('$/GFX/Unit/Descriptor_Unit_'+typename)
        pos=tag.TGDTagPosition()
        native.set_probe_position(struct.pack('<Qfff',long(sip.unwrapinstance(pos)),x,y,0.))
        group=var.TGDVariableUnitGroup()
        spawn=gd.TGDDescriptorCreateUnitOnPosition()
        spawn.SetCamp(camp);spawn.SetTypeUnit(unit_type)
        spawn.SetNbUnit(1);spawn.SetPosition(pos)
        spawn.SetGroup(group)
        actions.append(spawn);keep.extend([unit_type,pos,group,spawn])
    if mode=='tenvten':
        for ci,camp in enumerate(camps):
            alliance=1 if ci>=10 else 0
            ax,ay=by_alliance[alliance];bx,by=by_alliance[1-alliance]
            length=((bx-ax)**2+(by-ay)**2)**.5
            fx=(bx-ax)/length;fy=(by-ay)/length
            for k in range(4):
                lateral=((ci%10)-4.5)*140*215+(k%2)*35*215
                x=ax+(bx-ax)*.18-fy*lateral+fx*(k//2)*45*215
                y=ay+(by-ay)*.18+fx*lateral+fy*(k//2)*45*215
                spawn_at(k,camp,x,y,'M113A3_US')
        pause=gd.TGDDescriptorWaitDuration();pause.SetDuration(90.)
    elif mode in ('transport_api','transport'):
        ax,ay=by_alliance[1];bx,by=by_alliance[0]
        for i in range(8):
            spawn_at(i,camps[1+i%2],ax+(bx-ax)*.18+i*15000,ay+(by-ay)*.18,'Rifles_US','M113A3_US')
        for i in range(2):spawn_at(i,camps[0 if i==0 else 3],bx,by+i*5000,'M113A3_US')
        pause=gd.TGDDescriptorWaitDuration();pause.SetDuration(100. if mode=='transport_api' else 240.)
    elif mode in ('long','battle','mass'):
        marks=native.world_landmarks()
        objectives=[struct.unpack('<i3fii6f',marks[i:i+48]) for i in range(0,len(marks),48)]
        objectives=[r for r in objectives if r[0]==1]
        ax,ay=by_alliance[1];bx,by=by_alliance[0]
        length=((bx-ax)**2+(by-ay)**2)**.5;fx=(bx-ax)/length;fy=(by-ay)/length
        objective=min(objectives,key=lambda r:(r[1]-(ax+bx)*.5)**2+(r[2]-(ay+by)*.5)**2)
        cx,cy=objective[1],objective[2]
        native.log('FRONT_FIXTURE '+repr((mode,cx,cy)))
        for i in range(2): spawn_at(i,camps[0 if i==0 else 3],bx,by+i*5000,'M113A3_US')
        owners=[camps[1],camps[2],camps[4],camps[5]] if mode=='mass' else [camps[1],camps[2]]
        for wave in range(4):
            if wave:
                wait=gd.TGDDescriptorWaitDuration();wait.SetDuration(40.);actions.append(wait);keep.append(wait)
            count=(160 if wave==0 else 40) if mode=='mass' else (36 if wave==0 else 16)
            for i in range(count):
                x=cx-fx*(650+wave*90)*215+(i%6)*1500
                y=cy-fy*(650+wave*90)*215+(i//6)*1500
                spawn_at(i,owners[i%len(owners)],x,y,'M113A3_US')
            if mode=='battle':
                for i in range(18 if wave==0 else 8):
                    x=cx+fx*450*215-fy*((i%6)-2.5)*120*215
                    y=cy+fy*450*215+fx*((i%6)-2.5)*120*215
                    spawn_at(i,camps[4],x,y,'M113A3_US')
        pause=gd.TGDDescriptorWaitDuration();pause.SetDuration(120.)
    else:
        for i in range(14):
            ax,ay=by_alliance[1 if i<12 else 0]; bx,by=by_alliance[0 if i<12 else 1]
            x=ax+(bx-ax)*.1+(i%3)*1500.;y=ay+(by-ay)*.1+(i//3)*1500.
            spawn_at(i,camps[1+i%2] if i<12 else camps[0 if i==12 else 3],x,y,'M113A3_US')
        pause=gd.TGDDescriptorWaitDuration();pause.SetDuration(40.)
    effect=gd.TGDDescriptorSequential();effect.SetNbExecutions(1)
    effect.SetSubActions(actions+[pause,gd.TGDDescriptorLoadingDone(),gd.TGDDescriptorWaitForEver()])
    root.SetEffetMap(effect)
    keep.extend([effect,ai,pause])
    root.TransfertAllPythonSaveableToCPP()
    keep.extend([base,root,camps,settings])
    native.log('FIXTURE_CAMPS_PREPARED')

transport_orders={}
transport_pairs={}
def transport_tick(controller,api=True):
    raw=native.world_unit_snapshot()
    rows=[struct.unpack('<QQiii3f',raw[i:i+40]) for i in range(0,len(raw),40)]
    live=dict((r[0],r) for r in rows)
    if not transport_pairs:
        vehicles=[r for r in rows if r[3]==6 and native.unit_role(struct.pack('<Q',r[0]))=='transport']
        passengers=[r for r in rows if r[3]==6 and native.unit_role(struct.pack('<Q',r[0]))=='infantry']
        for r in passengers:
            options=[v for v in vehicles if v[1]==r[1] and v[0] not in transport_pairs.values()]
            if not options:continue
            v=min(options,key=lambda v:(v[5]-r[5])**2+(v[6]-r[6])**2)
            transport_pairs[r[0]]=v[0]
            result=native.fixture_load_transport(struct.pack('<QQ',r[0],v[0]))
            native.log('TRANSPORT_NATIVE_LOAD '+repr((r[0],v[0],struct.unpack('<i',result)[0])))
    for uid,carrier in transport_pairs.items():
        for entity in (uid,carrier):native.lease_ai_unit(struct.pack('<Qi',entity,1))
    pairs=[]
    for row in rows:
        data=native.unit_transporter(struct.pack('<Q',row[0]))
        carrier=struct.unpack('<Q',data)[0] if data else 0
        if carrier in live:
            pairs.append((row[0],carrier))
            for uid in (row[0],carrier):native.lease_ai_unit(struct.pack('<Qi',uid,1))
            if api and carrier not in transport_orders:
                c=live[carrier]
                points=list(controller.map_deploy.values())
                home=min(points,key=lambda p:(p[0]-c[5])**2+(p[1]-c[6])**2)
                away=max(points,key=lambda p:(p[0]-home[0])**2+(p[1]-home[1])**2)
                length=((away[0]-home[0])**2+(away[1]-home[1])**2)**.5
                f=((away[0]-home[0])/length,(away[1]-home[1])/length)
                target=(c[5]+f[0]*500*215,c[6]+f[1]*500*215)
                result=native.unload_at_ai_unit(struct.pack('<Qfff',carrier,target[0],target[1],c[7]))
                transport_orders[carrier]=target
                native.log('TRANSPORT_NATIVE_ORDER '+repr((carrier,target,struct.unpack('<i',result)[0])))
    if controller.tick%10==0:
        native.log('TRANSPORT_NATIVE_STATE '+repr((controller.tick,pairs,[(r[0],r[5],r[6],struct.unpack('<i',native.unit_activity(struct.pack('<Q',r[0])))[0]) for r in rows])))

# Read-only ownership evidence for the explicit twenty-seat headless fixture.
def tenvten_observe(tick):
    if tick % 10:return
    raw=native.world_unit_snapshot()
    rows=[struct.unpack('<QQiii3f',raw[i:i+40]) for i in range(0,len(raw),40)]
    native.log('TENVTEN_ROSTER '+repr((tick,[(r[0],r[1],r[2],r[3],r[5],r[6]) for r in rows])))
