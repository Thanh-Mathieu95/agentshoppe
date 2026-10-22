# Bán Không Rào Cản — Đặc tả dự án (đủ để code)

> Phiên bản 1.0 · 21/10/2026 · Đội SeOpe · Sea x OpenAI Codex Hackathon Vietnam 2026
> Tài liệu đi kèm `ban-khong-rao-can-ke-hoach.md` (kế hoạch, pitch, demo). File này là **đặc tả kỹ thuật**: user story, dữ liệu, API, agent, công cụ, cơ chế xác nhận, quản lý đơn, phát triển bán hàng, kiểm thử, cấu trúc code.

---

## Mục lục
0. Cách dùng tài liệu
1. Phạm vi: MVP hackathon và bản sau
2. User story và tiêu chí chấp nhận
3. Kiến trúc tổng thể
4. Cấu trúc thư mục
5. Mô hình dữ liệu
6. Máy trạng thái
7. Agent: vòng lặp, định tuyến ý định, prompt hệ thống
8. Danh sách công cụ (JSON schema)
9. Bộ máy xác nhận (Confirmation Engine)
10. Chuẩn hóa số tiếng Việt
11. Quản lý đơn hàng bằng giọng nói và chế độ hỗ trợ
12. Phát triển bán hàng
13. Trực shop: trả lời khách
14. Giao diện theo chế độ
15. API backend
16. Shopee giả lập (mock) và bộ sinh đơn
17. Kiểm thử
18. Cài đặt và chạy
19. Phân việc theo file cho 7 tiếng
20. Kịch bản demo (bản có quản lý đơn)

---

## 0. Cách dùng tài liệu

- **Code bằng tiếng Anh, giao tiếp với người dùng bằng tiếng Việt.** Tên biến, bảng và công cụ viết tiếng Anh; mọi câu agent nói viết tiếng Việt, đặt trong `app/i18n/vi.py`.
- **Mức ưu tiên:** mỗi mục có nhãn **[P0]** (bắt buộc cho demo), **[P1]** (làm nếu kịp) hoặc **[P2]** (chỉ nhắc trong pitch).
- **Nguyên tắc vàng:** mọi hành động có hậu quả (đăng tin, đổi giá, nhận đơn, báo đã gửi, hủy đơn, tham gia khuyến mãi, gửi tin cho khách) **phải đi qua Confirmation Engine** và **bị chặn bằng code** nếu chưa đủ xác nhận. LLM không bao giờ tự quyết những hành động này.

---

## 1. Phạm vi

| Khối | MVP hackathon | Bản sau |
|---|---|---|
| Chế độ giao tiếp | Nghe – Nói [P0], Nhìn – Chạm [P1], Có bảo trợ [P1] | Tiếng dân tộc, ngôn ngữ ký hiệu [P2] |
| Đăng hàng | Phỏng vấn, chụp ảnh, kiểm tra hợp lý, định giá, viết tin, đăng chờ [P0]; kiểm tra quy định [P1] | Nhiều biến thể (size, màu) |
| Quản lý đơn | Báo đơn mới, nhận đơn, kiểm tra đóng gói bằng camera, báo đã gửi, hỏi trạng thái [P0]; hủy đơn, gom đơn theo ngày gửi [P1] | Trả hàng, khiếu nại [P2] |
| Phát triển bán hàng | Bản tin cuối ngày [P0]; gợi ý tuần, cảnh báo hết hàng [P1] | Khuyến mãi, combo, hàng theo mùa [P1/P2] |
| Trực shop | Trả lời từ dữ liệu đã xác nhận, hỏi người bán khi không chắc, lưu FAQ [P0] | Cảnh báo lừa đảo [P1] |
| Tích hợp sàn | Shopee giả lập (mock) | Shopee Open Platform thật (cần quyền đối tác) |

---

## 2. User story và tiêu chí chấp nhận

> Định dạng: **ID · Là… · tôi muốn… · để…**, kèm tiêu chí chấp nhận (AC) viết theo Given/When/Then.

### Epic E1 — Bắt đầu và chọn chế độ

**US-1.1 [P0]** · Là người bán khiếm thị, tôi muốn bắt đầu chỉ bằng một nút lớn và giọng nói, để không phải tìm đọc menu.
- AC1: Màn hình đầu có đúng 1 nút chiếm ≥ 50% màn hình, có nhãn cho trình đọc màn hình là "Nhấn để nói".
- AC2: Lần đầu, agent nói lời chào dưới 15 giây và hỏi người bán thích nói chuyện hay bấm nút.

**US-1.2 [P1]** · Là người khiếm thính, tôi muốn chọn chế độ bằng hình, để không phải nghe hay đọc nhiều.
- AC1: Có 3 thẻ hình (tai và miệng / mắt và tay / hai người), mỗi thẻ có chữ dưới 4 từ.
- AC2: Chế độ được chọn lưu vào `Seller.mode` và áp dụng cho mọi phản hồi.

**US-1.3 [P1]** · Là người bán, tôi muốn có người bảo trợ duyệt giúp, để yên tâm khi chưa quen.
- AC1: Khi `Seller.guardian_required = true`, mọi hành động cấp ĐỎ cần thêm `GuardianApproval`.

### Epic E2 — Đăng hàng

**US-2.1 [P0]** · Là người bán, tôi muốn nói tên và giá sản phẩm, để agent tự tạo phiếu.
- AC1: Câu "mật ong rừng ba trăm nghìn một chai" tạo `Listing` với `name` và `price` ở trạng thái `HEARD`.
- AC2: Agent hỏi lần lượt các trường bắt buộc còn thiếu theo `CategoryTemplate`, mỗi lượt một câu.

**US-2.2 [P0]** · Là người khiếm thị, tôi muốn được hướng dẫn chụp ảnh, để ảnh đủ tốt.
- AC1: Ảnh tối, mờ hoặc lệch khung thì agent đưa ra **một** chỉ dẫn hành động cụ thể (hướng, khoảng cách, ánh sáng).
- AC2: Tối đa 3 lần chụp lại. Lần thứ 3 vẫn chưa đạt thì agent đề xuất nhờ người bảo trợ, hoặc dùng ảnh tốt nhất và báo rõ.
- AC3: Ảnh được chấp nhận phải được agent mô tả lại cho người bán xác nhận.

**US-2.3 [P0]** · Là người bán, tôi muốn biết tiền thực nhận, để không bán lỗ.
- AC1: Agent nói giá thị trường (min–max), phí ước tính và tiền thực nhận.
- AC2: Nếu tiền thực nhận ≤ 0, agent cảnh báo và hỏi có muốn đổi giá không.

**US-2.4 [P0]** · Là người bán, tôi muốn nghe lại toàn bộ tin trước khi đăng, để chắc chắn đúng.
- AC1: `publish_listing` trả lỗi `NOT_CONFIRMED` nếu còn trường ĐỎ hoặc VÀNG chưa `CONFIRMED`.
- AC2: Sau khi đăng, tin ở trạng thái `PENDING_PUBLISH` trong 10 phút; nói "rút lại" thì chuyển sang `DRAFT`.

### Epic E3 — Kiểm lỗi và xác nhận

**US-3.1 [P0]** · Là người bán, tôi muốn agent hỏi lại khi nó không chắc đã nghe đúng, để không đăng sai giá.
- AC1: Con số chứa từ trong `CONFUSABLES` luôn được xác nhận với câu nhấn ("ba, không phải bảy").
- AC2: Giá lệch ngoài [1/3, 3] lần giá trung vị thì agent hỏi lại và gợi ý cách hiểu khác (×10, ÷10).

**US-3.2 [P0]** · Là người bán, tôi muốn agent không viết điều tôi không nói, để không bị khách khiếu nại.
- AC1: Mọi câu trong `Listing.description` có ít nhất 1 thẻ `[field]` trỏ tới trường `CONFIRMED`.
- AC2: Các từ trong `BANNED_CLAIMS` bị xóa nếu không có trong lời người bán.

### Epic E4 — Quản lý đơn hàng

**US-4.1 [P0]** · Là người bán, tôi muốn được báo khi có đơn mới, để không bỏ sót đơn.
- AC1: Đơn mới tạo một thông báo theo chế độ (đọc to / thẻ to + rung) trong vòng 5 giây.
- AC2: Thông báo gồm tên sản phẩm, số lượng, tỉnh thành, số tiền người bán nhận, hạn chuẩn bị hàng.

**US-4.2 [P0]** · Là người bán, tôi muốn nhận đơn bằng lời, để không phải bấm.
- AC1: "Nhận đơn" → kiểm tra tồn kho → đọc lại đơn (cấp ĐỎ) → người bán xác nhận → `Order.status = ACCEPTED` và trừ tồn kho.
- AC2: Không đủ hàng thì agent báo và hỏi giao một phần hay từ chối đơn.

**US-4.3 [P0]** · Là người khiếm thị, tôi muốn camera kiểm tra hàng tôi đóng gói đúng đơn chưa, để không gửi nhầm.
- AC1: Người bán chụp hàng trước khi đóng gói; agent so ảnh với `OrderItem` (loại, số lượng, biến thể).
- AC2: Lệch thì agent nói cụ thể ("đơn cần 2 chai, tôi thấy 1 chai") và không cho báo "đã đóng gói".

**US-4.4 [P0]** · Là người bán, tôi muốn hỏi "hôm nay có mấy đơn", để nắm tình hình.
- AC1: Agent trả lời tổng số, số chưa xử lý, đơn gần hạn nhất, trong 1–3 câu.

**US-4.5 [P0]** · Là người bán, tôi muốn báo "đã gửi hàng" bằng lời.
- AC1: Đây là hành động không đảo ngược → xác nhận hai bước + cụm từ cố định "đã gửi rồi".
- AC2: Agent đọc mã vận đơn theo nhóm 4 ký tự để người bán đối chiếu với tờ biên nhận (hoặc chụp biên nhận để agent đọc).

