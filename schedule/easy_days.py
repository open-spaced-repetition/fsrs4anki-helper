from ..utils import *
from ..configuration import Config
from .reschedule import reschedule
from anki.utils import ids2str
from aqt.gui_hooks import collection_did_load


def easy_days(did):
    config = Config()
    config.load()
    if not config.load_balance:
        tooltip("Please enable load balance first")
        return
    if len(config.easy_days) == 0:
        tooltip("Please select easy days first")
        return
    today = mw.col.sched.today
    due_days = []
    for day_offset in range(365):
        if (datetime.now() + timedelta(days=day_offset)).weekday() in config.easy_days:
            due_days.append(today + day_offset)

    # find cards that are due in easy days in the next 365 days
    due_in_easy_days_cids = mw.col.db.list(
        f"""SELECT id
        FROM cards
        WHERE data != '' 
        AND json_extract(data, '$.s') IS NOT NULL
        AND CASE WHEN odid==0
        THEN due
        ELSE odue
        END IN {ids2str(due_days)}
        """
    )

    reschedule(
        None,
        recent=False,
        filter_flag=True,
        filtered_cids=set(due_in_easy_days_cids),
    )


@collection_did_load.append
def auto_easy_days(col):
    config = Config()
    config.load()
    if config.auto_easy_days:
        easy_days(None)
