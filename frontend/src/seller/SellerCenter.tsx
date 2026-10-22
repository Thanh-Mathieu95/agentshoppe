import { useEffect, useState } from "react";
import { getJSON, postJSON, profileId, setProfileId } from "../api";
import DemoToggle from "../components/DemoToggle";
import QuickPublish from "./QuickPublish";
import Icon, { Mark, type IconName } from "../components/Icon";
import "../market/market.css";

type Center = {
  shop: { id: number; name: string; owner: string; avatar: string; region: string; followers: number; assistant: boolean; mode: string; guardian_required: boolean };
  profile: { onboarded: boolean; missing: string[]; fields: { key: string; label: string; required: boolean; value: string | null }[] };
  revenue_30d: number; orders_by_status: Record<string, number>; days: { date: string; orders: number; revenue: number }[];
  products: { published: number; drafting: number; low_stock: number }; waiting_questions: number; blocked_errors: number; views_7d: number;
};

const vnd = (v: number) => "₫" + (v || 0).toLocaleString("vi-VN");
const STATUS_CHIP: Record<string, string> = { new: "new", accepted: "info", packed: "info", shipped: "ok", delivered: "ok", cancelled: "bad" };
const LSTATUS: Record<string, [string, string]> = { published: ["Đang bán", "ok"], drafting: ["Đang soạn", ""], ready: ["Chờ xác nhận đăng", "new"], pending_publish: ["Chờ lên sàn", "new"], hidden: ["Đã ẩn", "bad"] };
const FSTATE: Record<string, string> = { confirmed: "✔", checked: "…", heard: "?", empty: "·" };
const TABS: [string, IconName, string][] = [["quick", "sparkle", "Đăng nhanh từ ảnh"], ["profile", "user", "Hồ sơ cửa hàng"],["home", "home", "Tổng quan"], ["orders", "box", "Đơn hàng"], ["products", "bag", "Sản phẩm"], ["chat", "chat", "Chat với khách"], ["assistant", "shield", "Trợ lý & an toàn"]];

function usePoll<T>(url: string, ms = 3000): T | null {
  const [d, setD] = useState<T | null>(null);
  useEffect(() => {
    let alive = true;
    const load = () => getJSON<T>(url).then((x) => alive && setD(x)).catch(() => {});
    load();
    const t = setInterval(load, ms);
    let bc: BroadcastChannel | null = null;
    try { bc = new BroadcastChannel("bkrc-live"); bc.onmessage = load; } catch { /* chỉ còn hỏi định kỳ */ }
    return () => { alive = false; clearInterval(t); bc?.close(); };
  }, [url, ms]);
  return d;
}

