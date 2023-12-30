from aqt import (
    QDate,
    QDateEdit,
    QDateTime,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)
from ..utils import *
from ..configuration import Config
from .reschedule import reschedule
from anki.utils import ids2str
from aqt.gui_hooks import profile_will_close


def easy_days(did):
    config = Config()
    config.load()
    if not config.load_balance:
        tooltip("Please enable load balance first")
        return
    if len(config.easy_days) == 0:
        tooltip("Please select easy days first")
        return
    today = mw.col.sched.today
    due_days = []
    for day_offset in range(90):
        if (datetime.now() + timedelta(days=day_offset)).weekday() in config.easy_days:
            due_days.append(today + day_offset)

    # find cards that are due in easy days in the next 90 days
    due_in_easy_days_cids = mw.col.db.list(
        f"""SELECT id
        FROM cards
        WHERE data != '' 
        AND json_extract(data, '$.s') IS NOT NULL
        AND CASE WHEN odid==0
        THEN due
        ELSE odue
        END IN {ids2str(due_days)}
        """
    )

    fut = reschedule(
        None,
        recent=False,
        filter_flag=True,
        filtered_cids=set(due_in_easy_days_cids),
    )
    if fut:
        return fut.result()


@profile_will_close.append
def auto_easy_days():
    config = Config()
    config.load()
    if config.auto_easy_days:
        easy_days(None)


# Modified from https://github.com/sam1penny/countdown-to-events/blob/main/src/__init__.py#L86-L169
class EasySpecificDateWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.initUi()

    def initUi(self):
        self.layout = QVBoxLayout()

        self.dateLabel = QLabel()
        self.dateLabel.setText("Select The Specific Date")
        self.dateEdit = QDateEdit()
        self.dateEdit.setDateTime(QDateTime.currentDateTime())
        self.dateEdit.setMinimumDate(QDate.currentDate())

        self.applyEasyDayBtn = QPushButton("Apply Easy Day")
        self.applyEasyDayBtn.clicked.connect(self.apply_easy_day_for_specific_date)

        self.layout.addWidget(self.dateLabel)
        self.layout.addWidget(self.dateEdit)
        self.layout.addWidget(self.applyEasyDayBtn)

        self.layout.addStretch()

        self.setLayout(self.layout)
        self.setWindowTitle("Easy Day for a specific date")

    def apply_easy_day_for_specific_date(self):
        config = Config()
        config.load()
        if not config.load_balance:
            tooltip("Please enable load balance first")
            return
        specific_date = self.dateEdit.date().toPyDate()
        current_date = datetime.now().date()
        day_offset = (specific_date - current_date).days
        today = mw.col.sched.today
        specific_due = today + day_offset
        due_days = [specific_due]
        due_in_specific_date_cids = mw.col.db.list(
            f"""SELECT id
            FROM cards
            WHERE data != '' 
            AND json_extract(data, '$.s') IS NOT NULL
            AND CASE WHEN odid==0
            THEN due
            ELSE odue
            END IN {ids2str(due_days)}
            """
        )

        reschedule(
            None,
            recent=False,
            filter_flag=True,
            filtered_cids=set(due_in_specific_date_cids),
            easy_specific_due_dates=[specific_due],
        )


def easy_day_for_sepcific_date(did):
    mw.addEventWidget = EasySpecificDateWidget()
    mw.addEventWidget.show()
