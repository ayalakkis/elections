import json
import random
import time
from concurrent.futures import ThreadPoolExecutor
import requests
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from chain import Blockchain, make_vote
NODES = [
   "http://127.0.0.1:5001",
   "http://127.0.0.1:5002",
   "http://127.0.0.1:5003",
]
CANDIDATES = ["A", "B", "C"]
THREADS = 10
with open("voters.json") as f:
   voters = json.load(f)
keys = [Ed25519PrivateKey.from_private_bytes(bytes.fromhex(v["private"])) for v in voters]
votes = [make_vote(k, random.choice(CANDIDATES)) for k in keys]
print(f"Prepared {len(votes)} signed votes")

def send(i):
   url = NODES[i % len(NODES)]
   try:
      r = requests.post(url + "/vote", json=votes[i], timeout=10)
      return r.status_code
   except requests.RequestException:
      return 0

print(f"\n--- Test 1: blockchain, {THREADS} voters at the same time ---")
start = time.time()
with ThreadPoolExecutor(THREADS) as pool:
   codes = list(pool.map(send, range(len(votes))))
elapsed = time.time() - start
accepted = codes.count(201)
print(f"Accepted: {accepted}/{len(votes)}")
print(f"Time: {elapsed:.2f} s")
print(f"Speed: {len(votes) / elapsed:.1f} votes/second")
print("\nWaiting for the 3 nodes to agree...")
start = time.time()
while time.time() - start < 60:
   totals = []
   for url in NODES:
      try:
         r = requests.get(url + "/results", timeout=3).json()
         totals.append(sum(r["results"].values()))
      except requests.RequestException:
         totals.append(None)
   if totals[0] == len(votes) and len(set(totals)) == 1:
      print(f"All 3 nodes have {totals[0]} votes after {time.time() - start:.1f} s")
      break
   time.sleep(1)
else:
   print("Nodes did not agree in time:", totals)
print("\n--- Test 2: same votes, no network ---")
start = time.time()
plain = []
for v in votes:
   plain.append(v)
plain_time = time.time() - start
registered = [v["public"] for v in voters]
bc = Blockchain(registered, CANDIDATES)
start = time.time()
for v in votes:
   bc.add_block([v])
chain_time = time.time() - start
print(f"Plain list:  {len(votes) / plain_time:,.0f} votes/second")
print(f"Blockchain:  {len(votes) / chain_time:,.0f} votes/second (checks signature + hash)")
 