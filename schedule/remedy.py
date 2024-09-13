import os
from pathlib import Path
from ..utils import *
from anki.utils import ids2str


def ask_date_range():
    (s, r) = getText("Enter the start date in the format YYYYMMDD")
    if not r:
        return None, None
    start_date = datetime.strptime(s, "%Y%m%d").timestamp() * 1000
    (s, r) = getText("Enter the end date in the format YYYYMMDD")
    if not r:
        return None, None
    end_date = datetime.strptime(s, "%Y%m%d").timestamp() * 1000
    return int(start_date), int(end_date)


def remedy_hard_misuse(did):
    start_date, end_date = ask_date_range()
    if not start_date or not end_date:
        tooltip("Invalid date range")
        return

    print(start_date, end_date)
    revlog_ids = mw.col.db.list(
        f"""SELECT id
        FROM revlog
        WHERE ease = 2
        AND id > {start_date}
        AND id < {end_date}
        """
    )

    if len(revlog_ids) == 0:
        tooltip("No reviews in the date range")
        return

    mw.col.db.execute(
        f"""UPDATE revlog
        SET ease = 1
        WHERE id IN {ids2str(revlog_ids)}
        """
    )

    addon = mw.addonManager.addonFromModule(__name__)
    user_files = Path(mw.addonManager.addonsFolder(addon)) / "user_files"
    user_files.mkdir(parents=True, exist_ok=True)
    revlog_id_csv = os.path.join(user_files, "hard_misuse_remedy.csv")
    with open(revlog_id_csv, "a") as f:
        f.write("\n".join(map(str, revlog_ids)))

    tooltip(f"{len(revlog_ids)} reviews remedied")
    mw.reset()


def undo_remedy(did):
    addon = mw.addonManager.addonFromModule(__name__)
    user_files = Path(mw.addonManager.addonsFolder(addon)) / "user_files"
    user_files.mkdir(parents=True, exist_ok=True)
    revlog_id_csv = os.path.join(user_files, "hard_misuse_remedy.csv")
    if not os.path.exists(revlog_id_csv):
        tooltip("No remedied reviews found")
        return

    with open(revlog_id_csv, "r") as f:
        revlog_ids = list(map(int, f.read().splitlines()))

    mw.col.db.execute(
        f"""UPDATE revlog
        SET ease = 2
        WHERE id IN {ids2str(revlog_ids)}
        """
    )

    os.remove(revlog_id_csv)
    tooltip(f"{len(revlog_ids)} reviews restored")
    mw.reset()
