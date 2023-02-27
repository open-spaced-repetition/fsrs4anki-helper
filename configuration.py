
from aqt import mw

tag = mw.addonManager.addonFromModule(__name__)

LOAD_BALANCE = "load_balance"
FREE_DAYS = "free_days"


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
