from aqt import mw

tag = mw.addonManager.addonFromModule(__name__)

EASY_DATES = "easy_dates"
DAYS_TO_RESCHEDULE = "days_to_reschedule"
AUTO_RESCHEDULE_AFTER_SYNC = "auto_reschedule_after_sync"
AUTO_DISPERSE_AFTER_SYNC = "auto_disperse_after_sync"
AUTO_DISPERSE_WHEN_REVIEW = "auto_disperse_when_review"
AUTO_DISPERSE_AFTER_RESCHEDULE = "auto_disperse_after_reschedule"
MATURE_IVL = "mature_ivl"
RESCHEDULE_THRESHOLD = "reschedule_threshold"
DEBUG_NOTIFY = "debug_notify"
FSRS_STATS = "fsrs_stats"
DISPLAY_MEMORY_STATE = "display_memory_state"
HAS_RATED = "has_rated"
HAS_SPONSORED = "has_sponsored"
SHOW_STEPS_STATS = "show_steps_stats"


def load_config():
    return mw.addonManager.getConfig(tag)


def save_config(data):
    mw.addonManager.writeConfig(tag, data)


def run_on_configuration_change(function):
    mw.addonManager.setConfigUpdatedAction(__name__, lambda *_: function())


class Config:
    def load(self):
        self.data = load_config()

    def save(self):
        save_config(self.data)

    @property
    def easy_dates(self) -> list[str]:
        return self.data[EASY_DATES]

    @easy_dates.setter
    def easy_dates(self, value):
        self.data[EASY_DATES] = value
        self.save()

    @property
    def days_to_reschedule(self):
        return self.data[DAYS_TO_RESCHEDULE]

    @days_to_reschedule.setter
    def days_to_reschedule(self, value):
        self.data[DAYS_TO_RESCHEDULE] = value
        self.save()

    @property
    def auto_reschedule_after_sync(self):
        return self.data[AUTO_RESCHEDULE_AFTER_SYNC]

    @auto_reschedule_after_sync.setter
    def auto_reschedule_after_sync(self, value):
        self.data[AUTO_RESCHEDULE_AFTER_SYNC] = value
        self.save()

    @property
    def auto_disperse_after_sync(self):
        return self.data[AUTO_DISPERSE_AFTER_SYNC]

    @auto_disperse_after_sync.setter
    def auto_disperse_after_sync(self, value):
        self.data[AUTO_DISPERSE_AFTER_SYNC] = value
        self.save()

    @property
    def auto_disperse_when_review(self):
        return self.data[AUTO_DISPERSE_WHEN_REVIEW]

    @auto_disperse_when_review.setter
    def auto_disperse_when_review(self, value):
        self.data[AUTO_DISPERSE_WHEN_REVIEW] = value
        self.save()

    @property
    def auto_disperse_after_reschedule(self):
        return self.data[AUTO_DISPERSE_AFTER_RESCHEDULE]

    @auto_disperse_after_reschedule.setter
    def auto_disperse_after_reschedule(self, value):
        self.data[AUTO_DISPERSE_AFTER_RESCHEDULE] = value
        self.save()

    @property
    def mature_ivl(self):
        return self.data[MATURE_IVL]

    @mature_ivl.setter
    def mature_ivl(self, value):
        self.data[MATURE_IVL] = value
        self.save()

    @property
    def reschedule_threshold(self):
        return self.data[RESCHEDULE_THRESHOLD]

    @reschedule_threshold.setter
    def reschedule_threshold(self, value):
        self.data[RESCHEDULE_THRESHOLD] = value
        self.save()

    @property
    def debug_notify(self):
        return self.data[DEBUG_NOTIFY]

    @debug_notify.setter
    def debug_notify(self, value):
        self.data[DEBUG_NOTIFY] = value
        self.save()

    @property
    def fsrs_stats(self):
        return self.data[FSRS_STATS]

    @fsrs_stats.setter
    def fsrs_stats(self, value):
        self.data[FSRS_STATS] = value
        self.save()

    @property
    def display_memory_state(self):
        return self.data[DISPLAY_MEMORY_STATE]

    @display_memory_state.setter
    def display_memory_state(self, value):
        self.data[DISPLAY_MEMORY_STATE] = value
        self.save()

    @property
    def has_rated(self):
        return self.data[HAS_RATED]

    @has_rated.setter
    def has_rated(self, value):
        self.data[HAS_RATED] = value
        self.save()

    @property
    def has_sponsored(self):
        return self.data[HAS_SPONSORED]

    @has_sponsored.setter
    def has_sponsored(self, value):
        self.data[HAS_SPONSORED] = value
        self.save()

    @property
    def show_steps_stats(self):
        return self.data[SHOW_STEPS_STATS]

    @show_steps_stats.setter
    def show_steps_stats(self, value):
        self.data[SHOW_STEPS_STATS] = value
        self.save()
