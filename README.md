# FSRS4Anki Helper

FSRS4Anki Helper is an Anki add-on that supports [FSRS4Anki](https://github.com/open-spaced-repetition/fsrs4anki) scheduler. It has six features:
- **Reschedule** cards based on their entire review histories.
- **Postpone** a selected number of due cards.
- **Advance** a selected number of undue cards.
- **Balance** the load during rescheduling (based on fuzz).
- **No Anki** on Free Days (such as weekends) during rescheduling (based on load balance).
- **Disperse** Siblings (cards with the same note) to avoid interference & reminder.

# Requirement

- Anki version >= 2.1.55
- Enable V3 Scheduler
- FSRS4Anki scheduler version >= 3.0.0

# Installation

The FSRS4Anki Helper add-on is purely an added bonus and is not recommended for extensive use. 

Installation link: https://ankiweb.net/shared/info/759844606

# Usage

## Overview

| Feature name      | How does it work?                                            | When should I use it?                                        |
| ----------------- | ------------------------------------------------------------ | ------------------------------------------------------------ |
| Reschedule        | Calculate the stability, difficulty, and the optimum interval from the entire review logs for each card with the weights stored in your FSRS4Anki Scheduler code. | When you update the weights or other parameters in your FSRS4Anki Scheduler code. |
| Advance           | Decreases the intervals of undue cards based on current and requested R, and interval length to minimize damage to long-term learning. | When you want to review your material ahead of time, for example, before a test. |
| Postpone          | Increases the intervals of cards that are due today based on current and requested R, and interval length in a way that minimizes damage to long-term learning. | When you are dealing with a large number of reviews after taking a break from Anki. |
| Load Balancing    | After the optimal interval is calculated, it is adjusted by a random amount to make the distribution of reviews over time more uniform. | Always. This feature makes your workload (reviews/day) more consistent. |
| Free Days         | After the optimal interval is calculated, it is slightly adjusted to change the due date. | If you don't want to study on some days of the week, for example, Sundays. |
| Disperse Siblings | Siblings are cards generated from the same note. Their intervals are adjusted to spread them further apart from each other. | Always. This feature alleviate the interference; disabling it will only decrease the efficiency of spaced repetition. |

## Reschedule

Rescheduling all cards can predict the memory status based on each card's review history and arrange intervals, using the personalized parameters we filled in earlier.

Note: For cards that have been reviewed multiple times using Anki's default algorithm, rescheduling may give different intervals than the Scheduler because the Scheduler can't access the full review history when running. In this case, the intervals given by rescheduling will be more accurate. But afterward, there will be no difference between the two.

## Advance/Postpone

These two functions are very similar, so I'll talk about them together. You can set the number of cards to advance/postpone, and the Helper add-on will sort them in the order of relative advance/postpone, then perform the advance/postpone, ensuring that the deviation from the original review schedule is minimized while meeting the number of cards you set.

## Load Balance

Once the load balance option is enabled, rescheduling will make the daily review load as consistent and smooth as possible.

Here's a comparison, the first graph is rescheduling before enabling it, and the second graph is after enabling:

## Free days

In fact, you can choose any days from Monday to Sunday to take off. Once enabled, the Helper will try to avoid the dates you set for review when rescheduling.

Effect:

## Disperse Siblings

In Anki, some templates will generate multiple cards related in content from the same note, such as reversed cards (Front->Back, Back->Front) and cloze cards (when you make many cloze on the same note). If the review dates of these cards are too close, they may interfere or remind each other. Dispersing siblings can stagger the review dates of these cards as much as possible.

## Advanced Search

In the card browser, you can right-click on the header and click on Difficulty, Stability, Retention to display the current memory status of the card.

It also supports filtering syntax for three attributes, here are some examples:

- s<10: Cards with memory stability less than 10 days
- d=5: Cards with difficulty equal to 5
- r<0.6: Cards with memory retrievability (recall probability) less than 60%

## Advanced Statistics

Hold down the Shift key and click "Stats" to enter the old version of Anki's statistics interface.

Average retention, i.e., average retention rate, reflects the percentage of all cards you have reviewed that you still remember.

Average stability, i.e., average memory stability, reflects the forgetting rate of all cards you have reviewed. The greater the stability, the slower the forgetting rate.

# Mechanism

Please see this wiki page: [FSRS4Anki Helper WIKI](https://github.com/open-spaced-repetition/fsrs4anki-helper/wiki)
