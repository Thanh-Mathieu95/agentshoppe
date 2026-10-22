import { useCallback, useEffect, useRef, useState } from "react";
import { Channel, type Card, type ClientMsg, type LiveListing, type LiveProfile, type Mode, type Purpose, type Seller, type ServerEvent, postJSON, setProfileId } from "./api";
import CameraCapture from "./components/CameraCapture";
import type { MicState } from "./components/BigMicButton";
import Icon, { Mark } from "./components/Icon";
import PhoneShell from "./components/PhoneShell";
import { RealtimeVoice, type RtState } from "./realtime";
import TouchMode from "./modes/TouchMode";
import VoiceOrb from "./components/VoiceOrb";
import Onboarding from "./modes/Onboarding";
import { canRecognize, canRecord, chime, listenOnce, recordOnce, speak, stopSpeaking, vibrate } from "./speech";

export type Pending = { confirm_id: string; subject_ref: string; two_step: boolean; risk: string } | null;

const CONFIRM_TIMEOUT_MS = 30000;

export default function SellerApp({ sellerId }: { sellerId: number }) {
  const [seller, setSeller] = useState<Seller | null>(null);
  const [mode, setMode] = useState<Mode>("voice");
  const [online, setOnline] = useState(false);
  const [caption, setCaption] = useState<{ text: string; confirm: boolean }>({ text: "", confirm: false });
  const [cards, setCards] = useState<Card[]>([]);
  const [pending, setPending] = useState<Pending>(null);
  const [camera, setCamera] = useState<{ purpose: Purpose; guide: string } | null>(null);
  const [toast, setToast] = useState<{ kind: string; text: string } | null>(null);
  const [mic, setMic] = useState<MicState>("idle");
  const [live, setLive] = useState<LiveProfile | null>(null);
  const [liveListing, setLiveListing] = useState<LiveListing | null>(null);
  const serverSttRef = useRef(false);

  const chan = useRef<Channel | null>(null);
  const modeRef = useRef<Mode>("voice");
  const speakQ = useRef<Promise<void>>(Promise.resolve());
  const promptDoneAt = useRef<number | null>(null);
  const pendingRef = useRef<Pending>(null);
  const timeoutTimer = useRef<number>(0);
  const listening = useRef<{ stop: () => void } | null>(null);
  const lastSpoken = useRef("");
  // Hội thoại thời gian thực: mic luôn mở, không cần bấm. Lỗi thì rơi về "nghe liên tục" bằng ghi âm.
  const rtRef = useRef<RealtimeVoice | null>(null);
  const [rtState, setRtState] = useState<RtState | null>(null);
  const handsFree = useRef(false);
  const rtBuf = useRef<string[]>([]);
  const rtFlush = useRef(0);
  const cameraRef = useRef(false);
  const [shutter, setShutter] = useState(0);

  modeRef.current = mode;
  pendingRef.current = pending;
  cameraRef.current = !!camera;
  const rtOn = () => !!rtRef.current && rtRef.current.state !== "error";


  const send = useCallback((msg: ClientMsg) => {
    clearTimeout(timeoutTimer.current);
    if (msg.type !== "timeout" && msg.type !== "image" && pendingRef.current && promptDoneAt.current) {
      (msg as any).latency_ms = Math.round(performance.now() - promptDoneAt.current);
    }
    if (msg.type !== "timeout") setMic("thinking");
    chan.current?.send(msg);
  }, []);

  const armTimeout = useCallback(() => {
    clearTimeout(timeoutTimer.current);
    timeoutTimer.current = window.setTimeout(() => {
      if (pendingRef.current) chan.current?.send({ type: "timeout" });
    }, CONFIRM_TIMEOUT_MS);
  }, []);

  /** Nghe một câu rồi gửi. Không có Web Speech -> ghi âm gửi server (nếu server có STT). */
  const listen = useCallback(async (maxMs = 8000): Promise<void> => {
    if (rtOn()) return;
    stopSpeaking();
    listening.current?.stop();
    chime("listen");
    setMic("listening");
    // Server có nhận dạng giọng (OpenAI) -> ghi âm gửi lên: có độ tin cậy từng từ, chạy trên mọi trình duyệt.
    if (canRecord && serverSttRef.current) {
      const r = recordOnce(maxMs + 1000);
      listening.current = r;
      const b64 = await r.promise;
      listening.current = null;
      if (b64) send({ type: "audio", data: b64 });
      else {
        setMic("idle");
        if (pendingRef.current) armTimeout();
        // nghe liên tục: im lặng thì nghe tiếp, không bắt người bán bấm
        if (handsFree.current && modeRef.current === "voice" && !cameraRef.current) setTimeout(() => listen(maxMs), 300);
      }
      return;
    }
    if (canRecognize) {
      const l = listenOnce(maxMs);
      listening.current = l;
      const h = await l.promise;
      listening.current = null;
      if (h && h.text.trim()) {
        send({ type: "text", text: h.text, confidence: h.confidence });
      } else {
        setMic("idle");
        if (pendingRef.current) armTimeout();
      }
      return;
    }
    setMic("idle");
  }, [send, armTimeout]);

  const onEvent = useCallback((e: ServerEvent) => {
    switch (e.type) {
      case "hello":
        setSeller(e.seller);
        setMode(e.seller.mode);
        serverSttRef.current = e.stt === "openai";
        break;
      case "speak": {
        lastSpoken.current = e.text;
        setCaption({ text: e.text, confirm: e.priority === "confirm" });
        const confirm = e.priority === "confirm";
        if (modeRef.current === "voice" && rtOn()) {
          // Thông báo / kết quả từ máy chủ (đơn mới, kiểm tra ảnh...) -> đưa vào cuộc trò chuyện để trợ lý báo lại
          rtBuf.current.push(e.text);
          clearTimeout(rtFlush.current);
          rtFlush.current = window.setTimeout(() => {
            const text = rtBuf.current.join(" ");
            rtBuf.current = [];
            const waiting = pendingRef.current
              ? " Đây là câu cần xác nhận: đọc nguyên văn, chờ người bán trả lời rồi gọi confirm." : "";
            rtRef.current?.notify(`Thông báo từ máy chủ, hãy nói lại cho người bán (chỉ nói nội dung): ${text}${waiting}`);
          }, 250);
          break;
        }
        speakQ.current = speakQ.current.then(async () => {
          if (modeRef.current === "voice") {
            setMic("speaking");
            await speak(e.text, { speed: e.speed, confirm, audio: e.audio });
          }
          promptDoneAt.current = performance.now();
        });
        speakQ.current.then(() => setMic((m) => (m === "speaking" ? "idle" : m)));
        break;
      }
      case "card":
        setCards((cs) => {
          const c = e.card;
          if (c.kind === "order") return [c, ...cs.filter((x) => !(x.kind === "order" && x.order_id === c.order_id) && x.kind !== "confirm" && x.kind !== "confirm_order" && x.kind !== "summary")].slice(0, 6);
          if (c.kind === "stat") return [...cs.filter((x) => x.kind === "stat"), c];
          return [c];
        });
        break;
      case "turn_end":
        setPending(e.pending);
        pendingRef.current = e.pending;
        if (rtOn()) break;   // mic thời gian thực luôn mở; hẹn giờ xác nhận chạy khi đọc xong (onSpoken)
        if (!e.pending) {
          speakQ.current.then(() => {
            setMic((m) => (m === "thinking" ? "idle" : m));
            // nghe liên tục (hoặc ít nhất sau câu hỏi): người khiếm thị không phải tìm nút
            if (modeRef.current === "voice" && !cameraRef.current && (handsFree.current || lastSpoken.current.trim().endsWith("?"))) listen(8000);
          });
          break;
        }
        // Mic tự mở 8 giây sau câu đọc lại (chế độ nói); 30 giây im lặng thì nhắc lại một lần.
        speakQ.current.then(() => {
          if (!pendingRef.current) return;
          armTimeout();
          if (modeRef.current === "voice") listen(8000);
          else setMic("idle");
        });
        break;
      case "open_camera":
        setCamera({ purpose: e.purpose, guide: e.guide });
        break;
      case "mode":
        setMode(e.mode);
        break;
      case "profile": {
        const { type: _, ...p } = e;
        setLive(p);
        setSeller((s) => (s ? { ...s, onboarded: p.onboarded } : s));
        try { new BroadcastChannel("bkrc-live").postMessage("profile"); } catch { /* trình duyệt cũ */ }
        if (p.onboarded) setTimeout(() => setLive((cur) => (cur === p ? null : cur)), 6000);   // lưu xong: thẻ lui đi, còn lại micro
        break;
      }
      case "listing_live": {
        const { type: _, ...l } = e;
        if (l.status === "cancelled") { setLiveListing(null); break; }
        setLiveListing(l);
        try { new BroadcastChannel("bkrc-live").postMessage("listing"); } catch { /* trình duyệt cũ */ }
        if (l.status !== "drafting" && l.status !== "ready") setTimeout(() => setLiveListing((cur) => (cur === l ? null : cur)), 8000);
        break;
      }
      case "notify":
        if (e.kind === "published") setLiveListing(null);
        vibrate(e.vibrate);
        chime(e.kind);
        setToast({ kind: e.kind, text: e.payload?.text || "" });
        setTimeout(() => setToast(null), 6000);
        if (e.kind === "new_order" && modeRef.current === "touch") vibrate([200, 100, 200]);
        break;
    }
  }, [armTimeout, listen]);

  useEffect(() => {
    const c = new Channel(`/ws/session/${sellerId}`, onEvent, setOnline);
    chan.current = c;
    return () => c.close();
  }, [sellerId, onEvent]);

  /** Lời người bán (bản ghi thật từ Realtime) -> backend. */
  const onHeard = useCallback((text: string) => {
    if (cameraRef.current && /chụp|chup/i.test(text)) {   // nói "chụp" khi camera đang mở
      setShutter((x) => x + 1);
      return;
    }
    if (/^(tạm dừng|dừng nghe|tạm nghỉ|nghỉ đã)/i.test(text.trim())) {
      setTimeout(() => rtRef.current?.setPaused(true), 3500);   // để trợ lý kịp chào
      return;
    }
    // bản ghi THẬT lời người bán: công cụ confirm ở backend chỉ tin nguồn này
    fetch(`/api/rt/heard/${sellerId}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text }) });
  }, [sellerId]);

  // Chế độ nói: tự mở hội thoại thời gian thực, tự chào và dẫn việc. Không có nút micro bắt buộc.
  useEffect(() => {
    if (mode !== "voice" || !online || !seller) return;
    let cancelled = false;
    const rt = new RealtimeVoice({
      onState: (st) => {
        setRtState(st);
        setMic(st === "hearing" ? "listening" : st === "listening" ? "listening" : st === "speaking" ? "speaking"
          : st === "thinking" ? "thinking" : st === "paused" ? "paused" : st === "blocked" ? "blocked" : "connecting");
      },
      onHeard,
      onSpoken: () => { promptDoneAt.current = performance.now(); if (pendingRef.current) armTimeout(); },
      onError: (m) => console.warn("realtime:", m),
    });
    rtRef.current = rt;
    if (import.meta.env.DEV) (window as any).__rt = rt;   // kiểm thử trên máy không có micro
    rt.start(sellerId, true)   // trợ lý tự mở lời theo trạng thái cửa hàng
      .catch((err) => {
        console.warn("realtime unavailable, fallback to hands-free recording:", err);
        if (cancelled) return;
        rt.stop();
        rtRef.current = null;
        setRtState(null);
        handsFree.current = true;
        chan.current?.send({ type: "button", value: "hello" });
      });
    return () => { cancelled = true; rt.stop(); if (rtRef.current === rt) rtRef.current = null; setRtState(null); };
  }, [mode, online, seller?.id, sellerId, onHeard, armTimeout]);

  const button = (value: string, text?: string) => {
    if (text) return send({ type: "text", text });
    if (!value) return;
    send({ type: "button", value });
  };

  const changeMode = (m: Mode) => postJSON(`/api/sellers/${sellerId}/preferences`, { mode: m }, "PATCH");

  const micPress = () => {
    const rt = rtRef.current;
    if (rt) {   // chạm = bắt đầu (nếu trình duyệt chặn âm thanh) / tạm dừng / nghe tiếp
      if (rt.state === "blocked") rt.unblock();
      else if (rt.state === "paused") { rt.setPaused(false); rt.notify("Người bán vừa chạm để nói tiếp. Hỏi ngắn xem cần giúp gì."); }
      else rt.setPaused(true);
      return;
    }
    if (mic === "listening") { listening.current?.stop(); return; }
    if (mic === "speaking") { stopSpeaking(); setMic("idle"); }
    listen(8000);
  };

  const status = !online ? "Đang kết nối…" : {
    idle: "Sẵn sàng", listening: "Đang nghe", thinking: "Đang xử lý", speaking: "Đang nói", paused: "Tạm dừng",
    connecting: "Đang mở hội thoại", blocked: "Chạm để bắt đầu",
  }[mic];
  const header = (
    <header className="appbar">
      <Mark size={46} />
      <div>
        <div className="nm">Bạn Bán Hàng</div>
        <div className="sub"><span className={`dot ${online ? "ok" : ""}`} />{status} · {seller ? `${seller.honorific} ${seller.name}` : ""}</div>
      </div>
      <div className="sp">
        <button className="icon-btn" onClick={() => changeMode(mode === "voice" ? "touch" : "voice")}
                aria-label={mode === "voice" ? "Đổi sang chế độ bấm" : "Đổi sang chế độ nói"}>
          <Icon name={mode === "voice" ? "hand" : "ear"} />
        </button>
        {window.self === window.top && (
          <button className="icon-btn" onClick={() => confirm("Đổi sang hồ sơ khác?") && setProfileId(null)} aria-label="Đổi hồ sơ">
            <Icon name="user" />
          </button>
        )}
      </div>
    </header>
  );

  return (
    <PhoneShell>
      {toast && <div className={`toast ${toast.kind}`} role="alert"><Icon name={toast.kind === "warning" ? "alert" : "bell"} />{toast.text || "Có thông báo mới"}</div>}
      {mode === "voice" ? (
        // Điện thoại chỉ là một chiếc micro: không chữ, không thẻ, không nút phụ.
        <VoiceOrb state={online ? mic : "connecting"} onPress={micPress} profile={live} listing={liveListing}
                  onText={() => postJSON(`/api/sellers/${sellerId}/preferences`, { mode_now: "touch" }, "PATCH")} />
      ) : seller && !seller.onboarded ? (
        <Onboarding presetMode="touch" />   // người khiếm thính: điền hồ sơ bằng chữ
      ) : (
        <TouchMode seller={seller} online={online} caption={caption} cards={cards} pending={pending} header={header}
                   send={send} button={button} />
      )}
      {camera && (
        <CameraCapture purpose={camera.purpose} guide={camera.guide} voice={mode === "voice" && !rtState} shutter={shutter}
                       onClose={() => setCamera(null)}
                       onImage={(id) => { setCamera(null); send({ type: "image", image_id: id, purpose: camera.purpose, realtime: rtOn() }); }} />
      )}
    </PhoneShell>
  );
}
