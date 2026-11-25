"""Integration with an existing voter register.

Election authorities already keep a register of eligible citizens (a civil
registry database, usually exported as CSV). This adapter reads that existing
export, creates a key pair for each eligible person, and writes voters.json,
which every node loads as its list of registered public keys.

CSV columns: national_id,name,eligible   (eligible = yes/no)

Usage: python import_register.py register.csv
"""
import csv
import json
import sys
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from chain import pub_hex

if len(sys.argv) != 2:
   print(__doc__)
   sys.exit(1)
voters, skipped, seen = [], [], set()
try:
   with open(sys.argv[1], newline="", encoding="utf-8") as f:
       for line, row in enumerate(csv.DictReader(f), start=2):
           national_id = (row.get("national_id") or "").strip()
           name = (row.get("name") or "").strip()
           if not national_id or not name:
               skipped.append(f"line {line}: missing national_id or name")
               continue
           if national_id in seen:
               skipped.append(f"line {line}: duplicate national_id {national_id}")
               continue
           if (row.get("eligible") or "").strip().lower() != "yes":
               skipped.append(f"line {line}: {national_id} not eligible")
               continue
           seen.add(national_id)
           key = Ed25519PrivateKey.generate()
           private = key.private_bytes(
               serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption()
           ).hex()
           voters.append({"name": name, "national_id": national_id, "private": private, "public": pub_hex(key)})
except FileNotFoundError:
   print("Register file not found:", sys.argv[1])
   sys.exit(1)
except csv.Error as e:
   print("Register file is not valid CSV:", e)
   sys.exit(1)
with open("voters.json", "w") as f:
   json.dump(voters, f, indent=2)
print(f"Imported {len(voters)} voters from the register")
for s in skipped:
   print("Skipped", s)
print("Delete the *_chain.json files and restart the nodes to use the new register.")
