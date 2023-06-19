import anki.stats
import math
from .utils import *
from anki.hooks import wrap

def _line_now(i, a, b, bold=True):
    colon = ":"
    if bold:
        i.append(("<tr><td align=left>%s%s</td><td align=left><b>%s</b></td></tr>") % (a,colon,b))
    else:
        i.append(("<tr><td align=left>%s%s</td><td align=left>%s</td></tr>") % (a,colon,b))


def _lineTbl_now(i):
    return "<table>" + "".join(i) + "</table>"


def retention_stability_burden(lim) -> float:
    elapse_stability_ivl_list = mw.col.db.all(f"""
    SELECT 
        CASE WHEN odid==0
            THEN {mw.col.sched.today} - (due - ivl)
            ELSE {mw.col.sched.today} - (odue - ivl)
            END
        ,json_extract(json_extract(IIF(data != '', data, NULL), '$.cd'), '$.s')
        ,ivl 
    FROM cards 
    WHERE queue >= 1 
    AND data like '%\"cd\"%'
    """ + lim)
    # x[0]: elapsed days
    # x[1]: stability
    # x[2]: interval
    elapse_stability_ivl_list = filter(lambda x: x[1] is not None, elapse_stability_ivl_list)
    retention_stability_burden_list = list(map(lambda x: (math.pow(0.9, max(x[0], 0) / x[1]), x[1], 1/max(1, x[2])), elapse_stability_ivl_list))
    cnt = len(retention_stability_burden_list)
    if cnt == 0:
        return 0, 0, 0, 0
    recall_sum = sum(item[0] for item in retention_stability_burden_list)
    stability_sum = sum(item[1] for item in retention_stability_burden_list)
    burden_sum = sum(item[2] for item in retention_stability_burden_list)
    return recall_sum / cnt, stability_sum / cnt, burden_sum, cnt


def todayStats_new(self):
    lim = self._limit()
    if lim:
        lim = " AND did IN %s" % lim

    retention, stability, burden, count = retention_stability_burden(lim)
    estimated_total_knowledge = round(retention * count)
    i = []
    _line_now(i, "Average retention", f"{retention * 100: .2f}%")
    _line_now(i, "Average stability", f"{int(stability)} days")
    _line_now(i, "Burden", f"{burden: .2f} reviews/day")
    _line_now(i, "Count", f"{count} cards")
    _line_now(i, "Estimated total knowledge", f"{estimated_total_knowledge} cards")
    stats_data = _lineTbl_now(i)
    interpretation = "<h3>Interpretation</h3>" \
        + "<ul>" \
        + "<li><b>Average retention</b>: the average probability of recalling a card today. In most cases, it is higher than requested retention because requested retention refers to retention at the time of a review, whereas average retention is calculated based on all cards, including undue cards.</li>" \
        + "<li><b>Stability</b>: the number of days it takes for the retention to decay from 100% to 90%.</li>" \
        + "<li><b>Burden</b>: an estimate of the average number of cards that have to be reviewed daily (assuming review at the scheduled time without advancing or postponing). Burden = 1/I<sub>1</sub> + 1/I<sub>2</sub> + 1/I<sub>3</sub> +...+ 1/I<sub>n</sub> where I<sub>n</sub> - current interval of the n-th card.</li>" \
        + "<li><b>Count</b>: the number of cards with custom data, in other words, cards that are affected by FSRS (this does not include cards in the (re)learning stage).</li> " \
        + "<li><b>Estimated total knowledge</b>: the number of cards that the user is expected to know today, calculated as the product of average retention and count.</li>" \
        + "</ul>"
    return todayStats_old(self) + "<br><br><table style='text-align: center'><tr><td style='padding: 5px'>" \
        + "<h2>FSRS Stats</h2>" + stats_data + "</td></tr></table>" \
        + "<table style='text-align: left'><tr><td style='padding: 5px'>" + interpretation + "</td></tr></table>"


def _plot(self, data, title, subtitle, color):
    if not data:
        return ""

    txt = self._title(title, subtitle)

    graph_data = [dict(data=data, color=color)]

    yaxes = [dict(min=min(y for x, y in data),
                  max=max(y for x, y in data))]

    txt += self._graph(
        id="difficulty",
        data=graph_data,
        type="bars",
        conf=dict(
            xaxis=dict(min=1, max=10, ticks=[[i, i] for i in range(1, 11)]),
            yaxes=yaxes
        ),
        ylabel="Cards",
    )

    return txt

def difficulty_distribution_graph(self):
    lim = self._limit()
    if lim:
        lim = " AND did IN %s" % lim
    difficulty_count = mw.col.db.all(f"""
    SELECT 
        CAST(json_extract(json_extract(IIF(data != '', data, NULL), '$.cd'), '$.d') AS INT)
        ,count(*)
    FROM cards 
    WHERE queue >= 1 
    AND data like '%\"cd\"%'
    {lim}
    GROUP BY CAST(json_extract(json_extract(IIF(data != '', data, NULL), '$.cd'), '$.d') AS INT)
    """)
    # x[0]: difficulty
    # x[1]: cnt
    difficulty_count = tuple(filter(lambda x: x[0] is not None, difficulty_count))
    distribution_graph = _plot(self, difficulty_count, "Difficulty Distribution", "", "#00F")
    return cardGraph_old(self) + distribution_graph




def init_stats():
    global todayStats_old, cardGraph_old
    todayStats_old = anki.stats.CollectionStats.todayStats
    cardGraph_old = anki.stats.CollectionStats.cardGraph 
    anki.stats.CollectionStats.todayStats = todayStats_new
    anki.stats.CollectionStats.cardGraph = difficulty_distribution_graph
