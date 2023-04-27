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

![image](https://user-images.githubusercontent.com/32575846/218268780-1c757764-bd2b-42ba-8fab-3f42f526fdb4.png)

If you only want to reschedule a specific deck, you can click `Reschedule cards in deck`.

![image](https://user-images.githubusercontent.com/32575846/218268855-b3f42550-538d-43d1-a711-daf111e74ddb.png)

### Postpone

![image](https://user-images.githubusercontent.com/32575846/218268927-b47050d0-bf4f-4ebd-b84f-c51b28e00012.png)

![image](https://user-images.githubusercontent.com/32575846/218268959-ee1f49d7-b41e-4de9-8d65-25fecb63474f.png)

### Advance

![image](https://user-images.githubusercontent.com/32575846/218268901-8b735296-fea4-426d-949e-11b1f3a410a8.png)

![image](https://user-images.githubusercontent.com/32575846/218268974-4d6f8983-24c5-48aa-b942-b3f82a05ec37.png)

### Load Balance & Free Weekend

![image](https://user-images.githubusercontent.com/32575846/218268644-7432790e-4665-430d-aa22-5826700e17bd.png)

### Disperse Siblings

## Mechanism

Please see this wiki page: [FSRS4Anki Helper WIKI](https://github.com/open-spaced-repetition/fsrs4anki-helper/wiki)