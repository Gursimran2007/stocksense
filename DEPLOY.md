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
