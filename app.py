import os
import json
import base64
import logging
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import cv2
import numpy as np

from flask import (
    Flask,
    request,
    jsonify,
    render_template,
    session,
    redirect,
    url_for
)

from flask_cors import CORS
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import check_password_hash

from deepface import DeepFace


# =================================================
# APP CONFIG
# =================================================

app = Flask(__name__)

app.secret_key = os.environ.get(
    "FLASK_SECRET_KEY",
    "CHANGE_THIS_SECRET_IN_ENV"
)

app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SECURE=True,
    SESSION_COOKIE_SAMESITE="Lax",
    PERMANENT_SESSION_LIFETIME=timedelta(minutes=30)
)

app.wsgi_app = ProxyFix(
    app.wsgi_app,
    x_for=1,
    x_proto=1,
    x_host=1
)

CORS(
    app,
    resources={
        r"/verify": {
            "origins": [
                "https://chemist2door.co.uk",
                "https://verify.chemist2door.co.uk"
            ]
        }
    }
)


# =================================================
# SECURITY HEADERS
# =================================================

@app.after_request
def security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin"
    response.headers["Permissions-Policy"] = "camera=(self)"
    return response


# =================================================
# LOGGING
# =================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s"
)

logger = logging.getLogger("chemist2door-verification")


# =================================================
# GDPR SETTINGS
# =================================================

GDPR_CONFIG = {
    "retention_days": 7,
    "max_image_size": 5 * 1024 * 1024
}


# =================================================
# FILE STORAGE
# =================================================

STATS_FILE = "daily_stats.json"
AUDIT_FILE = "audit_log.json"


# =================================================
# ADMIN AUTH
# =================================================

ADMIN_USER = os.environ.get(
    "ADMIN_USER",
    "chemist2door"
)

ADMIN_PASSWORD_HASH = os.environ.get(
    "ADMIN_PASSWORD_HASH",
    ""
)


# =================================================
# JSON HELPERS
# =================================================

def load_json_file(path, default):
    if not os.path.exists(path):
        return default

    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save_json_file(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)


# =================================================
# GDPR AUDIT CLEANUP
# =================================================

def cleanup_audit_logs(logs):
    cutoff = datetime.now(timezone.utc) - timedelta(
        days=GDPR_CONFIG["retention_days"]
    )

    cleaned = []

    for item in logs:
        try:
            timestamp = datetime.fromisoformat(
                item["timestamp"].replace("Z", "+00:00")
            )

            if timestamp >= cutoff:
                cleaned.append(item)

        except Exception:
            continue

    return cleaned


def add_audit_log(verification_id, result, reason):
    logs = load_json_file(AUDIT_FILE, [])
    logs = cleanup_audit_logs(logs)

    logs.append({
        "verification_id": verification_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "result": "verified" if result else "failed",
        "reason": reason
    })

    save_json_file(AUDIT_FILE, logs)


def get_audit_logs():
    logs = load_json_file(AUDIT_FILE, [])
    logs = cleanup_audit_logs(logs)
    save_json_file(AUDIT_FILE, logs)
    return logs


# =================================================
# IMAGE SECURITY + PROCESSING
# =================================================

def decode_image_base64(data):
    try:
        if not data:
            return None

        if "," in data:
            data = data.split(",", 1)[1]

        raw = base64.b64decode(data, validate=True)

        if len(raw) > GDPR_CONFIG["max_image_size"]:
            logger.warning("Image too large")
            return None

        np_arr = np.frombuffer(raw, np.uint8)
        img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

        if img is None:
            logger.warning("OpenCV could not decode image")
            return None

        return img

    except Exception as e:
        logger.warning("Image decode failed: %s", e)
        return None


# =================================================
# FACE EMBEDDING
# =================================================

def extract_embedding(result):
    try:
        if not result:
            return None

        embedding = result[0].get("embedding")

        if not embedding:
            return None

        return np.array(embedding, dtype=np.float32)

    except Exception:
        return None


def get_embedding(image, strict=True):
    try:
        result = DeepFace.represent(
            img_path=image,
            model_name="Facenet512",
            detector_backend="opencv",
            enforce_detection=strict,
            align=True
        )

        return extract_embedding(result)

    except Exception as e:
        logger.info("Face extraction failed: %s", e)
        return None


# =================================================
# BASIC LIVENESS CHECK
# =================================================

