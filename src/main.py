from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

load_dotenv()

from src.auth.routes import router as auth_router
from src.blog.routes import router as blog_router

app = FastAPI(title="Concepts Blog API")

# CORS - adjust origins in production
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173", "http://127.0.0.1:3000", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router, prefix="/auth", tags=["auth"])
app.include_router(blog_router, prefix="/blogs", tags=["blogs"])

@app.get("/")
def root():
    return {"message": "Concepts Blog API running 🚀"}
