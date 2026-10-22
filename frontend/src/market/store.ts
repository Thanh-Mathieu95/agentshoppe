import { useSyncExternalStore } from "react";

export type Product = {
  id: number; title: string; price: number; list_price: number | null; discount: number; sold: number; rating: number;
  image: string | null; images: string[]; category: string; category_label: string; icon: string; stock: number;
  shop: { id: number; name: string; region: string; avatar: string; assistant: boolean; followers?: number; products?: number };
};
export type CartLine = { id: number; qty: number; title: string; price: number; image: string | null; shop: Product["shop"]; stock: number };

const KEY = "bkrc.cart";
let cart: CartLine[] = load();
const subs = new Set<() => void>();

function load(): CartLine[] {
  try { return JSON.parse(localStorage.getItem(KEY) || "[]"); } catch { return []; }
}
function save() {
  try { localStorage.setItem(KEY, JSON.stringify(cart)); } catch { /* chế độ riêng tư */ }
  subs.forEach((f) => f());
}

export const cartStore = {
  subscribe(f: () => void) { subs.add(f); return () => { subs.delete(f); }; },
  get: () => cart,
  add(p: Product, qty: number) {
    const ex = cart.find((l) => l.id === p.id);
    const max = p.stock || 99;
    cart = ex
      ? cart.map((l) => (l.id === p.id ? { ...l, qty: Math.min(max, l.qty + qty) } : l))
      : [...cart, { id: p.id, qty: Math.min(max, qty), title: p.title, price: p.price, image: p.image, shop: p.shop, stock: p.stock }];
    save();
  },
  setQty(id: number, qty: number) { cart = cart.map((l) => (l.id === id ? { ...l, qty: Math.max(1, Math.min(l.stock || 99, qty)) } : l)); save(); },
  remove(id: number) { cart = cart.filter((l) => l.id !== id); save(); },
  removeMany(ids: number[]) { cart = cart.filter((l) => !ids.includes(l.id)); save(); },
};

export function useCart() {
  return useSyncExternalStore(cartStore.subscribe, cartStore.get);
}

/** Mã người mua giả lập (không đăng nhập) để xem lại đơn của mình. */
export function buyerKey(): string {
  try {
    let k = localStorage.getItem("bkrc.buyer");
    if (!k) { k = "b" + Math.random().toString(36).slice(2, 10); localStorage.setItem("bkrc.buyer", k); }
    return k;
  } catch { return "guest-demo"; }
}

export function savedBuyer(): { name: string; phone: string; province: string; address: string } {
  try { return JSON.parse(localStorage.getItem("bkrc.buyerInfo") || "null") || { name: "", phone: "", province: "Hà Nội", address: "" }; }
  catch { return { name: "", phone: "", province: "Hà Nội", address: "" }; }
}
export function saveBuyer(v: ReturnType<typeof savedBuyer>) {
  try { localStorage.setItem("bkrc.buyerInfo", JSON.stringify(v)); } catch { /* bỏ qua */ }
}

export const vnd = (v: number) => "₫" + (v || 0).toLocaleString("vi-VN");
export const soldText = (n: number) => (n >= 1000 ? `${(n / 1000).toFixed(1).replace(".", ",")}k` : String(n));
export function go(path: string) { location.hash = path; window.scrollTo(0, 0); }
