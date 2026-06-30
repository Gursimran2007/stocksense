"""StockSense — plain-language inventory helper for shop owners (v1 demo UI).

Five-page layout (sidebar nav):
  1. Dashboard          — sales chart + current stock levels
  2. Record sales       — photo-of-register OCR + manual sell / receive stock
  3. Restocking         — what to buy + one-tap order per assigned supplier
  4. Suppliers          — named suppliers, edit them, assign one per product
  5. Inventory input    — set current stock, add items, upload / auto-sync
"""
import pandas as pd
import streamlit as st

from core import db
from core import auth
from core.adapters import TabularAdapter, ManualAdapter
from core.seed import seed_db, write_messy_excel
from core.engine import build_report, cash_view
from core.sourcing import whatsapp_link, marketplace_links, tel_link

st.set_page_config(page_title="StockSense", page_icon="S", layout="wide")
auth.init()


def inject_css():
    st.markdown("""
    <style>
      @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;450;500;600;700&display=swap');
      :root{
        --bg:#F4F1E8; --surface:#FFFFFF; --border:#E2DCC9; --border-2:#ECE7D8;
        --text:#1E2A22; --muted:#6E7A6C; --accent:#33503F; --accent-2:#3F624D;
        --accent-soft:#E7EDE4;
      }
      html, body, [class*="css"] { font-family:'Inter',sans-serif; color:var(--text); }
      .stApp { background:var(--bg); }
      header[data-testid="stHeader"]{ background:transparent; }
      [data-testid="stToolbar"]{ display:none; }
      /* Default Streamlit slides the collapsed sidebar fully off-screen,
         taking its only re-open arrow with it -> no way to reopen. Instead
         keep a thin on-screen rail (no translate) that holds just the toggle
         button, and hide the rest of the sidebar's content. */
      [data-testid="stSidebar"][aria-expanded="false"]{
        transform:none !important;
        width:46px !important; min-width:46px !important;
        overflow:hidden !important;
        background:var(--surface); border-right:1px solid var(--border);
      }
      [data-testid="stSidebar"][aria-expanded="false"] [data-testid="stSidebarUserContent"]{
        display:none !important;
      }
      [data-testid="stSidebar"][aria-expanded="false"] [data-testid="stSidebarHeader"]{
        width:46px !important; padding:8px 0 !important;
        justify-content:center !important; overflow:visible !important;
      }
      [data-testid="stSidebar"][aria-expanded="false"] [data-testid="stSidebarCollapseButton"]{
        transform:none !important; z-index:1000;
        visibility:visible !important; opacity:1 !important;
      }
      [data-testid="stSidebar"][aria-expanded="false"] [data-testid="stSidebarCollapseButton"] button{
        visibility:visible !important; opacity:1 !important;
        color:var(--accent); background:var(--surface);
        border:1px solid var(--border); border-radius:8px;
        box-shadow:0 1px 3px rgba(0,0,0,.08);
      }
      .block-container { padding-top:2.4rem; max-width:1200px; }
      h1,h2,h3,h4 { letter-spacing:-.015em; font-weight:600; }

      /* ---- top app bar (replaces colourful hero) ---- */
      .appbar{
        display:flex; align-items:center; gap:14px;
        padding:0 0 16px; margin-bottom:18px; border-bottom:1px solid var(--border);
      }
      .appbar .logo{
        width:38px; height:38px; border-radius:9px; flex:0 0 38px;
        background:var(--accent); color:#fff; font-weight:700; font-size:1.15rem;
        display:flex; align-items:center; justify-content:center;
        box-shadow:0 1px 2px rgba(15,23,42,.12);
      }
      .appbar .brand-name{ font-size:1.18rem; font-weight:650; line-height:1.1; }
      .appbar .brand-sub{ font-size:.86rem; color:var(--muted); margin-top:1px; }

      /* ---- metric cards: flat, data-dense ---- */
      [data-testid="stMetric"]{
        background:var(--surface); border:1px solid var(--border);
        border-radius:10px; padding:14px 16px;
      }
      [data-testid="stMetricLabel"] p{
        font-size:.72rem !important; font-weight:600; letter-spacing:.04em;
        text-transform:uppercase; color:var(--muted);
      }
      [data-testid="stMetricValue"]{ font-weight:650; font-size:1.7rem; }

      /* ---- buttons: flat, no bounce ---- */
      .stButton>button, .stDownloadButton>button, .stLinkButton>a,
      [data-testid="stFormSubmitButton"]>button{
        border-radius:8px; font-weight:550; font-size:.92rem;
        border:1px solid var(--border); background:var(--surface); color:var(--text);
        transition:background .12s ease, border-color .12s ease;
      }
      .stButton>button:hover, .stDownloadButton>button:hover, .stLinkButton>a:hover{
        border-color:#CBD2E0; background:#F4F6FA;
      }
      .stButton>button[kind="primary"], .stLinkButton>a[kind="primary"],
      [data-testid="stFormSubmitButton"]>button[kind="primary"]{
        background:var(--accent); border:1px solid var(--accent); color:#fff;
      }
      .stButton>button[kind="primary"]:hover,
      [data-testid="stFormSubmitButton"]>button[kind="primary"]:hover{
        background:var(--accent-2); border-color:var(--accent-2);
      }

      /* ---- sidebar: industry-standard vertical menu (full-width rows) ---- */
      [data-testid="stSidebar"]{ background:var(--surface); border-right:1px solid var(--border); }
      [data-testid="stSidebar"] .nav-head{
        font-size:.7rem; font-weight:700; letter-spacing:.08em; text-transform:uppercase;
        color:var(--muted); padding:2px 6px 6px;
      }
      [data-testid="stSidebar"] [role="radiogroup"]{ gap:1px; }
      [data-testid="stSidebar"] [role="radiogroup"] label{
        display:flex; width:100%; border-radius:6px; padding:9px 12px; margin:0;
        cursor:pointer; font-weight:500; font-size:.93rem; color:var(--text);
        border-left:3px solid transparent; transition:background .12s, color .12s;
      }
      [data-testid="stSidebar"] [role="radiogroup"] label:hover{ background:#F1EFE6; }
      [data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked){
        background:var(--accent-soft); color:var(--accent);
        border-left:3px solid var(--accent); font-weight:600;
      }
      [data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked) p{ color:var(--accent); font-weight:600; }
      [data-testid="stSidebar"] [role="radiogroup"] label > div:first-child{ display:none; }

      /* ---- surfaces ---- */
      [data-testid="stExpander"]{ border:1px solid var(--border); border-radius:10px; box-shadow:none; }
      [data-testid="stDataFrame"], [data-testid="stTable"]{
        border-radius:8px; overflow:hidden; border:1px solid var(--border);
      }
      [data-testid="stSidebar"] .stButton>button{ font-size:.86rem; }
      hr{ margin:1rem 0; border-color:var(--border-2); }
    </style>
    """, unsafe_allow_html=True)


