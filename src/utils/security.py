import hashlib
from passlib.context import CryptContext
from jose import jwt
from dotenv import load_dotenv
import os
from datetime import datetime, timedelta

load_dotenv()

# Configure CryptContext with explicit bcrypt settings
pwd_context = CryptContext(
    schemes=["bcrypt"], 
    deprecated="auto",
    bcrypt__rounds=12
)

SECRET_KEY = os.getenv("JWT_SECRET_KEY")
ALGORITHM = os.getenv("ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))

def hash_password(password: str) -> str:
    """Hash a password, handling bcrypt's 72-byte limitation"""
    try:
        # Check if password is too long for bcrypt (72 bytes)
        password_bytes = password.encode('utf-8')
        if len(password_bytes) > 72:
            # Pre-hash with SHA256 if too long
            password = hashlib.sha256(password_bytes).hexdigest()
        
        return pwd_context.hash(password)
    except Exception as e:
        # Fallback: use SHA256 + salt if bcrypt fails
        import secrets
        salt = secrets.token_hex(16)
        return f"sha256${salt}${hashlib.sha256((password + salt).encode()).hexdigest()}"

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash"""
    try:
        # Handle fallback SHA256 hashes
        if hashed_password.startswith("sha256$"):
            _, salt, hash_value = hashed_password.split("$", 2)
            return hashlib.sha256((plain_password + salt).encode()).hexdigest() == hash_value
        
        # Handle bcrypt passwords
        password_bytes = plain_password.encode('utf-8')
        if len(password_bytes) > 72:
            plain_password = hashlib.sha256(password_bytes).hexdigest()
            
        return pwd_context.verify(plain_password, hashed_password)
    except Exception:
        return False

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    token = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return token