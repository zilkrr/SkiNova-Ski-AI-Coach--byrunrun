from fastapi import FastAPI, File, UploadFile, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
import math
import uuid
import os

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

video_db = {}

# GPS 滑雪记录存储
gps_sessions: dict[str, dict] = {}


class GpsPoint(BaseModel):
    lat: float
    lng: float
    altitude: Optional[float] = None
    speed: Optional[float] = None
    accuracy: Optional[float] = None
    timestamp: Optional[str] = None


class GpsSessionCreate(BaseModel):
    name: Optional[str] = None


def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """计算两点间距离（米）"""
    r = 6371000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return r * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def calc_track_distance(points: list[dict]) -> float:
    total = 0.0
    for i in range(1, len(points)):
        p1, p2 = points[i - 1], points[i]
        total += haversine_m(p1["lat"], p1["lng"], p2["lat"], p2["lng"])
    return round(total, 1)


def calc_max_speed(points: list[dict]) -> float:
    speeds = [p["speed"] for p in points if p.get("speed") is not None and p["speed"] >= 0]
    return round(max(speeds), 1) if speeds else 0.0


@app.post("/upload")
async def upload_video(file: UploadFile = File(...)):
    video_id = str(uuid.uuid4())
    os.makedirs("uploads", exist_ok=True)
    file_location = f"uploads/{video_id}_{file.filename}"
    with open(file_location, "wb") as f_out:
        f_out.write(await file.read())
    video_db[video_id] = file_location
    return {"status": "success", "video_id": video_id, "filename": file.filename}


@app.post("/analyze")
async def analyze_video(video_id: str = Form(...)):
    if video_id not in video_db:
        return JSONResponse({"error": "视频ID未找到"}, status_code=404)
    analysis_result = {
        "inclination": 60,
        "stabilityScore": 85,
        "powerPoint": "奴隶关节",
    }
    return analysis_result


@app.get("/plan")
async def get_plan(resort: str):
    plans = {
        "wanlong": ["基础刻滑训练", "节奏稳定练习", "弧线控制进阶"],
        "thaiwoo": ["换刃节奏专项", "公园地形体验", "中高速弯道训练"],
        "yun-ding": ["重心迁移专练", "压强连续性", "基础自由滑行"],
        "beidahu": ["雪道适应训练", "连续弯道切换", "反脚滑行基础"],
        "songhua": ["地形公园基础", "短回转节奏", "平行式高级"],
        "yabuli": ["猫跳道专项", "纵向发力训练", "高频动作记忆"],
        "maoershan": ["节奏固化练习", "姿态对称训练", "入门至进阶全链路"],
    }
    plan = plans.get(resort.lower(), ["暂无对应计划，请选择有效雪场"])
    return {"resort": resort, "plan": plan}


# ── GPS 滑雪记录 API ──

@app.post("/gps/session/start")
async def start_gps_session(body: GpsSessionCreate = GpsSessionCreate()):
    session_id = str(uuid.uuid4())
    now = datetime.utcnow().isoformat() + "Z"
    gps_sessions[session_id] = {
        "session_id": session_id,
        "name": body.name or f"滑行记录 {datetime.now().strftime('%m-%d %H:%M')}",
        "status": "recording",
        "started_at": now,
        "ended_at": None,
        "points": [],
        "distance_m": 0.0,
        "max_speed_kmh": 0.0,
        "duration_s": 0,
    }
    return {"session_id": session_id, "started_at": now}


@app.post("/gps/session/{session_id}/point")
async def add_gps_point(session_id: str, point: GpsPoint):
    session = gps_sessions.get(session_id)
    if not session:
        return JSONResponse({"error": "会话未找到"}, status_code=404)
    if session["status"] != "recording":
        return JSONResponse({"error": "会话未在录制中"}, status_code=400)

    pt = {
        "lat": point.lat,
        "lng": point.lng,
        "altitude": point.altitude,
        "speed": point.speed,
        "accuracy": point.accuracy,
        "timestamp": point.timestamp or datetime.utcnow().isoformat() + "Z",
    }
    session["points"].append(pt)
    session["distance_m"] = calc_track_distance(session["points"])
    session["max_speed_kmh"] = calc_max_speed(session["points"])

    return {
        "point_count": len(session["points"]),
        "distance_m": session["distance_m"],
        "max_speed_kmh": session["max_speed_kmh"],
    }


