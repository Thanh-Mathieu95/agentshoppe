import { useEffect, useRef, useState } from "react";
import { vibrate } from "../speech";

/** Giữ 1,5 giây mới xác nhận (tránh chạm nhầm). Bàn phím: giữ Enter/Space. */
export default function HoldButton({ label, onDone, ms = 1500, className = "btn yes hold" }: {
  label: string; onDone: () => void; ms?: number; className?: string;
}) {
  const [p, setP] = useState(0);
  const start = useRef<number | null>(null);
  const raf = useRef(0);
  const fired = useRef(false);

  const tick = () => {
    if (start.current == null) return;
    const v = Math.min(1, (performance.now() - start.current) / ms);
    setP(v);
    if (v >= 1 && !fired.current) {
      fired.current = true;
      vibrate([80, 60, 160]);
      onDone();
      return;
    }
    raf.current = requestAnimationFrame(tick);
  };
  const down = () => {
    fired.current = false;
    start.current = performance.now();
    raf.current = requestAnimationFrame(tick);
  };
  const up = () => {
    start.current = null;
    cancelAnimationFrame(raf.current);
    if (!fired.current) setP(0);
  };
  useEffect(() => () => cancelAnimationFrame(raf.current), []);

  return (
    <button
      className={className}
      aria-label={`${label}. Giữ nút một giây rưỡi để xác nhận`}
      onPointerDown={down} onPointerUp={up} onPointerLeave={up} onPointerCancel={up}
      onKeyDown={(e) => { if ((e.key === "Enter" || e.key === " ") && start.current == null) { e.preventDefault(); down(); } }}
      onKeyUp={up}
      onContextMenu={(e) => e.preventDefault()}
    >
      <div className="fill" style={{ transform: `scaleX(${p})` }} />
      <span>{p > 0 && p < 1 ? "Giữ…" : label}</span>
    </button>
  );
}
