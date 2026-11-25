"""Casting a ballot: shared by the classic pages and the new portal interface."""
import json

from django.db import transaction

from . import ledger
from .models import LedgerReceipt, Voter, Votes


class CastResult:
    def __init__(self, ok, message, block=None, answers=None):
        self.ok, self.message, self.block, self.answers = ok, message, block, answers or []


def cast_ballot(voter, selections):
    """Put a validated ballot on the ledger, then save it in the website database.

    selections: [(Position, [Candidate, ...]), ...]. The vote is saved here only
    when at least one ledger node accepted it, so the two can always be compared.
    """
    if not selections:
        return CastResult(False, "Please select at least one candidate")
    if Voter.objects.filter(pk=voter.pk, voted=True).exists():
        return CastResult(False, "You have voted already")

    recorded, block, answers = ledger.record_ballot(voter, selections)
    if not recorded:
        if all(status == "down" for _, status, _ in answers):
            return CastResult(False, "The election ledger is not reachable right now. "
                                     "Your vote was not recorded; please try again.", answers=answers)
        reasons = sorted({str(info) for _, status, info in answers if status == "rejected"})
        if reasons == ["already voted"]:
            return CastResult(False, "The election ledger already holds a ballot from you. "
                                     "Your first ballot stands and cannot be changed.", answers=answers)
        return CastResult(False, "The election ledger rejected this ballot: " + ", ".join(reasons), answers=answers)

    with transaction.atomic():
        # Lock the voter row so two concurrent submissions cannot both vote
        locked = Voter.objects.select_for_update().get(pk=voter.pk)
        if locked.voted:
            return CastResult(False, "You have voted already")
        LedgerReceipt.objects.update_or_create(
            voter=locked, defaults={'block': block, 'answers': json.dumps(answers)})
        Votes.objects.bulk_create([
            Votes(voter=locked, position=position, candidate=candidate)
            for position, candidates in selections
            for candidate in candidates
        ])
        locked.voted = True
        locked.save(update_fields=['voted'])
    return CastResult(True, "Thanks for voting", block, answers)
