"""Capacity-constrained frontage allocation research core; NOT a WARNO plugin.

Pure deterministic planning over an authoritative snapshot supplied by a future
adapter. No game memory, input automation, executable patching or fake API calls.
Positions and distances are in metres in this model, not native WARNO units.
"""
from dataclasses import dataclass, field
from heapq import heappop, heappush
from math import hypot, isfinite


@dataclass(frozen=True)
class Unit:
    id: str
    owner: str
    alliance: str
    role: str
    x: float
    y: float
    previous_slot: str = ''
    hold_until: float = 0.0
    emergency: bool = False


@dataclass(frozen=True)
class Sector:
    id: str
    capacity: int
    # Same-width frontage sectors; a small minority may have weight 1.5.
    weight: float = 1.0


@dataclass(frozen=True)
class Slot:
    id: str
    sector: str
    x: float
    y: float
    roles: frozenset[str]


@dataclass(frozen=True)
class Route:
    unit: str
    slot: str
    # Adapter must supply a traversable, tactically admissible route. Missing
    # edges mean forbidden/unreachable; we never invent a straight-line route.
    cost: int


@dataclass(frozen=True)
class Obstacle:
    id: str
    x: float
    y: float
    sector: str = ''
    # An ally outside our control, including human-controlled units, must still
    # consume nearby physical space. It never becomes a controllable Unit.


@dataclass(frozen=True)
class Assignment:
    unit: str
    slot: str
    sector: str
    x: float
    y: float
    retained: bool


@dataclass
class Plan:
    assignments: dict[str, Assignment]
    unresolved: dict[str, str]
    sector_load: dict[str, int]
    pinned: list[str]
    fixed_overload: list[str]
    # Always false: this file has no game execution adapter.
    game_integrated: bool = field(default=False, init=False)

    @property
    def complete(self):
        return not self.unresolved and not self.fixed_overload


@dataclass
class _Edge:
    to: int
    rev: int
    cap: int
    cost: int


class _Flow:
    """Successive shortest augmenting paths, integer costs and node potentials."""
    def __init__(self, count):
        self.g = [[] for _ in range(count)]

    def add(self, a, b, cap, cost):
        forward = _Edge(b, len(self.g[b]), cap, cost)
        reverse = _Edge(a, len(self.g[a]), 0, -cost)
        self.g[a].append(forward)
        self.g[b].append(reverse)
        return forward

    def run(self, source, sink):
        # Initial forward costs are nonnegative. Potentials keep subsequent
        # residual costs nonnegative even with reverse cancellation edges.
        count = len(self.g)
        potential = [0] * count
        flow = 0
        while True:
            distance = [float('inf')] * count
            parent = [None] * count
            distance[source] = 0
            queue = [(0, source)]
            while queue:
                d, a = heappop(queue)
                if d != distance[a]:
                    continue
                for index, edge in enumerate(self.g[a]):
                    if not edge.cap:
                        continue
                    new = d + edge.cost + potential[a] - potential[edge.to]
                    if new < distance[edge.to]:
                        distance[edge.to] = new
                        parent[edge.to] = (a, index)
                        heappush(queue, (new, edge.to))
            if parent[sink] is None:
                return flow
            for i, d in enumerate(distance):
                if d != float('inf'):
                    potential[i] += d
            b = sink
            while b != source:
                a, index = parent[b]
                edge = self.g[a][index]
                edge.cap -= 1
                self.g[b][edge.rev].cap += 1
                b = a
            flow += 1


def _unique(items, kind):
    output = {}
    for item in items:
        if not item.id or item.id in output:
            raise ValueError('Missing or duplicate ' + kind + ' id')
        output[item.id] = item
    return dict(sorted(output.items()))


def _distance(a, b):
    return hypot(a.x - b.x, a.y - b.y)


def marginal_load(rank, weight):
    """Marginals of convex load squared / weight, in fixed integer precision."""
    return round(1000 * (2 * rank + 1) / weight)


