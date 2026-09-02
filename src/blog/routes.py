from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query
from fastapi.responses import Response, StreamingResponse
import httpx
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


def _ensure_upload_dir() -> bool:
    """Create the local uploads directory on demand.

    Never do this at import time.  A serverless filesystem is read-only outside
    /tmp, so a module-level mkdir raises OSError while this module is being
    imported, which takes down every route in the app - not just uploads.  It
    only stayed quiet before because the uploads/ directory was committed, so
    mkdir(exist_ok=True) had nothing to create.  Cloudinary is the real upload
    path in production; this local directory is the development fallback.
    """
    try:
        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        return True
    except OSError as exc:
        print(f"[uploads] local upload directory unavailable: {exc}")
        return False

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


# A blog series is a name shared by a set of posts plus a part number on each
# post (set via series_name/series_part on the blog document itself). Kept as
# its own collection - same shape as types/categories above - so the admin UI
# offers a dropdown of existing series instead of free text, and a rename
# updates every post in one place instead of relying on everyone typing the
# exact same string.

@router.get("/series")
def list_series(db=Depends(get_db)):
    docs = list(db.series.find().sort("name", 1))
    return {"items": [{"id": str(d["_id"]), "name": d["name"]} for d in docs]}


@router.post("/series", status_code=201)
def create_series(name: str = Form(...), user=Depends(require_admin), db=Depends(get_db)):
    name = name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Series name is required")
    existing = db.series.find_one({"name": name})
    if existing:
        return {"id": str(existing["_id"]), "name": existing["name"]}
    res = db.series.insert_one({
        "name": name,
        "created_by": user["username"],
        "created_at": datetime.utcnow(),
    })
    return {"id": str(res.inserted_id), "name": name}


@router.put("/series/{series_id}")
def rename_series(series_id: str, name: str = Form(...), user=Depends(require_admin), db=Depends(get_db)):
    try:
        oid = ObjectId(series_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid series id")
    existing = db.series.find_one({"_id": oid})
    if not existing:
        raise HTTPException(status_code=404, detail="Series not found")
    new_name = name.strip()
    if not new_name:
        raise HTTPException(status_code=400, detail="Series name is required")
    old_name = existing["name"]
    db.series.update_one({"_id": oid}, {"$set": {"name": new_name}})
    if old_name != new_name:
        # Keep every post's series_name pointed at the renamed series instead
        # of silently splitting it into "old name" and "new name" groups.
        db.blogs.update_many({"series_name": old_name}, {"$set": {"series_name": new_name}})
    return {"status": "updated", "name": new_name}


@router.delete("/series/{series_id}", status_code=204)
def delete_series(series_id: str, user=Depends(require_admin), db=Depends(get_db)):
    try:
        oid = ObjectId(series_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid series id")
    result = db.series.delete_one({"_id": oid})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Series not found")
    return {}


@router.get("/series/{series_name}/posts")
def list_series_posts(series_name: str, db=Depends(get_db)):
    """Ordered parts of a series, for prev/next navigation on the post page."""
    cursor = db.blogs.find(
        {"series_name": series_name},
        {"title": 1, "series_part": 1},
    ).sort([("series_part", 1), ("created_at", 1)])
    items = [
        {"id": str(d["_id"]), "title": d["title"], "series_part": d.get("series_part")}
        for d in cursor
    ]
    return {"items": items}


@router.get("/{blog_id}")
def get_blog(blog_id: str, db=Depends(get_db)):
    try:
        doc = db.blogs.find_one({"_id": ObjectId(blog_id)})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid blog id")
    if not doc:
        raise HTTPException(status_code=404, detail="Blog not found")
    return _doc_to_dict(doc)


@router.get("/{blog_id}/og-image")
async def get_og_image(blog_id: str, db=Depends(get_db)):
    """
    Proxy endpoint that serves the blog's cover image with no-cache headers.
    LinkedIn and other crawlers will always get the freshest image from this URL.
    """
    try:
        doc = db.blogs.find_one({"_id": ObjectId(blog_id)})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid blog id")
    if not doc or not doc.get("cover_image"):
        raise HTTPException(status_code=404, detail="Image not found")

    image_url = doc["cover_image"]
    # Resolve relative URLs
    if not image_url.startswith("http"):
        # Local file — read from disk
        local_path = Path(image_url.lstrip("/"))
        if not local_path.exists():
            raise HTTPException(status_code=404, detail="Image file not found")
        content = local_path.read_bytes()
        ext = local_path.suffix.lower()
        media_type = {
            ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
            ".png": "image/png", ".webp": "image/webp",
            ".gif": "image/gif",
        }.get(ext, "image/jpeg")
        return Response(
            content=content,
            media_type=media_type,
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate, max-age=0",
                "Pragma": "no-cache",
                "Expires": "0",
            },
        )

    # Remote URL (Cloudinary etc.) — proxy it
    async with httpx.AsyncClient(follow_redirects=True) as client:
        resp = await client.get(image_url)
        if resp.status_code != 200:
            raise HTTPException(status_code=502, detail="Failed to fetch image")
        content_type = resp.headers.get("content-type", "image/jpeg")
        return Response(
            content=resp.content,
            media_type=content_type,
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate, max-age=0",
                "Pragma": "no-cache",
                "Expires": "0",
            },
        )

