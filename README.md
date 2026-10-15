# Ski Pro / SkiNova — full-stack portfolio MVP

A ski practice notebook with a same-origin web frontend, FastAPI backend and SQLite persistence. Built by extending the original SkiNova course prototype. The preserved original source is in `legacy/`.

## Start

Python 3.11+ recommended. From this directory:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 8765 --reload
```

Open **http://127.0.0.1:8765**. Do not double-click the HTML file: the frontend needs the server. API docs: `/docs`.

On the current computer, the existing system Python already has FastAPI, Uvicorn and OpenCV, so `python3 -m uvicorn app.main:app --host 127.0.0.1 --port 8765` works without installing anything.

## Implemented and verified

- Generate ski/snowboard practice plans from a validated level, time budget and goal; time blocks add up to the selected duration.
- Store plans and linked training reflections in SQLite; retrieve them after refresh/restart and export the latest 100 journal records as CSV.
- Browser-specific anonymous HTTP-only sessions: records from another browser are not listed. This is not a user account system or account recovery service.
- Upload MP4/MOV/WebM up to 30 MB; server-generated filenames, basic container-header checks, optional decoding/metadata checks and deletion. No public upload directory.
- Three English guide pages rendered as HTML on the server; internal links, descriptions, canonical URLs and sitemap when a real public URL is configured.
- Import a query-dimensional Search Console CSV; aggregate clicks and impressions, recompute CTR, calculate impression-weighted position and flag review opportunities. A clearly labelled synthetic sample is available.
- Optional real Ollama call for plan explanations. It preserves the rules-based drills and duration allocation. The UI and saved data record `rules` versus `ollama` and explicitly report fallback.

## What is not implemented

- Body pose estimation, joint-angle measurement or technique grading. The old fixed 60-degree/85-point result was a placeholder and has not been carried into the new app.
- Live Google account connection, GA4 tracking, actual search rankings, proven traffic growth, external link placements or a production user base.
- A trained financing/medical model. That is a separate research repository.
- Public hosting, multi-device accounts, rate limits, production storage quotas or background video processing. Keep this MVP bound to localhost; do not expose it publicly without adding those controls.

## Optional model

Install Ollama from its official source, install a model appropriate for your machine, and set its exact installed model name:

```bash
export SKIPRO_MODEL='your-installed-model-name'
export SKIPRO_OLLAMA_URL='http://127.0.0.1:11434'
python -m uvicorn app.main:app --host 127.0.0.1 --port 8765
```

The backend calls `/api/chat` with non-streamed JSON output and a 45-second timeout. The model receives only the submitted plan profile and template. Without configuration, or when the call fails, the rule template is returned and labelled. Live inference has not been verified on this machine because no model service was configured; success/error handling is tested with controlled responses. Do not describe this as a trained AI coach.

Optional video inspection dependency: `python -m pip install 'opencv-python-headless>=4.10,<5'`. Without it, upload still works and inspection returns an explicit 503.

## Storage and privacy

`data/skipro.sqlite3` contains records; `data/uploads/` contains videos. Both are ignored by Git. Keep the browser cookie: clearing it loses access to that anonymous notebook. Uploaded data is never sent to the model. Sample SEO data is not written to the database. Do not share the data directory or publish personal training files.

Environment variables are read from the process. `.env.example` is a reference; the app does not auto-load `.env`. `SKIPRO_DATA_DIR` is resolved relative to the working directory if not absolute. Local runs default to `noindex` and robots disallow. Only set `SKIPRO_PUBLIC_URL` to a verified HTTPS origin when deploying reviewed public content; this alone does not make the service production-ready.

## Test

```bash
python -m unittest discover -s tests -v
```

Nine tests cover real ASGI requests, persistence, session boundaries, input errors, CSV formula protection, file limits, actual video metadata (when OpenCV is installed), SEO metrics and controlled model responses. No paid API is needed.

## Continue in Cursor

- Layout: `web/index.html`
- Styles: `web/style.css`
- UI interactions: `web/app.js`
- Routes/storage: `app/main.py`
- Training and CSV calculations: `app/services.py`
- English content: `content/guides.json`
- Integration contract and a copyable Cursor prompt: `docs/CURSOR_HANDOFF.md`

## References

- [FastAPI request files](https://fastapi.tiangolo.com/tutorial/request-files/) — this app uses a bounded binary request body to avoid a multipart dependency.
- [Ollama chat API](https://docs.ollama.com/api/chat)
- [Google SEO starter guide](https://developers.google.com/search/docs/fundamentals/seo-starter-guide)
- [People-first content](https://developers.google.com/search/docs/fundamentals/creating-helpful-content)
- [Search Console performance report](https://support.google.com/webmasters/answer/7576553?hl=en)
