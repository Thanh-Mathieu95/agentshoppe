/** Hội thoại thời gian thực (OpenAI Realtime qua WebRTC): mic luôn mở, cho ngắt lời.
 *  Realtime chỉ là tai và miệng: lời người bán (bản ghi) gửi cho backend; câu backend trả về được đọc nguyên văn. */

export type RtState = "connecting" | "listening" | "hearing" | "thinking" | "speaking" | "paused" | "blocked" | "error";

type Handlers = {
  onState: (s: RtState) => void;
  onHeard: (text: string) => void;
  onSpoken?: () => void;
  onSaid?: (text: string) => void;
  onError?: (msg: string) => void;
};

export class RealtimeVoice {
  private pc?: RTCPeerConnection;
  private dc?: RTCDataChannel;
  private audio = new Audio();
  private mic?: MediaStream;
  private queue: string[] = [];
  private speaking = false;
  private current = "";
  private oob = true;     // đọc ngoài hội thoại (không tích lũy ngữ cảnh) nếu server hỗ trợ
  state: RtState = "connecting";

  constructor(private h: Handlers) {
    this.audio.autoplay = true;
  }

  private set(s: RtState) {
    this.state = s;
    this.h.onState(s);
  }

  // Chế độ trợ lý: mô hình tự trò chuyện, gọi công cụ backend; code vẫn giữ cổng xác nhận.
  private agent = false;
  private sellerId = 0;
  private responding = false;
  private needResponse = false;

