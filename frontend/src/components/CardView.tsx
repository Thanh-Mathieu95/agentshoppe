import { useState } from "react";
import type { Card } from "../api";
import ConfirmCard from "./ConfirmCard";
import Icon, { type IconName } from "./Icon";
import MoneyVisual from "./MoneyVisual";
import OrderCard, { ICON } from "./OrderCard";

type Btn = (value: string, text?: string) => void;

const STAT: Record<string, [IconName, string]> = {
  "Đơn hôm nay": ["box", "t2"], "Tiền nhận": ["money", "t3"], "Việc cần làm": ["check", "t1"],
};

function AnswerBox({ numeric, placeholder, onSend }: { numeric?: boolean; placeholder: string; onSend: (t: string) => void }) {
  const [v, setV] = useState("");
  return (
    <form className="typebox" onSubmit={(e) => { e.preventDefault(); if (v.trim()) { onSend(v.trim()); setV(""); } }}>
      <input value={v} onChange={(e) => setV(e.target.value)} placeholder={placeholder} aria-label={placeholder}
             inputMode={numeric ? "numeric" : "text"} autoFocus />
      <button className="btn primary" aria-label="Gửi">➤</button>
    </form>
  );
}

/** Vẽ một thẻ server gửi, theo loại. */
export default function CardView({ card, button, pending }: { card: Card; button: Btn; pending: boolean }) {
  switch (card.kind) {
    case "confirm":
    case "summary":
    case "confirm_order":
    case "photo":
      return pending ? <ConfirmCard card={card} send={button} /> : null;
    case "order":
      return <OrderCard card={card} send={(v) => button(v)} />;
    case "ask":
    case "ask_number":
      return (
        <div className="card">
          <div className="label" style={{ color: "#fff" }}>{card.text}</div>
          <AnswerBox numeric={card.kind === "ask_number"} placeholder={card.kind === "ask_number" ? "Gõ số" : "Gõ câu trả lời"}
                     onSend={(t) => button("", t)} />
          {card.skippable && <button className="btn ghost" onClick={() => button("skip")}>Bỏ qua</button>}
        </div>
      );
    case "choices":
      return (
        <div className="card">
          <div className="label" style={{ color: "#fff" }}>{card.text}</div>
          <div className="options">
            {(card.options || []).map((o: string) => <button key={o} className="btn" onClick={() => button("", o)}>{o}</button>)}
          </div>
        </div>
      );
    case "categories":
      return (
        <div className="card">
          <div className="label" style={{ color: "#fff" }}>{card.text}</div>
          <div className="tiles">
            {(card.options || []).map((o: any) => (
              <button key={o.value} className="tile" onClick={() => button(`cat:${o.value}`)}>
                <span className="ico" aria-hidden="true">{ICON[o.visual] || "📦"}</span>{o.label}
              </button>
            ))}
          </div>
        </div>
      );
    case "question":
      return (
        <div className="card yellow">
          <span className="badge yellow">Khách hỏi · {card.buyer}</span>
          <div style={{ fontSize: 26, fontWeight: 800 }}>“{card.text}”</div>
          <AnswerBox placeholder="Gõ câu trả lời cho khách" onSend={(t) => button("", t)} />
        </div>
      );
    case "suggestion":
      return (
        <div className="card yellow">
          <div style={{ alignSelf: "center", width: 64, height: 64, borderRadius: 20, background: "#fff1d6", color: "#b45309", display: "grid", placeItems: "center" }}><Icon name="sparkle" size={34} /></div>
          <div style={{ fontSize: 22, lineHeight: 1.4 }}>{card.text}</div>
          <div className="row">
            <button className="btn yes" onClick={() => button(`growth:${card.suggestion_id}:accept`)}>Làm</button>
            <button className="btn" onClick={() => button(`growth:${card.suggestion_id}:later`)}>Để sau</button>
          </div>
          <button className="btn small ghost" onClick={() => button(`growth:${card.suggestion_id}:decline`)}>Không cần</button>
        </div>
      );
    case "stat":
      return (
        <div className={`tile stat ${STAT[card.text]?.[1] || "t2"}`}>
          <span className="ico"><Icon name={STAT[card.text]?.[0] || "box"} size={28} /></span>
          <span style={{ fontSize: 28 }}>{card.big}</span>
          <span style={{ color: "var(--muted)", fontSize: 18 }}>{card.text}</span>
          {card.visual && <MoneyVisual visual={card.visual} />}
          {card.detail && <span style={{ fontSize: 15, color: "var(--muted)" }}>{card.detail}</span>}
        </div>
      );
    case "warning":
      return (
        <div className="card red" role="alert">
          <div style={{ alignSelf: "center", color: "var(--bad)" }}><Icon name="alert" size={56} /></div>
          <div style={{ fontSize: 26, fontWeight: 900, textAlign: "center" }}>{card.text}</div>
          {card.detail && <div style={{ color: "var(--muted)", fontSize: 17 }}>“{card.detail}”</div>}
        </div>
      );
    case "published":
      return (
        <div className="card">
          <div style={{ alignSelf: "center", width: 76, height: 76, borderRadius: "50%", background: "var(--ok-soft)", color: "var(--ok)", display: "grid", placeItems: "center" }}><Icon name="check" size={44} stroke={3} /></div>
          <div className="label">{card.text}</div>
          {card.undo && <button className="btn" onClick={() => button("undo")}><Icon name="undo" /> Rút lại</button>}
        </div>
      );
    default:
      return card.text ? <div className="card"><div className="label">{card.text}</div></div> : null;
  }
}
