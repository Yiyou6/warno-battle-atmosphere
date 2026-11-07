"""Continuous control simulations, separate from native integration evidence."""
import ast
import math
import struct
import sys
import time
import types
import unittest
from test_runtime_controller import FakeNative, load

class FrontNative(FakeNative):
    def __init__(self):
        super().__init__()
        self.held=set(); self.destinations={}; self.objectives=[]
    def attack_move_ai_unit(self,packed): return self.move_ai_unit(packed)
    def move_ai_unit(self,packed):
        uid,x,y,z=struct.unpack('<Qfff',packed)
        self.destinations[uid]=(x,y); return super().move_ai_unit(packed)
    def lease_ai_unit(self,packed):
        uid,on=struct.unpack('<Qi',packed)
        if on: self.held.add(uid)
        else: self.held.discard(uid)
        return super().lease_ai_unit(packed)
    def world_landmarks(self):
        return super().world_landmarks()+b''.join(struct.pack('<i3fii6f',1,x,y,0.,-1,1,*([0.]*6)) for x,y in self.objectives)
    def world_navigation(self):
        return struct.pack('<IIfffI',120,120,15480.,0.,0.,14400)+b'\x01'*57600
    def advance(self,attraction=None):
        for r in self.rows:
            if not 1<=r[3]<=6 or self.activity.get(r[0],0): continue
            goal=self.destinations.get(r[0]) if r[0] in self.held else attraction
            if goal:
                x=goal[0]-r[5]; y=goal[1]-r[6]; length=math.hypot(x,y)
                k=min(1,17*.5*215/max(1,length));r[5]+=x*k;r[6]+=y*k

