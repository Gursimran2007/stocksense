"""Owner-only analytics for StockSense — NOT part of the shopkeeper app.

Run it yourself to see how much traffic the website is getting:

    streamlit run owner_analytics.py      # visual dashboard in the browser
    python owner_analytics.py             # quick numbers in the terminal

It reads the same live Turso database the site uses (via .streamlit/secrets.toml
or the TURSO_* env vars), so the numbers are real and up to date. Shopkeepers
never see this — it's a separate tool for you as the site owner.
"""
import sys

from core import db


def _stats():
    ov = db.analytics_overview()
    ov["daily"] = db.visits_by_day(30)
    ov["pages"] = db.top_pages(10)
    return ov


def _cli():
    s = _stats()
    print("\n=== StockSense — site analytics (owner) ===\n")
    print(f"  Total visits        : {s['visits']:,}")
    print(f"  Unique visitors     : {s['visitors']:,}")
    print(f"  Visits today        : {s['today']:,}")
    print(f"  Page views          : {s['pageviews']:,}")
    print()
    print(f"  Registered accounts : {s['shops']:,}")
    print(f"  Sign-ups (tracked)  : {s['signups']:,}")
    print(f"  Logins (all-time)   : {s['logins']:,}")
    print()
    if s["daily"]:
        print("  Visits per day (last 30 days):")
        for d in s["daily"]:
            bar = "#" * min(d["visits"], 50)
            print(f"    {d['day']}  {d['visits']:>4}  {bar}")
    if s["pages"]:
        print("\n  Most-viewed pages:")
        for p in s["pages"]:
            print(f"    {p['views']:>4}  {p['page']}")
    print()


def _dashboard():
    import pandas as pd
    import streamlit as st

    st.set_page_config(page_title="StockSense — Owner Analytics", page_icon="📊")
    st.title("📊 StockSense — Site Analytics")
    st.caption("Owner-only view of website traffic and accounts. "
               "Not visible to shopkeepers.")

    s = _stats()
    c = st.columns(4)
    c[0].metric("Total visits", f"{s['visits']:,}")
    c[1].metric("Unique visitors", f"{s['visitors']:,}")
    c[2].metric("Visits today", f"{s['today']:,}")
    c[3].metric("Page views", f"{s['pageviews']:,}")

    c = st.columns(3)
    c[0].metric("Registered accounts", f"{s['shops']:,}")
    c[1].metric("Sign-ups (tracked)", f"{s['signups']:,}")
    c[2].metric("Logins (all-time)", f"{s['logins']:,}")

    st.divider()
    if s["daily"]:
        df = pd.DataFrame(s["daily"]).set_index("day")
        st.subheader("Visits per day (last 30 days)")
        st.bar_chart(df["visits"])
        st.subheader("Unique visitors per day")
        st.line_chart(df["visitors"])
    else:
        st.info("No visits recorded yet.")

    if s["pages"]:
        st.subheader("Most-viewed pages")
        st.dataframe(pd.DataFrame(s["pages"]), hide_index=True,
                     use_container_width=True)


def _running_in_streamlit():
    try:
        from streamlit.runtime.scriptrunner import get_script_run_ctx
        return get_script_run_ctx() is not None
    except Exception:
        return False


if _running_in_streamlit():
    _dashboard()
elif __name__ == "__main__":
    _cli()
