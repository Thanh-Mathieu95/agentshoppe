import Icon from "./Icon";
import type { MicState } from "./BigMicButton";
import type { LiveListing, LiveProfile } from "../api";

const SR: Record<MicState, string> = {
  idle: "Chạm để nói",
  listening: "Tôi đang nghe, cứ nói tự nhiên",
  thinking: "Đang nghĩ",
  speaking: "Đang nói, có thể nói chen vào",
  paused: "Đã tạm dừng, chạm để nói tiếp",
  connecting: "Đang kết nối",
  blocked: "Chạm vào màn hình để bắt đầu",
};

type Row = { key: string; label: string; value: string | null; mark: "ok" | "wait" | "" ; fresh: boolean };

/** Thẻ tự điền: mỗi thông tin trợ lý nghe được / AI đọc từ ảnh hiện ra ngay. */
function LiveCard({ title, done, total, finished, rows, images }: {
  title: string; done: number; total: number; finished: boolean; rows: Row[]; images?: string[];
}) {
  return (
    <section className="live-card" aria-hidden="true">
      <div className="lc-head">
        <b>{title}</b>
        <span>{finished ? <Icon name="check" size={18} /> : `${done}/${total}`}</span>
      </div>
      <div className="lc-bar"><i style={{ width: `${(done / Math.max(1, total)) * 100}%` }} /></div>
      {images && images.length > 0 && (
        <div className="lc-imgs">{images.map((u) => <img key={u} src={u} alt="" />)}</div>
      )}
      <div className="lc-rows">
        {rows.map((r) => (
          <div key={r.key + (r.value || "")} className={`lc-row ${r.value ? "on" : ""} ${r.fresh ? "new" : ""}`}>
            <span>{r.label}</span>
            <b>{r.value || "…"}{r.mark === "ok" && <i className="lc-ok">✓</i>}{r.mark === "wait" && <i className="lc-wait">chờ xác nhận</i>}</b>
          </div>
        ))}
      </div>
    </section>
  );
}

function profileCard(p: LiveProfile) {
  const req = p.fields.filter((f) => f.required);
  return <LiveCard title={p.onboarded ? "Hồ sơ đã lưu" : "Hồ sơ cửa hàng"} finished={p.onboarded}
    done={req.filter((f) => f.value).length} total={req.length}
    rows={p.fields.filter((f) => f.value || f.required).map((f) => ({ key: f.key, label: f.label, value: f.value, mark: "", fresh: p.saved.includes(f.key) }))} />;
}

function listingCard(l: LiveListing) {
  const req = l.fields.filter((f) => f.required);
  const live = l.status === "drafting" || l.status === "ready";
  return <LiveCard title={live ? l.title || "Sản phẩm mới" : "Đã gửi đăng"} finished={!live} images={l.images}
    done={req.filter((f) => f.state === "confirmed").length} total={req.length}
    rows={l.fields.filter((f) => f.value || f.required).map((f) => ({
      key: f.key, label: f.label, value: f.value, fresh: !!f.value && f.state !== "confirmed",
      mark: f.state === "confirmed" ? "ok" : f.value ? "wait" : "",
    }))} />;
}

/** Điện thoại chỉ là một chiếc micro: cả màn hình là một nút, giữa là vòng tròn đổi theo trạng thái. */
export default function VoiceOrb({ state, onPress, onText, profile, listing }: {
  state: MicState; onPress: () => void; onText?: () => void; profile?: LiveProfile | null; listing?: LiveListing | null;
}) {
  const card = listing ? listingCard(listing) : profile ? profileCard(profile) : null;
  return (
    <div className={`orb-screen ${card ? "with-card" : ""}`}>
      <button className={`orb-area ${state}`} onClick={onPress} aria-label={SR[state]} autoFocus>
        <span className="orb">
          <span className="ring r1" /><span className="ring r2" /><span className="ring r3" />
          <span className="core"><Icon name="mic" size={64} stroke={2} /></span>
        </span>
        <span className="sr-only" aria-live="polite">{SR[state]}</span>
      </button>
      {card}
      {onText && (
        <button className="orb-text" onClick={onText} aria-label="Tôi không nghe được, dùng bằng chữ">
          Dùng bằng chữ
        </button>
      )}
    </div>
  );
}
