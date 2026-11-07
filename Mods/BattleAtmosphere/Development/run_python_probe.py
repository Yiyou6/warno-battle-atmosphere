"""Run only the isolated, bounded, headless script-entry experiment.

Exit code 6 with a BA_* exception is diagnostic output, NOT game success.
Never changes activation, copies installed mod files, or kills other processes.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import time
import os


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("receipt")
    parser.add_argument("--scenario", default="_2x3_BlackForestStorm_2vs2_CONQ")
    parser.add_argument("--timeout", type=float, default=40)
    parser.add_argument("--bridge", action="store_true", help="Load build-pinned research bridge into this new headless child only")
    parser.add_argument("--autohook", action="store_true", help="Observe the unmodified native skirmish launcher in a separate local data root")
    parser.add_argument("--fixture-camps", action="store_true", help="Explicit test-only provisioning for the empty headless lobby")
    parser.add_argument("--stock-data", action="store_true", help="Use shipped gameplay clusters and scenario packages, without local source overrides")
    parser.add_argument("--autoload", action="store_true", help="Run the isolated executable copy with its automatic VERSION loader; never inject")
    parser.add_argument("--installed-runtime", action="store_true", help="Verify the installed loader in an owned headless fixture child; never inject or touch a user session")
    parser.add_argument("--activation-gate", action="store_true", help="Exercise the real mod-activation and runtime.ini checks in the isolated copy")
    parser.add_argument("--replay-fixture", action="store_true", help="Read the copied skirmish replay instead of creating an empty map")
    parser.add_argument("--front-fixture",choices=["long","battle","mass","transport_api","transport","swapped","mass_swapped","transport_swapped"])
    args = parser.parse_args()
    development = Path(__file__).resolve().parent
    root = development.parents[2]
    runtime = root / ("Mods/BAScriptProbe/AutoRuntimeRoot" if args.autohook else "Mods/BAScriptProbe/RuntimeRoot")
    source = runtime / ("CommonData/Python/Eugen/ba_autorun.py" if args.autohook else "CommonData/Python/Eugen/ba_probe.py")
    if args.autoload or args.stock_data:
        source = root / 'Mods/BattleAtmosphere/Runtime/Python/ba_autorun.py'
    source_bytes = source.read_bytes()
    auxiliary_paths = [development / 'native_bridge/probe_bridge.c',
                       development / 'native_bridge/fx_budget.h',
                       development / 'native_bridge/cold_start_probe.c',
                       runtime / 'CommonData/Python/Eugen/ba_allocator.py',
                       runtime / 'CommonData/Python/Eugen/ba_fixture.py',
                       runtime / 'CommonData/Python/Eugen/ba_space.py',
                       development / 'native_bridge/embedded_python.h',
                       development / 'native_bridge/version_proxy.c',
                       root / 'Mods/BattleAtmosphere/Runtime/Python/ba_space.py',
                       root / 'Mods/BattleAtmosphere/Runtime/Python/ba_allocator.py',
                       root / 'Mods/BattleAtmosphere/Runtime/Python/ba_front.py',
                       root / 'Mods/BattleAtmosphere/Runtime/Python/ba_transport.py',
                       root / 'Mods/BattleAtmosphere/Runtime/Python/ba_tactics.py',
                       runtime / 'CommonData/Clusters/ClusterLoadGameplay.ndf']
    auxiliary = {str(p.relative_to(root)): p.read_bytes() for p in auxiliary_paths if p.exists()}
    command = [str(root / "WARNO.exe"), "-headless", "-nodialogbox",
               "-nocrashrpt", "-c", "-", "-noautologin", "-ignorecloudfiles",
               "-noMod", "--local-path", "BattleAtmosphereProbe",
               "-scenarioname", args.scenario, "-quitwhenmaploaded",
               "-rootdata", ".", "-uselocaldata", "CommonData:/BARuntimeDriver.ndf",
               "-ialevel", "3"]
    if args.autohook:
        command[command.index('--local-path') + 1] = 'BattleAtmosphereProbeAutoFixture' if args.fixture_camps else 'BattleAtmosphereProbeAuto'
    if args.replay_fixture:
        at = command.index("-scenarioname")
        command[at:at+2] = ["-replay", "ProgDir:/Mods/BAScriptProbe/Fixtures/skirmish-replay.rpl3"]
        command.remove("-quitwhenmaploaded")
    if args.stock_data:
        for option in ['-rootdata', '-uselocaldata']:
            at = command.index(option)
            del command[at:at+2]
    cwd = root if args.stock_data else runtime
    if args.autoload:
        if args.bridge or not (args.stock_data and args.autohook):
            raise ValueError('Autoload requires stock-data/autohook and forbids external injection')
        command[0] = str(root / 'Mods/BAScriptProbe/AutoloadBoot/WARNO.exe')
        cwd = Path(command[0]).parent
        from native_bridge.load_owned_probe import EXPECTED_EXE
        if hashlib.sha256(Path(command[0]).read_bytes()).hexdigest() != EXPECTED_EXE:
            raise ValueError('Unexpected isolated executable copy')
    if args.installed_runtime:
        if args.autoload or args.bridge or not (args.stock_data and args.autohook and args.fixture_camps and args.activation_gate):
            raise ValueError('Installed check requires stock-data/autohook/fixture-camps/activation-gate; no autoload copy or injection')
        from native_bridge.load_owned_probe import EXPECTED_EXE
        if hashlib.sha256(Path(command[0]).read_bytes()).hexdigest() != EXPECTED_EXE:
            raise ValueError('Unexpected installed executable')
        if not (cwd / 'version.dll').is_file():
            raise ValueError('Runtime is not installed')
    start = time.monotonic()
    env = os.environ.copy()
    if args.front_fixture:
        if not args.fixture_camps: raise ValueError("front fixture requires isolated camps")
        env["BA_FRONT_FIXTURE"] = args.front_fixture
    if args.activation_gate:
        env['BA_VALIDATE_ACTIVATION'] = '1'
    process = subprocess.Popen(command, cwd=cwd, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, env=env)
    timed_out = False
    bridge = None
    try:
        if args.bridge:
            from native_bridge.load_owned_probe import load_into_created_child
            bridge = load_into_created_child(process, command)
        stdout, stderr = process.communicate(timeout=args.timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        process.kill()
        stdout, stderr = process.communicate()
    except Exception as error:
        bridge = {"error": repr(error)}
        if process.poll() is None:
            process.kill()
        stdout, stderr = process.communicate()
    receipt = dict(command=command, cwd=str(cwd), returncode=process.returncode,
                   seconds=round(time.monotonic()-start, 3), timeout=timed_out,
                   source_sha256=hashlib.sha256(source_bytes).hexdigest(),
                   source_text=source_bytes.decode("utf-8"),
                   autoload_sha256=hashlib.sha256((cwd / 'version.dll').read_bytes()).hexdigest() if args.autoload or args.installed_runtime else None,
                   installed_runtime=args.installed_runtime,
                   activation_gate=args.activation_gate, front_fixture=args.front_fixture,
                   bridge=bridge,
                   auxiliary_sha256={p: hashlib.sha256(data).hexdigest() for p, data in auxiliary.items()},
                   auxiliary_text={p: data.decode('utf-8') for p, data in auxiliary.items()},
                   stdout=stdout.decode("utf-8", "replace"),
                   stderr=stderr.decode("utf-8", "replace"))
    path = development / args.receipt
    if path.parent.resolve() != development:
        raise ValueError("Receipt must stay in Development")
    path.write_text(json.dumps(receipt, ensure_ascii=True, indent=2), encoding="utf-8")
    print(json.dumps(receipt, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
