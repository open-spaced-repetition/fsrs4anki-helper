from ..utils import *
from ..configuration import Config
from .reschedule import reschedule
from anki.utils import ids2str


def free_days(did):
    config = Config()
    config.load()
    if not config.load_balance:
        tooltip("Please enable load balance first")
        return
    if len(config.free_days) == 0:
        tooltip("Please select free days first")
        return
    today = mw.col.sched.today
    due_days = []
    for day_offset in range(365):
        if (datetime.now() + timedelta(days=day_offset)).weekday() in config.free_days:
            due_days.append(today + day_offset)

    # find cards that are due in free days in the next 365 days
    due_in_free_days_cids = mw.col.db.list(
        f"""SELECT id
        FROM cards
        WHERE data != '' 
        AND json_extract(data, '$.cd') IS NOT NULL
        AND due IN {ids2str(due_days)}
        """
    )

    reschedule(
        None,
        recent=False,
        filter_flag=True,
        filtered_cids=set(due_in_free_days_cids),
    )