**US-4.6 [P1]** · Là người bán, tôi muốn được gom đơn theo ngày đi bưu cục, để đỡ đi lại.
- AC1: Agent đề xuất ngày gửi dựa trên `Seller.shipping_days` và hạn của từng đơn; đơn nào không kịp thì cảnh báo riêng.

**US-4.7 [P1]** · Là người bán, tôi muốn hủy đơn khi hết hàng, với lý do rõ ràng.
- AC1: Hủy là hành động ĐỎ, cần lý do chọn từ tối đa 3 lựa chọn, kèm cảnh báo hủy nhiều có thể ảnh hưởng shop.

### Epic E5 — Phát triển bán hàng

**US-5.1 [P0]** · Là người bán, tôi muốn nghe bản tin cuối ngày, để biết hôm nay bán thế nào.
- AC1: Bản tin dưới 45 giây: số đơn, tiền nhận, đơn cần gửi mai, câu hỏi khách chưa trả lời, **tối đa 1 gợi ý**.

**US-5.2 [P1]** · Là người bán, tôi muốn được nhắc khi sắp hết hàng.
- AC1: Tồn kho ≤ `low_stock_threshold` → nhắc; người bán có thể nói số lượng mới để cập nhật (cấp ĐỎ).

**US-5.3 [P1]** · Là người bán, tôi muốn nhận gợi ý tăng đơn được giải thích đơn giản, và chỉ áp dụng khi tôi đồng ý.
- AC1: Gợi ý không bao giờ tự áp dụng. Mỗi gợi ý gồm: làm gì, vì sao (1 câu, có số liệu nguồn), ảnh hưởng tiền.

### Epic E6 — Trực shop

**US-6.1 [P0]** · Là người mua, tôi muốn được trả lời nhanh và đúng.
- AC1: Agent chỉ trả lời từ trường `CONFIRMED` hoặc `FAQ` đã duyệt; mỗi câu trả lời lưu `source_refs`.
- AC2: Không có nguồn → trả lời khách "Shop đang kiểm tra, sẽ trả lời sớm", rồi tạo `SellerQuestion`.

**US-6.2 [P0]** · Là người bán, tôi muốn trả lời câu hỏi của khách bằng lời, và câu đó được lưu để lần sau agent tự trả lời.
- AC1: Câu trả lời của người bán được chuẩn hóa thành câu lịch sự, **đọc lại cho người bán duyệt**, rồi mới gửi khách và lưu FAQ.

---

## 3. Kiến trúc tổng thể

```
┌────────────── Frontend (PWA, React + Vite) ──────────────┐
│  VoiceMode   |  TouchMode   |  GuardianView  | DemoBoard │
│  mic, camera, TTS playback, big buttons, vibration       │
└───────────────┬──────────────────────────────────────────┘
                │ REST + WebSocket (/ws/session/{seller_id})
┌───────────────▼────────────── Backend (FastAPI) ─────────┐
│  SessionManager ── per seller: mode, pending confirmation │
│  Speech: STT adapter (OpenAI | FPT.AI) / TTS adapter      │
│  Agent Orchestrator (LLM + tool calling + vision)         │
│     ├─ IntentRouter (listing / order / growth / support)  │
│     ├─ Tools (section 8)                                  │
│     └─ ConfirmationEngine (section 9) ◄── hard gate       │
│  Validators: number normalizer, sanity, source checker    │
│  Services: PricingService, PolicyService, OrderService,   │
│            GrowthService, SupportService, Notifier        │
│  Repository (SQLModel + SQLite)                            │
└───────────────┬──────────────────────────────────────────┘
                │ HTTP
┌───────────────▼──────────────┐
│ Mock Shopee (FastAPI router)  │  listings, orders, buyer chat,
│ + Order simulator             │  fees, market prices (seed JSON)
└──────────────────────────────┘
```

**Công nghệ:**

| Lớp | Lựa chọn | Ghi chú |
|---|---|---|
| Backend | Python 3.11, FastAPI, SQLModel, SQLite, Uvicorn | Một tiến trình duy nhất cho đơn giản |
| LLM | Mô hình OpenAI có tool calling + vision | Tên model đặt trong `.env` (`LLM_MODEL`) |
| Nhận dạng giọng nói (STT) | OpenAI transcription; adapter dự phòng FPT.AI | Lấy độ tin cậy theo từ nếu API trả về; nếu không, dựa vào danh sách từ dễ nhầm |
| Đọc thành giọng (TTS) | OpenAI TTS hoặc FPT.AI (giọng Bắc) | Hỗ trợ tham số tốc độ |
| Frontend | React + Vite + TypeScript, PWA | `MediaRecorder` cho mic, `<input capture>` hoặc `getUserMedia` cho camera, `navigator.vibrate` |
| Kiểm thử | pytest, pytest-asyncio | Bộ kiểm thử chuẩn hóa số bắt buộc |

---

## 4. Cấu trúc thư mục

```
ban-khong-rao-can/
├── backend/
│   ├── app/
│   │   ├── main.py                  # FastAPI app, mount routers, websocket
│   │   ├── config.py                # đọc .env
│   │   ├── db.py                    # engine, session, init_db, seed
│   │   ├── models.py                # SQLModel tables (section 5)
│   │   ├── schemas.py               # Pydantic request/response
│   │   ├── i18n/vi.py               # mọi câu tiếng Việt agent nói
│   │   ├── speech/
│   │   │   ├── stt.py               # transcribe(audio) -> Transcript(words, confidences)
│   │   │   └── tts.py               # synthesize(text, speed) -> audio bytes
│   │   ├── agent/
│   │   │   ├── orchestrator.py      # vòng lặp agent (section 7)
│   │   │   ├── router.py            # phân loại ý định
│   │   │   ├── prompts.py           # system prompt theo chế độ
│   │   │   └── tools.py             # định nghĩa + dispatcher công cụ (section 8)
│   │   ├── confirm/
│   │   │   ├── engine.py            # ConfirmationEngine (section 9)
│   │   │   ├── templates.py         # câu đọc lại theo chế độ
│   │   │   └── confusables.py       # danh sách từ dễ nhầm
│   │   ├── validators/
│   │   │   ├── numbers.py           # chuẩn hóa số tiếng Việt (section 10)
│   │   │   ├── sanity.py            # kiểm tra hợp lý
│   │   │   └── sources.py           # soát nguồn tin đăng, BANNED_CLAIMS
│   │   ├── services/
│   │   │   ├── pricing.py
│   │   │   ├── policy.py
│   │   │   ├── vision.py            # chấm ảnh, đối chiếu, kiểm tra đóng gói
│   │   │   ├── orders.py            # section 11
│   │   │   ├── growth.py            # section 12
│   │   │   ├── support.py           # section 13
│   │   │   └── notifier.py          # đẩy thông báo qua websocket theo chế độ
│   │   └── mock_shopee/
│   │       ├── router.py            # section 16
│   │       └── simulator.py         # sinh đơn và tin nhắn khách
│   ├── data/
│   │   ├── categories.json          # CategoryTemplate
│   │   ├── market_prices.json
│   │   ├── fees.json
│   │   ├── policies.json
│   │   └── demo_seed.json           # người bán, sản phẩm, đơn mẫu
│   ├── tests/
│   │   ├── test_numbers.py
│   │   ├── test_confirm_engine.py
│   │   ├── test_sanity.py
│   │   ├── test_sources.py
│   │   ├── test_orders.py
│   │   └── test_scenarios.py        # kịch bản lỗi E1–E8
│   ├── requirements.txt
│   └── .env.example
└── frontend/
    ├── src/
    │   ├── main.tsx
    │   ├── api.ts                   # REST + WebSocket client
    │   ├── modes/
    │   │   ├── VoiceMode.tsx
    │   │   ├── TouchMode.tsx
    │   │   └── GuardianView.tsx
    │   ├── components/
    │   │   ├── BigMicButton.tsx
    │   │   ├── CameraCapture.tsx
    │   │   ├── ConfirmCard.tsx       # thẻ ĐÚNG/SAI cho chế độ chạm
    │   │   ├── OrderCard.tsx
    │   │   └── MoneyVisual.tsx       # hiển thị số tiền bằng hình tờ tiền
    │   └── demo/
    │       ├── DemoBoard.tsx         # bảng "lỗi đã chặn" + log agent cho màn hình lớn
    │       └── MockShopPage.tsx      # trang shop như người mua thấy
    └── package.json
```

---

## 5. Mô hình dữ liệu

> SQLModel. Mọi bảng có `id: int (PK)`, `created_at`, `updated_at`; không lặp lại ở dưới.

