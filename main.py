import os
from typing import List, Optional, Literal, Any, Dict
from fastapi import FastAPI, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
from bson import ObjectId
from hashlib import sha256
from datetime import datetime

from database import db, create_document, get_documents

app = FastAPI(title="Credit Card Complaint Portal API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Utils

def oid_str(o: Any) -> str:
    try:
        return str(o)
    except Exception:
        return o


def serialize_doc(doc: Dict) -> Dict:
    if not doc:
        return doc
    d = {**doc}
    if "_id" in d:
        d["id"] = str(d.pop("_id"))
    # convert datetimes
    for k, v in list(d.items()):
        if isinstance(v, datetime):
            d[k] = v.isoformat()
    return d


# Schemas for requests
class RegisterRequest(BaseModel):
    name: str
    email: EmailStr
    password: str
    role: Literal["user", "operator", "admin"] = "user"


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class ComplaintCreate(BaseModel):
    user_id: str
    title: str
    category: Literal["limit", "tagihan", "kartu_hilang", "penipuan", "biaya", "lainnya"] = "lainnya"
    description: str
    attachments: List[str] = []
    priority: Literal["rendah", "sedang", "tinggi"] = "sedang"


class ComplaintUpdate(BaseModel):
    status: Optional[Literal["baru", "diproses", "selesai", "ditolak"]] = None
    assigned_to: Optional[str] = None
    note: Optional[str] = None


class FaqCreate(BaseModel):
    question: str
    answer: str
    is_active: bool = True


class NewsCreate(BaseModel):
    title: str
    content: str
    cover_image: Optional[str] = None
    is_published: bool = False


class ContactMessageCreate(BaseModel):
    name: str
    email: EmailStr
    subject: str
    message: str


@app.get("/")
def root():
    return {"name": "Credit Card Complaint Portal API", "status": "ok"}


@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }
    try:
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
            response["database_name"] = getattr(db, 'name', None) or "unknown"
            response["connection_status"] = "Connected"
            try:
                response["collections"] = db.list_collection_names()[:10]
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️ Connected but Error: {str(e)[:80]}"
        else:
            response["database"] = "⚠️ Available but not initialized"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:80]}"
    return response


# -------------------- AUTH (Simple) --------------------
@app.post("/api/register")
def register(req: RegisterRequest):
    # Check existing
    existing = db.user.find_one({"email": req.email})
    if existing:
        raise HTTPException(status_code=400, detail="Email sudah terdaftar")
    password_hash = sha256(req.password.encode()).hexdigest()
    user_data = {
        "name": req.name,
        "email": req.email,
        "password_hash": password_hash,
        "role": req.role,
        "avatar_url": None,
        "is_active": True,
    }
    new_id = create_document("user", user_data)
    user = db.user.find_one({"_id": ObjectId(new_id)})
    return serialize_doc(user)


@app.post("/api/login")
def login(req: LoginRequest):
    user = db.user.find_one({"email": req.email})
    if not user:
        raise HTTPException(status_code=401, detail="Email atau password salah")
    password_hash = sha256(req.password.encode()).hexdigest()
    if user.get("password_hash") != password_hash:
        raise HTTPException(status_code=401, detail="Email atau password salah")
    # Simple sessionless login: return user profile (no JWT for demo)
    u = serialize_doc(user)
    u.pop("password_hash", None)
    return {"user": u}


# -------------------- COMPLAINTS --------------------
@app.post("/api/complaints")
def create_complaint(req: ComplaintCreate):
    # Validate user exists
    try:
        uid = ObjectId(req.user_id)
    except Exception:
        raise HTTPException(400, detail="user_id tidak valid")
    if not db.user.find_one({"_id": uid}):
        raise HTTPException(404, detail="User tidak ditemukan")
    data = {
        "user_id": req.user_id,
        "title": req.title,
        "category": req.category,
        "description": req.description,
        "attachments": req.attachments,
        "status": "baru",
        "assigned_to": None,
        "priority": req.priority,
        "sla_due_at": None,
        "notes": [],
    }
    new_id = create_document("complaint", data)
    doc = db.complaint.find_one({"_id": ObjectId(new_id)})
    return serialize_doc(doc)


@app.get("/api/complaints")
def list_complaints(status: Optional[str] = None, user_id: Optional[str] = None, assigned_to: Optional[str] = None, limit: int = 100):
    q: Dict[str, Any] = {}
    if status:
        q["status"] = status
    if user_id:
        q["user_id"] = user_id
    if assigned_to:
        q["assigned_to"] = assigned_to
    docs = get_documents("complaint", q, limit)
    return [serialize_doc(d) for d in docs]


@app.patch("/api/complaints/{complaint_id}")
def update_complaint(complaint_id: str, req: ComplaintUpdate):
    try:
        cid = ObjectId(complaint_id)
    except Exception:
        raise HTTPException(400, detail="ID tidak valid")
    updates: Dict[str, Any] = {}
    if req.status is not None:
        updates["status"] = req.status
    if req.assigned_to is not None:
        updates["assigned_to"] = req.assigned_to
    if req.note:
        db.complaint.update_one({"_id": cid}, {"$push": {"notes": {"text": req.note, "at": datetime.utcnow().isoformat()}}})
    if updates:
        db.complaint.update_one({"_id": cid}, {"$set": updates})
    doc = db.complaint.find_one({"_id": cid})
    if not doc:
        raise HTTPException(404, detail="Pengaduan tidak ditemukan")
    return serialize_doc(doc)


# -------------------- FAQ --------------------
@app.get("/api/faqs")
def get_faqs(only_active: bool = True):
    q = {"is_active": True} if only_active else {}
    docs = get_documents("faq", q, None)
    return [serialize_doc(d) for d in docs]


@app.post("/api/faqs")
def create_faq(req: FaqCreate):
    new_id = create_document("faq", req.model_dump())
    doc = db.faq.find_one({"_id": ObjectId(new_id)})
    return serialize_doc(doc)


# -------------------- NEWS --------------------
@app.get("/api/news")
def get_news(only_published: bool = True, limit: int = 50):
    q = {"is_published": True} if only_published else {}
    docs = get_documents("news", q, limit)
    return [serialize_doc(d) for d in docs]


@app.post("/api/news")
def create_news(req: NewsCreate):
    data = req.model_dump()
    if data.get("is_published") and "published_at" not in data:
        data["published_at"] = datetime.utcnow().isoformat()
    new_id = create_document("news", data)
    doc = db.news.find_one({"_id": ObjectId(new_id)})
    return serialize_doc(doc)


# -------------------- CONTACT --------------------
@app.post("/api/contact")
def create_contact(req: ContactMessageCreate):
    new_id = create_document("contactmessage", req.model_dump())
    doc = db.contactmessage.find_one({"_id": ObjectId(new_id)})
    return serialize_doc(doc)


# -------------------- DASHBOARD SUMMARY --------------------
@app.get("/api/dashboard/summary")
def dashboard_summary():
    total_users = db.user.count_documents({}) if db else 0
    total_complaints = db.complaint.count_documents({}) if db else 0
    open_complaints = db.complaint.count_documents({"status": {"$in": ["baru", "diproses"]}}) if db else 0
    closed_complaints = db.complaint.count_documents({"status": "selesai"}) if db else 0
    total_faqs = db.faq.count_documents({"is_active": True}) if db else 0
    total_news = db.news.count_documents({"is_published": True}) if db else 0
    return {
        "users": total_users,
        "complaints": total_complaints,
        "complaints_open": open_complaints,
        "complaints_closed": closed_complaints,
        "faqs": total_faqs,
        "news": total_news,
    }


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
