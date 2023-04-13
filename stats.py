import anki.stats
from datetime import datetime
import math
from .utils import *

todayStats_old = anki.stats.CollectionStats.todayStats


def _line_now(self, i, a, b, bold=True):
    colon = _(":")
    if bold:
        i.append(("<tr><td align=right>%s%s</td><td><b>%s</b></td></tr>") % (a,colon,b))
    else:
        i.append(("<tr><td align=right>%s%s</td><td>%s</td></tr>") % (a,colon,b))


def _lineTbl_now(self, i):
    return "<table>" + "".join(i) + "</table>"


def average_retention() -> float:
    today = mw.col.sched.today
    last_due_and_custom_data_rows = mw.col.db.all("select due - ivl, data from cards where queue = 2 and data != '{}'")
    ivl_and_stability_list = map(lambda x: (today - x[0], json.loads(json.loads(x[1])['cd'])['s']), last_due_and_custom_data_rows)
    recall_list = list(map(lambda x: math.pow(0.9, x[0] / x[1]), ivl_and_stability_list))
    return sum(recall_list) / len(recall_list)


def todayStats_new(self):
    i = []
    _line_now(self, i, "average retention", average_retention())
    return todayStats_old(self) + "<br><br><table style='text-align: center'><tr><td style='padding: 5px'>" \
        + "<h2>FSRS Stats</h2>" + _lineTbl_now(self, i) + "</td></tr></table>"


def init_stats():
    anki.stats.CollectionStats.todayStats = todayStats_new