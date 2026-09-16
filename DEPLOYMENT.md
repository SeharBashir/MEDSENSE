# Phase 6 — Deployment Guide

Two pieces to deploy: the FastAPI backend (Render, free tier) and the React dashboard (Vercel, free tier). Both connect directly to your existing GitHub repo.

---

## Step 0 — Build the public data file locally first

Before deploying anything, make sure `data/processed/public_data.json` exists and is up to date:

```powershell
python src/build_public_dataset.py
```

This reads your real `topics.csv`, `topic_summary.json`, and `insights_verified.json`, and produces the small, privacy-safe file the API actually serves.

**Important:** `public_data.json` needs to be committed to GitHub (unlike your raw/processed data files, which are gitignored) since Render will pull it from your repo, not from your local machine. Add this line to your `.gitignore` file to allow just this one file through:

```
!data/processed/public_data.json
```

Then:
```powershell
git add data/processed/public_data.json .gitignore
git commit -m "Add public dataset for API deployment"
git push
```

---

## Step 1 — Test everything locally first

**Backend:**
```powershell
cd api
pip install -r requirements.txt
uvicorn main:app --reload
```
Open http://localhost:8000/api/meta in your browser — you should see `{"n_topics": ..., "n_insights": ...}`.

**Frontend** (separate terminal):
```powershell
cd dashboard
npm install
npm run dev
```
Open the URL it prints (usually http://localhost:5173) — you should see the dashboard with your real insights and topics.

Don't move to deployment until both work locally.

---

## Step 2 — Deploy the API to Render

1. Go to https://render.com and sign up (free, GitHub login works).
2. Click **New +** → **Web Service**.
3. Connect your GitHub account and select your `medsense` repo.
4. Configure:
   - **Name:** `medsense-api` (or anything)
   - **Root Directory:** `api`
   - **Runtime:** Python 3
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `uvicorn main:app --host 0.0.0.0 --port $PORT`
   - **Instance Type:** Free
5. Click **Create Web Service**. Render will build and deploy — takes a few minutes.
6. Once live, you'll get a URL like `https://medsense-api.onrender.com`. Test it: open `https://medsense-api.onrender.com/api/meta` in your browser.

**Note on the free tier:** Render's free web services "spin down" after 15 minutes of inactivity and take ~30-60 seconds to wake back up on the next request. This is normal — if your dashboard looks like it's stuck loading the first time someone visits, that's the API waking up.

---

## Step 3 — Deploy the dashboard to Vercel

1. Go to https://vercel.com and sign up (free, GitHub login works).
2. Click **Add New** → **Project**.
3. Import your `medsense` repo.
4. Configure:
   - **Root Directory:** `dashboard`
   - **Framework Preset:** Vite (should auto-detect)
5. Before deploying, add an environment variable:
   - **Name:** `VITE_API_BASE`
   - **Value:** your Render URL from Step 2 (e.g. `https://medsense-api.onrender.com`) — no trailing slash
6. Click **Deploy**.

You'll get a URL like `https://medsense-dashboard.vercel.app` — this is your real, public, shareable dashboard link.

---

## Step 4 — Confirm it works cold

Open your Vercel URL in a new incognito/private browser window (no cached local state) and confirm:
- The overview page loads with real insights and topics (not placeholder data)
- Clicking a topic navigates to its detail page and shows example quotes
- Sorting by sentiment/size on the overview page works

If the API is asleep (Render free-tier spin-down), the first load may take ~30-60 seconds — that's expected, not a bug.

---

## Updating later

Any time you change your data (re-run the pipeline, update insights), you need to:
1. Re-run `python src/build_public_dataset.py`
2. Commit and push the updated `public_data.json`
3. Render will auto-redeploy on push (if auto-deploy is enabled, which is the default)

The frontend doesn't need redeployment unless you change the dashboard code itself.
