"""AI demand forecasting — a small neural net trained from scratch (numpy only).

Why not the moving-average / Croston heuristics? Those look at one SKU in
isolation and can't learn *why* demand moves. This model learns shared
structure across the whole shop:

  * weekly seasonality  (kirana demand spikes on weekends / paydays)
  * trend               (a line slowly rising or fading)
  * momentum            (last week vs the weeks before)

It is a 1-hidden-layer MLP (relu) trained with Adam on every SKU at once,
each SKU normalized by its own level so a slow spare-part borrows the weekly
shape learned from the fast movers (cross-SKU pooling). No paid APIs, no
heavyweight ML deps — just numpy, fully inspectable.

Public contract matches forecast.forecast_sku() so the reorder/cash math
downstream is untouched; we just feed it a smarter daily_rate + std and a
richer, model-derived sales analysis.
"""
import numpy as np
from datetime import datetime, timedelta
from collections import defaultdict

from .forecast import forecast_sku as _heuristic_forecast

N_DOW = 7
# feature layout: [dow one-hot(7), lag1, lag7, week_avg, month_avg, trend_pos]
N_FEAT = N_DOW + 5
_RNG = np.random.default_rng(42)

# A SKU needs at least this much real history before the net is trusted;
# below it we fall back to the explainable heuristic (cold-start safe).
MIN_SPAN = 21
MIN_POINTS = 8


def _series(sales_rows):
    """sales rows -> (start_date, full daily vector with gaps filled by 0)."""
    by_day = defaultdict(float)
    for r in sales_rows:
        try:
            d = datetime.fromisoformat(str(r["date"])[:10]).date()
        except ValueError:
            continue
        by_day[d] += float(r.get("qty", 0) or 0)
    if not by_day:
        return None, np.zeros(0)
    days = sorted(by_day)
    span = (days[-1] - days[0]).days + 1
    full = np.zeros(span)
    base = days[0]
    for d in days:
        full[(d - base).days] += by_day[d]
    return base, full


def _features(base, y, i, level):
    """Feature row for predicting demand on day index i of series y."""
    dow = (base + timedelta(days=int(i))).weekday()
    onehot = np.zeros(N_DOW)
    onehot[dow] = 1.0
    lag1 = y[i - 1] if i >= 1 else 0.0
    lag7 = y[i - 7] if i >= 7 else 0.0
    wk = y[max(0, i - 7):i].mean() if i > 0 else 0.0
    mo = y[max(0, i - 28):i].mean() if i > 0 else 0.0
    n = max(len(y), 1)
    return np.array([*onehot, lag1 / level, lag7 / level,
                     wk / level, mo / level, i / n])


class DemandNet:
    """Tiny MLP: N_FEAT -> H (relu) -> 1, trained with Adam on MSE."""

    def __init__(self, hidden=16):
        h = hidden
        self.W1 = _RNG.normal(0, np.sqrt(2 / N_FEAT), (N_FEAT, h))
        self.b1 = np.zeros(h)
        self.W2 = _RNG.normal(0, np.sqrt(2 / h), (h, 1))
        self.b2 = np.zeros(1)

    def _forward(self, X):
        z1 = X @ self.W1 + self.b1
        a1 = np.maximum(z1, 0.0)            # relu
        out = (a1 @ self.W2 + self.b2).ravel()
        return z1, a1, out

    def predict(self, X):
        return np.maximum(self._forward(X)[2], 0.0)   # demand can't be negative

    def fit(self, X, y, epochs=400, lr=0.01):
        params = [self.W1, self.b1, self.W2, self.b2]
        m = [np.zeros_like(p) for p in params]
        v = [np.zeros_like(p) for p in params]
        b1, b2, eps = 0.9, 0.999, 1e-8
        n = len(X)
        for t in range(1, epochs + 1):
            z1, a1, out = self._forward(X)
            err = (out - y) / n                          # dMSE/dout
            gW2 = a1.T @ err[:, None]
            gb2 = np.array([err.sum()])
            da1 = np.outer(err, self.W2.ravel()) * (z1 > 0)
            gW1 = X.T @ da1
            gb1 = da1.sum(axis=0)
            grads = [gW1, gb1, gW2, gb2]
            for i, (p, g) in enumerate(zip(params, grads)):
                m[i] = b1 * m[i] + (1 - b1) * g
                v[i] = b2 * v[i] + (1 - b2) * (g * g)
                mhat = m[i] / (1 - b1 ** t)
                vhat = v[i] / (1 - b2 ** t)
                p -= lr * mhat / (np.sqrt(vhat) + eps)
        return self