@app.post("/gps/session/{session_id}/stop")
async def stop_gps_session(session_id: str):
    session = gps_sessions.get(session_id)
    if not session:
        return JSONResponse({"error": "会话未找到"}, status_code=404)

    now = datetime.utcnow().isoformat() + "Z"
    session["status"] = "completed"
    session["ended_at"] = now
    session["distance_m"] = calc_track_distance(session["points"])
    session["max_speed_kmh"] = calc_max_speed(session["points"])

    if session["points"]:
        start_ts = session["points"][0].get("timestamp", session["started_at"])
        end_ts = session["points"][-1].get("timestamp", now)
        try:
            t0 = datetime.fromisoformat(start_ts.replace("Z", "+00:00"))
            t1 = datetime.fromisoformat(end_ts.replace("Z", "+00:00"))
            session["duration_s"] = max(0, int((t1 - t0).total_seconds()))
        except ValueError:
            session["duration_s"] = 0

    return {
        "session_id": session_id,
        "distance_m": session["distance_m"],
        "max_speed_kmh": session["max_speed_kmh"],
        "duration_s": session["duration_s"],
        "point_count": len(session["points"]),
    }


@app.get("/gps/sessions")
async def list_gps_sessions():
    sessions = sorted(
        gps_sessions.values(),
        key=lambda s: s["started_at"],
        reverse=True,
    )
    return {
        "sessions": [
            {
                "session_id": s["session_id"],
                "name": s["name"],
                "status": s["status"],
                "started_at": s["started_at"],
                "ended_at": s["ended_at"],
                "distance_m": s["distance_m"],
                "max_speed_kmh": s["max_speed_kmh"],
                "duration_s": s["duration_s"],
                "point_count": len(s["points"]),
            }
            for s in sessions
        ]
    }


@app.get("/gps/session/{session_id}")
async def get_gps_session(session_id: str):
    session = gps_sessions.get(session_id)
    if not session:
        return JSONResponse({"error": "会话未找到"}, status_code=404)
    return session


# ── Coach Marketplace ──

class Coach(BaseModel):
    id: str
    name: str
    ski_type: str
    level: str
    experience: int
    hourly_rate: float
    rating: float
    location: str
    avatar: str


class Booking(BaseModel):
    id: str
    coach_id: str
    user_name: str
    date: str
    duration: int
    status: str


class BookingCreate(BaseModel):
    coach_id: str
    user_name: str
    date: str
    duration: int


class RecommendCoachRequest(BaseModel):
    ski_level: str
    ski_type: str
    goal: str


SKI_TYPE_MAP = {
    "single": "单板",
    "double": "双板",
    "snowboard": "单板",
    "ski": "双板",
}

GOAL_LABELS = {
    "parallel_turn": "平行转弯",
    "carving": "刻滑",
    "switch": "反脚滑行",
    "park": "公园技巧",
    "freeride": "全山地滑行",
    "short_turn": "短回转",
    "mogul": "猫跳道",
}

LEVEL_WEIGHT = {
    "beginner": {"中级": 28, "高级": 35, "专家": 22},
    "intermediate": {"中级": 22, "高级": 32, "专家": 28},
    "advanced": {"中级": 15, "高级": 28, "专家": 35},
}


def score_coach(coach: dict, ski_level: str, ski_type_cn: str, goal: str) -> int:
    if coach["ski_type"] != ski_type_cn:
        return 0

    score = 40
    score += LEVEL_WEIGHT.get(ski_level, LEVEL_WEIGHT["beginner"]).get(coach["level"], 20)
    score += min(coach["experience"] * 1.5, 15)
    score += coach["rating"] * 5

    if goal in ("parallel_turn", "carving") and coach["level"] in ("高级", "专家"):
        score += 5
    if goal in ("park", "switch") and coach["ski_type"] == "单板":
        score += 5
    if goal in ("short_turn", "mogul") and coach["ski_type"] == "双板":
        score += 5

    return min(round(score), 99)


def build_recommend_reason(coach: dict, ski_type_cn: str, goal: str) -> str:
    goal_label = GOAL_LABELS.get(goal, goal)
    return f"拥有{coach['experience']}年{ski_type_cn}教学经验，擅长{goal_label}专项指导"

