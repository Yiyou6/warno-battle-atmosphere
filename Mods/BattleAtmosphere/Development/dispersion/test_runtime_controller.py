"""Behavioral adapter tests. These mock simulation input, not game execution."""
import importlib.util
import ast
import math
from pathlib import Path
import struct
import sys
import time
import types
import unittest

ROOT = Path(__file__).resolve().parents[4]
SOURCE = ROOT / 'Mods/BattleAtmosphere/Runtime/Python'


def load(name):
    if name=='ba_space':load('ba_transport');load('ba_tactics')
    spec = importlib.util.spec_from_file_location(name, SOURCE / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class FakeNative(types.ModuleType):
    def __init__(self):
        super().__init__('_ba_native')
        self.rows = [[i+10, 101+i%2, 0, 6, 1+i%2, 200000.+(i%3)*1000,
                      200000.+(i//3)*1000, 0.] for i in range(12)]
        self.rows.append([99, 103, 0, 0, 3, 230000., 200000., 0.])
        self.orders = []; self.leases = []; self.logs = []; self.valid = True
        self.activity = {}; self.roles = {}; self.blocked = set()
        self.deployments = [(0,200000.,0.), (1,200000.,460000.)]
    def fixture_mode(self): return True
    def world_landmarks(self):
        return b''.join(struct.pack('<i3fii6f', 2, x, y, 0., a, 0, *([0.]*6))
                        for a,x,y in self.deployments)
    def world_unit_snapshot(self):
        return b''.join(struct.pack('<QQiii3f', *r) for r in self.rows)
    def world_navigation(self):
        return struct.pack('<IIfffI',30,30,15480.,0.,0.,900) + b'\x01'*3600
    def unit_traits(self, packed): return struct.pack('<IIfI',81,3,55.,1)
    def unit_role(self, packed): return self.roles.get(struct.unpack('<Q',packed)[0],'transport')
    def unit_activity(self, packed): return struct.pack('<i',self.activity.get(struct.unpack('<Q',packed)[0],0))
    def unit_transporter(self, packed):return struct.pack('<Q',getattr(self,'carriers',{}).get(struct.unpack('<Q',packed)[0],2**64-1))
    def unload_at_ai_unit(self,packed):
        if not hasattr(self,'unloads'):self.unloads=[]
        self.unloads.append(struct.unpack('<Qfff',packed));return struct.pack('<i',1)
    def unload_now_ai_unit(self,packed):return self.unload_at_ai_unit(packed)
    def nav_point(self, packed):
        kind,x,y=struct.unpack('<Iff',packed)
        return struct.pack('<i',int(self.valid and (int(x//15480),int(y//15480)) not in self.blocked))
    def lease_ai_unit(self, packed):
        self.leases.append(struct.unpack('<Qi',packed)); return struct.pack('<i',1)
    def move_ai_unit(self, packed):
        self.orders.append(struct.unpack('<Qfff',packed)); return struct.pack('<i',1)
    def attack_move_ai_unit(self, packed): return self.move_ai_unit(packed)
    def log(self, message): self.logs.append(message)


class RuntimeConstraints(unittest.TestCase):
    def setUp(self):
        self.native=FakeNative();sys.modules['_ba_native']=self.native
        load('ba_front');self.space=load('ba_space');self.space.long=int
        self.space.ord=lambda x:x if isinstance(x,int) else ord(x)
        self.space.time=types.SimpleNamespace(clock=time.perf_counter)
        self.controller=self.space.Controller()
    def test_joint_owner_targets_respect_spacing(self):
        for _ in range(20):self.controller.step()
        targets=[c['target'] for c in self.controller.claims.values()]
        self.assertTrue(targets)
        for i,a in enumerate(targets):
            for b in targets[i+1:]:self.assertGreaterEqual(self.space.distance(a,b)/215,120)
        self.assertNotIn(99,{r[0] for r in self.native.orders})
        self.assertEqual({r[1] for r in self.native.rows if r[0] in self.controller.claims},{101,102})
    def test_unseen_enemy_positions_do_not_affect_allied_routes(self):
        self.controller.step();expected=list(self.native.orders)
        self.setUp();self.native.rows.append([200,200,1,6,4,210000.,240000.,0.])
        self.controller.step()
        self.assertEqual([r for r in self.native.orders if r[0]!=200],expected)
    def test_no_forward_terrain_does_not_create_backward_detour(self):
        self.native.blocked={(x,13) for x in range(30)}
        for _ in range(8):self.controller.step()
        self.assertFalse(self.native.orders);self.assertFalse(self.native.leases)
    def test_both_wings_have_outward_forward_waypoints(self):
        for _ in range(10):self.controller.step()
        sides={self.controller.intents[uid]['side'] for uid in self.controller.claims}
        self.assertEqual(sides,{-1,0,1})
        for uid,c in self.controller.claims.items():
            f=c['forward'];p=c['origin'];goal=c['target']
            gain=sum((goal[k]-p[k])*f[k] for k in range(2))/215
            spread=abs(-(goal[0]-p[0])*f[1]+(goal[1]-p[1])*f[0])/215
            self.assertGreaterEqual(gain+1e-6,max(65,spread*.35))
            for q in c['path']:
                self.assertGreater(sum((q[k]-p[k])*f[k] for k in range(2)),0);p=q
    def test_callback_does_not_order_every_half_second(self):
        self.controller.step();count=len(self.native.orders)
        self.controller.step()
        self.assertLessEqual(len(self.native.orders)-count,16)
        uid=self.native.orders[0][0]
        self.assertEqual(sum(r[0]==uid for r in self.native.orders),1)

if __name__=='__main__':unittest.main()
