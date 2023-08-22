import anki.stats
from .configuration import Config
from .utils import *

def _line_now(i, a, b, bold=True):
    colon = ":"
    style = "style='padding: 5px'"
    if bold:
        i.append(("<tr><td align=left %s>%s%s</td><td align=left><b>%s</b></td></tr>") % (style, a,colon,b))
    else:
        i.append(("<tr><td align=left %s>%s%s</td><td align=left>%s</td></tr>") % (style, a,colon,b))


def _lineTbl_now(i):
    return "<table>" + "".join(i) + "</table>"


def retention_stability_burden(lim) -> float:
    custom_scheduler = check_fsrs4anki(mw.col.all_config())
    if custom_scheduler is None:
        return
    version = get_version(custom_scheduler)
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
    retention_stability_burden_list = list(map(lambda x: (exponential_forgetting_curve(max(x[0], 0), x[1]) if version[0] == 3 else power_forgetting_curve(max(x[0], 0), x[1]), x[1], 1/max(1, x[2])), elapse_stability_ivl_list))
    cnt = len(retention_stability_burden_list)
    if cnt == 0:
        return 0, 0, 0, 0
    recall_sum = sum(item[0] for item in retention_stability_burden_list)
    stability_sum = sum(item[1] for item in retention_stability_burden_list)
    burden_sum = sum(item[2] for item in retention_stability_burden_list)
    return recall_sum / cnt, stability_sum / cnt, burden_sum, cnt


def todayStats_new(self):
    return todayStats_old(self) + get_true_retention(self) + get_fsrs_stats(self) + get_retention_graph(self)


def get_fsrs_stats(self):
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
    title = anki.stats.CollectionStats._title(self, "FSRS Stats", "Only calculated for cards with custom data (affected by FSRS)")
    stats_data = _lineTbl_now(i)
    interpretation = "<details><summary>Interpretation</summary>" \
        + "<ul>" \
        + "<li><b>Average retention</b>: the average probability of recalling a card today. In most cases, it is higher than requested retention because requested retention refers to retention at the time of a review, whereas average retention is calculated based on all cards, including undue cards.</li>" \
        + "<li><b>Stability</b>: the number of days it takes for the retention to decay from 100% to 90%.</li>" \
        + "<li><b>Burden</b>: an estimate of the average number of cards that have to be reviewed daily (assuming review at the scheduled time without advancing or postponing). Burden = 1/I<sub>1</sub> + 1/I<sub>2</sub> + 1/I<sub>3</sub> +...+ 1/I<sub>n</sub> where I<sub>n</sub> - current interval of the n-th card.</li>" \
        + "<li><b>Count</b>: the number of cards with custom data, in other words, cards that are affected by FSRS (this does not include cards in the (re)learning stage).</li> " \
        + "<li><b>Estimated total knowledge</b>: the number of cards that the user is expected to know today, calculated as the product of average retention and count.</li>" \
        + "</ul></details>"
    return self._section(title + stats_data + "<table style='text-align: left'><tr><td style='padding: 5px'>" + interpretation + "</td></tr></table>")


def get_retention_graph(self):
    start, days, chunk = self.get_start_end_chunk()
    lims = []
    if days is not None:
        lims.append(
            "id > %d" % ((self.col.sched.day_cutoff - (days * chunk * 86400)) * 1000)
        )
    lim = "cid in (select id from cards where did in %s)" % self._limit()
    if lim:
        lims.append(lim)
    if lims:
        lim = "AND " + " AND ".join(lims)

    query = f"""SELECT
    CAST((id/1000.0 - {mw.col.sched.day_cutoff}) / 86400.0 as int)/{chunk} AS day,
    SUM(CASE WHEN  ease == 1 THEN 0.0 ELSE 1.0 END) / COUNT(*) AS retention,
    COUNT(*) AS review_cnt
    FROM revlog
    WHERE (type = 1 OR lastIvl <= -86400 OR lastIvl >= 1)
    {lim}
    GROUP BY day
    """

    offset_retention_review_cnt = mw.col.db.all(query)
    data, _ = self._splitRepData(
        offset_retention_review_cnt,
        (
        (1, '#070', "Retention Rate"),
        (2, '#00F', "Review Cnt"),
        )
    )

    if not data:
        return ""

    rate_data, _, cnt_data, _ = data

    rate_data['lines'] = {"show": True}
    rate_data['bars'] = {"show": False}
    rate_data['yaxis'] = 1

    cnt_data['lines'] = {"show": False}
    cnt_data['bars'] = {"show": True}
    cnt_data['yaxis'] = 2

    data = [rate_data, cnt_data]
    print(data)

    conf = dict(
        xaxis=dict(tickDecimals=0, max=0.5),
        yaxes=[dict(min=0, max=1, ticks=[[x/10, str(round(x/10, 1))] for x in range(0, 11)]), dict(position="right", min=0)],
    )
    if days is not None:
        conf["xaxis"]["min"] = -days + 0.5

    def plot(id: str, data, ylabel: str, ylabel2: str) -> str:
        return self._graph(
            id, data=data, conf=conf, xunit=chunk, ylabel=ylabel, ylabel2=ylabel2
        )
    

    txt1 = self._title("Retention Graph", "Retention rate and review count over time")
    txt1 += plot("retention", data, ylabel="Retention Rate", ylabel2="Review Count")
    return self._section(txt1)


