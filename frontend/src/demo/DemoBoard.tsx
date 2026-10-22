import { useEffect, useRef, useState } from "react";
import { Channel, money, postJSON } from "../api";
import DemoToggle from "../components/DemoToggle";
import { ICON } from "../components/OrderCard";

const STATE_LABEL: Record<string, string> = { empty: "TRỐNG", heard: "ĐÃ NGHE", checked: "ĐÃ KIỂM", confirmed: "ĐÃ XÁC NHẬN" };
const STATUS: Record<string, string> = { drafting: "Đang soạn", ready: "Chờ xác nhận đăng", pending_publish: "Chờ lên sàn (rút lại được)", published: "Đang bán", hidden: "Đã ẩn" };

/** Màn hình lớn cho giám khảo: phụ đề, phiếu, lỗi đã chặn theo lớp, đơn hàng, shop. Phím 1–7 bắn sự kiện kịch bản. */
export default function DemoBoard({ sellerId }: { sellerId: number }) {
  const [b, setB] = useState<any>(null);
  const [flash, setFlash] = useState(false);
  const lastTotal = useRef(0);
  const subsEnd = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const c = new Channel(`/ws/board/${sellerId}`, (e) => e.type === "board_update" && setB(e.payload));
    return () => c.close();
  }, [sellerId]);

  useEffect(() => {
    if (!b) return;
    if (b.blocked.total > lastTotal.current && lastTotal.current) {
      setFlash(true);
      setTimeout(() => setFlash(false), 900);
    }
    lastTotal.current = b.blocked.total;
    subsEnd.current?.scrollIntoView({ block: "end" });
  }, [b]);

  const run = (key: string) => postJSON(`/api/demo/script/${key}?seller_id=${sellerId}`).catch((e) => alert(e.message));
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.target as HTMLElement)?.tagName === "INPUT") return;
      if (/^[1-9]$/.test(e.key)) run(e.key);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (!b) return <div className="board"><h1>Đang kết nối…</h1></div>;
  const l = b.listing;

  return (
    <div className="board">
      <header>
        <div>
          <h1>Bán Không Rào Cản · <span style={{ color: "var(--accent)" }}>{b.seller.name}</span></h1>
          <div style={{ color: "var(--muted)" }}>
            Chế độ: <b>{b.seller.mode === "voice" ? "👂 Nghe – Nói" : "👆 Nhìn – Chạm"}</b> · Agent: <b>{b.agent_mode === "llm" ? "LLM + công cụ" : "luật (offline)"}</b>
            {b.seller.guardian_required && <> · 👥 Bảo trợ: <b>{b.seller.guardian_name}</b></>}
          </div>
        </div>
        <nav className="nav">
          <a href="#/app" target="_blank">📱 Trợ lý</a>
          <a href="#/" target="_blank">🛒 Sàn</a>
          <a href="#/seller" target="_blank">🛍️ Kênh người bán</a>
          <a href="#/guardian" target="_blank">👥 Bảo trợ</a>
          <DemoToggle />
          <button className="btn small" onClick={() => confirm("Đặt lại toàn bộ dữ liệu demo?") && postJSON("/api/demo/reset")}>⟲ Đặt lại</button>
        </nav>
      </header>

      <section className="panel">
        <h2>Hội thoại</h2>
        {b.pending && <div className="pending-banner">⏳ Đang chờ người bán xác nhận{b.pending.two_step ? " (2 bước)" : ""}: {b.pending.subject_ref}
          {b.pending.flags?.length ? <div style={{ fontWeight: 500, fontSize: 14 }}>cờ: {b.pending.flags.join(", ")}</div> : null}</div>}
        <div className="subs" aria-live="polite">
          {b.subtitles.map((s: any, i: number) => <div key={i} className={s.who}>{s.text}</div>)}
          <div ref={subsEnd} />
        </div>
      </section>

      <section className="panel" style={{ gap: 14 }}>
        <div>
          <h2>Phiếu sản phẩm</h2>
          {l ? (
            <>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8, gap: 8 }}>
                <b style={{ fontSize: 20 }}>{ICON[l.category]} {l.title || "(chưa có tiêu đề)"}</b>
                <span className={`badge ${l.status === "published" ? "green" : l.status === "pending_publish" ? "yellow" : ""}`}>{STATUS[l.status] || l.status}</span>
              </div>
              <div className="fields">
                {l.fields.map((f: any) => (
                  <div key={f.key} className="field">
                    <span className={`risk ${f.risk}`} title={`Mức ${f.risk}`} />
                    <span><span style={{ color: "var(--muted)" }}>{f.label}:</span> <b>{f.value ?? "—"}</b></span>
                    <span className={`state ${f.state}`}>{STATE_LABEL[f.state]}</span>
                  </div>
                ))}
              </div>
              {l.images?.length > 0 && <img src={l.images[l.images.length - 1]} alt="" style={{ width: "100%", maxHeight: 140, objectFit: "cover", borderRadius: 12, marginTop: 8 }} />}
            </>
          ) : <div style={{ color: "var(--muted)" }}>Chưa có phiếu.</div>}
        </div>
        <div>
          <h2>Đơn hàng</h2>
          <div className="orders-mini">
            {b.orders.map((o: any) => (
              <div key={o.order_id}>
                <span>{o.items.map((i: any) => `${ICON[i.visual] || ""} ${i.qty}`).join(" ")} · {o.buyer}</span>
                <span className={`badge ${o.status === "new" ? "yellow" : o.status === "shipped" || o.status === "delivered" ? "green" : ""}`}>{o.status_text}</span>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="panel" style={{ gap: 14 }}>
        <div className={flash ? "flash" : ""}>
          <h2>Lỗi đã chặn</h2>
          <div style={{ display: "flex", alignItems: "baseline", gap: 12 }}>
            <span className="bigcount" style={{ transform: flash ? "scale(1.15)" : "none", transition: "transform .2s" }}>{b.blocked.total}</span>
            <span style={{ color: "var(--muted)" }}>/ {b.blocked.confirmations} lần xác nhận</span>
          </div>
          <div className="layers" style={{ marginTop: 10 }}>
            {b.blocked.by_layer.map((x: any) => (
              <div key={x.layer} className="layer"><span className="n">{x.layer}</span><span>{x.name}</span><b>{x.count}</b></div>
            ))}
          </div>
          <div className="blocked-log">
            {b.blocked.recent.map((r: any, i: number) => <div key={i}><code>L{r.layer} {r.code}</code> {r.detail}</div>)}
          </div>
        </div>
        <div>
          <h2>Kịch bản demo (phím tắt)</h2>
          <div className="script">
            {b.script.map((s: any) => <button key={s.key} onClick={() => run(s.key)}><kbd>{s.key}</kbd>{s.label}</button>)}
          </div>
        </div>
        <div>
          <h2>Shop như người mua thấy</h2>
          <div className="orders-mini">
            {b.shop.map((p: any) => <div key={p.id}><span>{ICON[p.category]} {p.title}</span><b>{p.price ? money(p.price) : ""}</b></div>)}
          </div>
          {b.guardian.length > 0 && <div className="pending-banner" style={{ marginTop: 8 }}>👥 {b.guardian.length} việc chờ người bảo trợ duyệt</div>}
        </div>
      </section>
    </div>
  );
}
