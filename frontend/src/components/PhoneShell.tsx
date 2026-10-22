import { useEffect, useState, type ReactNode } from "react";

/** Máy tính: hiện app trong khung điện thoại. Điện thoại thật hoặc khung nhúng: toàn màn hình. */
export default function PhoneShell({ children, side }: { children: ReactNode; side?: ReactNode }) {
  const embedded = window.self !== window.top;
  const [wide, setWide] = useState(window.innerWidth >= 640);
  useEffect(() => {
    const on = () => setWide(window.innerWidth >= 640);
    window.addEventListener("resize", on);
    return () => window.removeEventListener("resize", on);
  }, []);
  if (embedded || !wide) return <div className="screen full">{children}</div>;
  return (
    <div className="stage">
      <div className="device"><div className="screen">{children}</div></div>
      {side && <div className="stage-side">{side}</div>}
    </div>
  );
}
