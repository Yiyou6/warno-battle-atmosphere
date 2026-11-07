"""Synthetic model tests only. No assertion here establishes WARNO behaviour."""
from dataclasses import replace
from itertools import permutations
import math
import random
import unittest

from allocator import (Unit, Sector, Slot, Route, Obstacle, allocate,
                       marginal_load, require_game_adapter)


def field_case(count=40, weights=(1, 1, 1, 1), capacity=24):
    sectors = [Sector(str(i), capacity, w) for i, w in enumerate(weights)]
    slots = [Slot(f'{s.id}:{j}', s.id, int(s.id) * 1000 + j % 4 * 150,
                  j // 4 * 150, frozenset(['infantry', 'tank', 'at', 'recon', 'aa']))
             for s in sectors for j in range(capacity)]
    units = [Unit(f'u{i:03}', f'ai{i % 4}', 'blue', 'infantry', 1750, -200)
             for i in range(count)]
    routes = [Route(u.id, s.id, round(math.hypot(u.x-s.x, u.y-s.y)))
              for u in units for s in slots]
    return dict(alliance='blue', units=units, sectors=sectors, slots=slots, routes=routes)


class AllocationTests(unittest.TestCase):
    def assert_valid(self, plan, case):
        self.assertFalse(plan.game_integrated)
        self.assertEqual(len(plan.assignments), len({a.slot for a in plan.assignments.values()}))
        allowed = {(r.unit, r.slot) for r in case['routes']}
        for a in plan.assignments.values():
            self.assertIn((a.unit, a.slot), allowed)
        for s in case['sectors']:
            self.assertLessEqual(plan.sector_load[s.id], s.capacity)
        self.assertEqual(set(plan.assignments) | set(plan.unresolved),
                         {u.id for u in case['units']})

    def test_existing_clump_has_even_distinct_destinations(self):
        case = field_case()
        plan = allocate(**case)
        self.assertTrue(plan.complete)
        self.assertEqual(list(plan.sector_load.values()), [10]*4)
        self.assert_valid(plan, case)

    def test_limited_main_effort(self):
        case = field_case(54, weights=(1.5, 1, 1, 1))
        plan = allocate(**case)
        self.assertTrue(plan.complete)
        self.assertEqual(list(plan.sector_load.values()), [18, 12, 12, 12])
        self.assert_valid(plan, case)

    def test_four_owners_share_one_capacity_and_slot_inventory(self):
        case = field_case(80, capacity=20)
        plan = allocate(**case)
        self.assertTrue(plan.complete)
        self.assertEqual(len(plan.assignments), 80)
        self.assertEqual(list(plan.sector_load.values()), [20]*4)
        self.assert_valid(plan, case)

    def test_global_assignment_does_not_strand_specialist(self):
        case = dict(alliance='blue',
                    units=[Unit('flex','ai','blue','tank',0,0),
                           Unit('special','ai','blue','infantry',0,0)],
                    sectors=[Sector('s',2)],
                    slots=[Slot('a','s',0,1000,frozenset(['tank','infantry'])),
                           Slot('b','s',200,1000,frozenset(['tank']))],
                    routes=[Route('flex','a',0),Route('flex','b',10),Route('special','a',1)])
        plan = allocate(**case)
        self.assertTrue(plan.complete)
        self.assertEqual(plan.assignments['special'].slot, 'a')
        self.assertEqual(plan.assignments['flex'].slot, 'b')

    def test_unreachable_and_wrong_role_edges_are_not_used(self):
        case = field_case(1)
        case['routes'] = [Route(case['units'][0].id,case['slots'][0].id,0)]
        case['slots'][0] = replace(case['slots'][0], roles=frozenset(['aa']))
        plan = allocate(**case)
        self.assertFalse(plan.complete)
        self.assertEqual(len(plan.assignments), 0)
        self.assertEqual(list(plan.unresolved.values()), ['no_admissible_combat_position_or_route'])

    def test_human_ally_blocks_space_and_consumes_sector_capacity(self):
        case = field_case(7, capacity=2)
        slot = case['slots'][0]
        plan = allocate(**case, obstacles=[Obstacle('human',slot.x,slot.y,slot.sector)])
        self.assertTrue(plan.complete)
        self.assertNotIn(slot.id, [a.slot for a in plan.assignments.values()])
        self.assertNotIn('human',plan.assignments)
        self.assertEqual(list(plan.sector_load.values()),[2]*4)

    def test_human_overload_is_reported_without_taking_control(self):
        case = field_case(0, capacity=1)
        plan = allocate(**case, obstacles=[Obstacle('h1',0,0,'0'),Obstacle('h2',200,0,'0')])
        self.assertFalse(plan.complete)
        self.assertEqual(plan.fixed_overload,['0'])
        self.assertEqual(plan.assignments,{})

    def test_incoming_reinforcement_keeps_reservation(self):
        case = field_case(2, capacity=1)
        unit = case['units'][0]
        case['units'][0] = replace(unit,x=-1000,previous_slot='0:0',hold_until=20)
        plan = allocate(**case,now=5)
        self.assertIn(unit.id,plan.pinned)
        self.assertEqual(plan.assignments[unit.id].slot,'0:0')
        self.assertNotEqual(plan.assignments[case['units'][1].id].slot,'0:0')

    def test_casualty_releases_slot_and_reinforcement_fills_gap(self):
        case = field_case(8,capacity=2)
        first = allocate(**case)
        survivors = []
        dead = case['units'][0].id
        for u in case['units']:
            if u.id == dead:
                continue
            a = first.assignments[u.id]
            survivors.append(replace(u,x=a.x,y=a.y,previous_slot=a.slot,hold_until=20))
        fresh = Unit('fresh','ai0','blue','infantry',-1000,-1000)
        case['units'] = survivors+[fresh]
        case['routes'] = [r for r in case['routes'] if r.unit != dead]
        case['routes'] += [Route(fresh.id,s.id,1000) for s in case['slots']]
        second = allocate(**case,now=5)
        self.assertTrue(second.complete)
        self.assertEqual(second.assignments['fresh'].slot,first.assignments[dead].slot)
        self.assertEqual(len(second.pinned),7)

    def test_small_cost_changes_do_not_cancel_active_lease(self):
        case = field_case(4,capacity=2)
        first = allocate(**case)
        case['units'] = [replace(u,x=first.assignments[u.id].x,y=first.assignments[u.id].y,
                                previous_slot=first.assignments[u.id].slot,hold_until=20)
                         for u in case['units']]
        case['routes'] = [replace(r,cost=0 if r.slot.endswith(':1') else 5000)
                          for r in case['routes']]
        second = allocate(**case,now=5)
        self.assertEqual({u:a.slot for u,a in first.assignments.items()},
                         {u:a.slot for u,a in second.assignments.items()})

    def test_lost_route_breaks_lease(self):
        case = field_case(1)
        case['units'][0] = replace(case['units'][0],previous_slot='0:0',hold_until=20)
        case['routes'] = [r for r in case['routes'] if r.slot!='0:0']
        plan = allocate(**case,now=5)
        self.assertTrue(plan.complete)
        self.assertEqual(plan.pinned,[])
        self.assertNotEqual(plan.assignments['u000'].slot,'0:0')

    def test_existing_clump_breaks_leases(self):
        case = field_case(4,capacity=4)
        case['units'] = [replace(u,previous_slot=f'0:{i}',hold_until=20)
                         for i,u in enumerate(case['units'])]
        plan = allocate(**case,now=5)
        self.assertEqual(plan.pinned,[])
        self.assertEqual(list(plan.sector_load.values()),[1]*4)

    def test_overcapacity_is_failure_not_idle_reserve(self):
        case = field_case(9,capacity=2)
        plan = allocate(**case)
        self.assertFalse(plan.complete)
        self.assertEqual(len(plan.unresolved),1)
        self.assertEqual(len(plan.assignments),8)
        self.assert_valid(plan,case)

    def test_rejects_enemy_units_duplicate_ids_and_dense_candidates(self):
        case = field_case(1)
        with self.assertRaises(ValueError):
            allocate(**{**case,'units':[replace(case['units'][0],alliance='red')]})
        with self.assertRaises(ValueError):
            allocate(**{**case,'units':case['units']*2})
        with self.assertRaises(ValueError):
            allocate(**{**case,'slots':case['slots']+[replace(case['slots'][0],id='overlap')]})

    def test_rejects_global_mass_attack_weight(self):
        with self.assertRaises(ValueError):
            allocate(**field_case(4,weights=(1.5,1.5,1,1)))

    def test_input_order_does_not_change_plan(self):
        case = field_case(24)
        first = allocate(**case)
        for key in ['units','slots','sectors','routes']:
            case[key] = list(reversed(case[key]))
        second = allocate(**case)
        self.assertEqual(first.assignments,second.assignments)

    def test_against_exhaustive_small_matching_oracle(self):
        # Independent brute force verifies max cardinality, convex fairness and
        # cost, including sparse routes requiring cancellation/reassignment.
        rng = random.Random(94861)
        for _ in range(35):
            units=[Unit(str(i),'ai','blue','infantry',0,0) for i in range(3)]
            sectors=[Sector('left',3),Sector('right',3)]
            slots=[Slot(str(i),'left' if i<3 else 'right',i*150,0,frozenset(['infantry']))
                   for i in range(6)]
            routes=[Route(u.id,s.id,rng.randrange(20)) for u in units for s in slots
                    if rng.random()>.3]
            costs={(r.unit,r.slot):r.cost for r in routes}
            plan=allocate(alliance='blue',units=units,sectors=sectors,slots=slots,routes=routes)
            best=None
            for targets in permutations([s.id for s in slots]+['none0','none1','none2'],3):
                pairs=[(u.id,t) for u,t in zip(units,targets) if not t.startswith('none')]
                if any(pair not in costs for pair in pairs):
                    continue
                counts=[sum(int(t)<3 for _,t in pairs),sum(int(t)>=3 for _,t in pairs)]
                score=(-len(pairs),sum(marginal_load(i,1) for c in counts for i in range(c)),
                       sum(costs[p] for p in pairs))
                if best is None or score<best:
                    best=score
            actual=(-len(plan.assignments),
                    sum(marginal_load(i,1) for c in plan.sector_load.values() for i in range(c)),
                    sum(costs[u,a.slot] for u,a in plan.assignments.items()))
            self.assertEqual(actual,best)

    def test_no_claim_of_runtime_integration(self):
        with self.assertRaisesRegex(RuntimeError,'not implemented'):
            require_game_adapter()


if __name__=='__main__':
    unittest.main(verbosity=2)
