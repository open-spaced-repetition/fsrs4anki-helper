import os
from pathlib import Path
from ..utils import *
from anki.utils import ids2str


def RepresentsDatetime(s):
    try:
        return datetime.strptime(s, "%Y%m%d")
    except ValueError:
        tooltip("Invalid date format")
        return None


def ask_date_range():
    (s, r) = getText("Enter the start date in the format YYYYMMDD")
    if not r:
        return None, None
    start_date = RepresentsDatetime(s)
    if not start_date:
        return None, None
    (s, r) = getText("Enter the end date in the format YYYYMMDD")
    if not r:
        return None, None
    end_date = RepresentsDatetime(s)
    if not end_date:
        return None, None
    return start_date, end_date


def remedy_hard_misuse(did):
    start_date, end_date = ask_date_range()
    if not start_date or not end_date:
        return

    revlog_ids = mw.col.db.list(
        f"""SELECT id
        FROM revlog
        WHERE ease = 2
        AND id > {start_date.timestamp() * 1000}
        AND id < {end_date.timestamp() * 1000}
        """
    )

    if len(revlog_ids) == 0:
        tooltip("There are no reviews with a Hard rating in the selected range of dates.")
        return

    yes = askUser(
        f"""Between {start_date.strftime("%Y-%m-%d")} and {end_date.strftime("%Y-%m-%d")}, {len(revlog_ids)} reviews had a Hard rating.
These ratings will be replaced with Again. The IDs of these revlogs will be stored in a CSV file in the addon folder to allow undoing the changes.
Do you want to proceed?
    """
    )

    if not yes:
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
    revlog_id_csv = os.path.join(user_files, f"{mw.pm.name}_hard_misuse_remedy.csv")
    with open(revlog_id_csv, "a") as f:
        f.write("\n".join(map(str, revlog_ids)))

    tooltip(f"{len(revlog_ids)} reviews remedied")
    mw.reset()


def undo_remedy(did):
    addon = mw.addonManager.addonFromModule(__name__)
    user_files = Path(mw.addonManager.addonsFolder(addon)) / "user_files"
    user_files.mkdir(parents=True, exist_ok=True)
    revlog_id_csv = os.path.join(user_files, f"{mw.pm.name}_hard_misuse_remedy.csv")
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
