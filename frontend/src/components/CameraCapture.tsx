import { useEffect, useRef, useState } from "react";
import { getJSON, uploadImage, type Purpose } from "../api";
import { canRecognize, chime, listenOnce, vibrate } from "../speech";
import Icon from "./Icon";

type DemoPhoto = { name: string; label: string; url: string };
type Phase = "aim" | "count" | "review";

const PURPOSE_LABEL: Record<Purpose, string> = { listing: "Ảnh sản phẩm", packing_check: "Kiểm tra hàng", receipt: "Biên nhận" };

/** Tiếng màn trập ngắn (không cần file âm thanh). */
function shutterSound() {
  try {
    const ctx = new AudioContext();
    const len = ctx.sampleRate * 0.09;
    const buf = ctx.createBuffer(1, len, ctx.sampleRate);
    const d = buf.getChannelData(0);
    for (let i = 0; i < len; i++) d[i] = (Math.random() * 2 - 1) * Math.pow(1 - i / len, 3);
    const src = ctx.createBufferSource();
    src.buffer = buf;
    src.connect(ctx.destination);
    src.start();
    src.onended = () => ctx.close();
  } catch { /* không có âm thanh */ }
}

/** Màn hình chụp: khung căn 4 góc, nút chụp tròn, chớp sáng + tiếng màn trập, xem lại ảnh trong lúc gửi.
 *  Lệnh "chụp" bằng giọng nói: đếm ngược 3-2-1 có tiếng bíp để người khiếm thị kịp giữ máy yên. */
export default function CameraCapture({ purpose, guide, voice, shutter = 0, onImage, onClose }: {
  purpose: Purpose; guide: string; voice: boolean; shutter?: number;
  onImage: (imageId: number) => void; onClose: () => void;
}) {
  const video = useRef<HTMLVideoElement>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const [live, setLive] = useState<boolean | null>(null);
  const [phase, setPhase] = useState<Phase>("aim");
  const [count, setCount] = useState(0);
  const [flash, setFlash] = useState(false);
  const [preview, setPreview] = useState<string | null>(null);
  const [demo, setDemo] = useState<DemoPhoto[]>([]);
  const [showDemo, setShowDemo] = useState(false);
  const busy = useRef(false);
  const firstShutter = useRef(shutter);

  useEffect(() => {
    let stream: MediaStream | null = null;
    navigator.mediaDevices?.getUserMedia({ video: { facingMode: "environment", width: { ideal: 1280 } }, audio: false })
      .then((s) => {
        stream = s;
        if (video.current) video.current.srcObject = s;
        setLive(true);
      })
      .catch(() => { setLive(false); setShowDemo(true); });
    getJSON<DemoPhoto[]>("/api/demo/photos").then(setDemo).catch(() => {});
    return () => stream?.getTracks().forEach((t) => t.stop());
  }, []);

  // lệnh "chụp" từ hội thoại thời gian thực -> đếm ngược
  useEffect(() => {
    if (shutter !== firstShutter.current) countdown();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [shutter]);

  // không có hội thoại thời gian thực: tự nghe chữ "chụp"
  useEffect(() => {
    if (!voice || !canRecognize || !live) return;
    let alive = true;
    let stop = () => {};
    (async () => {
      while (alive) {
        const l = listenOnce(6000);
        stop = l.stop;
        const h = await l.promise;
        if (!alive) break;
        if (h && /chụp|chup/i.test(h.text)) { countdown(); break; }
      }
    })();
    return () => { alive = false; stop(); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [voice, live]);

  async function countdown() {
    if (busy.current || phase !== "aim") return;
    busy.current = true;
    setPhase("count");
    for (let n = 3; n >= 1; n--) {
      setCount(n);
      chime("listen");
      await new Promise((r) => setTimeout(r, 800));
    }
    busy.current = false;
    await shoot();
  }

  async function send(blob: Blob | null, demoName?: string, previewUrl?: string) {
    if (busy.current) return;
    busy.current = true;
    setPreview(previewUrl || (blob ? URL.createObjectURL(blob) : null));
    setPhase("review");
    try {
      const id = await uploadImage(blob, demoName);
      chime("ok");
      onImage(id);
    } catch {
      setPhase("aim");
      setPreview(null);
    } finally {
      busy.current = false;
    }
  }

  async function shoot() {
    const v = video.current;
    if (!live || !v || !v.videoWidth) { fileInput.current?.click(); setPhase("aim"); return; }
    setFlash(true);
    shutterSound();
    vibrate([40]);
    setTimeout(() => setFlash(false), 280);
    const c = document.createElement("canvas");
    c.width = v.videoWidth;
    c.height = v.videoHeight;
    c.getContext("2d")!.drawImage(v, 0, 0);
    const blob: Blob | null = await new Promise((r) => c.toBlob(r, "image/jpeg", 0.9));
    await send(blob);
  }

  return (
    <div className="cam" role="dialog" aria-label={`Camera: ${PURPOSE_LABEL[purpose]}`}>
      <video ref={video} autoPlay playsInline muted className={live ? "" : "hidden"} />
      {live === false && !preview && (
        <div className="cam-empty"><Icon name="camera" size={40} /><span>Không mở được camera trên máy này</span></div>
      )}
      {preview && <img className="cam-preview" src={preview} alt="Ảnh vừa chụp" />}

      <div className="cam-top">
        <button className="cam-round" onClick={onClose} aria-label="Đóng camera"><Icon name="x" /></button>
        <span className="cam-pill">{PURPOSE_LABEL[purpose]}</span>
        <span style={{ width: 44 }} />
      </div>

      {phase !== "review" && (
        <>
          <div className="cam-frame" aria-hidden="true"><i /><i /><i /><i /></div>
          <div className="cam-guide" aria-live="assertive">{guide}{voice ? " · nói “chụp”" : ""}</div>
        </>
      )}
      {phase === "count" && <div className="cam-count" aria-live="assertive">{count}</div>}
      {phase === "review" && (
        <div className="cam-sending" aria-live="polite"><span className="spin" />Đang kiểm tra ảnh…</div>
      )}
      {flash && <div className="cam-flash" />}

      <div className="cam-bottom">
        <button className="cam-round" onClick={() => setShowDemo((x) => !x)} aria-label="Ảnh mẫu" disabled={!demo.length}>
          <Icon name="sparkle" />
        </button>
        <button className="cam-shutter" onClick={() => phase === "aim" && shoot()} disabled={phase !== "aim"} aria-label="Chụp ảnh">
          <span />
        </button>
        <button className="cam-round" onClick={() => fileInput.current?.click()} aria-label="Chọn ảnh có sẵn">
          <Icon name="image" />
        </button>
      </div>

      {showDemo && phase === "aim" && demo.length > 0 && (
        <div className="cam-demo" aria-label="Ảnh mẫu cho demo">
          {demo.filter((d) => (purpose === "receipt" ? d.name.startsWith("receipt") : !d.name.startsWith("receipt"))).map((d) => (
            <button key={d.name} onClick={() => send(null, d.name, d.url)}>
              <img src={d.url} alt="" /><span>{d.label}</span>
            </button>
          ))}
        </div>
      )}
      <input ref={fileInput} type="file" accept="image/*" capture="environment" className="sr-only"
             onChange={(e) => e.target.files?.[0] && send(e.target.files[0])} />
    </div>
  );
}
