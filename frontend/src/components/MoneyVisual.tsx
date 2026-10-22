/** Số tiền bằng hình tờ tiền: "notes:500000x1,100000x2". */
const LABEL: Record<number, string> = { 500000: "500K", 200000: "200K", 100000: "100K", 50000: "50K", 20000: "20K", 10000: "10K" };

export function parseNotes(visual?: string): [number, number][] {
  if (!visual?.startsWith("notes:")) return [];
  return visual.slice(6).split(",").filter(Boolean).map((p) => {
    const [n, c] = p.split("x").map(Number);
    return [n, c] as [number, number];
  });
}

export default function MoneyVisual({ visual }: { visual?: string }) {
  const notes = parseNotes(visual);
  if (!notes.length) return null;
  const desc = notes.map(([n, c]) => `${c} tờ ${LABEL[n] || n}`).join(", ");
  return (
    <div className="notes" role="img" aria-label={desc}>
      {notes.map(([n, c]) =>
        c <= 4
          ? Array.from({ length: c }, (_, i) => <div key={`${n}-${i}`} className={`note n${n}`}>{LABEL[n]}</div>)
          : [<div key={n} className={`note n${n}`}>{LABEL[n]}</div>, <span key={`${n}x`} className="times">× {c}</span>],
      )}
    </div>
  );
}
