import os
from pathlib import Path
from anki.utils import ids2str
from aqt import QDateTime, QWidget, QVBoxLayout, QLabel, QPushButton, QDateEdit
from aqt.utils import tooltip, showInfo
from ..i18n import t
from ..utils import *


class RemedyDateRangeWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.setup_ui()

    def setup_ui(self):
        self.layout = QVBoxLayout()

        self.start_date_label = QLabel(t("remedy-start-date"))
        self.start_date_edit = QDateEdit()
        self.start_date_edit.setDateTime(datetime.strptime("2006-01-01", "%Y-%m-%d"))
        self.end_date_label = QLabel(t("remedy-end-date"))
        self.end_date_edit = QDateEdit()
        self.end_date_edit.setDateTime(QDateTime.currentDateTime())
        self.remedy_button = QPushButton(t("remedy"))
        self.remedy_button.clicked.connect(self.remedy_hard_misuse)

        self.layout.addWidget(self.start_date_label)
        self.layout.addWidget(self.start_date_edit)
        self.layout.addWidget(self.end_date_label)
        self.layout.addWidget(self.end_date_edit)
        self.layout.addWidget(self.remedy_button)

        self.setLayout(self.layout)
        self.setWindowTitle(t("remedy-title"))
        self.resize(300, 200)

    def remedy_hard_misuse(self):
        revlog_ids = mw.col.db.list(f"""SELECT id
            FROM revlog
            WHERE ease = 2
            AND id > {self.start_date_edit.dateTime().toMSecsSinceEpoch()}
            AND id < {self.end_date_edit.dateTime().toMSecsSinceEpoch()}
            """)

        if len(revlog_ids) == 0:
            tooltip(t("remedy-no-hard-reviews"))
            return

        start_date = self.start_date_edit.date().toString("yyyy-MM-dd")
        end_date = self.end_date_edit.date().toString("yyyy-MM-dd")
        yes = askUser(
            t("remedy-confirmation").format(
                count=len(revlog_ids), start_date=start_date, end_date=end_date
            )
        )

        if not yes:
            return

        mw.col.db.execute(f"""UPDATE revlog
            SET ease = 1, usn = -1
            WHERE id IN {ids2str(revlog_ids)}
            """)
        col_set_modified()
        mw.col.set_schema_modified()
        addon = mw.addonManager.addonFromModule(__name__)
        user_files = Path(mw.addonManager.addonsFolder(addon)) / "user_files"
        user_files.mkdir(parents=True, exist_ok=True)
        revlog_id_csv = os.path.join(user_files, f"{mw.pm.name}_hard_misuse_remedy.csv")
        with open(revlog_id_csv, "a") as f:
            f.write("\n".join(map(str, revlog_ids)))

        showInfo(t("remedy-success").format(count=len(revlog_ids)))
        mw.reset()
        self.close()


def remedy_hard_misuse(did):
    if not ask_one_way_sync():
        return

    mw.date_range_widget = RemedyDateRangeWidget()
    mw.date_range_widget.show()


def undo_remedy(did):
    addon = mw.addonManager.addonFromModule(__name__)
    user_files = Path(mw.addonManager.addonsFolder(addon)) / "user_files"
    user_files.mkdir(parents=True, exist_ok=True)
    revlog_id_csv = os.path.join(user_files, f"{mw.pm.name}_hard_misuse_remedy.csv")
    if not os.path.exists(revlog_id_csv):
        tooltip(t("undo-remedy-no-file"))
        return

    if not ask_one_way_sync():
        return

    with open(revlog_id_csv, "r") as f:
        revlog_ids = list(map(int, f.read().splitlines()))

    mw.col.db.execute(f"""UPDATE revlog
        SET ease = 2, usn = -1
        WHERE id IN {ids2str(revlog_ids)}
        """)
    col_set_modified()
    mw.col.set_schema_modified()
    os.remove(revlog_id_csv)
    tooltip(t("undo-remedy-restored").format(count=len(revlog_ids)))
    showInfo(t("undo-remedy-success").format(count=len(revlog_ids)))
    mw.reset()
