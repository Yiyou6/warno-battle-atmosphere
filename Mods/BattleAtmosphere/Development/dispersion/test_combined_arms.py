"""Behavioral regressions; native delivery is checked separately in game receipts."""
import sys,time,types,unittest,math
from test_runtime_controller import FakeNative,load

class Combined(unittest.TestCase):
    def setUp(self):
        self.n=FakeNative();sys.modules['_ba_native']=self.n
        load('ba_front');s=load('ba_space');s.long=int
        s.ord=lambda x:x if isinstance(x,int) else ord(x)
        s.time=types.SimpleNamespace(clock=time.perf_counter)
        self.c=s.Controller()
    def mount(self):
        self.n.rows=self.n.rows[:2]
        self.n.rows[1][1:5]=self.n.rows[0][1:5]
        for r in self.n.rows:r[6]=30000.
        self.n.roles={10:'ifv',11:'infantry'}
        self.n.activity={10:2,11:1};self.n.carriers={11:10}
        # A single carrier supplies one orientation sample: confirm it over
        # three callbacks before allowing a delivery lease.
        for _ in range(3):self.c.step()
        self.assertEqual(len(self.c.transport.journeys),1)
    def test_mounted_pair_stays_bound_and_destination_is_forward(self):
        self.mount();j=self.c.transport.journeys[10]
        self.assertEqual(j['passengers'],[11])
        self.assertGreater(self.c.project(0,j['target'])[0],500)
        self.assertFalse(self.n.orders)
        self.assertLessEqual(j['front']-self.c.project(0,j['target'])[0],550)
    def test_transport_rejects_cross_owner_or_human_pair(self):
        self.n.roles={10:'ifv',11:'infantry'};self.n.activity={10:2,11:1}
        self.n.carriers={11:10};self.c.step()
        self.assertFalse(self.c.transport.journeys)
        self.n.rows[1][1]=self.n.rows[0][1];self.n.rows[0][3]=0
        self.c.step();self.assertFalse(self.c.transport.journeys)
    def test_destroyed_passengers_are_not_delivered(self):
        self.mount();self.n.rows=self.n.rows[:1];self.n.activity[10]=0
        self.c.step()
        self.assertEqual(self.c.transport.delivered,0)
        self.assertFalse(self.c.transport.escorts)
        self.assertFalse(self.c.transport.journeys)
    def test_contact_unloads_instead_of_driving_through(self):
        self.mount();self.c.tick=30;self.n.activity[10]=34
        self.c.step()
        self.assertEqual(self.c.transport.emergency,1)
        self.assertEqual(self.c.transport.journeys[10]['phase'],'emergency')
    def test_stalled_transport_eventually_releases(self):
        self.mount()
        for _ in range(140):self.c.step()
        self.assertFalse(self.c.transport.journeys)
        self.assertTrue(any('delivery_failed' in s for s in self.n.logs))
    def test_moving_detour_is_not_false_idle(self):
        self.mount();j=self.c.transport.journeys[10]
        for _ in range(100):
            for r in self.n.rows:r[5]+=9*215;r[6]-=3*215
            self.c.step()
        self.assertIn(10,self.c.transport.journeys)
        self.assertEqual(self.c.transport.emergency,0)
        self.assertTrue(any('TRANSPORT_DETOUR_PROGRESS' in s for s in self.n.logs))
    def test_moving_in_circles_still_has_delivery_deadline(self):
        self.mount();j=self.c.transport.journeys[10];j['deadline']=self.c.tick+100
        for i in range(150):
            for r in self.n.rows:r[5]+=10*215 if i%2 else -10*215
            self.c.step()
        self.assertTrue(any('delivery_deadline' in s for s in self.n.logs))
        self.assertFalse(self.c.transport.journeys)
    def test_unload_transfers_to_continuous_front(self):
        self.mount();j=self.c.transport.journeys[10]
        for row in self.n.rows:row[5:7]=j['target']
        self.n.activity={};self.c.step()
        self.assertEqual(self.c.transport.delivered,1)
        self.assertIn(10,self.c.transport.escorts)
        for _ in range(20):self.c.step()
        self.assertEqual({r[0] for r in self.n.orders},{10,11})
    def test_unload_targets_are_reserved_across_owners(self):
        self.n.rows=self.n.rows[:8]
        self.n.carriers={}
        for i in range(0,8,2):
            car,foot=self.n.rows[i:i+2];foot[1:5]=car[1:5]
            self.n.roles[car[0]]='ifv';self.n.roles[foot[0]]='infantry'
            self.n.activity[car[0]]=2;self.n.activity[foot[0]]=1
            self.n.carriers[foot[0]]=car[0]
        for _ in range(3):self.c.step()
        targets=[j['target'] for j in self.c.transport.journeys.values()]
        self.assertGreaterEqual(len(targets),2)
        for i,a in enumerate(targets):
            for b in targets[i+1:]:self.assertGreaterEqual(math.dist(a,b)/215,160-1e-6)
    def tactical_setup(self):
        self.c.step();row=self.n.rows[0];b=self.c.boards[0]
        d,l=self.c.project(0,row[5:7]);b.front=d;b.centre=l
        b.tasks[row[0]]['lateral']=l
        return row,b,d,l
    def test_contact_and_flank_all_keep_positive_advance(self):
        row,b,d,l=self.tactical_setup();m=self.c.tactics
        self.c.traits[row[0]]=('armor',3,55)
        m.zones={(0,0):{'contact':2,'infantry':[d],'front':d}}
        g=m.goal(self.c,row,(d+400,l,'advance'))
        self.assertGreaterEqual(g[0]-d,100);self.assertLessEqual(g[0]-d,160)
        m.zones={(0,-1):{'contact':2,'front':d}}
        g=m.goal(self.c,row,(d+400,l,'advance'))
        self.assertGreater(g[0],d);self.assertGreater(g[1],l)
        self.assertEqual(b.tasks[row[0]]['tactic'],'adjacent_flank')
    def test_rear_arrivals_never_wait_for_local_support(self):
        row,b,d,l=self.tactical_setup();b.front=d+1000
        self.c.tactics.zones={(0,0):{'contact':4,'infantry':[d],'front':d}}
        expected=(d+500,l,'advance')
        self.assertEqual(self.c.tactics.goal(self.c,row,expected),expected)
        self.assertEqual(b.tasks[row[0]]['tactic'],'catch_up')
    def test_failed_path_changes_local_route_without_backward_order(self):
        row,b,d,l=self.tactical_setup();self.c.tactics.failed(row[0],self.c.tick)
        g=self.c.tactics.goal(self.c,row,(d+300,l,'advance'))
        self.assertGreater(g[0],d);self.assertNotEqual(g[1],l)
        self.assertEqual(b.tasks[row[0]]['tactic'],'detour')

if __name__=='__main__':unittest.main()
