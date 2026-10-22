import type { Card } from "../api";
import HoldButton from "./HoldButton";
import MoneyVisual from "./MoneyVisual";
import OrderCard from "./OrderCard";

function Visual({ visual }: { visual?: string }) {
  if (!visual) return null;
  if (visual.startsWith("notes:")) return <MoneyVisual visual={visual} />;
  if (visual.startsWith("count:")) {
    const n = Number(visual.slice(6));
    return <div className="dots" aria-hidden="true">{n <= 12 ? "●".repeat(n) : `● × ${n}`}</div>;
  }
  if (visual.startsWith("volume:")) {
    const ml = Number(visual.slice(7));
    const h = Math.min(120, 40 + ml / 12);
    return (
      <svg width="90" height="140" viewBox="0 0 90 140" style={{ alignSelf: "center" }} aria-hidden="true">
        <rect x="35" y={140 - h - 18} width="20" height="14" fill="#cfd8dc" />
        <rect x="15" y={140 - h} width="60" height={h} rx="10" fill="#ffb300" stroke="#fff" strokeWidth="3" />
      </svg>
    );
  }
  return null;
}

/** Thẻ ĐÚNG/SAI cho chế độ chạm: số lớn + hình + giữ ĐÚNG 1,5 giây. */
export default function ConfirmCard({ card, send }: { card: Card; send: (v: string, text?: string) => void }) {
  const risk = card.risk || "red";
  return (
    <div className={`card ${risk}`} role="group" aria-label={card.text}>
      {card.kind === "confirm_order" ? <OrderCard card={card} send={send} compact /> : null}
      {card.warning && <div className="warning" role="alert">⚠ {card.warning}</div>}
      {card.kind === "photo" && card.image_id && (
        <img src={`/api/images/${card.image_id}/file`} alt={card.detail || "Ảnh vừa chụp"} style={{ width: "100%", borderRadius: 16, maxHeight: 260, objectFit: "cover" }} />
      )}
      {card.kind === "summary" ? (
        <div style={{ display: "grid", gap: 6 }}>
          {card.title && <div className="label" style={{ color: "#fff" }}>{card.title}</div>}
          {(card.rows || []).map((r: any) => (
            <div key={r.key} style={{ display: "flex", justifyContent: "space-between", fontSize: 22, gap: 12 }}>
              <span style={{ color: "var(--muted)" }}>{r.label}</span><b style={{ textAlign: "right" }}>{r.value}</b>
            </div>
          ))}
        </div>
      ) : card.kind !== "confirm_order" && (
        <>
          {card.big && <div className="big">{card.big}</div>}
          <Visual visual={card.visual} />
          {card.text && <div className="label">{card.text}</div>}
        </>
      )}
      {card.alt && (
        <button className="btn primary" onClick={() => send("", card.alt.value)}>Ý là {card.alt.big}?</button>
      )}
      <div className="confirm-actions">
        <div className="row">
          <HoldButton label={card.two_step ? "Giữ để LÀM" : "ĐÚNG"} onDone={() => send("yes_hold")} />
          <button className="btn no hold" onClick={() => send("no")} aria-label="Sai">SAI</button>
        </div>
      </div>
    </div>
  );
}