inject_css()

# Tiny language layer for low-literacy / regional users (moat #1) -----------
LANGS = {"English": "en", "हिंदी": "hi", "Hinglish": "hinglish"}
T = {
    "title":   {"en": "StockSense", "hi": "StockSense",
                "hinglish": "StockSense"},
    "tagline": {"en": "What to buy today — and order it in one tap.",
                "hi": "आज क्या खरीदें — और एक टैप में ऑर्डर करें।",
                "hinglish": "Aaj kya khareedein — aur ek tap mein order karein."},
    # ---- nav ----
    "nav_dash": {"en": "Dashboard", "hi": "डैशबोर्ड",
                 "hinglish": "Dashboard"},
    "nav_sell": {"en": "Record sales", "hi": "बिक्री दर्ज करें",
                 "hinglish": "Bikri darj karo"},
    "nav_restock": {"en": "Restocking", "hi": "दोबारा स्टॉक",
                    "hinglish": "Restocking"},
    "nav_suppliers": {"en": "Suppliers", "hi": "सप्लायर",
                      "hinglish": "Suppliers"},
    "nav_input": {"en": "Inventory input", "hi": "स्टॉक भरें",
                  "hinglish": "Stock bharo"},
    # ---- restock ----
    "buy_these": {"en": "Buy these now", "hi": "अभी यह खरीदें",
                  "hinglish": "Abhi ye kharido"},
    "order_all": {"en": "Send full order on WhatsApp",
                  "hi": "पूरा ऑर्डर WhatsApp पर भेजें",
                  "hinglish": "Poora order WhatsApp par bhejo"},
    "order": {"en": "Order", "hi": "ऑर्डर", "hinglish": "Order"},
    "find": {"en": "Find supplier", "hi": "दुकानदार खोजें",
             "hinglish": "Supplier dhoondo"},
    "call": {"en": "Call", "hi": "कॉल", "hinglish": "Call"},
    "nothing": {"en": "Nothing urgent to buy.",
                "hi": "अभी कुछ ज़रूरी नहीं है।",
                "hinglish": "Abhi kuch zaroori nahi."},
    "supplier_num": {"en": "Default supplier WhatsApp number",
                     "hi": "डिफ़ॉल्ट सप्लायर का WhatsApp नंबर",
                     "hinglish": "Default supplier ka WhatsApp number"},
    # ---- sell ----
    "sell_help": {"en": "Enter how many of each item sold today. Stock updates "
                        "by itself — no recounting.",
                  "hi": "आज हर सामान कितना बिका, वह लिखें। स्टॉक अपने आप घटेगा।",
                  "hinglish": "Aaj har item kitna bika wo likho. Stock khud "
                              "update ho jayega."},
    "sold_qty": {"en": "Sold", "hi": "बिका", "hinglish": "Bika"},
    "in_stock": {"en": "In stock", "hi": "स्टॉक में", "hinglish": "Stock mein"},
    "save_sales": {"en": "Save today's sales", "hi": "आज की बिक्री सेव करें",
                   "hinglish": "Aaj ki bikri save karo"},
    "got_stock": {"en": "New stock arrived? Add it here",
                  "hi": "नया माल आया? यहाँ जोड़ें",
                  "hinglish": "Naya maal aaya? Yahan add karo"},
    "received_qty": {"en": "Received", "hi": "आया", "hinglish": "Aaya"},
    "save_stock": {"en": "Add to stock", "hi": "स्टॉक में जोड़ें",
                   "hinglish": "Stock mein add karo"},
    "photo_register": {"en": "Read from register photo (auto)",
                       "hi": "रजिस्टर की फ़ोटो से पढ़ें (अपने आप)",
                       "hinglish": "Register ki photo se padho (auto)"},
    "photo_help": {"en": "Snap your handwritten sales register. We read it and "
                         "show what we found — you fix any mistakes, then save.",
                   "hi": "अपने हाथ से लिखे बिक्री रजिस्टर की फ़ोटो लें। हम पढ़कर "
                         "दिखाएँगे — आप गलती सुधारकर सेव करें।",
                   "hinglish": "Apne haath se likhe register ki photo lo. Hum "
                               "padhke dikhayenge — aap galti sudhaar ke save karo."},
    "confirm_save": {"en": "Confirm & save these sales",
                     "hi": "जाँचकर बिक्री सेव करें",
                     "hinglish": "Check karke bikri save karo"},
    "download_excel": {"en": "Download as Excel (corrected)",
                       "hi": "Excel में डाउनलोड करें (सुधारी हुई)",
                       "hinglish": "Excel download karo (corrected)"},
    "review_note": {"en": "Please check every row — handwriting is read "
                          "best-effort and is never saved without your OK.",
                    "hi": "हर पंक्ति जाँचें — हैंडराइटिंग अनुमान से पढ़ी जाती है, "
                          "आपकी मंज़ूरी के बिना कभी सेव नहीं होती।",
                    "hinglish": "Har row check karo — handwriting guess hai, "
                                "aapki permission ke bina kabhi save nahi hoti."},
}


def t(key, lang):
    return T.get(key, {}).get(lang, T.get(key, {}).get("en", key))


CANON_FIELDS = ["sku", "name", "date", "qty", "stock", "unit_cost",
                "lead_time_days", "reliability"]

# Plain-language helpers ----------------------------------------------------
RISK_ORDER = {"high": 0, "medium": 1, "low": 2}
# small coloured status dots (HTML, not emoji) for the buy list / dashboard
DOT = {"high": "#B4543A", "medium": "#C8A04B", "low": "#5C7A5E"}


