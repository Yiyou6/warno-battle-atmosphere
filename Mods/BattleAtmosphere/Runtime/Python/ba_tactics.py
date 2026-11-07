# Python 2.5. Local forward decisions, no alternating stop/hold schedule.
from __future__ import division
import math

class Momentum(object):
    def __init__(self):
        self.zones={};self.failures={};self.counts={}
    def update(self,c,all_units):
        zones={}
        for alliance,units in all_units.items():
            board=c.boards[alliance]
            for u in units:
                if u[4]&7:continue
                lane=int(round((u[3]-board.centre)/260)) if board.centre is not None else 0
                zone=zones.setdefault((alliance,lane),{'depths':[],'contact':0,'infantry':[]})
                zone['depths'].append(u[2]);zone['contact']+=bool(u[4]&40)
                if c.traits[u[0]][0] in ('infantry','engineer','AT'):zone['infantry'].append(u[2])
        for key,z in zones.items():
            z['depths'].sort();z['front']=z['depths'][int((len(z['depths'])-1)*.7)]
        self.zones=zones
        for uid in list(self.failures):
            if c.tick>self.failures[uid][0]:del self.failures[uid]
    def failed(self,uid,tick):
        old=self.failures.get(uid,(0,0))
        self.failures[uid]=(tick+120,old[1]+1)
    def goal(self,c,row,goal):
        if goal is None:return None
        uid=row[0];a=row[2];board=c.boards[a];d,l=c.project(a,(row[5],row[6]))
        task=board.tasks.get(uid);role=c.traits[uid][0]
        if task is None:return goal
        gd,gl,phase=goal;mode='advance'
        lane=int(round((l-board.centre)/260)) if board.centre is not None else 0
        own=self.zones.get((a,lane),{});left=self.zones.get((a,lane-1),{});right=self.zones.get((a,lane+1),{})
        # Rear arrivals and unfinished wide-front deployment keep their full leg.
        if d<board.front-600 or abs(task['lateral']-l)>260:
            mode='catch_up' if d<board.front-600 else 'expand'
        elif uid in self.failures:
            count=self.failures[uid][1]
            shift=180*(-1 if count%2 else 1)
            gl=task['lateral']+shift;gd=d+max(140,abs(gl-l)*.4);mode='detour'
        elif own.get('contact',0):
            # Units actually firing are already protected by native combat state.
            # Everyone else keeps a positive advance; vehicles use smaller legs
            # alongside nearby dismounted infantry, without waiting to form a group.
            if role in ('armor','ifv','transport','appui') and own.get('infantry'):
                gd=d+max(100,min(gd-d,160));mode='moving_support'
            else:
                gd=d+max(140,min(gd-d,210));mode='contact_advance'
        elif left.get('contact',0) or right.get('contact',0):
            # A nearby friendly engagement signals pressure, not hidden enemy data.
            # Small, persistent corridor offset leaves the original frontage intact.
            if 'flank_offset' not in task:
                task['flank_offset']=130 if left.get('contact',0)>right.get('contact',0) else -130
                task['flank_until']=c.tick+120
            gl=task['lateral']+task['flank_offset'];gd=d+max(240,abs(gl-l)*.4);mode='adjacent_flank'
        elif own and (left or right) and own['front']>max(left.get('front',own['front']-260),right.get('front',own['front']-260))+180:
            gd=d+max(260,gd-d);mode='exploit'
        if 'flank_offset' in task and mode not in ('adjacent_flank','detour'):
            if c.tick<task['flank_until'] and mode not in ('catch_up','expand'):
                gl=task['lateral']+task['flank_offset']
            elif c.tick>=task['flank_until']:
                del task['flank_offset'];task.pop('flank_until',None)
        gain=min(gd-d,board.front+900-d)
        if gain<65:return goal
        gl=l+max(-gain/.35,min(gain/.35,gl-l))
        self.counts[mode]=self.counts.get(mode,0)+1
        task['tactic']=mode
        return d+gain,gl,('expand' if abs(gl-l)>100 else 'advance')
