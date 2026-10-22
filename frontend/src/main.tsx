import { StrictMode, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import DemoBoard from "./demo/DemoBoard";
import "./market/market.css";
import { CartPage, CheckoutPage, Home, OrdersPage, ProductPage, Search, ShopPage } from "./market/pages";
import { profileId } from "./api";
import PhoneShell from "./components/PhoneShell";
import GuardianView from "./modes/GuardianView";
import StartDraft from "./modes/StartDraft";
import SellerApp from "./SellerApp";
import SellerCenter from "./seller/SellerCenter";
import "./styles.css";

function useHash() {
  const [h, setH] = useState(location.hash || "#/");
  useEffect(() => {
    const on = () => setH(location.hash || "#/");
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);
  return h;
}

/** #/ sàn · #/p/:id · #/search · #/cart · #/checkout · #/orders · #/shop/:id · #/seller · #/app · #/board · #/guardian */
function useProfile() {
  const [id, setId] = useState(profileId());
  useEffect(() => {
    const on = () => setId(profileId());
    window.addEventListener("bkrc-profile", on);
    window.addEventListener("storage", on);   // hồ sơ tạo trong khung điện thoại -> Kênh Người Bán cập nhật
    return () => { window.removeEventListener("bkrc-profile", on); window.removeEventListener("storage", on); };
  }, []);
  return id;
}

function App() {
  const hash = useHash();
  const profile = useProfile();
  const sellerId = profile ?? 1;
  const [path, query = ""] = hash.slice(1).split("?");
  const params = new URLSearchParams(query);
  const seg = path.split("/").filter(Boolean);

  useEffect(() => {
    document.body.style.background = "#f4f6fb";
  }, [seg[0]]);

  switch (seg[0]) {
    case "app": return profile ? <SellerApp key={profile} sellerId={profile} /> : <PhoneShell><StartDraft /></PhoneShell>;
    case "board": return <DemoBoard sellerId={sellerId} />;
    case "guardian": return <GuardianView sellerId={sellerId} />;
    case "seller": return <SellerCenter key={sellerId} sellerId={sellerId} />;
    case "p": return <ProductPage id={Number(seg[1])} />;
    case "search": return <Search params={params} />;
    case "cart": return <CartPage />;
    case "checkout": return <CheckoutPage />;
    case "orders": return <OrdersPage params={params} />;
    case "shop": return <ShopPage id={Number(seg[1])} />;
    default: return <Home />;
  }
}

createRoot(document.getElementById("root")!).render(<StrictMode><App /></StrictMode>);
