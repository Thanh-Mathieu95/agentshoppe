from __future__ import annotations

from datetime import datetime

from pydantic import NaiveDatetime
from enum import Enum

from sqlmodel import JSON, Column, Field, SQLModel


class Mode(str, Enum):
    VOICE = "voice"   # Nghe – Nói
    TOUCH = "touch"   # Nhìn – Chạm


class Risk(str, Enum):
    RED = "red"
    YELLOW = "yellow"
    GREEN = "green"


class FieldState(str, Enum):
    EMPTY = "empty"
    HEARD = "heard"
    CHECKED = "checked"
    CONFIRMED = "confirmed"


class Source(str, Enum):
    VOICE = "voice"
    IMAGE = "image"
    GUARDIAN = "guardian"
    SYSTEM = "system"


class Base(SQLModel):
    created_at: NaiveDatetime = Field(default_factory=datetime.now)
    updated_at: NaiveDatetime = Field(default_factory=datetime.now)


class Seller(Base, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str
    honorific: str = "cô"
    mode: Mode = Mode.VOICE
    tts_speed: float = 0.9
    region: str | None = None
    shipping_days: list[str] = Field(default=[], sa_column=Column(JSON))  # "mon".."sun"
    guardian_required: bool = False
    guardian_name: str | None = None
    low_stock_threshold: int = 3
    shop_name: str | None = None
    avatar: str = "🏪"
    uses_assistant: bool = False              # shop có bật "Bạn Bán Hàng"
    followers: int = 0
    # hồ sơ cửa hàng (điền bằng trò chuyện)
    phone: str | None = None
    address: str | None = None               # địa chỉ lấy hàng (xã/huyện)
    main_products: str | None = None
    intro: str | None = None                 # vài câu giới thiệu shop cho người mua
    onboarded: bool = True                   # False: đang tạo hồ sơ
    theme: dict = Field(default={}, sa_column=Column(JSON))   # {"color", "banner_id"}: giao diện gian hàng


class Listing(Base, table=True):
    id: int | None = Field(default=None, primary_key=True)
    seller_id: int = Field(foreign_key="seller.id")
    category: str
    status: str = "drafting"   # drafting|ready|pending_publish|published|hidden
    pending_until: NaiveDatetime | None = None
    title: str | None = None
    draft_raw: str | None = None            # bản nháp gốc có thẻ, trước khi soát nguồn
    description: str | None = None          # bản có thẻ [key] đã soát
    public_description: str | None = None   # bản đã gỡ thẻ
    stock: int | None = None
    image_ids: list[int] = Field(default=[], sa_column=Column(JSON))
    views_7d: int = 0
    price_checked: bool = False
    acks: list[str] = Field(default=[], sa_column=Column(JSON))  # cảnh báo người bán đã xác nhận bỏ qua
    sold: int = 0
    rating: float = 0
    list_price: int | None = None             # giá gạch (trước giảm), chỉ để hiển thị


class Review(Base, table=True):
    id: int | None = Field(default=None, primary_key=True)
    listing_id: int = Field(index=True)
    buyer_name: str
    stars: int
    text: str


class ListingField(Base, table=True):
    id: int | None = Field(default=None, primary_key=True)
    listing_id: int = Field(foreign_key="listing.id", index=True)
    key: str
    value: str | None = None
    unit: str | None = None
    risk: Risk
    state: FieldState = FieldState.EMPTY
    source: Source | None = None
    confidence: float | None = None
    raw_utterance: str | None = None
    audio_ref: str | None = None
    confirmed_at: NaiveDatetime | None = None
    history: list[str] = Field(default=[], sa_column=Column(JSON))  # các giá trị đã nghe, cho CONTRADICTION


class Image(Base, table=True):
    id: int | None = Field(default=None, primary_key=True)
    owner_type: str        # listing | order_packing | receipt
    owner_id: int
    path: str
    quality: dict = Field(default={}, sa_column=Column(JSON))
    observations: dict = Field(default={}, sa_column=Column(JSON))
    description: str | None = None
    accepted: bool = False


class Order(Base, table=True):
    id: int | None = Field(default=None, primary_key=True)
    seller_id: int = Field(foreign_key="seller.id")
    external_id: str
    status: str = "new"    # new|accepted|packed|shipped|delivered|cancelled|dispute
    buyer_name: str
    buyer_province: str
    seller_payout: int
    ship_by: NaiveDatetime
    tracking_code: str | None = None
    cancel_reason: str | None = None
    packing_check_passed: bool = False
    packing_override: bool = False
    buyer_phone: str | None = None
    buyer_address: str | None = None
    buyer_key: str | None = None              # mã thiết bị người mua (giả lập, không đăng nhập)


class OrderItem(Base, table=True):
    id: int | None = Field(default=None, primary_key=True)
    order_id: int = Field(foreign_key="order.id", index=True)
    listing_id: int = Field(foreign_key="listing.id")
    quantity: int
    variant: str | None = None


class ConfirmationLog(Base, table=True):
    id: int | None = Field(default=None, primary_key=True)
    seller_id: int = Field(index=True)
    subject_type: str
    subject_ref: str
    risk: str = "red"
    prompt_text: str
    response_text: str | None = None
    response_ms: int | None = None
    result: str            # confirmed|rejected|timeout|unclear|corrected
    layer_flags: list[str] = Field(default=[], sa_column=Column(JSON))


class BlockedError(Base, table=True):
    id: int | None = Field(default=None, primary_key=True)
    seller_id: int = Field(index=True)
    layer: int             # 1 nghe, 2 hợp lý, 3 đối chiếu, 4 xác nhận chủ động, 5 cổng chặn
    code: str
    detail: str


class BuyerMessage(Base, table=True):
    id: int | None = Field(default=None, primary_key=True)
    seller_id: int
    listing_id: int | None = None
    order_id: int | None = None
    buyer_name: str
    text: str
    answer: str | None = None
    answer_sources: list[str] = Field(default=[], sa_column=Column(JSON))
    status: str = "new"    # new|answered_auto|waiting_seller|answered_seller|scam_flagged


class FAQ(Base, table=True):
    id: int | None = Field(default=None, primary_key=True)
    listing_id: int
    question: str
    answer: str
    approved_by_seller: bool = False


class GrowthSuggestion(Base, table=True):
    id: int | None = Field(default=None, primary_key=True)
    seller_id: int
    kind: str
    message: str
    evidence: dict = Field(default={}, sa_column=Column(JSON))
    action: dict = Field(default={}, sa_column=Column(JSON))
    status: str = "proposed"   # proposed|accepted|declined|expired


class GuardianApproval(Base, table=True):
    id: int | None = Field(default=None, primary_key=True)
    seller_id: int
    subject_ref: str
    summary: str = ""
    payload: dict = Field(default={}, sa_column=Column(JSON))   # ConfirmationRequest đã được người bán xác nhận
    status: str = "waiting"    # waiting|approved|rejected
