"""Close the loop — turn a reorder suggestion into a real PURCHASE action.

This is the moat: not "you should reorder 50 units" but a button that actually
places/sends the order. No paid APIs needed:

  * WhatsApp one-tap order to the shop's existing distributor (kiranas already
    order on WhatsApp) — pre-fills the exact item + qty list.
  * Deep links to B2B sourcing marketplaces (Udaan / IndiaMART / Amazon
    Business / JioMart) searched for the item.
  * Tap-to-call the supplier.

Returns plain URLs the UI renders as buttons; nothing is sent automatically.
"""
import re
import urllib.parse

# WHOLESALE / B2B sourcing only — kiranas buy from distributors, never D2C
# retail (Amazon/Flipkart excluded). App-only sites like Udaan 404 on the web,
# so only stable wholesale web-search endpoints are kept.
MARKETPLACES = {
    "IndiaMART": "https://dir.indiamart.com/search.mp?ss={q}",
    "TradeIndia": "https://www.tradeindia.com/search.html?keyword={q}",
    "Find wholesaler": "https://www.google.com/search?q={q}+wholesale+distributor",
}


def _digits(phone: str) -> str:
    """Keep digits only; assume India (91) if a 10-digit number is given."""
    d = re.sub(r"\D", "", phone or "")
    if len(d) == 10:
        d = "91" + d
    return d


def marketplace_links(item_name: str) -> dict:
    q = urllib.parse.quote_plus(item_name or "")
    return {name: url.format(q=q) for name, url in MARKETPLACES.items()}


def build_order_message(items, shop_name=None, lang="en") -> str:
    """items = list of (name, qty). Returns a ready-to-send order text."""
    head = {
        "en": "Hello, please send the following stock:",
        "hi": "नमस्ते, कृपया यह सामान भेजें:",
        "hinglish": "Namaste, ye stock bhej dijiye:",
    }.get(lang, "Hello, please send the following stock:")
    foot = {"en": "Thank you.", "hi": "धन्यवाद।",
            "hinglish": "Dhanyavaad."}.get(lang, "Thank you.")
    lines = [head]
    for name, qty in items:
        lines.append(f"- {name} x {int(qty)}")
    if shop_name:
        foot = f"{foot}\n- {shop_name}"
    lines.append(foot)
    return "\n".join(lines)


def whatsapp_link(phone: str, items, shop_name=None, lang="en") -> str:
    """One-tap WhatsApp order. If phone is blank, opens WhatsApp with the
    message pre-filled so the owner picks the contact themselves."""
    msg = build_order_message(items, shop_name, lang)
    text = urllib.parse.quote(msg)
    d = _digits(phone)
    return f"https://wa.me/{d}?text={text}" if d else f"https://wa.me/?text={text}"


def tel_link(phone: str) -> str:
    d = _digits(phone)
    return f"tel:+{d}" if d else ""
