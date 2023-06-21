
from aqt import mw

tag = mw.addonManager.addonFromModule(__name__)

# Config
LOAD_BALANCE = "load_balance"
FREE_DAYS = "free_days"
DAYS_TO_RESCHEDULE = "days_to_reschedule"
AUTO_RESCHEDULE_AFTER_SYNC = "auto_reschedule_after_sync"
AUTO_DISPERSE = "auto_disperse"
SAVED_OPTIMIZED_PARAMETERS = "saved_optimized"

# Deck params
RETENTION_IS_NOT_OPTIMIZED = "unoptimized_retention_warning"
REQUEST_RETENTION = "requested_retention"
MAX_INTERVAL = "maximum_interval"
EASY_BONUS = "easy_bonus"
HARD_INTERVAL = "hard_interval"

DEFAULT_PARAMS = {
    "DEFAULT": {
        "name": "global config for FSRS4Anki",
        "w": [1, 1, 5, -0.5, -0.5, 0.2, 1.4, -0.12, 0.8, 2, -0.2, 0.2, 1],
        REQUEST_RETENTION: 0.9,
        MAX_INTERVAL: 36500,
        EASY_BONUS: 1.3,
        HARD_INTERVAL: 1.2,
        RETENTION_IS_NOT_OPTIMIZED: False,
    }
}

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
    def auto_disperse(self):
        return self.data[AUTO_DISPERSE]

    @auto_disperse.setter
    def auto_disperse(self, value):
        self.data[AUTO_DISPERSE] = value
        self.save()

    @property
    def saved_optimized(self):
        return self.data.get(SAVED_OPTIMIZED_PARAMETERS, DEFAULT_PARAMS)

    @saved_optimized.setter
    def saved_optimized(self, value):
        self.data[SAVED_OPTIMIZED_PARAMETERS] = value
        self.save()

    @staticmethod
    def result_string(result: dict[str]):
        """Produce the pasteable config for a singular result"""
        return \
f"""    {{
        // Generated, Optimized anki deck settings
        "deckName": "{result["name"]}",
        "w": {result["w"]},
        "requestRetention": {result[REQUEST_RETENTION]}, {"//Un-optimized, Replace this with desired number." if result[RETENTION_IS_NOT_OPTIMIZED] else ""}
        "maximumInterval": {result[MAX_INTERVAL]},
        "easyBonus": {result[EASY_BONUS]},
        "hardInterval": {result[HARD_INTERVAL]},
    }},"""

    def results_string(self):
        """Get the config for every result"""
        self.load()
        results = '\n'.join(self.result_string(a) for a in self.saved_optimized.values())
    
        return \
f"""// Copy this into your optimizer code.
// You can edit these values in the addon's config.
// The full optimizer you need to paste this into can be found here
// https://github.com/open-spaced-repetition/fsrs4anki/blob/main/fsrs4anki_scheduler.js

const deckParams = [
{results}
]
"""