```python
# app/models.py (rút gọn — đủ để code)
from enum import Enum
from sqlmodel import SQLModel, Field, Column, JSON
from datetime import datetime

class Mode(str, Enum):
    VOICE = "voice"          # Nghe – Nói
    TOUCH = "touch"          # Nhìn – Chạm
class Risk(str, Enum):
    RED = "red"; YELLOW = "yellow"; GREEN = "green"
class FieldState(str, Enum):
    EMPTY = "empty"; HEARD = "heard"; CHECKED = "checked"; CONFIRMED = "confirmed"
class Source(str, Enum):
    VOICE = "voice"; IMAGE = "image"; GUARDIAN = "guardian"; SYSTEM = "system"

class Seller(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str
    mode: Mode = Mode.VOICE
    tts_speed: float = 0.9
    region: str | None = None                 # "Hà Giang"
    shipping_days: list[str] = Field(default=[], sa_column=Column(JSON))  # ["thu"] = thứ Năm
    guardian_required: bool = False
    guardian_name: str | None = None
    low_stock_threshold: int = 3

class Listing(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    seller_id: int = Field(foreign_key="seller.id")
    category: str                              # "honey", "tea", "handicraft", "candle", "dried_food"
    status: str = "drafting"                   # drafting|ready|pending_publish|published|hidden
    pending_until: datetime | None = None
    title: str | None = None
    description: str | None = None             # có thẻ [field] nội bộ; bản public đã gỡ thẻ
    stock: int | None = None
    image_ids: list[int] = Field(default=[], sa_column=Column(JSON))

class ListingField(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    listing_id: int = Field(foreign_key="listing.id")
    key: str                                   # "price", "volume_ml", "origin", ...
    value: str | None = None                   # luôn lưu dạng chuỗi chuẩn hóa ("300000", "500")
    unit: str | None = None                    # "VND", "ml", "g"
    risk: Risk
    state: FieldState = FieldState.EMPTY
    source: Source | None = None
    confidence: float | None = None
    raw_utterance: str | None = None           # câu gốc người bán nói
    audio_ref: str | None = None
    confirmed_at: datetime | None = None

class Image(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    owner_type: str                            # "listing" | "order_packing" | "receipt"
    owner_id: int
    path: str
    quality: dict = Field(default={}, sa_column=Column(JSON))   # {"bright":0.8,"sharp":0.9,"framed":true}
    observations: dict = Field(default={}, sa_column=Column(JSON))  # {"volume_ml_est":500,"count":1}
    accepted: bool = False

class Order(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    seller_id: int = Field(foreign_key="seller.id")
    external_id: str                           # mã đơn bên sàn (mock)
    status: str = "new"                        # xem 6.3
    buyer_name: str
    buyer_province: str
    seller_payout: int                         # VND người bán nhận
    ship_by: datetime
    tracking_code: str | None = None
    cancel_reason: str | None = None

class OrderItem(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    order_id: int = Field(foreign_key="order.id")
    listing_id: int = Field(foreign_key="listing.id")
    quantity: int
    variant: str | None = None

class ConfirmationLog(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    seller_id: int
    subject_type: str                          # "listing_field" | "action"
    subject_ref: str                           # "listing:12:price" | "order:5:ship"
    prompt_text: str                           # câu agent đã nói/hiện
    response_text: str | None = None
    response_ms: int | None = None
    result: str                                # "confirmed" | "rejected" | "timeout" | "unclear"
    layer_flags: list[str] = Field(default=[], sa_column=Column(JSON))  # ["confusable","sanity_price"]

class BlockedError(SQLModel, table=True):      # dùng cho DemoBoard và chỉ số
    id: int | None = Field(default=None, primary_key=True)
    seller_id: int
    layer: int                                 # 1..5
    code: str                                  # "CONFUSABLE_NUMBER", "PRICE_OUTLIER", ...
    detail: str

class BuyerMessage(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    seller_id: int
    listing_id: int | None = None
    order_id: int | None = None
    buyer_name: str
    text: str
    answer: str | None = None
    answer_sources: list[str] = Field(default=[], sa_column=Column(JSON))
    status: str = "new"                        # new|answered_auto|waiting_seller|answered_seller

class FAQ(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    listing_id: int
    question: str
    answer: str
    approved_by_seller: bool = False

class GrowthSuggestion(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    seller_id: int
    kind: str                                  # xem 12.2
    message: str                               # câu nói đơn giản
    evidence: dict = Field(default={}, sa_column=Column(JSON))
    action: dict = Field(default={}, sa_column=Column(JSON))   # payload hành động nếu đồng ý
    status: str = "proposed"                   # proposed|accepted|declined|expired

class GuardianApproval(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    seller_id: int
    subject_ref: str
    status: str = "waiting"                    # waiting|approved|rejected
```

**`data/categories.json` (mẫu):**

```json
{
  "honey": {
    "label": "Mật ong",
    "fields": [
      {"key": "name",        "risk": "red",    "ask": "Sản phẩm của cô tên là gì ạ?"},
      {"key": "price",       "risk": "red",    "ask": "Mỗi chai cô bán bao nhiêu tiền?", "unit": "VND"},
      {"key": "volume_ml",   "risk": "red",    "ask": "Mỗi chai bao nhiêu? Nửa lít hay một lít?", "unit": "ml"},
      {"key": "stock",       "risk": "red",    "ask": "Cô đang có bao nhiêu chai?"},
      {"key": "origin",      "risk": "yellow", "ask": "Mật ong lấy ở đâu ạ?"},
      {"key": "container",   "risk": "yellow", "ask": "Đựng chai nhựa hay chai thủy tinh?"},
      {"key": "harvest_time","risk": "yellow", "ask": "Mật ong lấy vào tháng nào?"},
      {"key": "storage",     "risk": "green",  "ask": "Bảo quản thế nào ạ?"}
    ],
    "fragile_liquid": true,
    "price_unit_hint": "per_container"
  }
}
```

---

## 6. Máy trạng thái

### 6.1. Trường thông tin (`ListingField.state`)

```
EMPTY ──set──► HEARD ──validators pass──► CHECKED ──seller confirms──► CONFIRMED
                 ▲            │ fail → hỏi lại (giữ HEARD)                │
                 └──────────── any edit ◄──────────────────────────────────┘
```
- Chuyển `CHECKED → CONFIRMED` **chỉ** do `ConfirmationEngine.resolve()` gọi. Không tool nào khác được làm việc này.
- Trường `GREEN` có thể chuyển thẳng sang `CONFIRMED` khi người bán duyệt bản tóm tắt cuối.

### 6.2. Tin đăng (`Listing.status`)

```
drafting ──all RED/YELLOW confirmed + checks pass──► ready
ready ──"đăng đi" (2 bước) [+ guardian]──► pending_publish (10 phút)
pending_publish ──"rút lại"──► drafting
pending_publish ──hết 10 phút──► published
published ──"ẩn"/hết hàng/hết mùa (xác nhận)──► hidden ──"đăng lại"──► published
```

### 6.3. Đơn hàng (`Order.status`)

```
new ──"nhận đơn" (RED)──► accepted ──packing check pass──► packed
new ──"hủy" + lý do (RED)──► cancelled
accepted ──"hủy" + lý do (RED)──► cancelled
packed ──"đã gửi rồi" (2 bước) + tracking──► shipped ──(mock)──► delivered
shipped/delivered ──(mock) khiếu nại──► dispute   [P2]
```
**Quy tắc:**
- Không chuyển sang `packed` nếu `packing_check` chưa đạt, trừ khi người bán chọn "bỏ qua kiểm tra" (vẫn phải xác nhận ĐỎ và được ghi log).
- `ship_by` còn dưới 24 giờ mà chưa `packed` → `Notifier` cảnh báo.

---

## 7. Agent

### 7.1. Vòng lặp xử lý một lượt

```python
# app/agent/orchestrator.py (khung)
async def handle_turn(seller: Seller, user_input: UserInput) -> list[OutputEvent]:
    # 1. Đầu vào: giọng nói -> STT (giữ độ tin cậy từng từ); chạm -> sự kiện nút; ảnh -> image_id
    transcript = await stt.transcribe(user_input.audio) if user_input.audio else None

    # 2. Nếu đang chờ xác nhận, xử lý ở đây và KHÔNG gọi LLM
    if session.pending_confirmation:
        result = confirm_engine.resolve(session.pending_confirmation, transcript, user_input.button)
        events = confirm_engine.render_followup(result, seller.mode)
        if result.needs_llm_followup is False:
            return events

    # 3. Gọi LLM với: system prompt theo chế độ + trạng thái rút gọn + lịch sử ngắn + tools
    state_summary = build_state_summary(seller)  # phiếu đang làm, đơn đang mở, câu hỏi chờ
    messages = prompts.build(seller.mode, state_summary, session.history[-12:], transcript)

    for _ in range(MAX_TOOL_STEPS):  # 6
        resp = await llm.chat(messages, tools=tools.SCHEMAS)
        if not resp.tool_calls:
            break
        for call in resp.tool_calls:
            out = await tools.dispatch(call.name, call.args, seller)   # validators & gates bên trong
            messages.append(tool_result(call, out))
            if out.get("requires_confirmation"):
                session.pending_confirmation = out["confirmation"]
                return confirm_engine.render_prompt(out["confirmation"], seller.mode)

    # 4. Lời đáp cuối của LLM -> kiểm tra độ dài, ngôn ngữ đơn giản -> TTS hoặc thẻ chạm
    return render_reply(resp.text, seller.mode)
```

**Điểm chốt:**
- **Khi đang chờ xác nhận, LLM không được tham gia.** Câu trả lời "đúng/sai" được phân tích bằng code (xem 9.5) để LLM không thể "tự xác nhận hộ".
- Mỗi lượt chỉ có **một câu hỏi** gửi tới người bán. Nếu LLM sinh nhiều câu hỏi, `render_reply` chỉ giữ câu đầu và đẩy phần còn lại vào hàng đợi.

### 7.2. Định tuyến ý định

| Ý định | Ví dụ lời nói | Nhánh |
|---|---|---|
| `create_listing` | "Cô muốn bán mật ong" | Đăng hàng |
| `edit_listing` | "Đổi giá mật ong thành 280" | Đăng hàng (trường về HEARD) |
| `order_query` | "Hôm nay có đơn nào không?" | Đơn hàng |
| `order_action` | "Nhận đơn", "đã gửi rồi", "hủy đơn này" | Đơn hàng |
| `stock_update` | "Còn 5 chai thôi" | Đơn hàng / tồn kho |
| `buyer_reply` | "Bảo khách là không pha đường" | Trực shop |
| `growth_query` | "Làm sao bán được nhiều hơn?" | Phát triển |
| `help` | "Nói lại", "chậm thôi", "không hiểu" | Điều khiển hội thoại |
| `undo` | "Rút lại", "thôi không đăng nữa" | Hoàn tác |

Bộ định tuyến **[P0]**: dùng chính LLM với danh sách công cụ, cộng một bộ từ khóa cứng cho các lệnh điều khiển (`nói lại`, `chậm thôi`, `dừng`, `rút lại`, `đúng`, `sai`). Từ khóa cứng được xử lý **trước** LLM.

### 7.3. Prompt hệ thống