coaches_db: dict[str, dict] = {
    "coach-001": {
        "id": "coach-001",
        "name": "李明",
        "ski_type": "单板",
        "level": "高级",
        "experience": 8,
        "hourly_rate": 380.0,
        "rating": 4.9,
        "location": "崇礼 · 万龙滑雪场",
        "avatar": "https://api.dicebear.com/7.x/avataaars/svg?seed=liming",
    },
    "coach-002": {
        "id": "coach-002",
        "name": "王雪",
        "ski_type": "双板",
        "level": "专家",
        "experience": 12,
        "hourly_rate": 480.0,
        "rating": 4.8,
        "location": "崇礼 · 云顶滑雪公园",
        "avatar": "https://api.dicebear.com/7.x/avataaars/svg?seed=wangxue",
    },
    "coach-003": {
        "id": "coach-003",
        "name": "张凯",
        "ski_type": "单板",
        "level": "中级",
        "experience": 5,
        "hourly_rate": 280.0,
        "rating": 4.6,
        "location": "吉林 · 北大湖滑雪度假区",
        "avatar": "https://api.dicebear.com/7.x/avataaars/svg?seed=zhangkai",
    },
    "coach-004": {
        "id": "coach-004",
        "name": "陈静",
        "ski_type": "双板",
        "level": "高级",
        "experience": 9,
        "hourly_rate": 420.0,
        "rating": 4.7,
        "location": "吉林 · 松花湖滑雪场",
        "avatar": "https://api.dicebear.com/7.x/avataaars/svg?seed=chenjing",
    },
    "coach-005": {
        "id": "coach-005",
        "name": "刘洋",
        "ski_type": "单板",
        "level": "专家",
        "experience": 15,
        "hourly_rate": 580.0,
        "rating": 5.0,
        "location": "哈尔滨 · 亚布力滑雪旅游度假区",
        "avatar": "https://api.dicebear.com/7.x/avataaars/svg?seed=liuyang",
    },
}

bookings_db: dict[str, dict] = {}


@app.get("/coaches")
async def list_coaches():
    return {"coaches": list(coaches_db.values())}


@app.get("/coaches/{coach_id}")
async def get_coach(coach_id: str):
    coach = coaches_db.get(coach_id)
    if not coach:
        return JSONResponse({"error": "教练未找到"}, status_code=404)
    return coach


@app.post("/booking")
async def create_booking(body: BookingCreate):
    if body.coach_id not in coaches_db:
        return JSONResponse({"error": "教练未找到"}, status_code=404)
    if body.duration <= 0:
        return JSONResponse({"error": "预约时长必须大于 0"}, status_code=400)

    booking_id = str(uuid.uuid4())
    booking = {
        "id": booking_id,
        "coach_id": body.coach_id,
        "user_name": body.user_name,
        "date": body.date,
        "duration": body.duration,
        "status": "pending",
    }
    bookings_db[booking_id] = booking
    return booking


@app.get("/bookings")
async def list_bookings():
    bookings = sorted(
        bookings_db.values(),
        key=lambda b: b["date"],
        reverse=True,
    )
    return {"bookings": bookings}


@app.post("/recommend-coach")
async def recommend_coach(body: RecommendCoachRequest):
    ski_type_cn = SKI_TYPE_MAP.get(body.ski_type.lower())
    if not ski_type_cn:
        return JSONResponse({"error": "无效的 ski_type，请使用 single 或 double"}, status_code=400)

    ski_level = body.ski_level.lower()
    if ski_level not in LEVEL_WEIGHT:
        return JSONResponse({"error": "无效的 ski_level，请使用 beginner / intermediate / advanced"}, status_code=400)

    candidates = [
        (score_coach(coach, ski_level, ski_type_cn, body.goal), coach)
        for coach in coaches_db.values()
    ]
    candidates = [(s, c) for s, c in candidates if s > 0]

    if not candidates:
        return JSONResponse({"error": "暂无匹配的教练"}, status_code=404)

    best_score, best_coach = max(candidates, key=lambda x: x[0])

    return {
        "coach": f"{best_coach['name']}教练",
        "match_score": best_score,
        "reason": build_recommend_reason(best_coach, ski_type_cn, body.goal),
    }
