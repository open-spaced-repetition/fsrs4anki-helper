from aqt.gui_hooks import reviewer_did_answer_card
from .disperse_siblings import disperse_siblings_when_review


def init_review_hook():
    reviewer_did_answer_card.append(disperse_siblings_when_review)