```text
Bạn là "Bạn Bán Hàng", trợ lý giúp người chưa quen công nghệ tự bán hàng trên Shopee.
Người bán có thể là người vùng cao (tiếng Việt là ngôn ngữ thứ hai) hoặc người khuyết tật.
Chế độ hiện tại: {mode_description}
Tên người bán: {seller_name}. Cách xưng hô: {honorific} (ví dụ "cô", "anh").

CÁCH NÓI
- Mỗi lượt tối đa 2 câu, mỗi câu dưới 15 từ, từ thông dụng.
- Chỉ hỏi MỘT câu mỗi lượt.
- Không dùng từ chuyên môn: nói "tiền Shopee giữ lại" thay vì "phí sàn",
  "mã gửi hàng" thay vì "mã vận đơn".
- Tiền: luôn để công cụ xác nhận đọc. Không tự đọc số tiền quan trọng.

QUY TẮC KHÔNG ĐƯỢC VI PHẠM
1. Chỉ ghi vào phiếu điều người bán nói hoặc điều thấy rõ trong ảnh.
   Dùng set_field với source tương ứng. Không đoán.
2. Khi công cụ trả về "warnings", hãy hỏi lại người bán về cảnh báo đầu tiên.
   Không tự sửa giá trị.
3. Không bao giờ tự nói "đã đăng", "đã nhận đơn", "đã gửi" khi công cụ chưa trả về ok=true.
4. Khi viết mô tả, mỗi câu phải có thẻ [key] của trường đã xác nhận. Không viết
   "nguyên chất", "tốt nhất", "chữa bệnh", "100%" trừ khi người bán nói đúng như vậy.
5. Khi trả lời khách mà không có thông tin đã xác nhận, gọi ask_seller. Không đoán.
6. Gợi ý phát triển bán hàng chỉ đưa tối đa 1 gợi ý mỗi lần, và không bao giờ tự áp dụng.
7. Nếu người bán có vẻ chưa hiểu, nói lại đơn giản hơn. Không chuyển bước.

TRẠNG THÁI HIỆN TẠI
{state_summary}
```

`mode_description`:
- VOICE: "Người bán dùng giọng nói và có thể không nhìn được màn hình. Mọi điều quan trọng phải nói ra. Khi mô tả ảnh, nói về vị trí, màu, ánh sáng."
- TOUCH: "Người bán không nghe được. Phản hồi sẽ hiện thành thẻ chữ to. Viết câu dưới 8 từ, dùng từ cụ thể, tránh thành ngữ."

---

## 8. Danh sách công cụ

> Định dạng function calling. Mọi công cụ trả về `{"ok": bool, "warnings": [...], "requires_confirmation": bool, "confirmation": {...}?, "data": {...}}`.

```json
[
  {"type":"function","function":{
    "name":"start_listing",
    "description":"Bắt đầu phiếu sản phẩm mới theo ngành hàng. Trả về danh sách trường cần hỏi.",
    "parameters":{"type":"object","properties":{
      "category":{"type":"string","enum":["honey","tea","handicraft","candle","dried_food"]}},
      "required":["category"]}}},

  {"type":"function","function":{
    "name":"set_field",
    "description":"Ghi một giá trị vào phiếu (trạng thái HEARD). Validators tự chạy. Nếu trường RED/YELLOW, công cụ trả requires_confirmation.",
    "parameters":{"type":"object","properties":{
      "listing_id":{"type":"integer"},
      "key":{"type":"string"},
      "raw_text":{"type":"string","description":"Nguyên văn đoạn người bán nói chứa giá trị"},
      "source":{"type":"string","enum":["voice","image","guardian"]}},
      "required":["listing_id","key","raw_text","source"]}}},

  {"type":"function","function":{
    "name":"next_missing_field",
    "description":"Trả về trường bắt buộc tiếp theo chưa có và câu hỏi gợi ý.",
    "parameters":{"type":"object","properties":{"listing_id":{"type":"integer"}},"required":["listing_id"]}}},

  {"type":"function","function":{
    "name":"assess_photo",
    "description":"Chấm chất lượng ảnh, sinh MỘT chỉ dẫn sửa cụ thể, và quan sát thuộc tính để đối chiếu (dung tích, số lượng, màu).",
    "parameters":{"type":"object","properties":{
      "image_id":{"type":"integer"},
      "purpose":{"type":"string","enum":["listing","packing_check","receipt"]},
      "expect":{"type":"object","description":"Thuộc tính mong đợi để đối chiếu, ví dụ {\"volume_ml\":1000,\"count\":2}"}},
      "required":["image_id","purpose"]}}},

  {"type":"function","function":{
    "name":"price_check",
    "description":"Tra giá thị trường, tính phí và tiền thực nhận.",
    "parameters":{"type":"object","properties":{"listing_id":{"type":"integer"}},"required":["listing_id"]}}},

  {"type":"function","function":{
    "name":"policy_check",
    "description":"Kiểm tra quy định ngành hàng và câu quảng cáo dễ vi phạm.",
    "parameters":{"type":"object","properties":{"listing_id":{"type":"integer"}},"required":["listing_id"]}}},

  {"type":"function","function":{
    "name":"draft_listing_text",
    "description":"Lưu bản nháp tiêu đề và mô tả do LLM viết, CÓ thẻ [key]. Công cụ soát nguồn và trả lại bản đã làm sạch.",
    "parameters":{"type":"object","properties":{
      "listing_id":{"type":"integer"},
      "title":{"type":"string"},
      "description_tagged":{"type":"string"}},
      "required":["listing_id","title","description_tagged"]}}},

  {"type":"function","function":{
    "name":"request_publish",
    "description":"Yêu cầu đăng tin. Code kiểm tra đủ điều kiện; nếu đủ, trả requires_confirmation với bản tóm tắt để xác nhận 2 bước.",
    "parameters":{"type":"object","properties":{"listing_id":{"type":"integer"}},"required":["listing_id"]}}},

  {"type":"function","function":{
    "name":"undo_last_action",
    "description":"Hoàn tác hành động gần nhất còn trong thời gian cho phép (rút lại tin đang chờ).",
    "parameters":{"type":"object","properties":{}}}},

  {"type":"function","function":{
    "name":"list_orders",
    "description":"Tóm tắt đơn theo bộ lọc. Trả số liệu để agent nói ngắn gọn.",
    "parameters":{"type":"object","properties":{
      "filter":{"type":"string","enum":["today","new","to_pack","to_ship","due_soon","all_open"]}},
      "required":["filter"]}}},

  {"type":"function","function":{
    "name":"get_order",
    "description":"Lấy chi tiết một đơn theo mã, tên người mua hoặc 'đơn mới nhất'.",
    "parameters":{"type":"object","properties":{
      "selector":{"type":"string","description":"'latest' | mã đơn | tên người mua | tỉnh"}},
      "required":["selector"]}}},

  {"type":"function","function":{
    "name":"request_order_action",
    "description":"Yêu cầu thao tác trên đơn. Luôn trả requires_confirmation. Code kiểm tra điều kiện (tồn kho, kiểm tra đóng gói).",
    "parameters":{"type":"object","properties":{
      "order_id":{"type":"integer"},
      "action":{"type":"string","enum":["accept","cancel","mark_packed","mark_shipped"]},
      "reason":{"type":"string"},
      "tracking_code":{"type":"string"}},
      "required":["order_id","action"]}}},

  {"type":"function","function":{
    "name":"packing_check",
    "description":"So ảnh hàng chuẩn bị gửi với đơn (loại, số lượng). Trả pass/fail và mô tả chênh lệch.",
    "parameters":{"type":"object","properties":{
      "order_id":{"type":"integer"},"image_id":{"type":"integer"}},
      "required":["order_id","image_id"]}}},

  {"type":"function","function":{
    "name":"plan_shipping_trip",
    "description":"Gom đơn theo ngày đi bưu cục của người bán và hạn từng đơn.",
    "parameters":{"type":"object","properties":{}}}},

  {"type":"function","function":{
    "name":"update_stock",
    "description":"Cập nhật tồn kho (RED, cần xác nhận).",
    "parameters":{"type":"object","properties":{
      "listing_id":{"type":"integer"},"raw_text":{"type":"string"}},
      "required":["listing_id","raw_text"]}}},

  {"type":"function","function":{
    "name":"daily_briefing",
    "description":"Tạo bản tin cuối ngày (số liệu + tối đa 1 gợi ý).",
    "parameters":{"type":"object","properties":{}}}},

  {"type":"function","function":{
    "name":"get_growth_suggestion",
    "description":"Lấy 1 gợi ý phát triển phù hợp nhất hiện tại, kèm bằng chứng số liệu.",
    "parameters":{"type":"object","properties":{}}}},

  {"type":"function","function":{
    "name":"respond_growth_suggestion",
    "description":"Người bán đồng ý/từ chối gợi ý. Đồng ý → requires_confirmation trước khi áp dụng.",
    "parameters":{"type":"object","properties":{
      "suggestion_id":{"type":"integer"},"decision":{"type":"string","enum":["accept","decline","later"]}},
      "required":["suggestion_id","decision"]}}},

  {"type":"function","function":{
    "name":"answer_buyer",
    "description":"Trả lời khách CHỈ từ trường CONFIRMED/FAQ đã duyệt. Phải liệt kê source_refs. Nếu thiếu nguồn, công cụ từ chối.",
    "parameters":{"type":"object","properties":{
      "message_id":{"type":"integer"},"answer":{"type":"string"},
      "source_refs":{"type":"array","items":{"type":"string"}}},
      "required":["message_id","answer","source_refs"]}}},

  {"type":"function","function":{
    "name":"ask_seller",
    "description":"Chuyển câu hỏi của khách cho người bán theo chế độ của họ; gửi khách câu chờ lịch sự.",
    "parameters":{"type":"object","properties":{"message_id":{"type":"integer"}},"required":["message_id"]}}},

  {"type":"function","function":{
    "name":"seller_answer",
    "description":"Ghi câu trả lời của người bán, chuẩn hóa lịch sự, yêu cầu xác nhận trước khi gửi khách và lưu FAQ.",
    "parameters":{"type":"object","properties":{
      "message_id":{"type":"integer"},"raw_text":{"type":"string"}},
      "required":["message_id","raw_text"]}}},

  {"type":"function","function":{
    "name":"set_preferences",
    "description":"Đổi chế độ, tốc độ đọc, ngày đi bưu cục. Đổi chế độ cần xác nhận.",
    "parameters":{"type":"object","properties":{
      "mode":{"type":"string","enum":["voice","touch"]},
      "tts_speed":{"type":"number"},
      "shipping_days":{"type":"array","items":{"type":"string"}}}}}}
]
```

