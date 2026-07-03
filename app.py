import os
import logging
import base64
import re
from datetime import datetime, date

from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from werkzeug.middleware.proxy_fix import ProxyFix

import cv2
import numpy as np
from numpy.linalg import norm
from deepface import DeepFace
import pytesseract

# -------------------------------------------------
# APP CONFIG (PRODUCTION READY)
# -------------------------------------------------
app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

# If behind reverse proxy / load balancer
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1)

# Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

logger = logging.getLogger("verify-service")

# -------------------------------------------------
# SECURITY / LIMITS
# -------------------------------------------------
MAX_IMAGE_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB
ALLOWED_CONTENT_TYPES = {"application/json"}

# Simple rate limit placeholder (per IP, in-memory)
RATE_LIMIT_MAX_REQUESTS = 60
RATE_LIMIT_WINDOW_SECONDS = 60
_rate_limit_store = {}


def rate_limit_check(ip):
    now = datetime.utcnow().timestamp()
    window_start = now - RATE_LIMIT_WINDOW_SECONDS

    if ip not in _rate_limit_store:
        _rate_limit_store[ip] = []

    # Purge old entries
    _rate_limit_store[ip] = [t for t in _rate_limit_store[ip] if t >= window_start]

    if len(_rate_limit_store[ip]) >= RATE_LIMIT_MAX_REQUESTS:
        return False

    _rate_limit_store[ip].append(now)
    return True


# -------------------------------------------------
# THRESHOLDS (TUNEABLE)
# -------------------------------------------------
FACE_HARD_FAIL = float(os.getenv("FACE_HARD_FAIL", 0.60))
FACE_STRONG_PASS = float(os.getenv("FACE_STRONG_PASS", 0.82))
EYE_HARD_FAIL = float(os.getenv("EYE_HARD_FAIL", 0.55))
EYE_STRONG_PASS = float(os.getenv("EYE_STRONG_PASS", 0.80))

MIN_AGE = int(os.getenv("MIN_AGE", 18))

# -------------------------------------------------
# DEEPFACE MODEL CACHE (PERFORMANCE)
# -------------------------------------------------
# DeepFace internally caches models, but we can still pre-load if needed.
DETECTOR_BACKEND = os.getenv("DETECTOR_BACKEND", "retinaface")
MODEL_NAME = os.getenv("MODEL_NAME", "Facenet512")


# -------------------------------------------------
# UTILITIES
# -------------------------------------------------
def safe_normalize(vec):
    try:
        n = norm(vec)
        return vec / n if n != 0 else vec
    except Exception:
        return vec


def decode_image(data):
    try:
        if not data:
            return None

        # Strip data URL prefix if present
        if "," in data:
            header, payload = data.split(",", 1)
            data = payload

        # Size guard
        if len(data) > MAX_IMAGE_SIZE_BYTES * 2:  # base64 approx
            logger.warning("Image too large")
            return None

        img_bytes = base64.b64decode(data)
        np_arr = np.frombuffer(img_bytes, np.uint8)
        img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

        if img is None:
            logger.warning("cv2.imdecode returned None")
            return None

        # Normalize size for embeddings
        return cv2.resize(img, (500, 500))

    except Exception:
        logger.exception("decode_image failed")
        return None


def extract_embedding(result):
    try:
        if isinstance(result, list) and len(result) > 0:
            emb = result[0].get("embedding")
            if emb is None:
                return None
            return np.array(emb, dtype=np.float32)
        return None
    except Exception:
        logger.exception("extract_embedding failed")
        return None


def extract_dob_from_id(id_img):
    try:
        gray = cv2.cvtColor(id_img, cv2.COLOR_BGR2GRAY)

        # Slight denoise + threshold to help OCR
        gray = cv2.medianBlur(gray, 3)
        _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

        text = pytesseract.image_to_string(thresh, config="--psm 6")
        text = text.replace(" ", "")

        patterns = [
            r"\d{4}-\d{2}-\d{2}",
            r"\d{2}/\d{2}/\d{4}",
            r"\d{2}\.\d{2}\.\d{4}",
        ]

        for p in patterns:
            m = re.findall(p, text)
            if m:
                candidate = m[0]
                try:
                    if "-" in candidate:
                        return datetime.strptime(candidate, "%Y-%m-%d").date()
                    elif "/" in candidate:
                        return datetime.strptime(candidate, "%d/%m/%Y").date()
                    elif "." in candidate:
                        return datetime.strptime(candidate, "%d.%m.%Y").date()
                except Exception:
                    continue

        return None

    except Exception:
        logger.exception("DOB extraction failed")
        return None


