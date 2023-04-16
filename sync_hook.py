from aqt.gui_hooks import sync_will_start, sync_did_finish
from .reschedule import reschedule
from .configuration import Config
from .utils import *


def create_comparelog(oldids: List[int]) -> None:
    oldids.extend(
        [id for id in mw.col.db.list("SELECT id FROM revlog")]
    )


def auto_reschedule(oldids: List[int]):
    if len(oldids) == 0:
        return
    config = Config()
    config.load()
    if not config.auto_reschedule_after_sync:
        return
    

    oldidstring = ",".join([str(oldid) for oldid in oldids])

    # exclude entries where ivl == lastIvl: they indicate a dynamic deck without rescheduling
    reviewed_cids = [cid for cid in mw.col.db.list(
            f"SELECT DISTINCT cid FROM revlog WHERE id NOT IN ({oldidstring}) and ivl != lastIvl"
        )
    ]

    reschedule(None, recent=False, filter=True, filtered_cid=set(reviewed_cids))


def init_sync_hook():
    oldids = []

    sync_will_start.append(lambda: create_comparelog(oldids))
    sync_did_finish.append(lambda: auto_reschedule(oldids))
