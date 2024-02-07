from aqt import (
    QDate,
    QDateEdit,
    QDateTime,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
    QSlider,
)
from aqt.qt import Qt
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
    for day_offset in range(35):
        if (
            config.easy_days_review_ratio > 0
            or (datetime.now() + timedelta(days=day_offset)).weekday()
            in config.easy_days
        ):
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
class EasySpecificDateManagerWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.initUi()
        self.specific_dates = []

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
        if specific_date < datetime.now().date():
            tooltip("Easy days can't be applied on past dates.")
            return
        self.specific_dates.append(specific_date)
        deckWidget = DateLabelWidget(specific_date, self)
        self.layout.insertWidget(self.layout.count() - 2, deckWidget)
        mw.deckBrowser.refresh()

    def apply_easy_day_for_specific_date(self):
        config = Config()
        config.load()
        if not config.load_balance:
            tooltip("Please enable load balance first")
            return
        if len(self.specific_dates) == 0:
            tooltip("Please add the dates first.")
            return
        specific_dues = []
        filtered_dues = []
        current_date = datetime.now().date()
        for specific_date in self.specific_dates:
            day_offset = (specific_date - current_date).days
            today = mw.col.sched.today
            specific_due = today + day_offset
            specific_dues.append(specific_due)
            filtered_dues.extend(
                [specific_due + i + max(0, 4 - day_offset) for i in range(-4, 5)]
            )
        filtered_dues = list(set(filtered_dues))

        filtered_dues_cids = mw.col.db.list(
            f"""SELECT id
            FROM cards
            WHERE data != '' 
            AND json_extract(data, '$.s') IS NOT NULL
            AND CASE WHEN odid==0
            THEN due
            ELSE odue
            END IN {ids2str(filtered_dues)}
            """
        )

        reschedule(
            None,
            recent=False,
            filter_flag=True,
            filtered_cids=set(filtered_dues_cids),
            easy_specific_due_dates=specific_dues,
        )


class DateLabelWidget(QWidget):
    def __init__(self, date, manager):
        super().__init__()
        self.manager = manager
        self.date = date
        layout = QHBoxLayout()
        self.setLayout(layout)
        self.eventDate = QLabel(date.strftime("%Y-%m-%d"))

        self.deleteButton = QPushButton("Delete")
        self.deleteButton.clicked.connect(self.deleteEvent)

        layout.addWidget(self.eventDate)
        layout.addWidget(self.deleteButton)

    def deleteEvent(self):
        self.manager.specific_dates.remove(self.date)
        self.setParent(None)
        mw.deckBrowser.refresh()


def easy_day_for_sepcific_date(did):
    mw.EasySpecificDateManagerWidget = EasySpecificDateManagerWidget()
    mw.EasySpecificDateManagerWidget.show()


class EasyDaysReviewRatioSlider(QWidget):
    def __init__(self, config: Config):
        super().__init__()
        self.config = config
        self.layout = QVBoxLayout()
        self.slider = QSlider(orientation=Qt.Orientation.Horizontal)
        self.slider.setMinimum(0)
        self.slider.setMaximum(9)
        self.slider.setValue(self.config.easy_days_review_ratio * 10)
        self.slider.valueChanged.connect(self.slider_value_changed)

        self.labelStart = QLabel("0%")
        self.labelEnd = QLabel("90%")
        self.labelValue = QLabel(
            f"current percentage: {int(self.config.easy_days_review_ratio * 100)}%"
        )

        self.saveBtn = QPushButton("Save")
        self.saveBtn.clicked.connect(self.save_ratio)

        sliderLayout = QHBoxLayout()
        sliderLayout.addWidget(self.labelStart)
        sliderLayout.addWidget(self.slider)
        sliderLayout.addWidget(self.labelEnd)

        saveBtnLayout = QHBoxLayout()
        saveBtnLayout.addWidget(self.labelValue)
        saveBtnLayout.addWidget(self.saveBtn)

        self.layout.addLayout(sliderLayout)
        self.layout.addLayout(saveBtnLayout)

        self.layout.addStretch()

        self.setLayout(self.layout)
        self.setWindowTitle("Set Easy Days Review Percentage")

    def slider_value_changed(self):
        value = max(0, min(round(self.slider.value() / 10, 1), 0.9))
        self.labelValue.setText(f"current percentage: {int(value * 100)}%")
        self.config.easy_days_review_ratio = value

    def save_ratio(self):
        value = max(0, min(round(self.slider.value() / 10, 1), 0.9))
        self.config.easy_days_review_ratio = value
        tooltip(f"Easy Days Review Percentage: {int(value * 100)}% saved successfully")
        self.close()


def easy_days_review_ratio(did, config: Config):
    mw.easyDaysReviewRatioSlider = EasyDaysReviewRatioSlider(config)
    mw.easyDaysReviewRatioSlider.show()
