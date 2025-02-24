from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from sendEmail import AIService

router = APIRouter()

class EmailRequest(BaseModel):
    to: str
    subject: str
    body: str
    sender_name: str
    receiver_name: str

@router.post("/send-email")
async def send_email(request: EmailRequest):
    try:
        email_service = AIService()
        result = await email_service.send_email_via_assistant(
            to=request.to,
            subject=request.subject,
            body=request.body
        )
        
        if result.get("status") == "success":
            return {
                "status": "success",
                "message": "Email sent successfully",
                "data": result
            }
        else:
            raise HTTPException(
                status_code=500,
                detail=result.get("message", "Failed to send email")
            )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=str(e)
        ) 