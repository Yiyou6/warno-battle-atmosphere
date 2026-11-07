"""Direction must match physical spawn sides, independently of map labels."""
import json,math,sys,time,types,unittest
from pathlib import Path
from test_runtime_controller import FakeNative,load

class Orientation(unittest.TestCase):
    def setup_controller(self,n):
        self.n=n;sys.modules['_ba_native']=n;load('ba_front');s=load('ba_space')
        s.long=int;s.ord=lambda x:x if isinstance(x,int) else ord(x)
        s.time=types.SimpleNamespace(clock=time.perf_counter)
        self.c=s.Controller()
    def test_swapped_alliances_move_toward_opponent(self):
        n=FakeNative()
        for r in n.rows:r[2]=1
        self.setup_controller(n)
        for _ in range(20):self.c.step()
        self.assertEqual(self.c.side_assignment,{1:0})
        self.assertTrue(n.orders)
        starts={r[0]:r for r in n.rows}
        self.assertTrue(all(o[2]>starts[o[0]][6] for o in n.orders))
    def test_one_carrier_does_not_need_enemy_units(self):
        n=FakeNative();n.rows=n.rows[:1];n.rows[0][2]=1;n.rows[0][6]=30000
        self.setup_controller(n);self.c.step()
        self.assertFalse(n.leases)
        self.c.step();self.c.step()
        self.assertEqual(self.c.side_assignment,{1:0})
        for _ in range(7):self.c.step()
        self.assertTrue(n.orders)
    def test_central_ambiguous_start_keeps_native_control(self):
        n=FakeNative()
        for r in n.rows:r[6]=230000
        self.setup_controller(n)
        for _ in range(20):self.c.step()
        self.assertFalse(n.orders);self.assertFalse(n.leases);self.assertFalse(self.c.frames)
    def test_frame_does_not_flip_after_crossing_enemy_half(self):
        n=FakeNative();self.setup_controller(n);self.c.step();frame=self.c.axis(0)
        for r in n.rows:r[6]=440000
        for _ in range(10):self.c.step()
        self.assertEqual(self.c.axis(0),frame)
    def test_delayed_opposite_alliance_uses_its_own_spawn(self):
        n=FakeNative();self.setup_controller(n);self.c.step()
        n.rows.extend([[500+i,200,1,6,4,200000.+i*1000,430000.,0.] for i in range(4)])
        self.c.step()
        self.assertEqual(self.c.side_assignment,{0:0,1:1})
        self.assertLess(self.c.axis(1)[1][1],0)
    def test_plane_and_loaded_passenger_do_not_vote_for_wrong_home(self):
        n=FakeNative();n.rows=n.rows[:4]
        for i,r in enumerate(n.rows):r[6]=20000 if i==0 else 440000
        n.roles={11:'air',12:'infantry',13:'infantry'};n.activity={12:1,13:1}
        self.setup_controller(n)
        for _ in range(3):self.c.step()
        self.assertEqual(self.c.side_assignment,{0:0})
    def test_live_regression_origins_select_opposite_map_labels(self):
        data=json.loads((Path(__file__).resolve().parents[1]/'direction-regression-evidence.json').read_text())
        n=FakeNative()
        n.deployments=[(0,1144375.,204561.),(1,901642.,1761825.)]
        n.rows=[[r['uid'],100+r['alliance'],r['alliance'],6,r['alliance']+1,*r['position'],0.] for r in data['rows']]
        self.setup_controller(n)
        # Read-only orientation replay does not assume the fake navigation
        # grid covers this actual map.
        self.c.activity={r[0]:0 for r in n.rows};self.c.tick=1;self.c.orient(n.rows)
        self.assertEqual(self.c.side_assignment,{0:1,1:0})
        for r in data['rows']:
            d,l=self.c.project(r['alliance'],r['position'])
            self.assertLess(abs(d),r['map_span']*.3)
            h,f=self.c.axis(r['alliance'])
            old=r['target'];p=r['position']
            self.assertLess((old[0]-p[0])*f[0]+(old[1]-p[1])*f[1],0)
    def test_rotated_swapped_geometry(self):
        for angle in (math.pi/2,math.pi,math.pi*1.3):
            n=FakeNative()
            def rotate(x,y):return (600000+x*math.cos(angle)-y*math.sin(angle),600000+x*math.sin(angle)+y*math.cos(angle))
            n.deployments=[(a,*rotate(x,y)) for a,x,y in n.deployments]
            for r in n.rows:r[2]=1;r[5:7]=rotate(*r[5:7])
            self.setup_controller(n);self.c.activity={r[0]:0 for r in n.rows};self.c.orient(n.rows)
            self.assertEqual(self.c.side_assignment,{1:0})
            f=self.c.axis(1)[1]
            self.assertAlmostEqual(f[0],-math.sin(angle));self.assertAlmostEqual(f[1],math.cos(angle))

if __name__=='__main__':unittest.main()
