import { useEffect, useRef, useState } from "react";
import { getJSON, postJSON, setProfileId } from "../api";
import Icon, { Mark, type IconName } from "../components/Icon";
import { hearOnce, say, stopSpeaking } from "../speech";

type Existing = { id: number; name: string; shop_name: string; region: string; avatar: string };
type ModeKey = "voice" | "touch" | "guardian";

const MODES: { key: ModeKey; icon: IconName; title: string; desc: string; bg: string; fg: string }[] = [
  { key: "voice", icon: "ear", title: "Nghe và nói", desc: "Trợ lý đọc to, bạn trả lời bằng giọng", bg: "#fff1d6", fg: "#b45309" },
  { key: "touch", icon: "hand", title: "Nhìn và chạm", desc: "Chữ to, hình rõ, không cần âm thanh", bg: "#e3ebff", fg: "#1d3fa6" },
  { key: "guardian", icon: "users", title: "Có người giúp", desc: "Người nhà duyệt các việc quan trọng", bg: "#dcf6e7", fg: "#065f2b" },
];
const HONORIFICS = ["cô", "chú", "bác", "chị", "anh", "em", "bà", "ông"];
const REGIONS = ["Hà Giang", "Lào Cai", "Sơn La", "Lai Châu", "Điện Biên", "Cao Bằng", "Yên Bái", "Đắk Lắk", "Lâm Đồng", "Hà Nội"];
const DAYS: [string, string][] = [["mon", "T2"], ["tue", "T3"], ["wed", "T4"], ["thu", "T5"], ["fri", "T6"], ["sat", "T7"], ["sun", "CN"]];

const PROMPTS = [
  "Chào bạn. Tôi là Bạn Bán Hàng, giúp bạn bán hàng trên sàn. Mình tạo hồ sơ trước nhé.",
  "Bạn muốn dùng thế nào? Nghe và nói, nhìn và chạm, hay có người giúp?",
  "Bạn tên là gì? Bấm nút micro màu vàng rồi nói tên.",
  "Cửa hàng của bạn ở tỉnh nào? Bấm micro rồi nói tên tỉnh.",
  "Bạn thường đi bưu cục gửi hàng vào thứ mấy? Chọn các ngày trên màn hình.",
  "Tôi đọc lại hồ sơ. Nếu đúng, bấm nút Tạo hồ sơ ở dưới cùng.",
];

function cleanName(t: string) {
  return t.replace(/^(dạ|vâng|à|ờ)[, ]*/i, "").replace(/^(tôi|tao|em|cô|chú|bác|chị|anh|mình)?\s*(tên là|tên|là)\s+/i, "")
    .replace(/[.!?]+$/, "").trim().replace(/(^|\s)\S/g, (c) => c.toUpperCase());
}
function cleanPlace(t: string) {
  return t.replace(/^(ở|tại|tỉnh|tôi ở|em ở|nhà ở)\s+/i, "").replace(/^(tỉnh)\s+/i, "").replace(/[.!?]+$/, "").trim()
    .replace(/(^|\s)\S/g, (c) => c.toUpperCase());
}

function MicField({ value, onChange, placeholder, hint, clean, autoListen }: {
  value: string; onChange: (v: string) => void; placeholder: string; hint: string; clean: (t: string) => string; autoListen?: boolean;
}) {
  const [rec, setRec] = useState(false);
  const stopRef = useRef<() => void>(() => {});
  const listen = async () => {
    if (rec) { stopRef.current(); return; }
    stopSpeaking();
    setRec(true);
    const h = hearOnce(hint);
    stopRef.current = h.stop;
    const text = await h.promise;
    setRec(false);
    if (text) onChange(clean(text));
  };
  useEffect(() => { if (autoListen && !value) { const t = setTimeout(listen, 200); return () => clearTimeout(t); } }, [autoListen]); // eslint-disable-line
  return (
    <div className="with-mic">
      <input value={value} onChange={(e) => onChange(e.target.value)} placeholder={placeholder} aria-label={placeholder} />
      <button type="button" className={rec ? "rec" : ""} onClick={listen} aria-label={rec ? "Dừng nghe" : "Nói để điền"}>
        <Icon name={rec ? "stop" : "mic"} size={28} />
      </button>
    </div>
  );
}

