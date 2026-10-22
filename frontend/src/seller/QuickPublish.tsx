import { useEffect, useRef, useState } from "react";
import { getJSON, postJSON } from "../api";
import Icon from "../components/Icon";

type Field = { key: string; label: string; value: string | null; unit: string | null; required: boolean;
  choices: string[] | null; numeric: boolean; from: string | null };
type Draft = { listing_id: number; status: string; category: string; container: string; images: string[];
  market: { min: number; max: number; note: string }; fields: Field[];
  price?: { price: number; floor: number } | null; product_url?: string };

const vnd = (v: number) => v.toLocaleString("vi-VN") + " đ";
const UNIT: Record<string, string> = { price: "đ", volume_ml: "ml", weight_g: "g" };

/** Đăng nhanh: ảnh + một câu -> AI điền cả tin -> xem lại trên màn hình -> một nút Đăng. */
export default function QuickPublish({ sellerId }: { sellerId: number }) {
  const [photo, setPhoto] = useState<{ file?: File; demo?: string; url: string } | null>(null);
  const [text, setText] = useState("");
  const [demos, setDemos] = useState<{ name: string; label: string; url: string }[]>([]);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [values, setValues] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState<"" | "ai" | "publish">("");
  const [err, setErr] = useState("");
  const [done, setDone] = useState<Draft | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => { getJSON<any[]>("/api/demo/photos").then((d) => setDemos(d.filter((x) => !x.name.startsWith("receipt") && !/dark|blurry/.test(x.name)))).catch(() => {}); }, []);
  // ảnh quảng cáo AI vẽ nền chạy ngầm: cập nhật dải ảnh khi có
  const [ver, setVer] = useState(0);
  useEffect(() => {
    if (!draft) return;
    if (done) {   // đã đăng bằng nền dự phòng: nền AI xong sẽ thay ảnh tại chỗ -> tải lại ảnh vài lần
      const t = setInterval(() => setVer((v) => v + 1), 6000);
      const stop = setTimeout(() => clearInterval(t), 70000);
      return () => { clearInterval(t); clearTimeout(stop); };
    }
    const t = setInterval(() => getJSON<Draft>(`/api/quick/${sellerId}/${draft.listing_id}`).then((d) => setDraft((x) => x && { ...x, images: d.images })).catch(() => {}), 3000);
    return () => clearInterval(t);
  }, [draft?.listing_id, done, sellerId]);

  const pick = (f: File | undefined) => f && setPhoto({ file: f, url: URL.createObjectURL(f) });

  const runAI = async () => {
    if (!photo) return;
    setBusy("ai"); setErr(""); setDone(null);
    const fd = new FormData();
    fd.append("text", text);
    if (photo.file) fd.append("file", photo.file);
    else if (photo.demo) fd.append("demo_photo", photo.demo);
    try {
      const r = await fetch(`/api/quick/${sellerId}`, { method: "POST", body: fd });
      const j = await r.json();
      if (!r.ok) throw new Error(j.detail || "Lỗi");
      setDraft(j);
      setValues(Object.fromEntries(j.fields.map((f: Field) => [f.key, f.value || ""])));
    } catch (e: any) { setErr(e.message); }
    setBusy("");
  };

  const publish = async () => {
    if (!draft) return;
    setBusy("publish"); setErr("");
    try {
      const r = await postJSON<any>(`/api/quick/${sellerId}/${draft.listing_id}/publish`, { values });
      if (!r.ok) setErr(r.errors.join(" "));
      else { setDone(r); setDraft(r); }
    } catch (e: any) { setErr(e.message); }
    setBusy("");
  };

  const reset = () => { setPhoto(null); setText(""); setDraft(null); setDone(null); setErr(""); };

  return (
    <div className="panel qp">
      <h3>Đăng nhanh từ ảnh <span className="chip new">AI điền sẵn · bạn xem lại · một nút đăng</span></h3>

      {!draft && <>
        <div className="qp-step">
          <div className={`qp-drop ${photo ? "has" : ""}`} onClick={() => fileRef.current?.click()}
               onDragOver={(e) => e.preventDefault()} onDrop={(e) => { e.preventDefault(); pick(e.dataTransfer.files[0]); }}>
            {photo ? <img src={photo.url} alt="Ảnh sản phẩm" /> : <><Icon name="image" size={40} /><b>Kéo thả hoặc bấm để chọn ảnh sản phẩm</b><span>Ảnh chụp sẵn trong máy</span></>}
            <input ref={fileRef} type="file" accept="image/*" hidden onChange={(e) => pick(e.target.files?.[0])} />
          </div>
          {demos.length > 0 && (
            <div className="qp-demos">Hoặc dùng ảnh mẫu:
              {demos.map((d) => <button key={d.name} className="chip" onClick={() => setPhoto({ demo: d.name, url: d.url })}>{d.label}</button>)}
            </div>
          )}
        </div>
        <label className="qp-say">Nói một câu về sản phẩm (tên, giá hoặc giá thấp nhất, số lượng)
          <textarea rows={2} value={text} onChange={(e) => setText(e.target.value)}
                    placeholder="Ví dụ: Mật ong bạc hà Đồng Văn, chai nửa lít, có 15 chai, bán không dưới 200 nghìn" />
        </label>
        <button className="qp-btn" disabled={!photo || busy === "ai"} onClick={runAI}>
          <Icon name="sparkle" /> {busy === "ai" ? "AI đang xem ảnh và điền tin… (khoảng 5 giây)" : "Để AI điền tin đăng"}
        </button>
      </>}

      {draft && <>
        <div className="qp-imgs">
          {draft.images.map((u, i) => <img key={u} src={ver ? `${u}?v=${ver}` : u} alt={`Ảnh ${i + 1}`} />)}
          {!done && draft.images.length < 4 && <div className="qp-imgwait">AI đang làm ảnh quảng cáo…</div>}
        </div>
        {draft.price && <div className="qp-note"><Icon name="sparkle" size={18} /> Giá đề xuất {vnd(draft.price.price)}: sàn đang bán {vnd(draft.market.min)}–{vnd(draft.market.max)} ({draft.market.note}), không thấp hơn giá sàn bạn nói ({vnd(draft.price.floor)}).</div>}
        <div className="qp-form">
          {draft.fields.map((f) => (
            <label key={f.key} className={values[f.key] ? "" : "empty"}>
              <span>{f.label}{f.required && <i>*</i>}{f.from === "image" && <em>AI đoán từ ảnh</em>}</span>
              {f.choices
                ? <select value={values[f.key] || ""} disabled={!!done} onChange={(e) => setValues({ ...values, [f.key]: e.target.value })}>
                    <option value="">—</option>{f.choices.map((c) => <option key={c}>{c}</option>)}</select>
                : <div className="qp-in"><input value={values[f.key] || ""} disabled={!!done} inputMode={f.numeric ? "numeric" : undefined}
                    onChange={(e) => setValues({ ...values, [f.key]: e.target.value })} placeholder={f.required ? "bắt buộc" : "không bắt buộc"} />
                    {f.numeric && <b>{f.key === "stock" ? draft.container : UNIT[f.key]}</b>}</div>}
            </label>
          ))}
        </div>
        {err && <div className="qp-err">{err}</div>}
        {done
          ? <div className="qp-done">
              <b>✓ {done.status === "published" ? "Sản phẩm đã lên sàn" : "Đã gửi đăng, chờ lên sàn"}</b>
              <a href={done.product_url} target="_blank" rel="noreferrer">Xem trên sàn ›</a>
              <button className="chip" onClick={reset}>Đăng sản phẩm khác</button>
            </div>
          : <div className="qp-actions">
              <button className="chip" onClick={reset}>Làm lại</button>
              <button className="qp-btn" disabled={busy === "publish"} onClick={publish}>
                <Icon name="send" /> {busy === "publish" ? "Đang hoàn tất ảnh và đăng…" : "Đăng lên sàn"}
              </button>
            </div>}
      </>}
      {!draft && err && <div className="qp-err">{err}</div>}
    </div>
  );
}
