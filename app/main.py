"""Local portfolio MVP. Same-origin frontend + SQLite + explicit optional AI."""
from contextlib import asynccontextmanager, contextmanager
from datetime import datetime, timezone, date
from pathlib import Path
from typing import Literal
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool
import csv
import io
import html
import json
import os
import secrets
import sqlite3
import uuid

from .services import make_plan, model_plan, analyze_gsc

ROOT = Path(__file__).resolve().parents[1]
DATA = Path(os.getenv('SKIPRO_DATA_DIR', str(ROOT / 'data')))
PUBLIC_URL = os.getenv('SKIPRO_PUBLIC_URL', '').rstrip('/')
MAX_VIDEO = 30 * 1024 * 1024


@contextmanager
def db():
    DATA.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DATA / 'skipro.sqlite3', timeout=15)
    con.row_factory = sqlite3.Row
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def init_db():
    with db() as con:
        con.executescript('''
        CREATE TABLE IF NOT EXISTS records (
          id TEXT PRIMARY KEY, owner TEXT NOT NULL, kind TEXT NOT NULL,
          created_at TEXT NOT NULL, payload TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS owner_kind ON records(owner, kind);
        ''')
    (DATA / 'uploads').mkdir(exist_ok=True)


@asynccontextmanager
async def lifespan(app):
    init_db()
    yield


app = FastAPI(title='Ski Pro API', version='2.0.0', lifespan=lifespan)


@app.middleware('http')
async def session_and_headers(request: Request, call_next):
    owner = request.cookies.get('skipro_session', '')
    if len(owner) != 64 or any(c not in '0123456789abcdef' for c in owner):
        owner = secrets.token_hex(32)
    request.state.owner = owner
    # Block browser cross-origin writes; no wildcard CORS or third-party sessions.
    if request.method not in {'GET', 'HEAD', 'OPTIONS'}:
        origin = request.headers.get('origin')
        expected = str(request.base_url).rstrip('/')
        if origin and origin != expected:
            return Response('Cross-origin write denied', status_code=403)
    response = await call_next(request)
    response.set_cookie('skipro_session', owner, httponly=True, samesite='strict', secure=request.url.scheme == 'https', max_age=60 * 60 * 24 * 180)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    if request.url.path.startswith('/api/'):
        response.headers['Cache-Control'] = 'no-store'
    if not PUBLIC_URL:
        response.headers['X-Robots-Tag'] = 'noindex, nofollow'
    return response


def save(owner, kind, payload):
    record = {'id': str(uuid.uuid4()), 'created_at': datetime.now(timezone.utc).isoformat(), **payload}
    with db() as con:
        con.execute('INSERT INTO records VALUES (?, ?, ?, ?, ?)', (record['id'], owner, kind, record['created_at'], json.dumps(record, ensure_ascii=False, allow_nan=False)))
    return record


def records(owner, kind):
    with db() as con:
        rows = con.execute('SELECT payload FROM records WHERE owner=? AND kind=? ORDER BY created_at DESC LIMIT 100', (owner, kind)).fetchall()
    return [json.loads(r['payload']) for r in rows]


def owned_record(owner, record_id, kind):
    with db() as con:
        row = con.execute('SELECT payload FROM records WHERE id=? AND owner=? AND kind=?', (record_id, owner, kind)).fetchone()
    if not row:
        raise HTTPException(404, 'Record not found')
    return json.loads(row['payload'])


@app.get('/api/health')
def health():
    with db() as con:
        con.execute('SELECT 1')
    return {'status': 'ok', 'storage': 'sqlite', 'plan_engine': 'ollama-configured' if os.getenv('SKIPRO_MODEL') else 'rules', 'video_analysis': 'metadata-only'}


class Profile(BaseModel):
    sport: Literal['ski', 'snowboard'] = 'ski'
    level: Literal['beginner', 'intermediate', 'advanced'] = 'beginner'
    minutes: int = Field(default=45, ge=20, le=120)
    goal: str = Field(default='Improve control and confidence', min_length=1, max_length=500)


@app.post('/api/plans', status_code=201)
async def create_plan(body: Profile, request: Request):
    profile = body.model_dump()
    plan = await run_in_threadpool(model_plan, profile, make_plan(profile))
    return save(request.state.owner, 'plan', {**plan, 'profile': profile})


@app.get('/api/plans')
def get_plans(request: Request):
    return {'items': records(request.state.owner, 'plan')}