def calculate_age(dob):
    today = date.today()
    return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))


def crop_eye_region(img):
    try:
        h, w, _ = img.shape
        y1, y2 = int(h * 0.15), int(h * 0.45)
        x1, x2 = int(w * 0.20), int(w * 0.80)
        eye = img[y1:y2, x1:x2]
        if eye is None or eye.size == 0:
            return img
        return cv2.resize(eye, (300, 300))
    except Exception:
        logger.exception("crop_eye_region failed")
        return img


def get_embedding(img, strict=True):
    try:
        # DeepFace can accept numpy array directly
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


# -------------------------------------------------
# EXTRA FEATURE: SIMPLE LIVENESS / ANTI-SPOOF HOOK
# -------------------------------------------------
def basic_liveness_score(selfie_img):
    """
    Placeholder liveness scoring:
    - Checks for very low variance (flat photo)
    - Checks for over-blur
    - You can later plug in a real anti-spoof model here.
    Returns float in [0, 1].
    """
    try:
        gray = cv2.cvtColor(selfie_img, cv2.COLOR_BGR2GRAY)
        # Variance of Laplacian (blur detection)
        fm = cv2.Laplacian(gray, cv2.CV_64F).var()

        # Normalize to [0,1] with simple heuristic
        # fm ~ 0 => very blurry / flat
        # fm ~ 1000+ => sharp
        score = max(0.0, min(1.0, fm / 1000.0))
        return float(score)
    except Exception:
        logger.exception("basic_liveness_score failed")
        return 0.0


LIVENESS_MIN_SCORE = float(os.getenv("LIVENESS_MIN_SCORE", 0.25))


# -------------------------------------------------
# RESPONSE HELPERS
# -------------------------------------------------
def error_response(code, message, http_status=400, extra=None):
    payload = {
        "status": False,
        "code": code,
        "message": message,
    }
    if extra and isinstance(extra, dict):
        payload.update(extra)
    return jsonify(payload), http_status


def success_response(data=None):
    payload = {
        "status": True,
        "code": "VERIFIED",
        "message": "Verification successful",
    }
    if data and isinstance(data, dict):
        payload.update(data)
    return jsonify(payload), 200


# -------------------------------------------------
# ROUTES
# -------------------------------------------------
@app.route("/")
def home():
    return render_template("index.html")


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "service": "verify", "time": datetime.utcnow().isoformat()})


