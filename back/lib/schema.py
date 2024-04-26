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
    updated: int
    updated_date: str

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
    updatedAt: int
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


class LeaderDetailData(BaseModel):
    userId: int
    leadOwner: bool
    hasCopy: bool
    leadPortfolioId: str
    nickname: str
    nicknameTranslate: Optional[str]
    avatarUrl: str
    status: str
    description: str
    descTranslate: Optional[str]
    favoriteCount: int
    currentCopyCount: int
    maxCopyCount: int
    totalCopyCount: int
    marginBalance: str
    initInvestAsset: str
    futuresType: str
    aumAmount: str
    copierPnl: str
    copierPnlAsset: str
    profitSharingRate: str
    unrealizedProfitShareAmount: str
    startTime: int
    endTime: Optional[int]
    closedTime: Optional[int]
    tag: List[str]
    positionShow: bool
    mockCopyCount: int
    sharpRatio: Optional[str]
    hasMock: bool
    lockPeriod: Optional[int]
    copierLockPeriodTime: Optional[int]
    badgeName: Optional[str]
    badgeModifyTime: Optional[int]
    badgeCopierCount: Optional[int]
    tagItemVos: List[Dict]
    feedAgreement: bool
    feedShareSwitch: bool
    feedSharePushLimit: int
    fixedRadioMinCopyUsd: int
    fixedAmountMinCopyUsd: int
    portfolioType: str
    publicLeadPortfolioId: str
    privateLeadPortfolioId: Optional[str]
    inviteCodeCount: int
    favorite: bool

class LeaderAccountData(BaseModel):
    levered_ratio: Optional[float]
    unlevered_ratio: Optional[float]

class LeaderPerformanceDate(BaseModel):
    roi: float
    pnl: float
    mdd: float
    winRate: float
    winOrders: float
    totalOrder: float
    sharpRatio: str

class LeaderGroupedPositionsData(BaseModel):
    symbol: Dict[str, str]
    positionAmount_SUM: Dict[str, float]
    unrealizedProfit_SUM: Dict[str, float]
    cumRealized_SUM: Dict[str, float]
    notionalValue_SUM: Dict[str, float]
    markPrice_AVERAGE: Dict[str, float]
    ABSOLUTE_LEVERED_VALUE_SUM: Dict[str, float]
    ABSOLUTE_UNLEVERED_VALUE_SUM: Dict[str, float]
    entryPrice_AVERAGE: Dict[str, float]
    leverage_AVERAGE: Dict[str, float]
    breakEvenPrice_AVERAGE: Dict[str, float]
    positionSide: Dict[str, str]
    LEVERED_POSITION_SHARE: Dict[str, float]
    UNLEVERED_POSITION_SHARE: Dict[str, float]
    LEVERED_RATIO: Dict[str, float]
    UNLEVERED_RATIO: Dict[str, float]

class LeaderChartItem(BaseModel):
    value: float
    dataType: str
    dateTime: int

class Leader(MongoModel):
    binanceId: str
    detail: LeaderDetailData
    account: LeaderAccountData
    # grouped_positions: LeaderGroupedPositionsData
    performance: LeaderPerformanceDate
    chart: List[LeaderChartItem]


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

class AllLeaders(APIResponse):
    data: List[Leader]

# class Lead(BaseModel):
#     model_config = ConfigDict()

#     id: ObjectIdType = Field(None, alias="_id")
#     leadId: str
#     encryptedUid: str
#     nickName: str
#     userPhotoUrl: str
#     rank: int
#     value: Optional[int] = None
#     positionShared: bool
#     twitterUrl: Optional[str] = None
#     updatedAt: int
#     followerCount: int
#     leaderboardUrl: str

#     class Config:
#         arbitrary_types_allowed = True
#         populate_by_alias=True
#         populate_by_name=True
#         validate_assignment=True


class UserDetailData(BaseModel):
    TARGET_RATIO: float
    active: bool
    chat_id: int
    favorite_leaders: List[str]

class UserAccountData(BaseModel):
    leverage: int
    value_USDT: float
    value_BTC: float
    levered_ratio: int
    unlevered_ratio: float
    collateral_margin_level: float
    collateral_value_USDT: float
    n_leaders: int
    active_leaders: List[str]

class UserLeadersData(BaseModel):
    WEIGHT: Dict[str, int]

class UserPositionsData(BaseModel):
    free: Dict[str, float]
    locked: Dict[str, float]
    borrowed: Dict[str, float]
    interest: Dict[str, float]
    netAsset: Dict[str, float]
    symbol: Dict[str, str]

class User(MongoModel):
    username: str
    detail: UserDetailData
    account: UserAccountData
    leaders: UserLeadersData
    positions: UserPositionsData


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