## Configure in this screen

### `days_to_reschedule`

This sets the number of days in "Reschedule cards reviewed in the last n days"; the current day included(!). Works like [searching for "rated:" in the browser](https://docs.ankiweb.net/searching.html?highlight=rated#answered).

## Configure via menu bar: Tools > FSRS Helper

### `easy_days`

Load Balancing must be enabled for this. Select any day of the week (e.g., Sunday) when you want to spend less time on Anki. It will reduce reviews on the selected day(s) and instead select another day when rescheduling.

### `load_balance`

Fuzz must be enabled for this (default: enabled, set in the scheduler code). During rescheduling, it keeps the daily number consistent instead of fluctuating.
