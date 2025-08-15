from datetime import datetime, date
from pydantic import BaseModel, EmailStr, Field

class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)

class UserOut(BaseModel):
    id: int
    email: EmailStr
    created_at: datetime

    model_config = {"from_attributes": True}

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"

# Jobs
class JobOut(BaseModel):
    id: int
    external_id: str
    title: str
    company: str | None = None
    location: str | None = None
    url: str | None = None
    posted_at: datetime | None = None
    discovered_at: datetime | None = None

    model_config = {"from_attributes": True}

class JobResultOut(BaseModel):
    id: int
    day: date
    starred: bool
    job: JobOut

    model_config = {"from_attributes": True}