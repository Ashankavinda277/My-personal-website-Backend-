from fastapi import APIRouter, Depends, HTTPException, Form, File, UploadFile
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

@router.put("/types/{old_type}")
def rename_type(old_type: str, new_type: str = Form(...), user = Depends(require_admin), db=Depends(get_db)):
    # Update all blogs with old_type to new_type
    result = db.blogs.update_many(
        {"type": old_type},
        {"$set": {"type": new_type}}
    )
    return {"status": "updated", "modified_count": result.modified_count}

@router.delete("/types/{type_name}")
def delete_type(type_name: str, user = Depends(require_admin), db=Depends(get_db)):
    # Remove type from all blogs that have it (set to null or empty string)
    result = db.blogs.update_many(
        {"type": type_name},
        {"$unset": {"type": ""}}
    )
    return {"status": "deleted", "modified_count": result.modified_count}



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
def create_blog(
    title: str = Form(...),
    content: str = Form(...),
    type: str = Form(None),
    cover: UploadFile = File(None),
    user = Depends(require_admin),
    db=Depends(get_db)
):
    doc = {
        "title": title,
        "content": content,
        "type": type,
        "author": user["username"],
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow()
    }

    if cover:
        try:
            import cloudinary
            import cloudinary.uploader
            # Check if cloudinary is configured implicitly or provide basic cleanup for safety
            # If CLOUDINARY_URL is in env, this works auto-magically. 
            # Otherwise we might need to configure it. 
            # For now, we attempt upload if module exists and let it raise if unconfigured.
            
            # Helper to reset file cursor if needed, though upload usually handles it
            cover.file.seek(0)
            upload_result = cloudinary.uploader.upload(cover.file)
            doc["cover_image"] = upload_result.get("secure_url")
        except Exception as e:
            print(f"Cloudinary upload failed: {e}")
            # Fallback or just ignore image
            pass

    res = db.blogs.insert_one(doc)
    return {"id": str(res.inserted_id)}

@router.put("/{blog_id}")
def update_blog(
    blog_id: str,
    title: str = Form(None),
    content: str = Form(None),
    type: str = Form(None),
    cover: UploadFile = File(None),
    user = Depends(require_admin), 
    db=Depends(get_db)
):
    try:
        oid = ObjectId(blog_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid blog id")
    
    doc = {}
    if title: doc["title"] = title
    if content: doc["content"] = content
    if type: doc["type"] = type
    
    if cover:
        try:
            import cloudinary
            import cloudinary.uploader
            cover.file.seek(0)
            upload_result = cloudinary.uploader.upload(cover.file)
            doc["cover_image"] = upload_result.get("secure_url")
        except Exception as e:
            print(f"Cloudinary upload failed: {e}")
            pass

    if not doc:
        # If nothing sent to update, just return ok or error
        # Currently the frontend might send partial data
        # For a "no-op" update, we can just return success
        return {"status": "updated", "message": "No changes made"}

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
