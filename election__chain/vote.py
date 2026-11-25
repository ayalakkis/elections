import json
import sys
from concurrent.futures import ThreadPoolExecutor
import requests
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from chain import make_vote
NODES = {
   "interior": "http://127.0.0.1:5001",
   "commission": "http://127.0.0.1:5002",
   "delegates": "http://127.0.0.1:5003",
}
if len(sys.argv) != 3:
   print("Usage: python vote.py <voter_index> <candidate>")
   sys.exit(1)
voter_index, candidate = int(sys.argv[1]), sys.argv[2]
with open("voters.json") as f:
   voter = json.load(f)[voter_index]
key = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(voter["private"]))
vote = make_vote(key, candidate)

def send(n):
   # The same signed vote goes to every node, so no single node can hide it.
   try:
       r = requests.post(NODES[n] + "/vote", json=vote, timeout=10)
       return n, r.status_code, r.json()
   except requests.RequestException:
       return n, None, None

with ThreadPoolExecutor(len(NODES)) as pool:
   answers = list(pool.map(send, NODES))
accepted = False
reasons = set()
for n, code, body in answers:
   if code is None:
       print(f"{n}: down, skipped")
   elif code == 201:
       accepted = True
       print(f"{n}: accepted in block {body['block']}")
   else:
       reasons.add(body["reason"])
       print(f"{n}: {body['reason']}")
if accepted:
   # The other nodes answer "already voted" because they received the block first.
   print("Vote recorded.")
elif all(code is None for _, code, _ in answers):
   print("Vote NOT recorded: all nodes are down.")
   sys.exit(2)
else:
   print("Vote rejected:", ", ".join(sorted(reasons)))
   sys.exit(3)
