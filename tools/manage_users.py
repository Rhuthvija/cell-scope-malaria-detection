"""
tools/manage_users.py
Create and list health-worker accounts.

  python tools/manage_users.py list
  python tools/manage_users.py add asha.padma "ASHA Padma" asha --village Dummugudem --district "Bhadradri Kothagudem"
  python tools/manage_users.py add doctor.dummugudem "Dr. Lakshmi (PHC Dummugudem)" doctor --district "Bhadradri Kothagudem"

Roles: asha (runs tests, sees own patients), doctor (tests + all records +
referrals + outbreak map), district (records, analytics, outbreak map), admin.
You'll be asked for the password (at least 8 characters); it is stored hashed.
"""
import argparse
import getpass
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import db  # noqa: E402

ap = argparse.ArgumentParser()
sub = ap.add_subparsers(dest="cmd", required=True)
sub.add_parser("list")
add = sub.add_parser("add")
add.add_argument("username")
add.add_argument("display_name")
add.add_argument("role", choices=db.ROLES)
add.add_argument("--village", default="")
add.add_argument("--district", default="")
args = ap.parse_args()

db.init_db()
if args.cmd == "list":
    for u in db.list_users():
        print(f"{u['username']:<22} {u['role']:<9} {u['display_name']:<30} {u['village']} {u['district']}")
else:
    pw = getpass.getpass("Password: ")
    if pw != getpass.getpass("Repeat password: "):
        sys.exit("Passwords don't match.")
    db.create_user(args.username, args.display_name, args.role, pw, args.village, args.district)
    print(f"Created {args.role} account '{args.username}'.")
