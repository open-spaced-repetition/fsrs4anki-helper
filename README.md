# FSRS4Anki Helper

FSRS4Anki Helper is an Anki add-on that supports [FSRS4Anki](https://github.com/open-spaced-repetition/fsrs4anki) scheduler. It has six features:

- **Reschedule** cards based on their entire review histories.
- **Postpone** a selected number of due cards.
- **Advance** a selected number of undue cards.
- **Balance** the load during rescheduling (based on fuzz).
- **No Anki** on Free Days (such as weekends) during rescheduling (based on load balance).
- **Disperse** Siblings (cards with the same note) to avoid interference & reminder.

# Requirements

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
| Reschedule        | Calculates the stability, difficulty, and the optimum interval from the entire review logs for each card with the weights stored in your FSRS4Anki Scheduler code. Then, it replaces the current due dates with the calculated ones. | When you update the weights or other parameters in your FSRS4Anki Scheduler code. |
| Advance           | Decreases the intervals of undue cards based on current and requested R, and interval length to minimize damage to long-term learning. | When you want to review your material ahead of time, for example, before a test. |
| Postpone          | Increases the intervals of cards that are due today based on current and requested R, and interval length in a way that minimizes damage to long-term learning. | When you are dealing with a large number of reviews after taking a break from Anki or after rescheduling. |
| Load Balancing    | After the optimal interval is calculated, it is adjusted by a random amount to make the distribution of reviews over time more uniform. | Always. This feature makes your workload (reviews per day) more consistent. |
| Free Days         | After the optimal interval is calculated, it is slightly adjusted to change the due date. | If you don't want to study on some days of the week, for example, Sundays. |
| Disperse Siblings | Siblings are cards generated from the same note. Their intervals are adjusted to spread them further apart from each other. | Always. This feature alleviates the interference; disabling it will only decrease the efficiency of spaced repetition. |

## Reschedule

Rescheduling all cards can predict the memory status based on each card's review history and arrange intervals, using the parameters from the Scheduler code. These parameters can be personalized with the FSRS Optimizer.

**Note**: For cards that have been reviewed multiple times using Anki's default algorithm, rescheduling may give different intervals than the Scheduler because the Scheduler can't access the full review history when running. In this case, the intervals given by rescheduling will be more accurate. But after rescheduling once, there will be no difference between the two.

![image](https://github.com/open-spaced-repetition/fsrs4anki-helper/assets/32575846/d59f5fef-ebe0-4741-bce6-941e9d6db7cf)

## Advance/Postpone

These two functions are very similar, so I'll talk about them together. You can set the number of cards to advance/postpone, and the Helper add-on will sort your cards and perform the advance/postpone in such a way that the deviation from the original review schedule is minimal while meeting the number of cards you set.

![image](https://github.com/open-spaced-repetition/fsrs4anki-helper/assets/32575846/7dec9dc6-d6f7-44b0-a845-ae4b9605073d)

![image](https://github.com/open-spaced-repetition/fsrs4anki-helper/assets/32575846/f9838010-cb00-44ce-aefc-10300f2a586e)

## Load Balance

Once the load balance option is enabled, rescheduling will make the daily review load as consistent and smooth as possible.

![image](https://github.com/open-spaced-repetition/fsrs4anki-helper/assets/32575846/96f8bd20-0421-4138-8b58-00abbcb3e6d0)

Here's a comparison, the first graph is rescheduling before enabling it, and the second graph is after enabling:

![image](https://github.com/open-spaced-repetition/fsrs4anki-helper/assets/32575846/1f31491c-7ee6-4eed-ab4a-7bc0dba5dff8)

![image](https://github.com/open-spaced-repetition/fsrs4anki-helper/assets/32575846/1c4f430d-824b-4145-801e-68fc0329fbbd)

## Free days

You can choose any day or days from Monday to Sunday to take off. Once enabled, the Helper will try to avoid these days when rescheduling.

![image](https://github.com/open-spaced-repetition/fsrs4anki-helper/assets/32575846/798dc25c-f06c-40fe-8866-ac28c8392273)

**Effect**:

![image](https://github.com/open-spaced-repetition/fsrs4anki-helper/assets/32575846/7fe6b4d0-ae99-40f8-8bd9-0f7c3ff1c638)

## Disperse Siblings

In Anki, some templates will generate multiple cards related in content from the same note, such as reversed cards (Front->Back, Back->Front) and cloze cards (when you make multiple clozes on the same note). If the review dates of these cards are too close, they may interfere with or remind you of each other. Dispersing siblings can spread the review dates of these cards out as much as possible.

![image](https://github.com/open-spaced-repetition/fsrs4anki-helper/assets/32575846/2e87b9c7-136d-4dc8-8677-c81bc28a0f6b)

## Advanced Search

In the card browser, you can right-click on the header and click on Difficulty, Stability, Retention to display the current memory states of cards.

![image](https://github.com/open-spaced-repetition/fsrs4anki-helper/assets/32575846/7fb2b357-19d0-45fb-9cc0-f925258a6280)

The Helper also adds [search syntax](https://docs.ankiweb.net/searching.html) for these three attributes, here are some examples:

- s<10: Cards with memory stability less than 10 days
- d=5: Cards with difficulty equal to 5
- r<0.6: Cards with memory retrievability (recall probability) less than 60%

## Advanced Statistics

Hold down the Shift key and click "Stats" to enter the old version of Anki's statistics interface.

![image](https://github.com/open-spaced-repetition/fsrs4anki-helper/assets/32575846/db368bcb-54a5-4ca2-bc14-acad382f643f)

The FSRS Stats are based on all cards in your deck or collection (whichever is selected) that you have ever reviewed. They remain unaffected by the 1 month/year settings.

Definitions:

- Total **burden**, as defined by Piotr Woźniak here: https://supermemo.guru/wiki/Burden
- The three component of the memory model used by FSRS:
	- Average **retention** reflects the percentage of cards that you would recall correctly if you were tested today.
	- Average (memory) **stability** reflects how fast you forget (forgetting rate). The greater the stability, the slower the forgetting rate.
	- **Difficulty** reflects how hard it is to increase or maintain the stability of a memory. The relative difficulty distribution within the deck/collection can be viewed at the bottom of the statistics interface:
    [screenshot of Difficulty Distribution]

# Mechanism

Please see this wiki page: [FSRS4Anki Helper WIKI](https://github.com/open-spaced-repetition/fsrs4anki-helper/wiki)
