/** Bộ icon nét tròn, đơn giản (24×24, stroke = currentColor). */
const P: Record<string, string> = {
  mic: "M12 3a3 3 0 0 0-3 3v6a3 3 0 0 0 6 0V6a3 3 0 0 0-3-3Z M5 11a7 7 0 0 0 14 0 M12 18v3",
  camera: "M4 8h3l2-3h6l2 3h3a1 1 0 0 1 1 1v9a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V9a1 1 0 0 1 1-1Z M12 16.5a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7Z",
  box: "M3.5 7.5 12 3l8.5 4.5v9L12 21l-8.5-4.5v-9Z M3.5 7.5 12 12l8.5-4.5 M12 12v9",
  chat: "M4 5h16v11H9l-5 4V5Z M8 9.5h8 M8 12.5h5",
  sun: "M12 16a4 4 0 1 0 0-8 4 4 0 0 0 0 8Z M12 2v2 M12 20v2 M4.9 4.9l1.4 1.4 M17.7 17.7l1.4 1.4 M2 12h2 M20 12h2 M4.9 19.1l1.4-1.4 M17.7 6.3l1.4-1.4",
  bag: "M5 8h14l-1 12H6L5 8Z M9 8V6a3 3 0 0 1 6 0v2 M12 11.5v5 M9.5 14h5",
  home: "M4 11 12 4l8 7v9h-5v-6H9v6H4v-9Z",
  repeat: "M4 12a8 8 0 0 1 13.7-5.7L20 8.5 M20 4v4.5h-4.5 M20 12a8 8 0 0 1-13.7 5.7L4 15.5 M4 20v-4.5h4.5",
  slow: "M12 20a8 8 0 1 0 0-16 8 8 0 0 0 0 16Z M12 8v4l2.5 2.5",
  keyboard: "M3 7h18v10H3V7Z M7 10h.01 M10 10h.01 M13 10h.01 M16 10h.01 M8 14h8",
  check: "M5 12.5 10 17.5 19 7",
  x: "M6 6l12 12 M18 6 6 18",
  ear: "M7 9a5 5 0 0 1 10 0c0 3-3 4-3 7a3 3 0 0 1-5.5 1.6 M10 9a2 2 0 0 1 4 0",
  hand: "M8 13V6.5a1.5 1.5 0 0 1 3 0V12 M11 11V5a1.5 1.5 0 0 1 3 0v6 M14 11V6.5a1.5 1.5 0 0 1 3 0v7.5a7 7 0 0 1-7 7c-2.5 0-4-1.2-5.3-3.3L3 15.4a1.5 1.5 0 0 1 2.4-1.8L8 16",
  users: "M9 11a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7Z M2.5 20a6.5 6.5 0 0 1 13 0 M16 4.3a3.5 3.5 0 0 1 0 6.4 M18 14a6.5 6.5 0 0 1 3.5 6",
  user: "M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8Z M4.5 21a7.5 7.5 0 0 1 15 0",
  store: "M4 9.5 5.5 4h13L20 9.5 M4 9.5a2.7 2.7 0 0 0 5.3 0 2.7 2.7 0 0 0 5.4 0 2.7 2.7 0 0 0 5.3 0 M5 12v8h14v-8 M10 20v-4h4v4",
  pin: "M12 21s-6.5-6-6.5-11a6.5 6.5 0 0 1 13 0c0 5-6.5 11-6.5 11Z M12 12.5a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5Z",
  truck: "M3 6h11v10H3V6Z M14 9.5h4l3 3.5v3h-7 M7 19a1.8 1.8 0 1 0 0-3.6A1.8 1.8 0 0 0 7 19Z M17.5 19a1.8 1.8 0 1 0 0-3.6 1.8 1.8 0 0 0 0 3.6Z",
  money: "M3 7h18v10H3V7Z M12 14.5a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5Z M6.5 10v.01 M17.5 14v.01",
  arrow: "M5 12h14 M13 6l6 6-6 6",
  back: "M19 12H5 M11 6l-6 6 6 6",
  speaker: "M4 9.5h3.5L12 5.5v13l-4.5-4H4v-5Z M16 9a4 4 0 0 1 0 6 M18.5 6.5a7.5 7.5 0 0 1 0 11",
  stop: "M7 7h10v10H7V7Z",
  shield: "M12 3 4.5 6v5.5c0 4.4 3.2 8.3 7.5 9.5 4.3-1.2 7.5-5.1 7.5-9.5V6L12 3Z M8.8 12l2.2 2.2 4.2-4.4",
  bell: "M6 16V11a6 6 0 0 1 12 0v5l1.5 2h-15L6 16Z M10 20.5a2.2 2.2 0 0 0 4 0",
  undo: "M9 14 4 9l5-5 M4 9h10.5a5.5 5.5 0 0 1 0 11H11",
  alert: "M12 3.5 2.5 20h19L12 3.5Z M12 10v4.5 M12 17.5v.01",
  sparkle: "M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8L12 3Z M19 16l.8 2.2L22 19l-2.2.8L19 22l-.8-2.2L16 19l2.2-.8L19 16Z",
  calendar: "M4 6h16v14H4V6Z M4 10h16 M8.5 3.5v4 M15.5 3.5v4",
  send: "M4 12 20 4l-4 16-4-6.5L4 12Z M12 13.5 20 4",
  logout: "M14 4h5v16h-5 M10 8l-4 4 4 4 M6 12h10",
  image: "M4 5h16v14H4V5Z M8.5 10a1.5 1.5 0 1 0 0-3 1.5 1.5 0 0 0 0 3Z M20 15l-5-5L5 19",
};

export type IconName = keyof typeof P;

export default function Icon({ name, size = 24, stroke = 2, className, title }: {
  name: IconName; size?: number; stroke?: number; className?: string; title?: string;
}) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={stroke}
         strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden={title ? undefined : true} role={title ? "img" : undefined}>
      {title && <title>{title}</title>}
      <path d={P[name]} />
    </svg>
  );
}

/** Dấu hiệu trợ lý: ô tròn tối, micro trắng — đơn giản, không hình con vật. */
export function Mark({ size = 44 }: { size?: number }) {
  return (
    <span aria-hidden="true" style={{ width: size, height: size, borderRadius: size * 0.32, background: "#161a26", color: "#fff",
                                      display: "inline-grid", placeItems: "center", flex: "0 0 auto" }}>
      <Icon name="mic" size={Math.round(size * 0.5)} stroke={2.2} />
    </span>
  );
}
