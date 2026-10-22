import { useEffect, useState } from "react";
import type { Card, ClientMsg, Seller } from "../api";
import CardView from "../components/CardView";
import Icon, { type IconName } from "../components/Icon";
import type { Pending } from "../SellerApp";

const HOME: { value: string; icon: IconName; label: string; cls: string }[] = [
  { value: "card:new_listing", icon: "bag", label: "Bán hàng mới", cls: "t1" },
  { value: "card:orders", icon: "box", label: "Đơn hàng", cls: "t2" },
  { value: "card:questions", icon: "chat", label: "Khách hỏi", cls: "t3" },
  { value: "card:today", icon: "sun", label: "Hôm nay", cls: "t4" },
];

/** Nhìn – Chạm: không âm thanh; thẻ chữ to; xác nhận bằng giữ nút 1,5 giây. */
export default function TouchMode(p: {
  seller: Seller | null; online: boolean; header: React.ReactNode; caption: { text: string; confirm: boolean };
  cards: Card[]; pending: Pending; send: (m: ClientMsg) => void; button: (v: string, t?: string) => void;
}) {
  const [home, setHome] = useState(true);
  const [typing, setTyping] = useState("");
  useEffect(() => { if (p.cards.length) setHome(false); }, [p.cards]);
  const stats = p.cards.filter((c) => c.kind === "stat");
  const others = p.cards.filter((c) => c.kind !== "stat");

  return (
    <main className="app">
      {p.header}
      <div className="convo">
        {p.caption.text && !home && (
          <div className={`bubble agent last ${p.caption.confirm ? "confirm" : ""}`} role="status">{p.caption.text}</div>
        )}
        {home ? (
          <>
            <div style={{ fontSize: 24, fontWeight: 800, margin: "6px 2px 2px" }}>Chào {p.seller?.honorific} {p.seller?.name?.split(" ").pop()}!</div>
            <div className="tiles">
              {HOME.map((h) => (
                <button key={h.value} className={`tile ${h.cls}`} onClick={() => { setHome(false); p.button(h.value); }}>
                  <span className="ico"><Icon name={h.icon} size={30} /></span>{h.label}
                </button>
              ))}
            </div>
          </>
        ) : (
          <>
            <button className="chip-btn" style={{ alignSelf: "flex-start" }} onClick={() => setHome(true)}><Icon name="home" size={20} />Về trang chính</button>
            {stats.length > 0 && <div className="tiles">{stats.map((c, i) => <CardView key={i} card={c} button={p.button} pending={!!p.pending} />)}</div>}
            {others.map((c, i) => <CardView key={`${c.kind}-${c.order_id ?? i}`} card={c} button={p.button} pending={!!p.pending} />)}
          </>
        )}
      </div>
      <form className="typebox typebox-wrap" onSubmit={(e) => { e.preventDefault(); if (typing.trim()) { p.send({ type: "text", text: typing.trim() }); setTyping(""); } }}>
        <input value={typing} onChange={(e) => setTyping(e.target.value)} placeholder="Gõ chữ…" aria-label="Gõ tin nhắn cho trợ lý" />
        <button className="btn primary" aria-label="Gửi"><Icon name="send" /></button>
      </form>
    </main>
  );
}
