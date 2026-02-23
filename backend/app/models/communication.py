from pydantic import BaseModel
from typing import Optional


class CommunicationCreate(BaseModel):
    property_id: int
    method: str              # email, mail, phone, site_visit, text
    direction: str = "outbound"
    date_sent: Optional[str] = None
    subject: str = ""
    body: str = ""


class CommunicationUpdate(BaseModel):
    response_received: Optional[bool] = None
    response_date: Optional[str] = None
    response_notes: Optional[str] = None


class CommunicationResponse(BaseModel):
    id: int
    property_id: int
    method: str
    direction: str
    date_sent: Optional[str]
    subject: str
    body: str
    response_received: bool
    response_date: Optional[str]
    response_notes: str
    created_at: str

    class Config:
        from_attributes = True
