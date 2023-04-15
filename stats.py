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


def retention_stability_burden() -> float:
    today = mw.col.sched.today
    last_due_and_custom_data_and_ivl_rows = mw.col.db.all("select due - ivl, data, ivl from cards where queue = 2 and data like '%\"cd\"%'")
    delay_stability_ivl_list = map(lambda x: (today - x[0], json.loads(json.loads(x[1])['cd'])['s'], x[2]), last_due_and_custom_data_and_ivl_rows)
    retention_stability_burden_list = list(map(lambda x: (math.pow(0.9, x[0] / x[1]), x[1], 1/x[2]), delay_stability_ivl_list))
    recall_sum = sum(item[0] for item in retention_stability_burden_list)
    stability_sum = sum(item[1] for item in retention_stability_burden_list)
    burden_sum = sum(item[2] for item in retention_stability_burden_list)
    cnt = len(retention_stability_burden_list)
    return recall_sum / cnt, stability_sum / cnt, burden_sum, cnt


def todayStats_new(self):
    i = []
    retention, stability, burden, count = retention_stability_burden()
    _line_now(self, i, "average retention", f"{retention * 100: .2f}%")
    _line_now(self, i, "average stability", f"{int(stability)}")
    _line_now(self, i, "total burden", f"{burden: .2f}")
    _line_now(self, i, "count", f"{count}")
    return todayStats_old(self) + "<br><br><table style='text-align: center'><tr><td style='padding: 5px'>" \
        + "<h2>FSRS Stats</h2>" + _lineTbl_now(self, i) + "</td></tr></table>"


def init_stats():
    anki.stats.CollectionStats.todayStats = todayStats_new
