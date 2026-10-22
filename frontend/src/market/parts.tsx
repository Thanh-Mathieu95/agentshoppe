import { useState, type ReactNode } from "react";
import { go, soldText, useCart, vnd, type Product } from "./store";

export function Stars({ value }: { value: number }) {
  const full = Math.round(value);
  return <span className="stars" aria-label={`${value} sao`}>{"★".repeat(full)}{"☆".repeat(5 - full)}</span>;
}

export function ProductCard({ p }: { p: Product }) {
  return (
    <a className="pc" href={`#/p/${p.id}`}>
      <div className="im">
        {p.image ? <img src={p.image} alt={p.title} loading="lazy" /> : <div style={{ fontSize: 80, display: "grid", placeItems: "center", height: "100%" }}>{p.icon}</div>}
        {p.discount > 0 && <div className="off">{p.discount}%<br />GIẢM</div>}
        {p.shop.assistant && <div className="mall">Shop vùng cao</div>}
      </div>
      <div className="bd">
        <div className="nm">{p.title}</div>
        {p.shop.assistant && <span className="tag-ai" style={{ alignSelf: "flex-start" }}>Bạn Bán Hàng hỗ trợ</span>}
        <div className="prow">
          <span className="price"><small>₫</small>{p.price.toLocaleString("vi-VN")}</span>
          <span className="sold">Đã bán {soldText(p.sold)}</span>
        </div>
        <div className="loc"><span>{p.rating ? <Stars value={p.rating} /> : null}</span><span>{p.shop.region}</span></div>
      </div>
    </a>
  );
}

export function Grid({ items }: { items: Product[] }) {
  if (!items.length) return <div className="empty"><div className="e">🔍</div>Không tìm thấy sản phẩm nào.</div>;
  return <div className="grid">{items.map((p) => <ProductCard key={p.id} p={p} />)}</div>;
}

const HOT = ["mật ong rừng", "thịt trâu gác bếp", "chè shan tuyết", "khăn thổ cẩm", "nến thơm"];

export function MarketLayout({ children, q: q0 = "" }: { children: ReactNode; q?: string }) {
  const cart = useCart();
  const [q, setQ] = useState(q0);
  const count = cart.reduce((s, l) => s + l.qty, 0);
  return (
    <div className="mk">
      <header className="hd">
        <div className="wrap">
          <div className="hd-top">
            <div className="links">
              <a href="#/seller">Kênh Người Bán</a>
              <a href="#/app">Trợ lý Bạn Bán Hàng</a>
              <a href="#/board">Bảng demo</a>
            </div>
            <div className="links">
              <span>🔔 Thông báo</span>
              <a href="#/orders">📦 Đơn mua</a>
              <span>Môi trường giả lập · không phải Shopee thật</span>
            </div>
          </div>
          <div className="hd-main">
            <a className="logo" href="#/" aria-label="Trang chủ sàn giả lập">
              <span className="bag">S</span>Shopee<small>GIẢ LẬP</small>
            </a>
            <div style={{ flex: 1 }}>
              <form className="search" role="search" onSubmit={(e) => { e.preventDefault(); go(`/search?q=${encodeURIComponent(q.trim())}`); }}>
                <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Tìm đặc sản vùng cao: mật ong, chè, thổ cẩm…" aria-label="Tìm sản phẩm" />
                <button aria-label="Tìm">🔍</button>
              </form>
              <div className="hint-terms">{HOT.map((h) => <a key={h} href={`#/search?q=${encodeURIComponent(h)}`}>{h}</a>)}</div>
            </div>
            <a className="cart-ico" href="#/cart" aria-label={`Giỏ hàng, ${count} sản phẩm`}>🛒{count > 0 && <b>{count}</b>}</a>
          </div>
        </div>
      </header>
      <div className="wrap">{children}</div>
      <footer className="ft">
        <div className="wrap" style={{ display: "flex", justifyContent: "space-between", gap: 20, flexWrap: "wrap" }}>
          <div>© 2026 Bán Không Rào Cản · Sàn thương mại giả lập cho Sea × OpenAI Codex Hackathon.<br />Biểu phí, giá thị trường và đơn hàng đều là dữ liệu minh họa.</div>
          <div>Người bán vùng cao và người khuyết tật dùng trợ lý <b>Bạn Bán Hàng</b> để đăng hàng, nhận đơn, trả lời khách bằng giọng nói.</div>
        </div>
      </footer>
    </div>
  );
}

export function Price({ v }: { v: number }) { return <span className="price">{vnd(v)}</span>; }
