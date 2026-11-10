Sibling dispersion chooses one integer due date inside each card's allowed
window and maximizes the minimum distance between the chosen dates. The most
recent review date is included as a fixed point. Card order is not prescribed:
nested windows can require exchanging the order of cards.

The production implementation is in
[schedule/disperse_siblings.py](../schedule/disperse_siblings.py). Its feasibility
check follows Algorithm B of
[Garey, Johnson, Simons and Tarjan (1981)](https://doi.org/10.1137/0210018).
A point in `[L, R]` becomes a task of length `g`, released at `L` and required to
finish by `R + g`. Non-overlapping tasks correspond exactly to points separated
by at least `g`.

**Correctness and complexity.** For a candidate gap, earliest-deadline dispatch
is tried first. Success is a feasible witness. When both endpoints are ordered,
an exchange argument makes failure conclusive. Otherwise, Algorithm B constructs
forbidden start regions before dispatching again; ordinary greedy failure alone
does not prove infeasibility.

The exact check maintains three kinds of state:

- A Fenwick tree counts processed tasks by deadline. Prefix sums give each
  deadline's load without individually updating every affected deadline.
- A Fenwick tree and predecessor links track relevant deadlines. A deadline
  dominated by a later deadline can be removed permanently, as in Lemmas 5 and 6
  of the paper.
- A weighted forest groups pseudo-offsets by `(deadline - offset) % g`. Union by
  size bounds path length by `O(log n)` without requiring path compression.

For a pseudo-critical time `c = D - g * load - offset`, a new forbidden open
region starts at `a = c - g`. Its target residue `a % g` is already represented
by the deadline attaining `c`. That deadline has positive load and `D > c`, so
it is activated before the region is applied. Consequently, all residues can be
compressed from the initial `D % g` values; updates merge groups and never split
existing members. Integer forbidden regions are `[a + 1, b - 1]`: both endpoints
of the corresponding open interval remain legal starts.

Each deadline is activated and removed at most once, and there are only `O(n)`
group insertions and merges. Tree operations cost `O(log n)`. Regions are appended
right-to-left and reversed once, avoiding repeated list insertion at the front.
One exact feasibility check therefore takes `O(n log n)` time and `O(n)` space.
Binary search over integer gaps gives `O(n log n log(W + 2))` total time, where
`W` is the total date span and `n` includes the fixed historical point. The final
rightward adjustment uses the computed point order and preserves the optimal gap.

**Regression tests.** Run from the repository root:

```sh
python -m unittest discover -s tests -v
```

[tests/sibling_gap_support.py](../tests/sibling_gap_support.py) loads production
definitions by AST, so tests do not require Anki or Qt. It also provides an
in-memory SQLite collection, copied card objects and synthetic review logs.
These fixtures exercise window generation, SQL selection and date writes; they
do not replace testing inside a running Anki application.

The suite compares against exhaustive integer-date search, a permutation oracle
and an independent quadratic exact checker in
[tests/sibling_gap_reference.py](../tests/sibling_gap_reference.py). That reference
is stored in the repository, so tests work in a shallow checkout. Coverage also
includes forced exact checks that bypass the greedy shortcut, weighted-offset
updates, deadline rank queries, input-order and translation invariance, and a
bound on the number of tree operations. Only standard-library modules are used.

**Benchmarking.** Compare any locally available Git revision with the working
tree, using the same workload for both solvers:

```sh
python scripts/benchmark_sibling_disperse.py --baseline HEAD --output /tmp/sibling-benchmark.json
```

Choose an earlier local revision instead of `HEAD` when measuring a committed
change. The script requires an explicit baseline; historical revisions are not
needed by the regression tests. Results include source hashes, repeated timing
samples and solution gaps. Timings cover sorting, feasibility checks and final
adjustment, and exclude collection I/O, window generation and validation. Keep
generated JSON results outside the source tree. Tests, benchmarks and this
document are excluded from the add-on package by the packaging allowlist.

**Separate follow-up issues.** These are outside the core max-min solver:

- With no usable review logs, `update_card_due_ivl()` changes `ivl` before the
  fallback computation `last_review = due - ivl`. This can cancel the requested
  due-date change. Preserve the previous review date before changing `ivl` when
  addressing this writeback issue.
- Deck-scoped selection may omit siblings in other decks. For example, moving
  a selected card from day 30 to day 33 can collide with an omitted sibling
  already fixed at day 33. Treating omitted siblings as fixed constraints would
  preserve the write scope while accounting for the entire note.
- If an unavoidable collision makes the optimal minimum gap zero, this objective
  alone cannot distinguish additional avoidable collisions. A secondary spacing
  objective requires its own specification and tests.
