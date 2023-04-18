from aqt.gui_hooks import sync_will_start, sync_did_finish
import time
from .reschedule import reschedule
from .disperse_siblings import disperse_siblings
from .configuration import Config
from .utils import *


def create_comparelog(local_rids: List[int]) -> None:
    local_rids.extend(
        [id for id in mw.col.db.list("SELECT id FROM revlog")]
    )


def auto_reschedule(local_rids: List[int]):
    if len(local_rids) == 0:
        return
    config = Config()
    config.load()
    if not config.auto_reschedule_after_sync:
        return
    

    local_rid_string = ",".join([str(local_rid) for local_rid in local_rids])

    # exclude entries where ivl == lastIvl: they indicate a dynamic deck without rescheduling
    remote_reviewed_cids = [cid for cid in mw.col.db.list(
            f"SELECT DISTINCT cid FROM revlog WHERE id NOT IN ({local_rid_string}) and ivl != lastIvl"
        )
    ]

    reschedule(None, recent=False, filter=True, filtered_cids=set(remote_reviewed_cids))

    remote_reviewed_cid_string = ",".join([str(cid) for cid in remote_reviewed_cids])
    rescheduled_nids_have_siblings = [nid for nid in mw.col.db.list(
        f"""SELECT DISTINCT nid 
            FROM cards 
            WHERE id IN ({remote_reviewed_cid_string}) 
            and queue = 2 
            and nid IN (
                SELECT nid
                FROM cards
                WHERE queue = 2
                AND data like '%"cd"%'
                GROUP BY nid
                HAVING count(*) > 1
            )"""
        )
    ]
    affected_notes = len(rescheduled_nids_have_siblings)
    if affected_notes > 0 and askUser(f"Rescheduling done. {affected_notes} notes with siblings affected. Disperse siblings?"):
        disperse_siblings(None, filter=True, filtered_nid_string=",".join([str(nid) for nid in rescheduled_nids_have_siblings]))


def init_sync_hook():
    local_rids = []

    sync_will_start.append(lambda: create_comparelog(local_rids))
    sync_did_finish.append(lambda: auto_reschedule(local_rids))