def allocate(*, alliance, units, sectors, slots, routes, now=0.0,
             obstacles=(), min_spacing=120.0, switch_cost=300):
    """Compute one joint plan for all controlled AI owners in ONE alliance.

    Objective, in strict order: assign as many units as feasible; balance load
    over same-width frontage sectors; minimise route/risk/switch costs. Slot
    separation and sector capacities are hard constraints, not soft incentives.

    A candidate Plan with unresolved units is NOT executable: the future adapter
    must obtain more usable combat positions/routes and replan. It must not park
    the overflow, silently drop it, or publish the partial plan as success.
    """
    units = _unique(units, 'unit')
    sectors = _unique(sectors, 'sector')
    slots = _unique(slots, 'slot')
    obstacles = _unique(obstacles, 'obstacle')
    if not alliance or not isfinite(now) or now < 0:
        raise ValueError('Invalid alliance or simulation time')
    if not isfinite(min_spacing) or min_spacing <= 0:
        raise ValueError('Spacing must be positive and finite')
    if not isinstance(switch_cost, int) or switch_cost < 0:
        raise ValueError('Invalid switch cost')
    if set(units) & set(obstacles):
        raise ValueError('Same physical unit is controlled and an obstacle')
    for item in [*units.values(), *slots.values(), *obstacles.values()]:
        if not isfinite(item.x) or not isfinite(item.y):
            raise ValueError('Non-finite position')
    for unit in units.values():
        if unit.alliance != alliance or not unit.owner or not unit.role:
            raise ValueError('Wrong alliance or incomplete unit identity')
        if not isfinite(unit.hold_until) or unit.hold_until < 0:
            raise ValueError('Invalid assignment lease')
    for sector in sectors.values():
        if not isinstance(sector.capacity, int) or sector.capacity < 0:
            raise ValueError('Invalid capacity')
        if not isfinite(sector.weight) or not 1 <= sector.weight <= 1.5:
            raise ValueError('Main effort weight must be between 1 and 1.5')
    if sum(s.weight > 1 for s in sectors.values()) > max(1, len(sectors) // 4):
        raise ValueError('Too many main effort sectors')
    for slot in slots.values():
        if slot.sector not in sectors or not slot.roles:
            raise ValueError('Invalid slot sector or empty role eligibility')
    for obstacle in obstacles.values():
        if obstacle.sector and obstacle.sector not in sectors:
            raise ValueError('Obstacle references an unknown frontage sector')
    points = list(slots.values())
    for i, a in enumerate(points):
        if any(_distance(a, b) + 1e-8 < min_spacing for b in points[i + 1:]):
            raise ValueError('Candidate positions violate minimum spacing')
    available = {s.id: s for s in points if all(
        _distance(s, o) + 1e-8 >= min_spacing for o in obstacles.values())}
    edges = {}
    for route in routes:
        if route.unit not in units or route.slot not in slots:
            raise ValueError('Route references an unknown unit/slot')
        if not isinstance(route.cost, int) or route.cost < 0:
            raise ValueError('Route cost must be a nonnegative integer')
        key = route.unit, route.slot
        if key in edges:
            raise ValueError('Duplicate route')
        # Terrain, weapon utility, exposure, transport state and reachability
        # must have been checked before a route is admitted to this list.
        edges[key] = route.cost

    # Existing clumps must be allowed to dissolve even when a previous order
    # still has a lease. Noncontrolled nearby allies also invalidate pinning.
    crowded = set()
    unit_list = list(units.values())
    for i, unit in enumerate(unit_list):
        for other in unit_list[i + 1:]:
            if _distance(unit, other) < min_spacing:
                crowded.update((unit.id, other.id))
        if any(_distance(unit, o) < min_spacing for o in obstacles.values()):
            crowded.add(unit.id)

    assignments = {}
    loads = {s: sum(o.sector == s for o in obstacles.values()) for s in sectors}
    fixed_overload = [s for s in sectors if loads[s] > sectors[s].capacity]
    used = set()
    pinned = []
    def eligible(unit, slot):
        return unit.role in slot.roles and (unit.id, slot.id) in edges
    def place(unit, slot):
        assignments[unit.id] = Assignment(unit.id, slot.id, slot.sector,
                                          slot.x, slot.y, unit.previous_slot == slot.id)
        loads[slot.sector] += 1
        used.add(slot.id)
    for unit in units.values():
        slot = available.get(unit.previous_slot)
        if (slot and unit.hold_until > now and not unit.emergency
                and unit.id not in crowded and eligible(unit, slot)
                and slot.id not in used and loads[slot.sector] < sectors[slot.sector].capacity):
            place(unit, slot)
            pinned.append(unit.id)

    moving = [u for u in units.values() if u.id not in assignments]
    free_slots = [s for s in available.values() if s.id not in used]
    # Layered residual graph: source -> units -> exclusive slots -> sectors -> sink.
    source = 0
    unit_nodes = {u.id: i + 1 for i, u in enumerate(moving)}
    slot_start = len(unit_nodes) + 1
    slot_nodes = {s.id: slot_start + i for i, s in enumerate(free_slots)}
    sector_start = slot_start + len(slot_nodes)
    sector_nodes = {s: sector_start + i for i, s in enumerate(sectors)}
    sink = sector_start + len(sector_nodes)
    flow = _Flow(sink + 1)
    route_edges = {}
    largest = max(edges.values(), default=0) + switch_cost
    # One integer of balance improvement dominates ALL secondary costs.
    balance_scale = len(moving) * largest + 1
    for unit in moving:
        flow.add(source, unit_nodes[unit.id], 1, 0)
        for slot in free_slots:
            if eligible(unit, slot):
                cost = edges[unit.id, slot.id]
                if unit.previous_slot and unit.previous_slot != slot.id:
                    cost += switch_cost
                route_edges[unit.id, slot.id] = flow.add(
                    unit_nodes[unit.id], slot_nodes[slot.id], 1, cost)
    for slot in free_slots:
        flow.add(slot_nodes[slot.id], sector_nodes[slot.sector], 1, 0)
    for sector in sectors.values():
        free_capacity = max(0, min(sector.capacity - loads[sector.id], len(moving)))
        for index in range(free_capacity):
            rank = loads[sector.id] + index
            flow.add(sector_nodes[sector.id], sink, 1,
                     marginal_load(rank, sector.weight) * balance_scale)
    flow.run(source, sink)
    for (unit_id, slot_id), edge in route_edges.items():
        if edge.cap == 0:
            place(units[unit_id], available[slot_id])
    unresolved = {}
    for unit in moving:
        if unit.id not in assignments:
            any_edge = any(eligible(unit, slot) for slot in available.values())
            unresolved[unit.id] = ('capacity_or_competing_role_limit' if any_edge
                                    else 'no_admissible_combat_position_or_route')
    return Plan(dict(sorted(assignments.items())), unresolved, loads, pinned, fixed_overload)


def require_game_adapter():
    """Explicit boundary: this prototype must never masquerade as an installed AI."""
    raise RuntimeError('WARNO runtime adapter is not implemented or validated; '
                       'allocation output cannot be sent to the game.')
