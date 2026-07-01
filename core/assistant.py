"""Grounded business Q&A assistant ("Ask StockSense").

Answers plain-language questions about sales projections, profit margins,
best/worst sellers, dead stock and reorder needs.

Design choice: this is a *grounded retrieval* assistant, NOT an LLM wrapper.
Every number it says is COMPUTED from the shop's real data (sales velocity,
unit cost, selling price). It builds a set of "fact cards" from the live
report, indexes them with a from-scratch TF-IDF model, and returns the
card(s) most relevant to the question. That means it can never hallucinate a
margin or a projection — if the data isn't there, it says so.
"""
from __future__ import annotations
import math
import re
from collections import Counter

from . import db
from .engine import build_report

_WORD = re.compile(r"[a-z0-9]+")

# tiny stopword list — keep it small so product words survive
_STOP = {
    "the", "a", "an", "of", "for", "to", "in", "on", "is", "are", "my", "our",
    "me", "i", "we", "what", "whats", "how", "much", "many", "do", "does",
    "will", "can", "could", "should", "and", "or", "with", "this", "that",
    "it", "its", "be", "am", "at", "by", "s",
}


def _tok(text: str):
    return [w for w in _WORD.findall(text.lower()) if w not in _STOP]


def _inr(x):
    return f"\u20b9{x:,.0f}"


# --------------------------------------------------------------------------
# Fact-card construction (this is the "knowledge" the assistant retrieves).
# --------------------------------------------------------------------------
def build_facts(db_path=None):
    """Compute grounded fact cards from live data. Returns list of
    {keywords, answer} dicts. `keywords` feeds retrieval; `answer` is shown."""
    report = build_report(db_path=db_path)
    products = {p["sku"]: p for p in db.get_products(db_path)}

    cards = []
    per_sku = []
    tot_rev_y = tot_profit_y = tot_cost_tied = 0.0
    priced = 0

    for r in report:
        sku = r["sku"]
        name = r["name"] or sku
        rate = float(r["reorder"]["daily_rate"] or 0)        # units/day
        cost = float(r["unit_cost"] or 0)
        sell = float(products.get(sku, {}).get("sell_price", 0) or 0)
        units_y = rate * 365.0
        units_m = rate * 30.0
        margin_u = sell - cost
        margin_pct = (margin_u / sell * 100.0) if sell > 0 else 0.0
        rev_y = units_y * sell
        profit_y = units_y * margin_u
        on_hand = float(r["on_hand"] or 0)
        risk = r["reorder"]["stockout_risk"]
        qty = int(r["reorder"]["suggested_qty"] or 0)

        if sell > 0:
            priced += 1
            tot_rev_y += rev_y
            tot_profit_y += profit_y
        tot_cost_tied += qty * cost

        per_sku.append({
            "sku": sku, "name": name, "rate": rate, "cost": cost, "sell": sell,
            "units_y": units_y, "units_m": units_m, "margin_u": margin_u,
            "margin_pct": margin_pct, "rev_y": rev_y, "profit_y": profit_y,
            "on_hand": on_hand, "risk": risk, "qty": qty,
        })

        if sell > 0:
            ptoks = set(_tok(f"{name} {sku}"))
            cards.append({
                "scope": ptoks,
                "keywords": f"{name} {sku} profit margin markup earn earnings "
                            f"selling price cost make money per unit",
                "answer": (
                    f"**{name}** — buy at {_inr(cost)}, sell at {_inr(sell)}. "
                    f"Margin {_inr(margin_u)}/unit ({margin_pct:.0f}%). "
                    f"At the current pace of {rate:.1f}/day that's about "
                    f"{_inr(profit_y)} profit a year."),
            })
            cards.append({
                "scope": ptoks,
                "keywords": f"{name} {sku} yearly annual monthly projection "
                            f"forecast sales revenue turnover units sell",
                "answer": (
                    f"**{name}** projection: about {units_m:.0f} units/month, "
                    f"{units_y:.0f} units/year \u2192 roughly {_inr(rev_y)} in "
                    f"annual sales at {_inr(sell)} each."),
            })

    # ---- shop-wide aggregate cards ----
    overall_margin = (tot_profit_y / tot_rev_y * 100.0) if tot_rev_y > 0 else 0.0
    priced_skus = [p for p in per_sku if p["sell"] > 0]

    cards.append({
        "keywords": "yearly annual projection forecast total sales revenue "
                    "turnover income how much year projected whole shop overall",
        "answer": (
            f"**Projected annual sales: {_inr(tot_rev_y)}** across "
            f"{priced} product(s), based on current daily selling pace. "
            f"That works out to roughly {_inr(tot_rev_y/12)} a month."),
    })
    cards.append({
        "keywords": "profit margin annual yearly total earnings money make "
                    "net overall bottom line how much profit",
        "answer": (
            f"**Projected annual profit: {_inr(tot_profit_y)}** "
            f"(overall margin {overall_margin:.0f}%). "
            f"About {_inr(tot_profit_y/12)} profit a month at the current pace."),
    })

    if priced_skus:
        best_rev = max(priced_skus, key=lambda p: p["rev_y"])
        best_profit = max(priced_skus, key=lambda p: p["profit_y"])
        best_margin = max(priced_skus, key=lambda p: p["margin_pct"])
        worst_margin = min(priced_skus, key=lambda p: p["margin_pct"])
        cards.append({
            "keywords": "best top biggest seller highest revenue earner "
                        "most sales popular star product bestseller",
            "answer": (
                f"Your top earner is **{best_rev['name']}** at about "
                f"{_inr(best_rev['rev_y'])}/year in sales, and your biggest "
                f"profit driver is **{best_profit['name']}** "
                f"({_inr(best_profit['profit_y'])}/year profit)."),
        })
        cards.append({
            "keywords": "highest lowest best worst margin markup most "
                        "profitable least profitable percentage",
            "answer": (
                f"Highest margin: **{best_margin['name']}** "
                f"({best_margin['margin_pct']:.0f}%). "
                f"Thinnest margin: **{worst_margin['name']}** "
                f"({worst_margin['margin_pct']:.0f}%)."),
        })

    dead = [p for p in per_sku if p["rate"] < 0.15]
    if dead:
        names = ", ".join(p["name"] for p in dead[:5])
        cards.append({
            "keywords": "dead slow stock not selling stuck money tied "
                        "clear clearance stagnant unsold moving overstock",
            "answer": (
                f"Barely-moving stock: **{names}**. Selling almost nothing per "
                f"day \u2014 consider a discount to free up cash."),
        })

    need = [p for p in per_sku if p["qty"] > 0]
    if need:
        need.sort(key=lambda p: p["qty"] * p["cost"], reverse=True)
        top = ", ".join(f"{p['name']} ({p['qty']})" for p in need[:5])
        cards.append({
            "keywords": "reorder restock buy order need running low out of "
                        "stock purchase what should replenish",
            "answer": (
                f"{len(need)} item(s) need restocking. Priority: **{top}**. "
                f"Estimated spend to cover them: {_inr(tot_cost_tied)}."),
        })

    return cards


