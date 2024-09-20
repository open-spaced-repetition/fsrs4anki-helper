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
from aqt.gui_hooks import profile_will_close


def easy_days(did):
    config = Config()
    config.load()
    if not config.load_balance:
        tooltip("Please enable load balance first")
        return
    if (
        all([r == 1 for r in config.easy_days_review_ratio_list])
        and len(config.easy_dates) == 0
    ):
        tooltip("Please select easy days or specific dates first")
        return
    today = mw.col.sched.today
    due_days = []
    for day_offset in range(35):
        if (
            config.easy_days_review_ratio_list[
                (sched_current_date() + timedelta(days=day_offset)).weekday()
            ]
            < 1
            or (sched_current_date() + timedelta(days=day_offset)).strftime("%Y-%m-%d")
            in config.easy_dates
        ):
            due_days.append(today + day_offset)

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
        None,
        recent=False,
        filter_flag=True,
        filtered_cids=set(due_in_easy_days_cids),
        apply_easy_days=True,
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
        if not self.config.load_balance:
            tooltip("Please enable load balance first")
            return
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


class EasyDaysReviewRatioSelector(QWidget):
    def __init__(self, config: Config):
        super().__init__()
        self.config = config
        self.layout = QVBoxLayout()

        self.weekdays = [
            "Monday",
            "Tuesday",
            "Wednesday",
            "Thursday",
            "Friday",
            "Saturday",
            "Sunday",
        ]
        self.modes = ["Normal", "Reduced", "Minimum"]
        self.mode_values = {"Normal": 1.0, "Reduced": 0.5, "Minimum": 0.0}

        self.radio_buttons = {}

        for i, day in enumerate(self.weekdays):
            day_layout = QHBoxLayout()
            day_label = QLabel(day)
            day_layout.addWidget(day_label)

            button_group = QButtonGroup(self)
            for mode in self.modes:
                radio_button = QRadioButton(mode)
                button_group.addButton(radio_button)
                day_layout.addWidget(radio_button)
                current_value = self.config.easy_days_review_ratio_list[i]
                if self.mode_values[mode] == current_value:
                    radio_button.setChecked(True)
                self.radio_buttons[f"{day}_{mode}"] = radio_button

            self.layout.addLayout(day_layout)

        self.saveBtn = QPushButton("Save")
        self.saveBtn.clicked.connect(self.save_settings)
        self.layout.addWidget(self.saveBtn)

        self.setLayout(self.layout)
        self.setWindowTitle("Set the review amount for each day of the week")
        self.resize(400, 250)

    def save_settings(self):
        settings = []
        for day in self.weekdays:
            for mode in self.modes:
                if self.radio_buttons[f"{day}_{mode}"].isChecked():
                    settings.append(self.mode_values[mode])
                    break
            else:
                settings.append(0.5)  # Default value if no mode is selected

        self.config.easy_days_review_ratio_list = settings
        self.close()


def easy_days_review_ratio(did, config: Config):
    mw.easyDaysReviewRatioSelector = EasyDaysReviewRatioSelector(config)
    mw.easyDaysReviewRatioSelector.show()
