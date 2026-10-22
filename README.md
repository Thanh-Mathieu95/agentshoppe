# Bán Không Rào Cản

Trợ lý **Bạn Bán Hàng** giúp người bán vùng cao, người khiếm thị, khiếm thính tự bán hàng trên sàn thương mại điện tử bằng giọng nói hoặc thẻ chạm. Trợ lý được cắm vào một **sàn thương mại giả lập kiểu Shopee** (người mua đặt hàng thật trên sàn, đơn báo về điện thoại người bán).

> Đặc tả gốc: `ban-khong-rao-can-spec.md`. Mọi hành động có hậu quả đều đi qua **Confirmation Engine** và bị chặn bằng code nếu chưa đủ xác nhận. LLM không bao giờ tự xác nhận.

## Chạy

```powershell
# Backend
cd backend
python -m venv .venv; .\.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env          # không cần key: agent chạy chế độ luật offline
python -m app.db --seed         # tạo DB, ảnh sản phẩm, 6 shop mẫu
pytest -q                       # 70 test
uvicorn app.main:app --port 8000 --reload

# Frontend
cd ..\frontend
npm install
npm run dev                     # http://localhost:5173
```

Điện thoại thật cần HTTPS để mở mic/camera (dùng tunnel). Trên máy tính dùng Chrome (Web Speech tiếng Việt).

## Các màn hình

| Đường dẫn | Ai dùng | Nội dung |
|---|---|---|
| `#/` | Người mua | Trang chủ sàn: danh mục, bán chạy, shop vùng cao |
| `#/search?q=` · `#/p/:id` · `#/shop/:id` | Người mua | Tìm kiếm, chi tiết (thông số đã xác nhận, đánh giá, **Hỏi shop** do trợ lý trả lời có nguồn), trang shop |
| `#/cart` · `#/checkout` · `#/orders` | Người mua | Giỏ hàng, đặt hàng COD giả lập, theo dõi đơn theo từng bước |
| `#/seller` | Người bán (máy tính) | Kênh Người Bán: tổng quan, đơn, sản phẩm, chat, an toàn; **điện thoại trợ lý** gắn bên phải |
| `#/app` | Người bán (điện thoại) | Trợ lý: chế độ **Nghe – Nói** (nút mic khổng lồ) và **Nhìn – Chạm** (thẻ to, giữ ĐÚNG 1,5 giây) |
| `#/board` | Giám khảo | Phụ đề, phiếu theo trạng thái trường, bộ đếm **lỗi đã chặn theo 5 lớp**, phím tắt kịch bản 1–7 |
| `#/guardian` | Người bảo trợ | Duyệt các hành động ĐỎ khi bật "cần bảo trợ" |

## Kịch bản demo nhanh

1. Mở `#/seller` (trợ lý nằm trong khung điện thoại) và `#/board` trên màn hình lớn.
2. Nói/gõ: *"Cô muốn bán mật ong rừng bảy trăm nghìn một chai"* → trợ lý nhấn "BẢY, không phải ba"; sửa *"không, ba trăm nghìn"*.
3. Chụp ảnh (có ảnh mẫu nếu không có camera): ảnh tối → hướng dẫn chụp lại; nói "một lít" khi ảnh là chai nửa lít → hỏi lại.
4. Nghe giá thị trường, tiền thực nhận, đọc lại tin → *"đăng đi"* → chờ 10 phút (phím 5 trên board để tua).
5. Mở `#/` như người mua → mua 2 chai → điện thoại người bán báo đơn → *"nhận đơn"*.
6. Chụp hàng: 1 chai → bị chặn "đơn cần hai chai"; 2 chai → đạt → *"đóng gói xong"* → chụp biên nhận → *"đã gửi rồi"*. Trang `#/orders` của người mua chuyển "Đang giao".
7. Người mua hỏi trên trang sản phẩm "có pha đường không?" → trợ lý hỏi người bán → người bán trả lời → đọc lại → *"gửi đi"* → lần sau tự trả lời.

## Kiến trúc

```
backend/app
  agent/      orchestrator (vòng lặp lượt), flow (luật + hiệu lực sau xác nhận), tools (schema LLM), prompts, llm, session
  confirm/    engine (phân tích đúng/sai bằng code, chống gật đầu theo quán tính), templates (đọc số, tờ tiền), confusables
  validators/ numbers (chuẩn hóa số tiếng Việt), sanity (giá lệch, ảnh lệch...), sources (thẻ [key], BANNED_CLAIMS)
  services/   listings, orders, vision (Pillow + mô hình nhìn), support, growth, pricing, policy, notifier
  mock_shopee/ sàn giả lập: catalog, sản phẩm, checkout, đơn người mua, chat
frontend/src
  market/     sàn (trang chủ, tìm kiếm, chi tiết, giỏ, thanh toán, đơn mua, shop)
  seller/     Kênh Người Bán
  modes/      VoiceMode, TouchMode, GuardianView ; components/ ConfirmCard, HoldButton, MoneyVisual, OrderCard, CameraCapture
  demo/       DemoBoard
```

**Chế độ agent:** không có key → bộ luật tiếng Việt (offline, ổn định cho demo). Có `OPENAI_API_KEY` + `LLM_MODEL` → LLM gọi công cụ cho câu nói tự do; xác nhận, đi tiếp phiếu và cổng chặn vẫn chạy bằng code. Ảnh: Pillow chấm tối/mờ thật; nhận dạng vật dùng mô hình nhìn nếu có key, nếu không dùng ảnh mẫu có sẵn nhãn.

**Dữ liệu giả lập:** biểu phí, giá thị trường, shop, đánh giá đều là dữ liệu minh họa, không phải của Shopee.
