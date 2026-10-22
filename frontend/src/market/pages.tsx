import { useEffect, useMemo, useState } from "react";
import { getJSON, postJSON } from "../api";
import { Grid, MarketLayout, Stars } from "./parts";
import { buyerKey, cartStore, go, saveBuyer, savedBuyer, soldText, useCart, vnd, type Product } from "./store";

type Cat = { key: string; label: string; icon: string; count: number };

function useFetch<T>(url: string | null, deps: unknown[] = [], pollMs = 0): [T | null, string | null, () => void] {
  const [data, setData] = useState<T | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [tick, setTick] = useState(0);
  useEffect(() => {
    if (!url) return;
    let alive = true;
    const load = () => getJSON<T>(url).then((d) => alive && (setData(d), setErr(null))).catch((e) => alive && setErr(e.message));
    load();
    const t = pollMs ? setInterval(load, pollMs) : 0;
    return () => { alive = false; if (t) clearInterval(t); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [url, tick, ...deps]);
  return [data, err, () => setTick((x) => x + 1)];
}

function Flash({ text }: { text: string | null }) {
  if (!text) return null;
  return <div className="toast-mk" role="status"><div className="e">✓</div>{text}</div>;
}

// ---------------- trang chủ ----------------
export function Home() {
  const [cats] = useFetch<Cat[]>("/mock/shopee/categories");
  const [items] = useFetch<Product[]>("/mock/shopee/catalog?sort=popular");
  const [fresh] = useFetch<Product[]>("/mock/shopee/catalog?sort=new");
  const assisted = (items || []).filter((p) => p.shop.assistant);
  return (
    <MarketLayout>
      <div className="hero">
        <div className="main">
          <h1>Đặc sản vùng cao, người bán tự đăng bằng giọng nói</h1>
          <p>Mỗi thông tin trên trang đều do người bán xác nhận lại. Trợ lý Bạn Bán Hàng không viết điều người bán không nói.</p>
          <div><a className="btn-w" href="#/search?q=">Mua ngay ›</a></div>
          <span className="big-ico" aria-hidden="true">🍯</span>
        </div>
        <div className="side">
          <div className="s1"><b>Miễn phí vận chuyển</b><span>Đơn đặc sản từ 300.000₫ (giả lập)</span></div>
          <div className="s2"><b>Shop vùng cao</b><span>Có trợ lý cho người khiếm thị, khiếm thính</span></div>
        </div>
      </div>

      <section className="section">
        <h2>Danh mục</h2>
        <div className="cats">
          {(cats || []).map((c) => (
            <a key={c.key} className="cat" href={`#/search?cat=${c.key}`}>
              <div className="ci" aria-hidden="true">{c.icon}</div><span>{c.label}</span>
            </a>
          ))}
        </div>
      </section>

      {assisted.length > 0 && (
        <section className="section">
          <div className="assist-strip">
            <span className="ico" aria-hidden="true">🎙️</span>
            <div>
              <b>Shop có Bạn Bán Hàng</b>
              <div style={{ color: "#555" }}>Người bán dùng giọng nói hoặc thẻ chạm. Câu trả lời cho khách chỉ lấy từ thông tin người bán đã xác nhận.</div>
            </div>
            <a href="#/app" className="btn-line" style={{ marginLeft: "auto" }}>Xem trợ lý</a>
          </div>
          <div style={{ padding: 14 }}><Grid items={assisted} /></div>
        </section>
      )}

      <section className="section">
        <h2>Bán chạy <a href="#/search?sort=popular">Xem tất cả ›</a></h2>
        <div style={{ padding: 14 }}><Grid items={(items || []).slice(0, 12)} /></div>
      </section>
      <section className="section">
        <h2>Mới đăng</h2>
        <div style={{ padding: 14 }}><Grid items={(fresh || []).slice(0, 6)} /></div>
      </section>
    </MarketLayout>
  );
}

// ---------------- tìm kiếm ----------------
const SORTS: [string, string][] = [["popular", "Phổ biến"], ["new", "Mới nhất"], ["rating", "Đánh giá"], ["price_asc", "Giá thấp → cao"], ["price_desc", "Giá cao → thấp"]];

export function Search({ params }: { params: URLSearchParams }) {
  const q = params.get("q") || "";
  const cat = params.get("cat") || "";
  const sort = params.get("sort") || "popular";
  const [cats] = useFetch<Cat[]>("/mock/shopee/categories");
  const [items] = useFetch<Product[]>(`/mock/shopee/catalog?${new URLSearchParams({ q, category: cat, sort })}`);
  const link = (o: Record<string, string>) => `#/search?${new URLSearchParams({ q, cat, sort, ...o })}`;
  return (
    <MarketLayout q={q}>
      <div className="page layout2">
        <aside className="filter" aria-label="Lọc theo danh mục">
          <b>☰ Danh mục</b>
          <a href={link({ cat: "" })} className={!cat ? "on" : ""}>Tất cả</a>
          {(cats || []).map((c) => <a key={c.key} href={link({ cat: c.key })} className={cat === c.key ? "on" : ""}>{c.icon} {c.label} ({c.count})</a>)}
        </aside>
        <div>
          {q && <div style={{ margin: "4px 0 12px", color: "#555" }}>Kết quả tìm kiếm cho “<b style={{ color: "#ee4d2d" }}>{q}</b>”</div>}
          <div className="sortbar">
            <span>Sắp xếp theo</span>
            {SORTS.map(([k, l]) => <button key={k} className={sort === k ? "on" : ""} onClick={() => (location.hash = link({ sort: k }))}>{l}</button>)}
          </div>
          <Grid items={items || []} />
        </div>
      </div>
    </MarketLayout>
  );
}

// ---------------- chi tiết ----------------
type Detail = Product & {
  description: string; specs: { label: string; value: string; key: string }[];
  reviews: { buyer: string; stars: number; text: string; at: string }[]; faqs: { q: string; a: string }[];
};
type Msg = { id: number; buyer: string; text: string; answer: string | null; status: string; by_assistant: boolean };

export function ProductPage({ id }: { id: number }) {
  const [p, err] = useFetch<Detail>(`/mock/shopee/products/${id}`);
  const [msgs, , reloadMsgs] = useFetch<Msg[]>(`/mock/shopee/messages?listing_id=${id}`, [], 3000);
  const [shopItems] = useFetch<{ products: Product[] }>(p ? `/mock/shopee/shops/${p.shop.id}` : null);
  const [img, setImg] = useState(0);
  const [qty, setQty] = useState(1);
  const [flash, setFlash] = useState<string | null>(null);
  const [ask, setAsk] = useState("");
  useEffect(() => { setImg(0); setQty(1); }, [id]);

  if (err) return <MarketLayout><div className="page"><div className="empty"><div className="e">😕</div>{err.includes("404") ? "Sản phẩm không còn bán." : err}</div></div></MarketLayout>;
  if (!p) return <MarketLayout><div className="page">Đang tải…</div></MarketLayout>;

  const add = (buy: boolean) => {
    cartStore.add(p, qty);
    if (buy) go("/cart");
    else { setFlash("Đã thêm vào giỏ hàng"); setTimeout(() => setFlash(null), 1400); }
  };
  const sendAsk = async () => {
    if (!ask.trim()) return;
    const b = savedBuyer();
    await postJSON("/mock/shopee/messages", { listing_id: p.id, text: ask.trim(), buyer_name: b.name || "Khách" });
    setAsk("");
    reloadMsgs();
  };

  return (
    <MarketLayout>
      <Flash text={flash} />
      <div className="page">
        <div style={{ color: "#555", marginBottom: 12, fontSize: 13 }}>
          <a href="#/">Trang chủ</a> › <a href={`#/search?cat=${p.category}`}>{p.icon} {p.category_label}</a> › {p.title}
        </div>
        <div className="pd">
          <div className="gal">
            {p.images.length ? <img src={p.images[img]} alt={p.title} /> : <div style={{ fontSize: 160, textAlign: "center" }}>{p.icon}</div>}
            {p.images.length > 1 && (
              <div className="thumbs">{p.images.map((u, i) => <img key={u} src={u} alt="" className={i === img ? "on" : ""} onClick={() => setImg(i)} />)}</div>
            )}
          </div>
          <div>
            <h1>{p.shop.assistant && <span className="tag-ai" style={{ marginRight: 8 }}>Shop vùng cao</span>}{p.title}</h1>
            <div className="meta">
              {p.rating > 0 && <><span style={{ color: "#ee4d2d", borderBottom: "1px solid #ee4d2d" }}>{p.rating.toFixed(1)}</span><Stars value={p.rating} /><span className="sep" /></>}
              <span><b>{p.reviews.length}</b> đánh giá</span><span className="sep" />
              <span><b>{soldText(p.sold)}</b> đã bán</span>
            </div>
            <div className="pricebox">
              {p.list_price && <s>{vnd(p.list_price)}</s>}
              <span className="now">{vnd(p.price)}</span>
              {p.discount > 0 && <span className="badge">{p.discount}% GIẢM</span>}
            </div>
            <div className="line"><span>Vận chuyển</span><span>🚚 Gửi từ <b>{p.shop.region}</b> · giao 3–5 ngày</span></div>
            {p.specs.slice(0, 2).map((s) => <div key={s.key} className="line"><span>{s.label}</span><span>{s.value}</span></div>)}
            <div className="line">
              <span>Số lượng</span>
              <span style={{ display: "flex", gap: 14, alignItems: "center" }}>
                <span className="qty">
                  <button onClick={() => setQty(Math.max(1, qty - 1))} aria-label="Bớt">−</button>
                  <input value={qty} inputMode="numeric" aria-label="Số lượng"
                         onChange={(e) => setQty(Math.max(1, Math.min(p.stock || 1, Number(e.target.value.replace(/\D/g, "")) || 1)))} />
                  <button onClick={() => setQty(Math.min(p.stock || 1, qty + 1))} aria-label="Thêm">+</button>
                </span>
                <span style={{ color: "#888" }}>{p.stock} sản phẩm có sẵn</span>
              </span>
            </div>
            <div className="btns">
              <button className="btn-line" onClick={() => add(false)} disabled={!p.stock}>🛒 Thêm vào giỏ hàng</button>
              <button className="btn-o" onClick={() => add(true)} disabled={!p.stock}>{p.stock ? "Mua ngay" : "Hết hàng"}</button>
            </div>
          </div>
        </div>

        <div className="shopbar">
          <div className="av" aria-hidden="true">{p.shop.avatar}</div>
          <div>
            <b style={{ fontSize: 16 }}>{p.shop.name}</b>
            <div style={{ color: "#888", fontSize: 13, marginTop: 4 }}>{p.shop.region}{p.shop.assistant && " · Người bán dùng trợ lý giọng nói"}</div>
            <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
              <a className="btn-g" href={`#/shop/${p.shop.id}`}>🏪 Xem shop</a>
            </div>
          </div>
          <div className="stats">
            <span>Sản phẩm <b>{p.shop.products}</b></span>
            <span>Người theo dõi <b>{soldText(p.shop.followers || 0)}</b></span>
          </div>
        </div>

        <div className="box">
          <h3>CHI TIẾT SẢN PHẨM {p.shop.assistant && <span className="verified">✔ Người bán đã xác nhận từng thông tin</span>}</h3>
          <dl className="specs">
            <dt>Danh mục</dt><dd>{p.icon} {p.category_label}</dd>
            {p.specs.map((s) => <FragmentSpec key={s.key} s={s} />)}
            <dt>Gửi từ</dt><dd>{p.shop.region}</dd>
          </dl>
          <h3 style={{ marginTop: 22 }}>MÔ TẢ SẢN PHẨM</h3>
          <div className="desc">{p.description}</div>
        </div>

        <div className="box">
          <h3>HỎI SHOP</h3>
          <div className="qa">
            {p.faqs.map((f, i) => <div key={`f${i}`}><div className="q">❓ {f.q}</div><div className="a">💬 {f.a}<span className="by">người bán đã duyệt</span></div></div>)}
            {(msgs || []).filter((m) => m.status !== "scam_flagged").map((m) => (
              <div key={m.id}>
                <div className="q">❓ {m.text} <span style={{ color: "#999", fontWeight: 400, fontSize: 12 }}>— {m.buyer}</span></div>
                {m.answer && <div className="a">💬 {m.answer}
                  {m.by_assistant && <span className="by">trả lời tự động từ dữ liệu đã xác nhận</span>}
                  {m.status === "waiting_seller" && <span className="by">đang chờ người bán</span>}
                  {m.status === "answered_seller" && <span className="by">người bán trả lời</span>}
                </div>}
              </div>
            ))}
            {!p.faqs.length && !(msgs || []).length && <div style={{ color: "#888" }}>Chưa có câu hỏi nào.</div>}
          </div>
          <form className="ask" onSubmit={(e) => { e.preventDefault(); sendAsk(); }}>
            <input value={ask} onChange={(e) => setAsk(e.target.value)} placeholder="Hỏi người bán về sản phẩm này…" aria-label="Câu hỏi cho shop" maxLength={500} />
            <button className="btn-o" style={{ minWidth: 100, height: 42 }}>Gửi</button>
          </form>
        </div>

        <div className="box">
          <h3>ĐÁNH GIÁ SẢN PHẨM</h3>
          {p.reviews.length === 0 && <div style={{ color: "#888", padding: "0 14px" }}>Chưa có đánh giá.</div>}
          {p.reviews.map((r, i) => (
            <div className="review" key={i}>
              <div className="av">{r.buyer[0]}</div>
              <div><div style={{ fontSize: 13 }}>{r.buyer}</div><Stars value={r.stars} /><div style={{ color: "#999", fontSize: 12 }}>{r.at}</div>
                <div style={{ marginTop: 6 }}>{r.text}</div></div>
            </div>
          ))}
        </div>

        {shopItems && shopItems.products.length > 1 && (
          <section className="section"><h2>Sản phẩm khác của shop</h2>
            <div style={{ padding: 14 }}><Grid items={shopItems.products.filter((x) => x.id !== p.id)} /></div></section>
        )}
      </div>
    </MarketLayout>
  );
}

function FragmentSpec({ s }: { s: { label: string; value: string } }) {
  return <><dt>{s.label}</dt><dd>{s.value}</dd></>;
}

// ---------------- giỏ hàng ----------------
export function CartPage() {
  const cart = useCart();
  const groups = useMemo(() => {
    const m = new Map<number, typeof cart>();
    cart.forEach((l) => m.set(l.shop.id, [...(m.get(l.shop.id) || []), l]));
    return [...m.values()];
  }, [cart]);
  const total = cart.reduce((s, l) => s + l.price * l.qty, 0);
  return (
    <MarketLayout>
      <div className="page">
        <h2 style={{ margin: "0 0 14px", fontWeight: 500, color: "#ee4d2d" }}>🛒 Giỏ hàng</h2>
        {!cart.length ? (
          <div className="empty"><div className="e">🛒</div><p>Giỏ hàng của bạn còn trống</p><a className="btn-o" href="#/">Mua ngay</a></div>
        ) : (
          <>
            <div className="cart-head"><span /><span>Sản phẩm</span><span>Đơn giá</span><span>Số lượng</span><span>Số tiền</span><span /></div>
            {groups.map((g) => (
              <div key={g[0].shop.id} style={{ marginBottom: 12 }}>
                <div className="cart-shop">{g[0].shop.avatar} {g[0].shop.name}{g[0].shop.assistant && <span className="tag-ai">Bạn Bán Hàng</span>}</div>
                {g.map((l) => (
                  <div key={l.id} className="cart-row">
                    <a href={`#/p/${l.id}`}>{l.image && <img src={l.image} alt="" />}</a>
                    <a href={`#/p/${l.id}`}>{l.title}</a>
                    <span>{vnd(l.price)}</span>
                    <span className="qty">
                      <button onClick={() => cartStore.setQty(l.id, l.qty - 1)} aria-label="Bớt">−</button>
                      <input value={l.qty} aria-label="Số lượng" inputMode="numeric" onChange={(e) => cartStore.setQty(l.id, Number(e.target.value.replace(/\D/g, "")) || 1)} />
                      <button onClick={() => cartStore.setQty(l.id, l.qty + 1)} aria-label="Thêm">+</button>
                    </span>
                    <span className="price">{vnd(l.price * l.qty)}</span>
                    <button onClick={() => cartStore.remove(l.id)} style={{ color: "#ee4d2d" }}>Xóa</button>
                  </div>
                ))}
              </div>
            ))}
            <div className="sum-bar">
              <span>Tổng thanh toán ({cart.reduce((s, l) => s + l.qty, 0)} sản phẩm):</span>
              <span className="total">{vnd(total)}</span>
              <a className="btn-o" href="#/checkout">Mua hàng</a>
            </div>
          </>
        )}
      </div>
    </MarketLayout>
  );
}

// ---------------- thanh toán ----------------
const PROVINCES = ["Hà Nội", "TP. Hồ Chí Minh", "Đà Nẵng", "Hải Phòng", "Cần Thơ", "Huế", "Hà Giang", "Lào Cai", "Sơn La", "Thái Nguyên", "Lâm Đồng", "Đắk Lắk", "Nghệ An", "Quảng Ninh"];

export function CheckoutPage() {
  const cart = useCart();
  const [f, setF] = useState(savedBuyer());
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const total = cart.reduce((s, l) => s + l.price * l.qty, 0);
  const ship = total >= 300000 ? 0 : 30000;
  const valid = f.name.trim().length >= 2 && /^0\d{8,10}$/.test(f.phone.trim()) && f.address.trim().length >= 3;

  const place = async () => {
    setErr(null);
    setBusy(true);
    try {
      saveBuyer(f);
      const r = await fetch("/mock/shopee/checkout", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ buyer_key: buyerKey(), buyer_name: f.name.trim(), phone: f.phone.trim(), province: f.province,
                               address: f.address.trim(), items: cart.map((l) => ({ listing_id: l.id, qty: l.qty })) }),
      });
      const j = await r.json();
      if (!r.ok) throw new Error(j.detail?.[0]?.msg || j.detail || "Đặt hàng thất bại");
      cartStore.removeMany(cart.map((l) => l.id));
      go(`/orders?placed=${j.order_ids.length}`);
    } catch (e: any) {
      setErr(String(e.message));
    } finally {
      setBusy(false);
    }
  };

  if (!cart.length) return <MarketLayout><div className="page"><div className="empty"><div className="e">🧾</div>Không có sản phẩm để thanh toán. <a href="#/" style={{ color: "#ee4d2d" }}>Về trang chủ</a></div></div></MarketLayout>;

  return (
    <MarketLayout>
      <div className="page">
        <h2 style={{ margin: "0 0 14px", fontWeight: 500, color: "#ee4d2d" }}>Thanh toán</h2>
        <div className="box" style={{ padding: 0 }}>
          <div className="addr-line" />
          <div style={{ padding: "20px 24px" }}>
            <div style={{ color: "#ee4d2d", fontSize: 17, marginBottom: 14 }}>📍 Địa chỉ nhận hàng</div>
            <div className="form">
              <label>Họ tên<input value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} autoComplete="name" /></label>
              <label>Số điện thoại<input value={f.phone} onChange={(e) => setF({ ...f, phone: e.target.value })} inputMode="tel" placeholder="09xxxxxxxx" /></label>
              <label>Tỉnh / Thành phố<select value={f.province} onChange={(e) => setF({ ...f, province: e.target.value })}>{PROVINCES.map((p) => <option key={p}>{p}</option>)}</select></label>
              <label>Địa chỉ cụ thể<input value={f.address} onChange={(e) => setF({ ...f, address: e.target.value })} placeholder="Số nhà, đường, phường…" /></label>
            </div>
          </div>
        </div>
        <div className="box">
          <div style={{ fontSize: 17, marginBottom: 10 }}>Sản phẩm</div>
          {cart.map((l) => (
            <div key={l.id} style={{ display: "grid", gridTemplateColumns: "56px 1fr 110px 60px 120px", gap: 14, alignItems: "center", padding: "10px 0", borderTop: "1px solid #f0f0f0" }}>
              {l.image ? <img src={l.image} alt="" style={{ width: 52, height: 52, objectFit: "cover" }} /> : <span />}
              <span>{l.title}<div style={{ color: "#888", fontSize: 12 }}>{l.shop.name}</div></span>
              <span>{vnd(l.price)}</span><span>×{l.qty}</span><span style={{ textAlign: "right" }}>{vnd(l.price * l.qty)}</span>
            </div>
          ))}
        </div>
        <div className="box">
          <div style={{ display: "flex", justifyContent: "space-between", flexWrap: "wrap", gap: 10 }}>
            <span style={{ fontSize: 17 }}>Phương thức thanh toán</span>
            <span><b>Thanh toán khi nhận hàng (COD)</b> <span style={{ color: "#888" }}>· giả lập, không thu tiền thật</span></span>
          </div>
          <div style={{ display: "grid", justifyContent: "end", gap: 8, marginTop: 18, gridTemplateColumns: "auto 160px", textAlign: "right" }}>
            <span style={{ color: "#888" }}>Tổng tiền hàng</span><span>{vnd(total)}</span>
            <span style={{ color: "#888" }}>Phí vận chuyển</span><span>{ship ? vnd(ship) : "Miễn phí"}</span>
            <span style={{ color: "#888" }}>Tổng thanh toán</span><span className="price" style={{ fontSize: 26 }}>{vnd(total + ship)}</span>
          </div>
          {err && <div className="err" style={{ marginTop: 14 }}>{err}</div>}
          <div style={{ display: "flex", justifyContent: "flex-end", marginTop: 18, gap: 12, alignItems: "center" }}>
            {!valid && <span style={{ color: "#888" }}>Điền họ tên, số điện thoại (bắt đầu bằng 0) và địa chỉ</span>}
            <button className="btn-o" onClick={place} disabled={!valid || busy}>{busy ? "Đang đặt…" : "Đặt hàng"}</button>
          </div>
        </div>
      </div>
    </MarketLayout>
  );
}

