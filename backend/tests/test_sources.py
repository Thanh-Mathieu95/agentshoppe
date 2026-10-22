from types import SimpleNamespace

from app.models import FieldState
from app.validators import sources


def F(value, state=FieldState.CONFIRMED, raw=None):
    return SimpleNamespace(value=value, state=state, raw_utterance=raw or value, history=[value])


FIELDS = {"name": F("Mật ong rừng"), "origin": F("Hà Giang"), "volume_ml": F("500"),
          "harvest_time": F("tháng ba", FieldState.HEARD)}


def codes(errs):
    return [e[0] for e in errs]


def test_untagged_sentence_removed():
    assert codes(sources.check("Mật ong rất thơm.", FIELDS)) == ["UNSOURCED_SENTENCE"]


def test_tag_to_unconfirmed_field():
    assert "SOURCE_NOT_CONFIRMED" in codes(sources.check("Lấy mật tháng ba [harvest_time].", FIELDS))


def test_banned_claims():
    errs = sources.check("Mật ong nguyên chất 100% [name].", FIELDS)
    assert codes(errs).count("BANNED_CLAIM") == 2


def test_banned_claim_allowed_if_seller_said_it():
    fields = {**FIELDS, "name": F("Mật ong nguyên chất", raw="mật ong nguyên chất")}
    assert sources.check("Mật ong nguyên chất [name].", fields) == []


def test_name_from_utterance():
    from app.services.listings import name_from_utterance
    assert name_from_utterance("cô muốn đăng bán mật ong rừng nhà nuôi, giá ba trăm nghìn một chai nhé") == "Mật ong rừng nhà nuôi"
    assert name_from_utterance("Cô muốn bán mật ong rừng ba trăm nghìn một chai") == "Mật ong rừng"
    assert name_from_utterance("Chè Shan tuyết") == "Chè Shan tuyết"


def test_clean_keeps_only_sourced():
    text = "Mật ong rừng lấy ở Hà Giang [name][origin]. Mật ong tốt nhất vùng. Mỗi chai 500 ml [volume_ml]. Không dùng cho trẻ dưới 1 tuổi. [policy]"
    tagged, public = sources.clean(text, FIELDS)
    assert "tốt nhất" not in public
    assert public == "Mật ong rừng lấy ở Hà Giang. Mỗi chai 500 ml. Không dùng cho trẻ dưới 1 tuổi."


def test_split_stable_when_tags_follow_period_on_new_line():
    from app.validators.sources import split_sentences
    t = "Mật ong đóng chai. [name][volume_ml]\nLấy ở Đồng Văn. [origin]"
    a = split_sentences(t)
    assert a == split_sentences(" ".join(a)) and a[0].endswith("[volume_ml]")