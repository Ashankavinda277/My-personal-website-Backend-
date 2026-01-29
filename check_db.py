from pymongo import MongoClient
import os
from dotenv import load_dotenv
import sys

# Ensure dspython is importable
try:
    import dns
    print("dnspython is installed and importable")
except ImportError:
    print("dnspython is NOT installed")

load_dotenv()
uri = os.getenv("DATABASE_URL")
print(f"URI found: {'Yes' if uri else 'No'}")
if uri:
    # mask password
    print(f"URI start: {uri.split('@')[-1] if '@' in uri else '...'}")

try:
    client = MongoClient(uri)
    client.admin.command('ping')
    print("MongoDB Connection Successful!")
except Exception as e:
    print(f"Connection Failed: {e}")
