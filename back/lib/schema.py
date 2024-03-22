from pydantic import BaseModel, Field, ConfigDict, PlainSerializer, AfterValidator, WithJsonSchema
from typing import Union, Annotated, Any, Optional
from bson.objectid import ObjectId

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    username: Union[str, None] = None

# DeSerialize MongoDB ObjectId
def validate_object_id(v: Any) -> ObjectId:
    if isinstance(v, ObjectId):
        return v
    if ObjectId.is_valid(v):
        return ObjectId(v)
    raise ValueError("Invalid ObjectId")

ObjectIdType = Annotated[
    Union[str, ObjectId],
    PlainSerializer(lambda x: str(x), return_type=str, when_used="json"),
    AfterValidator(validate_object_id),
    WithJsonSchema({"type": "string"}, mode="serialization"),
]

class Lead(BaseModel):
    model_config = ConfigDict()

    id: ObjectIdType = Field(None, alias="_id")
    encryptedUid: str
    nickName: str
    userPhotoUrl: str
    rank: int
    value: Optional[int] = None
    positionShared: bool
    twitterUrl: Optional[str] = None
    updateTime: int
    followerCount: int
    leaderboardUrl: str

    class Config:
        arbitrary_types_allowed = True
        populate_by_alias=True
        populate_by_name=True
        validate_assignment=True

class User(BaseModel):
    model_config = ConfigDict()

    id: ObjectIdType = Field(None, alias="_id")
    username: str
    password_hash: str

    class Config:
        arbitrary_types_allowed = True
        populate_by_alias=True
        populate_by_name=True
        validate_assignment=True

# Pydantic model for login credentials
class LoginCredentials(BaseModel):
    username: str
    password: str

# Pydantic model for user registration
class RegisterUser(BaseModel):
    username: str
    email: str  # Assuming you want to use this somewhere
    password: str