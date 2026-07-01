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

# COMMERCIAL-STYLE STRICT THRESHOLDS
# 0.0 = totally different, 1.0 = identical
FACE_HARD_FAIL = 0.60      # below this = definite mismatch
FACE_STRONG_PASS = 0.80    # above this = strong verified

EYE_HARD_FAIL = 0.55       # eye-region similarity strict
EYE_STRONG_PASS = 0.78


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
        return None


def extract_embedding(emb):
    if isinstance(emb, list):
        emb = emb[0]
    return np.array(emb["embedding"], dtype=np.float32)


def extract_dob_from_id(id_img):
    try:
        gray = cv2.cvtColor(id_img, cv2.COLOR_BGR2GRAY)
        text = pytesseract.image_to_string(gray)
        text = text.replace(" ", "")

        m = re.findall(r"\d{4}-\d{2}-\d{2}", text)
        if m:
            try:
                return datetime.strptime(m[0], "%Y-%m-%d").date()
            except:
                pass

        m = re.findall(r"\d{2}/\d{2}/\d{4}", text)
        if m:
            try:
                return datetime.strptime(m[0], "%d/%m/%Y").date()
            except:
                pass

        m = re.findall(r"\d{2}\.\d{2}\.\d{4}", text)
        if m:
            try:
                return datetime.strptime(m[0], "%d.%m.%Y").date()
            except:
                pass

        return None
    except:
        return None


def calculate_age(dob):
    today = date.today()
    return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))


def crop_eye_region(img):
    """
    Simple eye-region crop (top middle of face area).
    Not true biometric, but adds extra check.
    """
    try:
        h, w, _ = img.shape
        # Rough region: upper 40% of image, center 60% width
        y1 = int(h * 0.15)
        y2 = int(h * 0.45)
        x1 = int(w * 0.20)
        x2 = int(w * 0.80)
        eye = img[y1:y2, x1:x2]
        if eye.size == 0:
            return img
        return cv2.resize(eye, (300, 300))
    except:
        return img


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

        # AGE CHECK FROM ID
        dob = extract_dob_from_id(id_img)
        age = None
        age_checked = False
        underage_blocked = False

        if dob is not None:
            age = calculate_age(dob)
            age_checked = True
            if age < 18:
                underage_blocked = True

        # MAIN FACE EMBEDDINGS (FULL FACE)
        emb_selfie = DeepFace.represent(
            img_path=selfie,
            model_name="Facenet512",
            enforce_detection=True,
            detector_backend="opencv",
            align=True
        )

        emb_id = DeepFace.represent(
            img_path=id_img,
            model_name="Facenet512",
            enforce_detection=True,
            detector_backend="opencv",
            align=True
        )

        if not emb_selfie or not emb_id:
            return jsonify({
                "status": False,
                "code": "NO_FACE",
                "message": "No face detected"
            }), 422

        emb_selfie = extract_embedding(emb_selfie)
        emb_id = extract_embedding(emb_id)

        emb_selfie = emb_selfie / norm(emb_selfie)
        emb_id = emb_id / norm(emb_id)

        face_similarity = float(np.dot(emb_selfie, emb_id))

        # EXTRA: EYE REGION CHECK
        selfie_eye = crop_eye_region(selfie)
        id_eye = crop_eye_region(id_img)

        eye_emb_selfie = DeepFace.represent(
            img_path=selfie_eye,
            model_name="Facenet512",
            enforce_detection=False,
            detector_backend="opencv",
            align=True
        )

        eye_emb_id = DeepFace.represent(
            img_path=id_eye,
            model_name="Facenet512",
            enforce_detection=False,
            detector_backend="opencv",
            align=True
        )

        if eye_emb_selfie and eye_emb_id:
            eye_emb_selfie = extract_embedding(eye_emb_selfie)
            eye_emb_id = extract_embedding(eye_emb_id)

            eye_emb_selfie = eye_emb_selfie / norm(eye_emb_selfie)
            eye_emb_id = eye_emb_id / norm(eye_emb_id)

            eye_similarity = float(np.dot(eye_emb_selfie, eye_emb_id))
        else:
            eye_similarity = None

        # DECISION LOGIC – COMMERCIAL STYLE
        final_status = False
        decision = "FACE_MISMATCH"

        # First: age block
        if underage_blocked:
            final_status = False
            decision = "UNDERAGE"

        else:
            # Face must be strongly similar
            if face_similarity < FACE_HARD_FAIL:
                final_status = False
                decision = "FACE_MISMATCH"
            else:
                # If we have eye similarity, use it as extra gate
                if eye_similarity is not None:
                    if eye_similarity < EYE_HARD_FAIL:
                        final_status = False
                        decision = "EYE_MISMATCH"
                    elif face_similarity >= FACE_STRONG_PASS and eye_similarity >= EYE_STRONG_PASS:
                        final_status = True
                        decision = "VERIFIED_STRONG"
                    else:
                        final_status = False
                        decision = "BIOMETRIC_UNCERTAIN"
                else:
                    # No eye data, rely only on strong face similarity
                    if face_similarity >= FACE_STRONG_PASS:
                        final_status = True
                        decision = "VERIFIED_STRONG"
                    else:
                        final_status = False
                        decision = "FACE_UNCERTAIN"

        return jsonify({
            "status": final_status,
            "code": decision,
            "message": "Verification successful" if final_status else "Verification failed",
            "face_similarity": face_similarity,
            "eye_similarity": eye_similarity,
            "dob": dob.isoformat() if dob else None,
            "age": age,
            "age_checked": age_checked
        })

    except Exception as e:
        logging.exception("Error in /verify")
        return jsonify({
            "status": False,
            "code": "SERVER_ERROR",
            "message": "Internal server error"
        }), 500


if __name__ == "__main__":
    print("Secure Verify running on http://127.0.0.1:5000")
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)