def _dot(color):
    return f"<span style='color:{color};font-size:1.05em'>&#9679;</span>"


def _sku_from_name(name, taken):
    """Make a tidy unique SKU from a product name (e.g. 'Basmati Rice' -> RICE)."""
    import re
    base = re.sub(r"[^A-Za-z0-9]+", "-", (name or "").strip().upper()).strip("-")
    base = base[:14] or "ITEM"
    sku, i = base, 2
    while sku in taken:
        sku = f"{base}-{i}"; i += 1
    return sku


def _match_sku(text, products):
    """Fuzzy-match an OCR'd item name to an existing SKU; '' if no good match."""
    import difflib
    text = (text or "").strip().lower()
    if not text:
        return ""
    names = {p["sku"]: (p.get("name") or p["sku"]) for p in products}
    choices = []
    for sku, nm in names.items():
        choices.append((sku, nm.lower()))
        choices.append((sku, sku.lower()))
    best = difflib.get_close_matches(text, [c[1] for c in choices], n=1, cutoff=0.5)
    if best:
        for sku, label in choices:
            if label == best[0]:
                return sku
    return ""


def _grid_to_excel(rows):
    """Turn the corrected confirm-grid rows into an .xlsx the system can re-ingest.
    Columns match the canonical sales import (sku, name, qty, date)."""
    import io
    from datetime import date as _d
    today = _d.today().isoformat()
    out = [{
        "sku": (r.get("Match to SKU") or "").strip(),
        "name": (r.get("Item (as read)") or "").strip(),
        "qty": int(r.get("Qty sold") or 0),
        "date": today,
    } for r in rows if (r.get("Match to SKU") or r.get("Item (as read)"))]
    buf = io.BytesIO()
    pd.DataFrame(out, columns=["sku", "name", "qty", "date"]).to_excel(
        buf, index=False, sheet_name="sales")
    buf.seek(0)
    return buf.getvalue()


def _bill_text(lines, total, shop_name=""):
    """Plain-text receipt for a counter bill (download / print)."""
    from datetime import datetime as _dt
    head = (shop_name or "StockSense").strip()
    out = [head, _dt.now().strftime("%d-%m-%Y  %H:%M"), "-" * 32]
    for r in lines:
        q = int(r["Qty"] or 0)
        if q <= 0:
            continue
        price = float(r["Price"] or 0)
        name = (r["Item"] or r["sku"])[:18]
        out.append(f"{name:<18}{q:>3} x {price:>7.2f}")
        out.append(f"{'':<24}{q * price:>9.2f}")
    out += ["-" * 32, f"{'TOTAL':<18}{'Rs ' + format(total, ',.2f'):>14}",
            "", "Thank you!"]
    return "\n".join(out)


# ============================================================ AUTH GATE
def _activate_shop(user):
    """Point this session at the logged-in shop's own isolated DB."""
    st.session_state["uid"] = user["id"]
    st.session_state["username"] = user["username"]
    st.session_state["shop_name"] = user.get("shop_name") or user["username"]
    db.set_active_db(db.shop_db_path(user["id"]))
    db.init_db()


def _render_login():
    st.markdown(
        "<div class='appbar'><div class='logo'>S</div>"
        "<div><div class='brand-name'>StockSense</div>"
        "<div class='brand-sub'>Sign in to your shop</div></div></div>",
        unsafe_allow_html=True)
    tab_login, tab_signup = st.tabs(["Log in", "Create shop account"])

    with tab_login:
        with st.form("login_form"):
            u = st.text_input("Username (your phone number works)")
            p = st.text_input("Password", type="password")
            ok = st.form_submit_button("Log in", use_container_width=True)
        if ok:
            try:
                user = auth.login(u, p)
            except auth.AuthError as e:
                st.error(str(e))
            else:
                token = auth.create_session(user["id"])
                st.query_params["s"] = token
                _activate_shop(user)
                st.rerun()

    with tab_signup:
        with st.form("signup_form"):
            shop = st.text_input("Shop name", placeholder="e.g. Sharma Kirana Store")
            u2 = st.text_input("Choose a username (phone number is fine)")
            p2 = st.text_input("Choose a password (6+ characters)", type="password")
            p3 = st.text_input("Repeat password", type="password")
            ok2 = st.form_submit_button("Create account", use_container_width=True)
        if ok2:
            if p2 != p3:
                st.error("The two passwords don't match.")
            else:
                try:
                    uid = auth.signup(u2, p2, shop)
                except auth.AuthError as e:
                    st.error(str(e))
                else:
                    user = {"id": uid, "username": auth._norm(u2),
                            "shop_name": shop.strip()}
                    token = auth.create_session(uid)
                    st.query_params["s"] = token
                    _activate_shop(user)
                    st.rerun()


def _auth_gate():
    """Block the whole app until a valid session exists."""
    if "uid" in st.session_state:
        # Keep the active DB pinned across reruns within this session.
        db.set_active_db(db.shop_db_path(st.session_state["uid"]))
        return
    token = st.query_params.get("s")
    user = auth.resolve_session(token)
    if user:
        _activate_shop(user)
        return
    _render_login()
    st.stop()


_auth_gate()


