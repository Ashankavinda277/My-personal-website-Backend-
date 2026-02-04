from fastapi import APIRouter, Depends, HTTPException, File, UploadFile, Form
from src.database.connection import get_db
from src.models.schemas import BlogCreate, BlogUpdate
from src.auth.deps import get_current_user, require_admin
from src.utils.cloudinary_upload import upload_image_to_cloudinary, delete_image_from_cloudinary
from bson import ObjectId
from datetime import datetime
from typing import Optional, List

router = APIRouter()

def _doc_to_dict(doc):
    if not doc:
        return None
    doc["id"] = str(doc["_id"])
    doc.pop("_id", None)
    return doc

@router.get("/")
def list_blogs(db=Depends(get_db)):
    docs = list(db.blogs.find().sort("created_at", -1))
    return {"items": [_doc_to_dict(d) for d in docs]}

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
async def create_blog(
    title: str = Form(...),
    content: str = Form(...),
    tags: Optional[str] = Form("[]"),
    image: Optional[UploadFile] = File(None),
    user = Depends(require_admin),
    db=Depends(get_db)
):
    # Parse tags from JSON string
    import json
    try:
        tags_list = json.loads(tags) if tags else []
    except json.JSONDecodeError:
        tags_list = []
    
    # Handle image upload to Cloudinary
    image_url = None
    image_public_id = None
    
    if image:
        # Validate file type
        if not image.content_type or not image.content_type.startswith('image/'):
            raise HTTPException(status_code=400, detail="File must be an image")
        
        try:
            # Upload to Cloudinary
            upload_result = await upload_image_to_cloudinary(image)
            image_url = upload_result["url"]
            image_public_id = upload_result["public_id"]
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Image upload failed: {str(e)}")
    
    doc = {
        "title": title,
        "content": content,
        "tags": tags_list,
        "image_url": image_url,
        "image_public_id": image_public_id,
        "author": user["username"],
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow()
    }
    
    res = db.blogs.insert_one(doc)
    return {"id": str(res.inserted_id), "image_url": image_url}

@router.put("/{blog_id}")
async def update_blog(
    blog_id: str,
    title: Optional[str] = Form(None),
    content: Optional[str] = Form(None),
    tags: Optional[str] = Form(None),
    image: Optional[UploadFile] = File(None),
    user = Depends(require_admin),
    db=Depends(get_db)
):
    try:
        oid = ObjectId(blog_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid blog id")
    
    # Get existing blog to delete old image if needed
    existing_blog = db.blogs.find_one({"_id": oid})
    if not existing_blog:
        raise HTTPException(status_code=404, detail="Blog not found")
    
    doc = {}
    
    if title is not None:
        doc["title"] = title
    if content is not None:
        doc["content"] = content
    if tags is not None:
        import json
        try:
            doc["tags"] = json.loads(tags) if tags else []
        except json.JSONDecodeError:
            doc["tags"] = []
    
    # Handle image upload to Cloudinary
    if image:
        # Validate file type
        if not image.content_type or not image.content_type.startswith('image/'):
            raise HTTPException(status_code=400, detail="File must be an image")
        
        try:
            # Delete old image from Cloudinary if exists
            if existing_blog.get("image_public_id"):
                delete_image_from_cloudinary(existing_blog["image_public_id"])
            
            # Upload new image
            upload_result = await upload_image_to_cloudinary(image)
            doc["image_url"] = upload_result["url"]
            doc["image_public_id"] = upload_result["public_id"]
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Image upload failed: {str(e)}")
    
    if not doc:
        raise HTTPException(status_code=400, detail="No fields to update")
    
    doc["updated_at"] = datetime.utcnow()
    result = db.blogs.update_one({"_id": oid}, {"$set": doc})
    return {"status": "updated", "image_url": doc.get("image_url")}

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
