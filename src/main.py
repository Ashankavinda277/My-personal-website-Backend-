from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

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

# Custom exception handler to prevent binary data in error responses
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = []
    for error in exc.errors():
        # Remove binary data from error messages
        error_dict = {
            "loc": error["loc"],
            "msg": error["msg"],
            "type": error["type"]
        }
        # Don't include the actual input data if it might be binary
        if "input" in error and error["loc"][-1] != "image":
            error_dict["input"] = error["input"]
        errors.append(error_dict)
    
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": errors}
    )

app.include_router(auth_router, prefix="/auth", tags=["auth"])
app.include_router(blog_router, prefix="/blogs", tags=["blogs"])

@app.get("/")
def root():
    return {"message": "Concepts Blog API running 🚀"}
