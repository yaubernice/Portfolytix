from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class RegisterRequest(BaseModel): 
    model_config = ConfigDict(extra="forbid")

    email: EmailStr #pydantic checks the value has valid email format
    password: str = Field(min_length=8, max_length=128) #password length

    @field_validator("email") #normalize email
    @classmethod
    def normalize_email(cls, value: EmailStr) -> str:
        return str(value).lower() #convert email to lowercase


class LoginRequest(BaseModel): #login request schema
    model_config = ConfigDict(extra="forbid")

    email: EmailStr #pydantic checks the value has valid email format
    password: str = Field(min_length=1, max_length=128) #password length

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: EmailStr) -> str:
        return str(value).lower()


class UserOut(BaseModel): #user output schema
    # convert SQLAlchemy model to Pydantic model
    model_config = ConfigDict(from_attributes=True)

    id: UUID #user ID
    email: EmailStr #user email
    created_at: datetime #user creation time
    updated_at: datetime #user update time


class TokenOut(BaseModel): #token output schema
    access_token: str #access token
    token_type: str = "bearer" #token type
    expires_in: int #token expire time
