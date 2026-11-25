import json
import sys
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from chain import pub_hex
count = int(sys.argv[1]) if len(sys.argv) > 1 else 5
voters = []
for i in range(count):
   key = Ed25519PrivateKey.generate()
   private = key.private_bytes(
       serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption()
   ).hex()
   voters.append({"name": f"voter{i}", "private": private, "public": pub_hex(key)})
with open("voters.json", "w") as f:
   json.dump(voters, f, indent=2)
print("Created", len(voters), "voters")