---

## 9. Bộ máy xác nhận (Confirmation Engine)

### 9.1. Cấu trúc một yêu cầu xác nhận

```python
@dataclass
class ConfirmationRequest:
    id: str
    seller_id: int
    subject_ref: str                 # "listing:12:price" | "order:5:accept" | "listing:12:publish"
    kind: Literal["field", "action"]
    risk: Risk
    value_display: dict              # {"number":300000,"unit":"VND"} hoặc {"summary":[...]}
    flags: list[str]                 # ["confusable:ba/bảy", "sanity:price_low", "image_mismatch"]
    two_step: bool                   # True cho hành động không đảo ngược
    action_phrase: str | None        # "đăng đi" | "đã gửi rồi" | "nhận đơn" | "hủy đơn"
    attempts: int = 0
    asked_at: datetime = ...
```

### 9.2. Bảng mức độ và cách xác nhận

| Đối tượng | Mức | Hai bước | Cụm từ hành động |
|---|---|---|---|
| Trường `name`, `price`, `volume_ml`, `stock` | RED | Không | "đúng" |
| Trường `origin`, `container`, `harvest_time` | YELLOW | Không | "đúng" |
| Đăng tin | RED | **Có** | "đăng đi" |
| Đổi giá tin đang bán | RED | **Có** | "đổi giá" |
| Nhận đơn | RED | Không | "nhận đơn" |
| Báo đã gửi | RED | **Có** | "đã gửi rồi" |
| Hủy đơn | RED | **Có** | "hủy đơn" |
| Gửi câu trả lời người bán cho khách | YELLOW | Không | "gửi đi" |
| Áp dụng gợi ý phát triển | RED nếu đổi giá/khuyến mãi, ngược lại YELLOW | Theo mức | "làm đi" |
| Đổi chế độ | YELLOW | Không | "đổi" |

**Chế độ chạm:** cụm từ hành động được thay bằng **giữ nút ĐÚNG trong 1,5 giây**, có thanh tiến trình và rung khi xong. Cách này tránh chạm nhầm.

### 9.3. Sinh câu đọc lại (`templates.py`)

```python
def money_spoken(v: int) -> str:
    # 300000 -> "ba trăm nghìn đồng"
    ...

def money_as_notes(v: int) -> str:
    # Tách theo mệnh giá 500k, 200k, 100k, 50k, 20k, 10k
    # 300000 -> "ba tờ một trăm nghìn"; 150000 -> "một tờ một trăm nghìn và một tờ năm mươi nghìn"
    ...

def volume_spoken(ml: int) -> str:
    # 500 -> "nửa lít"; 1000 -> "một lít"; 250 -> "hai trăm năm mươi mi-li-lít"
    ...

def emphasize_confusable(word: str) -> str:
    # "bảy" -> "BẢY — bảy, không phải ba"
    ...

FIELD_READBACK_VOICE = {
  "price":     "{name}: giá {money}. Tức là {notes}. {emphasis}Đúng thì {honorific} nói 'đúng'.",
  "volume_ml": "Mỗi {container} là {volume}. Đúng không {honorific}?",
  "stock":     "{honorific} đang có {stock} {container}. Đúng không ạ?",
  "name":      "Tên sản phẩm là: {name}. Đúng không ạ?",
}
FIELD_READBACK_TOUCH = {
  "price":     {"big": "{money_digits} đ", "visual": "notes", "text": "Giá mỗi {container}"},
  "volume_ml": {"big": "{volume_short}", "visual": "container_icon", "text": "Mỗi {container}"},
}
```

- **Giọng nói:** tốc độ TTS = `seller.tts_speed`. Riêng câu xác nhận ĐỎ đọc chậm hơn 10% và có ngắt nghỉ trước con số.
- **Chạm:** số hiển thị cỡ ≥ 48px, có hình tờ tiền (`MoneyVisual`) và hai nút ĐÚNG/SAI chiếm nửa dưới màn hình.

### 9.4. Danh sách từ dễ nhầm (`confusables.py`)

```python
CONFUSABLE_GROUPS = [
    {"ba", "bảy"},
    {"năm", "lăm", "lăng"},
    {"mười", "mươi"},
    {"một", "mốt"},
    {"tư", "từ", "bốn"},
    {"trăm", "chăm", "tram"},
    {"nghìn", "nghìn", "ngàn"},
    {"triệu", "chiệu"},
    {"lít", "lạng"},
    {"cân", "cặp"},
    {"chai", "hai"},
    {"sáu", "sau"},
]
# Từ nào trong câu chứa giá trị số/đơn vị mà thuộc nhóm trên -> flag "confusable:<word>"
```

### 9.5. Phân tích câu trả lời xác nhận (bằng code, không dùng LLM)

```python
YES = {"đúng", "đúng rồi", "phải", "chuẩn", "ừ đúng", "vâng đúng", "đúng ạ"}
NO  = {"sai", "không", "không phải", "sai rồi", "chưa đúng", "nhầm"}
WEAK_YES = {"ừ", "ờ", "vâng", "ok", "ừm", "dạ"}       # không đủ cho RED lần đầu
CONTROL = {"nói lại": "repeat", "chậm thôi": "slower", "dừng": "stop"}

def resolve(req: ConfirmationRequest, transcript, button) -> Resolution:
    if button == "yes_hold":  return confirmed(req)
    if button == "no":        return rejected(req)
    text = normalize(transcript.text)

    if text in CONTROL:       return control(CONTROL[text])
    if any(p in text for p in NO):   return rejected(req)        # -> hỏi "sai chỗ nào?"

    # 1. Chứa số mới? -> người bán đang sửa giá trị
    new_value = numbers.parse(text, context=req.subject_ref)
    if new_value and new_value != req.value_display.get("number"):
        return corrected(req, new_value)                     # trường về HEARD, chạy lại validators

    # 2. Hai bước: phải đúng cụm từ hành động
    if req.two_step:
        if req.action_phrase in text: return confirmed(req)
        return clarify(req, "say_action_phrase")             # "Muốn đăng thì nói 'đăng đi' ạ."

    # 3. RED: "ừ" yếu lần đầu -> hỏi lại rõ hơn
    if req.risk == Risk.RED and text in WEAK_YES and req.attempts == 0:
        return clarify(req, "explicit_yes")                  # "Cô nói 'đúng' giúp tôi nhé."

    if any(p in text for p in YES) or (text in WEAK_YES and req.risk != Risk.RED):
        return confirmed(req)

    return clarify(req, "unclear")
```

**Chống gật đầu theo quán tính:**

```python
def rubber_stamp_suspected(seller_id) -> bool:
    last = recent_confirmations(seller_id, n=3)
    return (len(last) == 3
            and all(c.result == "confirmed" and c.risk == "red" for c in last)
            and all(c.response_ms < 2000 for c in last))

# Nếu True: trước khi chấp nhận xác nhận RED tiếp theo, chèn câu hỏi mở:
#   "Cô nhắc lại giúp tôi, mỗi chai cô bán bao nhiêu tiền?"
# So câu trả lời với giá trị đã xác nhận; lệch -> trường về HEARD và ghi BlockedError(layer=4, code="RUBBER_STAMP").
```

**Hết giờ:**
- 30 giây không có phản hồi → hỏi lại 1 lần.
- Thêm 30 giây vẫn không có → `result="timeout"`, lưu nháp, nói "Khi nào {honorific} sẵn sàng thì nhấn nút nói tiếp nhé". **Không bao giờ coi im lặng là đồng ý.**

**Khi người bán nói "sai":**
- Nếu đang xác nhận một trường, hỏi "{honorific} nói lại {tên trường} giúp tôi".
- Nếu đang xác nhận bản tóm tắt nhiều trường, hỏi "Sai chỗ nào ạ: tên, giá, hay số lượng?". Đưa tối đa 3 lựa chọn, là các trường ĐỎ theo thứ tự quan trọng. Ở chế độ chạm, hiện 3 thẻ để chọn.

### 9.6. Cổng chặn bằng code

```python
def can_publish(listing) -> GateResult:
    errors = []
    for f in listing.fields:
        if f.risk in (Risk.RED, Risk.YELLOW) and f.state != FieldState.CONFIRMED:
            errors.append(("NOT_CONFIRMED", f.key))
    errors += sanity.check_listing(listing)                 # lớp 2
    errors += vision.cross_check(listing)                   # lớp 3: ảnh so với trường
    errors += sources.check(listing.description)            # lớp 3: soát nguồn
    if not any(img.accepted for img in listing.images):
        errors.append(("NO_ACCEPTED_PHOTO", None))
    if listing.seller.guardian_required and not guardian_approved(listing):
        errors.append(("WAITING_GUARDIAN", None))
    for e in errors: log_blocked(listing.seller_id, e)
    return GateResult(ok=not errors, errors=errors)

def can_order_action(order, action) -> GateResult:
    if action == "accept"        and not stock_enough(order): return fail("OUT_OF_STOCK")
    if action == "mark_packed"   and not order.packing_check_passed and not order.packing_override:
        return fail("PACKING_NOT_VERIFIED")
    if action == "mark_shipped"  and order.status != "packed": return fail("NOT_PACKED")
    if action == "mark_shipped"  and not order.tracking_code:  return fail("NO_TRACKING")
    return ok()
```

### 9.7. Kiểm tra hợp lý (`sanity.py`)

