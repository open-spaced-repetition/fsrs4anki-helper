## Configure in this screen

### `days_to_reschedule`

Default: `7`

This sets the number of days in "Reschedule cards reviewed in the last n days"; the current day included(!). Works like [searching for "rated:" in the browser](https://docs.ankiweb.net/searching.html?highlight=rated#answered).

### `easy_dates`

Default: `[]`

A list of specific dates (in `YYYY-MM-DD` format) that should be treated as easy days. Cards due on these dates will be rescheduled to avoid those days. You can manage these dates through Tools → FSRS Helper → Less Anki on Easy Days → Apply easy days for specific dates, which opens a window where you can add, remove, and apply easy days for specific dates.

### `auto_reschedule_after_sync`

Default: `false`

When enabled, cards reviewed on other devices (that don't support FSRS, such as AnkiDroid or AnkiWeb) will be automatically rescheduled according to the FSRS algorithm after syncing. It is recommended to sync daily for the best results if you rely on this feature.

### `auto_disperse_after_sync`

Default: `false`

When enabled, siblings of cards reviewed on other devices will be automatically dispersed after syncing. **Note:** This option is ignored if both `auto_reschedule_after_sync` and `auto_disperse_after_reschedule` are enabled, because the siblings will be dispersed automatically after the rescheduling operation completes.

### `auto_disperse_when_review`

Default: `false`

When enabled, siblings will be automatically dispersed after each review. **Warning:** This can cause constant queue rebuilding, which slows down Anki and breaks Display Order settings.

### `auto_disperse_after_reschedule`

Default: `false`

When enabled, siblings will be automatically dispersed after rescheduling operations complete. This is useful to ensure siblings remain properly spaced after cards have been rescheduled.

### `mature_ivl`

Default: `21`

The interval threshold (in days) used to distinguish between "young" and "mature" cards in statistics. Cards with intervals greater than or equal to this value are considered mature. This setting affects the True Retention statistics display.

### `reschedule_threshold`

Default: `0`

A threshold value (between 0 and 1) that controls when cards should be rescheduled. If set to a value greater than 0, cards whose current interval falls within a calculated range (based on desired retention and the threshold) will be skipped during rescheduling. This helps avoid unnecessary rescheduling of cards that are already close to optimal.

The threshold works by calculating an interval range around the optimal interval:
- Lower bound: calculated using a desired retention derived from `(1 + threshold) * odds`, which results in a higher desired retention and thus a shorter interval
- Upper bound: calculated using a desired retention derived from `(1 - threshold) * odds`, which results in a lower desired retention and thus a longer interval
- If the card's current interval falls within this range `[lower_bound, upper_bound]`, it is skipped

**Note:** This threshold is only applied when rescheduling normally. It is ignored when applying easy days or during auto-reschedule after sync.

- `0`: Reschedule all cards (default)
- `0.1`: Skip cards if their interval is within the calculated range around optimal
- Higher values: Skip more cards (wider range)

### `reschedule-set-due-date`

Default: `false`

When enabled, rescheduling will include cards that have manually set due dates (cards whose last revlog entry is type = 4, which represents manual scheduling). By default (`false`), these cards are skipped during rescheduling to preserve manually set schedules.

### `display_memory_state`

Default: `false`

When enabled, displays the current Difficulty (D), Stability (S), and Retrievability (R) values below the answer buttons after each review.

### `show_steps_stats`

Default: `false`

When enabled, adds the Steps Stats section to the statistics page, which helps fine-tune your (re)learning steps.

### `show_true_retention`

Default: `true`

When enabled, adds the True Retention section to the statistics page. True retention is the pass rate calculated only on cards with intervals greater than or equal to one day. **Note:** This table may slow down the statistics page loading if you have a lot of reviews.

### `fsrs_stats`

Default: `true`

When enabled, displays FSRS Stats in the statistics page, including Daily Load, average retention, and average stability.

### `debug_notify`

Default: `false`

When enabled, shows debug notifications during sibling dispersion operations. This displays information about cards that are too close together and cannot be properly dispersed. This is mainly for development and troubleshooting purposes.

### `has_rated`

Default: `false`

Internal flag used to track whether the user has rated the add-on. This is automatically managed by the add-on and should not be modified manually.
