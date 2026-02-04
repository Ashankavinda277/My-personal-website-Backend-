import cloudinary
import cloudinary.uploader
from fastapi import UploadFile
import os
from dotenv import load_dotenv

load_dotenv()

# Configure Cloudinary
cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET")
)

async def upload_image_to_cloudinary(file: UploadFile, folder: str = "blog_images"):
    """
    Upload an image to Cloudinary and return the URL
    """
    try:
        # Read file contents
        contents = await file.read()
        
        # Upload to Cloudinary
        result = cloudinary.uploader.upload(
            contents,
            folder=folder,
            resource_type="image",
            allowed_formats=["jpg", "jpeg", "png", "gif", "webp"]
        )
        
        # Return the secure URL
        return {
            "url": result.get("secure_url"),
            "public_id": result.get("public_id")
        }
    except Exception as e:
        raise Exception(f"Failed to upload image: {str(e)}")

def delete_image_from_cloudinary(public_id: str):
    """
    Delete an image from Cloudinary using its public_id
    """
    try:
        result = cloudinary.uploader.destroy(public_id)
        return result
    except Exception as e:
        raise Exception(f"Failed to delete image: {str(e)}")
