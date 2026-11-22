# DOKARI WEATHER RADAR — FREE CLOUD EDITION

**Working zero-subscription-cost discovery pipeline**: GitHub Actions + Google News public RSS + optional YouTube Data API + GitHub Pages dashboard. No dedicated server or paid services required **within free-tier limits**.

## Setup (10–20 minutes)

1. Create a **public** GitHub repository and upload the contents of this folder, including `.github/workflows/radar.yml` (hidden folder). A public repo means the collected URLs/data are public; never store private contacts, passwords, permissions correspondence, or unreleased editorial notes here.
2. Repository **Settings → Pages → Build and deployment → Deploy from a branch**. Choose `main` and `/docs`. The dashboard will be at `https://YOUR-USERNAME.github.io/YOUR-REPOSITORY/` after deployment.
3. Open **Actions → Global Weather Radar → Run workflow**. The first run fetches public Google News RSS and commits `docs/data.json`. Refresh the dashboard after it completes.
4. Optional for **real YouTube video discovery**: create a project in Google Cloud, enable **YouTube Data API v3**, create a restricted API key, then add it in repository **Settings → Secrets and variables → Actions → New repository secret** as `YOUTUBE_API_KEY`. Never paste it into code or the public repository. YouTube search costs 100 quota units per call; this implementation makes 5 calls/run, 3 scheduled runs/day (about 1500 units/day, below the usual default 10,000/day; quota is not guaranteed). YouTube API setup may require a Google Cloud account; check Google's current terms and billing requirements before activation.
5. The GitHub workflow is scheduled **05:13, 11:13, 17:13 UTC**. GitHub Actions scheduled runs can be delayed or skipped and can be disabled after prolonged inactivity. Use **Run workflow** to test manually. For a public repository, Actions and Pages are typically free within GitHub policies; verify current limits.

## What is automated

- Public news RSS searches across 10 global weather regions, in local languages.
- Optional YouTube search for recent uploads, rotating query coverage to conserve quota.
- Dedupe by source URL; retention up to 14 days, max 600 items.
- Browser-based searchable dashboard with original links, source and timestamps.
- Manual Facebook, Instagram and YouTube search shortcuts in local languages.

## What is NOT automated

- Facebook and Instagram public-video harvesting: no general free official API supports universal discovery. Search shortcuts are manual and may change as sites change.
- Downloading third-party videos, rights clearance, verification of capture date/location, and automatic posting to Dokari/Facebook.
- News RSS results are **articles**, not necessarily social videos. Upload time ≠ recording time. All items require editorial verification.
- This repository does **not** promise full 24/7 real-time coverage, exhaustive discovery, or free unlimited usage.

## Local test (optional)

```bash
python3 collector.py
python3 -m http.server 8000 --directory docs
```

Open `http://localhost:8000`. No Python dependencies beyond the standard library.

## Security / editorial guardrails

- Use only public RSS and authorized APIs. Do not bypass platform restrictions or download third-party footage without appropriate rights.
- Confirm original creator, recording time/location, weather context, and permission before republishing footage. Crediting a creator alone is not a license.
- Do not treat headlines, upload dates, or AI classifications as verified facts.
- API key must remain in GitHub Actions secrets. Never include it in the public Pages site.
- Review the terms of all providers periodically.

## Next production improvements

- Add authorized Facebook/Instagram sources if access becomes available.
- Add private editorial approval workflow separate from the public dashboard.
- Add opt-in alerting (Telegram or email) with credentials stored in secrets.
- Track daily yield: actual video candidates, verified unique clips, usable rights-cleared clips.
