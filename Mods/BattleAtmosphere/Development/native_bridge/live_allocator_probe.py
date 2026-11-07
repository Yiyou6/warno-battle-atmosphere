# Python 2.5, isolated test-world fixture, NEVER the normal skirmish entry.
# Candidate edges here describe the test arrangement, not verified navigation.
import _ba_native as native
import sip
import struct
import time
import math
import _ndf
import _gd_descriptor as gd
import _gd_variable as var
import _gd_object_specific as specific
import _front_game_rules_specific as rules
import _gd_tag as tag
import ba_allocator as alloc


def pointer(obj):
    return long(sip.unwrapinstance(obj))


class ProbeWrapper(object):
    def __init__(self, root):
        self.root = root
    def TerminateScript(self):
        native.finish_script()
        self.root = None


def run_probe():
    camps = [var.TGDVariableCamp() for i in range(3)]
    for index, camp in enumerate(camps):
        camp.SetAlliance(0 if index < 2 else 1)
    groups, actions = [], []
    unit_type = _ndf.Database.GetObject('$/GFX/Unit/Descriptor_Unit_M113A3_US')
    for i in range(12):
        group = var.TGDVariableUnitGroup()
        pos = tag.TGDTagPosition()
        # This coordinate is only the bounded unit-creation fixture.
        native.set_probe_position(struct.pack('<Qfff',pointer(pos),50000.+(i%4)*1000.,50000.+(i//4)*1000.,0.))
        spawn = gd.TGDDescriptorCreateUnitOnPosition()
        spawn.SetCamp(camps[i%2])
        spawn.SetTypeUnit(unit_type)
        spawn.SetNbUnit(1)
        spawn.SetGroup(group)
        spawn.SetPosition(pos)
        groups.append(group)
        actions.append(spawn)
    count = var.TGDVariableInteger()
    sample = gd.TGDDescriptorSetVariableIntegerFromUnitGroup()
    sample.SetGroup(groups[0])
    sample.SetVariable(count)
    tick = [0]
    destinations = {}
    def on_tick():
        tick[0] += 1
        rows = []
        for i, group in enumerate(groups):
            state = native.probe_first_unit_state(struct.pack('<Q',pointer(group)))
            if state:
                rows.append((i,struct.unpack('<Q',state[8:16])[0],struct.unpack('<fff',state[48:60])))
        nearest = []
        for i,uid,xyz in rows:
            nearest.append(min([math.hypot(xyz[0]-other[2][0],xyz[1]-other[2][1]) for other in rows if other[0] != i] or [0.]))
        native.log('LIVE_SAMPLE '+repr((tick[0],len(rows),round(min(nearest or [0.]),1),[(i,round(xyz[0],1),round(xyz[1],1)) for i,uid,xyz in rows])))
        if tick[0] == 1 and len(rows) == 12:
            cx = sum(row[2][0] for row in rows)/len(rows)
            cy = sum(row[2][1] for row in rows)/len(rows)
            sectors = [alloc.Sector(str(j),3) for j in range(4)]
            slots = [alloc.Slot('%d:%d'%(s,j),str(s),cx+(s-1.5)*20000+(j-1)*6000,cy+12000,
                                frozenset(['vehicle'])) for s in range(4) for j in range(3)]
            units = [alloc.Unit(str(uid),'fixture_ai_'+str(i%2),'fixture_alliance','vehicle',xyz[0],xyz[1]) for i,uid,xyz in rows]
            routes = [alloc.Route(u.id,s.id,int(math.hypot(u.x-s.x,u.y-s.y))) for u in units for s in slots]
            begin = time.clock()
            plan = alloc.allocate(alliance='fixture_alliance',units=units,sectors=sectors,slots=slots,
                                  routes=routes,min_spacing=6000.)
            native.log('LIVE_ALLOCATION '+repr((plan.complete,plan.sector_load,len(plan.assignments),time.clock()-begin)))
            if not plan.complete:
                raise RuntimeError('Incomplete fixture allocation')
            for i,uid,xyz in rows:
                assignment = plan.assignments[str(uid)]
                destinations[i] = (assignment.x,assignment.y)
                native.move_probe_group(struct.pack('<Qfff',pointer(groups[i]),assignment.x,assignment.y,xyz[2]))
        if destinations:
            error = [math.hypot(xyz[0]-destinations[i][0],xyz[1]-destinations[i][1]) for i,uid,xyz in rows]
            native.log('LIVE_TARGET_ERROR '+repr((tick[0],round(sum(error)/max(1,len(error)),1),round(max(error or [0.]),1))))
    native.set_tick_callback(on_tick)
    native.observe_count_action(struct.pack('<Q',pointer(sample)))
    pause = gd.TGDDescriptorWaitDuration()
    pause.SetDuration(1.)
    repeating = gd.TGDDescriptorSequential()
    repeating.SetNbExecutions(25)
    repeating.SetSubActions([sample,pause])
    effect = gd.TGDDescriptorSequential()
    effect.SetNbExecutions(1)
    effect.SetSubActions(actions+[repeating,gd.TGDDescriptorLoadingDone(),gd.TGDDescriptorWaitForEver()])
    settings = rules.TGDSpecificTacticalGameRules()
    settings.SetCheckEndGame(False)
    root = specific.TGDDescriptorLaunchEffetStandard()
    root.SetCampList(camps)
    root.SetGameRules(settings)
    root.SetEffetMap(effect)
    root.TransfertAllPythonSaveableToCPP()
    native.start_script(struct.pack('<Q',pointer(root)))
    return ProbeWrapper(root)


def launch():
    try:
        return run_probe()
    except Exception:
        import traceback
        native.log(('PYTHON_ERROR '+traceback.format_exc()).encode('utf-8'))
        native.diagnostic_exit()
