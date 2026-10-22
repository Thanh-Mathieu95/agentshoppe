"""Mọi câu tiếng Việt agent nói. {h} = cách xưng hô (cô), {H} = viết hoa đầu (Cô)."""

T = {
    # --- chào, chế độ ---
    "greeting": "Chào {h} {name}. Tôi là Bạn Bán Hàng. {H} muốn nói chuyện, hay bấm nút?",
    "greeting_back": "Chào {h}. {H} muốn bán hàng mới, xem đơn, hay nghe tin hôm nay?",
    "what_next": "{H} muốn làm gì tiếp ạ?",
    "not_understood": "Tôi chưa hiểu. {H} muốn bán hàng mới, hay hỏi về đơn hàng?",
    "stopped": "Tôi dừng. Phiếu vẫn được lưu. Khi nào {h} sẵn sàng thì nhấn nút nói tiếp nhé.",
    "slower_ok": "Vâng, tôi sẽ nói chậm hơn.",
    "nothing_to_repeat": "Tôi chưa nói gì để nhắc lại ạ.",
    "mode_changed_voice": "Đã đổi sang chế độ nói chuyện.",
    "mode_changed_touch": "Đã đổi sang chế độ bấm.",
    "ask_change_mode": "{H} muốn đổi sang chế độ {mode_label}? Đồng ý thì nói 'đổi'.",

    # --- xác nhận ---
    "say_yes_hint": "Đúng thì {h} nói 'đúng'.",
    "clarify_explicit_yes": "{H} nói 'đúng' giúp tôi nhé, cho chắc ạ.",
    "clarify_unclear": "Tôi chưa nghe rõ. Đúng thì {h} nói 'đúng', sai thì nói 'sai'.",
    "clarify_action_phrase": "Muốn làm thì {h} nói '{phrase}' ạ. Không thì nói 'thôi'.",
    "confirm_timeout_reask": "{H} còn đó không ạ? {prompt}",
    "confirm_timeout_final": "Tôi lưu lại đã. Khi nào {h} sẵn sàng thì nhấn nút nói tiếp nhé.",
    "field_rejected": "{H} nói lại {label} giúp tôi.",
    "summary_rejected": "Sai chỗ nào ạ: {options}?",
    "action_cancelled": "Vâng, tôi chưa làm gì cả.",
    "rubber_stamp_question": "{H} nhắc lại giúp tôi, {question}",
    "rubber_stamp_ok": "Đúng rồi ạ. Cảm ơn {h}.",
    "rubber_stamp_mismatch": "Lúc nãy {h} xác nhận {old}, giờ {h} nói {new}. Tôi ghi lại {new} và hỏi lại nhé.",
    "emphasis_prefix": "Tôi nhắc lại số: {words}. ",
    "assumed_unit_note": "Tức là {money}, có chữ NGHÌN. ",
    "low_confidence_note": "Tôi nghe chưa rõ lắm. ",

    # --- đọc lại trường ---
    "readback_price": "{name}: giá {money}. Tức là {notes}. {emphasis}Đúng thì {h} nói 'đúng'.",
    "readback_volume_ml": "Mỗi {container} là {volume}. {emphasis}Đúng không {h}?",
    "readback_weight_g": "Mỗi {container} nặng {weight}. {emphasis}Đúng không {h}?",
    "readback_stock": "{H} đang có {stock_words} {container}. {emphasis}Đúng không ạ?",
    "readback_name": "Tên sản phẩm là: {value}. Đúng không ạ?",
    "readback_generic": "{label_cap}: {value}. Đúng không ạ?",

    # --- kiểm tra hợp lý ---
    "PRICE_OUTLIER_LOW": "Giá này thấp hơn nhiều so với hàng cùng loại, từ {min} đến {max}. {H} bán {price}, hay ý {h} là {alt}?",
    "PRICE_OUTLIER_HIGH": "Giá này cao hơn nhiều so với hàng cùng loại, từ {min} đến {max}. {H} bán {price}, hay ý {h} là {alt}?",
    "NEGATIVE_PAYOUT": "Bán giá này {h} lỗ khoảng {loss}. {H} có muốn đổi giá không?",
    "STOCK_OUTLIER": "{H} có {stock} hay {alt} ạ?",
    "CONTRADICTION": "Lúc nãy {h} nói {a}, giờ nói {b}. Cái nào đúng ạ?",
    "IMAGE_MISMATCH": "Trong ảnh tôi thấy {obs}, nhưng {h} nói {val}. {H} kiểm tra giúp tôi, cái nào đúng?",
    "UNIT_MISMATCH": "Tôi chưa rõ đơn vị. {H} nói lại {label} giúp tôi nhé.",
    "NOT_A_NUMBER": "Tôi chưa nghe ra con số. {H} nói lại {label} giúp tôi.",

    # --- đăng hàng ---
    "start_listing": "Vâng, mình đăng {label} nhé.",
    "ask_category": "{H} muốn bán loại hàng gì ạ? Mật ong, chè, đồ thủ công, nến hay đồ khô?",
    "ask_photo": "Giờ {h} chụp một ảnh sản phẩm nhé. Đặt sản phẩm lên bàn, chỗ sáng, rồi nhấn nút chụp.",
    "photo_guide_dark": "Ảnh hơi tối. {H} quay mặt về phía cửa sổ hoặc bật đèn, rồi chụp lại.",
    "photo_guide_blurry": "Ảnh bị mờ. {H} tì khuỷu tay lên bàn, giữ yên hai giây rồi chụp lại.",
    "photo_guide_cut_off": "Sản phẩm bị lệch ra mép ảnh. {H} lùi điện thoại ra một gang tay rồi chụp lại.",
    "photo_guide_cluttered": "Trong ảnh có nhiều đồ quá. {H} dọn bớt đồ xung quanh rồi chụp lại.",
    "photo_give_up": "Ảnh vẫn chưa tốt lắm. Tôi dùng ảnh rõ nhất. {H} có thể nhờ {guardian} chụp lại sau.",
    "photo_describe": "Tôi thấy {desc}. Đúng hàng của {h} không ạ?",
    "photo_describe_unknown": "Ảnh đủ sáng và rõ. Tôi chưa nhận ra chi tiết trong ảnh. Đây là hàng của {h} phải không ạ?",
    "photo_ok": "Ảnh tốt rồi ạ.",
    "skip_ok": "Vâng, bỏ qua phần này.",
    "price_report": "Hàng cùng loại bán từ {min} đến {max}. Mỗi {container}, Shopee giữ lại khoảng {fee}, tiền hộp gói khoảng {packaging}. {H} còn khoảng {payout}.",
    "policy_note": "Lưu ý: {say}",
    "draft_ready": "Tôi đã viết xong tin đăng.",
    "publish_summary": "Tôi đọc lại tin: {name}. Giá {money}. {extras}. Có {stock_words} {container}. Muốn đăng thì {h} nói 'đăng đi'.",
    "publish_pending": "Đã gửi tin lên. Trong {wait}, nếu muốn {h} nói 'rút lại'.",
    "publish_done": "Tin {name} đã lên Shopee rồi ạ.",
    "undo_done": "Đã rút lại tin. Tin quay về bản nháp.",
    "undo_nothing": "Không có gì để rút lại ạ.",
    "gate_blocked": "Chưa đăng được. {reason}",
    "gate_NOT_CONFIRMED": "Còn {label} chưa xác nhận.",
    "gate_NO_ACCEPTED_PHOTO": "Còn thiếu ảnh sản phẩm.",
    "gate_WAITING_GUARDIAN": "Đang chờ {guardian} duyệt.",
    "gate_SANITY": "Còn điều cần kiểm tra lại.",
    "gate_SOURCE": "Mô tả có câu chưa có nguồn.",
    "listing_need_choice": "{H} đang làm phiếu {name}. {H} muốn làm tiếp không?",

    # --- đơn hàng ---
    "new_order": "Có đơn mới. {buyer} ở {province} đặt {items}. {H} nhận về {payout}. Phải gửi trước {deadline}. {H} muốn nhận đơn thì nói 'nhận đơn'.",
    "order_detail": "Đơn của {buyer} ở {province}: {items}. {H} nhận về {payout}. Hạn gửi {deadline}. Trạng thái: {status}.",
    "order_accept_prompt": "Đơn của {buyer}: {items}, {h} nhận về {payout}. Nhận thì {h} nói 'nhận đơn'.",
    "order_accepted": "Đã nhận đơn. Khi chuẩn bị hàng xong, {h} chụp hàng để tôi kiểm tra nhé.",
    "order_out_of_stock": "Không đủ hàng: đơn cần {need}, {h} chỉ còn {have}. {H} có thêm hàng không, hay hủy đơn?",
    "order_none": "Không có đơn nào ạ.",
    "order_not_found": "Tôi không tìm thấy đơn đó ạ.",
    "order_summary": "Hôm nay có {total} đơn. {pending}{nearest}",
    "order_summary_pending": "Còn {n} đơn chưa xử lý. ",
    "order_summary_nearest": "Đơn gần hạn nhất là của {buyer}, hạn {deadline}.",
    "orders_due_soon": "Có {n} đơn sắp hết hạn gửi. Gần nhất là của {buyer}, hạn {deadline}.",
    "orders_due_none": "Không có đơn nào sắp trễ ạ.",
    "orders_filter": "Có {n} đơn {label}. {first}",
    "packing_ask_photo": "{H} bày hàng của đơn này lên bàn rồi chụp một ảnh nhé.",
    "packing_mismatch": "Đơn cần {need}, tôi chỉ thấy {seen}. {H} kiểm tra lại giúp tôi.",
    "packing_unsure": "Tôi đếm chưa được hàng trong ảnh. {H} chụp lại gần hơn, chỗ sáng hơn nhé.",
    "packing_pass": "Đúng {need}. {H} đóng gói được rồi. {tip} Đóng xong thì nói 'đóng gói xong'.",
    "packing_not_verified": "Chưa kiểm tra hàng. {H} chụp hàng để tôi xem trước nhé. Nếu muốn bỏ qua thì nói 'bỏ qua kiểm tra'.",
    "packed_prompt": "Báo đơn của {buyer} đã đóng gói xong? Đúng thì {h} nói 'đúng'.",
    "packed_done": "Đã ghi đóng gói xong. Gửi ở bưu cục xong thì {h} chụp tờ biên nhận cho tôi nhé.",
    "packing_override_prompt": "{H} muốn bỏ qua kiểm tra hàng của đơn {buyer}? Tôi sẽ ghi lại việc này. Đúng thì nói 'đúng'.",
    "receipt_ask_photo": "{H} chụp tờ biên nhận ở bưu cục giúp tôi nhé.",
    "receipt_read": "Mã gửi hàng: {spoken}.",
    "receipt_unsure": "Tôi đọc chưa rõ mã. {H} đọc giúp tôi mã trên tờ giấy nhé.",
    "ship_need_tracking": "Chưa có mã gửi hàng. {H} chụp tờ biên nhận giúp tôi trước nhé.",
    "ship_not_packed": "Đơn này chưa đóng gói xong. {H} kiểm tra hàng và đóng gói trước nhé.",
    "ship_prompt": "Đơn của {buyer}, {items}, mã gửi hàng kết thúc bằng {last4}. Gửi rồi thì {h} nói 'đã gửi rồi'.",
    "shipped_done": "Đã báo gửi hàng cho đơn của {buyer}. Shopee sẽ báo khách.",
    "cancel_ask_reason": "Vì sao hủy ạ: {options}?",
    "cancel_prompt": "Hủy đơn của {buyer} vì {reason}. Hủy nhiều có thể làm shop bị giảm điểm. Chắc chắn thì {h} nói 'hủy đơn'.",
    "cancelled_done": "Đã hủy đơn của {buyer}.",
    "ship_plan": "{plan}{late}",
    "ship_plan_day": "{day} {h} mang {n} đơn đi gửi. ",
    "ship_plan_late": "Có {n} đơn hạn {deadline}, không kịp chờ ngày gửi. {H} có đi bưu cục sớm hơn được không?",
    "ship_plan_none": "Không có đơn nào cần gửi ạ.",
    "warn_due_soon": "Đơn của {buyer} còn chưa tới một ngày là hết hạn gửi.",
    "stock_prompt": "Cập nhật {name} còn {stock_words} {container}. Đúng thì {h} nói 'đúng'.",
    "stock_done": "Đã cập nhật còn {stock_words} {container}.",
    "low_stock": "{name} còn {n} {container}. {H} có thêm hàng không?",
    "payout_month": "Tháng này {h} nhận về {money} từ {n} đơn.",

    # --- trực shop ---
    "buyer_wait": "Dạ shop đang kiểm tra, sẽ trả lời bạn sớm ạ.",
    "buyer_question": "{buyer} hỏi: {text} {H} trả lời thế nào ạ?",
    "buyer_question_queued": "Có khách hỏi. {H} muốn nghe không?",
    "seller_answer_prompt": "Tôi sẽ trả lời khách là: {answer} Gửi đi nhé? Đồng ý thì nói 'gửi đi'.",
    "seller_answer_sent": "Đã gửi khách. Lần sau có người hỏi giống vậy, tôi tự trả lời.",
    "auto_answered": "Tôi đã trả lời khách hỏi về {topic}.",
    "scam_warning": "Tin này có dấu hiệu lừa đảo. Không gửi hàng khi Shopee chưa báo có đơn. Không đọc mã cho ai.",
    "no_buyer_questions": "Không có khách nào đang chờ ạ.",

    # --- phát triển ---
    "briefing": "Hôm nay {h} có {n_orders} đơn, nhận về {payout}. {to_ship}{questions}{suggestion}{H} muốn nghe chi tiết phần nào thì nói tên phần đó.",
    "briefing_to_ship": "Ngày mai cần gửi {n} đơn, hạn sớm nhất là {earliest}. ",
    "briefing_questions": "Có {n} khách đang chờ {h} trả lời. ",
    "briefing_suggestion": "Gợi ý: {text} ",
    "suggestion_none": "Hiện chưa có gợi ý gì mới. Shop đang ổn ạ.",
    "suggestion_ask": "{text} {H} có muốn làm không?",
    "suggestion_declined": "Vâng, tôi sẽ không nhắc lại việc này trong một tuần.",
    "suggestion_later": "Vâng, để sau ạ.",
    "restock_ask_number": "{H} có thêm bao nhiêu {container}?",
    "title_prompt": "Tên mới: {title}. Đổi thì {h} nói 'làm đi'.",
    "title_done": "Đã đổi tên tin đăng.",
    "price_change_prompt": "Đổi giá {name} từ {old} thành {new}. Mỗi {container} {h} vẫn nhận khoảng {payout}. Chắc chắn thì nói 'đổi giá'.",
    "price_change_done": "Đã đổi giá thành {new}.",
    "bundle_note": "Tôi ghi lại ý này. Khi {h} muốn, tôi sẽ giúp tạo tin gói chung.",
    "seasonal_prompt": "Đăng lại tin {name}? Đồng ý thì {h} nói 'đăng đi'.",
    "republished": "Đã đăng lại tin {name}.",

    # --- bảo trợ ---
    "guardian_sent": "Đã gửi cho {guardian} duyệt. Khi duyệt xong tôi báo {h}.",
    "guardian_approved": "{guardian} đã duyệt. ",
    "guardian_rejected": "{guardian} chưa đồng ý việc: {summary}.",
}

DAY_NAMES = {"mon": "thứ Hai", "tue": "thứ Ba", "wed": "thứ Tư", "thu": "thứ Năm", "fri": "thứ Sáu", "sat": "thứ Bảy", "sun": "Chủ nhật"}
WEEKDAY_KEYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]

ORDER_STATUS = {"new": "đơn mới, chưa nhận", "accepted": "đã nhận, chưa đóng gói", "packed": "đã đóng gói, chưa gửi",
                "shipped": "đã gửi", "delivered": "khách đã nhận", "cancelled": "đã hủy", "dispute": "đang khiếu nại"}

CANCEL_REASONS = ["hết hàng", "khách yêu cầu", "không gửi kịp"]

MODE_LABEL = {"voice": "nói chuyện", "touch": "bấm"}


def t(key: str, h: str = "cô", **kw) -> str:
    return T[key].format(h=h, H=h[:1].upper() + h[1:], **kw)


def cap(s: str) -> str:
    return s[:1].upper() + s[1:] if s else s
