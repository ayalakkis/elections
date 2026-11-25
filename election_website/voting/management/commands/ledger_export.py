from django.core.management.base import BaseCommand

from voting import ledger


class Command(BaseCommand):
    help = "Create ledger keys for every voter and write voters.json and election.json for the nodes."

    def handle(self, *args, **options):
        if ledger.export_register():
            self.stdout.write(self.style.SUCCESS("Register and ballot written to " + str(ledger.settings.LEDGER_DIR)))
        else:
            self.stderr.write("Ledger folder not found: " + str(ledger.settings.LEDGER_DIR))
