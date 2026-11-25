"""Bridge between this election website and the distributed blockchain ledger.

The ledger is the separate project in ../election__chain: three independent nodes
(interior, commission, delegates) that each keep a full, hash linked, signed copy
of every ballot. This module is the only place where the website talks to it:

* export_register()  writes the voter register (public keys) and the ballot
                     (positions and candidates) for the nodes to load.
* record_ballot()    signs a voter's ballot and sends it to all three nodes.
* audit()            downloads every node's chain, checks it and finds the majority.

Everything goes over HTTP and JSON, the same REST interface the nodes already offer.
"""
import hashlib
import json
import os
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor

import requests
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey, Ed25519PublicKey)
from django.conf import settings

from .models import Candidate, LedgerKey, Position, Voter

# (connect, read) timeouts: a node that is down is skipped quickly.
SEND_TIMEOUT = (0.5, 10)
READ_TIMEOUT = (0.5, 3)


# Keys and signatures (same format as election__chain/chain.py)

def canonical(body):
    return json.dumps(body, sort_keys=True).encode()


def hash_block(block):
    return hashlib.sha256(canonical(block)).hexdigest()


def key_for(voter):
    """Return the voter's ledger key, creating it the first time."""
    try:
        return voter.ledgerkey
    except LedgerKey.DoesNotExist:
        private = Ed25519PrivateKey.generate()
        public = private.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw).hex()
        raw = private.private_bytes(
            serialization.Encoding.Raw, serialization.PrivateFormat.Raw,
            serialization.NoEncryption()).hex()
        return LedgerKey.objects.create(voter=voter, public_key=public, private_key=raw)


def signed_ballot(voter, selections):
    """selections: [(Position, [Candidate, ...]), ...] as returned by parse_ballot."""
    key = key_for(voter)
    body = {
        "voter": key.public_key,
        "ballot": {str(p.id): [str(c.id) for c in cands] for p, cands in selections},
        "timestamp": time.time(),
    }
    private = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(key.private_key))
    return {"body": body, "signature": private.sign(canonical(body)).hex()}


def signature_ok(vote):
    try:
        key = Ed25519PublicKey.from_public_bytes(bytes.fromhex(vote["body"]["voter"]))
        key.verify(bytes.fromhex(vote["signature"]), canonical(vote["body"]))
        return True
    except (InvalidSignature, ValueError, KeyError, TypeError):
        return False


# Register and ballot export

def election_config():
    positions = {}
    for position in Position.objects.order_by('priority', 'id').prefetch_related('candidate_set'):
        positions[str(position.id)] = {
            "name": position.name,
            "max_vote": position.max_vote,
            "candidates": {str(c.id): c.fullname for c in position.candidate_set.all()},
        }
    return {"positions": positions}


def _write_json(path, data):
    # Write to a temporary file, then rename: a node never reads a half written file.
    folder = os.path.dirname(path)
    fd, tmp = tempfile.mkstemp(dir=folder, suffix=".tmp")
    with os.fdopen(fd, "w") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, path)


def export_register():
    """Write voters.json and election.json into the ledger folder.

    Only public keys leave the website. The nodes re-read these files within a few
    seconds, so voters and candidates added in the admin panel can vote right away.
    """
    folder = settings.LEDGER_DIR
    if not os.path.isdir(folder):
        return False
    for voter in Voter.objects.filter(ledgerkey__isnull=True):
        key_for(voter)
    voters = [{"name": "voter%d" % k.voter_id, "public": k.public_key}
              for k in LedgerKey.objects.order_by('voter_id')]
    _write_json(os.path.join(folder, "voters.json"), voters)
    _write_json(os.path.join(folder, "election.json"), election_config())
    return True


# Sending a ballot

def _post(name, url, vote):
    try:
        r = requests.post(url + "/vote", json=vote, timeout=SEND_TIMEOUT)
        data = r.json()
        if r.status_code == 201:
            return name, "accepted", data.get("block")
        return name, "rejected", data.get("reason", "rejected")
    except (requests.RequestException, ValueError):
        return name, "down", None


def record_ballot(voter, selections):
    """Sign the ballot and send it to every node in parallel.

    Returns (recorded, block, answers). recorded is True when at least one node
    accepted the ballot. If every node that answered says "already voted", the
    ledger already holds this voter's earlier ballot, and that ballot stands.
    """
    vote = signed_ballot(voter, selections)
    nodes = settings.LEDGER_NODES
    with ThreadPoolExecutor(len(nodes)) as pool:
        answers = list(pool.map(lambda item: _post(item[0], item[1], vote), nodes.items()))
    blocks = [info for _, status, info in answers if status == "accepted"]
    return bool(blocks), (min(blocks) if blocks else None), answers


# Auditing

def chain_problem(chain, registered, positions):
    """None if the chain is valid, otherwise the reason (same checks as auditor.py)."""
    seen = set()
    for i in range(1, len(chain)):
        block = chain[i]
        copy = {k: v for k, v in block.items() if k != "hash"}
        if hash_block(copy) != block["hash"]:
            return "block %d hash does not match its content" % i
        if block["prev_hash"] != chain[i - 1]["hash"]:
            return "block %d is not linked to block %d" % (i, i - 1)
        for vote in block["votes"]:
            voter = vote["body"].get("voter")
            if not signature_ok(vote):
                return "block %d has a vote with a bad signature" % i
            if voter not in registered:
                return "block %d has a vote from an unregistered voter" % i
            if voter in seen:
                return "block %d has a second vote from the same voter" % i
            seen.add(voter)
    return None


def tally(chain):
    counts = {}
    for block in chain:
        for vote in block["votes"]:
            for chosen in vote["body"].get("ballot", {}).values():
                for cid in chosen:
                    counts[cid] = counts.get(cid, 0) + 1
    return counts


def _get_chain(name, url):
    try:
        return name, requests.get(url + "/chain", timeout=READ_TIMEOUT).json()
    except (requests.RequestException, ValueError):
        return name, None


def audit():
    registered = set(LedgerKey.objects.values_list('public_key', flat=True))
    config = election_config()["positions"]
    nodes = settings.LEDGER_NODES
    with ThreadPoolExecutor(len(nodes)) as pool:
        chains = dict(pool.map(lambda item: _get_chain(*item), nodes.items()))

    reports, honest = [], {}
    for name, url in nodes.items():
        chain = chains.get(name)
        if chain is None:
            reports.append({"name": name, "url": url, "status": "DOWN", "reason": "not reachable", "blocks": 0, "ballots": 0})
            continue
        reason = chain_problem(chain, registered, config)
        ballots = sum(len(b["votes"]) for b in chain)
        status = "VALID" if reason is None else "TAMPERED"
        reports.append({"name": name, "url": url, "status": status, "reason": reason or "all hashes, links and signatures check out",
                        "blocks": len(chain), "ballots": ballots, "tip": chain[-1]["hash"][:16]})
        if reason is None:
            honest[name] = chain

    groups = {}
    for name, chain in honest.items():
        groups.setdefault(chain[-1]["hash"], []).append(name)
    majority = next((names for names in groups.values() if len(names) * 2 > len(nodes)), None)
    official = tally(honest[majority[0]]) if majority else None
    blocks = honest[majority[0]] if majority else next(iter(honest.values()), [])
    return {"nodes": reports, "majority": majority, "official": official, "blocks": blocks}
