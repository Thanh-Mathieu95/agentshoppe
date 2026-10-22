import { useEffect, useState } from "react";
import { getJSON, postJSON } from "../api";

/** Chế độ demo: tin chờ 10 giây thay vì 10 phút trước khi lên sàn. */
export default function DemoToggle() {
  const [on, setOn] = useState<boolean | null>(null);
  useEffect(() => { getJSON<{ on: boolean }>("/api/demo/mode").then((r) => setOn(r.on)).catch(() => {}); }, []);
  if (on === null) return null;
  const flip = () => postJSON<{ on: boolean }>("/api/demo/mode", { on: !on }).then((r) => setOn(r.on));
  return (
    <button className={`demo-toggle ${on ? "on" : ""}`} role="switch" aria-checked={on} onClick={flip}
            title={on ? "Tin lên sàn sau 10 giây" : "Tin lên sàn sau 10 phút"}>
      <span className="knob" /> Demo {on ? "· đăng sau 10 giây" : "tắt"}
    </button>
  );
}
