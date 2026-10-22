/** Nghe – Nói trên trình duyệt: Web Speech API (vi-VN) + âm báo. */

type Rec = {
  lang: string; interimResults: boolean; maxAlternatives: number; continuous: boolean;
  start(): void; stop(): void; abort(): void;
  onresult: ((e: any) => void) | null; onerror: ((e: any) => void) | null; onend: (() => void) | null;
};

const RecCtor: (new () => Rec) | undefined = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
export const canRecognize = !!RecCtor;
export const canRecord = typeof MediaRecorder !== "undefined" && !!navigator.mediaDevices?.getUserMedia;

export type Heard = { text: string; confidence: number | null };

/** Nghe một câu. Trả null nếu im lặng / lỗi. */
export function listenOnce(maxMs = 8000): { promise: Promise<Heard | null>; stop: () => void } {
  if (!RecCtor) return { promise: Promise.resolve(null), stop: () => {} };
  const rec = new RecCtor();
  rec.lang = "vi-VN";
  rec.interimResults = false;
  rec.maxAlternatives = 1;
  rec.continuous = false;
  let done = false;
  let resolveFn: (h: Heard | null) => void = () => {};
  const promise = new Promise<Heard | null>((resolve) => (resolveFn = resolve));
  const finish = (h: Heard | null) => {
    if (done) return;
    done = true;
    clearTimeout(timer);
    resolveFn(h);
  };
  rec.onresult = (e: any) => {
    const alt = e.results[0][0];
    finish({ text: alt.transcript, confidence: typeof alt.confidence === "number" && alt.confidence > 0 ? alt.confidence : null });
  };
  rec.onerror = () => finish(null);
  rec.onend = () => finish(null);
  const timer = setTimeout(() => { try { rec.stop(); } catch { /* đã dừng */ } }, maxMs);
  try { rec.start(); } catch { finish(null); }
  return { promise, stop: () => { try { rec.stop(); } catch { /* đã dừng */ } } };
}

/** Ghi âm để server nhận dạng. Tự dừng khi im lặng 1,2 giây sau lúc bắt đầu nói. */
export function recordOnce(maxMs = 9000): { promise: Promise<string | null>; stop: () => void } {
  let stopFn = () => {};
  const promise = (async () => {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } });
    const rec = new MediaRecorder(stream);
    const chunks: Blob[] = [];
    rec.ondataavailable = (e) => chunks.push(e.data);
    const stopped = new Promise<void>((r) => (rec.onstop = () => r()));
    const stop = () => { if (rec.state !== "inactive") rec.stop(); };
    stopFn = stop;
    rec.start();
    const ac = new AudioContext();
    const an = ac.createAnalyser();
    an.fftSize = 1024;
    ac.createMediaStreamSource(stream).connect(an);
    const buf = new Uint8Array(an.fftSize);
    let spoke = false;
    let quietSince = performance.now();
    const started = performance.now();
    const timer = setInterval(() => {
      an.getByteTimeDomainData(buf);
      let peak = 0;
      for (const v of buf) peak = Math.max(peak, Math.abs(v - 128));
      const now = performance.now();
      if (peak > 14) { spoke = true; quietSince = now; }
      if ((spoke && now - quietSince > 1200) || (!spoke && now - started > 6000) || now - started > maxMs) stop();
    }, 80);
    await stopped;
    clearInterval(timer);
    ac.close();
    stream.getTracks().forEach((t) => t.stop());
    if (!spoke) return null;
    const blob = new Blob(chunks, { type: rec.mimeType });
    if (blob.size < 2000) return null;
    const bytes = new Uint8Array(await blob.arrayBuffer());
    let bin = "";
    bytes.forEach((b) => (bin += String.fromCharCode(b)));
    return btoa(bin);
  })().catch(() => null);
  return { promise, stop: () => stopFn() };
}

let viVoice: SpeechSynthesisVoice | null = null;
function pickVoice() {
  const voices = speechSynthesis.getVoices();
  viVoice = voices.find((v) => v.lang?.toLowerCase().startsWith("vi")) || null;
}
if ("speechSynthesis" in window) {
  pickVoice();
  speechSynthesis.onvoiceschanged = pickVoice;
}

let currentAudio: HTMLAudioElement | null = null;