# --------------------------------------------------------------------------
# From-scratch TF-IDF retrieval over the fact cards.
# --------------------------------------------------------------------------
class _Tfidf:
    def __init__(self, docs):
        self.docs = docs
        self.tf = [Counter(_tok(d)) for d in docs]
        df = Counter()
        for c in self.tf:
            df.update(c.keys())
        n = len(docs)
        self.idf = {w: math.log((1 + n) / (1 + f)) + 1.0 for w, f in df.items()}
        self.vecs = [self._vec(tf) for tf in self.tf]

    def _vec(self, tf):
        v = {w: (1 + math.log(c)) * self.idf.get(w, 0.0) for w, c in tf.items()}
        norm = math.sqrt(sum(x * x for x in v.values())) or 1.0
        return {w: x / norm for w, x in v.items()}

    def rank(self, query):
        q = self._vec(Counter(_tok(query)))
        scores = []
        for i, v in enumerate(self.vecs):
            s = sum(q.get(w, 0.0) * x for w, x in v.items())
            scores.append((s, i))
        scores.sort(reverse=True)
        return scores


def answer(question: str, db_path=None, cards=None) -> str:
    """Return a grounded answer string for a natural-language business question.

    Pass pre-built `cards` (from build_facts) to skip recomputation — useful
    when the caller caches facts across questions."""
    q = (question or "").strip()
    if not q:
        return "Ask me about your sales projection, profit margins, best "\
               "sellers or what to restock."

    if cards is None:
        cards = build_facts(db_path)
    if not cards:
        return ("I don't have enough data yet. Add some products with selling "
                "prices and record a few sales, then ask me again.")

    qtoks = set(_tok(q))
    # Does the question name a specific product? If so, keep that product's
    # cards plus shop-wide cards; otherwise answer at the whole-shop level so a
    # generic "yearly projection" returns the TOTAL, not one product.
    named = any((c.get("scope") and (c["scope"] & qtoks)) for c in cards)
    if named:
        pool = [c for c in cards if not c.get("scope") or (c["scope"] & qtoks)]
    else:
        pool = [c for c in cards if not c.get("scope")]
    if not pool:
        pool = cards

    idx = _Tfidf([c["keywords"] for c in pool])
    ranked = idx.rank(q)
    top_score = ranked[0][0]

    if top_score <= 0:
        return ("I couldn't match that to your data. Try asking about your "
                "yearly sales projection, profit margins, best sellers, dead "
                "stock, or what to restock.")

    # Return the single best-matching card — one focused answer per question.
    return pool[ranked[0][1]]["answer"]
