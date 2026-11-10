"""Shared support for sibling-gap tests and developer benchmarks.

Only standard-library dependencies are required. Production definitions are
loaded by AST to avoid starting Anki/Qt; the solver itself is never copied here.
The collection fixture uses SQLite, copied cards and synthetic review logs.
"""

import ast
import copy
import itertools
import json
import math
import sqlite3
from bisect import bisect_left, bisect_right
from heapq import heappop, heappush
from pathlib import Path
from types import SimpleNamespace as NS

ROOT = Path(__file__).resolve().parents[1]
TODAY = 1000
SOLVER_NAMES = {
    "maximize_siblings_due_gap",
    "find_max_min_gap_and_arrangement",
    "_place_siblings_with_gap",
    "_dispatch_sibling_points",
    "_sibling_forbidden_regions",
    "_GapFenwickTree",
    "_GapOffsets",
}
SOURCES = {
    "utils.py": {
        "get_revlogs",
        "filter_revlogs",
        "get_last_review_date_and_interval",
        "update_card_due_ivl",
        "get_fuzz_range",
        "next_interval",
        "get_decay",
        "get_dr",
        "write_custom_data",
        "FUZZ_RANGES",
        "DECAY",
    },
    "schedule/disperse_siblings.py": SOLVER_NAMES
    | {
        "get_siblings",
        "get_due_range",
        "disperse",
        "disperse_siblings_background",
    },
}


def _namespace():
    return {
        "math": math,
        "json": json,
        "Dict": dict,
        "Tuple": tuple,
        "Card": object,
        "List": list,
        "DeckManager": object,
        "CardStatsResponse": NS(StatsRevlogEntry=object),
        "REVLOG_CRAM": 3,
        "ids2str": lambda ids: "(" + ",".join(map(str, ids)) + ")",
        "t": lambda key, **kwargs: key,
        "bisect_left": bisect_left,
        "bisect_right": bisect_right,
        "heappop": heappop,
        "heappush": heappush,
    }


def _load_definitions(source, filename, names, namespace):
    tree = ast.parse(source)
    nodes = [
        node
        for node in tree.body
        if (isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name in names)
        or (
            isinstance(node, ast.Assign)
            and any(
                isinstance(target, ast.Name) and target.id in names
                for target in node.targets
            )
        )
    ]
    exec(compile(ast.Module(body=nodes, type_ignores=[]), filename, "exec"), namespace)


def load_functions():
    """Load production scheduling functions with simulated Anki names."""
    namespace = _namespace()
    for filename, names in SOURCES.items():
        _load_definitions((ROOT / filename).read_text(), filename, names, namespace)
    return namespace


def load_solver(source):
    """Load a pure solver from current, historical or reference source text."""
    namespace = _namespace()
    _load_definitions(source, "schedule/disperse_siblings.py", SOLVER_NAMES, namespace)
    return namespace


def gap(dates):
    ordered = sorted(dates.values())
    return min(b - a for a, b in zip(ordered, ordered[1:]))


def brute_force(windows, fixed_order=None):
    keys = list(windows)
    best = -1
    arrangement = None
    for values in itertools.product(
        *(range(windows[k][0], windows[k][1] + 1) for k in keys)
    ):
        dates = dict(zip(keys, values))
        if fixed_order is not None and any(
            dates[a] > dates[b] for a, b in zip(fixed_order, fixed_order[1:])
        ):
            continue
        candidate = gap(dates)
        if candidate > best:
            best, arrangement = candidate, dates
    return best, arrangement


def spec(
    cid, last, stability, last_interval=0, due=None, logs=True, deck=1, maximum=36500
):
    return dict(
        cid=cid,
        last=last,
        stability=stability,
        last_interval=last_interval,
        due=due,
        logs=logs,
        deck=deck,
        maximum=maximum,
    )


