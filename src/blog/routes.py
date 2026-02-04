from fastapi import APIRouter, Depends, HTTPException
from src.database.connection import get_db
from src.models.schemas import BlogCreate, BlogUpdate
from src.auth.deps import get_current_user, require_admin
from bson import ObjectId
from datetime import datetime

router = APIRouter()

def _doc_to_dict(doc):
    if not doc:
        return None
    doc["id"] = str(doc["_id"])
    doc.pop("_id", None)
    return doc

@router.get("/types")
def list_types(db=Depends(get_db)):
    types = db.blogs.distinct("type")
    # Filter out None/empty types if needed
    clean_types = [t for t in types if t]
    # Return as list of objects to match frontend expectations if necessary, 
    # or just simple list. Frontend 'Category' interface expects {id, name, image}.
    # We'll return simple objects for now.
    return {"items": [{"id": t, "name": t} for t in clean_types]}

@router.get("/")
def list_blogs(
    type: str = None, 
    page: int = 1, 
    limit: int = 100, 
    db=Depends(get_db)
):
    query = {}
    if type and type != "All":
        query["type"] = type

    skip = (page - 1) * limit
    
    total = db.blogs.count_documents(query)
    cursor = db.blogs.find(query).sort("created_at", -1).skip(skip).limit(limit)
    docs = list(cursor)
    
    return {
        "items": [_doc_to_dict(d) for d in docs],
        "total": total,
        "page": page,
        "limit": limit,
        "pages": (total + limit - 1) // limit
    }

@router.get("/{blog_id}")
def get_blog(blog_id: str, db=Depends(get_db)):
    try:
        doc = db.blogs.find_one({"_id": ObjectId(blog_id)})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid blog id")
    if not doc:
        raise HTTPException(status_code=404, detail="Blog not found")
    return _doc_to_dict(doc)

@router.post("/", status_code=201)
def create_blog(payload: BlogCreate, user = Depends(require_admin), db=Depends(get_db)):
    doc = payload.dict()
    doc.update({
        "author": user["username"],
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow()
    })
    res = db.blogs.insert_one(doc)
    return {"id": str(res.inserted_id)}

@router.put("/{blog_id}")
def update_blog(blog_id: str, payload: BlogUpdate, user = Depends(require_admin), db=Depends(get_db)):
    try:
        oid = ObjectId(blog_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid blog id")
    doc = {k: v for k, v in payload.dict().items() if v is not None}
    if not doc:
        raise HTTPException(status_code=400, detail="No fields to update")
    doc["updated_at"] = datetime.utcnow()
    result = db.blogs.update_one({"_id": oid}, {"$set": doc})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Blog not found")
    return {"status": "updated"}

@router.delete("/{blog_id}", status_code=204)
def delete_blog(blog_id: str, user = Depends(require_admin), db=Depends(get_db)):
    try:
        oid = ObjectId(blog_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid blog id")
    result = db.blogs.delete_one({"_id": oid})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Blog not found")
    return {}
