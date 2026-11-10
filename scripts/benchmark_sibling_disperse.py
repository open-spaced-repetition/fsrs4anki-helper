"""Compare the original and current sibling solvers, excluding Anki I/O.

Run from the repository root:
python scripts/benchmark_sibling_disperse.py --baseline HEAD --output /tmp/sibling-benchmark.json
"""

import argparse
import gc
import hashlib
import json
import platform
import statistics
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from random import Random
from time import perf_counter_ns

ROOT = Path(__file__).resolve().parents[1]
# Support direct execution from any working directory.
sys.path.insert(0, str(ROOT))
from tests.sibling_gap_support import (  # noqa: E402
    Fixture,
    load_functions,
    load_solver,
    spec,
)

SOURCE = "schedule/disperse_siblings.py"


def mixed_fuzz(count, sample):
    """Generate windows with production get_due_range, outside the timed loop."""
    rng = Random(10000 * count + sample)
    ns = load_functions()
    specs = []
    for cid in range(count):
        stability = rng.randint(7, 180)
        last = -rng.randint(0, min(20, stability - 3))
        last_interval = rng.randint(1, max(1, stability // 2))
        specs.append(spec(cid + 1, last, stability, last_interval))
    fixture = Fixture(ns, specs)
    try:
        rows = ns["get_siblings"]()[1]
        windows = {}
        reviews = []
        for cid, _, stability, due, retention, maximum in rows:
            window, last = ns["get_due_range"](cid, stability, due, retention, maximum)
            windows[cid] = window
            reviews.append(last)
        latest = max(reviews)
        windows[-1] = (latest, latest)
        return windows
    finally:
        fixture.sql.close()


def workloads():
    for count in (2, 5, 10, 20, 100):
        yield (
            "mixed_fuzz",
            count,
            [mixed_fuzz(count, sample) for sample in range(20)],
            None,
        )
    for count in (2, 10, 100, 1000, 3000):
        nested = {i: (i, 4 * count - i) for i in range(count)}
        nested[-1] = (0, 0)
        yield "nested", count, [nested], 4
        waiting = {-1: (-3, -3)}
        for i in range(count // 2):
            waiting[2 * i] = (4 * i, 4 * i + 3)
            waiting[2 * i + 1] = (4 * i + 1, 4 * i + 1)
        yield "requires_forbidden_regions", count, [waiting], 2


def check_result(windows, result):
    score, dates = result
    assert set(dates) == set(windows)
    assert all(left <= dates[k] <= right for k, (left, right) in windows.items())
    ordered = sorted(dates.values())
    assert score == min(b - a for a, b in zip(ordered, ordered[1:]))


def profile_checks(ns, cases):
    """Instrument a separate untimed pass; restore functions before timing."""
    stats = dict(candidate_checks=0, exact_checks=0, bisect_left_calls=0)
    original_place = ns["_place_siblings_with_gap"]
    original_bisect = ns["bisect_left"]

    def counted_bisect(*args):
        stats["bisect_left_calls"] += 1
        return original_bisect(*args)

    def counted_place(*args):
        stats["candidate_checks"] += 1
        before = stats["bisect_left_calls"]
        result = original_place(*args)
        stats["exact_checks"] += stats["bisect_left_calls"] > before
        return result

    ns["_place_siblings_with_gap"] = counted_place
    ns["bisect_left"] = counted_bisect
    try:
        for windows in cases:
            ns["maximize_siblings_due_gap"](windows)
    finally:
        ns["_place_siblings_with_gap"] = original_place
        ns["bisect_left"] = original_bisect
    return stats


def timed_batch(solver, cases, loops):
    gc_enabled = gc.isenabled()
    gc.disable()
    try:
        start = perf_counter_ns()
        for _ in range(loops):
            for windows in cases:
                solver(windows)
        return perf_counter_ns() - start
    finally:
        if gc_enabled:
            gc.enable()


def calibrate(solver, cases):
    loops = 1
    while timed_batch(solver, cases, loops) < 20_000_000 and loops < 65536:
        loops *= 2
    return loops


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--baseline",
        required=True,
        help="Local Git revision to compare with the working-tree solver (e.g. HEAD)",
    )
    parser.add_argument("--repeats", type=int, default=7)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.repeats < 1:
        parser.error("--repeats must be positive")
    baseline_commit = subprocess.check_output(
        ["git", "rev-parse", args.baseline], cwd=ROOT, text=True
    ).strip()
    old_source = subprocess.check_output(
        ["git", "show", f"{baseline_commit}:{SOURCE}"], cwd=ROOT, text=True
    )
    new_source = (ROOT / SOURCE).read_text()
    namespaces = {"old": load_solver(old_source), "new": load_solver(new_source)}
    solvers = {name: ns["maximize_siblings_due_gap"] for name, ns in namespaces.items()}
    results = {
        "metadata": {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "python": platform.python_version(),
            "platform": platform.platform(),
            "cpu": (
                subprocess.check_output(
                    ["sysctl", "-n", "machdep.cpu.brand_string"], text=True
                ).strip()
                if platform.system() == "Darwin"
                else platform.processor() or platform.machine()
            ),
            "baseline_commit": baseline_commit,
            "old_source_sha256": hashlib.sha256(old_source.encode()).hexdigest(),
            "new_source_sha256": hashlib.sha256(new_source.encode()).hexdigest(),
            "repeats": args.repeats,
            "timing": "Single process; warm/calibrate to >=20ms per batch; alternating old/new order; GC disabled only during timing; median per-note batch mean.",
            "scope": "Pure maximize_siblings_due_gap, including sorting and postprocessing. Excludes loading code, generating windows, instrumentation, validation, SQLite, Anki and UI.",
        },
        "results": [],
    }
    for shape, count, cases, expected in workloads():
        scores = {}
        for name, solver in solvers.items():
            scores[name] = []
            for windows in cases:
                result = solver(windows)
                check_result(windows, result)
                scores[name].append(result[0])
                if name == "new" and expected is not None:
                    assert result[0] == expected
        assert all(new >= old for old, new in zip(scores["old"], scores["new"]))
        profile = profile_checks(namespaces["new"], cases)
        loops = {name: calibrate(solver, cases) for name, solver in solvers.items()}
        samples = {"old": [], "new": []}
        for repeat in range(args.repeats):
            order = ("old", "new") if repeat % 2 == 0 else ("new", "old")
            for name in order:
                elapsed = timed_batch(solvers[name], cases, loops[name])
                samples[name].append(elapsed / (loops[name] * len(cases)) / 1000)
        medians = {name: statistics.median(values) for name, values in samples.items()}
        row = {
            "shape": shape,
            "siblings": count,
            "notes_per_batch": len(cases),
            "old_median_us": medians["old"],
            "new_median_us": medians["new"],
            "new_over_old": medians["new"] / medians["old"],
            "old_gaps": scores["old"],
            "new_gaps": scores["new"],
            "notes_improved": sum(
                new > old for old, new in zip(scores["old"], scores["new"])
            ),
            "new_check_profile": profile,
            "loops_per_sample": loops,
            "samples_us": samples,
        }
        results["results"].append(row)
        print(
            f"{shape:28s} n={count:4d} old={medians['old']:10.3f} us "
            f"new={medians['new']:10.3f} us ratio={row['new_over_old']:7.2f} "
            f"improved={row['notes_improved']}/{len(cases)} "
            f"exact_checks={profile['exact_checks']}/{profile['candidate_checks']}",
            flush=True,
        )
    args.output.write_text(json.dumps(results, indent=2) + "\n")
    print(f"Saved {args.output}")


if __name__ == "__main__":
    main()
