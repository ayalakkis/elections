from django.db import models
from account.models import CustomUser
# Create your models here.


class Voter(models.Model):
    admin = models.OneToOneField(CustomUser, on_delete=models.CASCADE)
    phone = models.CharField(max_length=11, unique=True)  # Used for OTP
    otp = models.CharField(max_length=10, null=True)
    verified = models.BooleanField(default=False)
    voted = models.BooleanField(default=False)
    otp_sent = models.IntegerField(default=0)  # Control how many OTPs are sent

    def __str__(self):
        return self.admin.last_name + ", " + self.admin.first_name


class Position(models.Model):
    name = models.CharField(max_length=50, unique=True)
    max_vote = models.IntegerField()
    priority = models.IntegerField()

    def __str__(self):
        return self.name


class Candidate(models.Model):
    fullname = models.CharField(max_length=50)
    photo = models.ImageField(upload_to="candidates")
    bio = models.TextField()
    position = models.ForeignKey(Position, on_delete=models.CASCADE)

    def __str__(self):
        return self.fullname


class Votes(models.Model):
    voter = models.ForeignKey(Voter, on_delete=models.CASCADE)
    position = models.ForeignKey(Position, on_delete=models.CASCADE)
    candidate = models.ForeignKey(Candidate, on_delete=models.CASCADE)


class LedgerKey(models.Model):
    """The voter's Ed25519 key for the blockchain ledger.

    Demo simplification: the website keeps the private key and signs for the
    voter. In a real deployment it would stay on the voter's own device or ID card.
    """
    voter = models.OneToOneField(Voter, on_delete=models.CASCADE)
    public_key = models.CharField(max_length=64, unique=True)
    private_key = models.CharField(max_length=64)


class LedgerReceipt(models.Model):
    """What the ledger answered when this voter's ballot was sent."""
    voter = models.OneToOneField(Voter, on_delete=models.CASCADE)
    block = models.IntegerField(null=True)
    answers = models.TextField()  # JSON: [[node, status, info], ...]
    created_at = models.DateTimeField(auto_now_add=True)
