# Blockchain integration

This folder is the open-source election website
[jobic10/e-voting-with-django](https://github.com/jobic10/e-voting-with-django) (MIT license, see `LICENSE`),
connected to our distributed blockchain ledger in `../election__chain`.

The website keeps its own features: voter login, the ballot with several positions, the admin dashboard,
results charts and the PDF report. We added the ledger next to its database: every ballot is signed and
stored by three independent nodes, and the admin can check at any time that the website's count matches
the ledger.

## The new interface (portal)

The website now opens on a new interface built on the same backend (`portal/`). The classic AdminLTE pages
are still at `/account/` and `/administrator/` for managing voters, positions and candidates.

| Address | Page |
|---|---|
| `/` | Overview: live network of the 3 nodes, turnout, latest blocks, how the protection works |
| `/signin/` | Sign in for students and staff |
| `/vote/` | Step by step ballot with candidate cards, a review step, and a "sign and cast" animation that shows each node's real answer |
| `/receipt/` | Ballot receipt: block number, choices, public key, and a live check of the ballot on all 3 copies |
| `/results/` | Live results from the ledger majority, with turnout |
| `/explorer/` | Ledger explorer: every block, hash, signature and ballot |
| `/control/` | Control room (staff): node health, activity feed, ledger vs website database, tampering demo |

It is plain HTML, CSS and JavaScript with no external libraries or fonts, so it works offline, in light and dark
mode, and on phones. The JSON endpoints it uses are in `portal/views.py` (`/api/overview/`, `/api/chain/`,
`/api/vote/`, `/api/verify/`, `/api/tamper/`). Ballot casting is shared with the classic pages in `voting/services.py`.

## What we added or changed

| File | Change |
|---|---|
| `voting/ledger.py` (new) | The bridge to the ledger: voter keys, signing a ballot, sending it to the 3 nodes in parallel, exporting the voter register, and the audit (hash, link and signature checks plus the majority). |
| `voting/models.py` | Two new tables: `LedgerKey` (each voter's Ed25519 key) and `LedgerReceipt` (what each node answered). Migration `voting/migrations/0002_ledger.py`. |
| `voting/views.py` | `submit_ballot()` sends the signed ballot to the ledger first. The vote is saved in the website only when at least one node accepted it. The voter dashboard shows a blockchain receipt. |
| `voting/signals.py` (new), `voting/apps.py` | When voters, positions or candidates change, `voters.json` (public keys only) and `election.json` (the ballot) are rewritten for the nodes. The nodes reload them within 3 seconds. |
| `administrator/ledger_views.py` (new), `administrator/templates/admin/ledger.html` (new) | The "Blockchain Audit" admin page: the 3 nodes, the official majority result compared with the website database, a block explorer, and demonstration buttons to tamper with one copy. |
| `administrator/urls.py`, `administrator/templates/sidebar.html`, `account/middleware.py` | The new page's address, menu link and access rule (admins only). |
| `voting/management/commands/seed_demo.py`, `ledger_export.py` (new) | Create the demo student council election; write the register for the nodes. |
| `voting/test_ledger.py` (new), `voting/testing.py`, `e_voting/settings.py` | 11 new tests; the existing tests never touch the real ledger. Settings `LEDGER_DIR` and `LEDGER_NODES`. |

In `../election__chain`, `chain.py` now also accepts a full ballot (several positions, several choices per
position) and checks it against `election.json`; `node.py` reloads the register and ballot when they change;
`auditor.py` prints candidate names.

## How to run it

From the project folder, in PowerShell:

```
python -m pip install -r election_website\requirements.txt flask
.\start_demo.ps1 -Fresh
```

This opens one window per ledger node, one for the website, and the browser at http://127.0.0.1:8000/.
The demo accounts are listed at the top of `voting/management/commands/seed_demo.py`.

## What to show

1. Open the **Control room** as the admin in one window. In a second window (or a private window), sign in as a student and vote: watch the casting animation, then the receipt checking the ballot on all three copies. The control room logs the new block.
2. Close one node's window and vote as another student: the vote is still recorded and the receipt shows that node as offline. Start the node again (`python node.py commission`): it loads its chain from disk and copies the missing block from its peers.
3. In the control room, press **Tamper a ballot** on one node: it turns red, the network diagram shows "2 of 3 copies agree", and the official result still comes from the other two. **Tamper and rehash** shows that recomputing the hashes does not help, because the signature check catches it. Restart that node to restore its copy from disk.
4. In the classic admin (**Manage voters and candidates** in the footer), open **Votes** and press **Reset**: the website database is emptied, but the ledger still holds every ballot and the control room shows the difference. A student who tries to vote again is refused by the ledger.
5. Close all three node windows and try to vote: the website refuses to record a vote it cannot put on the ledger.

## Limits of this demonstration

* The website keeps each voter's private key and signs for them. In a real election the key would stay on the voter's device or ID card.
* Ballots are linked to a public key, so they are not secret.
* `DJANGO_DEBUG=True` and the default secret key are for a local demonstration only.
