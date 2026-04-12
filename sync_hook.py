from typing import List

from anki.utils import ids2str
from aqt.gui_hooks import sync_did_finish, sync_will_start
from aqt.qt import QTimer

from .configuration import Config
from .i18n import t
from .schedule.disperse_siblings import disperse_siblings
from .schedule.reschedule import reschedule
from .utils import *


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
    mw._sync_collection_and_media(mw._refresh_after_sync)


def auto_reschedule(remote_reviewed_cids: List[int], texts: List[str]) -> bool:
    if len(remote_reviewed_cids) == 0:
        return False
    texts.clear()
    config = Config()
    config.load()
    cnt = 0
    if not config.auto_reschedule_after_sync:
        texts.append(t("reschedule-skipped"))
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
        result = fut.result()
        cnt, finish_text = result[0], result[1]
        texts.append(finish_text)

    return cnt > 0


def auto_disperse(remote_reviewed_cids: List[int], texts: List[str]) -> bool:
    if len(remote_reviewed_cids) == 0:
        return False
    config = Config()
    config.load()
    card_cnt = 0
    if not config.auto_disperse_after_sync:
        return False

    if config.auto_reschedule_after_sync and config.auto_disperse_after_reschedule:
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
        card_cnt, _ = fut.result()

    return card_cnt > 0


def init_sync_hook():
    local_rids = []
    texts = []

    def on_sync_finished():
        remote_reviewed_cids = review_cid_remote(local_rids) if local_rids else []
        modified = auto_reschedule(remote_reviewed_cids, texts)
        modified = auto_disperse(remote_reviewed_cids, texts) or modified
        if modified:
            QTimer.singleShot(0, push_changes)

    sync_will_start.append(lambda: create_comparelog(local_rids))
    sync_did_finish.append(on_sync_finished)
