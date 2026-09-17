"""Exact-oracle and simulated Anki regressions; standard library only.

Run from the repository root: python -m unittest discover -s tests -v
"""

import itertools
import random
import unittest
from pathlib import Path
from unittest.mock import patch

from tests.sibling_gap_support import (
    Fixture,
    brute_force,
    load_functions,
    load_solver,
    spec,
)


def permutation_optimum(windows):
    """Independent oracle for wider windows without enumerating every day.

    For each ordering, every pair a < b imposes
    gap <= (right[b] - left[a]) // (b - a). Enumerate all orderings.
    """
    return max(
        min(
            (order[b][1] - order[a][0]) // (b - a)
            for b in range(1, len(order))
            for a in range(b)
        )
        for order in itertools.permutations(windows)
    )


class DisperseSiblingsTests(unittest.TestCase):
    def setUp(self):
        self.functions = load_functions()
        self.solve = self.functions["maximize_siblings_due_gap"]
        self.place = self.functions["_place_siblings_with_gap"]

    def assert_arrangement(self, windows, dates, expected_gap):
        self.assertEqual(set(dates), set(windows))
        for cid, (left, right) in windows.items():
            self.assertLessEqual(left, dates[cid])
            self.assertLessEqual(dates[cid], right)
        ordered = sorted(dates.values())
        actual = min((b - a for a, b in zip(ordered, ordered[1:])), default=0)
        self.assertEqual(actual, expected_gap)

    def test_real_window_and_writeback_regressions(self):
        cases = [
            ([spec(1, 0, 2, 1), spec(2, -4, 5, 1)], 1),
            ([spec(1, -9, 14, 7), spec(2, -49, 52, 30)], 7),
            ([spec(1, 0, 29, 28, maximum=29), spec(2, -255, 270, 200, deck=2)], 14),
            ([spec(cid, 0, 30, 10) for cid in (1, 2, 3)], 3),
        ]
        for inputs, expected in cases:
            with self.subTest(inputs=inputs):
                fixture = Fixture(self.functions, inputs)
                self.addCleanup(fixture.sql.close)
                result = fixture.evaluate()
                self.assertEqual(result["optimal_gap"], expected)
                self.assertEqual(result["reported_gap"], expected)
                self.assertEqual(result["written_gap"], expected)
                self.assertEqual(result["written"], result["planned"])

    def test_all_original_3375_profiles(self):
        intervals = [(left, right) for left in range(5) for right in range(left, 5)]
        for profile in itertools.product(intervals, repeat=3):
            windows = {**dict(enumerate(profile, start=1)), -1: (0, 0)}
            expected, _ = brute_force(windows)
            actual, dates = self.solve(windows)
            self.assertEqual(actual, expected, windows)
            self.assert_arrangement(windows, dates, expected)

    def test_exhaustive_unanchored_windows_and_feasibility(self):
        for count, last_day in ((3, 5), (4, 4)):
            intervals = [
                (left, right)
                for left in range(last_day + 1)
                for right in range(left, last_day + 1)
            ]
            for profile in itertools.product(intervals, repeat=count):
                windows = dict(enumerate(profile))
                expected, _ = brute_force(windows)
                actual, dates = self.solve(windows)
                self.assertEqual(actual, expected, windows)
                self.assert_arrangement(windows, dates, expected)
                # Check the feasibility oracle itself on BOTH sides of the
                # optimum, not just the gap selected by binary search.
                for candidate_gap in range(expected + 2):
                    placed = self.place(profile, candidate_gap)
                    self.assertEqual(
                        placed is not None,
                        candidate_gap <= expected,
                        (windows, candidate_gap),
                    )
                    if placed is not None:
                        for date, (left, right) in zip(placed, profile):
                            self.assertLessEqual(left, date)
                            self.assertLessEqual(date, right)
                        ordered = sorted(placed)
                        self.assertTrue(
                            all(
                                b - a >= candidate_gap
                                for a, b in zip(ordered, ordered[1:])
                            )
                        )
                    if candidate_gap > 0:
                        # Exercise the exact algorithm even when the greedy
                        # shortcut would succeed, so it cannot mask defects.
                        order = sorted(
                            range(count),
                            key=lambda i: (profile[i][0], profile[i][1], i),
                        )
                        regions = self.functions["_sibling_forbidden_regions"](
                            profile, candidate_gap, order
                        )
                        self.assertEqual(
                            regions is not None,
                            candidate_gap <= expected,
                            (windows, candidate_gap),
                        )
                        if regions is not None:
                            exact = self.functions["_dispatch_sibling_points"](
                                profile, candidate_gap, order, *regions
                            )
                            self.assertIsNotNone(
                                exact, (windows, candidate_gap, regions)
                            )
                            for date, (left, right) in zip(exact, profile):
                                self.assertLessEqual(left, date)
                                self.assertLessEqual(date, right)
                            ordered = sorted(exact)
                            self.assertTrue(
                                all(
                                    b - a >= candidate_gap
                                    for a, b in zip(ordered, ordered[1:])
                                )
                            )

    def test_seeded_wide_windows_against_permutations(self):
        rng = random.Random(20260916)
        for _ in range(120):
            count = rng.randrange(2, 8)
            profile = [
                tuple(sorted((rng.randrange(-30, 61), rng.randrange(-30, 61))))
                for _ in range(count)
            ]
            if rng.randrange(2):
                i = rng.randrange(count)
                profile[i] = (profile[i][0], profile[i][0])
            expected = permutation_optimum(profile)
            windows = dict(enumerate(profile))
            actual, dates = self.solve(windows)
            self.assertEqual(actual, expected, windows)
            self.assert_arrangement(windows, dates, expected)
            self.assertIsNone(self.place(profile, expected + 1))

    def test_waiting_for_a_narrow_window(self):
        # Dispatching the available wide card at 0 misses the fixed card at 1.
        # The exact check must forbid starting at 0, then place at 1 and 3.
        windows = {-1: (-3, -3), 1: (0, 3), 2: (1, 1)}
        actual, dates = self.solve(windows)
        self.assertEqual(actual, 2)
        self.assertEqual(dates, {-1: -3, 1: 3, 2: 1})
        self.assertIsNone(self.place(list(windows.values()), 3))

    def test_order_invariance_and_date_translation(self):
        windows = {-1: (-9, -9), 1: (3, 7), 2: (0, 8), 3: (10, 15)}
        expected = self.solve(windows)
        for items in itertools.permutations(windows.items()):
            self.assertEqual(self.solve(dict(items)), expected)
        for offset in (-(10**30), -1000, 1000, 10**12, 10**30):
            shifted = {
                cid: (left + offset, right + offset)
                for cid, (left, right) in windows.items()
            }
            actual, dates = self.solve(shifted)
            self.assertEqual(actual, expected[0])
            self.assertEqual(dates, {cid: d + offset for cid, d in expected[1].items()})

    def test_large_gap_counterexample_family(self):
        for m in (4, 10, 30, 100, 36500, 10**9, 10**20):
            windows = {-1: (0, 0), 1: (m, m), 2: (0, m + 1)}
            actual, dates = self.solve(windows)
            self.assertEqual(actual, m // 2)
            self.assert_arrangement(windows, dates, m // 2)

    def test_large_nested_note(self):
        count = 1000
        windows = {i: (i, 4 * count - i) for i in range(count)}
        windows[-1] = (0, 0)
        actual, dates = self.solve(windows)
        # The total span bounds the minimum gap by 4, so this also proves
        # optimality independently of the production feasibility check.
        self.assertEqual(actual, 4)
        self.assert_arrangement(windows, dates, 4)

    def test_large_note_requiring_forbidden_regions(self):
        windows = {-1: (-3, -3)}
        for i in range(500):
            windows[2 * i] = (4 * i, 4 * i + 3)
            windows[2 * i + 1] = (4 * i + 1, 4 * i + 1)
        actual, dates = self.solve(windows)
        # Greedy puts the first wide card at 0 and misses the fixed card at 1.
        # The total span bounds the gap by floor(2002 / 1000) = 2.
        self.assertEqual(actual, 2)
        self.assert_arrangement(windows, dates, 2)

    def test_empty_singleton_duplicate_and_disjoint_windows(self):
        for windows, expected in (
            ({}, 0),
            ({1: (-3, 7)}, 0),
            ({1: (2, 2), 2: (2, 2)}, 0),
            ({1: (-8, -5), 2: (4, 8), 3: (20, 20)}, 14),
        ):
            actual, dates = self.solve(windows)
            self.assertEqual(actual, expected)
            self.assert_arrangement(windows, dates, expected)

    def test_list_helper_preserves_input_and_card_mapping(self):
        windows = [(3, 7), (-9, -9), (0, 8)]
        original = windows.copy()
        actual, dates = self.functions["find_max_min_gap_and_arrangement"](windows)
        self.assertEqual(windows, original)
        self.assertEqual(actual, 7)
        self.assert_arrangement(dict(enumerate(windows)), dict(enumerate(dates)), 7)

    def test_random_feasible_windows_against_previous_exact_solver(self):
        source = Path(__file__).with_name("sibling_gap_reference.py").read_text()
        reference = load_solver(source)["_place_siblings_with_gap"]
        rng = random.Random(20261001)
        for _ in range(2000):
            count = rng.randrange(2, 81)
            gap = rng.randrange(2, 201)
            date = rng.randrange(-1000, 1000)
            windows = []
            for i in range(count):
                date += gap + rng.randrange(gap)
                windows.append(
                    (date - rng.randrange(3 * gap), date + rng.randrange(3 * gap))
                )
            rng.shuffle(windows)
            for candidate in (gap, gap + 1, 2 * gap):
                expected = reference(windows, candidate)
                actual = self.place(windows, candidate)
                self.assertEqual(actual is None, expected is None, (windows, candidate))
                if actual is not None:
                    for point, (left, right) in zip(actual, windows):
                        self.assertLessEqual(left, point)
                        self.assertLessEqual(point, right)
                    dates = sorted(actual)
                    self.assertTrue(
                        all(b - a >= candidate for a, b in zip(dates, dates[1:]))
                    )

    def test_fenwick_ranks_after_deletions(self):
        tree_type = self.functions["_GapFenwickTree"]
        rng = random.Random(4)
        for size in (1, 2, 7, 32, 127):
            tree = tree_type(size, full=True)
            remaining = list(range(size))
            while remaining:
                for rank, index in enumerate(remaining, start=1):
                    self.assertEqual(tree.select(rank), index)
                self.assertEqual(tree.select(len(remaining) + 1), size)
                for end in range(size + 1):
                    self.assertEqual(
                        tree.prefix_sum(end), sum(i < end for i in remaining)
                    )
                index = rng.choice(remaining)
                remaining.remove(index)
                tree.add(index, -1)
            self.assertEqual(tree.select(1), size)

    def test_pseudo_offsets_match_individual_updates(self):
        rng = random.Random(2718)
        offsets_type = self.functions["_GapOffsets"]
        for gap in (2, 3, 7, 31, 10**18 + 3):
            deadlines = sorted(rng.randrange(1, 10 * gap) for _ in range(150))
            offsets = offsets_type(deadlines, gap)
            expected = {}
            pending = list(range(len(deadlines)))
            rng.shuffle(pending)
            while pending:
                for _ in range(min(3, len(pending))):
                    index = pending.pop()
                    offsets.activate(index, deadlines[index])
                    expected[index] = 0
                representative = rng.choice(list(expected))
                target = (deadlines[representative] - expected[representative]) % gap
                start = -20 * gap + target
                end = start + rng.randrange(1, gap + 1)
                # Independently test membership in the open cyclic arc by
                # its positive distance from the target; both ends are legal.
                for index in expected:
                    phase = (deadlines[index] - expected[index]) % gap
                    distance = (phase - target) % gap
                    if 0 < distance < end - start:
                        expected[index] += distance
                offsets.forbid(start, end)
                for index, value in expected.items():
                    self.assertEqual(offsets.offset(index), value)
                    # Union by size bounds path depth even without compression.
                    depth = 0
                    node = index
                    while offsets.parents[node] != node:
                        node = offsets.parents[node]
                        depth += 1
                    self.assertLessEqual(depth, len(expected).bit_length())

    def test_exact_checker_uses_linearly_many_tree_operations(self):
        tree_type = self.functions["_GapFenwickTree"]
        originals = {
            name: getattr(tree_type, name) for name in ("add", "prefix_sum", "select")
        }
        calls = [0]

        def counted(name):
            def invoke(tree, *args):
                calls[0] += 1
                return originals[name](tree, *args)

            return invoke

        with (
            patch.object(tree_type, "add", counted("add")),
            patch.object(tree_type, "prefix_sum", counted("prefix_sum")),
            patch.object(tree_type, "select", counted("select")),
        ):
            for size in (100, 1000, 3000):
                points = [(-3, -3)]
                for i in range(size // 2):
                    points.extend(((4 * i, 4 * i + 3), (4 * i + 1, 4 * i + 1)))
                calls[0] = 0
                order = sorted(range(len(points)), key=lambda i: points[i])
                regions = self.functions["_sibling_forbidden_regions"](points, 2, order)
                self.assertIsNotNone(regions)
                self.assertGreater(calls[0], size)
                # Each tree operation is logarithmic; deleted deadlines and
                # merged residues are never revisited as separate entries.
                self.assertLess(calls[0], 20 * len(points))


if __name__ == "__main__":
    unittest.main()