  async start(sellerId: number, agent = false): Promise<void> {
    this.agent = agent;
    this.sellerId = sellerId;
    this.set("connecting");
    const r = await fetch(`/api/rt/session/${sellerId}${agent ? "?agent=true" : ""}`, { method: "POST" });
    if (!r.ok) throw new Error(`session ${r.status}`);
    const { client_secret, model } = await r.json();

    this.mic = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
    });
    const pc = new RTCPeerConnection();
    this.pc = pc;
    pc.ontrack = (e) => { this.audio.srcObject = e.streams[0]; };
    this.mic.getTracks().forEach((t) => pc.addTrack(t, this.mic!));
    const dc = pc.createDataChannel("oai-events");
    this.dc = dc;
    dc.onmessage = (m) => this.onEvent(JSON.parse(m.data));
    const opened = new Promise<void>((res) => (dc.onopen = () => res()));

    await pc.setLocalDescription(await pc.createOffer());
    const ans = await fetch(`https://api.openai.com/v1/realtime/calls?model=${encodeURIComponent(model)}`, {
      method: "POST", body: pc.localDescription!.sdp,
      headers: { Authorization: `Bearer ${client_secret}`, "Content-Type": "application/sdp" },
    });
    if (!ans.ok) throw new Error(`sdp ${ans.status}`);
    await pc.setRemoteDescription({ type: "answer", sdp: await ans.text() });
    await opened;
    try {
      await this.audio.play();
    } catch {
      this.set("blocked");   // trình duyệt chặn tự phát âm thanh: cần một lần chạm
      return;
    }
    this.set("listening");
    if (this.agent) this.respond();   // trợ lý tự mở lời
  }

  /** Gọi sau một lần chạm khi trình duyệt chặn âm thanh. */
  async unblock() {
    await this.audio.play();
    this.set("listening");
    if (this.agent) this.respond();
    else this.flush();
  }

  /** Đưa thông báo của hệ thống (đơn mới, kết quả ảnh...) vào cuộc trò chuyện để trợ lý báo người bán. */
  notify(text: string) {
    this.send({ type: "conversation.item.create", item: { type: "message", role: "system", content: [{ type: "input_text", text }] } });
    this.respond();
  }

  /** Người bán gõ chữ thay vì nói (người đi cùng, hoặc kiểm thử): đi đúng đường như lời nói. */
  typeText(text: string) {
    this.h.onHeard(text);
    this.send({ type: "conversation.item.create", item: { type: "message", role: "user", content: [{ type: "input_text", text }] } });
    this.respond();
  }

  private respond() {
    if (this.state === "blocked" || this.state === "paused") { this.needResponse = true; return; }
    if (this.responding) { this.needResponse = true; return; }
    this.responding = true;
    this.send({ type: "response.create" });
  }

  private async runTool(callId: string, name: string, argsJson: string) {
    let args = {};
    try { args = JSON.parse(argsJson || "{}"); } catch { /* tham số hỏng -> gửi rỗng */ }
    let output: unknown;
    try {
      const r = await fetch(`/api/rt/tool/${this.sellerId}`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name, args }),
      });
      output = await r.json();
    } catch {
      output = { ok: false, error: "Mất kết nối máy chủ. Xin lỗi người bán và thử lại." };
    }
    console.info("[rt] công cụ", name, args, "->", output);
    this.send({ type: "conversation.item.create", item: { type: "function_call_output", call_id: callId, output: JSON.stringify(output) } });
    this.respond();
  }

  /** Đọc nguyên văn một câu do backend đưa. */
  say(text: string) {
    if (!text.trim()) return;
    this.queue.push(text.trim());
    this.flush();
  }

  private flush() {
    if (this.speaking || !this.dc || this.dc.readyState !== "open" || this.state === "blocked") return;
    const text = this.queue.shift();
    if (!text) return;
    this.current = text;
    this.speaking = true;
    this.set("speaking");
    const response: Record<string, unknown> = {
      output_modalities: ["audio"],
      instructions: `Đọc NGUYÊN VĂN câu sau bằng tiếng Việt, không thêm, không bớt, không đổi số: «${text}»`,
    };
    if (this.oob) Object.assign(response, { conversation: "none", input: [] });
    this.send({ type: "response.create", response });
  }

  setPaused(p: boolean) {
    this.mic?.getAudioTracks().forEach((t) => (t.enabled = !p));
    if (p) {
      this.send({ type: "response.cancel" });
      this.send({ type: "output_audio_buffer.clear" });
      this.queue = [];
      this.speaking = false;
    }
    this.set(p ? "paused" : "listening");
    if (!p && this.agent && this.needResponse) { this.needResponse = false; this.respond(); }
  }

  stop() {
    this.mic?.getTracks().forEach((t) => t.stop());
    this.dc?.close();
    this.pc?.close();
  }

  private send(ev: unknown) {
    if (this.dc?.readyState === "open") this.dc.send(JSON.stringify(ev));
  }

  private onEvent(e: any) {
    switch (e.type) {
      case "input_audio_buffer.speech_started":
        // người bán nói chen: bỏ những câu chưa đọc, server tự cắt câu đang đọc
        this.queue = [];
        if (this.state !== "paused") this.set("hearing");
        break;
      case "input_audio_buffer.speech_stopped":
        if (this.state !== "paused") this.set("thinking");
        break;
      case "conversation.item.input_audio_transcription.completed": {
        const t = (e.transcript || "").trim();
        if (t) this.h.onHeard(t);
        else if (this.state === "thinking") this.set("listening");
        break;
      }
      case "response.output_audio_transcript.done":
        console.info("[rt] đã nói:", e.transcript, this.agent ? "" : `| cần nói: ${this.current}`);
        if (this.agent) this.h.onSaid?.(e.transcript);
        break;
      case "response.created":
        if (this.agent) this.responding = true;
        break;
      case "response.output_item.done":
        if (this.agent && e.item?.type === "function_call") this.runTool(e.item.call_id, e.item.name, e.item.arguments);
        break;
      case "output_audio_buffer.started":
        if (this.agent && this.state !== "paused") this.set("speaking");
        break;
      case "response.done":
      case "output_audio_buffer.stopped":
        if (this.agent) {
          if (e.type === "response.done") {
            this.responding = false;
            if (this.state === "thinking") this.set("listening");
            if (this.needResponse) { this.needResponse = false; this.respond(); }
          } else if (this.state === "speaking") {
            this.set("listening");
            this.h.onSpoken?.();
          }
          break;
        }
        if (!this.speaking) break;
        if (e.type === "response.done" && e.response?.status === "completed") break;   // chờ âm thanh phát hết
        this.speaking = false;
        if (this.state !== "paused") this.set(this.queue.length ? "speaking" : "listening");
        this.h.onSpoken?.();
        this.flush();
        break;
      case "error": {
        const msg = e.error?.message || "lỗi";
        if (this.oob && /conversation|input/i.test(msg)) {   // server cũ không hỗ trợ đọc ngoài hội thoại
          this.oob = false;
          this.speaking = false;
          if (this.current) this.queue.unshift(this.current);
          this.flush();
          break;
        }
        if (/no active response|cancel/i.test(msg)) break;
        this.h.onError?.(msg);
        break;
      }
    }
  }
}
