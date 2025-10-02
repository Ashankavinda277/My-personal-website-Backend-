from pymongo import MongoClient
import os
from dotenv import load_dotenv

load_dotenv()

MONGO_URI = os.getenv("DATABASE_URL")
DB_NAME = os.getenv("MONGO_DB_NAME")

if not MONGO_URI or not DB_NAME:
    raise Exception("Set DATABASE_URL and MONGO_DB_NAME in your .env")

# Create single global client (reuse)
client = MongoClient(MONGO_URI)
db = client[DB_NAME]

# FastAPI dependency (simple)
def get_db():
    return db