// ---------------- đơn mua ----------------
type BuyerOrder = { id: number; code: string; status: string; status_text: string; step: number; shop: Product["shop"]; items: (Product & { qty: number })[]; total: number; tracking: string | null; created_at: string; cancel_reason: string | null };
const TABS: [string, string][] = [["all", "Tất cả"], ["new", "Chờ xác nhận"], ["accepted", "Chờ lấy hàng"], ["shipped", "Đang giao"], ["delivered", "Đã giao"], ["cancelled", "Đã hủy"]];
const STEP_ICON = ["🧾", "✅", "📦", "🚚", "⭐"];
const STEP_TEXT = ["Đã đặt", "Shop đã nhận", "Đã đóng gói", "Đang giao", "Đã giao"];

export function OrdersPage({ params }: { params: URLSearchParams }) {
  const [rows] = useFetch<BuyerOrder[]>(`/mock/shopee/buyer/orders?buyer_key=${buyerKey()}`, [], 3000);
  const [tab, setTab] = useState("all");
  const placed = params.get("placed");
  const list = (rows || []).filter((o) => tab === "all" || o.status === tab || (tab === "accepted" && o.status === "packed"));
  return (
    <MarketLayout>
      <div className="page">
        {placed && <div className="box" style={{ borderLeft: "4px solid #00a86b" }}>✅ Đặt hàng thành công ({placed} đơn). Trang này tự cập nhật khi người bán xử lý đơn — thử mở <a href="#/app" style={{ color: "#ee4d2d" }}>trợ lý của người bán</a> và nói “nhận đơn”.</div>}
        <div className="tabs" role="tablist">{TABS.map(([k, l]) => <button key={k} role="tab" aria-selected={tab === k} className={tab === k ? "on" : ""} onClick={() => setTab(k)}>{l}</button>)}</div>
        {!list.length && <div className="empty"><div className="e">📦</div>Chưa có đơn hàng</div>}
        {list.map((o) => (
          <div className="ord" key={o.id}>
            <div className="top">
              <span>{o.shop?.avatar} <b>{o.shop?.name}</b> {o.shop?.assistant && <span className="tag-ai">Bạn Bán Hàng</span>}</span>
              <span style={{ color: "#888" }}>Mã đơn {o.code} · <span className="st">{o.status_text}</span></span>
            </div>
            {o.status !== "cancelled" && (
              <div className="steps" aria-label={`Tiến trình: ${o.status_text}`}>
                {STEP_TEXT.map((t, i) => <div key={t} className={i <= o.step ? "done" : ""}><div className="dot">{STEP_ICON[i]}</div>{t}</div>)}
              </div>
            )}
            {o.items.map((it) => (
              <a className="it" key={it.id} href={`#/p/${it.id}`}>
                {it.image && <img src={it.image} alt="" />}
                <div style={{ flex: 1 }}>{it.title}<div style={{ color: "#888" }}>x{it.qty}</div></div>
                <span className="price">{vnd(it.price)}</span>
              </a>
            ))}
            <div className="foot">
              {o.tracking && <span style={{ color: "#555", marginRight: "auto" }}>📮 Mã vận đơn: <b>{o.tracking}</b></span>}
              {o.cancel_reason && <span style={{ color: "#d0011b", marginRight: "auto" }}>Lý do hủy: {o.cancel_reason}</span>}
              <span>Thành tiền: <span className="price" style={{ fontSize: 20 }}>{vnd(o.total)}</span></span>
            </div>
          </div>
        ))}
      </div>
    </MarketLayout>
  );
}

