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

HARD_FAIL_THRESHOLD = 0.30
SOFT_PASS_THRESHOLD = 0.45


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

        dob = extract_dob_from_id(id_img)
        age = None
        age_checked = False
        underage_blocked = False

        if dob is not None:
            age = calculate_age(dob)
            age_checked = True
            if age < 18:
                underage_blocked = True

        emb1 = DeepFace.represent(
            img_path=selfie,
            model_name="Facenet512",
            enforce_detection=False,
            detector_backend="opencv",
            align=True
        )

        emb2 = DeepFace.represent(
            img_path=id_img,
            model_name="Facenet512",
            enforce_detection=False,
            detector_backend="opencv",
            align=True
        )

        if not emb1 or not emb2:
            return jsonify({
                "status": False,
                "code": "NO_FACE",
                "message": "No face detected"
            }), 422

        emb1 = extract_embedding(emb1)
        emb2 = extract_embedding(emb2)

        emb1 = emb1 / norm(emb1)
        emb2 = emb2 / norm(emb2)

        similarity = float(np.dot(emb1, emb2))

        if similarity < HARD_FAIL_THRESHOLD:
            final_status = False
            decision = "FACE_MISMATCH"
        elif similarity >= SOFT_PASS_THRESHOLD:
            final_status = True
            decision = "VERIFIED"
        else:
            final_status = True
            decision = "VERIFIED_BORDERLINE"

        if underage_blocked:
            final_status = False
            decision = "UNDERAGE"

        return jsonify({
            "status": final_status,
            "code": decision,
            "message": "Verification successful" if final_status else "Verification failed",
            "similarity": similarity,
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
