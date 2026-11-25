import hashlib
import json
import time
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

def hash_block(block):
   data = json.dumps(block, sort_keys=True).encode()
   return hashlib.sha256(data).hexdigest()

def pub_hex(private_key):
   return private_key.public_key().public_bytes(
       serialization.Encoding.Raw, serialization.PublicFormat.Raw
   ).hex()

def sign_body(private_key, body):
   signature = private_key.sign(json.dumps(body, sort_keys=True).encode()).hex()
   return {"body": body, "signature": signature}

def make_vote(private_key, candidate):
   # Simple vote: one candidate (used by vote.py and benchmark.py).
   return sign_body(private_key, {"voter": pub_hex(private_key), "candidate": candidate, "timestamp": time.time()})

def make_ballot(private_key, ballot):
   # Full ballot: {position_id: [candidate_id, ...]} (used by the election website).
   return sign_body(private_key, {"voter": pub_hex(private_key), "ballot": ballot, "timestamp": time.time()})

def check_signature(vote):
   try:
       key = Ed25519PublicKey.from_public_bytes(bytes.fromhex(vote["body"]["voter"]))
       key.verify(bytes.fromhex(vote["signature"]), json.dumps(vote["body"], sort_keys=True).encode())
       return True
   except (InvalidSignature, ValueError, KeyError, TypeError):
       return False

def check_ballot(ballot, positions):
   # positions: {position_id: {"max_vote": n, "candidates": {candidate_id: name}}}
   if not isinstance(ballot, dict) or not ballot:
       return "empty ballot"
   for position_id, chosen in ballot.items():
       position = positions.get(position_id)
       if position is None:
           return "unknown position"
       if not isinstance(chosen, list) or not chosen or len(set(chosen)) != len(chosen):
           return "invalid choice"
       if len(chosen) > position["max_vote"]:
           return "too many candidates"
       if any(c not in position["candidates"] for c in chosen):
           return "unknown candidate"
   return None

def count_votes(chain):
   # Simple votes are counted by candidate; ballots by candidate id ("c<id>").
   results = {}
   for block in chain:
       for vote in block["votes"]:
           body = vote["body"]
           if "ballot" in body:
               keys = ["c" + c for chosen in body["ballot"].values() for c in chosen]
           else:
               keys = [body["candidate"]]
           for k in keys:
               results[k] = results.get(k, 0) + 1
   return results

class Blockchain:
   def __init__(self, registered_voters, candidates, positions=None):
       self.registered = set(registered_voters)
       self.candidates = set(candidates)
       self.positions = positions or {}
       self.voted = set()
       genesis = {"index": 0, "prev_hash": "0" * 64, "timestamp": 0, "votes": []}
       genesis["hash"] = hash_block(genesis)
       self.chain = [genesis]
   def check_vote(self, vote):
       if not check_signature(vote):
           return False, "bad signature"
       voter = vote["body"]["voter"]
       if voter not in self.registered:
           return False, "not registered"
       if voter in self.voted:
           return False, "already voted"
       if "ballot" in vote["body"]:
           problem = check_ballot(vote["body"]["ballot"], self.positions)
           if problem:
               return False, problem
       elif vote["body"].get("candidate") not in self.candidates:
           return False, "unknown candidate"
       return True, "ok"
   def add_block(self, votes):
       accepted = []
       for vote in votes:
           ok, reason = self.check_vote(vote)
           if ok:
               accepted.append(vote)
               self.voted.add(vote["body"]["voter"])
           else:
               print("Rejected:", reason)
       if not accepted:
           return None
       prev = self.chain[-1]
       block = {
           "index": prev["index"] + 1,
           "prev_hash": prev["hash"],
           "timestamp": time.time(),
           "votes": accepted,
       }
       block["hash"] = hash_block(block)
       self.chain.append(block)
       return block
   def is_valid(self):
       for i in range(1, len(self.chain)):
           block = self.chain[i]
           prev = self.chain[i - 1]
           copy = {k: v for k, v in block.items() if k != "hash"}
           if hash_block(copy) != block["hash"]:
               return False
           if block["prev_hash"] != prev["hash"]:
               return False
       return True
   def count(self):
       return count_votes(self.chain)

if __name__ == "__main__":
   ali = Ed25519PrivateKey.generate()
   sara = Ed25519PrivateKey.generate()
   omar = Ed25519PrivateKey.generate()
   outsider = Ed25519PrivateKey.generate()
   positions = {"1": {"name": "President", "max_vote": 1, "candidates": {"1": "Rami", "2": "Lina"}}}
   bc = Blockchain([pub_hex(ali), pub_hex(sara), pub_hex(omar)], ["A", "B"], positions)
   bc.add_block([make_vote(ali, "A"), make_vote(sara, "B")])
   bc.add_block([make_vote(ali, "B")])
   bc.add_block([make_vote(outsider, "A")])
   fake = make_vote(sara, "A")
   fake["body"]["candidate"] = "B"
   bc.add_block([fake])
   bc.add_block([make_ballot(omar, {"1": ["1", "2"]})])
   bc.add_block([make_ballot(omar, {"1": ["2"]})])
   print("Results:", bc.count())
   print("Valid:", bc.is_valid())
