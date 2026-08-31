from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import os
import sys

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

load_dotenv()

# Must run before any request is parsed: lifts Starlette's 1 MB cap on
# non-file form fields so long blog posts can be submitted.
from src.utils.form_limits import apply_multipart_limits

apply_multipart_limits()

from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from src.auth.routes import router as auth_router
from src.blog.routes import router as blog_router
from src.contact.routes import router as contact_router

app = FastAPI(title="Concepts Blog API")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Custom exception handler
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = []
    for error in exc.errors():
        error_dict = {
            "loc": error["loc"],
            "msg": error["msg"],
            "type": error["type"]
        }
        if "input" in error and error["loc"][-1] != "image":
            error_dict["input"] = error["input"]
        errors.append(error_dict)
    
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": errors}
    )

app.include_router(auth_router, prefix="/auth", tags=["auth"])
app.include_router(blog_router, prefix="/blogs", tags=["blogs"])
app.include_router(contact_router, prefix="/contact", tags=["contact"])

@app.get("/")
def root():
    return {"message": "Concepts Blog API running 🚀"}