| Mã | Điều kiện | Câu hỏi lại |
|---|---|---|
| `PRICE_OUTLIER_LOW` | price < median/3 | "Giá này thấp hơn nhiều so với hàng cùng loại ({min}–{max}). {honorific} bán {price}, hay ý {honorific} là {price×10}?" |
| `PRICE_OUTLIER_HIGH` | price > median×3 | Tương tự, gợi ý ÷10 |
| `NEGATIVE_PAYOUT` | payout ≤ 0 | "Bán giá này {honorific} lỗ khoảng {loss}. Có muốn đổi giá không?" |
| `UNIT_MISMATCH` | đơn vị không có trong `allowed_units` của ngành | Hỏi lại đơn vị |
| `STOCK_OUTLIER` | stock > 1000 | "{honorific} có {stock} hay {stock/10}?" |
| `CONTRADICTION` | cùng trường có 2 giá trị khác nhau trong 10 lượt gần nhất | "Lúc nãy {honorific} nói {a}, giờ nói {b}. Cái nào đúng ạ?" |
| `IMAGE_MISMATCH` | |quan sát ảnh − giá trị| vượt ngưỡng (dung tích ±30%, số lượng ≠) | "Trong ảnh tôi thấy {obs}, nhưng {honorific} nói {val}. {honorific} kiểm tra giúp tôi." |

### 9.8. Soát nguồn tin đăng (`sources.py`)

```python
BANNED_CLAIMS = ["nguyên chất", "100%", "chữa", "trị bệnh", "tốt nhất", "số 1", "cam kết", "thần dược"]
TAG = re.compile(r"\[([a-z_]+)\]")

def check(description_tagged: str, listing) -> list[Error]:
    errors = []
    for sentence in split_sentences(description_tagged):
        keys = TAG.findall(sentence)
        if not keys:
            errors.append(("UNSOURCED_SENTENCE", sentence))
            continue
        for k in keys:
            f = listing.field(k)
            if not f or f.state != FieldState.CONFIRMED:
                errors.append(("SOURCE_NOT_CONFIRMED", k))
        for claim in BANNED_CLAIMS:
            if claim in sentence.lower() and not seller_said(listing, claim):
                errors.append(("BANNED_CLAIM", claim))
    return errors

def clean(description_tagged) -> str:
    # bỏ câu lỗi, gỡ thẻ [key] để tạo bản công khai
    ...
```

---

## 10. Chuẩn hóa số tiếng Việt (`validators/numbers.py`)

**Giao diện:**

```python
@dataclass
class ParsedNumber:
    value: float
    unit: str | None          # "VND" | "ml" | "g" | "item"
    raw: str
    confusable_words: list[str]
    assumed_unit: bool        # True nếu đơn vị suy từ ngữ cảnh (ví dụ "ba trăm" trong ngữ cảnh giá -> nghìn)

def parse(text: str, context: str | None = None) -> ParsedNumber | None
```

**Quy tắc:**
- Đơn vị số: không, một/mốt, hai, ba, bốn/tư, năm/lăm, sáu, bảy, tám, chín, mười/mươi.
- Bậc: trăm, nghìn/ngàn/k, triệu/củ, "chục" (= 10).
- "rưỡi": nửa của bậc ngay trước. "ba trăm rưỡi" = 350; "một triệu rưỡi" = 1.500.000; "hai lít rưỡi" = 2,5 lít.
- "linh"/"lẻ": "một trăm linh năm" = 105.
- Viết tắt sau bậc: "một triệu hai" = 1.200.000; "hai trăm mốt" = 210; "ba nghìn tư" = 3.400.
- **Ngữ cảnh giá:** nếu kết quả < 10.000 và không có từ "đồng" hay bậc "nghìn" → hiểu là nghìn, đặt `assumed_unit=True`. Khi `assumed_unit` là True thì **luôn** xác nhận và nói rõ "ba trăm **nghìn** đồng".
- Đơn vị dung tích: "lít" ×1000 ml, "nửa lít" = 500, "xị" (dân gian) → `assumed_unit=True` và hỏi lại.
- Chữ số viết sẵn ("300k", "300.000", "300,000") đều phải parse được.

**Bộ kiểm thử bắt buộc (`tests/test_numbers.py`):**

| Đầu vào | Ngữ cảnh | Kết quả mong đợi |
|---|---|---|
| "ba trăm nghìn" | price | 300000 VND |
| "ba trăm" | price | 300000 VND, assumed_unit |
| "bảy trăm rưỡi" | price | 750000 VND, confusable["bảy"] |
| "một trăm rưỡi" | price | 150000 VND |
| "một triệu hai" | price | 1200000 VND |
| "hai trăm mốt" | price | 210000 VND, confusable["mốt"] |
| "ba mươi lăm nghìn" | price | 35000 VND, confusable["lăm"] |
| "300k" | price | 300000 VND |
| "một trăm linh năm" | stock | 105 item |
| "hai lít rưỡi" | volume | 2500 ml |
| "nửa lít" | volume | 500 ml |
| "năm chục chai" | stock | 50 item |
| "hai củ" | price | 2000000 VND |
| "bốn mươi tư" | stock | 44 |
| "không có" | price | None |

---

## 11. Quản lý đơn hàng bằng giọng nói và chế độ hỗ trợ

### 11.1. Danh mục lệnh

| Lời nói mẫu (giọng nói) | Thao tác chạm tương ứng | Công cụ | Mức xác nhận |
|---|---|---|---|
| "Hôm nay có đơn nào không?" | Thẻ "Đơn hôm nay" | `list_orders(today)` | Không |
| "Đơn nào sắp trễ?" | Thẻ đỏ "Gần hạn" | `list_orders(due_soon)` | Không |
| "Đọc đơn mới nhất" | Chạm vào thẻ đơn | `get_order(latest)` | Không |
| "Đơn của chị Lan ở Hà Nội" | Tìm theo ảnh sản phẩm | `get_order("Lan")` | Không |
| "Nhận đơn" | Giữ nút NHẬN | `request_order_action(accept)` | RED |
| "Kiểm tra hàng giúp tôi" | Nút camera trên thẻ đơn | `packing_check` | Không (chỉ kiểm tra) |
| "Đóng gói xong rồi" | Giữ nút ĐÃ ĐÓNG GÓI | `request_order_action(mark_packed)` | RED (cần packing_check đạt) |
| "Đã gửi rồi" + chụp biên nhận | Giữ nút ĐÃ GỬI + chụp biên nhận | `assess_photo(receipt)` → `request_order_action(mark_shipped)` | RED, 2 bước |
| "Hủy đơn này, hết hàng rồi" | Nút HỦY → chọn 1 trong 3 lý do bằng hình | `request_order_action(cancel)` | RED, 2 bước |
| "Thứ Năm này đi bưu cục được không?" | Thẻ "Lịch gửi" | `plan_shipping_trip` | Không |
| "Còn năm chai thôi" | Bàn phím số cỡ lớn | `update_stock` | RED |
| "Tháng này được bao nhiêu tiền?" | Thẻ "Tiền về" | `list_orders` + tổng payout | Không |

### 11.2. Luồng đơn mới (giọng nói)

```
[Mock tạo đơn] → OrderService.ingest() → Notifier.push(seller, "new_order")
Agent: "Có đơn mới. Chị Lan ở Hà Nội đặt hai chai mật ong nửa lít.
        Cô nhận về hai trăm bảy mươi nghìn. Phải gửi trước thứ Sáu.
        Cô muốn nhận đơn thì nói 'nhận đơn'."
Người bán: "Nhận đơn."
  → can_order_action(accept): tồn kho 8 ≥ 2 ✓
  → ConfirmationRequest(RED, action_phrase="nhận đơn") — người bán đã nói đúng cụm từ trong câu,
    engine chấp nhận ngay vì câu nhắc vừa rồi đã đọc đủ chi tiết đơn
  → Order.status = accepted, stock = 6
Agent: "Đã nhận đơn. Khi chuẩn bị hàng xong, cô chụp hàng để tôi kiểm tra nhé."
```

> **Lưu ý cài đặt:** chỉ chấp nhận "nhận đơn" là xác nhận nếu câu nhắc **ngay trước đó** đã đọc đủ sản phẩm, số lượng, số tiền. Nếu người bán nói "nhận đơn" khi chưa nghe chi tiết, engine đọc chi tiết trước rồi mới hỏi xác nhận.

### 11.3. Kiểm tra đóng gói bằng camera (điểm nhấn cho người khiếm thị)

1. Agent: "Cô bày hàng của đơn này lên bàn rồi chụp một ảnh nhé."
2. `assess_photo(purpose="packing_check", expect={"items":[{"listing":"Mật ong rừng","count":2,"volume_ml":500}]})`
3. Vision trả về `{"count_seen":1,"volume_ml_est":500,"confidence":0.8}`.
4. Lệch → `BlockedError(layer=3, code="PACKING_MISMATCH")` → agent: "Đơn cần hai chai, tôi chỉ thấy một chai. Cô kiểm tra lại giúp tôi."
5. Khớp → `order.packing_check_passed = True` → agent: "Đúng hai chai mật ong nửa lít. Cô đóng gói được rồi. Nhớ quấn giấy chống sốc vì là chai thủy tinh."

**Prompt cho vision (packing):**

```text
Đếm và mô tả các sản phẩm trong ảnh. Trả về JSON:
{"items":[{"type":"...", "count": n, "volume_ml_est": n|null, "notes":"..."}],
 "confidence": 0..1, "photo_issue": null|"dark"|"blurry"|"cut_off"|"cluttered"}
Không đoán khi không chắc: nếu không đếm được, đặt count=null và photo_issue phù hợp.
```

### 11.4. Báo đã gửi và đọc mã gửi hàng

- Người bán chụp tờ biên nhận ở bưu cục. `assess_photo(purpose="receipt")` đọc mã gửi hàng (OCR bằng vision).
- Agent đọc mã theo nhóm 4 ký tự, chậm: "Mã gửi hàng: S-P-X-V... nhóm một: 1-2-3-4, nhóm hai: 5-6-7-8...". Nếu đọc ảnh không chắc, agent hỏi người bán đọc lại số trên giấy.
- Sau đó xác nhận hai bước:
  1. Agent tóm tắt: "Đơn của chị Lan, hai chai, mã gửi hàng kết thúc bằng 5678."
  2. Người bán nói "đã gửi rồi" → `shipped`.

