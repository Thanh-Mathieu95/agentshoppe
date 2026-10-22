import Icon, { type IconName } from "./Icon";

export type MicState = "idle" | "listening" | "thinking" | "speaking" | "paused" | "connecting" | "blocked";

const LABEL: Record<MicState, [string, string, IconName | null]> = {
  idle: ["Chạm để nói", "Chạm vào bất kỳ đâu trong vùng vàng", "mic"],
  listening: ["Tôi đang nghe", "Cứ nói tự nhiên, không cần bấm gì", null],
  thinking: ["Đang nghĩ…", "Đợi tôi một chút nhé", "sparkle"],
  speaking: ["Đang nói…", "Cần thì cứ nói chen vào", null],
  paused: ["Đã tạm dừng", "Chạm vào đây để nói tiếp", "mic"],
  connecting: ["Đang kết nối…", "Chuẩn bị nghe và nói", "sparkle"],
  blocked: ["Chạm để bắt đầu", "Chỉ cần chạm một lần, sau đó cứ nói", "mic"],
};

/** Nửa dưới màn hình: trạng thái nghe/nói. Thời gian thực thì không cần bấm; chạm để tạm dừng / nói tiếp. */
export default function BigMicButton({ state, onPress }: { state: MicState; onPress: () => void }) {
  const [lbl, hint, icon] = LABEL[state];
  const live = state === "listening" || state === "speaking";
  return (
    <button className={`talk ${state === "paused" || state === "blocked" ? "idle" : state}`} onClick={onPress}
            aria-label={`${lbl}. ${hint}`} autoFocus>
      <span className="mic-circle">
        {live || !icon ? <span className="wave" aria-hidden="true"><i /><i /><i /><i /><i /></span> : <Icon name={icon} size={56} stroke={2.2} />}
      </span>
      <span className="lbl" aria-live="polite">{lbl}</span>
      <span className="hint">{hint}</span>
    </button>
  );
}
