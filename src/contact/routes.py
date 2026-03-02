from fastapi import APIRouter, Depends, HTTPException
from src.models.schemas import ContactMessage
from src.database.connection import get_db
from src.utils.email_sender import send_email
from datetime import datetime
from pydantic import BaseModel
from bson import ObjectId

router = APIRouter()


class EmailReply(BaseModel):
    message_id: str
    reply_subject: str
    reply_body: str


@router.post("/submit")
def submit_contact_message(message: ContactMessage, db=Depends(get_db)):
    """
    Receive and store contact form submissions
    """
    try:
        # Create message document
        message_doc = {
            "name": message.name,
            "email": message.email,
            "subject": message.subject,
            "message": message.message,
            "submitted_at": datetime.utcnow(),
            "status": "new"  # Can be used to track if message was read/responded
        }
        
        # Insert into database
        result = db.contact_messages.insert_one(message_doc)
        
        return {
            "success": True,
            "message": "Thank you for reaching out! We'll get back to you soon.",
            "id": str(result.inserted_id)
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to submit message: {str(e)}")


@router.get("/messages")
def get_contact_messages(db=Depends(get_db)):
    """
    Retrieve all contact messages (for admin use)
    Could add authentication here to protect this endpoint
    """
    try:
        messages = []
        for msg in db.contact_messages.find().sort("submitted_at", -1):
            msg["_id"] = str(msg["_id"])
            # Ensure datetime is properly serialized as ISO format string
            if "submitted_at" in msg and msg["submitted_at"]:
                msg["submitted_at"] = msg["submitted_at"].isoformat() + "Z"
            if "replied_at" in msg and msg["replied_at"]:
                msg["replied_at"] = msg["replied_at"].isoformat() + "Z"
            messages.append(msg)
        
        return {"messages": messages, "count": len(messages)}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve messages: {str(e)}")


@router.post("/reply")
def reply_to_message(reply: EmailReply, db=Depends(get_db)):
    """
    Send an email reply to a contact message
    """
    try:
        # Get the original message
        message = db.contact_messages.find_one({"_id": ObjectId(reply.message_id)})
        
        if not message:
            raise HTTPException(status_code=404, detail="Message not found")
        
        # Send the email
        send_email(
            to_email=message["email"],
            subject=reply.reply_subject,
            body=reply.reply_body,
            reply_to_name=message["name"]
        )
        
        # Update message status to "replied"
        db.contact_messages.update_one(
            {"_id": ObjectId(reply.message_id)},
            {"$set": {
                "status": "replied",
                "replied_at": datetime.utcnow()
            }}
        )
        
        return {
            "success": True,
            "message": "Email sent successfully!"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to send email: {str(e)}")
