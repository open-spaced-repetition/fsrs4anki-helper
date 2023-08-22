
from aqt.gui_hooks import reviewer_did_answer_card
from .reschedule import reschedule_when_review
from .disperse_siblings import disperse_siblings_when_review


def reschedule_and_disperse_siblings_when_review(reviewer, card, ease):
    undo_entry = reschedule_when_review(reviewer, card, ease)
    disperse_siblings_when_review(reviewer, card, ease, undo_entry)


def init_review_hook():
    reviewer_did_answer_card.append(reschedule_and_disperse_siblings_when_review)