"""Keep the ledger's voter register and ballot in step with the website."""
import logging

from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .models import Candidate, Position, Voter

logger = logging.getLogger(__name__)


@receiver(post_save, sender=Voter)
@receiver(post_save, sender=Candidate)
@receiver(post_save, sender=Position)
@receiver(post_delete, sender=Candidate)
@receiver(post_delete, sender=Position)
def update_ledger_register(sender, **kwargs):
    from . import ledger
    try:
        ledger.export_register()
    except Exception:
        # The website keeps working even if the ledger folder is not available.
        logger.exception("Could not export the voter register to the ledger")
