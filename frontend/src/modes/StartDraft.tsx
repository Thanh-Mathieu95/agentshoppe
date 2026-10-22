import { useEffect } from "react";
import { postJSON, setProfileId } from "../api";
import VoiceOrb from "../components/VoiceOrb";

/** Mở app lần đầu: tạo hồ sơ nháp rồi vào thẳng cuộc trò chuyện (trợ lý tự hỏi để điền hồ sơ). */
export default function StartDraft() {
  useEffect(() => {
    let alive = true;
    postJSON<{ id: number }>("/api/sellers/draft").then((r) => alive && setProfileId(r.id)).catch(() => {});
    return () => { alive = false; };
  }, []);
  return <VoiceOrb state="connecting" onPress={() => {}} />;
}