/** Đọc to. Câu xác nhận ĐỎ đọc chậm hơn 10% và ngắt nghỉ trước con số. */
export function speak(text: string, opts: { speed?: number; confirm?: boolean; audio?: string } = {}): Promise<void> {
  stopSpeaking();
  const rate = (opts.speed ?? 0.9) * (opts.confirm ? 0.9 : 1);
  if (opts.audio) {
    return new Promise((resolve) => {
      const a = new Audio(`data:audio/mp3;base64,${opts.audio}`);
      currentAudio = a;
      a.onended = () => resolve();
      a.onerror = () => resolve();
      a.play().catch(() => resolve());
    });
  }
  if (!("speechSynthesis" in window)) return Promise.resolve();
  const spoken = opts.confirm ? text.replace(/(giá|là|có|bằng)\s+/g, "$1, ") : text;
  return new Promise((resolve) => {
    const u = new SpeechSynthesisUtterance(spoken);
    u.lang = "vi-VN";
    if (viVoice) u.voice = viVoice;
    u.rate = rate;
    u.onend = () => resolve();
    u.onerror = () => resolve();
    speechSynthesis.speak(u);
  });
}

export function stopSpeaking() {
  if ("speechSynthesis" in window) speechSynthesis.cancel();
  if (currentAudio) { currentAudio.pause(); currentAudio = null; }
}

let serverSpeech: Promise<{ stt: string; tts: string }> | null = null;
function speechConfig() {
  serverSpeech = serverSpeech || fetch("/api/config").then((r) => r.json()).catch(() => ({ stt: "browser", tts: "browser" }));
  return serverSpeech;
}

/** Đọc một câu ngoài phiên trợ lý (màn tạo hồ sơ): giọng server nếu có, không thì giọng trình duyệt. */
export async function say(text: string, speed = 0.95): Promise<void> {
  const cfg = await speechConfig();
  if (cfg.tts === "openai") {
    try {
      const r = await fetch("/api/speech/tts", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text, speed }) });
      const j = await r.json();
      if (j.audio) return speak(text, { audio: j.audio });
    } catch { /* dùng giọng trình duyệt */ }
  }
  return speak(text, { speed });
}

/** Nghe một câu và trả chữ (màn tạo hồ sơ). */
export function hearOnce(hint = ""): { promise: Promise<string | null>; stop: () => void } {
  let stop = () => {};
  const promise = (async () => {
    const cfg = await speechConfig();
    if (cfg.stt === "openai" && canRecord) {
      const r = recordOnce(9000);
      stop = r.stop;
      const b64 = await r.promise;
      if (!b64) return null;
      const bin = atob(b64);
      const bytes = new Uint8Array(bin.length);
      for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
      const fd = new FormData();
      fd.append("audio", new Blob([bytes], { type: "audio/webm" }), "speech.webm");
      fd.append("hint", hint);
      const res = await fetch("/api/speech/stt", { method: "POST", body: fd });
      return res.ok ? ((await res.json()).text as string) || null : null;
    }
    const l = listenOnce(8000);
    stop = l.stop;
    return (await l.promise)?.text || null;
  })().catch(() => null);
  return { promise, stop: () => stop() };
}

let ctx: AudioContext | null = null;
/** Âm báo khác nhau: đơn mới / khách hỏi / cảnh báo / mic mở. */
export function chime(kind: "new_order" | "buyer_question" | "warning" | "listen" | "ok" | string) {
  try {
    ctx = ctx || new AudioContext();
    const seq: Record<string, number[]> = {
      new_order: [660, 880, 1100], buyer_question: [520, 700], warning: [300, 220, 300], listen: [880], ok: [700, 1000],
    };
    const notes = seq[kind] || [600];
    notes.forEach((f, i) => {
      const o = ctx!.createOscillator();
      const g = ctx!.createGain();
      o.frequency.value = f;
      o.type = kind === "warning" ? "square" : "sine";
      g.gain.setValueAtTime(0.0001, ctx!.currentTime + i * 0.16);
      g.gain.exponentialRampToValueAtTime(0.25, ctx!.currentTime + i * 0.16 + 0.02);
      g.gain.exponentialRampToValueAtTime(0.0001, ctx!.currentTime + i * 0.16 + 0.15);
      o.connect(g).connect(ctx!.destination);
      o.start(ctx!.currentTime + i * 0.16);
      o.stop(ctx!.currentTime + i * 0.16 + 0.16);
    });
  } catch { /* không có âm thanh */ }
}

export function vibrate(pattern?: number[]) {
  if (navigator.vibrate) navigator.vibrate(pattern || [200]);
}
