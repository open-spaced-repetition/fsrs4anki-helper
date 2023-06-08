# FSRS4Anki Helper

FSRS4Anki Helper is an Anki add-on that supports [FSRS4Anki](https://github.com/open-spaced-repetition/fsrs4anki) scheduler. It has six features:
- **Reschedule** cards based on their entire review histories.
- **Postpone** a selected number of due cards.
- **Advance** a selected number of undue cards.
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

### Overview

| Feature name      | How does it work?                                            | When should I use it?                                        |
| ----------------- | ------------------------------------------------------------ | ------------------------------------------------------------ |
| Reschedule        | Calculate the stability, difficulty, and the optimum interval from the entire review logs for each card with the weights stored in your FSRS4Anki Scheduler code. | When you update the weights or other parameters in your FSRS4Anki Scheduler code. |
| Postpone          | Increases the intervals of cards that are due today based on current and requested R, relative overdue-ness, and interval length in a way that minimizes damage to long-term learning. | When you are dealing with a large number of reviews after taking a break from Anki. |
| Advance           | Decreases the intervals of undue cards based on current and requested R, relative overdue-ness, and interval length to minimize damage to long-term learning. | When you want to review your material ahead of time, for example, before a test. |
| Free Days         | After the optimal interval is calculated, it is slightly adjusted to change the due date. | If you don't want to study on some days of the week, for example, Sundays. |
| Disperse Siblings | Siblings are cards generated from the same note. Their intervals are adjusted to spread them further apart from each other. | Always. This feature alleviate the interference; disabling it will only decrease the efficiency of spaced repetition. |
| Load Balancing    | After the optimal interval is calculated, it is adjusted by a random amount to make the distribution of reviews over time more uniform. | Always. This feature makes your workload (reviews/day) more consistent. |

### Reschedule

Set parameters for your FSRS4Anki scheduler. Then click `Tools -> FSRS4Anki Helper -> Reschedule all cards`:

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

These features can be used to postpone or advance a selected number of cards. Postpone is useful to deal with a backlog. Advance is useful to review your cards before a large exam or before going on a vacation. Remember that every time you use Postpone or Advance, you depart from the optimal scheduling. So, using this feature often is not recommended.

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
