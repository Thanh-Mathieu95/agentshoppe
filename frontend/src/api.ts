export type Card = { kind: string; [k: string]: any };
export type LiveProfile = { onboarded: boolean; saved: string[]; missing: number;
  fields: { key: string; label: string; required: boolean; value: string | null }[] };
export type LiveListing = { listing_id: number; title: string; status: string; images: string[];
  fields: { key: string; label: string; required: boolean; value: string | null; state: string }[] };

export type ServerEvent =
  | { type: "hello"; seller: Seller; agent_mode: string; stt: string; tts: string }
  | { type: "speak"; text: string; priority?: "normal" | "confirm"; audio?: string; speed?: number }
  | { type: "card"; card: Card }
  | { type: "notify"; kind: string; payload: any; vibrate?: number[] }
  | { type: "open_camera"; purpose: Purpose; guide: string; ref_id?: number }
  | { type: "turn_end"; pending: { confirm_id: string; subject_ref: string; two_step: boolean; risk: string } | null }
  | { type: "mode"; mode: Mode }
  | ({ type: "profile" } & LiveProfile)
  | ({ type: "listing_live" } & LiveListing)
  | { type: "board_update"; payload: any };

export type Mode = "voice" | "touch";
export type Purpose = "listing" | "packing_check" | "receipt";
export type Seller = { id: number; name: string; mode: Mode; honorific: string; tts_speed: number; onboarded: boolean };

export type ClientMsg =
  | { type: "text"; text: string; confidence?: number | null; latency_ms?: number | null; realtime?: boolean }
  | { type: "audio"; data: string; latency_ms?: number | null }
  | { type: "button"; value: string; latency_ms?: number | null; realtime?: boolean }
  | { type: "image"; image_id: number; purpose: Purpose; realtime?: boolean }
  | { type: "timeout" };

function wsUrl(path: string) {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  return `${proto}://${location.host}${path}`;
}

/** WebSocket tự nối lại; gửi khi mất mạng sẽ được xếp hàng. */
export class Channel {
  private ws?: WebSocket;
  private queue: string[] = [];
  private closed = false;
  constructor(private path: string, private onEvent: (e: ServerEvent) => void, private onStatus?: (ok: boolean) => void) {
    this.open();
  }
  private open() {
    const ws = new WebSocket(wsUrl(this.path));
    this.ws = ws;
    ws.onopen = () => {
      this.onStatus?.(true);
      this.queue.splice(0).forEach((m) => ws.send(m));
    };
    ws.onmessage = (m) => this.onEvent(JSON.parse(m.data));
    ws.onclose = () => {
      this.onStatus?.(false);
      if (!this.closed) setTimeout(() => this.open(), 1200);
    };
  }
  send(msg: ClientMsg) {
    const s = JSON.stringify(msg);
    if (this.ws?.readyState === WebSocket.OPEN) this.ws.send(s);
    else this.queue.push(s);
  }
  close() {
    this.closed = true;
    this.ws?.close();
  }
}

export async function uploadImage(file: Blob | null, demoPhoto?: string): Promise<number> {
  const fd = new FormData();
  if (demoPhoto) fd.append("demo_photo", demoPhoto);
  else if (file) fd.append("file", file, "photo.jpg");
  const r = await fetch("/api/images", { method: "POST", body: fd });
  if (!r.ok) throw new Error("upload failed");
  return (await r.json()).image_id;
}

export async function getJSON<T = any>(url: string): Promise<T> {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`${r.status} ${url}`);
  return r.json();
}

export async function postJSON<T = any>(url: string, body: any = {}, method = "POST"): Promise<T> {
  const r = await fetch(url, { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  if (!r.ok) throw new Error(`${r.status} ${url}`);
  return r.json();
}

export const money = (v: number) => v.toLocaleString("vi-VN") + " đ";

/** Hồ sơ người bán đang dùng: ?seller= trên URL, nếu không thì lưu trong trình duyệt. */
const PROFILE_KEY = "bkrc.sellerId";
export function profileId(): number | null {
  const q = new URLSearchParams(location.search).get("seller");
  if (q) return Number(q);
  try { const v = localStorage.getItem(PROFILE_KEY); return v ? Number(v) : null; } catch { return null; }
}
export function setProfileId(id: number | null) {
  try { id ? localStorage.setItem(PROFILE_KEY, String(id)) : localStorage.removeItem(PROFILE_KEY); } catch { /* bỏ qua */ }
  window.dispatchEvent(new Event("bkrc-profile"));
}