def basic_liveness_score(selfie_img):
    try:
        gray = cv2.cvtColor(selfie_img, cv2.COLOR_BGR2GRAY)
        blur_score = cv2.Laplacian(gray, cv2.CV_64F).var()

        if blur_score < 50:
            return 0.25

        if blur_score < 150:
            return 0.50

        if blur_score < 300:
            return 0.75

        return 1.0

    except Exception:
        return 0.0


# =================================================
# FACE MATCHING
# =================================================

def compare_faces(selfie_embedding, id_embedding):
    try:
        selfie_norm = np.linalg.norm(selfie_embedding)
        id_norm = np.linalg.norm(id_embedding)

        if selfie_norm == 0 or id_norm == 0:
            return 0.0

        selfie_embedding = selfie_embedding / selfie_norm
        id_embedding = id_embedding / id_norm

        similarity = float(np.dot(selfie_embedding, id_embedding))
        return similarity

    except Exception:
        return 0.0


# =================================================
# VERIFICATION RESULT LOGGER
# =================================================

def verification_audit(verification_id, status, reason):
    add_audit_log(
        verification_id,
        status,
        reason
    )

    logger.info(
        "Verification %s : %s",
        verification_id,
        reason
    )


# =================================================
# AUTH HELPERS
# =================================================

def is_admin():
    return session.get("is_admin", False) is True


# =================================================
# ADMIN ROUTES
# =================================================

@app.route("/login/admin")
def login_admin_redirect():
    return redirect(url_for("admin_login"))


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "GET":
        return render_template("admin_login.html")

    username = request.form.get("username", "")
    password = request.form.get("password", "")

    if (
        username == ADMIN_USER
        and ADMIN_PASSWORD_HASH
        and check_password_hash(ADMIN_PASSWORD_HASH, password)
    ):
        session.permanent = True
        session["is_admin"] = True
        return redirect(url_for("stats"))

    return render_template(
        "admin_login.html",
        error="Invalid credentials"
    )


@app.route("/stats")
def stats():
    if not is_admin():
        return redirect(url_for("admin_login"))

    stats_data = load_json_file(STATS_FILE, {})
    logs = get_audit_logs()

    return render_template(
        "stats.html",
        stats=stats_data,
        logs=logs
    )


# =================================================
# STATS UPDATE
# =================================================

def update_stats(result):
    today = datetime.now(timezone.utc).date().isoformat()
    stats = load_json_file(STATS_FILE, {})

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

    save_json_file(STATS_FILE, stats)


# =================================================
# VERIFY API
# =================================================

@app.route("/verify", methods=["POST"])
def verify():
    verification_id = str(uuid4())

    try:
        data = request.get_json(silent=True) or {}

        selfie = decode_image_base64(data.get("selfie"))
        id_image = decode_image_base64(data.get("id_image"))

        if selfie is None or id_image is None:
            update_stats(False)
            verification_audit(
                verification_id,
                False,
                "invalid_images"
            )

            return jsonify({
                "status": False,
                "message": "Invalid images"
            }), 400

        live_score = basic_liveness_score(selfie)

        if live_score < 0.50:
            update_stats(False)
            verification_audit(
                verification_id,
                False,
                "liveness_failed"
            )

            return jsonify({
                "status": False,
                "message": "Liveness failed"
            }), 422

        selfie_embedding = get_embedding(selfie)
        id_embedding = get_embedding(id_image)

        if selfie_embedding is None or id_embedding is None:
            update_stats(False)
            verification_audit(
                verification_id,
                False,
                "face_not_detected"
            )

            return jsonify({
                "status": False,
                "message": "Face not detected"
            }), 422

        similarity = compare_faces(selfie_embedding, id_embedding)

        logger.info(
            "Verification %s similarity score: %.4f",
            verification_id,
            similarity
        )

        if similarity >= 0.55:
            update_stats(True)
            verification_audit(
                verification_id,
                True,
                "verified"
            )

            return jsonify({
                "status": True,
                "redirect": "/"
            }), 200

        update_stats(False)
        verification_audit(
            verification_id,
            False,
            "face_mismatch"
        )

        return jsonify({
            "status": False,
            "message": "Face mismatch"
        }), 200

    except Exception as e:
        logger.exception("Verification error: %s", e)

        update_stats(False)
        verification_audit(
            verification_id,
            False,
            "server_error"
        )

        return jsonify({
            "status": False,
            "message": "Server error"
        }), 500


# =================================================
# START SERVER
# =================================================

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=5000,
        debug=False
    )