@router.post("/upload-image", status_code=201)
def upload_image(
    cover: UploadFile = File(...),
    user = Depends(require_admin),
):
    """
    Upload an image for use in blog content (rich text editor).
    Returns the image URL.
    """
    try:
        if _cloud_name and _cloud_key and _cloud_secret:
            # Upload to Cloudinary
            contents = cover.file.read()
            public_id = f"concepts_blog/content/{uuid.uuid4().hex}"
            result = cloudinary.uploader.upload(
                io.BytesIO(contents),
                public_id=public_id,
                folder="concepts_blog/content",
                resource_type="image",
            )
            image_url = result.get("secure_url") or result.get("url")
        else:
            # Fallback to local storage - return full URL
            ext = Path(cover.filename).suffix
            filename = f"{uuid.uuid4().hex}{ext}"
            dest = UPLOAD_DIR / filename
            _ensure_upload_dir()
            with dest.open("wb") as f:
                f.write(cover.file.read())
            # Return full URL for local uploads (accessible from frontend)
            image_url = f"http://127.0.0.1:8000/uploads/{filename}"
        
        return {"url": image_url, "image_url": image_url}
    except Exception as e:
        print(f"Image upload failed: {e}")
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")


@router.post("/", status_code=201)
def create_blog(
    title: str = Form(...),
    content: str = Form(...),
    tags: str = Form(None),
    type: str = Form(None),
    series_name: str = Form(None),
    series_part: str = Form(None),
    cover: UploadFile = File(None),
    user = Depends(require_admin),
    db=Depends(get_db)
):
    # handle tags (comma separated)
    tag_list = []
    if tags:
        tag_list = [t.strip() for t in tags.split(",") if t.strip()]

    # series_part arrives as a form string (possibly empty) rather than an
    # int so a blank value doesn't fail FastAPI's request validation.
    series_part_value = None
    if series_part:
        try:
            series_part_value = int(series_part)
        except ValueError:
            series_part_value = None

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
                _ensure_upload_dir()
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
        "series_name": series_name or None,
        "series_part": series_part_value,
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
    series_name: str = Form(None),
    series_part: str = Form(None),
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
    # The admin form always sends these two (empty string when the post is
    # not part of a series), so an explicit "" here means "detach from the
    # series" rather than "field omitted" - unlike `type` above, this field
    # can be cleared once set.
    if series_name is not None:
        update_data["series_name"] = series_name or None
    if series_part is not None:
        if series_part == "":
            update_data["series_part"] = None
        else:
            try:
                update_data["series_part"] = int(series_part)
            except ValueError:
                pass

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
                    invalidate=True,  # Bust Cloudinary CDN cache
                )
                cover_url = result.get("secure_url") or result.get("url")
                update_data["cover_image"] = cover_url
            else:
                ext = Path(cover.filename).suffix
                filename = f"{uuid.uuid4().hex}{ext}"
                dest = UPLOAD_DIR / filename
                _ensure_upload_dir()
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
