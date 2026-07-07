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
from deepface import DeepFace

# -------------------------------------------------
# APP CONFIG
# -------------------------------------------------
app = Flask(__name__)
app.secret_key = "change-this-key"

CORS(app, resources={r"/*": {"origins": ["https://chemist2door.co.uk"]}})
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("verify-service")

# -------------------------------------------------
# GDPR CONFIG
# -------------------------------------------------
GDPR_CONFIG = {
    "retention_days": 7
}

# -------------------------------------------------
# FILES
# -------------------------------------------------
STATS_FILE = "daily_stats.json"
AUDIT_FILE = "audit_log.json"

ADMIN_USER = "chemist2door"
ADMIN_PASS = "Ali123?"

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
        stats[today] = {"total_attempts": 0, "verified": 0, "failed": 0}

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
            continue
    return cleaned

def add_audit_log(verification_id, result, reason):
    logs = load_json_file(AUDIT_FILE, [])
    logs = cleanup_audit_logs(logs)
    logs.append({
        "verification_id": verification_id,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "result": "verified" if result else "failed",
        "reason": reason
    })
    save_json_file(AUDIT_FILE, logs)

def get_audit_logs():
    logs = load_json_file(AUDIT_FILE, [])
    logs = cleanup_audit_logs(logs)
    save_json_file(AUDIT_FILE, logs)
    return logs

# -------------------------------------------------
# IMAGE UTILITIES
# -------------------------------------------------
def decode_image_base64(data):
    try:
        if "," in data:
            data = data.split(",")[1]
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
            model_name="Facenet512",
            enforce_detection=strict,
            detector_backend="retinaface",
            align=True,
        )
        return extract_embedding(result)
    except:
        return None

def basic_liveness_score(selfie_img):
    try:
        gray = cv2.cvtColor(selfie_img, cv2.COLOR_BGR2GRAY)
        fm = cv2.Laplacian(gray, cv2.CV_64F).var()
        if fm < 50: return 0.30
        if fm < 150: return 0.50
        if fm < 300: return 0.70
        return 1.0
    except:
        return 0.0

# -------------------------------------------------
# AUTH HELPERS
# -------------------------------------------------
def is_admin():
    return session.get("is_admin") is True

# -------------------------------------------------
# ROUTES
# -------------------------------------------------
@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "GET":
        return render_template("admin_login.html")

    username = request.form.get("username")
    password = request.form.get("password")

    if username == ADMIN_USER and password == ADMIN_PASS:
        session["is_admin"] = True
        return redirect(url_for("stats"))

    return render_template("admin_login.html", error="Invalid credentials")

@app.route("/stats", methods=["GET"])
def stats():
    if not is_admin():
        return redirect(url_for("admin_login"))

    stats_data = load_stats()
    logs = get_audit_logs()

    return render_template("stats.html", stats=stats_data, logs=logs)

@app.route("/verify", methods=["POST"])
def verify():
    try:
        data = request.get_json(silent=True) or {}

        selfie = decode_image_base64(data.get("selfie"))
        id_img = decode_image_base64(data.get("id_image"))

        verification_id = str(uuid4())

        if selfie is None or id_img is None:
            update_stats(False)
            add_audit_log(verification_id, False, "invalid_images")
            return jsonify({"status": False}), 400

        liveness_score = basic_liveness_score(selfie)
        if liveness_score < 0.20:
            update_stats(False)
            add_audit_log(verification_id, False, "liveness_failed")
            return jsonify({"status": False}), 422

        emb_selfie = get_embedding(selfie)
        emb_id = get_embedding(id_img)

        if emb_selfie is None or emb_id is None:
            update_stats(False)
            add_audit_log(verification_id, False, "face_not_detected")
            return jsonify({"status": False}), 422

        emb_selfie = emb_selfie / np.linalg.norm(emb_selfie)
        emb_id = emb_id / np.linalg.norm(emb_id)

        similarity = float(np.dot(emb_selfie, emb_id))

        if similarity >= 0.55:
            update_stats(True)
            add_audit_log(verification_id, True, "verified")
            return jsonify({"status": True}), 200

        update_stats(False)
        add_audit_log(verification_id, False, "face_mismatch")
        return jsonify({"status": False}), 200

    except:
        update_stats(False)
        return jsonify({"status": False}), 500

# -------------------------------------------------
# MAIN
# -------------------------------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
