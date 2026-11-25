"""Create a small student council election for the demonstration.

Accounts (local demo only):
    admin:  admin@university.test   password: AdminDemo#2026
    voters: student1@university.test ... student8@university.test   password: StudentDemo#2026
"""
import io

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from PIL import Image, ImageDraw

from account.models import CustomUser
from voting import ledger
from voting.models import Candidate, Position, Voter

ADMIN_EMAIL, ADMIN_PASSWORD = "admin@university.test", "AdminDemo#2026"
VOTER_PASSWORD = "StudentDemo#2026"
STUDENTS = ["Rami Haddad", "Lina Khoury", "Omar Saleh", "Maya Nassar", "Karim Aoun", "Nour Fares", "Hadi Zein", "Sara Mansour"]
BALLOT = [
    ("President", 1, [("Ali Hamdan", "Fourth year computer science. Wants longer library hours."),
                      ("Rana Itani", "Third year engineering. Wants more student clubs.")]),
    ("Vice President", 1, [("Jad Karam", "Second year business. Focus on transport."),
                           ("Dana Sleiman", "Third year law. Focus on student rights.")]),
    ("Council Member", 2, [("Tarek Bazzi", "Sports and events."), ("Yara Chami", "Mental health support."),
                           ("Fadi Rizk", "Cheaper cafeteria.")]),
]


def avatar(name, colour):
    img = Image.new("RGB", (200, 200), colour)
    draw = ImageDraw.Draw(img)
    initials = "".join(part[0] for part in name.split()[:2])
    draw.text((100, 104), initials, fill="white", font_size=84, anchor="mm")
    out = io.BytesIO()
    img.save(out, format="PNG")
    return ContentFile(out.getvalue(), name=name.replace(" ", "_").lower() + ".png")


class Command(BaseCommand):
    help = "Create the demo admin, voters, positions and candidates, then export the ledger register."

    def handle(self, *args, **options):
        if not CustomUser.objects.filter(email=ADMIN_EMAIL).exists():
            CustomUser.objects.create_superuser(email=ADMIN_EMAIL, password=ADMIN_PASSWORD)
        for i, full in enumerate(STUDENTS, start=1):
            first, last = full.split()
            email = "student%d@university.test" % i
            if CustomUser.objects.filter(email=email).exists():
                continue
            user = CustomUser.objects.create_user(email=email, password=VOTER_PASSWORD, user_type='2',
                                                  first_name=first, last_name=last)
            Voter.objects.create(admin=user, phone="0700000000%d" % i)
        colours = ["#2F5D8C", "#B03A2E", "#2E7D4F", "#B7791F", "#6B4C9A", "#1F7A8C", "#8C2F5D"]
        n = 0
        for priority, (pname, max_vote, candidates) in enumerate(BALLOT, start=1):
            position, _ = Position.objects.get_or_create(name=pname, defaults={"max_vote": max_vote, "priority": priority})
            for fullname, bio in candidates:
                if not Candidate.objects.filter(fullname=fullname, position=position).exists():
                    Candidate.objects.create(fullname=fullname, bio=bio, position=position,
                                             photo=avatar(fullname, colours[n % len(colours)]))
                n += 1
        with open("election_title.txt", "w") as f:
            f.write("Student Council Election 2026")
        ledger.export_register()
        self.stdout.write(self.style.SUCCESS("Demo election ready: %d voters, %d positions, %d candidates"
                                             % (Voter.objects.count(), Position.objects.count(), Candidate.objects.count())))