/** Tạo hồ sơ bằng màn hình (cho người khiếm thính / người nhìn được). presetMode: bỏ bước chọn cách dùng. */
export default function Onboarding({ presetMode }: { presetMode?: ModeKey } = {}) {
  const [step, setStep] = useState(presetMode ? 2 : 0);
  const [mode, setMode] = useState<ModeKey | null>(presetMode ?? null);
  const [name, setName] = useState("");
  const [honor, setHonor] = useState("cô");
  const [shop, setShop] = useState("");
  const [region, setRegion] = useState("");
  const [days, setDays] = useState<string[]>(["tue", "fri"]);
  const [guardian, setGuardian] = useState("");
  const avatar = "🏪";
  const [existing, setExisting] = useState<Existing[]>([]);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const voice = mode === "voice" || mode === "guardian";

  useEffect(() => { getJSON<Existing[]>("/api/sellers").then(setExisting).catch(() => {}); }, []);
  useEffect(() => {
    if (step === 0 || (step > 1 && !voice)) return;
    let text = PROMPTS[step];
    if (step === 5) text += ` Tên: ${name}. Gọi là ${honor}. Cửa hàng: ${shop || "Shop " + name}, ở ${region}.`;
    say(text);
    return () => stopSpeaking();
  }, [step]); // eslint-disable-line

  const canNext = [true, !!mode, name.trim().length >= 2, region.trim().length >= 2, days.length > 0, true][step];
  const next = () => setStep((s) => Math.min(5, s + 1));
  const back = () => setStep((s) => Math.max(0, s - 1));

  const create = async () => {
    setBusy(true);
    setErr("");
    try {
      const s = await postJSON("/api/sellers", {
        name: name.trim(), honorific: honor, shop_name: shop.trim() || `Shop ${name.trim()}`, region: region.trim(),
        mode: mode === "touch" ? "touch" : "voice", shipping_days: days, guardian_required: mode === "guardian",
        guardian_name: guardian.trim() || null, avatar,
      });
      stopSpeaking();
      setProfileId(s.id);
    } catch {
      setErr("Chưa tạo được hồ sơ. Kiểm tra lại tên và tỉnh nhé.");
      setBusy(false);
    }
  };

  return (
    <div className="ob">
      {step > 0 && (
        <>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <button className="icon-btn" onClick={back} aria-label="Quay lại"><Icon name="back" /></button>
            <div className="progress" style={{ flex: 1 }} aria-label={`Bước ${step} trên 5`}>
              {[1, 2, 3, 4, 5].map((i) => <i key={i} className={i <= step ? "on" : ""} />)}
            </div>
            <button className="icon-btn" onClick={() => say(PROMPTS[step])} aria-label="Nghe lại hướng dẫn"><Icon name="speaker" /></button>
          </div>
        </>
      )}

      {step === 0 && <>
        <div className="hero-bee"><Mark size={88} /></div>
        <h1>Chào bạn!<br />Tôi là Bạn Bán Hàng</h1>
        <p className="lead">Tôi giúp bạn đăng hàng, nhận đơn và trả lời khách bằng giọng nói. Mọi việc quan trọng đều đọc lại để bạn xác nhận.</p>
        <button className="btn primary" style={{ minHeight: 76, fontSize: 22 }} onClick={next}>
          Tạo hồ sơ của tôi <Icon name="arrow" />
        </button>
        {existing.length > 0 && <>
          <div style={{ color: "var(--muted)", fontWeight: 700, marginTop: 8 }}>Hoặc mở hồ sơ đã có</div>
          {existing.map((e) => (
            <button key={e.id} className="profile" onClick={() => setProfileId(e.id)}>
              <span className="av">{e.avatar}</span>
              <span style={{ flex: 1 }}><b style={{ fontSize: 18 }}>{e.name}</b><div style={{ color: "var(--muted)" }}>{e.shop_name} · {e.region}</div></span>
              <Icon name="arrow" />
            </button>
          ))}
        </>}
      </>}

      {step === 1 && <>
        <h1>Bạn muốn dùng thế nào?</h1>
        <div className="modes" role="radiogroup">
          {MODES.map((m) => (
            <button key={m.key} role="radio" aria-checked={mode === m.key} className={`mode ${mode === m.key ? "on" : ""}`}
                    onClick={() => { setMode(m.key); if (m.key !== "touch") say(m.title); }}>
              <span className="ico" style={{ background: m.bg, color: m.fg }}><Icon name={m.icon} size={34} /></span>
              <span><b>{m.title}</b><span>{m.desc}</span></span>
            </button>
          ))}
        </div>
      </>}

      {step === 2 && <>
        <h1>Bạn tên là gì?</h1>
        <label className="field">Tên của bạn
          <MicField value={name} onChange={setName} placeholder="Ví dụ: Lò Thị Mai" hint="Người bán nói tên mình" clean={cleanName} autoListen={voice} />
        </label>
        <div className="field">Trợ lý gọi bạn là
          <div className="choices">{HONORIFICS.map((h) => <button key={h} className={`choice ${honor === h ? "on" : ""}`} onClick={() => setHonor(h)}>{h}</button>)}</div>
        </div>
      </>}

      {step === 3 && <>
        <h1>Cửa hàng của bạn</h1>
        <label className="field">Tỉnh / nơi ở
          <MicField value={region} onChange={setRegion} placeholder="Ví dụ: Hà Giang" hint="Tên tỉnh ở Việt Nam" clean={cleanPlace} autoListen={voice} />
        </label>
        <div className="choices">{REGIONS.map((r) => <button key={r} className={`choice ${region === r ? "on" : ""}`} onClick={() => setRegion(r)}>{r}</button>)}</div>
        <label className="field">Tên cửa hàng (không bắt buộc)
          <MicField value={shop} onChange={setShop} placeholder={`Shop ${name || "của bạn"}`} hint="Tên cửa hàng" clean={(t) => t.replace(/[.!?]+$/, "")} />
        </label>
      </>}

      {step === 4 && <>
        <h1>Ngày đi gửi hàng</h1>
        <p className="lead">Chọn những ngày bạn thường ra bưu cục. Trợ lý sẽ gom đơn theo các ngày này.</p>
        <div className="choices" role="group" aria-label="Ngày gửi hàng">
          {DAYS.map(([k, l]) => (
            <button key={k} aria-pressed={days.includes(k)} className={`choice ${days.includes(k) ? "on" : ""}`} style={{ minWidth: 64 }}
                    onClick={() => setDays((d) => (d.includes(k) ? d.filter((x) => x !== k) : [...d, k]))}>{l}</button>
          ))}
        </div>
        {mode === "guardian" && (
          <label className="field">Người giúp bạn duyệt việc quan trọng
            <MicField value={guardian} onChange={setGuardian} placeholder="Ví dụ: anh Hùng (con trai)" hint="Tên người thân" clean={(t) => t.replace(/[.!?]+$/, "")} />
          </label>
        )}
      </>}

      {step === 5 && <>
        <h1>Kiểm tra lại hồ sơ</h1>
        <div className="summary">
          <div><span>Tên</span><b>{avatar} {name}</b></div>
          <div><span>Gọi là</span><b>{honor}</b></div>
          <div><span>Cửa hàng</span><b>{shop || `Shop ${name}`}</b></div>
          <div><span>Ở</span><b>{region}</b></div>
          <div><span>Cách dùng</span><b>{MODES.find((m) => m.key === mode)?.title}</b></div>
          <div><span>Ngày gửi hàng</span><b>{DAYS.filter(([k]) => days.includes(k)).map(([, l]) => l).join(", ")}</b></div>
          {mode === "guardian" && <div><span>Người giúp</span><b>{guardian || "—"}</b></div>}
        </div>
        {err && <div className="card red" role="alert">{err}</div>}
      </>}

      {step > 0 && (
        <div className="foot">
          {step < 5
            ? <button className="btn primary" disabled={!canNext} onClick={next}>Tiếp tục <Icon name="arrow" /></button>
            : <button className="btn dark" disabled={busy} onClick={create}><Icon name="check" /> {busy ? "Đang tạo…" : "Tạo hồ sơ"}</button>}
        </div>
      )}
    </div>
  );
}
