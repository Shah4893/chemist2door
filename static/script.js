const video = document.getElementById("video");
const captureBtn = document.getElementById("captureBtn");
const selfieCanvas = document.getElementById("selfieCanvas");
const idInput = document.getElementById("idInput");
const idPreview = document.getElementById("idPreview");
const idFileName = document.getElementById("idFileName");
const verifyBtn = document.getElementById("verifyBtn");
const resultText = document.getElementById("resultText");

let selfieBase64 = "";
let idBase64 = "";
let verifyLocked = false;

/* ---------------------------
   SECURE CAMERA START
---------------------------- */
async function startCamera() {
    try {
        const stream = await navigator.mediaDevices.getUserMedia({
            video: {
                facingMode: "user",
                width: { ideal: 1280 },
                height: { ideal: 720 }
            }
        });

        if (!stream || !stream.getTracks().length) {
            throw new Error("Fake or invalid camera stream");
        }

        video.srcObject = stream;
        await video.play();

        video.setAttribute("playsinline", true);

    } catch (err) {
        console.error("Camera error:", err);
        resultText.style.color = "#ff4444";
        resultText.textContent = "Camera blocked or unavailable.";
    }
}

startCamera();

/* ---------------------------
   SECURE SELFIE CAPTURE
---------------------------- */
captureBtn.onclick = () => {
    const ctx = selfieCanvas.getContext("2d");

    selfieCanvas.width = video.videoWidth;
    selfieCanvas.height = video.videoHeight;

    ctx.drawImage(video, 0, 0);

    const raw = selfieCanvas.toDataURL("image/jpeg", 1.0);

    // Anti‑spoofing: ensure image is not blank
    if (raw.length < 50000) {
        resultText.style.color = "#ff4444";
        resultText.textContent = "Selfie invalid. Try again.";
        return;
    }

    selfieBase64 = raw;

    resultText.style.color = "#00eaff";
    resultText.textContent = "Selfie captured.";
};

/* ---------------------------
   SECURE ID UPLOAD
---------------------------- */
idInput.onchange = () => {
    const file = idInput.files[0];
    if (!file) return;

    if (file.size < 50000) {
        resultText.style.color = "#ff4444";
        resultText.textContent = "ID image too small or corrupted.";
        return;
    }

    idFileName.textContent = file.name;

    const reader = new FileReader();
    reader.onload = () => {
        idBase64 = reader.result;
        idPreview.src = reader.result;

        resultText.style.color = "#00eaff";
        resultText.textContent = "ID loaded.";
    };

    reader.readAsDataURL(file);
};

/* ---------------------------
   SECURE VERIFY
---------------------------- */
verifyBtn.onclick = async () => {

    if (verifyLocked) return;
    verifyLocked = true;

    if (!selfieBase64) {
        resultText.style.color = "#ff4444";
        resultText.textContent = "Please capture a selfie.";
        verifyLocked = false;
        return;
    }

    if (!idBase64) {
        resultText.style.color = "#ff4444";
        resultText.textContent = "Please upload an ID image.";
        verifyLocked = false;
        return;
    }

    resultText.style.color = "#00eaff";
    resultText.textContent = "Processing...";

    const payload = {
        selfie: selfieBase64,
        id_image: idBase64
    };

    try {
        const res = await fetch("/verify", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });

        let data = null;

        try {
            data = await res.json();
        } catch {
            throw new Error("Invalid JSON response from server");
        }

        if (!res.ok) {
            resultText.style.color = "#ff4444";
            resultText.textContent = data.message || "Verification failed.";
            verifyLocked = false;
            return;
        }

        // Anti‑spoofing: backend must return similarity + code
        if (!("similarity" in data) || !("code" in data)) {
            resultText.style.color = "#ff4444";
            resultText.textContent = "Invalid server response.";
            verifyLocked = false;
            return;
        }

        if (data.status === true) {
            resultText.style.color = "#00ff99";
            resultText.textContent = "✔ Verified";

            setTimeout(() => {
                window.location.href = "/";
            }, 2000);

        } else {
            resultText.style.color = "#ff4444";
            resultText.textContent = "✘ " + (data.message || "Verification failed");

            setTimeout(() => {
                window.location.href = "/";
            }, 2500);
        }

    } catch (e) {
        console.error("VERIFY ERROR:", e);
        resultText.style.color = "#ff4444";
        resultText.textContent = "Request error.";
    }

    verifyLocked = false;
};