### 11.5. Gom đơn theo ngày gửi [P1]

```python
def plan_shipping_trip(seller):
    open_orders = orders(seller, status in ["accepted", "packed"])
    next_days = next_shipping_dates(seller.shipping_days, horizon_days=7)
    plan = {d: [] for d in next_days}
    late = []
    for o in sorted(open_orders, key=lambda o: o.ship_by):
        day = first(d for d in next_days if d <= o.ship_by.date())
        (plan[day] if day else late).append(o)
    return plan, late
# Agent: "Thứ Năm cô mang 3 đơn đi gửi. Có 1 đơn hạn thứ Tư, không kịp chờ thứ Năm.
#         Cô có đi bưu cục thứ Tư được không?"
```

### 11.6. Hiển thị ở chế độ chạm

`OrderCard` gồm:
- Ảnh sản phẩm lớn
- Số lượng bằng chữ số lớn kèm số icon tương ứng (●●)
- Số tiền dùng `MoneyVisual`
- Thanh hạn gửi đổi màu: xanh nếu còn trên 2 ngày, vàng nếu còn 1–2 ngày, đỏ nếu dưới 1 ngày
- 3 nút hành động theo trạng thái

Chữ dưới 8 từ. Đơn mới thì máy rung 2 lần.

---

## 12. Phát triển bán hàng

### 12.1. Nguyên tắc
1. **Mỗi lần tối đa 1 gợi ý**, kèm 1 câu lý do có số liệu.
2. **Không bao giờ tự áp dụng.** Đồng ý thì mới đi qua Confirmation Engine.
3. Ưu tiên gợi ý **ít rủi ro và dễ đảo ngược** trước.
4. Người bán từ chối thì không nhắc lại gợi ý cùng loại trong 7 ngày.

### 12.2. Danh mục gợi ý

| `kind` | Điều kiện kích hoạt | Lời gợi ý mẫu | Hành động khi đồng ý | Mức |
|---|---|---|---|---|
| `restock` | stock ≤ ngưỡng | "Mật ong còn 2 chai. Tuần trước cô bán 6 chai. Cô có thêm hàng không?" | `update_stock` | RED |
| `answer_pending` | Câu hỏi khách chờ trên 12 giờ | "Có 2 khách đang chờ cô trả lời. Trả lời nhanh giúp bán được hơn." | Mở luồng trả lời | Không |
| `better_photo` | Tin có lượt xem nhưng không ai mua, ảnh chất lượng thấp | "Nhiều người xem nhưng chưa ai mua. Chụp lại ảnh sáng hơn có thể giúp." | Luồng chụp ảnh | YELLOW |
| `title_keywords` | Từ khóa người mua hay tìm không có trong tiêu đề (dữ liệu mock) | "Người mua hay tìm 'mật ong bạc hà'. Cô có muốn thêm vào tên không?" | Sửa tiêu đề (đọc lại) | YELLOW |
| `price_position` | Giá cao hơn 80% hàng cùng loại và ít đơn | "Giá cô cao hơn phần lớn shop khác. Giảm còn 280 nghìn thì cô vẫn nhận X." | Đổi giá | RED, 2 bước |
| `bundle` | Khách thường mua 2 sản phẩm cùng nhau | "Khách hay mua mật ong cùng chè. Cô có muốn bán gói cả hai không?" | Tạo tin combo | RED |
| `seasonal` | Lịch mùa vụ trong `categories.json` | "Sắp tới mùa mật ong bạc hà. Cô muốn đăng lại tin năm ngoái không?" | Đăng lại (đọc lại) | RED, 2 bước |
| `promotion` [P2] | Có chương trình của sàn (mock) | "Shopee có chương trình giảm giá 10.10. Tham gia thì cô nhận ít hơn X mỗi chai, nhưng thường bán nhiều hơn." | Tham gia | RED, 2 bước |

### 12.3. Bản tin cuối ngày (`daily_briefing`)

```
Mẫu giọng nói (≤ 45 giây):
"Hôm nay cô có {n_orders} đơn, nhận về {payout_spoken}.
 Ngày mai cần gửi {n_to_ship} đơn{, hạn sớm nhất là {earliest}}.
 {Có {n_q} khách đang chờ cô trả lời.}
 {Gợi ý: {one_suggestion}}
 Cô muốn nghe chi tiết phần nào thì nói tên phần đó."
```

Chế độ chạm hiển thị 3 thẻ: Đơn, Tiền, Việc cần làm. Gợi ý (nếu có) là thẻ thứ 4 với nút "Làm" và "Để sau".

### 12.4. Dữ liệu cho gợi ý (mock)

`demo_seed.json` chứa:
- `views_last_7d`: lượt xem 7 ngày gần nhất
- `orders_last_7d`: đơn 7 ngày gần nhất
- `buyer_search_terms`: từ khóa người mua hay tìm
- `co_purchase_pairs`: các cặp sản phẩm hay được mua cùng nhau
- `season_calendar`: lịch mùa vụ

Mọi số trong lời gợi ý phải lấy từ đây và được lưu trong `GrowthSuggestion.evidence`.

---

## 13. Trực shop

```
Khách hỏi → BuyerMessage(new)
  → SupportService.try_auto_answer():
        tìm trong FAQ đã duyệt + trường CONFIRMED (khớp từ khóa / LLM chọn nguồn)
        LLM viết câu trả lời → answer_buyer(source_refs) → code kiểm tra mọi ref hợp lệ
        ok → gửi khách, status=answered_auto
        không có nguồn → ask_seller → gửi khách "Shop đang kiểm tra, sẽ trả lời sớm ạ"
  → Người bán (giọng nói): "Khách ở Đà Nẵng hỏi: mật ong có pha đường không?"
     Người bán: "Không pha gì hết, mật nhà nuôi lấy luôn."
  → seller_answer: LLM chuẩn hóa → "Dạ, mật ong của shop không pha thêm gì, lấy trực tiếp từ đàn ong nhà nuôi ạ."
  → Đọc lại cho người bán (YELLOW): "Tôi sẽ trả lời khách là: ... Gửi đi nhé?" → "gửi đi"
  → gửi khách + lưu FAQ(approved_by_seller=True) + cập nhật trường "additives" = "none" (CONFIRMED, source=voice)
```

**Cảnh báo lừa đảo [P1]:**
- Tin nhắn chứa mẫu nghi ngờ (chuyển khoản ngoài sàn, link lạ, "đã chuyển tiền rồi gửi hàng trước", yêu cầu mã OTP) → agent cảnh báo người bán: "Tin này có dấu hiệu lừa đảo. Không gửi hàng khi Shopee chưa báo có đơn."
- Không tự trả lời các tin này.

---

## 14. Giao diện theo chế độ

| Màn hình | VoiceMode | TouchMode |
|---|---|---|
| Chính | 1 nút mic khổng lồ; dòng chữ nhỏ cho người nhìn được | 4 thẻ lớn: Bán hàng mới, Đơn hàng, Khách hỏi, Hôm nay |
| Xác nhận | Âm báo + câu đọc lại; mic tự mở 8 giây | `ConfirmCard`: số lớn + hình + ĐÚNG (giữ 1,5 giây)/SAI |
| Camera | Hướng dẫn bằng giọng nói; tự chụp khi nói "chụp" hoặc nhấn nút to | Khung hướng dẫn tương phản cao, mũi tên chỉ hướng |
| Thông báo | Âm báo khác nhau cho đơn mới / khách hỏi / cảnh báo | Rung + thẻ màu |

**Bắt buộc về tiếp cận:**
- Mọi nút có `aria-label` tiếng Việt.
- Tương phản ≥ 7:1.
- Vùng chạm ≥ 64px.
- Không có thao tác nào chỉ làm được bằng cử chỉ phức tạp (vuốt nhiều ngón).
- VoiceMode dùng được với TalkBack/VoiceOver đang bật: mic phải là phần tử focus đầu tiên.

**DemoBoard (màn hình lớn cho giám khảo):**
- Hội thoại dạng phụ đề
- Phiếu sản phẩm với trạng thái từng trường (màu)
- Bộ đếm "Lỗi đã chặn" theo lớp
- Trạng thái đơn hàng
- Trang shop giả lập như người mua nhìn thấy

---

## 15. API backend

| Method | Path | Mô tả |
|---|---|---|
| POST | `/api/sellers` | Tạo người bán (tên, chế độ, vùng) |
| GET | `/api/sellers/{id}` | Thông tin + tùy chọn |
| PATCH | `/api/sellers/{id}/preferences` | Đổi chế độ, tốc độ, ngày gửi (qua xác nhận) |
| WS | `/ws/session/{seller_id}` | Kênh chính: gửi audio/sự kiện nút/ảnh; nhận lời nói (audio + text), thẻ, thông báo |
| POST | `/api/turn/{seller_id}` | Dự phòng không dùng WS: multipart `audio` hoặc `button` hoặc `image` → danh sách OutputEvent |
| POST | `/api/images` | Tải ảnh, trả `image_id` |
| GET | `/api/listings?seller_id=` | Danh sách tin |
| GET | `/api/listings/{id}` | Tin + trường + trạng thái |
| GET | `/api/orders?seller_id=&status=` | Danh sách đơn |
| GET | `/api/demo/board/{seller_id}` | Dữ liệu cho DemoBoard |
| POST | `/api/demo/reset` | Đặt lại dữ liệu demo |
| POST | `/api/demo/simulate/order` | Bắn một đơn mới (cho demo) |
| POST | `/api/demo/simulate/buyer_message` | Bắn một câu hỏi của khách |

**Định dạng sự kiện WebSocket:**

