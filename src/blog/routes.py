from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query
from src.database.connection import get_db
from src.models.schemas import BlogCreate, BlogUpdate
from src.auth.deps import get_current_user, require_admin
from src.utils.cloudinary_upload import upload_image_to_cloudinary, delete_image_from_cloudinary
from bson import ObjectId
from datetime import datetime
import os
import uuid
import io
from pathlib import Path
import cloudinary
import cloudinary.uploader

router = APIRouter()

# configure cloudinary from environment if available
_cloud_name = os.environ.get("CLOUDINARY_CLOUD_NAME")
_cloud_key = os.environ.get("CLOUDINARY_API_KEY")
_cloud_secret = os.environ.get("CLOUDINARY_API_SECRET")
if _cloud_name and _cloud_key and _cloud_secret:
    cloudinary.config(
        cloud_name=_cloud_name,
        api_key=_cloud_key,
        api_secret=_cloud_secret,
        secure=True,
    )

# directory to store uploaded files (served from /uploads) - kept for backward compatibility
UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

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


@router.get("/types")
def list_types(db=Depends(get_db)):
    docs = list(db.types.find().sort("name", 1))
    return {"items": [{"id": str(d["_id"]), "name": d["name"], "image": d.get("image")} for d in docs]}


@router.post("/types", status_code=201)
def create_type(
    name: str = Form(...), 
    image: UploadFile | None = File(None),
    user=Depends(require_admin), 
    db=Depends(get_db)
):
    if db.types.find_one({"name": name}):
        raise HTTPException(status_code=400, detail="Type already exists")
    
    image_url = None
    if image:
        try:
            if _cloud_name and _cloud_key and _cloud_secret:
                contents = image.file.read()
                public_id = f"concepts_type/{uuid.uuid4().hex}"
                result = cloudinary.uploader.upload(
                    io.BytesIO(contents),
                    public_id=public_id,
                    folder="concepts_type",
                    resource_type="image",
                )
                image_url = result.get("secure_url") or result.get("url")
            else:
                ext = Path(image.filename).suffix
                filename = f"type_{uuid.uuid4().hex}{ext}"
                dest = UPLOAD_DIR / filename
                with dest.open("wb") as f:
                    f.write(image.file.read())
                image_url = f"/uploads/{filename}"
        except Exception:
            image_url = None

    res = db.types.insert_one({
        "name": name, 
        "image": image_url,
        "created_by": user["username"], 
        "created_at": datetime.utcnow()
    })
    return {"id": str(res.inserted_id), "name": name, "image": image_url}

@router.delete("/types/{type_id}", status_code=204)
def delete_type(type_id: str, user=Depends(require_admin), db=Depends(get_db)):
    try:
        oid = ObjectId(type_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid type id")
    result = db.types.delete_one({"_id": oid})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Type not found")
    return {}

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
    tags: str = Form(None),
    type: str = Form(None),
    cover: UploadFile = File(None),
    user = Depends(require_admin),
    db=Depends(get_db)
):
    # handle tags (comma separated)
    tag_list = []
    if tags:
        tag_list = [t.strip() for t in tags.split(",") if t.strip()]

    cover_url = None
    if cover:
        # If Cloudinary is configured, upload to Cloudinary and use the returned URL
        try:
            if _cloud_name and _cloud_key and _cloud_secret:
                # read bytes and upload
                contents = cover.file.read()
                public_id = f"concepts_blog/{uuid.uuid4().hex}"
                result = cloudinary.uploader.upload(
                    io.BytesIO(contents),
                    public_id=public_id,
                    folder="concepts_blog",
                    resource_type="image",
                )
                cover_url = result.get("secure_url") or result.get("url")
            else:
                # fallback to local storage
                ext = Path(cover.filename).suffix
                filename = f"{uuid.uuid4().hex}{ext}"
                dest = UPLOAD_DIR / filename
                with dest.open("wb") as f:
                    f.write(cover.file.read())
                cover_url = f"/uploads/{filename}"
        except Exception as e:
            print(f"Upload failed: {e}")
            # don't crash on upload failure; store None
            cover_url = None

    doc = {
        "title": title,
        "content": content,
        "tags": tag_list,
        "cover_image": cover_url,
        "type": type,
        "author": user["username"],
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    }

    res = db.blogs.insert_one(doc)
    return {"id": str(res.inserted_id), "image_url": cover_url}

from typing import Optional

@router.put("/{blog_id}")
def update_blog(
    blog_id: str,
    title: str = Form(None),
    content: str = Form(None),
    type: str = Form(None),
    cover: Optional[UploadFile] = File(None),
    user = Depends(require_admin),
    db=Depends(get_db)
):
    try:
        oid = ObjectId(blog_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid blog id")
    
    # Check if blog exists first
    existing_blog = db.blogs.find_one({"_id": oid})
    if not existing_blog:
        raise HTTPException(status_code=404, detail="Blog not found")

    update_data = {}
    if title is not None:
        update_data["title"] = title
    if content is not None:
        update_data["content"] = content
    if type is not None:
        update_data["type"] = type

    if cover:
        # Handle new image upload
        try:
            if _cloud_name and _cloud_key and _cloud_secret:
                contents = cover.file.read()
                public_id = f"concepts_blog/{uuid.uuid4().hex}"
                result = cloudinary.uploader.upload(
                    io.BytesIO(contents),
                    public_id=public_id,
                    folder="concepts_blog",
                    resource_type="image",
                )
                cover_url = result.get("secure_url") or result.get("url")
                update_data["cover_image"] = cover_url
            else:
                ext = Path(cover.filename).suffix
                filename = f"{uuid.uuid4().hex}{ext}"
                dest = UPLOAD_DIR / filename
                with dest.open("wb") as f:
                    f.write(cover.file.read())
                update_data["cover_image"] = f"/uploads/{filename}"
        except Exception:
            pass # Keep old image if upload fails

    if not update_data:
         # If nothing provided to update, just return success
        return {"status": "no changes"}

    update_data["updated_at"] = datetime.utcnow()
    db.blogs.update_one({"_id": oid}, {"$set": update_data})
    return {"status": "updated"}

@router.delete("/{blog_id}", status_code=204)
def delete_blog(blog_id: str, user = Depends(require_admin), db=Depends(get_db)):
    try:
        oid = ObjectId(blog_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid blog id")
    
    # Get blog to delete image from Cloudinary
    blog = db.blogs.find_one({"_id": oid})
    if not blog:
        raise HTTPException(status_code=404, detail="Blog not found")
    
    # Delete image from Cloudinary if exists
    if blog.get("image_public_id"):
        try:
            delete_image_from_cloudinary(blog["image_public_id"])
        except Exception:
            pass  # Continue even if image deletion fails
    
    result = db.blogs.delete_one({"_id": oid})
    return {}
