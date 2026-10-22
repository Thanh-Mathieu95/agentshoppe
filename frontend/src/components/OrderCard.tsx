import type { Card } from "../api";
import HoldButton from "./HoldButton";
import MoneyVisual from "./MoneyVisual";

export const ICON: Record<string, string> = { honey: "🍯", tea: "🍵", handicraft: "🧶", candle: "🕯️", dried_food: "🥩" };

const ACTION: Record<string, { label: string; hold?: boolean; cam?: boolean }> = {
  accept: { label: "NHẬN ĐƠN", hold: true },
  cancel: { label: "Hủy" },
  packing_check: { label: "📷 Kiểm tra hàng", cam: true },
  mark_packed: { label: "ĐÃ ĐÓNG GÓI", hold: true },
  receipt: { label: "📷 Chụp biên nhận", cam: true },
  mark_shipped: { label: "ĐÃ GỬI", hold: true },
};

function hoursLeft(iso: string) {
  return (new Date(iso).getTime() - Date.now()) / 36e5;
}

export default function OrderCard({ card, send, compact }: { card: Card; send: (v: string) => void; compact?: boolean }) {
  const left = hoursLeft(card.ship_by);
  const pct = Math.max(4, Math.min(100, (left / 96) * 100));
  return (
    <div className={compact ? "" : `card ${card.urgency === "red" ? "red" : card.urgency === "yellow" ? "yellow" : ""}`}
         style={{ display: "grid", gap: 12 }} aria-label={`Đơn của ${card.buyer}, ${card.status_text}`}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8 }}>
        <b style={{ fontSize: 22 }}>{card.buyer}</b>
        <span className="badge">{card.province}</span>
      </div>
      {(card.items || []).map((it: any, i: number) => (
        <div key={i} style={{ display: "flex", alignItems: "center", gap: 14 }}>
          {it.image_id
            ? <img src={`/api/images/${it.image_id}/file`} alt={it.name} style={{ width: 96, height: 96, borderRadius: 14, objectFit: "cover" }} />
            : <div style={{ fontSize: 72 }} aria-hidden="true">{ICON[it.visual] || "📦"}</div>}
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 56, fontWeight: 900, lineHeight: 1 }}>{it.qty}</div>
            <div className="dots" style={{ textAlign: "left" }} aria-hidden="true">{"●".repeat(Math.min(it.qty, 10))}</div>
            <div style={{ fontSize: 18, color: "var(--muted)" }}>{it.container} {it.name}</div>
          </div>
        </div>
      ))}
      <div style={{ fontSize: 34, fontWeight: 900, textAlign: "center" }}>{card.payout_big}</div>
      <MoneyVisual visual={card.visual} />
      <div>
        <div className="deadline" aria-label={`Hạn gửi ${card.deadline}`}>
          <div className={card.urgency} style={{ width: `${pct}%` }} />
        </div>
        <div style={{ display: "flex", justifyContent: "space-between", fontSize: 17, marginTop: 6, color: "var(--muted)" }}>
          <span>Gửi trước: <b style={{ color: "#fff" }}>{card.deadline}</b></span>
          <span>{card.status_text}</span>
        </div>
      </div>
      {card.tracking && <div style={{ textAlign: "center", fontSize: 22, letterSpacing: 2 }}>📮 {card.tracking}</div>}
      {!compact && (card.actions || []).length > 0 && (
        <div className="options">
          {card.actions.map((a: string) => {
            const def = ACTION[a];
            if (!def) return null;
            const value = `order:${card.order_id}:${a}`;
            if (a === "mark_packed" && !card.packing_ok) return null;
            return def.hold
              ? <HoldButton key={a} label={def.label} onDone={() => send(value)} className="btn primary hold" />
              : <button key={a} className={`btn ${def.cam ? "" : "ghost"}`} onClick={() => send(value)}>{def.label}</button>;
          })}
        </div>
      )}
    </div>
  );
}
