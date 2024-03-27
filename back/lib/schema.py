from pydantic import BaseModel, Field, ConfigDict, PlainSerializer, AfterValidator, WithJsonSchema
from typing import Union, Annotated, Any, Optional, List, Dict
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

class MongoModel(BaseModel):
    id: ObjectIdType = Field(None, alias="_id")

    class Config:
        arbitrary_types_allowed = True
        populate_by_alias=True
        populate_by_name=True
        validate_assignment=True

class PositionHistory(MongoModel):
    symbol: str
    position_type: str = Field(alias='type')
    opened: int
    closed: Optional[int] = None
    avgCost: float
    avgClosePrice: float
    closingPnl: float
    maxOpenInterest: float
    closedVolume: float
    isolated: str
    side: str
    status: str
    updateTime: int
    leaderId: ObjectIdType = Field(None)

class Position(MongoModel):
    symbol: str
    collateral: str
    positionAmount: str  # Assuming this is a string representation of a decimal number
    entryPrice: str  # Same as above
    unrealizedProfit: str  # Same as above
    cumRealized: str  # Same as above
    askNotional: str  # Same as above
    bidNotional: str  # Same as above
    notionalValue: str  # Same as above
    markPrice: str  # Same as above
    leverage: int
    isolated: bool
    isolatedWallet: str  # Assuming this is a string representation of a decimal number
    adl: int
    positionSide: str
    breakEvenPrice: str  # Same as above
    leaderId: ObjectIdType = Field(None)

class Transfer(MongoModel):
    time: int
    coin: str
    amount: float
    from_account: str = Field(alias='from')  # 'from' is a Python reserved keyword, so we use an alias
    to: str
    transType: str
    leaderId: ObjectIdType = Field(None)

class Leader(MongoModel):
    binanceId: str
    profileUrl: str
    userId: int
    nickname: str
    avatarUrl: str
    status: str
    initInvestAsset: str
    positionShow: bool
    updateTime: int
    totalBalance: float
    liveRatio: float
    positionsValue: float
    positionsNotionalValue: float
    mix: Dict[str, float]

class APIResponse(BaseModel):
    success: bool = False
    message: str = ''

class LeaderTickData(BaseModel):
    leader: Leader = None
    positions: Optional[List[Position]] = None
    position_history: Optional[List[PositionHistory]] = None
    transfer_history: Optional[List[Transfer]] = None

class LeaderTickResponse(APIResponse):
    data: LeaderTickData

class Lead(BaseModel):
    model_config = ConfigDict()

    id: ObjectIdType = Field(None, alias="_id")
    leadId: str
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

class Params(BaseModel):
    dataType:  Optional[str] = None
    timeRange:  Optional[str] = None
    pageNumber:  Optional[int] = None
    pageSize:  Optional[int] = None