@app.route("/verify", methods=["POST"])
def verify():
    try:
        # -----------------------------
        # RATE LIMIT + CONTENT TYPE
        # -----------------------------
        ip = request.headers.get("X-Forwarded-For", request.remote_addr)
        if not rate_limit_check(ip):
            return error_response("RATE_LIMIT", "Too many requests", 429)

        if request.content_type not in ALLOWED_CONTENT_TYPES:
            return error_response("INVALID_CONTENT_TYPE", "Content-Type must be application/json", 415)

        data = request.get_json(silent=True) or {}

        selfie_b64 = data.get("selfie")
        id_b64 = data.get("id_image")

        if not selfie_b64 or not id_b64:
            return error_response("INVALID_IMAGE", "Invalid or missing images", 400)

        # -----------------------------
        # DECODE IMAGES
        # -----------------------------
        selfie = decode_image(selfie_b64)
        id_img = decode_image(id_b64)

        if selfie is None or id_img is None:
            return error_response("INVALID_IMAGE", "Unable to decode images", 400)

        # -----------------------------
        # LIVENESS / ANTI-SPOOF CHECK
        # -----------------------------
        liveness_score = basic_liveness_score(selfie)
        if liveness_score < LIVENESS_MIN_SCORE:
            logger.info(f"Liveness failed: score={liveness_score}")
            return error_response(
                "LIVENESS_FAIL",
                "Liveness / anti-spoof check failed",
                422,
                {"liveness_score": liveness_score},
            )

        # -----------------------------
        # AGE CHECK
        # -----------------------------
        dob = extract_dob_from_id(id_img)
        age = None
        age_checked = False
        underage_blocked = False

        if dob:
            age = calculate_age(dob)
            age_checked = True
            if age < MIN_AGE:
                underage_blocked = True

        # -----------------------------
        # FACE EMBEDDINGS
        # -----------------------------
        emb_selfie = get_embedding(selfie, strict=True)
        emb_id = get_embedding(id_img, strict=False)

        if emb_selfie is None or emb_id is None:
            return error_response("NO_FACE", "No face detected", 422)

        emb_selfie = safe_normalize(emb_selfie)
        emb_id = safe_normalize(emb_id)

        face_similarity = float(np.dot(emb_selfie, emb_id))

        # -----------------------------
        # EYE CHECK
        # -----------------------------
        selfie_eye = crop_eye_region(selfie)
        id_eye = crop_eye_region(id_img)

        eye_emb_selfie = get_embedding(selfie_eye, strict=False)
        eye_emb_id = get_embedding(id_eye, strict=False)

        eye_similarity = None

        if eye_emb_selfie is not None and eye_emb_id is not None:
            eye_emb_selfie = safe_normalize(eye_emb_selfie)
            eye_emb_id = safe_normalize(eye_emb_id)
            eye_similarity = float(np.dot(eye_emb_selfie, eye_emb_id))

        # -----------------------------
        # DECISION LOGIC
        # -----------------------------
        final_status = False
        decision = "FACE_MISMATCH"

        if underage_blocked:
            decision = "UNDERAGE"

        else:
            if face_similarity < FACE_HARD_FAIL:
                decision = "FACE_MISMATCH"

            else:
                if eye_similarity is not None:
                    if eye_similarity < EYE_HARD_FAIL:
                        decision = "EYE_MISMATCH"

                    elif face_similarity >= FACE_STRONG_PASS and eye_similarity >= EYE_STRONG_PASS:
                        final_status = True
                        decision = "VERIFIED_STRONG"

                    else:
                        decision = "BIOMETRIC_UNCERTAIN"

                else:
                    if face_similarity >= FACE_STRONG_PASS:
                        final_status = True
                        decision = "VERIFIED_STRONG"
                    else:
                        decision = "FACE_UNCERTAIN"

        # -----------------------------
        # BUILD RESPONSE
        # -----------------------------
        resp_data = {
            "status": final_status,
            "code": decision,
            "message": "Verification successful" if final_status else "Verification failed",
            "face_similarity": face_similarity,
            "eye_similarity": eye_similarity,
            "dob": dob.isoformat() if dob else None,
            "age": age,
            "age_checked": age_checked,
            "liveness_score": liveness_score,
            "redirect": "/" if final_status else None,
        }

        return jsonify(resp_data), 200 if final_status else 200

    except Exception:
        logger.exception("Error in /verify")
        return error_response("SERVER_ERROR", "Internal server error", 500)


# -------------------------------------------------
# GLOBAL ERROR HANDLERS
# -------------------------------------------------
@app.errorhandler(404)
def not_found(e):
    return error_response("NOT_FOUND", "Endpoint not found", 404)


@app.errorhandler(405)
def method_not_allowed(e):
    return error_response("METHOD_NOT_ALLOWED", "Method not allowed", 405)


@app.errorhandler(500)
def internal_error(e):
    logger.exception("Unhandled 500 error")
    return error_response("SERVER_ERROR", "Internal server error", 500)


# -------------------------------------------------
# ENTRY POINT
# -------------------------------------------------
if __name__ == "__main__":
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "5000"))
    debug = bool(int(os.getenv("DEBUG", "0")))

    print(f"Secure Verify running on http://{host}:{port}")
    app.run(host=host, port=port, debug=debug, threaded=True)
