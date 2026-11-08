"""Twenty-seat compatibility tests. Movement is simulated, not game rendering."""
import math
import struct
import sys
import time
import types
import unittest
from test_continuous_front import FrontNative
from test_runtime_controller import load


class TwentySeats(unittest.TestCase):
    def setup_match(self, per_owner=12, swapped=False):
        self.n = FrontNative()
        self.n.deployments = [(0, 4300 * 215., 0.), (1, 4300 * 215., 8000 * 215.)]
        self.n.objectives = [(x * 215., 4000 * 215.) for x in (2500, 4300, 6100)]
        self.n.rows = []
        self.signs = {}
        self.owners = {}
        for seat in range(20):
            side = seat // 10
            alliance = side ^ int(swapped)
            owner = (seat + 3) * 2**40 + 2**33
            for j in range(per_owner):
                uid = (seat + 1) * 2**40 + j * 2**32 + 123
                x = (2200 + (seat % 10) * 420 + (j % 3) * 35) * 215.
                y = (1600 + (j // 3) * 45) * 215.
                if side: y = 8000 * 215. - y
                self.n.rows.append([uid, owner, alliance, 0 if seat == 0 else 6, seat, x, y, 0.])
                self.owners[uid] = seat
                self.signs[uid] = 1 if side == 0 else -1
        sys.modules['_ba_native'] = self.n
        load('ba_front')
        self.s = load('ba_space')
        self.s.long = int
        self.s.ord = lambda x: x if isinstance(x, int) else ord(x)
        self.s.time = types.SimpleNamespace(clock=time.perf_counter)
        self.c = self.s.Controller()

    def ticks(self, count, move=True):
        for _ in range(count):
            if move: self.n.advance()
            self.c.step()

    def test_all_nineteen_ai_owners_receive_forward_orders_and_human_does_not(self):
        for swapped in (False, True):
            self.setup_match(swapped=swapped)
            starts = {r[0]: r[6] for r in self.n.rows}
            self.ticks(80)
            self.assertEqual({self.owners[o[0]] for o in self.n.orders}, set(range(1, 20)))
            self.assertTrue(all((o[2] - starts[o[0]]) * self.signs[o[0]] > 0 for o in self.n.orders))
            self.assertEqual(set(self.c.boards), {0, 1})
            self.assertTrue(all(0 not in {self.owners[u] for u in b.tasks} for b in self.c.boards.values()))

    def test_batched_discovery_and_planning_reach_all_twenty_seats(self):
        self.setup_match(per_owner=40)  # 800 total units in owner-major order.
        self.ticks(120)
        ordered = {o[0] for o in self.n.orders}
        for seat in range(1, 20):
            # Full movement coverage is a separate load/terrain criterion;
            # this checks owner reachability, not a claimed battle result.
            self.assertTrue({u for u in ordered if self.owners[u] == seat}, seat)
            self.assertEqual(len({u for u in self.c.attempts if self.owners[u] == seat}), 40, seat)
        self.assertEqual(len(self.c.traits), 800)

    def test_cross_owner_destinations_keep_spacing_on_both_sides(self):
        self.setup_match()
        self.ticks(40, move=False)
        for alliance in (0, 1):
            targets = [v['target'] for v in self.c.claims.values() if v['alliance'] == alliance]
            self.assertGreater(len(targets), 25)
            for i, p in enumerate(targets):
                for q in targets[i+1:]:
                    self.assertGreaterEqual(math.dist(p, q) / 215., 120 - 1e-5)

    def test_high_seat_human_and_dead_units_release_control(self):
        self.setup_match()
        self.ticks(40)
        uid = next(u for u in self.c.claims if self.owners[u] == 19)
        row = next(r for r in self.n.rows if r[0] == uid)
        row[3] = 0
        before = len(self.n.orders)
        self.ticks(2)
        self.assertNotIn(uid, self.c.claims)
        self.assertNotIn(uid, self.n.held)
        self.assertNotIn(uid, {o[0] for o in self.n.orders[before:]})
        dead = next(u for u in self.c.claims if self.owners[u] == 18)
        self.n.rows = [r for r in self.n.rows if r[0] != dead]
        self.ticks(2)
        self.assertNotIn(dead, self.c.claims)
        self.assertNotIn(dead, self.n.held)

    def test_reinforcement_at_last_owner_gets_forward_route(self):
        self.setup_match()
        self.ticks(80)
        row = list(next(r for r in self.n.rows if self.owners[r[0]] == 19))
        row[0] += 2**30
        row[6] = 6900 * 215.
        self.owners[row[0]] = 19
        self.n.rows.append(row)
        self.ticks(50)
        orders = [o for o in self.n.orders if o[0] == row[0]]
        self.assertTrue(orders)
        self.assertTrue(all(o[2] < 6900 * 215. for o in orders))

    def test_support_air_and_script_camps_are_left_to_native_ai(self):
        self.setup_match()
        protected = set()
        for seat, role in ((16, 'AA'), (17, 'artillerie'), (18, 'air')):
            for r in self.n.rows:
                if self.owners[r[0]] == seat:
                    self.n.roles[r[0]] = role
                    protected.add(r[0])
        for r in self.n.rows:
            if self.owners[r[0]] == 19:
                r[3] = 7
                protected.add(r[0])
        self.ticks(60)
        self.assertFalse(protected & {o[0] for o in self.n.orders})

    def test_transports_from_all_nineteen_owners_get_separate_forward_dropoffs(self):
        self.setup_match(per_owner=4, swapped=True)
        self.n.carriers = {}
        for seat in range(20):
            rows = [r for r in self.n.rows if self.owners[r[0]] == seat]
            car, passenger = rows[0], rows[1]
            self.n.roles[car[0]] = 'ifv'
            self.n.roles[passenger[0]] = 'infantry'
            self.n.activity[car[0]] = 2
            self.n.activity[passenger[0]] = 1
            self.n.carriers[passenger[0]] = car[0]
        self.ticks(60, move=False)
        self.assertEqual({self.owners[u] for u in self.c.transport.journeys}, set(range(1,20)))
        starts = {r[0]:r for r in self.n.rows}
        for uid, j in self.c.transport.journeys.items():
            self.assertTrue(all(starts[p][1] == j['owner'] for p in j['passengers']))
            self.assertGreater((j['target'][1]-starts[uid][6])*self.signs[uid], 0)
            for other,k in self.c.transport.journeys.items():
                if other != uid and k['alliance'] == j['alliance']:
                    self.assertGreaterEqual(math.dist(k['target'],j['target'])/215, 160-1e-5)

    def test_failed_dropoff_search_is_bounded_and_fair_across_owners(self):
        self.setup_match(per_owner=40)
        self.n.carriers = {}
        expected = set()
        for seat in range(20):
            rows = [r for r in self.n.rows if self.owners[r[0]] == seat]
            for car, passenger in zip(rows[::2], rows[1::2]):
                self.n.roles[car[0]] = 'ifv'
                self.n.roles[passenger[0]] = 'infantry'
                self.n.activity[car[0]] = 2
                self.n.activity[passenger[0]] = 1
                self.n.carriers[passenger[0]] = car[0]
                if seat: expected.add(car[0])
        # No dropoff exists: count actual planner calls with native terrain
        # rejection, including warm cache. Successful starts alone do not
        # bound work when all attempts fail.
        self.n.valid = False
        actual = self.c.transport.delivery_point
        calls = []
        seen = set()
        def counted(*args):
            calls.append(args[1]); seen.add(args[1])
            return actual(*args)
        self.c.transport.delivery_point = counted
        peak = 0
        for _ in range(200):
            calls[:] = []
            self.ticks(1, move=False)
            peak = max(peak, len(calls))
        self.assertEqual(seen, expected)
        self.assertEqual(len(self.c.transport.journeys), 0)
        self.assertFalse(self.n.held)  # Deferred searches retain native control.
        self.assertLessEqual(peak, 16)

    def transport_lease_failure(self, renew):
        self.setup_match(per_owner=4)
        self.n.carriers = {}
        rows = [r for r in self.n.rows if self.owners[r[0]] == 19]
        car, passenger = rows[:2]
        self.n.roles[car[0]] = 'ifv'; self.n.roles[passenger[0]] = 'infantry'
        self.n.activity[car[0]] = 2; self.n.activity[passenger[0]] = 1
        self.n.carriers[passenger[0]] = car[0]
        original = self.n.lease_ai_unit
        def reject_passenger(packed):
            uid,on = struct.unpack('<Qi',packed)
            if uid == passenger[0] and on: return struct.pack('<i',0)
            return original(packed)
        if renew:
            self.ticks(25,move=False)
            self.assertIn(car[0],self.c.transport.journeys)
        self.n.lease_ai_unit = reject_passenger
        self.ticks(1 if renew else 25,move=False)
        self.assertNotIn(car[0],self.c.transport.journeys)
        self.assertNotIn(car[0],self.n.held)
        self.assertNotIn(passenger[0],self.n.held)
        if not renew:
            self.assertNotIn(car[0],{o[0] for o in getattr(self.n,'unloads',[])})

    def test_transport_does_not_order_after_partial_lease_failure(self):
        self.transport_lease_failure(False)

    def test_transport_releases_pair_after_failed_renewal(self):
        self.transport_lease_failure(True)


if __name__ == '__main__':
    unittest.main()
