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

That's it — no secrets, env vars, or config required to get running.

## Accounts & data

- Each shopkeeper taps **Create shop account** (username can be their phone
  number) and gets their **own isolated database** — no one sees another
  shop's stock or sales.
- Passwords are hashed (pbkdf2-sha256, 200k rounds, per-user salt). Plaintext
  passwords are never stored.
- A login survives browser refreshes for 30 days via a session token.

## IMPORTANT — persistent storage on the free tier

Streamlit Community Cloud has an **ephemeral filesystem**: when the app sleeps
or redeploys, files written at runtime (the shop databases under `data/`) can
be wiped. For a demo this is fine. For real shopkeepers who must not lose data,
point StockSense at a persistent disk:

```
STOCKSENSE_DATA_DIR=/mnt/persistent/stocksense
```

Set that environment variable to a durable path. Free options that give you a
persistent disk:

- **Render** free web service + a small persistent disk
- **Railway** / **Fly.io** free allowance with a mounted volume
- Any host where you can attach a volume and run `streamlit run app.py`

Until a persistent `STOCKSENSE_DATA_DIR` is configured, treat a Community Cloud
deployment as a demo, not a system of record.

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
- Hosting: free on Render's free plan (sleeps when idle; **ephemeral disk**)
- For real shops that can't lose data: Render paid plan + persistent disk,
  then set `STOCKSENSE_DATA_DIR` to the disk mount path in `render.yaml`.

> Note: I (Claude) can prepare all the files and config, but **buying the
> domain and editing its DNS must be done by you** — those need your account
> and payment. Everything else above is already wired up in this repo.