class TrainingLog(BaseModel):
    plan_id: str
    date: date
    minutes: int = Field(ge=1, le=480)
    effort: int = Field(ge=1, le=10)
    note: str = Field(default='', max_length=1500)


@app.post('/api/logs', status_code=201)
def create_log(body: TrainingLog, request: Request):
    owned_record(request.state.owner, body.plan_id, 'plan')
    return save(request.state.owner, 'log', body.model_dump(mode='json'))


@app.get('/api/logs')
def get_logs(request: Request):
    items = records(request.state.owner, 'log')
    return {'items': items, 'total_minutes': sum(x['minutes'] for x in items), 'sessions': len(items)}


@app.get('/api/logs/export')
def export_logs(request: Request):
    out = io.StringIO()
    fields = ['date', 'minutes', 'effort', 'note', 'plan_id']
    writer = csv.DictWriter(out, fieldnames=fields, extrasaction='ignore')
    writer.writeheader()
    for item in records(request.state.owner, 'log'):
        # Prevent spreadsheet formula injection in free text.
        safe = {k: ("'" + v if isinstance(v, str) and v.lstrip().startswith(('=', '+', '-', '@')) else v) for k, v in item.items()}
        writer.writerow(safe)
    return Response(out.getvalue(), media_type='text/csv', headers={'Content-Disposition': 'attachment; filename="training-log.csv"'})


async def limited_body(request, limit):
    data = bytearray()
    async for part in request.stream():
        if len(data) + len(part) > limit:
            raise HTTPException(413, 'File exceeds size limit')
        data.extend(part)
    if not data:
        raise HTTPException(422, 'Empty file')
    return bytes(data)


@app.post('/api/videos', status_code=201)
async def upload_video(request: Request, filename: str = 'clip.mp4'):
    name = Path(filename).name[:120]
    suffix = Path(name).suffix.lower()
    if suffix not in {'.mp4', '.mov', '.webm'}:
        raise HTTPException(415, 'Use MP4, MOV or WebM')
    raw = await limited_body(request, MAX_VIDEO)
    is_mp4 = len(raw) >= 12 and raw[4:8] == b'ftyp'
    is_webm = raw[:4] == b'\x1aE\xdf\xa3'
    if not (is_webm if suffix == '.webm' else is_mp4):
        raise HTTPException(415, 'File header does not match the video format')
    key = str(uuid.uuid4()) + suffix
    path = DATA / 'uploads' / key
    path.write_bytes(raw)
    try:
        return save(request.state.owner, 'video', {'filename': name, 'storage_key': key, 'bytes': len(raw), 'status': 'uploaded'})
    except Exception:
        path.unlink(missing_ok=True)
        raise


@app.get('/api/videos')
def list_videos(request: Request):
    return {'items': [{k: v for k, v in x.items() if k != 'storage_key'} for x in records(request.state.owner, 'video')]}


def inspect_video(path):
    try:
        import cv2
    except ImportError:
        raise HTTPException(503, 'Video inspection needs optional opencv-python-headless. No posture score has been generated.')
    cap = cv2.VideoCapture(str(path))
    try:
        if not cap.isOpened():
            raise HTTPException(422, 'Video could not be decoded; try an H.264 MP4')
        ok, frame = cap.read()
        fps = float(cap.get(cv2.CAP_PROP_FPS))
        frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if not ok or fps <= 0 or frames <= 0:
            raise HTTPException(422, 'Video metadata is invalid')
        return {'width': frame.shape[1], 'height': frame.shape[0], 'fps': round(fps, 2), 'duration_seconds': round(frames / fps, 2), 'frame_count': frames,
                'analysis_type': 'metadata-only', 'notice': 'File decoded successfully. This version does not infer body pose, joint angles or technique scores.'}
    finally:
        cap.release()


@app.post('/api/videos/{video_id}/inspect')
async def video_inspect(video_id: str, request: Request):
    record = owned_record(request.state.owner, video_id, 'video')
    result = await run_in_threadpool(inspect_video, DATA / 'uploads' / record['storage_key'])
    return {'video_id': video_id, **result}


@app.delete('/api/videos/{video_id}', status_code=204)
def delete_video(video_id: str, request: Request):
    record = owned_record(request.state.owner, video_id, 'video')
    (DATA / 'uploads' / record['storage_key']).unlink(missing_ok=True)
    with db() as con:
        con.execute('DELETE FROM records WHERE id=? AND owner=?', (video_id, request.state.owner))
    return Response(status_code=204)


