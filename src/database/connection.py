from pymongo import MongoClient
from pymongo.errors import ConfigurationError, ConnectionFailure
import os
import sys
from dotenv import load_dotenv
from fastapi import HTTPException

load_dotenv()

MONGO_URI = os.getenv("DATABASE_URL")
DB_NAME = os.getenv("MONGO_DB_NAME")

client = None
db = None

class MockDB:
    def __getattr__(self, name):
        # This will be called when code tries to access db.users, db.blogs, etc.
        # We verify connection lazily or just fail.
        return self._do_raise

    def _do_raise(self, *args, **kwargs):
        print("Blocked DB Error: Database connection is missing/invalid.")
        raise HTTPException(status_code=500, detail="Database connection is invalid. Please check backend logs and .env file.")

try:
    if not MONGO_URI or not DB_NAME:
        print("WARNING: DATABASE_URL or MONGO_DB_NAME not set in .env")
        db = MockDB()
    else:
        # Try to initialize. For SRV, this might throw ConfigurationError immediately if DNS fails
        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        # We won't force a ping here to allow 'lazy' startup, but SRV resolution happens now.
        db = client[DB_NAME]
except (ConfigurationError, ConnectionFailure, Exception) as e:
    print(f"!!! CRITICAL DATABASE ERROR !!!")
    print(f"Could not connect to MongoDB: {e}")
    print(f"The server is starting in LIMITED MODE. Database requests will failing until fixed.")
    print(f"Please update D:\\Projects\\My personal Website\\My-personal-website-Backend-\\.env with a correct DATABASE_URL.")
    db = MockDB()

# FastAPI dependency
def get_db():
    return db
