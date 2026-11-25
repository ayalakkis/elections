# Distributed E-Voting Ledger

Distributed Systems, Final Project 2026. Prepared by Aya Lakkis and Mohammad Othman, supervised by Dr. Adib Haddad.

A blockchain built from scratch in Python and shared by three parties who do not fully trust each other:
the Ministry of Interior, the Supervisory Commission and the candidates' delegates. Every ballot is signed
with Ed25519, chained with SHA-256 hashes and copied to all three nodes. An auditor checks every copy and
takes the official result from the majority, so no single party can change the result unnoticed.

The ledger is integrated with an existing open-source election website
([jobic10/e-voting-with-django](https://github.com/jobic10/e-voting-with-django), MIT license), which now
has a new interface: step by step ballot, signed receipt checked against every copy, live results,
ledger explorer and a control room.

## Contents

| Folder or file | What it is |
|---|---|
| `election__chain/` | The blockchain: `chain.py` (blocks, hashes, signatures), `node.py` (one node per party, REST API), `vote.py` (command-line voter), `auditor.py`, `benchmark.py`, voter register tools |
| `election_website/` | The election website connected to the ledger. `portal/` is the new interface, `voting/ledger.py` the bridge to the nodes. See `election_website/BLOCKCHAIN_INTEGRATION.md` |
| `start_demo.ps1` | Starts the three nodes and the website on one Windows laptop |
| `Distributed E-Voting Ledger Design Document_6411.docx` | Design document |
| `Distributed E-Voting Ledger Presentation.pptx` | Presentation |
| `screenshots/` | Screenshots of the command-line demo, the website and the new interface |

## Run it

Requirements: Python 3.11 or newer.

```
python -m pip install -r election_website/requirements.txt flask
.\start_demo.ps1 -Fresh
```

Then open http://127.0.0.1:8000/. The demo accounts are listed at the top of
`election_website/voting/management/commands/seed_demo.py`.

Command-line only (no website):

```
cd election__chain
python setup_voters.py 5
python node.py interior        # terminal 1
python node.py commission      # terminal 2
python node.py delegates       # terminal 3
python vote.py 0 A
python auditor.py
```

## Tests

```
cd election_website
$env:DJANGO_DEBUG = 'True'    # PowerShell
python manage.py test
```
