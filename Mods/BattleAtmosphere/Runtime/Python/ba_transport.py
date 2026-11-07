# Python 2.5. Paired ground transport, native delivery, then moving support.
from __future__ import division
import math
import struct
import _ba_native as native

SCALE=215.0
PASSENGERS=frozenset(['infantry','engineer','AT','reco'])
CARRIERS=frozenset(['ifv','transport','appui'])

def status(data):return struct.unpack('<i',data)[0] if data is not None else -1
def distance(a,b):return math.hypot(a[0]-b[0],a[1]-b[1])

class Mechanized(object):
    def __init__(self):
        self.journeys={};self.cooldown={};self.escorts={}
        self.delivered=0;self.emergency=0;self.started=0
    def release(self,carrier,reason,tick):
        journey=self.journeys.pop(carrier,None)
        if journey:
            for uid in [carrier]+journey['passengers']:native.lease_ai_unit(struct.pack('<Qi',uid,0))
            self.cooldown[carrier]=tick+40
            native.log('TRANSPORT_RETURN '+repr((carrier,reason)))
    def delivery_point(self,c,carrier,row,passengers,all_units):
        alliance=row[2];board=c.boards[alliance]
        d,l=c.project(alliance,(row[5],row[6]))
        task=board.tasks.get(carrier,{})
        # Do not count mounted passengers as a stationary front at the spawn.
        local=[u for u in all_units.get(alliance,[]) if not u[4]&7 and abs(u[3]-l)<900]
        contact=sorted(u[2] for u in local if u[4]&40)
        if contact:
            front=contact[len(contact)//2]
        else:
            mid=c.spans[alliance]*.5
            advancing=sorted(u[2] for u in local)
            front=max(board.front,mid*.85,advancing[int((len(advancing)-1)*.7)] if advancing else 0)
        lateral=task.get('lateral',l)
        lateral=max(l-1000,min(l+1000,lateral))
        kind=c.traits[carrier][1]
        best=None
        for behind in (250,400,550):
            depth=front-behind
            if depth<d-80:depth=d
            for offset in (0,-160,160,-320,320,-480,480):
                point=c.unproject(alliance,depth,lateral+offset)
                cell=c.nav.index(*point)
                if not c.nav.valid(kind,cell) or not all(c.nav.valid(c.traits[uid][1],cell) for uid in passengers):continue
                if any(j['alliance']==alliance and other!=carrier and distance(point,j['target'])<160*SCALE for other,j in self.journeys.items()):continue
                if any(math.hypot(depth-u[2],lateral+offset-u[3])<90 for u in local):continue
                score=abs(offset)+abs(behind-250)*.4
                if best is None or score<best[0]:best=(score,point,front,depth)
                if score==0:return best
        return best
    def step(self,c,rows,live,all_units):
        pairs={}
        for row in rows:
            uid=row[0]
            if row[2] not in c.boards:continue
            if not c.activity.get(uid,0)&1:continue
            traits=c.traits.get(uid)
            if traits is None or traits[0] not in PASSENGERS:continue
            data=native.unit_transporter(struct.pack('<Q',uid))
            carrier=struct.unpack('<Q',data)[0] if data else 0
            car=live.get(carrier);ct=c.traits.get(carrier)
            if car is None or ct is None or ct[0] not in CARRIERS:continue
            if car[1]!=row[1] or car[2]!=row[2] or not 1<=car[3]<=6:continue
            pairs.setdefault(carrier,[]).append(uid)
        for carrier in list(self.journeys):
            j=self.journeys[carrier];row=live.get(carrier)
            if row is None or row[1]!=j['owner'] or not 1<=row[3]<=6:
                self.release(carrier,'identity',c.tick);continue
            flags=c.activity.get(carrier,-1)
            if flags<0 or flags&5:
                self.release(carrier,'rout_or_unknown',c.tick);continue
            if not flags&2:
                survivors=[uid for uid in j['passengers'] if uid in live and live[uid][1]==j['owner'] and c.activity.get(uid,-1)>=0 and not c.activity[uid]&1]
                gap=distance((row[5],row[6]),j['target'])/SCALE
                if survivors:
                    self.delivered+=1
                    native.log('TRANSPORT_DELIVERED '+repr((carrier,survivors,round(gap,1),j['phase'],c.tick-j['start'])))
                else:native.log('TRANSPORT_PASSENGERS_LOST '+repr((carrier,j['passengers'])))
                self.release(carrier,'unloaded' if survivors else 'passengers_lost',c.tick)
                if survivors:self.escorts[carrier]={'passengers':survivors,'owner':row[1],'expires':c.tick+240}
                continue
            for uid in [carrier]+j['passengers']:native.lease_ai_unit(struct.pack('<Qi',uid,1))
            pos=(row[5],row[6]);remaining=distance(pos,j['target'])
            if remaining<j['best']-8*SCALE:j['best']=remaining;j['progress']=c.tick
            # A native route can initially head away from the destination to
            # reach a bridge. Motion is progress too; straight-line distance
            # alone falsely unloads working transports during such detours.
            if distance(pos,j['motion'])>=8*SCALE:
                j['motion']=pos;j['last_motion']=c.tick
            idle=c.tick-max(j['progress'],j['last_motion'])
            expired=c.tick>=j['deadline']
            if c.tick-j['progress']>=80 and idle<80 and not j.get('detour_logged'):
                j['detour_logged']=True
                native.log('TRANSPORT_DETOUR_PROGRESS '+repr((carrier,c.tick-j['start'],round(remaining/SCALE,1))))
            emergency=bool(flags&40) or idle>=80 or expired
            if emergency and c.tick-j['last_order']>=16:
                result=status(native.unload_now_ai_unit(struct.pack('<Qfff',carrier,row[5],row[6],row[7])))
                j['last_order']=c.tick;j['phase']='emergency';self.emergency+=1
                reason='contact' if flags&40 else 'delivery_deadline' if expired else 'no_progress'
                native.log('TRANSPORT_EMERGENCY '+repr((carrier,reason,result)))
                if idle>=120 or c.tick>=j['deadline']+40:self.release(carrier,'delivery_failed',c.tick)
            elif remaining<300*SCALE and c.tick-j['last_order']>=30 and j.get('retargets',0)<3:
                # Recheck a moving front near arrival; never chase it indefinitely.
                passengers=[uid for uid in j['passengers'] if uid in live and c.traits.get(uid)]
                choice=self.delivery_point(c,carrier,row,passengers,all_units) if passengers else None
                if choice and choice[2]>j['front']+350 and choice[3]>c.project(row[2],pos)[0]+200:
                    unused,target,front,depth=choice
                    result=status(native.unload_at_ai_unit(struct.pack('<Qfff',carrier,target[0],target[1],row[7])))
                    if result==1:
                        j['target']=target;j['front']=front;j['last_order']=c.tick
                        j['best']=distance(pos,target);j['progress']=c.tick
                        j['retargets']=j.get('retargets',0)+1
                        native.log('TRANSPORT_RETARGET '+repr((carrier,front,depth,target)))
        begun=0
        for carrier,passengers in sorted(pairs.items()):
            if carrier in self.journeys or self.cooldown.get(carrier,0)>c.tick:continue
            flags=c.activity.get(carrier,-1)
            if flags<0 or flags&45 or not flags&2:continue
            if begun>=4 or c.nav.checks>=80:break
            row=live[carrier];choice=self.delivery_point(c,carrier,row,passengers,all_units)
            if choice is None:continue
            unused,target,front,depth=choice
            for uid in [carrier]+passengers:
                if uid in c.claims:c.release(uid,'mechanized_transfer')
                native.lease_ai_unit(struct.pack('<Qi',uid,1))
            result=status(native.unload_at_ai_unit(struct.pack('<Qfff',carrier,target[0],target[1],row[7])))
            if result!=1:
                for uid in [carrier]+passengers:native.lease_ai_unit(struct.pack('<Qi',uid,0))
                self.cooldown[carrier]=c.tick+20;continue
            self.journeys[carrier]={'owner':row[1],'alliance':row[2],'passengers':passengers,
                'target':target,'front':front,'phase':'delivery','start':c.tick,'last_order':c.tick,
                'progress':c.tick,'best':distance((row[5],row[6]),target),
                'motion':(row[5],row[6]),'last_motion':c.tick,
                'deadline':c.tick+max(360,min(1200,int(distance((row[5],row[6]),target)/SCALE/8.0*2.0+120)))}
            begun+=1;self.started+=1
            native.log('TRANSPORT_ROUTE '+repr((carrier,passengers,round(front,1),round(depth,1),target)))
        for carrier in list(self.escorts):
            e=self.escorts[carrier]
            if carrier not in live or live[carrier][1]!=e['owner'] or c.tick>=e['expires'] or not any(uid in live for uid in e['passengers']):del self.escorts[carrier]
        for carrier in list(self.cooldown):
            if carrier not in live or c.tick>=self.cooldown[carrier]:del self.cooldown[carrier]
    def escort_goal(self,c,row,goal,live):
        escort=self.escorts.get(row[0])
        if escort is None or goal is None:return goal
        friends=[live[uid] for uid in escort['passengers'] if uid in live and live[uid][1]==row[1]]
        if not friends:return goal
        depths=[c.project(row[2],(r[5],r[6]))[0] for r in friends]
        d,l=c.project(row[2],(row[5],row[6]));front=max(depths)
        # A short forward leg, never a timed hold or a backwards regroup order.
        gain=max(85,min(goal[0]-d,front+120-d))
        spread=max(-gain/.35,min(gain/.35,goal[1]-l))
        return d+gain,l+spread,goal[2]
