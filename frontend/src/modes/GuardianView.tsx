import { useEffect, useState } from "react";
import { getJSON, postJSON } from "../api";

type Approval = { id: number; subject_ref: string; summary: string; status: string; at: string; card?: any };

/** Người bảo trợ duyệt các hành động ĐỎ khi bật "cần bảo trợ". */
export default function GuardianView({ sellerId }: { sellerId: number }) {
  const [rows, setRows] = useState<Approval[]>([]);
  const [required, setRequired] = useState(false);
  const [name, setName] = useState("");

  const load = () => {
    getJSON<Approval[]>(`/api/guardian/${sellerId}`).then(setRows).catch(() => {});
    getJSON(`/api/sellers/${sellerId}`).then((s) => { setRequired(s.guardian_required); setName(s.name); }).catch(() => {});
  };
  useEffect(() => {
    load();
    const t = setInterval(load, 2500);
    return () => clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sellerId]);

  const decide = async (id: number, approve: boolean) => {
    await postJSON(`/api/guardian/approvals/${id}`, { approve });
    load();
  };
  const toggle = async () => {
    await postJSON(`/api/sellers/${sellerId}/preferences`, { guardian_required: !required }, "PATCH");
    load();
  };
  const waiting = rows.filter((r) => r.status === "waiting");

  return (
    <main className="app">
      <h1 style={{ margin: "8px 0 0" }}>👥 Người bảo trợ</h1>
      <div style={{ color: "var(--muted)", fontSize: 18 }}>Duyệt giúp {name}: đăng tin, nhận đơn, báo gửi, hủy đơn.</div>
      <button className={`btn ${required ? "yes" : ""}`} onClick={toggle} aria-pressed={required}>
        {required ? "✓ Đang bật: việc quan trọng cần tôi duyệt" : "Bật: việc quan trọng cần tôi duyệt"}
      </button>
      {waiting.length === 0 && <div className="card"><div className="label">Không có việc chờ duyệt.</div></div>}
      {waiting.map((r) => (
        <div key={r.id} className="card yellow">
          <span className="badge yellow">{r.subject_ref}</span>
          <div style={{ fontSize: 21, lineHeight: 1.45 }}>{r.summary}</div>
          {r.card?.big && <div className="big" style={{ fontSize: 44 }}>{r.card.big}</div>}
          <div className="row">
            <button className="btn yes" onClick={() => decide(r.id, true)}>Duyệt</button>
            <button className="btn no" onClick={() => decide(r.id, false)}>Từ chối</button>
          </div>
        </div>
      ))}
      {rows.filter((r) => r.status !== "waiting").slice(0, 6).map((r) => (
        <div key={r.id} style={{ color: "var(--muted)", fontSize: 15 }}>
          {r.status === "approved" ? "✓" : "✗"} {r.at} · {r.subject_ref}
        </div>
      ))}
    </main>
  );
}
