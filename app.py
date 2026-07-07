import os
import logging
import base64
import json
from datetime import datetime, date, timedelta
from uuid import uuid4

from flask import Flask, request, jsonify, render_template, session, redirect, url_for
from flask_cors import CORS
from werkzeug.middleware.proxy_fix import ProxyFix

import cv2
import numpy as np
from numpy.linalg import norm
from deepface import DeepFace

# -------------------------------------------------
# APP CONFIG
# -------------------------------------------------
app = Flask(__name__)
app.secret_key = os.environ.get("VERIFY_SECRET_KEY", "change-this-key")

# ✅ Restricted CORS (set your real domain here)
CORS(app, resources={r"/*": {"origins": ["https://chemist2door.co.uk"]}})
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("verify-service")

# -------------------------------------------------
# GDPR CONFIG
# -------------------------------------------------
GDPR_CONFIG = {
    "controller_name": "Chemist2Door Ltd",
    "lawful_basis": "legal_obligation",
    "contact_email": "support@chemist2door.co.uk",
    "retention_days": 7,  # audit logs kept max 7 days
}

# -------------------------------------------------
# FILES
# -------------------------------------------------
STATS_FILE = "daily_stats.json"
AUDIT_FILE = "audit_log.json"

ADMIN_USER = os.environ.get("VERIFY_ADMIN_USER", "admin")
ADMIN_PASS = os.environ.get("VERIFY_ADMIN_PASS", "strongpassword")

