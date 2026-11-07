# Python 2.5. Persistent alliance-wide frontage, independent of engine APIs.
from __future__ import division
import math

LANE = 260.0
CORE_RADIUS = 260.0
CORE_CAPACITY = 4

class FrontBoard(object):
    def __init__(self, objectives):
        self.objectives=objectives
        self.tasks={}; self.lanes=[]; self.centre=None; self.front=0.0
        self.core={}; self.loads={}; self.generation=0
    def update(self, rows, tick, corridor_ok=None):
        # rows: id, owner, depth(m), lateral(m), activity.
        if not rows: self.tasks={}; return
        live=dict((r[0],r) for r in rows)
        for uid in list(self.tasks):
            if uid not in live or self.tasks[uid]['owner']!=live[uid][1]: del self.tasks[uid]
        lateral=sorted(r[3] for r in rows)
        if self.centre is None:
            centre=lateral[len(lateral)//2]
            if self.objectives:
                public=sorted(p[1] for p in self.objectives)
                centre=max(centre-300,min(centre+300,public[len(public)//2]))
            self.centre=round(centre/LANE)*LANE
        wanted=min(25,max(3,int(math.ceil(len(rows)/3.0))))
        if wanted%2==0: wanted+=1
        proposed=list(range(-(wanted//2),wanted//2+1))
        if corridor_ok is not None:
            proposed=[k for k in proposed if corridor_ok(self.centre+k*LANE)]
        if not proposed: proposed=[0]
        geometry_changed=corridor_ok is not None and any(not corridor_ok(self.centre+k*LANE) for k in self.lanes)
        # Hysteresis for losses; immediately respect narrower navigable terrain.
        if not self.lanes or len(proposed)>len(self.lanes) or wanted<len(self.lanes)*.5 or geometry_changed:
            self.lanes=proposed; self.generation+=1
            ranked=sorted(rows,key=lambda r:(r[3],r[0]))
            for rank,r in enumerate(ranked):
                lane=self.lanes[min(len(self.lanes)-1,int(rank*len(self.lanes)/len(ranked)))]
                self.tasks[r[0]]={'owner':r[1],'lane':lane,'assigned':tick,'legs':self.tasks.get(r[0],{}).get('legs',0)}
        loads=dict((lane,0) for lane in self.lanes)
        for task in self.tasks.values(): loads[task['lane']]=loads.get(task['lane'],0)+1
        for row in sorted(rows,key=lambda r:(r[3],r[0])):
            if row[0] in self.tasks: continue
            lane=min(self.lanes,key=lambda k:(loads[k],abs(self.centre+k*LANE-row[3]),k))
            self.tasks[row[0]]={'owner':row[1],'lane':lane,'assigned':tick,'legs':0}; loads[lane]+=1
        # Retain capture-contact assignments until death or leaving the point.
        # Occupancy status is not known: apply the cap to every public objective.
        self.core={}
        for index,p in enumerate(self.objectives):
            near=[r for r in rows if abs(r[2]-p[0])<650 and abs(r[3]-p[1])<650]
            near.sort(key=lambda r:(self.tasks[r[0]].get('core')!=index,
                       abs(self.centre+self.tasks[r[0]]['lane']*LANE-p[1]),abs(r[2]-p[0]),r[0]))
            self.core[index]=set(r[0] for r in near[:CORE_CAPACITY])
        for r in rows:
            task=self.tasks[r[0]]; task['core']=None
            goal=self.centre+task['lane']*LANE
            for index,p in enumerate(self.objectives):
                if r[0] in self.core[index]: task['core']=index
                elif -550< p[0]-r[2] <700 and abs(goal-p[1])<CORE_RADIUS+70:
                    # Overflow goes forward onto shoulders, never circles back.
                    side=-1 if r[3]<p[1] or (r[3]==p[1] and r[0]%2==0) else 1
                    goal=p[1]+side*(CORE_RADIUS+160+abs(task['lane'])*35)
            task['lateral']=goal
            task['side']=-1 if goal<self.centre-LANE*.6 else 1 if goal>self.centre+LANE*.6 else 0
        # A robust actual front, not a clock advancing through resistance.
        actual_lanes={}
        for r in rows:
            if not r[4]&7:
                lane=int(round((r[3]-self.centre)/LANE))
                actual_lanes.setdefault(lane,[]).append(r[2])
        lane_fronts=[]
        for values in actual_lanes.values():
            values.sort();lane_fronts.append(values[int((len(values)-1)*.7)])
        lane_fronts.sort()
        if lane_fronts: self.front=lane_fronts[int((len(lane_fronts)-1)*.6)]
        self.loads=loads
    def goal(self,row):
        task=self.tasks[row[0]]; d=row[2]; lateral=row[3]
        spread=max(-1800,min(1800,task['lateral']-lateral))
        gain=max(200,abs(spread)*.4)
        # Bounded lead. Front stalls under resistance; reinforcements catch up.
        limit=self.front+900
        gain=min(gain,limit-d)
        if gain<65: return None
        spread=max(-gain/0.35,min(gain/0.35,spread))
        phase='expand' if abs(task['lateral']-lateral)>100 else 'advance'
        return d+gain,lateral+spread,phase