class AIForecaster:
    """Fit once on the whole shop, then forecast each SKU.

    Usage:
        f = AIForecaster().fit(sales_by_sku)
        f.forecast_sku(sku, horizon_days)   # same dict shape as forecast_sku()
    """

    def __init__(self, horizon_days=30):
        self.horizon_days = horizon_days
        self.net = None
        self._cache = {}        # sku -> (base, y, level)
        self._trained = False

    def fit(self, sales_by_sku):
        Xs, ys = [], []
        for sku, rows in sales_by_sku.items():
            base, y = _series(rows)
            if base is None or len(y) < MIN_POINTS:
                continue
            level = max(float(y.mean()), 0.5)
            self._cache[sku] = (base, y, level)
            for i in range(1, len(y)):
                Xs.append(_features(base, y, i, level))
                ys.append(y[i] / level)
        if len(Xs) >= 30:                       # enough signal to learn
            self.net = DemandNet().fit(np.array(Xs), np.array(ys))
            self._trained = True
        return self

    # -- internals ---------------------------------------------------------
    def _roll_forward(self, base, y, level, horizon):
        """Predict `horizon` future days autoregressively; return preds array."""
        buf = list(y)
        preds = []
        n = len(y)
        for step in range(horizon):
            i = n + step
            yb = np.array(buf)
            feat = _features(base, yb, i, level)
            p = float(self.net.predict(feat[None, :])[0] * level)
            preds.append(p)
            buf.append(p)
        return np.array(preds)

    def _weekly_shape(self, base, y, level):
        """Probe the net for the demand multiplier it learned per weekday."""
        recent = y[-28:] if len(y) >= 7 else y
        lag1 = recent.mean() if len(recent) else level
        out = []
        for dow in range(N_DOW):
            onehot = np.zeros(N_DOW); onehot[dow] = 1.0
            feat = np.array([*onehot, lag1 / level, lag1 / level,
                             lag1 / level, lag1 / level, 1.0])
            out.append(float(self.net.predict(feat[None, :])[0] * level))
        return np.array(out)

    # -- public ------------------------------------------------------------
    def forecast_sku(self, sku, horizon_days=None):
        horizon = horizon_days or self.horizon_days
        cached = self._cache.get(sku)
        # Cold start or untrained -> explainable heuristic.
        if not self._trained or cached is None:
            return self._fallback(sku, horizon)
        base, y, level = cached
        span = len(y)
        if span < MIN_SPAN:
            return self._fallback(sku, horizon)

        future = self._roll_forward(base, y, level, horizon)
        rate = float(max(future.mean(), 0.0))

        # residual std on in-sample one-step predictions -> realistic safety stock
        idx = np.arange(1, span)
        X = np.array([_features(base, y, i, level) for i in idx])
        insample = self.net.predict(X) * level
        resid = y[1:] - insample
        std = float(np.std(resid)) if len(resid) > 1 else rate * 0.3

        analysis = self._analysis(base, y, level, rate)
        return {
            "method": "ai_neural",
            "daily_rate": round(rate, 3),
            "daily_std": round(std, 3),
            "horizon_qty": round(rate * horizon, 2),
            "horizon_days": horizon,
            "explanation": analysis["summary"],
            "ai_analysis": analysis,
            "n_points": int((y > 0).sum()),
            "span_days": span,
            "intermittent": bool((y <= 0).mean() >= 0.4),
        }

    def _analysis(self, base, y, level, rate):
        dow_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        shape = self._weekly_shape(base, y, level)
        busiest = dow_names[int(np.argmax(shape))]
        quietest = dow_names[int(np.argmin(shape))]

        # trend: compare first vs last third of history -> %/month
        third = max(len(y) // 3, 1)
        early = y[:third].mean()
        late = y[-third:].mean()
        if early > 1e-6:
            monthly_pct = (late - early) / early / (len(y) / 30.0) * 100
        else:
            monthly_pct = 0.0
        direction = ("rising" if monthly_pct > 3 else
                     "falling" if monthly_pct < -3 else "steady")

        # momentum: last 7 days vs the 21 before
        recent = y[-7:].mean() if len(y) >= 7 else y.mean()
        baseline = y[-28:-7].mean() if len(y) >= 28 else y.mean()
        momentum = ((recent - baseline) / baseline * 100) if baseline > 1e-6 else 0.0

        summary = (f"AI forecast {rate:.1f}/day. Demand is {direction} "
                   f"({monthly_pct:+.0f}%/month); busiest day {busiest}, "
                   f"quietest {quietest}.")
        return {
            "summary": summary,
            "busiest_day": busiest,
            "quietest_day": quietest,
            "weekly_shape": {dow_names[i]: round(float(v), 2)
                             for i, v in enumerate(shape)},
            "trend_pct_month": round(float(monthly_pct), 1),
            "trend_dir": direction,
            "momentum_pct": round(float(momentum), 1),
        }

    def _fallback(self, sku, horizon):
        """Explainable heuristic for SKUs the net can't trust yet."""
        rows = self._cache.get(sku)
        sales = [{"date": (rows[0] + timedelta(days=i)).isoformat(), "qty": q}
                 for i, q in enumerate(rows[1])] if rows else []
        fc = _heuristic_forecast(sales, horizon)
        fc["method"] = fc["method"] + "_fallback"
        fc["ai_analysis"] = None
        return fc
