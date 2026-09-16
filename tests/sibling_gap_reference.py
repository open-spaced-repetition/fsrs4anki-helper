"""Independent quadratic oracle, preserved from commit f0c58df.

This test-only copy does not import the optimized solver. Keeping the reference
here also allows CI to run from a shallow checkout without Git history.
"""

from bisect import bisect_left, bisect_right
from heapq import heappop, heappush


def _place_siblings_with_gap(points, min_gap):
    """Find a feasible arrangement in any order, or return None.

    Treat a point in [L, R] as a job of length min_gap with release L and
    completion deadline R + min_gap. Earliest-deadline dispatch is sufficient
    after excluding forbidden start regions (Garey et al., 1981;
    https://doi.org/10.1137/0210018). See also the integer formulation in
    Artiouchine and Baptiste, section 3: https://doi.org/10.1007/s10601-006-9009-1.

    Incremental backward scheduling computes these regions in O(n^2 log n)
    time and O(n) space. A successful greedy pass skips that work entirely.
    """
    if not points or min_gap == 0:
        return [left for left, _ in points]

    release_order = sorted(
        range(len(points)), key=lambda i: (points[i][0], points[i][1], i)
    )

    def dispatch(forbidden_starts, forbidden_ends):
        ready = []
        pending = 0
        date = points[release_order[0]][0]
        arrangement = [0] * len(points)
        for _ in points:
            if not ready:
                date = max(date, points[release_order[pending]][0])
            region = bisect_right(forbidden_starts, date) - 1
            if region >= 0 and date <= forbidden_ends[region]:
                date = forbidden_ends[region] + 1
            while pending < len(points) and points[release_order[pending]][0] <= date:
                i = release_order[pending]
                left, right = points[i]
                heappush(ready, (right, left, i))
                pending += 1
            right, _, i = heappop(ready)
            if date > right:
                return None
            arrangement[i] = date
            date += min_gap
        return arrangement

    arrangement = dispatch([], [])
    if arrangement is not None:
        return arrangement

    # Inclusive forbidden integer regions, sorted and merged. No feasible
    # arrangement may put ANY point in these regions, regardless of its ID.
    forbidden_starts = []
    forbidden_ends = []
    deadlines = sorted({right for _, right in points})
    latest_starts = [right + min_gap for right in deadlines]
    first_active = len(deadlines)
    pending = len(points) - 1
    while pending >= 0:
        release = points[release_order[pending]][0]
        while pending >= 0 and points[release_order[pending]][0] == release:
            _, right = points[release_order[pending]]
            first_deadline = bisect_left(deadlines, right)
            first_active = min(first_active, first_deadline)
            # For each deadline, add this job to the set of jobs released at
            # or after 'release' that must finish by that deadline. Pack that
            # set backwards, skipping forbidden starts. Previously packed
            # jobs remain valid: new regions end before their release dates.
            for j in range(first_deadline, len(deadlines)):
                date = latest_starts[j] - min_gap
                region = bisect_right(forbidden_starts, date) - 1
                if region >= 0 and date <= forbidden_ends[region]:
                    date = forbidden_starts[region] - 1
                latest_starts[j] = date
            pending -= 1

        latest_start = min(latest_starts[first_active:])
        if latest_start < release:
            return None

        # A point starting here would prevent a constrained set from starting
        # by its latest feasible start. Integer endpoints are inclusive.
        lower = latest_start - min_gap + 1
        upper = release - 1
        if lower <= upper:
            # Releases decrease, so a new region can only touch the leftmost
            # existing region. Merge adjacent regions as well as overlaps.
            if forbidden_starts and upper >= forbidden_starts[0] - 1:
                forbidden_starts[0] = min(forbidden_starts[0], lower)
            else:
                forbidden_starts.insert(0, lower)
                forbidden_ends.insert(0, upper)

    return dispatch(forbidden_starts, forbidden_ends)
