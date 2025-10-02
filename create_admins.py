# run from project root: python create_admins.py
from src.database.connection import db
from src.utils.security import hash_password

admins = [
    {"username": "ashan", "password": hash_password("change_this_password"), "role": "admin"},
    {"username": "girlfriend", "password": hash_password("change_her_password"), "role": "admin"}
]

def create_admins():
    for a in admins:
        if db.users.find_one({"username": a["username"]}):
            print(f"user {a['username']} already exists")
        else:
            db.users.insert_one(a)
            print(f"created {a['username']}")

if __name__ == "__main__":
    create_admins()
