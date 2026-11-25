import json
import os
import sys
import threading
import time
import requests
from flask import Flask, jsonify, request
from chain import Blockchain, hash_block
CANDIDATES = ["A", "B", "C"]
NODES = {
   "interior": "http://127.0.0.1:5001",
   "commission": "http://127.0.0.1:5002",
   "delegates": "http://127.0.0.1:5003",
}
if len(sys.argv) != 2 or sys.argv[1] not in NODES:
   print("Usage: python node.py <" + "|".join(NODES) + ">")
   sys.exit(1)
name = sys.argv[1]
port = int(NODES[name].rsplit(":", 1)[1])
peers = {n: u for n, u in NODES.items() if n != name}
# The register (voters.json) and the ballot (election.json) are written by the
# election website, or by setup_voters.py / import_register.py for the command-line demo.
# They are re-read whenever they change, so a node does not need a restart.
CONFIG_FILES = ("voters.json", "election.json")
config_stamp = None
registered, positions = [], {}

def load_config():
   global registered, positions, config_stamp
   stamp = tuple(os.path.getmtime(f) if os.path.exists(f) else None for f in CONFIG_FILES)
   if stamp == config_stamp:
       return False
   try:
       with open("voters.json") as f:
           new_registered = [v["public"] for v in json.load(f)]
       new_positions = {}
       if os.path.exists("election.json"):
           with open("election.json") as f:
               new_positions = json.load(f)["positions"]
   except (OSError, ValueError, KeyError) as e:
       print("Could not read the voter register or ballot:", e)
       return False
   registered, positions, config_stamp = new_registered, new_positions, stamp
   return True

load_config()
bc = Blockchain(registered, CANDIDATES, positions)
lock = threading.Lock()

def refresh_config():
   # Called with the lock held.
   if load_config():
       bc.registered, bc.positions = set(registered), positions
       print(f"Register reloaded: {len(registered)} voters, {len(positions)} positions")
app = Flask(name)
FILE = f"{name}_chain.json"

def save():
   with open(FILE, "w") as f:
       json.dump(bc.chain, f)

def accept_block(target, block):
   prev = target.chain[-1]
   if block["index"] != prev["index"] + 1 or block["prev_hash"] != prev["hash"]:
       return False
   copy = {k: v for k, v in block.items() if k != "hash"}
   if hash_block(copy) != block["hash"]:
       return False
   seen = set()
   for vote in block["votes"]:
       ok, _ = target.check_vote(vote)
       voter = vote["body"]["voter"]
       if not ok or voter in seen:
           return False
       seen.add(voter)
   target.chain.append(block)
   target.voted.update(seen)
   return True

def rebuild(blocks):
   new = Blockchain(registered, CANDIDATES, positions)
   if not blocks or blocks[0] != new.chain[0]:
       return None
   for block in blocks[1:]:
       if not accept_block(new, block):
           return None
   return new

def send_block(peer, url, block):
   try:
       # (connect, read) timeouts: a dead peer is detected quickly.
       requests.post(url + "/block", json=block, timeout=(0.5, 2))
   except requests.RequestException:
       print(f"Could not reach {peer}")

def broadcast(block):
   # Send to all peers in parallel, so one dead peer does not delay the others
   # and the voter gets an answer in at most about 2 seconds.
   threads = [threading.Thread(target=send_block, args=(p, u, block)) for p, u in peers.items()]
   for t in threads:
       t.start()
   for t in threads:
       t.join()

def sync():
   for peer, url in peers.items():
       try:
           blocks = requests.get(url + "/chain", timeout=(0.5, 2)).json()
       except requests.RequestException:
           continue
       longer = len(blocks) > len(bc.chain)
       tie = len(blocks) == len(bc.chain) and blocks[-1]["hash"] < bc.chain[-1]["hash"]
       if not (longer or tie):
           continue
       new = rebuild(blocks)
       if not new:
           continue
       old_votes = [v for b in bc.chain for v in b["votes"]]
       bc.chain, bc.voted = new.chain, new.voted
       print(f"Synced chain from {peer}")
       for v in old_votes:
           if bc.check_vote(v)[0]:
               block = bc.add_block([v])
               print("Re-added lost vote")
               threading.Thread(target=broadcast, args=(block,)).start()
       save()

def sync_loop():
   while True:
       with lock:
           refresh_config()
           sync()
       time.sleep(3)

@app.post("/vote")
def vote():
   data = request.get_json()
   with lock:
       refresh_config()
       ok, reason = bc.check_vote(data)
       if not ok:
           return jsonify({"status": "rejected", "reason": reason}), 400
       block = bc.add_block([data])
       save()
   broadcast(block)
   return jsonify({"status": "accepted", "block": block["index"]}), 201

@app.post("/block")
def receive_block():
   block = request.get_json()
   with lock:
       if accept_block(bc, block):
           save()
           return jsonify({"status": "added"})
       sync()
   return jsonify({"status": "synced"}), 202

@app.get("/chain")
def get_chain():
   # Take a snapshot first (list() is atomic in CPython), so a block appended
   # while the answer is being serialised cannot change it. No lock is taken here:
   # two nodes syncing from each other while holding their own lock would wait on each other.
   return jsonify(list(bc.chain))

@app.get("/results")
def results():
   counts = bc.count()
   names = {"c" + cid: p["name"] + ": " + cname for p in positions.values() for cid, cname in p["candidates"].items()}
   named = {names.get(k, k): v for k, v in counts.items()}
   return jsonify({"node": name, "blocks": len(bc.chain), "results": counts, "named_results": named})

@app.post("/tamper")
def tamper():
   # Demo only. ?rehash=1 is a smarter attacker who also recomputes every hash,
   # so the chain looks consistent; the Auditor still catches it by the signature.
   with lock:
       if len(bc.chain) > 1:
           body = bc.chain[1]["votes"][0]["body"]
           if "ballot" in body:
               # Move this ballot's first choice to another candidate of the same position.
               position_id, chosen = next(iter(body["ballot"].items()))
               others = [c for c in positions.get(position_id, {}).get("candidates", {}) if c not in chosen]
               chosen[0] = others[0] if others else chosen[0] + "0"
           else:
               body["candidate"] = "C"
           if request.args.get("rehash"):
               for i in range(1, len(bc.chain)):
                   bc.chain[i]["prev_hash"] = bc.chain[i - 1]["hash"]
                   copy = {k: v for k, v in bc.chain[i].items() if k != "hash"}
                   bc.chain[i]["hash"] = hash_block(copy)
   return jsonify({"status": "tampered"})

if __name__ == "__main__":
   if os.path.exists(FILE):
       with open(FILE) as f:
           loaded = rebuild(json.load(f))
       if loaded:
           bc.chain, bc.voted = loaded.chain, loaded.voted
           print(f"Loaded {len(bc.chain) - 1} blocks from disk")
       else:
           print("Saved chain is invalid, starting fresh")
   threading.Thread(target=sync_loop, daemon=True).start()
   app.run(port=port)