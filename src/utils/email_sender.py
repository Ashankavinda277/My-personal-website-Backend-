import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
from dotenv import load_dotenv

load_dotenv()

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587
SMTP_EMAIL = os.getenv("SMTP_EMAIL", "concepts.update@gmail.com")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "").replace(" ", "")  # Remove any spaces


def send_email(to_email: str, subject: str, body: str, reply_to_name: str = ""):
    """
    Send an email using Gmail SMTP
    
    Args:
        to_email: Recipient email address
        subject: Email subject
        body: Email body (plain text)
        reply_to_name: Original sender's name for context
    """
    if not SMTP_PASSWORD:
        raise Exception("SMTP_PASSWORD not configured in environment variables")
    
    try:
        # Create message
        message = MIMEMultipart("alternative")
        message["From"] = f"Concepts Blog <{SMTP_EMAIL}>"
        message["To"] = to_email
        message["Subject"] = subject
        
        # Create email body with context
        email_content = f"""
Hi {reply_to_name},

{body}

---
Best regards,
Concepts Blog Team
concepts.update@gmail.com
"""
        
        # Attach plain text
        part = MIMEText(email_content, "plain")
        message.attach(part)
        
        # Create SMTP session
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()  # Enable encryption
            server.login(SMTP_EMAIL, SMTP_PASSWORD)
            server.send_message(message)
        
        return True
    except Exception as e:
        print(f"Failed to send email: {str(e)}")
        raise e