# ============================================================ SIDEBAR (only nav)
with st.sidebar:
    st.markdown(
        f"<div class='nav-head'>Shop</div>"
        f"<div style='font-weight:600;margin-bottom:.5rem'>"
        f"{st.session_state.get('shop_name','')}</div>",
        unsafe_allow_html=True)
    lang_name = st.selectbox("Language", list(LANGS.keys()))
    LANG = LANGS[lang_name]
    st.divider()
    st.markdown("<div class='nav-head'>Menu</div>", unsafe_allow_html=True)
    PAGES = ["nav_dash", "nav_sell", "nav_restock", "nav_suppliers", "nav_input"]
    page = st.radio(" ", PAGES, format_func=lambda k: t(k, LANG),
                    label_visibility="collapsed")
    st.divider()
    if st.button("Load demo shop", use_container_width=True):
        seed_db(); st.session_state.pop("imported_file", None); st.rerun()

    # Start over is destructive -> require a second, explicit confirm so a
    # shopkeeper can't wipe a year of real data with one stray tap.
    if st.session_state.get("confirm_reset"):
        st.warning("This deletes ALL your products, sales and stock. Sure?")
        cc = st.columns(2)
        if cc[0].button("Yes, erase", use_container_width=True):
            db.reset_db()
            st.session_state.pop("imported_file", None)
            st.session_state.pop("confirm_reset", None)
            st.rerun()
        if cc[1].button("Cancel", use_container_width=True):
            st.session_state.pop("confirm_reset", None); st.rerun()
    else:
        if st.button("Start over", use_container_width=True):
            st.session_state["confirm_reset"] = True; st.rerun()

    st.divider()
    with st.expander("Account"):
        st.caption(f"Signed in as **{st.session_state.get('username','')}**")
        with st.form("change_pw"):
            op = st.text_input("Current password", type="password")
            np_ = st.text_input("New password (6+ chars)", type="password")
            if st.form_submit_button("Change password"):
                try:
                    auth.change_password(st.session_state["uid"], op, np_)
                    st.success("Password changed.")
                except auth.AuthError as e:
                    st.error(str(e))
        if st.button("Log out", use_container_width=True):
            auth.destroy_session(st.query_params.get("s"))
            st.query_params.clear()
            for k in ("uid", "username", "shop_name"):
                st.session_state.pop(k, None)
            st.rerun()

st.markdown(
    "<div class='appbar'><div class='logo'>S</div>"
    "<div><div class='brand-name'>StockSense</div>"
    f"<div class='brand-sub'>{t('tagline', LANG)}</div></div></div>",
    unsafe_allow_html=True)

have_data = bool(db.get_products())


def _need_data_hint():
    st.info("No shop yet. Click **Load demo shop** in the sidebar, or go to "
            "**Inventory input** to upload your file or add items.")


# ============================================================ PAGE: DASHBOARD
def page_dashboard(report):
    if not have_data:
        _need_data_hint(); return
    low = sum(1 for r in report
              if r["reorder"]["stockout_risk"] in ("high", "medium"))
    total_units = sum(int(r["on_hand"]) for r in report)
    m = st.columns(3)
    m[0].metric("Items", len(report))
    m[1].metric("Total units in stock", f"{total_units:,}")
    m[2].metric("Running low", low)

    st.subheader("Sales over time")
    sales = db.get_sales()
    if sales:
        sdf = pd.DataFrame(sales)
        daily = sdf.groupby("date")["qty"].sum()
        st.line_chart(daily, height=260, color="#33503F")
        st.caption("Total units sold per day across all items.")
    else:
        st.caption("No sales logged yet — record some under **Record sales**.")

    st.subheader("Current stock levels")
    inv = sorted(report, key=lambda r: r["on_hand"], reverse=True)
    bar = pd.DataFrame(
        {"In stock": [int(r["on_hand"]) for r in inv]},
        index=[r["name"] or r["sku"] for r in inv])
    st.bar_chart(bar, height=320, color="#33503F")
    st.markdown(
        f"<div style='font-size:.82rem;color:#6E7A6C'>"
        f"{_dot(DOT['high'])} buy now &nbsp; {_dot(DOT['medium'])} getting low "
        f"&nbsp; {_dot(DOT['low'])} fine for now (see Restocking)</div>",
        unsafe_allow_html=True)

    _ai_analysis_panel(report)


def _ai_analysis_panel(report):
    """Shop-level read from the neural forecaster: trend, momentum, weekday shape."""
    ai_rows = [r for r in report if (r["forecast"].get("ai_analysis"))]
    if not ai_rows:
        return
    st.subheader("AI sales analysis")
    st.caption("A small neural net, trained on your whole shop's history, "
               "reads the trend, weekly rhythm and recent momentum behind every item.")

    rising = sorted((r for r in ai_rows
                     if r["forecast"]["ai_analysis"]["trend_dir"] == "rising"),
                    key=lambda r: -r["forecast"]["ai_analysis"]["trend_pct_month"])
    falling = sorted((r for r in ai_rows
                      if r["forecast"]["ai_analysis"]["trend_dir"] == "falling"),
                     key=lambda r: r["forecast"]["ai_analysis"]["trend_pct_month"])

    c = st.columns(2)
    with c[0]:
        st.markdown("**Picking up speed**")
        if rising:
            for r in rising[:4]:
                a = r["forecast"]["ai_analysis"]
                st.markdown(f"{_dot(DOT['low'])} **{r['name'] or r['sku']}** "
                            f"&nbsp;+{a['trend_pct_month']:.0f}%/mo",
                            unsafe_allow_html=True)
        else:
            st.caption("Nothing trending up right now.")
    with c[1]:
        st.markdown("**Slowing down**")
        if falling:
            for r in falling[:4]:
                a = r["forecast"]["ai_analysis"]
                st.markdown(f"{_dot(DOT['high'])} **{r['name'] or r['sku']}** "
                            f"&nbsp;{a['trend_pct_month']:.0f}%/mo",
                            unsafe_allow_html=True)
        else:
            st.caption("Nothing fading right now.")

    # shop-wide weekly rhythm (average the per-item weekday shapes)
    import numpy as _np
    dows = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    stacked = _np.array([[r["forecast"]["ai_analysis"]["weekly_shape"][d]
                          for d in dows] for r in ai_rows])
    shop_week = stacked.sum(axis=0)
    busiest = dows[int(shop_week.argmax())]
    st.markdown(f"**Busiest day across the shop: {busiest}** — "
                "stock up the day before.")
    import altair as alt
    wk_df = pd.DataFrame({"Day": dows, "Predicted units": shop_week})
    chart = (alt.Chart(wk_df).mark_bar(color="#33503F")
             .encode(x=alt.X("Day:N", sort=dows, title=None),
                     y=alt.Y("Predicted units:Q", title=None))
             .properties(height=220))
    st.altair_chart(chart, use_container_width=True)

    with st.expander("Per-item AI read"):
        st.dataframe(pd.DataFrame([{
            "Item": r["name"] or r["sku"],
            "AI forecast/day": r["forecast"]["daily_rate"],
            "Trend/mo": f"{r['forecast']['ai_analysis']['trend_pct_month']:+.0f}%",
            "Last-week momentum": f"{r['forecast']['ai_analysis']['momentum_pct']:+.0f}%",
            "Busiest day": r["forecast"]["ai_analysis"]["busiest_day"],
        } for r in ai_rows]), use_container_width=True, hide_index=True)


