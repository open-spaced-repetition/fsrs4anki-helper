from aqt.gui_hooks import sync_will_start, sync_did_finish
from .schedule.reschedule import reschedule
from .schedule.disperse_siblings import disperse_siblings
from .configuration import Config
from .utils import *


def create_comparelog(local_rids: List[int]) -> None:
    local_rids.extend([id for id in mw.col.db.list("SELECT id FROM revlog")])


def review_cid_remote(local_rids: List[int]):
    local_rid_string = ",".join([str(local_rid) for local_rid in local_rids])
    # exclude entries where ivl == lastIvl: they indicate a dynamic deck without rescheduling
    remote_reviewed_cids = [
        cid
        for cid in mw.col.db.list(
            f"SELECT DISTINCT cid FROM revlog WHERE id NOT IN ({local_rid_string}) and ivl != lastIvl"
        )
    ]
    return remote_reviewed_cids


def auto_reschedule(local_rids: List[int], texts: List[str]):
    if len(local_rids) == 0:
        return
    config = Config()
    config.load()
    if not config.auto_reschedule_after_sync:
        return

    remote_reviewed_cids = review_cid_remote(local_rids)

    fut = reschedule(
        None,
        recent=False,
        filter_flag=True,
        filtered_cids=set(remote_reviewed_cids),
    )

    if fut:
        # wait for reschedule to finish
        texts.append(fut.result())


def auto_disperse(local_rids: List[int], texts: List[str]):
    if len(local_rids) == 0:
        return
    config = Config()
    config.load()
    if not config.auto_disperse_after_sync:
        return

    remote_reviewed_cids = review_cid_remote(local_rids)
    remote_reviewed_cid_string = ",".join([str(cid) for cid in remote_reviewed_cids])
    remote_reviewed_nids = [
        nid
        for nid in mw.col.db.list(
            f"""SELECT DISTINCT nid 
            FROM cards 
            WHERE id IN ({remote_reviewed_cid_string})
        """
        )
    ]
    remote_reviewed_nid_string = ",".join([str(nid) for nid in remote_reviewed_nids])

    fut = disperse_siblings(
        None,
        filter_flag=True,
        filtered_nid_string=remote_reviewed_nid_string,
        text_from_reschedule="<br>".join(texts),
    )

    if fut:
        # wait for disperse to finish
        return fut.result()


def init_sync_hook():
    local_rids = []
    texts = []

    sync_will_start.append(lambda: create_comparelog(local_rids))
    sync_did_finish.append(lambda: auto_reschedule(local_rids, texts))
    sync_did_finish.append(lambda: auto_disperse(local_rids, texts))