# -------------------------------------------------
# HELPERS
# -------------------------------------------------
def load_json_file(path, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r") as f:
            return json.load(f)
    except:
        return default

def save_json_file(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=4)

def load_stats():
    return load_json_file(STATS_FILE, {})

def save_stats(stats):
    save_json_file(STATS_FILE, stats)

def update_stats(result):
    today = date.today().isoformat()
    stats = load_stats()

    if today not in stats:
        stats[today] = {
            "total_attempts": 0,
            "verified": 0,
            "failed": 0
        }

    stats[today]["total_attempts"] += 1
    if result:
        stats[today]["verified"] += 1
    else:
        stats[today]["failed"] += 1

    save_stats(stats)

def cleanup_audit_logs(logs):
    cutoff = datetime.utcnow() - timedelta(days=GDPR_CONFIG["retention_days"])
    cleaned = []
    for log in logs:
        try:
            ts = datetime.fromisoformat(log["timestamp"].replace("Z", ""))
            if ts >= cutoff:
                cleaned.append(log)
        except:
            # if timestamp bad, drop it
            continue
    return cleaned

def add_audit_log(verification_id, result, method="face_match"):
    logs = load_json_file(AUDIT_FILE, [])
    logs = cleanup_audit_logs(logs)
    logs.append({
        "verification_id": verification_id,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "result": "verified" if result else "failed",
        "method": method
    })
    save_json_file(AUDIT_FILE, logs)

def get_audit_logs():
    logs = load_json_file(AUDIT_FILE, [])
    logs = cleanup_audit_logs(logs)
    save_json_file(AUDIT_FILE, logs)
    return logs

# -------------------------------------------------
# SIMPLE RATE LIMITING
# -------------------------------------------------
RATE_LIMIT_WINDOW = 60  # seconds
RATE_LIMIT_MAX = 30     # requests per window
rate_cache = {}

def check_rate_limit(ip):
    now = datetime.utcnow()
    entry = rate_cache.get(ip)
    if not entry:
        rate_cache[ip] = {"count": 1, "reset": now + timedelta(seconds=RATE_LIMIT_WINDOW)}
        return True
    if now > entry["reset"]:
        rate_cache[ip] = {"count": 1, "reset": now + timedelta(seconds=RATE_LIMIT_WINDOW)}
        return True
    if entry["count"] >= RATE_LIMIT_MAX:
        return False
    entry["count"] += 1
    return True

# -------------------------------------------------
# FACE CONFIG
# -------------------------------------------------
FACE_PASS = 0.55
FACE_STRONG = 0.60
LIVENESS_MIN_SCORE = 0.20

DETECTOR_BACKEND = "retinaface"
MODEL_NAME = "Facenet512"

# -------------------------------------------------
# IMAGE UTILITIES
# -------------------------------------------------
def decode_image_base64(data):
    try:
        img_bytes = base64.b64decode(data)
        np_arr = np.frombuffer(img_bytes, np.uint8)
        img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
        if img is None:
            return None
        return cv2.resize(img, (500, 500))
    except:
        return None

def extract_embedding(result):
    try:
        emb = result[0].get("embedding")
        return np.array(emb, dtype=np.float32)
    except:
        return None

def get_embedding(img, strict=True):
    try:
        result = DeepFace.represent(
            img_path=img,
            model_name=MODEL_NAME,
            enforce_detection=strict,
            detector_backend=DETECTOR_BACKEND,
            align=True,
        )
        return extract_embedding(result)
    except Exception as e:
        logger.error(f"DeepFace failed: {e}")
        return None

def basic_liveness_score(selfie_img):
    try:
        gray = cv2.cvtColor(selfie_img, cv2.COLOR_BGR2GRAY)
        fm = cv2.Laplacian(gray, cv2.CV_64F).var()

        if fm < 50:
            return 0.30
        elif fm < 150:
            return 0.50
        elif fm < 300:
            return 0.70
        return 1.0
    except:
        return 0.0

# -------------------------------------------------
# SECURITY HEADERS
# -------------------------------------------------
@app.after_request
def add_security_headers(response):
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Content-Security-Policy"] = "default-src 'self'; img-src 'self' data:;"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response

# -------------------------------------------------
# AUTH HELPERS
# -------------------------------------------------
def is_admin():
    return session.get("is_admin") is True

def require_admin():
    if not is_admin():
        return redirect(url_for("admin_login"))

# -------------------------------------------------
# ROUTES: PUBLIC
# -------------------------------------------------
@app.route("/")
def home():
    return render_template("index.html")

@app.route("/gdpr/info", methods=["GET"])
def gdpr_info():
    return jsonify({
        "controller": GDPR_CONFIG["controller_name"],
        "lawful_basis": GDPR_CONFIG["lawful_basis"],
        "contact_email": GDPR_CONFIG["contact_email"],
        "retention_days": GDPR_CONFIG["retention_days"],
        "note": "Images and embeddings are processed in memory only and not stored."
    })

@app.route("/privacy", methods=["GET"])
def privacy():
    return jsonify({
        "purpose": "Identity/age verification for restricted pharmacy services.",
        "data_processed": ["selfie image", "ID image (face area only)"],
        "storage": "No images or embeddings are stored; only aggregated stats and non-personal audit logs (max 7 days).",
        "rights": [
            "Right of access",
            "Right to erasure",
            "Right to object",
            "Right to restriction",
            "Right to human review of automated decisions"
        ],
        "contact_email": GDPR_CONFIG["contact_email"]
    })

@app.route("/verify/review", methods=["POST"])
def request_human_review():
    data = request.get_json(silent=True) or {}
    verification_id = data.get("verification_id")
    reason = data.get("reason", "user_disagrees_with_automated_decision")
    logger.info(f"HUMAN REVIEW REQUEST: id={verification_id}, reason={reason}")
    return jsonify({"status": True, "message": "Human review requested"}), 200

@app.route("/user/export", methods=["POST"])
def user_export():
    return jsonify({
        "status": True,
        "message": "No user-specific personal data stored by this verification service. Only aggregated stats and non-personal audit logs (without names/IP) are kept for max 7 days."
    }), 200

@app.route("/user/delete", methods=["POST"])
def user_delete():
    return jsonify({
        "status": True,
        "message": "No user-specific personal data stored; nothing to delete in this service."
    }), 200

@app.route("/verify", methods=["POST"])
def verify():
    try:
        ip = request.headers.get("X-Forwarded-For", request.remote_addr)
        if not check_rate_limit(ip):
            return jsonify({"status": False, "message": "Rate limit exceeded"}), 429

        data = request.get_json(silent=True) or {}

        logger.info("=== NEW VERIFICATION REQUEST RECEIVED ===")
        logger.info(f"Raw selfie length: {len(str(data.get('selfie')))}")
        logger.info(f"Raw ID length: {len(str(data.get('id_image')))}")

        selfie_b64 = data.get("selfie")
        id_b64 = data.get("id_image")

        selfie = decode_image_base64(selfie_b64)
        id_img = decode_image_base64(id_b64)

        verification_id = str(uuid4())

        if selfie is None or id_img is None:
            update_stats(False)
            add_audit_log(verification_id, False)
            return jsonify({"status": False, "message": "Invalid images", "verification_id": verification_id}), 400

        liveness_score = basic_liveness_score(selfie)
        logger.info(f"LIVENESS SCORE = {liveness_score}")

        if liveness_score < LIVENESS_MIN_SCORE:
            update_stats(False)
            add_audit_log(verification_id, False)
            return jsonify({"status": False, "message": "Liveness failed", "verification_id": verification_id}), 422

        emb_selfie = get_embedding(selfie, strict=True)
        emb_id = get_embedding(id_img, strict=True)

        if emb_selfie is None or emb_id is None:
            update_stats(False)
            add_audit_log(verification_id, False)
            return jsonify({"status": False, "message": "Face not detected", "verification_id": verification_id}), 422

        emb_selfie = emb_selfie / np.linalg.norm(emb_selfie)
        emb_id = emb_id / np.linalg.norm(emb_id)

        face_similarity = float(np.dot(emb_selfie, emb_id))
        logger.info(f"FACE SIMILARITY = {face_similarity}")

        if face_similarity >= FACE_STRONG or face_similarity >= FACE_PASS:
            update_stats(True)
            add_audit_log(verification_id, True)
            return jsonify({
                "status": True,
                "message": "Verified",
                "redirect": "https://chemist2door.co.uk",
                "automated_decision": True,
                "verification_id": verification_id
            }), 200

        update_stats(False)
        add_audit_log(verification_id, False)
        return jsonify({
            "status": False,
            "message": "Face mismatch",
            "automated_decision": True,
            "verification_id": verification_id,
            "human_review_endpoint": "/verify/review"
        }), 200

    except Exception as e:
        logger.exception("SERVER ERROR")
        update_stats(False)
        return jsonify({"status": False, "message": "Server error"}), 500

# -------------------------------------------------
# ADMIN AUTH + STATS
# -------------------------------------------------
@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "GET":
        return jsonify({"message": "Send JSON {username, password} via POST to login as admin."})
    data = request.get_json(silent=True) or {}
    username = data.get("username")
    password = data.get("password")
    if username == ADMIN_USER and password == ADMIN_PASS:
        session["is_admin"] = True
        return jsonify({"status": True, "message": "Admin logged in"})
    return jsonify({"status": False, "message": "Invalid credentials"}), 401

@app.route("/admin/logout", methods=["POST"])
def admin_logout():
    session.pop("is_admin", None)
    return jsonify({"status": True, "message": "Admin logged out"})

@app.route("/stats", methods=["GET"])
def stats():
    if not is_admin():
        return require_admin()
    return jsonify(load_stats())

@app.route("/stats/audit", methods=["GET"])
def stats_audit():
    if not is_admin():
        return require_admin()
    logs = get_audit_logs()
    return jsonify(logs)

@app.route("/stats/download", methods=["GET"])
def stats_download():
    if not is_admin():
        return require_admin()
    logs = get_audit_logs()
    # Simple JSON download; for CSV you can format as needed
    return jsonify({
        "status": True,
        "count": len(logs),
        "logs": logs
    })

# -------------------------------------------------
# MAIN
# -------------------------------------------------
if __name__ == "__main__":
    # HTTPS enforced at reverse proxy on your SSL subdomain.
    app.run(host="0.0.0.0", port=5000, debug=False)
