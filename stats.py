import anki.stats
import math
from .utils import *

todayStats_old = anki.stats.CollectionStats.todayStats


def _line_now(i, a, b, bold=True):
    colon = _(":")
    if bold:
        i.append(("<tr><td align=right>%s%s</td><td><b>%s</b></td></tr>") % (a,colon,b))
    else:
        i.append(("<tr><td align=right>%s%s</td><td>%s</td></tr>") % (a,colon,b))


def _lineTbl_now(i):
    return "<table>" + "".join(i) + "</table>"


def retention_stability_burden(lim) -> float:
    today = mw.col.sched.today
    last_due_and_custom_data_and_ivl_rows = mw.col.db.all("""
    SELECT CASE WHEN odid==0 
        THEN due - ivl
        ELSE odue - ivl
        END
        ,data
        ,ivl 
    FROM cards 
    WHERE queue >= 1 
    AND data like '%\"cd\"%'
    """ + lim)
    delay_stability_ivl_list = map(lambda x: (today - min(today, x[0]), json.loads(json.loads(x[1])['cd'])['s'], x[2]), last_due_and_custom_data_and_ivl_rows)
    retention_stability_burden_list = list(map(lambda x: (math.pow(0.9, x[0] / x[1]), x[1], 1/max(1, x[2])), delay_stability_ivl_list))
    recall_sum = sum(item[0] for item in retention_stability_burden_list)
    stability_sum = sum(item[1] for item in retention_stability_burden_list)
    burden_sum = sum(item[2] for item in retention_stability_burden_list)
    cnt = len(retention_stability_burden_list)
    return recall_sum / cnt, stability_sum / cnt, burden_sum, cnt


def todayStats_new(self):
    lim = self._limit()
    if lim:
        lim = " AND did IN %s" % lim

    retention, stability, burden, count = retention_stability_burden(lim)
    i = []
    _line_now(i, "Average retention", f"{retention * 100: .2f}%")
    _line_now(i, "Average stability", f"{int(stability)} days")
    _line_now(i, "Total burden", f"{burden: .2f} reviews/day")
    _line_now(i, "Count", f"{count} cards")
    stats_data = _lineTbl_now(i)
    interpretation = "<h3>Interpretation</h3>" \
        + "<ul><li>Retention: the probability of recalling a card today. The average retention is often higher than your requested retention because it  is calculated in all cards including those undue cards. </li>" \
        + "<li>Stability: the number of days it takes for the retention to decay from 100% to 90%. </li>" \
        + "<li>Burden: the number of reviews needed to maintain retention perday. Total burden is the sum of reciprocals of all intervals, in days (aka the sum of 1/interval, like 1/I<sub>1</sub> + 1/I<sub>2</sub> + 1/I<sub>3</sub> +...+ 1/I<sub>n</sub>). </li>" \
        + "<li>Count: the number of cards with custom data. </li></ul>"
    return todayStats_old(self) + "<br><br><table style='text-align: center'><tr><td style='padding: 5px'>" \
        + "<h2>FSRS Stats</h2>" + stats_data + "</td></tr></table>" \
        + "<table style='text-align: left'><tr><td style='padding: 5px'>" + interpretation + "</td></tr></table>"


def init_stats():
    anki.stats.CollectionStats.todayStats = todayStats_new
