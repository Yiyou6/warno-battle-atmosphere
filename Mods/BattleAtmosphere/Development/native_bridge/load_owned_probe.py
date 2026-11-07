"""Load the research DLL ONLY into a newly created headless test child.

No PID option, no attaching to a user's running game, no original-file edits.
Executable SHA, all headless/offline flags and DLL callsite must match.
"""
import ctypes as C
from ctypes import wintypes as W
import hashlib
from pathlib import Path
import time

EXPECTED_EXE = "70f34d844ebf23eea92d535fad0fffb6e0bc60dd1f64cc80c2b903d06abab3a8"


def load_into_created_child(process, command):
    if process.poll() is not None:
        raise RuntimeError("The owned test child has already stopped")
    required = {"-headless", "-nodialogbox", "-nocrashrpt", "-noautologin", "-noMod", "--local-path"}
    if not required.issubset(command) or command[command.index('--local-path')+1] not in {
            'BattleAtmosphereProbe', 'BattleAtmosphereProbeAuto', 'BattleAtmosphereProbeAutoFixture'}:
        raise ValueError("Refusing a non-isolated launch")
    if hashlib.sha256(Path(command[0]).read_bytes()).hexdigest() != EXPECTED_EXE:
        raise ValueError("Unsupported executable build")
    dll = Path(__file__).with_name("probe_bridge.dll").resolve()
    kernel = C.WinDLL("kernel32", use_last_error=True)
    kernel.VirtualAllocEx.argtypes = [W.HANDLE, C.c_void_p, C.c_size_t, W.DWORD, W.DWORD]
    kernel.VirtualAllocEx.restype = C.c_void_p
    kernel.WriteProcessMemory.argtypes = [W.HANDLE, C.c_void_p, C.c_void_p, C.c_size_t, C.POINTER(C.c_size_t)]
    kernel.WriteProcessMemory.restype = W.BOOL
    kernel.GetModuleHandleW.argtypes = [W.LPCWSTR]
    kernel.GetModuleHandleW.restype = C.c_void_p
    kernel.GetProcAddress.argtypes = [C.c_void_p, C.c_char_p]
    kernel.GetProcAddress.restype = C.c_void_p
    kernel.CreateRemoteThread.argtypes = [W.HANDLE, C.c_void_p, C.c_size_t, C.c_void_p, C.c_void_p, W.DWORD, C.POINTER(W.DWORD)]
    kernel.CreateRemoteThread.restype = W.HANDLE
    kernel.WaitForSingleObject.argtypes = [W.HANDLE, W.DWORD]
    kernel.WaitForSingleObject.restype = W.DWORD
    kernel.GetExitCodeThread.argtypes = [W.HANDLE, C.POINTER(W.DWORD)]
    kernel.CloseHandle.argtypes = [W.HANDLE]
    kernel.VirtualFreeEx.argtypes = [W.HANDLE, C.c_void_p, C.c_size_t, W.DWORD]
    # Verify the actual system loader address is mapped identically in our child.
    # ReadProcessMemory is confined to this child; no arbitrary PID is accepted.
    kernel.ReadProcessMemory.argtypes = [W.HANDLE, C.c_void_p, C.c_void_p, C.c_size_t, C.POINTER(C.c_size_t)]
    kernel.ReadProcessMemory.restype = W.BOOL
    loader = kernel.GetProcAddress(kernel.GetModuleHandleW("kernel32.dll"), b"LoadLibraryW")
    check = C.create_string_buffer(32)
    read = C.c_size_t()
    handle = W.HANDLE(int(process._handle))
    if not loader:
        raise C.WinError(C.get_last_error())
    deadline = time.monotonic() + 2
    while not kernel.ReadProcessMemory(handle, loader, check, 32, C.byref(read)):
        if process.poll() is not None or time.monotonic() >= deadline:
            raise C.WinError(C.get_last_error())
        time.sleep(0.02)
    if read.value != 32 or check.raw != C.string_at(loader, 32):
        raise RuntimeError("System loader mapping differs; refusing guessed address")
    payload = (str(dll) + "\0").encode("utf-16-le")
    storage = kernel.VirtualAllocEx(handle, None, len(payload), 0x3000, 4)
    if not storage:
        raise C.WinError(C.get_last_error())
    written = C.c_size_t()
    thread = None
    done = False
    try:
        data = C.create_string_buffer(payload)
        if not kernel.WriteProcessMemory(handle, storage, data, len(payload), C.byref(written)) or written.value != len(payload):
            raise C.WinError(C.get_last_error())
        thread = kernel.CreateRemoteThread(handle, None, 0, loader, storage, 0, None)
        if not thread:
            raise C.WinError(C.get_last_error())
        if kernel.WaitForSingleObject(thread, 20000) != 0:
            raise RuntimeError("Owned child's loader did not finish within twenty seconds")
        done = True
        code = W.DWORD()
        if not kernel.GetExitCodeThread(thread, C.byref(code)) or not code.value:
            raise RuntimeError("Research DLL refused to load")
        return {"dll": str(dll), "dll_sha256": hashlib.sha256(dll.read_bytes()).hexdigest(),
                "owned_pid": process.pid, "loader_finished": True}
    finally:
        if thread:
            kernel.CloseHandle(thread)
        if done or not thread:
            kernel.VirtualFreeEx(handle, storage, 0, 0x8000)