class CsvInput(BaseModel):
    csv: str = Field(max_length=2_000_000)


@app.post('/api/seo/analyze')
def seo(body: CsvInput):
    try:
        return {**analyze_gsc(body.csv), 'source': 'user-imported-csv'}
    except ValueError as e:
        raise HTTPException(422, str(e))


@app.get('/api/seo/sample')
def sample_seo():
    return {**analyze_gsc((ROOT / 'content/sample-gsc.csv').read_text()), 'source': 'synthetic-demo', 'notice': 'Synthetic learning data. Not live Search Console traffic.'}


def articles():
    return json.loads((ROOT / 'content/guides.json').read_text())


def shell(title, description, body, path):
    canonical = f'<link rel="canonical" href="{html.escape(PUBLIC_URL + path, quote=True)}">' if PUBLIC_URL else ''
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(title)} | Ski Pro</title><meta name="description" content="{html.escape(description, quote=True)}">{canonical}<link rel="stylesheet" href="/static/style.css"></head><body><header class="topbar"><a class="brand" href="/">Ski<span>Pro</span> <small>FIELD NOTES</small></a><a href="/">Open training workspace ↗</a></header><main class="reading">{body}</main><footer>AI-assisted editorial samples · No claim of certified instruction</footer></body></html>'''


@app.get('/guides', response_class=HTMLResponse)
def guides():
    cards = ''.join(f'<article class="panel"><p class="eyebrow">{html.escape(a["intent"])}</p><h2><a href="/guides/{a["slug"]}">{html.escape(a["title"])}</a></h2><p>{html.escape(a["description"])}</p></article>' for a in articles())
    return shell('Ski learning guides', 'Practical guides to recording ski practice, reviewing video and planning a beginner session.', '<p class="eyebrow">THE LEARNING LIBRARY</p><h1>Small steps.<br>Better sessions.</h1><p>English editorial samples for skiers who want a clearer practice routine.</p>' + cards, '/guides')


@app.get('/guides/{slug}', response_class=HTMLResponse)
def guide(slug: str):
    a = next((x for x in articles() if x['slug'] == slug), None)
    if not a:
        raise HTTPException(404, 'Guide not found')
    sections = ''.join(f'<section><h2>{html.escape(s["heading"])}</h2><p>{html.escape(s["text"])}</p></section>' for s in a['sections'])
    links = ''.join(f'<li><a href="/guides/{x["slug"]}">{html.escape(x["title"])}</a></li>' for x in articles() if x['slug'] != slug)
    body = f'<a href="/guides">← All guides</a><p class="eyebrow">{html.escape(a["intent"])}</p><h1>{html.escape(a["title"])}</h1><p class="lede">{html.escape(a["description"])}</p><p class="subtle">By Ski Pro editorial demo · AI-assisted draft · Review before publication</p>{sections}<aside class="panel">This article is a planning and recording guide. On-snow skills should be taught by a qualified instructor.</aside><h2>Continue reading</h2><ul>{links}</ul><a class="button" href="/">Build a practice plan ↗</a>'
    return shell(a['title'], a['description'], body, '/guides/' + slug)


@app.get('/robots.txt')
def robots():
    text = f'User-agent: *\nAllow: /\nDisallow: /api/\nDisallow: /docs\nDisallow: /openapi.json\nSitemap: {PUBLIC_URL}/sitemap.xml\n' if PUBLIC_URL else 'User-agent: *\nDisallow: /\n'
    return Response(text, media_type='text/plain')


@app.get('/sitemap.xml')
def sitemap():
    if not PUBLIC_URL:
        return Response('<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"/>', media_type='application/xml')
    urls = ['/', '/guides'] + ['/guides/' + x['slug'] for x in articles()]
    text = '<?xml version="1.0"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">' + ''.join(f'<url><loc>{html.escape(PUBLIC_URL + p)}</loc></url>' for p in urls) + '</urlset>'
    return Response(text, media_type='application/xml')


app.mount('/static', StaticFiles(directory=ROOT / 'web'), name='static')


@app.get('/')
def home():
    source = (ROOT / 'web/index.html').read_text()
    if PUBLIC_URL:
        source = source.replace('</head>', f'<link rel="canonical" href="{html.escape(PUBLIC_URL, quote=True)}/"></head>')
    return HTMLResponse(source)
