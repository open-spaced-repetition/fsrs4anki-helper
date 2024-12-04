from aqt import (
    QButtonGroup,
    QDate,
    QDateEdit,
    QDateTime,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
    QSlider,
)
from aqt.qt import Qt
from ..utils import *
from ..configuration import Config
from .reschedule import reschedule
from anki.utils import ids2str


def easy_days(did):
    config = Config()
    config.load()
    today = mw.col.sched.today
    due_days = [today + day_offset for day_offset in range(35)]

    # find cards that are due in easy days in the next 35 days
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
        did=None,
        recent=False,
        filter_flag=True,
        filtered_cids=set(due_in_easy_days_cids),
        apply_easy_days=True,
    )
    if fut:
        return fut.result()


# Modified from https://github.com/sam1penny/countdown-to-events/blob/main/src/__init__.py#L86-L169
class EasySpecificDateManagerWidget(QWidget):
    def __init__(self, config: Config):
        super().__init__()
        self.initUi()
        self.config = config
        current_date = sched_current_date()
        self.config.easy_dates = [
            date
            for date in self.config.easy_dates
            if datetime.strptime(date, "%Y-%m-%d").date() >= current_date
        ]
        self.specific_dates = [
            datetime.strptime(date, "%Y-%m-%d").date()
            for date in self.config.easy_dates
        ]
        for specific_date in self.specific_dates:
            deckWidget = DateLabelWidget(specific_date, self)
            self.layout.insertWidget(self.layout.count() - 2, deckWidget)

    def initUi(self):
        self.layout = QVBoxLayout()

        self.dateLabel = QLabel()
        self.dateLabel.setText("Select the Date(s)")
        self.dateEdit = QDateEdit()
        self.dateEdit.setDateTime(QDateTime.currentDateTime())

        self.addDateBtn = QPushButton("Add the Selected Date")
        self.addDateBtn.clicked.connect(self.addEventFunc)

        self.applyEasyDayBtn = QPushButton("Apply Easy Days")
        self.applyEasyDayBtn.clicked.connect(self.apply_easy_day_for_specific_date)

        self.layout.addWidget(self.dateLabel)
        self.layout.addWidget(self.dateEdit)
        self.layout.addWidget(self.addDateBtn)
        self.layout.addWidget(self.applyEasyDayBtn)

        self.layout.addStretch()

        self.setLayout(self.layout)
        self.setWindowTitle("Easy Days for Specific Dates")

    def addEventFunc(self):
        specific_date = self.dateEdit.date().toPyDate()
        if specific_date in self.specific_dates:
            tooltip("This date has already been added")
            return
        if specific_date < sched_current_date():
            tooltip("Easy days can't be applied on past dates.")
            return
        self.specific_dates.append(specific_date)
        self.config.easy_dates = [
            date.strftime("%Y-%m-%d") for date in self.specific_dates
        ]
        deckWidget = DateLabelWidget(specific_date, self)
        self.layout.insertWidget(self.layout.count() - 2, deckWidget)
        mw.deckBrowser.refresh()

    def apply_easy_day_for_specific_date(self):
        if len(self.specific_dates) == 0:
            tooltip("Please add the dates first.")
            return
        specific_dues = []
        current_date = sched_current_date()
        for specific_date in self.specific_dates:
            day_offset = (specific_date - current_date).days
            today = mw.col.sched.today
            specific_due = today + day_offset
            specific_dues.append(specific_due)

        filtered_dues_cids = mw.col.db.list(
            f"""SELECT id
            FROM cards
            WHERE data != '' 
            AND json_extract(data, '$.s') IS NOT NULL
            AND CASE WHEN odid==0
            THEN due
            ELSE odue
            END IN {ids2str(specific_dues)}
            """
        )

        reschedule(
            None,
            recent=False,
            filter_flag=True,
            filtered_cids=set(filtered_dues_cids),
            easy_specific_due_dates=specific_dues,
            apply_easy_days=True,
        )


class DateLabelWidget(QWidget):
    def __init__(self, date, manager):
        super().__init__()
        self.date = date
        self.manager = manager
        self.config = manager.config
        layout = QHBoxLayout()
        self.setLayout(layout)
        self.eventDate = QLabel(date.strftime("%Y-%m-%d"))

        self.deleteButton = QPushButton("Delete")
        self.deleteButton.clicked.connect(self.deleteEvent)

        layout.addWidget(self.eventDate)
        layout.addWidget(self.deleteButton)

    def deleteEvent(self):
        self.config.easy_dates = list(
            filter(
                lambda x: x != self.date.strftime("%Y-%m-%d"), self.config.easy_dates
            )
        )
        self.manager.specific_dates.remove(self.date)
        self.setParent(None)
        mw.deckBrowser.refresh()


def easy_day_for_sepcific_date(did, config: Config):
    mw.EasySpecificDateManagerWidget = EasySpecificDateManagerWidget(config)
    mw.EasySpecificDateManagerWidget.show()
