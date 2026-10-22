from app.confirm.engine import ConfirmationRequest, log_confirmation, resolve, rubber_stamp_suspected
from app.models import Risk


def field_req(risk=Risk.RED, number=300000, key="price"):
    return ConfirmationRequest(seller_id=1, subject_ref=f"listing:1:{key}", kind="field", risk=risk, prompt_text="?",
                               value_display={"key": key, "number": number})


def action_req(two_step=True, phrase="đăng đi"):
    return ConfirmationRequest(seller_id=1, subject_ref="listing:1:publish", kind="action", risk=Risk.RED,
                               prompt_text="?", two_step=two_step, action_phrase=phrase)


def test_yes_no():
    assert resolve(field_req(), "đúng rồi").kind == "confirmed"
    assert resolve(field_req(), "Đúng ạ").kind == "confirmed"
    assert resolve(field_req(), "sai rồi").kind == "rejected"
    assert resolve(field_req(), "không phải").kind == "rejected"
    assert resolve(field_req(), "không đúng").kind == "rejected"


def test_weak_yes_by_risk():
    r = resolve(field_req(Risk.RED), "ừ")
    assert r.kind == "clarify" and r.reason == "explicit_yes"
    req = field_req(Risk.RED)
    req.attempts = 1
    assert resolve(req, "ừ").kind == "confirmed"
    assert resolve(field_req(Risk.YELLOW, number=None, key="origin"), "vâng").kind == "confirmed"


def test_two_step_needs_phrase():
    assert resolve(action_req(), "đúng rồi").reason == "say_action_phrase"
    assert resolve(action_req(), "ừ").reason == "say_action_phrase"
    assert resolve(action_req(), "ừ đăng đi").kind == "confirmed"
    assert resolve(action_req(), "thôi").kind == "rejected"
    assert resolve(action_req(phrase="đã gửi rồi"), "tôi đã gửi rồi").kind == "confirmed"


def test_buttons():
    assert resolve(action_req(), None, "yes_hold").kind == "confirmed"
    assert resolve(action_req(), None, "no").kind == "rejected"


def test_correction_inside_answer():
    r = resolve(field_req(number=700000), "không, ba trăm nghìn")
    assert r.kind == "corrected" and r.new_value.int_value == 300000
    assert resolve(field_req(number=700000), "không phải bảy trăm").kind == "rejected"
    assert resolve(field_req(number=300000), "ba trăm nghìn").kind == "confirmed"
    stock = field_req(number=5, key="stock")
    assert resolve(stock, "còn năm chai thôi").kind == "confirmed"


def test_control_words():
    assert resolve(field_req(), "nói lại").control == "repeat"
    assert resolve(field_req(), "chậm thôi").control == "slower"
    assert resolve(field_req(), "dừng").control == "stop"


def test_unclear_never_confirms():
    for text in ["", "hả", "cái gì", "để tôi xem"]:
        assert resolve(field_req(), text).kind == "clarify"


def test_rubber_stamp(db):
    req = field_req()
    for _ in range(3):
        log_confirmation(db, req, "confirmed", "đúng", 500)
    assert rubber_stamp_suspected(db, 1)
    log_confirmation(db, req, "confirmed", "đúng", 3500)
    assert not rubber_stamp_suspected(db, 1)
