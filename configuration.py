from aqt import mw

tag = mw.addonManager.addonFromModule(__name__)

LOAD_BALANCE = "load_balance"
FREE_DAYS = "free_days"
DAYS_TO_RESCHEDULE = "days_to_reschedule"
AUTO_RESCHEDULE_AFTER_SYNC = "auto_reschedule_after_sync"
AUTO_DISPERSE_AFTER_SYNC = "auto_disperse_after_sync"
AUTO_DISPERSE = "auto_disperse"
MATURE_IVL = "mature_ivl"
DEBUG_NOTIFY = "debug_notify"
FSRS_STATS = "fsrs_stats"


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
    def load_balance(self):
        return self.data[LOAD_BALANCE]

    @load_balance.setter
    def load_balance(self, value):
        self.data[LOAD_BALANCE] = value
        self.save()

    @property
    def free_days(self):
        return self.data[FREE_DAYS]

    @free_days.setter
    def free_days(self, day_enable):
        day, enable = day_enable
        if enable:
            self.data[FREE_DAYS] = sorted(set(self.data[FREE_DAYS] + [day]))
        else:
            if day in self.data[FREE_DAYS]:
                self.data[FREE_DAYS].remove(day)
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
    def auto_disperse(self):
        return self.data[AUTO_DISPERSE]

    @auto_disperse.setter
    def auto_disperse(self, value):
        self.data[AUTO_DISPERSE] = value
        self.save()

    @property
    def mature_ivl(self):
        return self.data[MATURE_IVL]

    @mature_ivl.setter
    def mature_ivl(self, value):
        self.data[MATURE_IVL] = value
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