```jsonc
// client → server
{"type":"audio","data":"<base64 webm/opus>"}
{"type":"button","value":"yes_hold"|"no"|"repeat"|"slower"|"card:new_listing"|...}
{"type":"image","image_id":42,"purpose":"listing"|"packing_check"|"receipt"}

// server → client
{"type":"speak","text":"...","audio":"<base64 mp3>","priority":"normal"|"confirm"}
{"type":"card","card":{"kind":"confirm","big":"300.000 đ","visual":"notes:100000x3","text":"Giá mỗi chai"}}
{"type":"notify","kind":"new_order"|"buyer_question"|"warning","payload":{...},"vibrate":[200,100,200]}
{"type":"open_camera","purpose":"packing_check","guide":"Bày hàng lên bàn rồi chụp"}
{"type":"board_update","payload":{...}}   // chỉ DemoBoard nhận
```

---

## 16. Shopee giả lập (mock)

```
/mock/shopee/listings            POST/GET    — tạo, xem tin công khai
/mock/shopee/orders              GET         — đơn của shop
/mock/shopee/orders/{id}/status  POST        — accept|pack|ship|cancel
/mock/shopee/messages            GET/POST    — chat người mua
/mock/shopee/fees                GET         — biểu phí (từ fees.json)
/mock/shopee/market_prices       GET ?category=&q=
```

**`fees.json` (giả định cho demo, ghi rõ là ước tính):**

```json
{"note":"Biểu phí giả định để minh họa, không phải biểu phí thật của Shopee",
 "commission_rate":0.08, "payment_fee_rate":0.04, "fixed_fee_per_order":0,
 "shipping_estimates":{"liquid_glass_500ml":{"weight_g":800,"fee":30000}}}
```

**`simulator.py`:**
- `spawn_order(listing_id, qty, buyer, province, ship_by_days)` → tạo đơn + gọi `OrderService.ingest`.
- `spawn_buyer_message(listing_id, text)`.
- Chế độ kịch bản: đọc `demo_script.json` để bắn sự kiện theo thứ tự khi bấm phím tắt trên DemoBoard. Tránh dùng hẹn giờ ngẫu nhiên trong lúc demo.

---

## 17. Kiểm thử

### 17.1. Unit test bắt buộc

| File | Nội dung |
|---|---|
| `test_numbers.py` | Toàn bộ bảng mục 10 |
| `test_confirm_engine.py` | YES/NO/WEAK_YES theo mức; hai bước cần đúng cụm từ; sửa số trong câu trả lời; hết giờ; phát hiện gật đầu theo quán tính |
| `test_sanity.py` | Từng mã lỗi trong 9.7 |
| `test_sources.py` | Câu không thẻ bị loại; thẻ trỏ trường chưa xác nhận bị loại; BANNED_CLAIMS |
| `test_orders.py` | Không nhận đơn khi thiếu hàng; không packed khi kiểm tra đóng gói chưa đạt; không shipped khi thiếu mã |

### 17.2. Kịch bản lỗi (`test_scenarios.py`), mỗi kịch bản phải sinh `BlockedError` đúng lớp

| ID | Đầu vào giả lập | Mong đợi |
|---|---|---|
| S-E1 | STT trả "bảy trăm" độ tin cậy 0,7 | Hỏi lại với nhấn "bảy, không phải ba"; lớp 1 |
| S-E2 | "ba trăm" ở ngữ cảnh giá | Đọc lại "ba trăm **nghìn** đồng"; assumed_unit |
| S-E3 | Ảnh ước 500ml, trường 1000ml | IMAGE_MISMATCH; lớp 3 |
| S-E4 | Giá 35.000 cho mật ong (median 300.000) | PRICE_OUTLIER_LOW, gợi ý 350.000; lớp 2 |
| S-E5 | Người bán trả "ừ" cho giá lần đầu | clarify explicit_yes |
| S-E6 | 3 xác nhận RED liên tiếp < 2 giây | Câu hỏi mở; nếu trả lời lệch → RUBBER_STAMP; lớp 4 |
| S-E7 | LLM viết "mật ong nguyên chất 100%" không thẻ | UNSOURCED_SENTENCE + BANNED_CLAIM; lớp 3 |
| S-E8 | Gọi request_publish khi origin chưa xác nhận | NOT_CONFIRMED; tin không đăng |
| S-O1 | Ảnh đóng gói 1 chai, đơn cần 2 | PACKING_MISMATCH; không cho packed |
| S-O2 | "Đã gửi rồi" khi chưa có mã | NO_TRACKING |
| S-O3 | Im lặng 60 giây khi xác nhận nhận đơn | timeout; đơn vẫn `new` |
| S-B1 | Khách hỏi điều chưa có trong dữ liệu | ask_seller; không trả lời đoán |

### 17.3. Thử với người thật (trước ngày thi)
- 1 người bịt mắt (hoặc người khiếm thị thật) thực hiện trọn luồng: đăng tin → nhận đơn → kiểm tra đóng gói → báo đã gửi. Đo thời gian, đếm số lần hỏi lại, ghi lại chỗ bối rối.
- Điều chỉnh câu chữ trong `i18n/vi.py` theo phản hồi.

---

## 18. Cài đặt và chạy

```bash
# Backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env      # điền OPENAI_API_KEY, LLM_MODEL, STT_PROVIDER, TTS_PROVIDER
python -m app.db --seed   # tạo DB + nạp data/*.json
pytest -q                 # phải xanh trước khi demo
uvicorn app.main:app --reload --port 8000

# Frontend
cd ../frontend
npm install
npm run dev               # http://localhost:5173 ; dùng HTTPS hoặc localhost để được quyền mic/camera
```

**`requirements.txt`:**
```
fastapi
uvicorn[standard]
sqlmodel
pydantic
python-multipart
openai
httpx
pytest
pytest-asyncio
```

**`.env.example`:**
```
OPENAI_API_KEY=
LLM_MODEL=            # mô hình có tool calling + vision
STT_PROVIDER=openai   # openai | fpt
TTS_PROVIDER=openai   # openai | fpt
FPT_API_KEY=
CONFIRM_TIMEOUT_S=30
PENDING_PUBLISH_MIN=10
RUBBER_STAMP_MS=2000
ASR_CONF_THRESHOLD=0.85
```

**Điện thoại demo:** dùng HTTPS (ví dụ một tunnel) để trình duyệt điện thoại cho phép mic và camera. Kiểm tra trước trên đúng máy sẽ dùng.

---

## 19. Phân việc theo file cho 7 tiếng (4 người)

| Giờ | A — Agent & xác nhận | B — Giọng nói, ảnh, đơn hàng | C — Dữ liệu, kiểm thử, mock | D — Frontend & demo |
|---|---|---|---|---|
| 0:00–1:00 | `models.py`, `db.py`, `orchestrator.py` khung | `speech/stt.py`, `speech/tts.py` | `data/*.json`, `mock_shopee/router.py` | `VoiceMode`, `BigMicButton`, `api.ts` (WS) |
| 1:00–2:30 | `validators/numbers.py` + `confirm/engine.py` | `services/vision.py` (assess_photo) + `CameraCapture` phía server | `test_numbers.py`, `test_confirm_engine.py` | `ConfirmCard`, `MoneyVisual` |
| 2:30–4:00 | `agent/tools.py` (listing tools), `sanity.py`, `sources.py`, cổng `can_publish` | `services/orders.py` + packing_check + receipt | `simulator.py`, `test_scenarios.py` | `TouchMode`, `OrderCard`, `DemoBoard` |
| 4:00–5:00 | Order tools + `can_order_action` | `services/support.py` (answer/ask seller) | `services/growth.py` (daily_briefing, restock) | `MockShopPage` |
| 5:00–6:00 | Ghép, sửa lỗi luồng chính | Thông báo đơn mới, âm báo, rung | Chạy kịch bản demo 5 lần, ghi số liệu | Tập demo, slide |
| 6:00–7:00 | Khóa code | Quay video dự phòng | Chuẩn bị số liệu cho hỏi đáp | Tập pitch |

**Cắt giảm khi trễ (theo thứ tự):**
1. `promotion`, `bundle`, `seasonal`
2. Gom đơn theo ngày
3. Cảnh báo lừa đảo
4. Chế độ bảo trợ
5. TouchMode chỉ còn 1 màn hình xác nhận

**Không cắt:** Confirmation Engine, chuẩn hóa số, cổng chặn, packing_check.

---

## 20. Kịch bản demo (3 phút, bản có quản lý đơn)

| Thời gian | Diễn ra | Giám khảo thấy |
|---|---|---|
| 0:00–0:15 | Câu trích dẫn thật từ người dùng đã phỏng vấn | Đội hiểu người dùng |
| 0:15–1:00 | Thành viên bịt mắt đăng mật ong. Agent hướng dẫn chụp lại vì tối, mô tả ảnh. Người bán nói "bảy trăm" → agent hỏi lại "bảy, không phải ba" | Chụp ảnh cho người khiếm thị + lớp 1 |
| 1:00–1:25 | Ảnh chai nửa lít khác lời "một lít" → agent hỏi lại. Đọc lại, tiền thực nhận, "đăng đi", tin chờ 10 phút | Lớp 2–3–5; bộ đếm "lỗi đã chặn" tăng |
| 1:25–2:10 | Bấm phím trên DemoBoard → đơn mới 2 chai. Agent đọc đơn → "nhận đơn". Người bán chụp hàng: chỉ 1 chai → agent chặn: "Đơn cần hai chai". Thêm chai, chụp lại → đạt | **Quản lý đơn bằng giọng nói + kiểm tra đóng gói** |
| 2:10–2:35 | Chuyển TouchMode: cùng đơn hiện thành thẻ to, giữ nút ĐÃ ĐÓNG GÓI, không âm thanh | Một agent, mọi người bán |
| 2:35–2:50 | Giám khảo đóng vai khách hỏi câu khó → agent hỏi người bán → người bán trả lời → agent đọc lại, gửi | Không bịa, học thành FAQ |
| 2:50–3:00 | Bản tin cuối ngày 10 giây + câu chốt pitch | Phát triển bán hàng |
