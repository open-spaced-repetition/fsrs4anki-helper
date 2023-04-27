# FSRS4Anki Helper

FSRS4Anki Helper is an Anki add-on that supports [FSRS4Anki](https://github.com/open-spaced-repetition/fsrs4anki) scheduler. It has five features:
- **Reschedule** cards based on their entire review histories.
- **Postpone** due cards whose retention is higher than your target.
- **Advance** undue cards whose retention is lower than your target.
- **Balance** the load during rescheduling (based on fuzz).
- **No Anki** on Free Days (such as weekends) during rescheduling (based on load balance).
- **Disperse** Siblings (cards with the same note) to avoid interference & reminder.

## Requirement

- Anki version >= 2.1.55
- Enable V3 Scheduler
- FSRS4Anki scheduler version >= 3.0.0

## Installation

The easiest way to install FSRS4Anki Helper is through AnkiWeb: https://ankiweb.net/shared/info/759844606

## Usage

### Reschedule

Set parameters for your FSRS4Anki scheduler. Then click `Tools -> FSRS4Anki Helper -> Reschedule all cards (Ctrl+R)`:

![image](https://user-images.githubusercontent.com/32575846/234739908-336eda6f-11db-4db7-96c5-7e1fdb280119.png)

It will calculate the memory state by considering each card's full review history and then reschedules the review interval and due.

If the number of your revlogs exceeds 10k, the process may be time-consuming. So I don't recommend rescheduling all cards too much. Just use it after you modified the parameters.

It may induce backlog when your first rescheduling. If you feel uncomfortable, please use `Postpone` or set a lower `requestedRetention`.

If you only want to reschedule a specific deck, you can click `Reschedule cards` in the options menu (gear icon in the right side of each deck).

![image](https://user-images.githubusercontent.com/32575846/234741376-ac88bb39-c7be-40ea-b7cb-dbd7d1ac148e.png)

#### Reschedule cards reviewed in the last X days

Due to the poor performance of rescheduling, I develop this feature. It filters the cards reviewed recently, so it is pretty fast.

![image](https://user-images.githubusercontent.com/32575846/234741784-58510653-7c19-4f8c-a9e5-a8a466503e50.png)

You can configure the X in the config of FSRS4Anki Helper add-on.

![image](https://user-images.githubusercontent.com/32575846/234742188-9ee70dd8-009f-4371-a47d-d23282a7b2f2.png)

#### Auto reschedule recent reviews after sync

Many people use AnkiDroid which haven't supported FSRS. This feature can filter the cards reviewed in other devices after sync and auto apply rescheduling to them.

![image](https://user-images.githubusercontent.com/32575846/234742500-c5bc748d-5f5e-4307-a27b-346edb0ae1d2.png)

### Postpone & Advance

These features can apply a temporary `requestedRetention` to cards which have been scheduled or rescheduled by FSRS. It doesn't modify the `requestedRetention` in the custom scheduling code.

![image](https://user-images.githubusercontent.com/32575846/234742970-4733a244-aaad-4fab-9434-726ffac8b280.png)

![image](https://user-images.githubusercontent.com/32575846/234743037-53a0d0bb-0ee5-4da4-984b-68a99b949c04.png)

### Load Balance & No Anki

Load Balance can smooth the number of reviews per day during rescheduling. But it doesn't guarantee perfect balance within a single rescheduling. It would have a smoother load after each rescheduling. This feature does render the rescheduling process more time-intensive.

No Anki can avoid configured days of week when rescheduling. But it doesn't guarantee perfect avoidance because it should consider the fuzz range of cards.

![image](https://user-images.githubusercontent.com/32575846/234743512-8a0761e1-cc2a-49d4-9f8e-1b37d23291be.png)

### Disperse Siblings

Disperse Siblings can reschedule the date of siblings (cards from same note) to avoid showing them too closely.

![image](https://user-images.githubusercontent.com/32575846/234745480-78d43334-0822-475a-a9ed-f3966cebc448.png)

## Mechanism

Please see this wiki page: [FSRS4Anki Helper WIKI](https://github.com/open-spaced-repetition/fsrs4anki-helper/wiki)
