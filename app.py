from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import cv2
import numpy as np
import base64
import logging
from deepface import DeepFace
from numpy.linalg import norm
from datetime import datetime, date
import pytesseract
import re

app = Flask(__name__)
CORS(app)

logging.basicConfig(level=logging.INFO)

# -----------------------------
# THRESHOLDS
# -----------------------------
FACE_HARD_FAIL = 0.60
FACE_STRONG_PASS = 0.82
EYE_HARD_FAIL = 0.55
EYE_STRONG_PASS = 0.80


# -----------------------------
# UTILITIES
# -----------------------------
def safe_normalize(vec):
    try:
        n = norm(vec)
        return vec / n if n != 0 else vec
    except:
        return vec


def decode_image(data):
    try:
        if not data:
            return None

        if "," in data:
            data = data.split(",", 1)[1]

        img_bytes = base64.b64decode(data)
        np_arr = np.frombuffer(img_bytes, np.uint8)
        img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

        if img is None:
            return None

        return cv2.resize(img, (500, 500))

    except:
        logging.exception("decode_image failed")
        return None


def extract_embedding(result):
    try:
        if isinstance(result, list) and len(result) > 0:
            emb = result[0].get("embedding")
            if emb is None:
                return None
            return np.array(emb, dtype=np.float32)
        return None
    except:
        return None


def extract_dob_from_id(id_img):
    try:
        gray = cv2.cvtColor(id_img, cv2.COLOR_BGR2GRAY)
        text = pytesseract.image_to_string(gray, config="--psm 6")
        text = text.replace(" ", "")

        patterns = [
            r"\d{4}-\d{2}-\d{2}",
            r"\d{2}/\d{2}/\d{4}",
            r"\d{2}\.\d{2}\.\d{4}"
        ]

        for p in patterns:
            m = re.findall(p, text)
            if m:
                try:
                    if "-" in m[0]:
                        return datetime.strptime(m[0], "%Y-%m-%d").date()
                    elif "/" in m[0]:
                        return datetime.strptime(m[0], "%d/%m/%Y").date()
                    elif "." in m[0]:
                        return datetime.strptime(m[0], "%d.%m.%Y").date()
                except:
                    continue

        return None

    except:
        logging.exception("DOB extraction failed")
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
    except:
        return img


def get_embedding(img, strict=True):
    try:
        result = DeepFace.represent(
            img_path=img,
            model_name="Facenet512",
            enforce_detection=strict,
            detector_backend="retinaface",   # FIXED
            align=True
        )
        return extract_embedding(result)
    except Exception as e:
        logging.error(f"DeepFace failed: {e}")
        return None


# -----------------------------
# ROUTES
# -----------------------------
@app.route("/")
def home():
    return render_template("index.html")


@app.route("/verify", methods=["POST"])
def verify():
    try:
        data = request.get_json() or {}

        selfie = decode_image(data.get("selfie"))
        id_img = decode_image(data.get("id_image"))

        if selfie is None or id_img is None:
            return jsonify({
                "status": False,
                "code": "INVALID_IMAGE",
                "message": "Invalid or missing images"
            }), 400

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
            if age < 18:
                underage_blocked = True

        # -----------------------------
        # FACE EMBEDDINGS
        # -----------------------------
        emb_selfie = get_embedding(selfie)
        emb_id = get_embedding(id_img, strict=False)

        if emb_selfie is None or emb_id is None:
            return jsonify({
                "status": False,
                "code": "NO_FACE",
                "message": "No face detected"
            }), 422

        emb_selfie = safe_normalize(emb_selfie)
        emb_id = safe_normalize(emb_id)

        face_similarity = float(np.dot(emb_selfie, emb_id))

        # -----------------------------
        # EYE CHECK
        # -----------------------------
        selfie_eye = crop_eye_region(selfie)
        id_eye = crop_eye_region(id_img)

        eye_emb_selfie = get_embedding(selfie_eye)
        eye_emb_id = get_embedding(id_eye)

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

        return jsonify({
            "status": final_status,
            "code": decision,
            "message": "Verification successful" if final_status else "Verification failed",
            "face_similarity": face_similarity,
            "eye_similarity": eye_similarity,
            "dob": dob.isoformat() if dob else None,
            "age": age,
            "age_checked": age_checked,
            "redirect": "/" if final_status else None
        })

    except Exception:
        logging.exception("Error in /verify")
        return jsonify({
            "status": False,
            "code": "SERVER_ERROR",
            "message": "Internal server error"
        }), 500


if __name__ == "__main__":
    print("Secure Verify running on http://127.0.0.1:5000")
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)