class Fixture:
    def __init__(self, ns, specs):
        self.ns = ns
        self.specs = specs
        self.cards = {}
        self.logs = {}
        self.configs = {}
        self.sql = sqlite3.connect(":memory:")
        self.sql.execute("""CREATE TABLE cards (
            id INTEGER PRIMARY KEY, nid INTEGER, did INTEGER, odid INTEGER,
            type INTEGER, queue INTEGER, data TEXT, due INTEGER, odue INTEGER
        )""")
        for s in specs:
            cid = s["cid"]
            due = s["due"]
            if due is None:
                due = s["last"] + min(
                    ns["next_interval"](s["stability"], 0.9, -0.5), s["maximum"]
                )
            self.cards[cid] = NS(
                id=cid,
                nid=1,
                did=s["deck"],
                ivl=due - s["last"],
                due=TODAY + due,
                odid=0,
                odue=0,
                decay=0.5,
                custom_data="",
            )
            self.logs[cid] = (
                [
                    NS(
                        button_chosen=3,
                        review_kind=1,
                        time=(TODAY + s["last"]) * 86400 + 43200,
                        last_interval=s["last_interval"] * 86400,
                    )
                ]
                if s["logs"]
                else []
            )
            config = {"desiredRetention": 0.9, "rev": {"maxIvl": s["maximum"]}}
            assert s["deck"] not in self.configs or self.configs[s["deck"]] == config
            self.configs[s["deck"]] = config
            self.sql.execute(
                "INSERT INTO cards VALUES (?,1,?,0,2,2,?,?,0)",
                (cid, s["deck"], json.dumps({"s": s["stability"]}), TODAY + due),
            )

        def noop(*args, **kwargs):
            pass

        col = NS(
            sched=NS(today=TODAY, day_cutoff=(TODAY + 1) * 86400),
            db=NS(all=lambda query: self.sql.execute(query).fetchall()),
            decks=NS(
                deck_and_child_ids=lambda did: [did],
                get=lambda did: {},
                config_dict_for_deck_id=lambda did: self.configs[did],
            ),
            get_card=lambda cid: copy.deepcopy(self.cards[cid]),
            get_review_logs=lambda cid: copy.deepcopy(self.logs[cid]),
            update_cards=self.update_cards,
            add_custom_undo_entry=lambda label: 1,
            merge_undo_entries=noop,
        )
        ns["mw"] = NS(
            col=col,
            taskman=NS(run_on_main=lambda callback: callback()),
            progress=NS(start=noop, update=noop, want_cancel=lambda: False),
        )

    def update_cards(self, cards):
        for card in cards:
            self.cards[card.id] = copy.deepcopy(card)
            self.sql.execute("UPDATE cards SET due=? WHERE id=?", (card.due, card.id))

    def dates(self):
        return {cid: card.due - TODAY for cid, card in self.cards.items()}

    def evaluate(self, did=None):
        before = self.dates()
        selected = self.ns["get_siblings"](did)[1]
        planned, windows, reported_gap = self.ns["disperse"](selected)
        planned = {cid: due - TODAY for cid, due in planned.items()}
        windows = {
            cid: (left - TODAY, right - TODAY) for cid, (left, right) in windows.items()
        }
        # Cards outside a requested deck cannot move, but remain siblings.
        evaluation_windows = dict(windows)
        for cid, due in before.items():
            evaluation_windows.setdefault(cid, (due, due))
        optimum, best_dates = brute_force(evaluation_windows)
        self.ns["disperse_siblings_background"](did)
        actual = self.dates()
        anchor = windows[-1][0]
        return {
            "inputs": self.specs,
            "selected_ids": [row[0] for row in selected],
            "windows_including_fixed_omitted_siblings": evaluation_windows,
            "before": before,
            "before_gap": gap({-1: anchor, **before}),
            "planned": planned,
            "reported_gap": reported_gap,
            "written": actual,
            "written_gap": gap({-1: anchor, **actual}),
            "written_intervals": {cid: c.ivl for cid, c in self.cards.items()},
            "optimal_gap": optimum,
            "optimal_dates": best_dates,
        }
