"""Read-only live-run evidence capture; never calls or changes the game process."""
import argparse
import collections
import datetime
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'native_bridge'))
from verify_runtime import events as bridge_events


def events(output, name):
    normalized = '\n'.join('BA_BRIDGE ' + line[len('BA_RUNTIME '):]
                           if line.startswith('BA_RUNTIME ') else line
                           for line in output.splitlines())
    return bridge_events(normalized, name)


def capture(pid):
    runtime = ROOT.parent / 'Runtime'
    source = runtime / 'last-run.log'
    raw = source.read_bytes()
    text = raw.decode('utf-8', errors='replace')
    # A write may be in progress. Preserve every byte, parse complete lines only.
    complete = text[:text.rfind('\n') + 1]
    current = complete.rsplit('BA_RUNTIME AUTOMATIC_SKIRMISH_ENTRY', 1)[-1]
    stats = events(current, 'SPACE_STATUS')
    boards = events(current, 'FRONT_STATUS')
    metrics = events(current, 'FRONT_METRICS')
    orders = events(current, 'SPACE_ORDER')
    arrivals = events(current, 'FRONT_ARRIVAL')
    returns = events(current, 'SPACE_RETURN')
    routes = events(current, 'SPACE_ROUTE')
    now = datetime.datetime.now(datetime.timezone.utc)
    prefix = ROOT / ('runtime-live-preview4-%s-%s' % (pid, now.strftime('%Y%m%dT%H%M%SZ')))
    revision = [s.split('SPACE_REVISION ', 1)[1] for s in current.splitlines() if 'SPACE_REVISION ' in s]
    result = {
        'observed_utc': now.isoformat(),
        'reported_process_id': pid,
        'log_last_write_utc': datetime.datetime.fromtimestamp(source.stat().st_mtime, datetime.timezone.utc).isoformat(),
        'log_bytes': len(raw),
        'log_sha256': hashlib.sha256(raw).hexdigest(),
        'raw_log': prefix.with_suffix('.log').name,
        'revision': revision[-1] if revision else None,
        'scenario': current.strip().splitlines()[0].removeprefix('BA_RUNTIME ') if current.strip() else None,
        'last_status': stats[-1] if stats else None,
        'last_board': boards[-1] if boards else None,
        'latest_metrics': metrics[-1] if metrics else None,
        'metrics_history': metrics,
        'initial_orders_accepted': sum(o[-1] == 1 for o in orders),
        'waypoint_orders': len(events(current, 'SPACE_WAYPOINT')),
        'unique_units_ordered': len(set(o[0] for o in orders if o[-1] == 1)),
        'route_phases': dict(collections.Counter(r[1] for r in routes)),
        'completed_routes': len(arrivals),
        'units_completed_at_least_3_routes': sum(v >= 3 for v in collections.Counter(a[0] for a in arrivals).values()),
        'return_reasons': dict(collections.Counter(r[1] for r in returns)),
        'max_sampled_planning_ms': max((s[-1] for s in stats), default=None),
        'stopped': 'AUTOMATIC_SKIRMISH_STOP' in current,
        'errors': [s for s in current.splitlines() if any(w in s for w in ('Traceback', 'Error:', 'FAILED', 'EXCEPTION'))],
        'limitations': 'Log evidence only; density includes AI maneuver units and does not prove visual quality or objective ownership.',
    }
    prefix.with_suffix('.log').write_bytes(raw)
    prefix.with_suffix('.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps({k: v for k, v in result.items() if k not in ('metrics_history', 'last_board')}, indent=2))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--pid', type=int, required=True, help='Process id already confirmed by read-only OS inventory.')
    capture(parser.parse_args().pid)
