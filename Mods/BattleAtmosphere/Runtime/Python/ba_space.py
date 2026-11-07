# Python 2.5. Map-independent, bounded spatial corrections alongside native AI.
from __future__ import division
import struct
import math
import time
from heapq import heappop, heappush
import _ba_native as native
from ba_front import FrontBoard, CORE_RADIUS, CORE_CAPACITY
from ba_transport import Mechanized
from ba_tactics import Momentum

SCALE = 215.0
SPACING = 120.0
ROLES = frozenset(['armor','infantry','engineer','AT','ifv','transport','appui','reco'])
LANE = 300.0

def distance(a,b):
    return math.hypot(a[0]-b[0],a[1]-b[1])

def status(value):
    return struct.unpack('<i',value)[0] if value is not None else -1

class Navigation(object):
    def __init__(self,data):
        self.w,self.h,self.cell,self.ox,self.oy,self.count = struct.unpack('<IIfffI',data[:24])
        self.masks = [data[24+k*self.count:24+(k+1)*self.count] for k in range(4)]
        self.cache = {}
        self.checks = 0
    def index(self,x,y):
        a=int(math.floor((x-self.ox)/self.cell)); b=int(math.floor((y-self.oy)/self.cell))
        return b*self.w+a if 0<=a<self.w and 0<=b<self.h else -1
    def position(self,i):
        return ((i%self.w+.5)*self.cell+self.ox,(i//self.w+.5)*self.cell+self.oy)
    def valid(self,kind,i):
        if not 0<=i<self.count or not 0<=kind<4: return False
        key=(kind,i)
        if key not in self.cache:
            if self.checks>=240: return False
            self.checks+=1
            x,y=self.position(i)
            self.cache[key] = ord(self.masks[kind][i])!=0 and status(native.nav_point(struct.pack('<Iff',kind,x,y)))==1
        return self.cache[key]
    def neighbours(self,i):
        x=i%self.w; y=i//self.w
        result=[]
        if x>0: result.append(i-1)
        if x+1<self.w: result.append(i+1)
        if y>0: result.append(i-self.w)
        if y+1<self.h: result.append(i+self.w)
        return result
    def routes(self,kind,origin,max_steps=13):
        # Conservative four-neighbour coarse route. Endpoints are checked by
        # native tactical navigation; actual movement still needs feedback.
        start=self.index(origin[0],origin[1])
        if start<0 or not self.valid(kind,start): return {}
        costs={start:0}; queue=[start]; cursor=0
        while cursor<len(queue):
            here=queue[cursor]; cursor+=1
            if costs[here]>=max_steps: continue
            for other in self.neighbours(here):
                if other not in costs and self.valid(kind,other):
                    costs[other]=costs[here]+1; queue.append(other)
        return costs

    def direct_path(self,kind,origin,goal,forward):
        # Validate the complete shallow forward ray, not just its endpoint.
        # This avoids forcing a 45-degree grid staircase on wide wing routes.
        if sum((goal[k]-origin[k])*forward[k] for k in range(2))<=1e-3:return []
        steps=max(1,int(math.ceil(distance(origin,goal)/(self.cell*.4))))
        previous=self.index(*origin)
        if not self.valid(kind,previous):return []
        for k in range(1,steps+1):
            p=(origin[0]+(goal[0]-origin[0])*k/steps,origin[1]+(goal[1]-origin[1])*k/steps)
            cell=self.index(*p)
            if not self.valid(kind,cell):return []
            if cell%self.w!=previous%self.w and cell//self.w!=previous//self.w:
                if not self.valid(kind,(previous//self.w)*self.w+cell%self.w) or not self.valid(kind,(cell//self.w)*self.w+previous%self.w):return []
            previous=cell
        count=max(1,int(math.ceil(distance(origin,goal)/(150*SCALE))))
        return [(origin[0]+(goal[0]-origin[0])*k/count,origin[1]+(goal[1]-origin[1])*k/count) for k in range(1,count+1)]

    def forward_paths(self,kind,origin,forward,side=0,max_steps=10):
        # Directed eight-neighbour graph. Expansion can go diagonally outward,
        # but never backwards or inward across the assigned wing.
        start=self.index(origin[0],origin[1])
        if start<0 or not self.valid(kind,start): return {},{}
        lateral=(-forward[1],forward[0]); costs={start:0}; parents={start:None}
        queue=[start]; cursor=0
        while cursor<len(queue):
            here=queue[cursor]; cursor+=1
            if costs[here]>=max_steps: continue
            hx=here%self.w; hy=here//self.w
            for dy in (-1,0,1):
                for dx in (-1,0,1):
                    if not (dx or dy) or not 0<=hx+dx<self.w or not 0<=hy+dy<self.h: continue
                    advance=dx*forward[0]+dy*forward[1]
                    across=dx*lateral[0]+dy*lateral[1]
                    if advance < -1e-6 or (side and side*across < -1e-6): continue
                    other=(hy+dy)*self.w+hx+dx
                    if other in costs or not self.valid(kind,other): continue
                    if dx and dy and (not self.valid(kind,hy*self.w+hx+dx) or not self.valid(kind,(hy+dy)*self.w+hx)): continue
                    costs[other]=costs[here]+1; parents[other]=here; queue.append(other)
        return costs,parents

    def waypoints(self,kind,reachable,index,origin,forward,side):
        # Find a route towards THIS endpoint, not the arbitrary predecessor
        # of the reachability flood. Otherwise every unit shares its first turn.
        start=self.index(*origin); goal=self.position(index)
        lateral=(-forward[1],forward[0]); parents={start:None}; costs={start:0}
        queue=[(distance(origin,goal),start)]
        while queue:
            unused,here=heappop(queue)
            if here==index: break
            a=origin if here==start else self.position(here)
            hx=here%self.w; hy=here//self.w
            for dy in (-1,0,1):
                for dx in (-1,0,1):
                    if not (dx or dy) or not 0<=hx+dx<self.w or not 0<=hy+dy<self.h: continue
                    other=(hy+dy)*self.w+hx+dx
                    if other not in reachable: continue
                    b=self.position(other); vx=b[0]-a[0]; vy=b[1]-a[1]
                    if vx*forward[0]+vy*forward[1]<-1e-3: continue
                    if side and side*(vx*lateral[0]+vy*lateral[1]) < -1e-3: continue
                    if dx and dy and (not self.cache.get((kind,hy*self.w+hx+dx)) or not self.cache.get((kind,(hy+dy)*self.w+hx))): continue
                    # Penalise deviation from the origin-to-goal corridor.
                    deviation=abs((b[0]-origin[0])*(goal[1]-origin[1])-(b[1]-origin[1])*(goal[0]-origin[0]))/max(1,distance(origin,goal))
                    cost=costs[here]+distance(a,b)+deviation*.2
                    if cost<costs.get(other,float('inf')):
                        costs[other]=cost; parents[other]=here
                        heappush(queue,(cost+distance(b,goal),other))
        if index not in parents: return []
        path=[]; node=index
        while node!=start:
            path.append(self.position(node)); node=parents[node]
        path.reverse()
        def clear(a,b):
            steps=max(1,int(math.ceil(distance(a,b)/(self.cell*.25))))
            previous=self.index(*a)
            for step in range(1,steps+1):
                k=step/steps; current=self.index(a[0]+(b[0]-a[0])*k,a[1]+(b[1]-a[1])*k)
                if not self.cache.get((kind,current)): return False
                if current%self.w!=previous%self.w and current//self.w!=previous//self.w:
                    if not self.cache.get((kind,(previous//self.w)*self.w+current%self.w)) or not self.cache.get((kind,(current//self.w)*self.w+previous%self.w)): return False
                previous=current
            return True
        # Smooth only across verified grid cells, then bound each segment.
        points=[]; a=origin; cursor=0
        while cursor<len(path):
            end=cursor
            for candidate in range(len(path)-1,cursor,-1):
                if clear(a,path[candidate]): end=candidate; break
            b=path[end]; count=max(1,int(math.ceil(distance(a,b)/(150*SCALE))))
            points.extend((a[0]+(b[0]-a[0])*k/count,a[1]+(b[1]-a[1])*k/count) for k in range(1,count+1))
            a=b; cursor=end+1
        previous=origin
        for point in points:
            if (point[0]-previous[0])*forward[0]+(point[1]-previous[1])*forward[1]<=1e-3: return []
            previous=point
        return points

class Controller(object):
    def __init__(self):
        self.fixture=bool(native.fixture_mode())
        self.tick=0; self.nav=None; self.traits={}; self.claims={}; self.cooldown={}
        self.intents={}; self.boards={}; self.blocked={}; self.activity={}; self.attempts={}
        self.issued=0; self.returned=0; self.failed=0; self.observed={}
        self.transport=Mechanized();self.births={};self.force_roles={}
        self.tactics=Momentum()
        raw=native.world_landmarks()
        rows=[struct.unpack('<i3fii6f',raw[i:i+48]) for i in range(0,len(raw),48)]
        self.objectives=[(r[1],r[2]) for r in rows if r[0]==1]
        self.map_deploy={}
        for row in rows:
            if row[0]==2: self.map_deploy.setdefault(row[4],[]).append((row[1],row[2]))
        for key in self.map_deploy:
            points=self.map_deploy[key]
            self.map_deploy[key]=(sum(p[0] for p in points)/len(points),sum(p[1] for p in points)/len(points))
        self.deploy={};self.frames={};self.spans={};self.spawn_votes={};self.spawn_seen=set()
        self.spawn_since={};self.side_assignment={}
        native.log('SPACE_REVISION combined-front-preview.6')
    def orient(self,rows):
        # Map-side labels are NOT runtime player alliances: lobby side swaps
        # can put alliance 0 in map deployment 1. Establish the physical home
        # from the first ground units, before taking any movement/transport lease.
        # Ambiguous central spawns remain with native AI; never guess by label.
        keys=sorted(self.map_deploy)
        if len(keys)!=2:return
        a,b=[self.map_deploy[k] for k in keys]
        vx=b[0]-a[0];vy=b[1]-a[1];length=math.hypot(vx,vy)
        if length<100*SCALE:return
        for row in rows:
            uid=row[0];alliance=row[2]
            if alliance in self.frames or uid in self.spawn_seen:continue
            self.spawn_seen.add(uid)
            # Passengers can have stale spatial data inside their carrier.
            if self.activity.get(uid,-1)<0 or self.activity[uid]&1:continue
            ratio=((row[5]-a[0])*vx+(row[6]-a[1])*vy)/(length*length)
            if not -.3<=ratio<=1.3 or .47<ratio<.53:continue
            side=keys[0 if ratio<=.47 else 1]
            votes=self.spawn_votes.setdefault(alliance,[])
            if len(votes)<128:votes.append((side,row[1],row[5],row[6],ratio))
            self.spawn_since.setdefault(alliance,self.tick)
        for alliance,votes in sorted(self.spawn_votes.items()):
            if alliance in self.frames or not votes:continue
            counts=dict((k,len([v for v in votes if v[0]==k])) for k in keys)
            side=max(keys,key=lambda k:counts[k]);n=counts[side]
            if n/len(votes)<.8:continue
            if n<3 and self.tick-self.spawn_since[alliance]<2:continue
            if side in self.side_assignment.values():continue
            home=self.map_deploy[side];away=self.map_deploy[keys[1] if side==keys[0] else keys[0]]
            self.frames[alliance]=(home,((away[0]-home[0])/length,(away[1]-home[1])/length))
            self.spans[alliance]=length/SCALE;self.deploy[alliance]=home
            self.side_assignment[alliance]=side
            self.boards[alliance]=FrontBoard([self.project(alliance,p) for p in self.objectives])
            native.log('SPACE_ORIENTATION '+repr((alliance,side,counts,len(votes),self.tick,votes[:4])))
            native.log('SPACE_FRAME '+repr((alliance,self.frames[alliance][0],self.frames[alliance][1])))
    def axis(self,alliance):
        return self.frames.get(alliance)
    def project(self,alliance,p):
        home,f=self.axis(alliance); x=(p[0]-home[0])/SCALE; y=(p[1]-home[1])/SCALE
        return x*f[0]+y*f[1],-x*f[1]+y*f[0]
    def unproject(self,alliance,d,l):
        home,f=self.axis(alliance)
        return home[0]+SCALE*(d*f[0]-l*f[1]),home[1]+SCALE*(d*f[1]+l*f[0])
    def release(self,uid,reason):
        native.lease_ai_unit(struct.pack('<Qi',uid,0))
        claim=self.claims.pop(uid,None)
        if claim and reason in ('no_progress','deadline','route_backtrack'):
            self.blocked[(uid,claim['cell'])]=self.tick+120
        self.cooldown[uid]=self.tick+16
        self.returned+=1
        if reason in ('no_progress','route_backtrack'):self.tactics.failed(uid,self.tick)
        native.log('SPACE_RETURN '+repr((uid,reason)))
    def issue(self,uid,row,point):
        result=status(native.attack_move_ai_unit(struct.pack('<Qfff',uid,point[0],point[1],row[7])))
        if result!=1: self.failed+=1
        return result
    def step(self):
        started=time.clock(); self.tick+=1
        raw=native.world_unit_snapshot()
        rows=[struct.unpack('<QQiii3f',raw[i:i+40]) for i in range(0,len(raw),40)]
        live=dict((r[0],r) for r in rows)
        if self.nav is None:
            data=native.world_navigation()
            if data: self.nav=Navigation(data)
            else: return
        self.nav.checks=0; self.activity={}; refresh=0; all_units={};ground=[]
        for row in rows:
            uid=row[0]
            if uid not in self.traits:
                if refresh>=64: continue
                refresh+=1; packed=struct.pack('<Q',uid); data=native.unit_traits(packed)
                if data is None: self.traits[uid]=None; continue
                role=native.unit_role(packed); values=struct.unpack('<IIfI',data)
                self.force_roles[uid]=role
                if 1<=row[3]<=6:
                    key=(row[1],role);self.births[key]=self.births.get(key,0)+1
                self.traits[uid]=(role,values[1],values[2]) if values[3] and values[1]<4 else None
            traits=self.traits[uid]
            if not 0<=row[3]<=6 or traits is None or traits[0] not in ROLES: continue
            flag=status(native.unit_activity(struct.pack('<Q',uid))); self.activity[uid]=flag
            ground.append(row)
        self.orient(ground)
        for row in ground:
            uid=row[0];flag=self.activity[uid]
            if not 1<=row[3]<=6 or row[2] not in self.boards:continue
            d,l=self.project(row[2],(row[5],row[6]))
            all_units.setdefault(row[2],[]).append((uid,row[1],d,l,flag))
        # Preserve the accepted front-board cadence. Resolving orientation
        # mid-cycle must not prematurely fan loaded carriers across lanes.
        if self.tick==1 or self.tick%10==0:
            for alliance,board in self.boards.items():
                units=all_units.get(alliance,[])
                depths=sorted(r[2] for r in units)
                reference=board.front if board.front else (depths[len(depths)//2] if depths else 0)
                kinds=set(self.traits[r[0]][1] for r in units)
                def corridor_ok(lateral):
                    # Coarse geometry screens impossible lanes; every route is
                    # still validated by native tactical navigation before issue.
                    for offset in (-250,0,250,500):
                        point=self.unproject(alliance,reference+offset,lateral)
                        cell=self.nav.index(*point)
                        if cell>=0 and any(ord(self.nav.masks[k][cell])!=0 for k in kinds):return True
                    return False
                board.update(units,self.tick,corridor_ok)
            self.intents={}
            for board in self.boards.values(): self.intents.update(board.tasks)
            self.tactics.update(self,all_units)
        self.transport.step(self,rows,live,all_units)
        for uid in list(self.claims):
            claim=self.claims[uid]; row=live.get(uid); flag=self.activity.get(uid,-1)
            if row is None or row[1]!=claim['owner'] or row[2]!=claim['alliance'] or not 1<=row[3]<=6:
                self.release(uid,'identity_changed'); continue
            if flag<0 or flag&23:
                self.release(uid,'native_activity'); continue
            if status(native.lease_ai_unit(struct.pack('<Qi',uid,1)))!=1:
                self.release(uid,'lease_rejected'); continue
            if flag&40:
                # Keep the spatial task while native tactical combat proceeds.
                claim['last_progress']=self.tick
                continue
            if claim['mode']!='transit': continue
            pos=(row[5],row[6]); waypoint=claim['path'][claim['cursor']]
            if distance(pos,waypoint)<35*SCALE:
                claim['cursor']+=1
                if claim['cursor']>=len(claim['path']):
                    claim['mode']='ready'; claim['ready']=self.tick
                    task=self.intents.get(uid)
                    if task: task['legs']+=1
                    native.log('FRONT_ARRIVAL '+repr((uid,self.tick,task['legs'] if task else 0)))
                    continue
                waypoint=claim['path'][claim['cursor']]
                if self.issue(uid,row,waypoint)!=1:
                    self.release(uid,'order_rejected'); continue
                claim['best_distance']=distance(pos,waypoint); claim['last_progress']=self.tick
                native.log('SPACE_WAYPOINT '+repr((uid,claim['cursor'],len(claim['path']),1)))
            f=claim['forward']; origin=claim['origin']
            if ((pos[0]-origin[0])*f[0]+(pos[1]-origin[1])*f[1]) < -70*SCALE:
                self.release(uid,'route_backtrack'); continue
            remaining=distance(pos,waypoint)
            if remaining<claim['best_distance']-8*SCALE:
                claim['best_distance']=remaining; claim['progress']=pos; claim['last_progress']=self.tick
            elif self.tick-claim['last_progress']>=80:
                self.release(uid,'no_progress'); continue
        eligible=[]
        for row in rows:
            uid=row[0]; claim=self.claims.get(uid)
            if uid not in self.intents or self.activity.get(uid,-1)!=0 or self.cooldown.get(uid,0)>self.tick: continue
            if claim and claim['mode']=='transit': continue
            eligible.append(row)
        self.plan(eligible,rows)
        if self.tick==1 or self.tick%(10 if self.fixture else 60)==0:
            native.log('SPACE_STATUS '+repr((self.tick,len(rows),len(eligible),len(self.claims),self.issued,self.returned,round((time.clock()-started)*1000,3))))
            native.log('FRONT_STATUS '+repr((self.tick,[(a,len(b.tasks),len(b.lanes),round(b.front,1),b.loads) for a,b in sorted(self.boards.items())])))
            native.log('FRONT_METRICS '+repr((self.tick,[(a,self.metrics(a,u)) for a,u in sorted(all_units.items())])))
            native.log('TRANSPORT_STATUS '+repr((self.tick,len(self.transport.journeys),len(self.transport.escorts),self.transport.started,self.transport.delivered,self.transport.emergency)))
            native.log('TACTIC_STATUS '+repr((self.tick,self.tactics.counts)))
            mix={}
            for r in rows:
                if 1<=r[3]<=6 and r[0] in self.force_roles:
                    key=(r[1],self.force_roles[r[0]]);mix[key]=mix.get(key,0)+1
            native.log('FORCE_MIX '+repr((self.tick,mix,self.births)))
            if self.fixture:
                native.log('SPACE_POSITIONS '+repr([(r[0],r[2],r[3],r[5],r[6]) for r in rows]))
                native.log('FRONT_ACTIVITY '+repr(sorted(self.activity.items())))
        if self.tick%120==0:
            for mapping in (self.traits,self.cooldown,self.attempts,self.observed,self.force_roles):
                for uid in list(mapping):
                    if uid not in live: del mapping[uid]
            for key in list(self.blocked):
                if key[0] not in live or self.blocked[key]<=self.tick: del self.blocked[key]
    def metrics(self,alliance,units):
        if not units:return {}
        board=self.boards[alliance];ls=sorted(r[3] for r in units);buckets={};idle=0
        for r in units:
            uid,owner,d,l,flag=r;key=(int(math.floor(d/200)),int(math.floor(l/200)))
            buckets.setdefault(key,[]).append(r)
            old=self.observed.get(uid)
            if old is None or math.hypot(d-old[0],l-old[1])>25:
                self.observed[uid]=(d,l,self.tick)
            elif flag==0 and d<board.front-900 and self.tick-old[2]>=60:idle+=1
        largest=0
        for r in units:
            x=int(math.floor(r[2]/200));y=int(math.floor(r[3]/200));near=0
            for dx in (-1,0,1):
                for dy in (-1,0,1):
                    near+=sum(math.hypot(q[2]-r[2],q[3]-r[3])<200 for q in buckets.get((x+dx,y+dy),()))
            largest=max(largest,near)
        cores=[sum(math.hypot(r[2]-p[0],r[3]-p[1])<CORE_RADIUS for r in units) for p in board.objectives]
        band=set(int(math.floor(r[3]/260)) for r in units if board.front-800<r[2]<board.front+1000)
        ordered=sorted(band);gaps=[b-a-1 for a,b in zip(ordered,ordered[1:])]
        return {'width80_m':round(ls[int(len(ls)*.9)]-ls[int(len(ls)*.1)],1),
                'largest_200m_cluster':largest,'objective_core_peak':max(cores) if cores else 0,
                'front_band_lanes':len(band),'empty_internal_lanes':max(gaps) if gaps else 0,
                'rear_idle_30s':idle,'in_combat':sum(bool(r[4]&32) for r in units)}
    def plan(self,eligible,rows):
        if not eligible: return
        live=dict((r[0],r) for r in rows)
        # Age fairness: a dense front cannot starve other owners or rear arrivals.
        eligible.sort(key=lambda r:(self.attempts.get(r[0],-10000),r[0]))
        buckets={}; width=SPACING*SCALE; core_load={}
        def add(alliance,uid,p):
            key=(alliance,int(math.floor(p[0]/width)),int(math.floor(p[1]/width)))
            buckets.setdefault(key,[]).append((uid,p))
            for index,point in enumerate(self.objectives):
                if distance(p,point)<CORE_RADIUS*SCALE:
                    core_load.setdefault((alliance,index),set()).add(uid)
        for row in rows:
            if self.traits.get(row[0]) is not None: add(row[2],row[0],(row[5],row[6]))
        for uid,c in self.claims.items():
            if c['mode']=='transit': add(c['alliance'],uid,c['target'])
        for uid,j in self.transport.journeys.items():
            add(j['alliance'],uid,j['target'])
        def free(alliance,uid,p):
            gx=int(math.floor(p[0]/width));gy=int(math.floor(p[1]/width))
            for dx in (-1,0,1):
                for dy in (-1,0,1):
                    for other,q in buckets.get((alliance,gx+dx,gy+dy),()):
                        if other!=uid and distance(p,q)<width: return False
            for index,point in enumerate(self.objectives):
                occupied=core_load.get((alliance,index),set())
                if distance(p,point)<CORE_RADIUS*SCALE and len(occupied-set([uid]))>=CORE_CAPACITY: return False
            return True
        attempted=0; issued=0
        for row in eligible:
            if attempted>=16 or self.nav.checks>=240: break
            uid=row[0]; alliance=row[2]; board=self.boards[alliance]; task=board.tasks.get(uid)
            if task is None: continue
            if self.tick-self.attempts.get(uid,-10000)<4: continue
            attempted+=1; self.attempts[uid]=self.tick
            pos=(row[5],row[6]); d,l=self.project(alliance,pos); goal=board.goal((uid,row[1],d,l,0))
            goal=self.tactics.goal(self,row,goal)
            goal=self.transport.escort_goal(self,row,goal,live)
            claim=self.claims.get(uid)
            if goal is None:
                if claim: claim['mode']='hold'
                continue
            gd,gl,phase=goal; f=self.axis(alliance)[1]; across=(-f[1],f[0])
            side=(-1 if gl<l else 1) if phase=='expand' else 0
            kind=self.traits[uid][1]
            choice=None; direct=[]
            for dd in (0,144,-144,288,-288,432):
                for dl in (0,144,-144,288,-288):
                    nd=gd+dd;nl=gl+dl;gain=nd-d;spread=nl-l
                    if not max(65,abs(spread)*.35)<=gain<=1000 or nd>board.front+1000:continue
                    if phase=='expand' and side*spread<40:continue
                    point=self.unproject(alliance,nd,nl);cell=self.nav.index(*point)
                    if self.blocked.get((uid,cell),0)>self.tick or not free(alliance,uid,point):continue
                    direct.append((abs(dd)+abs(dl)*2.5,cell,point,nd,nl))
            direct.sort()
            for cost,cell,point,nd,nl in direct:
                path=self.nav.direct_path(kind,pos,point,f)
                if path:choice=(cell,point,nd,nl,path);break
                if self.nav.checks>=240:break
            if choice is None and self.nav.checks<240:
                reachable,unused=self.nav.forward_paths(kind,pos,f,side,max_steps=16)
                options=[]
                for cell in reachable:
                    if self.blocked.get((uid,cell),0)>self.tick: continue
                    point=self.nav.position(cell); nd,nl=self.project(alliance,point)
                    gain=nd-d; spread=nl-l
                    if not max(65,abs(spread)*.35)<=gain<=800: continue
                    if nd>board.front+1000: continue
                    if phase=='expand' and side*spread<40: continue
                    cost=abs(nd-gd)+2.5*abs(nl-gl)
                    options.append((cost,cell,point,nd,nl))
                options.sort()
                for cost,cell,point,nd,nl in options:
                    if not free(alliance,uid,point): continue
                    path=self.nav.waypoints(kind,reachable,cell,pos,f,side)
                    if not path: continue
                    choice=(cell,point,nd,nl,path);break
            if choice is None:
                if claim and self.tick-claim.get('ready',self.tick)>40: self.release(uid,'no_next_route')
                continue
            cell,point,nd,nl,path=choice
            if status(native.lease_ai_unit(struct.pack('<Qi',uid,1)))!=1: continue
            accepted=self.issue(uid,row,path[0])
            if accepted!=1:
                self.release(uid,'order_rejected'); continue
            self.claims[uid]={'owner':row[1],'alliance':alliance,'target':point,'progress':pos,
                             'last_progress':self.tick,'best_distance':distance(pos,path[0]),'cell':cell,
                             'path':path,'cursor':0,'forward':f,'origin':pos,'mode':'transit','ready':self.tick}
            add(alliance,uid,point); self.issued+=1; issued+=1
            native.log('SPACE_ROUTE '+repr((uid,phase,task['side'],task['lane'],len(path),d,nd,l,nl)))
            native.log('SPACE_ORDER '+repr((uid,path[0][0],path[0][1],accepted)))
        if issued: native.log('SPACE_PLAN '+repr((self.tick,issued,{})))
