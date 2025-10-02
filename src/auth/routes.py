from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from src.database.connection import get_db
from src.utils.security import hash_password, verify_password, create_access_token

router = APIRouter()

class LoginRequest(BaseModel):
    username: str
    password: str

@router.post("/login")
def login(payload: LoginRequest, db=Depends(get_db)):
    user = db.users.find_one({"username": payload.username})
    if not user or not verify_password(payload.password, user["password"]):
        raise HTTPException(status_code=400, detail="Incorrect username or password")
    token = create_access_token({"sub": user["username"]})
    return {"access_token": token, "token_type": "bearer"}


@router.post("/register", status_code=201)
def register(payload: LoginRequest, db=Depends(get_db)):
    if db.users.find_one({"username": payload.username}):
        raise HTTPException(status_code=400, detail="Username already registered")
    db.users.insert_one({
        "username": payload.username,
        "password": hash_password(payload.password),
        "role": "admin"
    })
    return {"message": "User registered successfully"}