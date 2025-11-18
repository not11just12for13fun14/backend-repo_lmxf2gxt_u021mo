"""
Database Schemas for Public Banking Credit Card Complaint Portal

Each Pydantic model represents a collection in MongoDB.
Collection name = lowercase class name.
"""

from pydantic import BaseModel, Field, EmailStr
from typing import Optional, Literal, List
from datetime import datetime

# User and Auth
class User(BaseModel):
    name: str = Field(..., description="Full name")
    email: EmailStr = Field(..., description="Email address")
    password_hash: str = Field(..., description="BCrypt hash of the password")
    role: Literal["user", "operator", "admin"] = Field("user", description="Access level")
    avatar_url: Optional[str] = Field(None, description="Profile avatar URL")
    is_active: bool = Field(True, description="Whether the user is active")

# Complaint (Pengaduan)
class Complaint(BaseModel):
    user_id: str = Field(..., description="ID of the submitting user")
    title: str = Field(..., description="Complaint title")
    category: Literal[
        "limit", "tagihan", "kartu_hilang", "penipuan", "biaya", "lainnya"
    ] = Field("lainnya", description="Complaint category")
    description: str = Field(..., description="Detailed description of the complaint")
    attachments: List[str] = Field(default_factory=list, description="Attachment URLs")
    status: Literal["baru", "diproses", "selesai", "ditolak"] = Field(
        "baru", description="Complaint status workflow"
    )
    assigned_to: Optional[str] = Field(None, description="Operator user ID handling the complaint")
    priority: Literal["rendah", "sedang", "tinggi"] = Field("sedang")
    sla_due_at: Optional[datetime] = Field(None, description="SLA due time")
    notes: List[dict] = Field(default_factory=list, description="Operator/admin notes")

# FAQ
class Faq(BaseModel):
    question: str
    answer: str
    is_active: bool = True

# News / Info
class News(BaseModel):
    title: str
    content: str
    cover_image: Optional[str] = None
    published_at: Optional[datetime] = None
    is_published: bool = False

# Contact messages
class ContactMessage(BaseModel):
    name: str
    email: EmailStr
    subject: str
    message: str
    handled: bool = False

# Audit Log (optional helper)
class AuditLog(BaseModel):
    actor_id: str
    action: str
    resource: str
    resource_id: Optional[str] = None
    metadata: dict = {}