export default function SellerCenter({ sellerId }: { sellerId: number }) {
  const [tab, setTab] = useState<string>("profile");
  const c = usePoll<Center>(`/api/seller-center/${sellerId}`);
  const orders = usePoll<any[]>(`/api/orders?seller_id=${sellerId}`);
  const products = usePoll<any[]>(`/api/listings?seller_id=${sellerId}`, 4000);
  const msgs = usePoll<any[]>(`/api/messages?seller_id=${sellerId}`, 4000);
  const board = usePoll<any>(`/api/demo/board/${sellerId}`, 4000);
  const [ofilter, setOfilter] = useState("all");

  /** Thao tác đơn từ máy tính vẫn phải qua trợ lý: lệnh được đẩy sang điện thoại để người bán xác nhận. */
  const viaAssistant = (value: string) => {
    const fd = new FormData();
    fd.append("button", value);
    fetch(`/api/turn/${sellerId}`, { method: "POST", body: fd });
  };

  if (!c) return <div className="sc"><div className="top">Đang tải…</div></div>;
  const bs = c.orders_by_status;
  const maxRev = Math.max(1, ...c.days.map((d) => d.revenue));
  const olist = (orders || []).filter((o) => ofilter === "all" || o.status === ofilter);

  return (
    <div className="sc">
      <div className="top">
        <div className="brand"><Icon name="store" /> Kênh Người Bán <span>· {c.shop.avatar} {c.shop.name}</span></div>
        <div style={{ display: "flex", gap: 16, alignItems: "center" }}>
          <DemoToggle />
          {profileId() === null
            ? <button className="chip new" onClick={() => setProfileId(1)}>Dùng hồ sơ mẫu Cô Mai</button>
            : <button className="chip" onClick={() => setProfileId(null)}>Đổi hồ sơ</button>}
          {c.shop.assistant && <span className="ai-badge">Bạn Bán Hàng đang bật · chế độ {c.shop.mode === "voice" ? "Nghe – Nói" : "Nhìn – Chạm"}</span>}
          <a href="#/" style={{ color: "#ee4d2d" }}>Về sàn ›</a>
        </div>
      </div>

      <nav className="side" aria-label="Menu kênh người bán">
        {TABS.map(([k, ico, label]) => (
          <button key={k} className={tab === k ? "on" : ""} onClick={() => setTab(k)}>
            <Icon name={ico} size={20} />{label}
            {k === "orders" && bs.new ? <span className="count">{bs.new}</span> : null}
            {k === "chat" && c.waiting_questions ? <span className="count">{c.waiting_questions}</span> : null}
          </button>
        ))}
      </nav>

      <main>
        {tab === "quick" && <QuickPublish sellerId={sellerId} />}

        {tab === "profile" && (
          <div className="panel">
            <h3>Hồ sơ cửa hàng
              <span className={`chip ${c.profile.onboarded ? "ok" : "new"}`}>
                {c.profile.onboarded ? "✓ Người bán đã xác nhận" : `Đang điền qua trò chuyện · còn thiếu ${c.profile.missing.length}`}
              </span>
            </h3>
            <div style={{ color: "#888", fontSize: 13, marginBottom: 12 }}>Tự cập nhật khi người bán nói chuyện với trợ lý trên điện thoại.</div>
            <table>
              <tbody>
                {c.profile.fields.map((f) => (
                  <tr key={f.key + (f.value || "")} className={f.value ? "just-filled" : ""}>
                    <td style={{ width: 200, color: "#555" }}>{f.label}{f.required && <span style={{ color: "#ee4d2d" }}> *</span>}</td>
                    <td>{f.value ? <b>{f.value}</b> : <span style={{ color: "#bbb" }}>{f.required ? "chưa có" : "không bắt buộc"}</span>}</td>
                    <td style={{ width: 40, textAlign: "right" }}>{f.value ? <span style={{ color: "#0a8a55" }}>✓</span> : ""}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {tab === "home" && <>
          <div className="panel">
            <h3>Việc cần làm</h3>
            <div className="todo">
              <div><b>{bs.new || 0}</b>Chờ xác nhận</div>
              <div><b>{bs.accepted || 0}</b>Chờ đóng gói</div>
              <div><b>{bs.packed || 0}</b>Chờ gửi</div>
              <div><b>{c.waiting_questions}</b>Khách chờ trả lời</div>
            </div>
          </div>
          <div className="panel">
            <h3>Phân tích bán hàng <span style={{ fontSize: 12, color: "#999", fontWeight: 400 }}>30 ngày</span></h3>
            <div className="kpis">
              <div className="kpi"><div className="l">Tiền về (sau phí)</div><div className="v">{vnd(c.revenue_30d)}</div></div>
              <div className="kpi"><div className="l">Lượt xem 7 ngày</div><div className="v">{c.views_7d}</div></div>
              <div className="kpi"><div className="l">Sản phẩm đang bán</div><div className="v">{c.products.published}</div></div>
              <div className="kpi"><div className="l">Lỗi trợ lý đã chặn</div><div className="v" style={{ color: "#ee4d2d" }}>{c.blocked_errors}</div></div>
            </div>
            <div className="bars" aria-label="Tiền về 7 ngày">
              {c.days.map((d) => (
                <div key={d.date}><span>{d.revenue ? Math.round(d.revenue / 1000) + "k" : ""}</span>
                  <div className="b" style={{ height: `${(d.revenue / maxRev) * 100}%` }} />{d.date.slice(8)}/{d.date.slice(5, 7)}</div>
              ))}
            </div>
          </div>
          {c.products.low_stock > 0 && <div className="panel" style={{ borderLeft: "4px solid #ffb300" }}>⚠ {c.products.low_stock} sản phẩm sắp hết hàng. Trợ lý sẽ nhắc người bán trong bản tin cuối ngày.</div>}
        </>}

        {tab === "orders" && (
          <div className="panel">
            <h3>Đơn hàng
              <span style={{ display: "flex", gap: 6 }}>
                {[["all", "Tất cả"], ["new", "Chờ xác nhận"], ["accepted", "Chờ đóng gói"], ["packed", "Chờ gửi"], ["shipped", "Đang giao"]].map(([k, l]) => (
                  <button key={k} className={`chip ${ofilter === k ? "new" : ""}`} onClick={() => setOfilter(k)}>{l}</button>
                ))}
              </span>
            </h3>
            <div style={{ color: "#888", fontSize: 13, marginBottom: 10 }}>Nút thao tác gửi lệnh sang trợ lý trên điện thoại. Người bán vẫn phải tự xác nhận (đọc lại, giữ nút 1,5 giây hoặc nói cụm từ).</div>
            <table>
              <thead><tr><th>Mã đơn</th><th>Sản phẩm</th><th>Người mua</th><th>Tiền về</th><th>Hạn gửi</th><th>Trạng thái</th><th /></tr></thead>
              <tbody>
                {olist.map((o) => (
                  <tr key={o.order_id}>
                    <td>{o.external_id}</td>
                    <td>{o.items.map((i: any) => `${i.qty} × ${i.name}`).join(", ")}</td>
                    <td>{o.buyer}<div style={{ color: "#999", fontSize: 12 }}>{o.province}</div></td>
                    <td>{vnd(o.payout)}</td>
                    <td><span className={`chip ${o.urgency === "red" ? "bad" : o.urgency === "yellow" ? "new" : "ok"}`}>{o.deadline}</span></td>
                    <td><span className={`chip ${STATUS_CHIP[o.status] || ""}`}>{o.status_text}</span>{o.tracking && <div style={{ fontSize: 12, color: "#999" }}>{o.tracking}</div>}</td>
                    <td>
                      {o.status === "new" && <button className="chip new" onClick={() => viaAssistant(`order:${o.order_id}:accept`)}>Nhận qua trợ lý</button>}
                      {o.status === "accepted" && <button className="chip info" onClick={() => viaAssistant(`order:${o.order_id}:packing_check`)}>Kiểm tra hàng</button>}
                      {o.status === "packed" && <button className="chip info" onClick={() => viaAssistant(`order:${o.order_id}:receipt`)}>Chụp biên nhận</button>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {tab === "products" && (
          <div className="panel">
            <h3>Sản phẩm <span style={{ fontSize: 13, color: "#888", fontWeight: 400 }}>Thêm sản phẩm mới bằng giọng nói trên trợ lý →</span></h3>
            <table>
              <thead><tr><th /><th>Tên</th><th>Giá</th><th>Kho</th><th>Đã bán</th><th>Thông tin đã xác nhận</th><th>Trạng thái</th></tr></thead>
              <tbody>
                {(products || []).map((p) => {
                  const fs = Object.values(p.fields || {}) as any[];
                  const ok = fs.filter((f) => f.state === "confirmed").length;
                  const st = LSTATUS[p.status] || [p.status, ""];
                  return (
                    <tr key={p.id}>
                      <td>{p.image ? <img src={p.image} alt="" /> : <span style={{ fontSize: 30 }}>{p.icon}</span>}</td>
                      <td>{p.status === "published" ? <a href={`#/p/${p.id}`} style={{ color: "#2673dd" }}>{p.title}</a> : (p.title || "(chưa có tên)")}</td>
                      <td>{p.price ? vnd(p.price) : "—"}</td>
                      <td style={{ color: (p.stock ?? 0) <= 3 ? "#c62828" : undefined }}>{p.stock ?? "—"}</td>
                      <td>{p.sold}</td>
                      <td title={Object.entries(p.fields || {}).map(([k, f]: any) => `${k}: ${f.state}`).join("\n")}>
                        <span style={{ letterSpacing: 2 }}>{Object.values(p.fields || {}).map((f: any) => FSTATE[f.state]).join("")}</span> {ok}/{fs.length}
                      </td>
                      <td><span className={`chip ${st[1]}`}>{st[0]}</span></td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}

        {tab === "chat" && (
          <div className="panel">
            <h3>Chat với khách</h3>
            <table>
              <thead><tr><th>Khách</th><th>Câu hỏi</th><th>Trả lời</th><th>Trạng thái</th></tr></thead>
              <tbody>
                {(msgs || []).map((m) => (
                  <tr key={m.id}>
                    <td>{m.buyer}<div style={{ fontSize: 12, color: "#999" }}>{m.product}</div></td>
                    <td>{m.text}</td>
                    <td style={{ color: "#555" }}>{m.answer || "—"}</td>
                    <td><span className={`chip ${{ answered_auto: "ok", answered_seller: "ok", waiting_seller: "new", scam_flagged: "bad" }[m.status as string] || ""}`}>
                      {{ answered_auto: "Tự trả lời (có nguồn)", answered_seller: "Người bán trả lời", waiting_seller: "Chờ người bán", scam_flagged: "⚠ Nghi lừa đảo", new: "Mới" }[m.status as string]}
                    </span></td>
                  </tr>
                ))}
              </tbody>
            </table>
            {c.waiting_questions > 0 && <button className="chip new" style={{ marginTop: 12 }} onClick={() => viaAssistant("card:questions")}>Đọc câu hỏi cho người bán trên trợ lý</button>}
          </div>
        )}

        {tab === "assistant" && board && <>
          <div className="panel">
            <h3>5 lớp chống sai của Bạn Bán Hàng</h3>
            <table>
              <tbody>
                {board.blocked.by_layer.map((l: any) => <tr key={l.layer}><td style={{ width: 40 }}><b>L{l.layer}</b></td><td>{l.name}</td><td style={{ textAlign: "right" }}><b style={{ color: "#ee4d2d", fontSize: 18 }}>{l.count}</b></td></tr>)}
              </tbody>
            </table>
          </div>
          <div className="panel">
            <h3>Cài đặt trợ lý</h3>
            <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
              <button className={`chip ${c.shop.mode === "voice" ? "ok" : ""}`} onClick={() => postJSON(`/api/sellers/${sellerId}/preferences`, { mode: "voice" }, "PATCH")}>👂 Nghe – Nói</button>
              <button className={`chip ${c.shop.mode === "touch" ? "ok" : ""}`} onClick={() => postJSON(`/api/sellers/${sellerId}/preferences`, { mode: "touch" }, "PATCH")}>👆 Nhìn – Chạm</button>
              <button className={`chip ${c.shop.guardian_required ? "ok" : ""}`} onClick={() => postJSON(`/api/sellers/${sellerId}/preferences`, { guardian_required: !c.shop.guardian_required }, "PATCH")}>
                👥 Cần người bảo trợ duyệt: {c.shop.guardian_required ? "BẬT" : "TẮT"}
              </button>
              <a className="chip" href="#/guardian" target="_blank">Mở màn hình bảo trợ ›</a>
              <a className="chip" href="#/board" target="_blank">Mở bảng demo ›</a>
            </div>
            <p style={{ color: "#888", fontSize: 13 }}>Đổi chế độ cũng phải được người bán xác nhận trên điện thoại.</p>
          </div>
          <div className="panel">
            <h3>Lỗi đã chặn gần đây</h3>
            {board.blocked.recent.map((r: any, i: number) => <div key={i} style={{ fontSize: 13, padding: "4px 0", borderTop: "1px solid #f0f0f0" }}><b style={{ color: "#c62828" }}>L{r.layer} {r.code}</b> · {r.detail}</div>)}
          </div>
        </>}
      </main>

      <aside className="assistant" aria-label="Trợ lý Bạn Bán Hàng trên điện thoại người bán">
        <div className="ttl"><b style={{ display: "flex", gap: 8, alignItems: "center" }}><Mark size={28} /> Bạn Bán Hàng</b><span>điện thoại của {c.shop.owner}</span></div>
        <div className="phone"><iframe src="/#/app" title="Trợ lý Bạn Bán Hàng" allow="microphone; camera" /></div>
        <div className="feat">
          <span>• Nói “Cô muốn bán mật ong rừng ba trăm nghìn một chai”</span>
          <span>• Đơn mới từ sàn tự báo bằng giọng nói · nói “nhận đơn”</span>
          <span>• Chụp hàng trước khi gói để kiểm tra đúng đơn</span>
        </div>
      </aside>
    </div>
  );
}