# ============================================================ PAGE: RECORD SALES
def page_sell(report):
    if not have_data:
        _need_data_hint(); return
    st.subheader(t("nav_sell", LANG))

    # ---- COUNTER BILL: search an item -> build a bill -> save (auto-deducts) --
    st.markdown("### New bill")
    st.caption("Search an item, add it to the bill. Saving the bill prints a "
               "receipt, records the sales and updates your stock.")
    cart = st.session_state.setdefault("bill_cart", {})   # sku -> {name,price,qty}

    opts = sorted(report, key=lambda r: (r["name"] or r["sku"]).lower())

    def _opt_label(r):
        return (f"{r['name'] or r['sku']}  ·  {r['sku']}  ·  "
                f"stock {int(r['on_hand'])}  ·  ₹{float(r['unit_cost'] or 0):,.2f}")

    sc = st.columns([5, 1, 2])
    pick = sc[0].selectbox(
        "Search product", options=[None] + opts,
        format_func=lambda r: "Type to search a product…" if r is None
        else _opt_label(r), key="bill_pick", label_visibility="collapsed")
    add_qty = sc[1].number_input("Qty", min_value=1, step=1, value=1,
                                 key="bill_qty", label_visibility="collapsed")
    if sc[2].button("Add to bill", type="primary", use_container_width=True) \
            and pick is not None:
        sku = pick["sku"]
        line = cart.get(sku, {"name": pick["name"] or sku,
                              "price": float(pick["unit_cost"] or 0), "qty": 0})
        line["qty"] += int(add_qty)
        cart[sku] = line
        st.rerun()

    if cart:
        rows = [{"sku": s, "Item": l["name"], "Price": l["price"],
                 "Qty": l["qty"]} for s, l in cart.items()]
        edited = st.data_editor(
            rows, use_container_width=True, hide_index=True, key="bill_editor",
            column_config={
                "sku": None,
                "Item": st.column_config.TextColumn(disabled=True),
                "Price": st.column_config.NumberColumn(
                    "Price ₹", min_value=0.0, step=1.0, format="₹%.2f"),
                "Qty": st.column_config.NumberColumn(min_value=0, step=1),
            })
        # keep edits so they survive the next add-to-bill rerun
        for r in edited:
            if r["sku"] in cart:
                cart[r["sku"]]["price"] = float(r["Price"] or 0)
                cart[r["sku"]]["qty"] = int(r["Qty"] or 0)
        total = sum(float(r["Price"] or 0) * int(r["Qty"] or 0) for r in edited)
        st.markdown(f"#### Bill total: ₹{total:,.2f}")
        bc = st.columns([2, 2, 1])
        if bc[0].button("Save bill & update stock", type="primary",
                        use_container_width=True):
            n = 0
            for r in edited:
                q = int(r["Qty"] or 0)
                if r["sku"] and q > 0:
                    db.record_sale(r["sku"], q); n += 1
            st.session_state["bill_cart"] = {}
            st.success(f"Bill saved · {n} item(s) · ₹{total:,.2f}. Stock updated.")
            st.rerun()
        bc[1].download_button(
            "Download receipt",
            data=_bill_text(edited, total, db.get_setting("shop_name", "")),
            file_name="bill.txt", mime="text/plain",
            use_container_width=True)
        if bc[2].button("Clear", use_container_width=True):
            st.session_state["bill_cart"] = {}
            st.rerun()
    else:
        st.caption("No items on the bill yet.")

    st.divider()

    # ---- AUTOMATED PATH: photo of handwritten register -> confirm grid ----
    with st.expander(t("photo_register", LANG), expanded=False):
        st.caption(t("photo_help", LANG))
        # OCR pulls in heavy/optional deps (opencv, an OCR engine). On a slim
        # free host they may be absent — degrade gracefully instead of crashing
        # the whole page so the rest of the app still works.
        try:
            from core.adapters.ocr_handwritten import HandwrittenRegisterOCRAdapter
        except Exception:
            st.info("Photo reading isn't available on this server yet. "
                    "Use the manual entry below, or upload an Excel/CSV under "
                    "**Inventory input**.")
            HandwrittenRegisterOCRAdapter = None
        src = st.radio("photo source", ["Take photo", "Upload photo"],
                       horizontal=True, label_visibility="collapsed")
        img = (st.camera_input("Register photo") if src == "Take photo"
               else st.file_uploader("Register photo", type=["jpg", "jpeg", "png"]))
        if img is not None and HandwrittenRegisterOCRAdapter is not None:
            with st.spinner("Reading your register…"):
                batch = HandwrittenRegisterOCRAdapter().normalize(img.getvalue())
            for w in batch.warnings:
                st.info(w)
            st.warning(t("review_note", LANG))
            products = db.get_products()
            sku_opts = [""] + [p["sku"] for p in products]
            rows = batch.meta.get("rows", [])
            seed = [{
                "Item (as read)": r.get("item", ""),
                "Match to SKU": _match_sku(r.get("item", ""), products),
                "Qty sold": int(r.get("qty", 0) or 0),
                "Confidence": f"{r.get('confidence', 0):.0%}",
            } for r in rows] or [{"Item (as read)": "", "Match to SKU": "",
                                  "Qty sold": 0, "Confidence": ""}]
            edited = st.data_editor(
                seed, num_rows="dynamic", use_container_width=True,
                column_config={
                    "Match to SKU": st.column_config.SelectboxColumn(
                        options=sku_opts, required=False),
                    "Qty sold": st.column_config.NumberColumn(min_value=0, step=1),
                    "Confidence": st.column_config.TextColumn(disabled=True),
                }, key="ocr_grid")
            bcols = st.columns([2, 2])
            if bcols[0].button(t("confirm_save", LANG), type="primary"):
                n = 0
                for row in edited:
                    sku = row.get("Match to SKU") or ""
                    qty = row.get("Qty sold") or 0
                    if sku and qty > 0:
                        db.record_sale(sku, qty); n += 1
                st.success(f"Saved {n} sale(s).")
                st.rerun()
            bcols[1].download_button(
                t("download_excel", LANG), data=_grid_to_excel(edited),
                file_name="register_sales.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    st.divider()
    st.caption(t("sell_help", LANG))
    with st.form("sell_form"):
        sold = {}
        for r in report:
            item = r["name"] or r["sku"]
            cc = st.columns([4, 2])
            cc[0].markdown(f"**{item}**  \n{t('in_stock', LANG)}: "
                           f"{int(r['on_hand'])}")
            sold[r["sku"]] = cc[1].number_input(
                t("sold_qty", LANG), min_value=0, step=1, value=0,
                key=f"sell_{r['sku']}")
        if st.form_submit_button(t("save_sales", LANG), type="primary"):
            n = 0
            for sku, q in sold.items():
                if q and q > 0:
                    db.record_sale(sku, q); n += 1
            st.success(f"Saved {n} sale(s).") if n else st.info("Nothing entered.")
            st.rerun()

    with st.expander(t("got_stock", LANG)):
        with st.form("recv_form"):
            recv = {}
            for r in report:
                item = r["name"] or r["sku"]
                cc = st.columns([4, 2])
                cc[0].markdown(f"**{item}**")
                recv[r["sku"]] = cc[1].number_input(
                    t("received_qty", LANG), min_value=0, step=1, value=0,
                    key=f"recv_{r['sku']}")
            if st.form_submit_button(t("save_stock", LANG)):
                n = 0
                for sku, q in recv.items():
                    if q and q > 0:
                        db.receive_stock(sku, q); n += 1
                st.success(f"Added stock for {n} item(s).") if n \
                    else st.info("Nothing entered.")
                st.rerun()


# ============================================================ PAGE: RESTOCKING
def page_restock(report):
    if not have_data:
        _need_data_hint(); return
    default_num = db.get_setting("supplier_phone", "")
    shop_name = db.get_setting("shop_name", "")

    plan_full = cash_view(report)[0]
    full_cost = plan_full["reorder_all_cost"]

    st.subheader("How much can you spend on stock right now?")
    c = st.columns([3, 1])
    budget = c[0].slider("Your budget today (₹)", 0, int(full_cost) + 1000,
                         int(full_cost), step=500,
                         help="Drag down if cash is tight. We'll buy the most "
                              "important items first.")
    c[1].metric("Buy-everything cost", f"₹{full_cost:,.0f}")

    plan, guard = cash_view(report, cash_cap=budget, cash_on_hand=budget)

    m = st.columns(3)
    m[0].metric("Your shopping list", f"₹{plan['lean_cost']:,.0f}")
    m[1].metric("Items to buy", len([l for l in plan["chosen"] if l.qty > 0]))
    m[2].metric("Cash saved vs buying all", f"₹{plan['cash_saved']:,.0f}")

    if guard["triggered"]:
        st.warning("Cash looks tight and some items are selling slower. "
                   "We're holding back the non-urgent ones to protect your money.")

    st.markdown(f"### {t('buy_these', LANG)}")
    buy = [l for l in plan["chosen"] if l.qty > 0]
    if not buy:
        st.success(t("nothing", LANG))
    else:
        # ---- group the order by the supplier each item is assigned to ----
        groups = {}   # key -> {"name","phone","items":[...]}
        for l in buy:
            key = l.supplier_name or "__default__"
            g = groups.setdefault(key, {
                "name": l.supplier_name or "Default supplier",
                "phone": l.supplier_phone or default_num, "items": []})
            g["items"].append(l)

        for g in groups.values():
            items = [(l.name or l.sku, l.qty) for l in g["items"]]
            total = sum(l.cost for l in g["items"])
            st.markdown(f"**{g['name']}** · {len(items)} item(s) · "
                        f"₹{total:,.0f}")
            wa = whatsapp_link(g["phone"], items, shop_name or None, LANG)
            oc = st.columns([2, 1])
            oc[0].link_button(t("order_all", LANG), wa, type="primary",
                              use_container_width=True)
            tl = tel_link(g["phone"]) if g["phone"] else ""
            if tl:
                oc[1].link_button(t("call", LANG), tl, use_container_width=True)
            elif not g["phone"]:
                oc[1].caption("Set this supplier's number under Suppliers.")

            for l in g["items"]:
                item = l.name or l.sku
                dot = _dot(DOT.get(l.stockout_risk, DOT["medium"]))
                cols = st.columns([3, 2, 3])
                cols[0].markdown(f"{dot} **{item}** — buy **{int(l.qty)}** · "
                                 f"₹{l.cost:,.0f}", unsafe_allow_html=True)
                cols[1].link_button(
                    t("order", LANG),
                    whatsapp_link(g["phone"], [(item, l.qty)],
                                  shop_name or None, LANG),
                    use_container_width=True)
                with cols[2].popover(t("find", LANG),
                                     use_container_width=True):
                    for mname, url in marketplace_links(item).items():
                        st.link_button(mname, url, use_container_width=True)
            st.divider()

    if plan["high_risk_skipped"]:
        st.markdown("### Couldn't fit in your budget — but these run out soon")
        st.table(pd.DataFrame([{
            "Item": l.name or l.sku, "Still need": int(l.qty),
            "Would cost": f"₹{l.cost:,.0f}"} for l in plan["high_risk_skipped"]]))
        st.caption("Raise your budget above, or buy these as soon as you can.")

    slow = plan["slow_movers"]
    if slow:
        st.markdown("### Don't restock these — they're barely selling")
        st.table(pd.DataFrame([{"Item": l.name or l.sku} for l in slow]))
        st.caption("Money spent here just sits on your shelf.")

    st.caption("Nothing is ordered automatically — this is just your suggested "
               "list. You decide and buy.")


# ============================================================ PAGE: SUPPLIERS
def page_suppliers():
    st.subheader(t("nav_suppliers", LANG))

    # ---- default fallback number + shop name (settings) ----
    with st.expander("Default supplier & shop name", expanded=False):
        cur_num = db.get_setting("supplier_phone", "")
        cur_shop = db.get_setting("shop_name", "")
        num = st.text_input(t("supplier_num", LANG), value=cur_num,
                            placeholder="9198XXXXXXXX")
        shop = st.text_input("Shop name (optional)", value=cur_shop)
        if num != cur_num:
            db.set_setting("supplier_phone", num)
        if shop != cur_shop:
            db.set_setting("shop_name", shop)
        st.caption("Used for items that aren't assigned to a specific supplier.")

    if not have_data:
        _need_data_hint()

    # ---- the named suppliers list (add / edit / delete) ----
    st.markdown("### Your suppliers")
    suppliers = db.get_supplier_master()
    for s in suppliers:
        with st.expander(f"{s['name']}"
                         + (f" · {s['phone']}" if s['phone'] else "")):
            with st.form(f"sup_{s['id']}"):
                cc = st.columns(2)
                nm = cc[0].text_input("Name", value=s["name"])
                ph = cc[1].text_input("WhatsApp / phone", value=s["phone"] or "")
                cc2 = st.columns(2)
                lt = cc2[0].number_input("Days to deliver", min_value=0.0,
                                         value=float(s["lead_time_days"] or 7))
                rel = cc2[1].slider("Reliability", 0.5, 1.0,
                                    float(s["reliability"] or 0.95), 0.01)
                bc = st.columns(2)
                if bc[0].form_submit_button("Save", type="primary"):
                    db.update_supplier(s["id"], nm, ph, lt, rel)
                    st.success("Saved"); st.rerun()
                if bc[1].form_submit_button("Delete"):
                    db.delete_supplier(s["id"])
                    st.warning(f"Removed {s['name']}"); st.rerun()

    products = db.get_products()
    prod_label = {p["sku"]: (p.get("name") or p["sku"]) for p in products}
    label_sku = {v: k for k, v in prod_label.items()}
    with st.form("add_sup"):
        st.markdown("**Add a new supplier**")
        cc = st.columns(2)
        nm = cc[0].text_input("Supplier name (e.g. Sharma Distributors)")
        ph = cc[1].text_input("WhatsApp / phone", placeholder="9198XXXXXXXX")
        cc2 = st.columns(2)
        lt = cc2[0].number_input("Days to deliver", min_value=0.0, value=7.0)
        rel = cc2[1].slider("Reliability", 0.5, 1.0, 0.95, 0.01)
        picked = st.multiselect(
            "Which items do you buy from this supplier?",
            list(label_sku.keys()),
            help="Pick items already in your shop. Reorders for these go to "
                 "this supplier. You can change it any time below.") \
            if products else []
        new_names = st.text_input(
            "Add new product name(s) for this supplier",
            placeholder="e.g. Basmati Rice 5kg, Sunflower Oil 1L",
            help="Type product names (comma-separated) this supplier provides. "
                 "We'll create them and link them to this supplier.")
        if st.form_submit_button("Add supplier", type="primary") and nm:
            sid = db.add_supplier(nm, ph, lt, rel)
            for lbl in picked:
                db.assign_product_supplier(label_sku[lbl], sid)
            # create any typed-in products, then link them to this supplier
            taken = {p["sku"] for p in products}
            created = 0
            for raw in new_names.split(","):
                pname = raw.strip()
                if not pname:
                    continue
                new_sku = _sku_from_name(pname, taken)
                taken.add(new_sku)
                db.upsert_products([{"sku": new_sku, "name": pname,
                                     "unit_cost": 0}])
                db.assign_product_supplier(new_sku, sid)
                created += 1
            linked = len(picked) + created
            st.success(f"Added {nm}"
                       + (f" · linked {linked} item(s)" if linked else ""))
            st.rerun()

    # ---- assign one supplier per product ----
    if have_data and suppliers:
        st.divider()
        st.markdown("### Who do you buy each item from?")
        st.caption("Pick a supplier for each item. Its reorders go to that "
                   "supplier (and use their delivery time) until you change it.")
        products = db.get_products()
        psup = db.get_product_supplier_map()
        name_to_id = {s["name"]: s["id"] for s in suppliers}
        id_to_name = {s["id"]: s["name"] for s in suppliers}
        opts = [""] + [s["name"] for s in suppliers]
        seed = [{
            "Item": p.get("name") or p["sku"],
            "_sku": p["sku"],
            "Supplier": id_to_name.get((psup.get(p["sku"]) or {}).get("id"), ""),
        } for p in products]
        edited = st.data_editor(
            seed, use_container_width=True, hide_index=True, key="assign_grid",
            column_config={
                "Item": st.column_config.TextColumn(disabled=True),
                "_sku": None,
                "Supplier": st.column_config.SelectboxColumn(options=opts),
            })
        if st.button("Save assignments", type="primary"):
            for row in edited:
                sid = name_to_id.get(row.get("Supplier") or "")
                db.assign_product_supplier(row["_sku"], sid)
            st.success("Saved who supplies each item"); st.rerun()


# ============================================================ PAGE: INVENTORY IN
def _upload_flow():
    """Excel/CSV upload with auto column-mapping. Takes over the page while a
    new file is being confirmed."""
    up = st.file_uploader("Upload Excel or CSV", type=["xlsx", "xls", "csv"],
                          key="inv_upload")
    file_tag = (up.name, up.size) if up is not None else None
    already = st.session_state.get("imported_file") == file_tag
    if up is None or already:
        return
    st.markdown("#### Reading your file")
    ad = TabularAdapter()
    df = ad.read(up)
    st.write("First few rows we saw:")
    st.dataframe(df.head(8), use_container_width=True)
    mapping = ad.suggest_mapping(df, CANON_FIELDS)
    nice = {"sku": "Item code/ID", "name": "Item name", "date": "Sale date",
            "qty": "Quantity sold", "stock": "Stock left now",
            "unit_cost": "Cost price"}
    st.write("**We figured out your columns automatically.** Fix any if wrong:")
    cols = ["(none)"] + list(df.columns)
    corrected = {}
    g = st.columns(3)
    for i, f in enumerate(["sku", "name", "date", "qty", "stock", "unit_cost"]):
        with g[i % 3]:
            guess = mapping[f]["column"]
            idx = cols.index(guess) if guess in cols else 0
            tick = "✓ " if guess else ""
            sel = st.selectbox(f"{tick}{nice[f]}", cols, index=idx, key=f"m_{f}")
            if sel != "(none)":
                corrected[f] = {"column": sel, "confidence": 1.0}
    if st.button("Looks right — load my shop", type="primary"):
        b = ad.normalize(df, corrected)
        if not b.products:
            st.error("Couldn't read any items — check the **Item code/ID** column.")
            for w in b.warnings:
                st.info(w)
            return
        db.upsert_products(b.products)
        if b.sales:     db.insert_sales(b.sales)
        if b.inventory: db.upsert_inventory(b.inventory)
        if b.suppliers: db.upsert_suppliers(b.suppliers)
        st.session_state["imported_file"] = file_tag
        st.success(f"Loaded {len(b.products)} items and {len(b.sales)} sales.")
        st.rerun()


def page_input():
    st.subheader(t("nav_input", LANG))

    # ---- 1. set current stock for existing items (the core "input" task) ----
    products = db.get_products()
    if products:
        st.markdown("### Set what's on the shelf right now")
        inv = {i["sku"]: i["on_hand"] for i in db.get_inventory()}
        seed = [{"Item": p.get("name") or p["sku"], "_sku": p["sku"],
                 "In stock now": int(inv.get(p["sku"], 0) or 0)} for p in products]
        edited = st.data_editor(
            seed, use_container_width=True, hide_index=True, key="stock_grid",
            column_config={
                "Item": st.column_config.TextColumn(disabled=True),
                "_sku": None,
                "In stock now": st.column_config.NumberColumn(min_value=0, step=1),
            })
        if st.button("Save stock counts", type="primary"):
            db.upsert_inventory([{"sku": r["_sku"], "stock": r["In stock now"]}
                                 for r in edited])
            st.success("Stock updated"); st.rerun()
        st.divider()

    # ---- 2. add a single item by hand ----
    with st.expander("Add or update one item by hand",
                     expanded=not products):
        with st.form("manual"):
            c = st.columns(2)
            sku = c[0].text_input("Item code (e.g. RICE-5KG)")
            name = c[1].text_input("Item name (e.g. Basmati Rice 5kg)")
            c2 = st.columns(3)
            stock = c2[0].number_input("In stock now", min_value=0.0, value=0.0)
            cost = c2[1].number_input("Cost price (₹)", min_value=0.0, value=0.0)
            lead = c2[2].number_input("Days to restock", min_value=0.0, value=7.0)
            st.caption("Optional: log a recent sale so we learn how fast it sells.")
            c3 = st.columns(2)
            sdate = c3[0].date_input("Sale date", value=None)
            sqty = c3[1].number_input("How many sold that day", min_value=0.0,
                                      value=0.0)
            if st.form_submit_button("Save item", type="primary") and sku:
                raw = {"products": [{"sku": sku, "name": name, "unit_cost": cost}],
                       "inventory": [{"sku": sku, "stock": stock}],
                       "suppliers": [{"sku": sku, "lead_time_days": lead,
                                      "reliability": 0.95}]}
                if sdate and sqty:
                    raw["sales"] = [{"sku": sku, "date": sdate.isoformat(),
                                     "qty": sqty}]
                b = ManualAdapter().normalize(raw)
                db.upsert_products(b.products); db.upsert_inventory(b.inventory)
                db.upsert_suppliers(b.suppliers)
                if b.sales:
                    db.insert_sales(b.sales)
                st.success(f"Saved {name or sku}"); st.rerun()

    # ---- 3. upload a file (auto column-mapping) ----
    with st.expander("Upload an Excel / CSV file", expanded=not products):
        _upload_flow()
        st.caption("No file handy? Make a sample messy one to try the upload:")
        if st.button("Make a sample file"):
            p = write_messy_excel()
            with open(p, "rb") as f:
                st.download_button("Download sample.xlsx", f,
                                   file_name="sample.xlsx")

    # ---- 4. hands-off auto-sync ----
    with st.expander("Auto-sync from billing software (hands-off)"):
        from pathlib import Path
        from core.adapters.pos import REGISTRY
        inbox = Path(__file__).resolve().parent / "inbox"
        inbox.mkdir(exist_ok=True)
        st.markdown(f"Export sales/stock into this folder and the scheduler "
                    f"ingests it automatically:\n\n`{inbox}`")
        waiting = [p.name for p in inbox.iterdir()
                   if p.is_file() and p.suffix.lower() in (".xlsx", ".xls", ".csv")]
        st.write(f"Files waiting: **{len(waiting)}**"
                 + (f" ({', '.join(waiting)})" if waiting else ""))
        if st.button("Sync now", type="primary"):
            conn = REGISTRY["inbox"]({"folder": str(inbox)})
            batch = conn.sync()
            if batch.products: db.upsert_products(batch.products)
            if batch.sales: db.insert_sales(batch.sales)
            if batch.inventory: db.upsert_inventory(batch.inventory)
            st.success(f"Synced {batch.meta.get('files', 0)} file(s): "
                       f"{len(batch.products)} items, {len(batch.sales)} sales.")
            for w in batch.warnings: st.warning(w)
            st.rerun()
        st.code("./schedule_mac.sh install        # every 6h (default)\n"
                "INTERVAL_HOURS=1 ./schedule_mac.sh install   # hourly\n"
                "./schedule_mac.sh uninstall       # stop", language="bash")
        status = {"inbox": "Working now (folder export)",
                  "tally": "Real — needs Tally running (localhost:9000)",
                  "vyapar": "Needs API key — use inbox export meanwhile",
                  "marg": "Planned — use inbox export",
                  "busy": "Planned — use inbox export"}
        st.table(pd.DataFrame([{"Billing software": n.title(),
                                "Status": status.get(n, "")} for n in REGISTRY]))


# ============================================================ DISPATCH
_needs_report = page in ("nav_dash", "nav_sell", "nav_restock")
report = []
if have_data and _needs_report:
    report = build_report()
    report.sort(key=lambda r: RISK_ORDER.get(r["reorder"]["stockout_risk"], 3))

if page == "nav_dash":
    page_dashboard(report)
elif page == "nav_sell":
    page_sell(report)
elif page == "nav_restock":
    page_restock(report)
elif page == "nav_suppliers":
    page_suppliers()
elif page == "nav_input":
    page_input()