def bar_plot(self, data, title, subtitle, color):
    if not data:
        return ""

    txt = self._title(title, subtitle)

    graph_data = [dict(data=data, color=color)]

    yaxes = [dict(min=0,
                  max=max(y for x, y in data))]

    txt += self._graph(
        id="difficulty",
        data=graph_data,
        type="bars",
        conf=dict(
            xaxis=dict(min=0.5, max=10.5, ticks=[[i, i] for i in range(1, 11)]),
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
        CAST(ROUND(json_extract(json_extract(IIF(data != '', data, NULL), '$.cd'), '$.d')) AS INT)
        ,count(*)
    FROM cards 
    WHERE queue >= 1 
    AND data like '%\"cd\"%'
    {lim}
    GROUP BY CAST(ROUND(json_extract(json_extract(IIF(data != '', data, NULL), '$.cd'), '$.d')) AS INT)
    """)
    # x[0]: difficulty
    # x[1]: cnt
    difficulty_count = tuple(filter(lambda x: x[0] is not None, difficulty_count))
    distribution_graph = bar_plot(self, difficulty_count, "Difficulty Distribution", "Lower value of D (horizontal axis) = less difficult, higher value of D = more difficult", "#72bcd4")
    return cardGraph_old(self) + distribution_graph

def init_stats():
    global todayStats_old, cardGraph_old
    todayStats_old = anki.stats.CollectionStats.todayStats
    cardGraph_old = anki.stats.CollectionStats.cardGraph 
    anki.stats.CollectionStats.todayStats = todayStats_new
    anki.stats.CollectionStats.cardGraph = difficulty_distribution_graph

# code modified from https://ankiweb.net/shared/info/1779060522

def get_true_retention(self):
    lim = "cid in (select id from cards where did in %s)" % self._limit()
    if lim:
        lim = " AND " + lim
    pastDay = stats_list(lim, (mw.col.sched.day_cutoff-86400)*1000)

    pastYesterday = stats_list(lim, (mw.col.sched.day_cutoff-86400*2)*1000)
    pastYesterday[0] -= pastDay[0]
    pastYesterday[1] -= pastDay[1]
    pastYesterday[2] = retentionAsString(pastYesterday[0], pastYesterday[0] + pastYesterday[1])
    pastYesterday[3] -= pastDay[3]
    pastYesterday[4] -= pastDay[4]
    pastYesterday[5] = retentionAsString(pastYesterday[3], pastYesterday[3] + pastYesterday[4])
    pastYesterday[6] = pastYesterday[0] + pastYesterday[3]
    pastYesterday[7] = pastYesterday[1] + pastYesterday[4]
    pastYesterday[8] = retentionAsString(pastYesterday[6], pastYesterday[6] + pastYesterday[7])
    pastYesterday[9] -= pastDay[9]
    pastYesterday[10] -= pastDay[10]

    pastWeek = stats_list(lim, (mw.col.sched.day_cutoff-86400*7)*1000)
    
    if self.type == 0:
        period = 31; pname = u"Month"
    elif self.type == 1:
        period = 365; pname = u"Year"
    elif self.type == 2:
        period = 10000; pname = u"Deck life"    
    pastPeriod = stats_list(lim, (mw.col.sched.day_cutoff-86400*period)*1000)
    true_retention_part = anki.stats.CollectionStats._title(self, "True Retention", "The True Retention is the pass rate calculated only on cards with intervals greater than or equal to one day. It is a better indicator of the learning quality than the Again rate.")
    true_retention_part += u"""
        <style>
            td.trl { border: 1px solid; text-align: left; padding: 5px  }
            td.trr { border: 1px solid; text-align: right; padding: 5px  }
            td.trc { border: 1px solid; text-align: center; padding: 5px }
            span.young { color: #77cc77 }
            span.mature { color: #00aa00 }
            span.yam { color: #55aa55 }
            span.relearn { color: #c35617 }
        </style>
        <br /><br />
        <table style="border-collapse: collapse;" cellspacing="0" cellpadding="2">
            <tr>
                <td class="trl" rowspan=3><b>Past</b></td>
                <td class="trc" colspan=9><b>Reviews on Cards</b></td>
                <td class="trc" colspan=2 valign=middle><b>Cards</b></td>
            </tr>
            <tr>
                <td class="trc" colspan=3><span class="young"><b>Young</b></span></td>
                <td class="trc" colspan=3><span class="mature"><b>Mature</b></span></td>
                <td class="trc" colspan=3><span class="yam"><b>Young and Mature</b></span></td>
                <td class="trc" rowspan=2><span class="young"><b>Learnt</b></span></td>
                <td class="trc" rowspan=2><span class="relearn"><b>Relearnt</b></span></td>
            </tr>
            <tr>
                <td class="trc"><span class="young">Pass</span></td>
                <td class="trc"><span class="young">Fail</span></td>
                <td class="trc"><span class="young">Retention</span></td>
                <td class="trc"><span class="mature">Pass</span></td>
                <td class="trc"><span class="mature">Fail</span></td>
                <td class="trc"><span class="mature">Retention</span></td>
                <td class="trc"><span class="yam">Pass</span></td>
                <td class="trc"><span class="yam">Fail</span></td>
                <td class="trc"><span class="yam">Retention</span></td>
            </tr>"""
    true_retention_part += stats_row("Day", pastDay)
    true_retention_part += stats_row("Yesterday", pastYesterday)
    true_retention_part += stats_row("Week", pastWeek)
    true_retention_part += stats_row(pname, pastPeriod)
    true_retention_part += "</table>"
    return self._section(true_retention_part)

def retentionAsString(n, d):
    return "%0.1f%%" % ((n * 100) / d) if d else "N/A"

def stats_list(lim, span):
    config = Config()
    config.load()
    yflunked, ypassed, mflunked, mpassed, learned, relearned = mw.col.db.first("""
    select
    sum(case when lastIvl < %(i)d and ease = 1 and (type = 1 OR lastIvl <= -86400 OR lastIvl >= 1) then 1 else 0 end), /* flunked young */
    sum(case when lastIvl < %(i)d and ease > 1 and (type = 1 OR lastIvl <= -86400 OR lastIvl >= 1) then 1 else 0 end), /* passed young */
    sum(case when lastIvl >= %(i)d and ease = 1 and (type = 1 OR lastIvl <= -86400 OR lastIvl >= 1) then 1 else 0 end), /* flunked mature */
    sum(case when lastIvl >= %(i)d and ease > 1 and (type = 1 OR lastIvl <= -86400 OR lastIvl >= 1) then 1 else 0 end), /* passed mature */
    count(DISTINCT case when type = 0 and (ivl >= 1 OR ivl <= -86400) and cid NOT in ( SELECT id FROM cards WHERE type = 0) then cid else NULL end), /* learned */
    sum(case when type = 2 and (ivl >= 1 OR ivl <= -86400) and (lastIvl > -86400 and lastIvl <= 0) then 1 else 0 end) + sum(case when type = 0 and (lastIvl <= -86400 OR lastIvl >= 1) and ease = 1 then 1 else 0 end)/* relearned */
    from revlog where id > ? """ % dict(i=config.mature_ivl) + lim, span)
    yflunked, mflunked = yflunked or 0, mflunked or 0
    ypassed, mpassed = ypassed or 0, mpassed or 0
    learned, relearned = learned or 0, relearned or 0

    return [
        ypassed,
        yflunked,
        retentionAsString(ypassed, float(ypassed + yflunked)), 
        mpassed,
        mflunked,
        retentionAsString(mpassed, float(mpassed + mflunked)), 
        ypassed + mpassed,
        yflunked + mflunked,
        retentionAsString(ypassed + mpassed, float(ypassed + mpassed + yflunked + mflunked)), 
        learned,
        relearned]

def stats_row(name, values):
    return u"""
        <tr>
            <td class="trl">""" + name + """</td>
            <td class="trr"><span class="young">""" + str(values[0]) + u"""</span></td>
            <td class="trr"><span class="young">""" + str(values[1]) + u"""</span></td>
            <td class="trr"><span class="young">""" + values[2] + u"""</span></td>
            <td class="trr"><span class="mature">""" + str(values[3]) + u"""</span></td>
            <td class="trr"><span class="mature">""" + str(values[4]) + u"""</span></td>
            <td class="trr"><span class="mature">""" + values[5] + u"""</span></td>
            <td class="trr"><span class="yam">""" + str(values[6]) + u"""</span></td>
            <td class="trr"><span class="yam">""" + str(values[7]) + u"""</span></td>
            <td class="trr"><span class="yam">""" + values[8] + u"""</span></td>
            <td class="trr"><span class="young">""" + str(values[9]) + u"""</span></td>
            <td class="trr"><span class="relearn">""" + str(values[10]) + u"""</span></td>
        </tr>"""
