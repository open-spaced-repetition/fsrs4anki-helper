from aqt.gui_hooks import sync_will_start, sync_did_finish
from aqt.sync import sync_collection
from anki.utils import ids2str
from typing import List
from .schedule.reschedule import reschedule
from .schedule.disperse_siblings import disperse_siblings
from .configuration import Config
from .utils import *
from .i18n import t


def create_comparelog(local_rids: List[int]) -> None:
    local_rids.clear()
    local_rids.extend([id for id in mw.col.db.list("SELECT id FROM revlog")])


def review_cid_remote(local_rids: List[int]):
    config = Config()
    config.load()
    local_rid_string = ids2str(local_rids)
    # get cids of revlog entries that were not present in the collection before sync
    # exclude manual entries and reviews done in filtered decks with rescheduling disabled
    remote_reviewed_cids = [
        cid
        for cid in mw.col.db.list(
            f"""SELECT DISTINCT cid
            FROM revlog
            WHERE id NOT IN {local_rid_string}
            {"AND type != 4" if config.auto_disperse_after_reschedule else "AND ease > 0"}
            AND (type < 3 OR factor != 0)
            """
        )  # type: 0=learn, 1=review, 2=relearn, 3=filtered, 4=manual, 5=reschedule
    ]
    return remote_reviewed_cids


def push_changes() -> None:
    if not mw.pm.sync_auth():
        return
    sync_collection(mw, on_done=lambda: mw.reset())


def auto_reschedule(local_rids: List[int], texts: List[str]) -> bool:
    if len(local_rids) == 0:
        return False
    texts.clear()
    config = Config()
    config.load()
    if not config.auto_reschedule_after_sync:
        texts.append(t("reschedule-skipped"))
        return False

    remote_reviewed_cids = review_cid_remote(local_rids)
    if not remote_reviewed_cids:
        return False

    fut = reschedule(
        did=None,
        recent=False,
        filter_flag=True,
        filtered_cids=set(remote_reviewed_cids),
        auto_reschedule=True,
    )

    if fut:
        # wait for reschedule to finish
        texts.append(fut.result())

    return True


def auto_disperse(local_rids: List[int], texts: List[str]) -> bool:
    if len(local_rids) == 0:
        return False
    config = Config()
    config.load()
    if not config.auto_disperse_after_sync:
        return False

    if config.auto_reschedule_after_sync and config.auto_disperse_after_reschedule:
        return False

    remote_reviewed_cids = review_cid_remote(local_rids)
    if not remote_reviewed_cids:
        return False

    remote_reviewed_cid_string = ids2str(remote_reviewed_cids)
    remote_reviewed_nids = [
        nid
        for nid in mw.col.db.list(f"""SELECT DISTINCT nid
            FROM cards
            WHERE id IN {remote_reviewed_cid_string}
        """)
    ]
    remote_reviewed_nid_string = ids2str(remote_reviewed_nids)

    fut = disperse_siblings(
        None,
        filter_flag=True,
        filtered_nid_string=remote_reviewed_nid_string,
        text_from_reschedule="<br>".join(texts),
    )
    texts.clear()

    if fut:
        # wait for disperse to finish
        fut.result()

    return True


def init_sync_hook():
    local_rids = []
    texts = []

    def on_sync_finished():
        modified = auto_reschedule(local_rids, texts)
        modified = auto_disperse(local_rids, texts) or modified
        if modified:
            push_changes()

    sync_will_start.append(lambda: create_comparelog(local_rids))
    sync_did_finish.append(on_sync_finished)
