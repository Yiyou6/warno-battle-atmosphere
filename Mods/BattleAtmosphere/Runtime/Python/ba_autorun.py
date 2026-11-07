# Automatic skirmish sidecar. The native launcher retains roster and rules.
import _ba_native as native
import sip
import struct
import _gd_descriptor as gd
from ba_space import Controller
class Observer(object):
    def __init__(self,owned): self.owned=owned
    def TerminateScript(self):
        native.finish_script()
        self.owned=None
        native.log('AUTO_PYTHON_CLEANUP')
def launch():
    native.log('AUTO_PYTHON_STARTED '+repr(native.world_context()))
    controller=Controller()
    def tick():
        if native.fixture_mode() in ('transport','transport_swapped') and controller.tick<10:
            import ba_fixture
            ba_fixture.transport_tick(controller,False)
            controller.tick+=1
            return
        if native.fixture_mode()=='transport_api':
            import ba_fixture
            ba_fixture.transport_tick(controller)
            controller.tick+=1
            return
        if controller.tick==0 and native.fixture_mode():
            raw=native.world_unit_snapshot()
            for i in range(0,len(raw),40):
                r=struct.unpack('<QQiii3f',raw[i:i+40])
                if r[4]==3 and r[3]==7: native.fixture_mark_human(struct.pack('<Q',r[0]))
            raw=native.world_unit_snapshot()
            for i in range(0,len(raw),40):
                r=struct.unpack('<QQiii3f',raw[i:i+40])
                if r[3] not in range(1,7):
                    result=native.move_ai_unit(struct.pack('<Qfff',r[0],r[5]+10000,r[6]+10000,r[7]))
                    native.log('IDENTITY_GUARD '+repr((r[3],struct.unpack('<i',result)[0])))
        controller.step()
    native.set_tick_callback(tick)
    pause=gd.TGDDescriptorWaitDuration()
    pause.SetDuration(.5)
    native.observe_timer_action(struct.pack('<Q',long(sip.unwrapinstance(pause))))
    loop=gd.TGDDescriptorSequential()
    loop.SetNbExecutions(1000000)
    loop.SetSubActions([pause])
    native.attach_update(struct.pack('<Q',long(sip.unwrapinstance(loop))))
    return Observer([pause,loop,controller,tick])