// ---------------- trang shop ----------------
export function ShopPage({ id }: { id: number }) {
  const [s] = useFetch<{ name: string; owner: string; region: string; avatar: string; followers: number; assistant: boolean;
    rating: number | null; intro: string | null; color: string | null; banner: string | null; products: Product[] }>(`/mock/shopee/shops/${id}`);
  if (!s) return <MarketLayout><div className="page">Đang tải…</div></MarketLayout>;
  const bg = s.color ? `linear-gradient(90deg,${s.color},${s.color}cc)` : "linear-gradient(90deg,#3a2b23,#6b4a36)";
  return (
    <MarketLayout>
      <div className="page">
        {s.banner && <img className="shop-banner" src={s.banner} alt={`Ảnh bìa gian hàng ${s.name}`} />}
        {s.intro && <p className="shop-intro" style={{ borderColor: s.color || "#ee4d2d" }}>{s.intro}</p>}
        <div className="shopbar" style={{ background: bg, color: "#fff" }}>
          <div className="av">{s.avatar}</div>
          <div>
            <b style={{ fontSize: 20 }}>{s.name}</b>
            <div style={{ opacity: .85, marginTop: 4 }}>Chủ shop: {s.owner} · {s.region}</div>
            {s.assistant && <div style={{ marginTop: 8 }}><span className="tag-ai">Người bán dùng trợ lý giọng nói Bạn Bán Hàng</span></div>}
          </div>
          <div className="stats" style={{ color: "#fff" }}>
            <span>Sản phẩm <b style={{ color: "#ffb199" }}>{s.products.length}</b></span>
            <span>Người theo dõi <b style={{ color: "#ffb199" }}>{soldText(s.followers)}</b></span>
            {s.rating && <span>Đánh giá <b style={{ color: "#ffb199" }}>{s.rating} ★</b></span>}
          </div>
        </div>
        <Grid items={s.products} />
      </div>
    </MarketLayout>
  );
}