class ContinuousTests(unittest.TestCase):
    def setUp(self):
        self.n=FrontNative();sys.modules['_ba_native']=self.n
        load('ba_front');self.s=load('ba_space');self.s.long=int
        self.s.ord=lambda x:x if isinstance(x,int) else ord(x)
        self.s.time=types.SimpleNamespace(clock=time.perf_counter)
        self.c=self.s.Controller()
    def large(self,n=36):
        self.n.deployments=[(0,4000*215.,0.),(1,4000*215.,8000*215.)]
        self.n.objectives=[(4000*215.,4000*215.)]
        self.n.rows=[[i+10,101+i%4,0,6,1+i%4,4000.*215+(i%6)*1500,3000.*215+(i//6)*1500,0.] for i in range(n)]
        self.c=self.s.Controller()
    def tick(self,n=1,attraction=None):
        for _ in range(n):self.n.advance(attraction);self.c.step()
    def test_arrival_keeps_lease_and_starts_next_leg(self):
        self.c.step();uid=next(iter(self.c.claims));row=next(r for r in self.n.rows if r[0]==uid)
        for _ in range(8):
            c=self.c.claims[uid]
            if c['mode']=='transit': row[5:7]=c['path'][c['cursor']]
            self.c.step()
        self.assertIn(uid,self.n.held)
        self.assertGreater(self.c.intents[uid]['legs'],0)
        self.assertNotIn((uid,0),self.n.leases)
    def test_joint_front_assigns_every_ai_without_waiting_for_density(self):
        self.large(72);self.tick(30)
        self.assertEqual(len(self.c.boards[0].tasks),72)
        self.assertGreater(len(self.c.claims),40)
        loads=self.c.boards[0].loads
        self.assertLessEqual(max(loads.values())-min(loads.values()),1)
    def test_unowned_objective_long_running_reinforcements_do_not_recollapse(self):
        self.large();attraction=self.n.objectives[0]; widths=[]
        for tick in range(480):
            if tick in (120,240):
                for i in range(16):
                    uid=1000+tick+i
                    self.n.rows.append([uid,101+i%4,0,6,1+i%4,4000*215.+(i%4)*1200,3000*215.+(i//4)*1200,0.])
            self.tick(attraction=attraction)
            if tick>=240 and tick%40==0:
                ls=sorted(self.c.project(0,(r[5],r[6]))[1] for r in self.n.rows)
                widths.append(ls[int(len(ls)*.9)]-ls[int(len(ls)*.1)])
        self.assertTrue(widths);self.assertGreater(min(widths),1500)
        self.assertGreater(widths[-1],2000)
        self.assertGreater(sum(t['legs']>=3 for t in self.c.intents.values()),40)
        nearby=sum(math.hypot(r[5]-attraction[0],r[6]-attraction[1])<260*215 for r in self.n.rows)
        self.assertLessEqual(nearby,8)
        self.assertGreater(sum(r[6]>3500*215 for r in self.n.rows),len(self.n.rows)*.75)
    def test_live_diagnostics_measure_actual_clump_and_rear_idle(self):
        self.large();self.c.step();board=self.c.boards[0]
        units=[(r[0],r[1],*self.c.project(0,r[5:7]),0) for r in self.n.rows]
        self.c.tick=1;first=self.c.metrics(0,units)
        self.assertEqual(first['largest_200m_cluster'],36)
        board.front=5000;self.c.tick=61;second=self.c.metrics(0,units)
        self.assertEqual(second['rear_idle_30s'],36)
    def test_mass_capture_attraction_does_not_pin_the_alliance_front(self):
        self.large(320);point=self.n.objectives[0]
        self.tick(360,attraction=point)
        nearby=sum(math.hypot(r[5]-point[0],r[6]-point[1])<260*215 for r in self.n.rows)
        self.assertLessEqual(nearby,8)
        self.assertGreaterEqual(len(self.c.claims),300)
        ls=sorted(self.c.project(0,r[5:7])[1] for r in self.n.rows)
        self.assertGreater(ls[288]-ls[32],4000)
    def test_contact_keeps_task_and_does_not_issue_over_combat(self):
        self.c.step();uid=next(iter(self.c.claims));before=len([r for r in self.n.orders if r[0]==uid])
        self.n.activity[uid]=32;self.tick(100)
        self.assertIn(uid,self.n.held)
        self.assertEqual(len([r for r in self.n.orders if r[0]==uid]),before)
        self.n.activity[uid]=4;self.c.step();self.assertNotIn(uid,self.n.held)
    def test_transport_and_support_and_human_excluded(self):
        for r,flag in zip(self.n.rows[:3],(1,2,4)):self.n.activity[r[0]]=flag
        self.n.roles[13]='AA';self.n.roles[14]='artillerie';self.tick(20)
        self.assertFalse({10,11,12,13,14,99}&{r[0] for r in self.n.orders})
    def test_identity_change_releases(self):
        self.c.step();uid=next(iter(self.c.claims))
        for r in self.n.rows:
            if r[0]==uid:r[3]=0
        self.c.step();self.assertNotIn(uid,self.c.claims)
    def test_front_width_adapts_to_narrow_map_geometry(self):
        self.n.world_navigation=lambda:struct.pack('<IIfffI',20,120,15480.,0.,0.,2400)+b'\x01'*9600
        self.n.deployments=[(0,720*215.,0.),(1,720*215.,8000*215.)]
        self.n.objectives=[]
        self.n.rows=[[i+10,101+i%4,0,6,1+i%4,720.*215+i%6*1000,2000.*215+i//6*1000,0.] for i in range(80)]
        self.c=self.s.Controller();self.tick(20)
        board=self.c.boards[0]
        self.assertLess(len(board.lanes),10)
        self.assertGreater(len(board.lanes),2)
        for lane in board.lanes:
            p=self.c.unproject(0,2200,board.centre+lane*260)
            self.assertGreaterEqual(self.c.nav.index(*p),0)
    def test_no_terrain_does_not_lease(self):
        self.n.valid=False;self.tick(20);self.assertFalse(self.n.leases)
    def test_rotation_preserves_forward_paths(self):
        for angle in (0,math.pi/4,math.pi/2,math.pi,math.pi*1.5):
            self.setUp();c=math.cos(angle);s=math.sin(angle)
            def rotate(x,y):return 500000+(x-230000)*c-(y-230000)*s,500000+(x-230000)*s+(y-230000)*c
            self.n.deployments=[(a,*rotate(x,y)) for a,x,y in self.n.deployments]
            for r in self.n.rows:r[5:7]=rotate(r[5],r[6])
            self.c=self.s.Controller();self.tick(20)
            self.assertTrue(self.c.claims)
            for cl in self.c.claims.values():
                p=cl['origin'];f=cl['forward']
                for q in cl['path']:
                    self.assertGreater((q[0]-p[0])*f[0]+(q[1]-p[1])*f[1],0);p=q
    def test_slow_forward_progress_is_not_cancelled_by_fixed_route_age(self):
        self.c.step();uid=next(iter(self.c.claims));row=next(r for r in self.n.rows if r[0]==uid)
        for _ in range(340):
            cl=self.c.claims.get(uid)
            if cl and cl['mode']=='transit':
                q=cl['path'][cl['cursor']];dx=q[0]-row[5];dy=q[1]-row[6];k=min(1,215/max(1,math.hypot(dx,dy)))
                row[5]+=dx*k;row[6]+=dy*k
            self.c.step()
        self.assertNotIn((uid,0),self.n.leases)
    def test_circular_motion_is_not_counted_as_route_progress(self):
        self.c.step();uid=next(iter(self.c.claims));row=next(r for r in self.n.rows if r[0]==uid);origin=row[5:7]
        for tick in range(105):
            row[5]=origin[0]+30*215*math.cos(tick*.7);row[6]=origin[1]+30*215*math.sin(tick*.7)
            self.c.step()
        self.assertIn((uid,0),self.n.leases)
    def test_stall_retries_without_permanent_lease(self):
        self.c.step();uid=next(iter(self.c.claims))
        for _ in range(81):self.c.step()
        self.assertIn((uid,0),self.n.leases)

if __name__=='__main__':unittest.main()
