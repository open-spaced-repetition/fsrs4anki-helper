import os
from pathlib import Path
from ..utils import *
from anki.utils import ids2str
from aqt import QDateTime, QWidget, QVBoxLayout, QLabel, QPushButton, QDateEdit


class RemedyDateRangeWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.setup_ui()

    def setup_ui(self):
        self.layout = QVBoxLayout()

        self.start_date_label = QLabel("Select the Start Date")
        self.start_date_edit = QDateEdit()
        self.start_date_edit.setDateTime(datetime.strptime("2006-01-01", "%Y-%m-%d"))
        self.end_date_label = QLabel("Select the End Date")
        self.end_date_edit = QDateEdit()
        self.end_date_edit.setDateTime(QDateTime.currentDateTime())
        self.remedy_button = QPushButton("Remedy")
        self.remedy_button.clicked.connect(self.remedy_hard_misuse)

        self.layout.addWidget(self.start_date_label)
        self.layout.addWidget(self.start_date_edit)
        self.layout.addWidget(self.end_date_label)
        self.layout.addWidget(self.end_date_edit)
        self.layout.addWidget(self.remedy_button)

        self.setLayout(self.layout)
        self.setWindowTitle("Remedy Hard Misuse")
        self.resize(300, 200)

    def remedy_hard_misuse(self):
        revlog_ids = mw.col.db.list(
            f"""SELECT id
            FROM revlog
            WHERE ease = 2
            AND id > {self.start_date_edit.dateTime().toMSecsSinceEpoch()}
            AND id < {self.end_date_edit.dateTime().toMSecsSinceEpoch()}
            """
        )

        if len(revlog_ids) == 0:
            tooltip(
                "There are no reviews with a Hard rating in the selected range of dates."
            )
            return

        start_date = self.start_date_edit.date().toString("yyyy-MM-dd")
        end_date = self.end_date_edit.date().toString("yyyy-MM-dd")
        yes = askUser(
            f"""Between {start_date} and {end_date}, {len(revlog_ids)} reviews had a Hard rating.
These ratings will be replaced with Again. The IDs of these revlogs will be stored in a CSV file in the addon folder to allow undoing the changes.
Do you want to proceed?
        """
        )

        if not yes:
            return

        mw.col.db.execute(
            f"""UPDATE revlog
            SET ease = 1, usn = -1
            WHERE id IN {ids2str(revlog_ids)}
            """
        )
        col_set_modified()

        addon = mw.addonManager.addonFromModule(__name__)
        user_files = Path(mw.addonManager.addonsFolder(addon)) / "user_files"
        user_files.mkdir(parents=True, exist_ok=True)
        revlog_id_csv = os.path.join(user_files, f"{mw.pm.name}_hard_misuse_remedy.csv")
        with open(revlog_id_csv, "a") as f:
            f.write("\n".join(map(str, revlog_ids)))

        tooltip(f"{len(revlog_ids)} reviews remedied")
        mw.reset()


def remedy_hard_misuse(did):
    mw.date_range_widget = RemedyDateRangeWidget()
    mw.date_range_widget.show()


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
        SET ease = 2, usn = -1
        WHERE id IN {ids2str(revlog_ids)}
        """
    )
    col_set_modified()

    os.remove(revlog_id_csv)
    tooltip(f"{len(revlog_ids)} reviews restored")
    mw.reset()
