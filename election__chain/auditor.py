import json
import requests
import os
from chain import hash_block, check_signature, count_votes
NODES = {
   "interior": "http://127.0.0.1:5001",
   "commission": "http://127.0.0.1:5002",
   "delegates": "http://127.0.0.1:5003",
}
with open("voters.json") as f:
   registered = {v["public"] for v in json.load(f)}
names = {}
if os.path.exists("election.json"):
   with open("election.json") as f:
       for p in json.load(f)["positions"].values():
           for cid, cname in p["candidates"].items():
               names["c" + cid] = p["name"] + ": " + cname

def problem(chain):
   # Returns None if the chain is valid, otherwise the reason it is not.
   seen = set()
   for i in range(1, len(chain)):
       block = chain[i]
       copy = {k: v for k, v in block.items() if k != "hash"}
       if hash_block(copy) != block["hash"]:
           return f"block {i} hash does not match its content"
       if block["prev_hash"] != chain[i - 1]["hash"]:
           return f"block {i} is not linked to block {i - 1}"
       for vote in block["votes"]:
           voter = vote["body"]["voter"]
           if not check_signature(vote):
               return f"block {i} has a vote with a bad signature"
           if voter not in registered:
               return f"block {i} has a vote from an unregistered voter"
           if voter in seen:
               return f"block {i} has a second vote from the same voter"
           seen.add(voter)
   return None

def count(chain):
   return {names.get(k, k): v for k, v in count_votes(chain).items()}

honest = {}
for name, url in NODES.items():
   try:
       chain = requests.get(url + "/chain", timeout=3).json()
   except requests.RequestException:
       print(f"{name}: DOWN")
       continue
   reason = problem(chain)
   if reason is None:
       print(f"{name}: VALID, {len(chain)} blocks, {count(chain)}")
       honest[name] = chain
   else:
       print(f"{name}: TAMPERED! ({reason})")
tips = {}
for name, chain in honest.items():
   tips.setdefault(chain[-1]["hash"], []).append(name)
for tip, names in tips.items():
   if len(names) >= 2:
       print("Majority agree:", names)
       print("Official result:", count(honest[names[0]]))
       break
else:
   print("No majority, cannot confirm the result")
