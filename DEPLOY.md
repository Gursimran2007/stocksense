# Deploying StockSense (100% free)

StockSense runs on **Streamlit Community Cloud** — free, no card needed.
Everything else (auth, database) is built in with the Python standard library
and SQLite, so there are no paid services to sign up for.

## Steps

1. Push this repo to GitHub (already done if you cloned it from yours).
2. Go to https://share.streamlit.io and sign in with GitHub (free).
3. Click **New app** → pick this repo → branch `main` → main file `app.py`.
4. Click **Deploy**. First boot installs `requirements.txt` and takes a minute.
5. Share the resulting `https://<you>.streamlit.app` link with shopkeepers.

It runs immediately with no config. **But** for real shops, add the free Turso
database (see "make data survive restarts" below) — otherwise data is wiped
whenever the free host restarts.

## Accounts & data

- Each shopkeeper taps **Create shop account** (username can be their phone
  number). Every account's products, sales and stock are scoped to that shop —
  no one sees another shop's data (row-level multi-tenancy).
- Passwords are hashed (pbkdf2-sha256, 200k rounds, per-user salt). Plaintext
  passwords are never stored.
- A login survives browser refreshes for 30 days via a session token.

## IMPORTANT — make data survive restarts (free, no card)

Both Streamlit Community Cloud and Render's free plan have an **ephemeral
filesystem**: when the app sleeps or redeploys, any local database file is
**wiped**. So a shopkeeper could lose a week of records. The fix is to store
data in a free **hosted** database instead of a local file. StockSense supports
**Turso** (hosted SQLite/libSQL) out of the box — same SQLite we already use,
just durable.

### Set up Turso (one time, ~3 minutes, no payment)

1. Go to https://turso.tech and sign up with GitHub (free, no card).
2. Create a database (any name, e.g. `stocksense`).
3. Copy two things it gives you:
   - the **database URL** (looks like `libsql://stocksense-you.turso.io`)
   - an **auth token** (generate one in the database's settings)
4. In your host's **Environment** settings, add:

```
TURSO_DATABASE_URL = libsql://stocksense-you.turso.io
TURSO_AUTH_TOKEN   = <the token>
```

That's it. With those set, every shop's data is stored in Turso and survives
restarts, redeploys, and sleeps. Leave them unset and the app falls back to a
local file (fine for a quick demo, but wiped on restart).

Turso's free tier (≈9 GB, 500 DBs) is far more than a kirana shop will ever use.

---

## Giving shopkeepers a real domain (not `*.streamlit.app`)

A `*.streamlit.app` URL looks like a dev demo. Streamlit Community Cloud
**cannot** use a custom domain (not even on a paid plan). To hand out something
like `stocksense.in`, deploy on **Render** instead — it allows custom domains
for free — and point a cheap domain at it.

### 1. Buy a cheap domain (you do this — needs a card)

| Where | Typical price (India) |
|-------|-----------------------|
| Cloudflare Registrar | `.in` ~₹700/yr (at cost, no markup) |
| Hostinger / GoDaddy | `.in` ~₹500–700/yr; `.shop`/`.store`/`.xyz` often ₹99–199 first year |

Pick something short the shopkeeper can say out loud.

### 2. Deploy on Render (free)

1. Push this repo to GitHub.
2. https://render.com → sign up free → **New → Blueprint** → pick this repo.
   It reads `render.yaml` automatically. Click **Apply**.
3. You get `https://stocksense.onrender.com` once it builds.

### 3. Attach your domain (free on Render)

1. Render dashboard → your service → **Settings → Custom Domains → Add**.
2. Type your domain (e.g. `stocksense.in`).
3. Render shows a DNS record (a CNAME, or an A record for the bare domain).
   Add it in your domain registrar's DNS panel. HTTPS is issued automatically.

Now shopkeepers open `https://stocksense.in` — no "streamlit" anywhere.

### Cost summary

- Domain: ~₹99–700/yr (the only required cost)
- Hosting: free on Render's free plan (sleeps when idle)
- Database: free on Turso (set `TURSO_DATABASE_URL` + `TURSO_AUTH_TOKEN`) so
  data persists even though the host's disk is ephemeral — no payment needed.

> Note: I (Claude) can prepare all the files and config, but **buying the
> domain and editing its DNS must be done by you** — those need your account
> and payment. Everything else above is already wired up in this repo.
