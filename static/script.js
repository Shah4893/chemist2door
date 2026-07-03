// =============================
// ELEMENTS
// =============================
const video = document.getElementById("video");
const selfieCanvas = document.getElementById("selfieCanvas");
const captureBtn = document.getElementById("captureBtn");
const retakeBtn = document.getElementById("retakeBtn");
const verifyBtn = document.getElementById("verifyBtn");
const resultBox = document.getElementById("resultBox");
const resultText = document.getElementById("resultText");
const faceOval = document.getElementById("faceOval");
const idInput = document.getElementById("idInput");
const idPreview = document.getElementById("idPreview");
const idFileName = document.getElementById("idFileName");

// =============================
// STATE
// =============================
let selfieBase64 = null;
let idBase64 = null;
let verifying = false;
let streamRef = null;

// =============================
// HELPERS
// =============================
function showResult(message) {
    resultBox.classList.remove("hidden");
    resultText.textContent = message;
}

function updateVerifyButtonState() {
    const ready = !!selfieBase64 && !!idBase64;
    verifyBtn.disabled = !ready || verifying;
    verifyBtn.classList.toggle("disabled", !ready || verifying);
}

// =============================
// CAMERA START (MASTER)
// =============================
async function startCamera() {
    try {
        if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
            showResult("Camera not supported on this device");
            return;
        }

        streamRef = await navigator.mediaDevices.getUserMedia({
            video: {
                width: { ideal: 720 },
                height: { ideal: 720 },
                facingMode: "user"
            },
            audio: false
        });

        video.srcObject = streamRef;

        await new Promise(resolve => {
            video.onloadedmetadata = () => resolve();
        });

        await video.play();

        showResult("Camera ready");
        detectFace();

    } catch (err) {
        console.error("Camera error:", err);
        showResult("Camera access blocked. Please allow camera.");
    }
}

// Auto start
startCamera();

// =============================
// FACE DETECTION (VISUAL ONLY)
// =============================
function detectFace() {
    const loop = () => {
        if (video.readyState >= 2 && video.videoWidth > 0) {
            faceOval.style.borderColor = "#00ff00";
            faceOval.style.boxShadow = "0 0 25px #00ff00";
            resultText.textContent = "Face detected";
        }
        requestAnimationFrame(loop);
    };
    loop();
}

// =============================
// STOP CAMERA
// =============================
function stopCamera() {
    if (streamRef) {
        streamRef.getTracks().forEach(t => t.stop());
        streamRef = null;
    }
}

// =============================
// SELFIE CAPTURE (MASTER)
// =============================
captureBtn.onclick = () => {
    if (!video.videoWidth || !video.videoHeight) {
        showResult("Camera still loading...");
        return;
    }

    const ctx = selfieCanvas.getContext("2d");

    // Match video resolution
    selfieCanvas.width = video.videoWidth;
    selfieCanvas.height = video.videoHeight;

    ctx.drawImage(video, 0, 0, selfieCanvas.width, selfieCanvas.height);

    // High-quality JPEG but not huge
    selfieBase64 = selfieCanvas.toDataURL("image/jpeg", 0.9);

    // Stop camera and show frozen frame
    stopCamera();
    video.style.display = "none";
    selfieCanvas.style.display = "block";

    captureBtn.disabled = true;
    captureBtn.innerText = "Captured";
    retakeBtn.style.display = "inline-block";
    retakeBtn.disabled = false;

    faceOval.style.display = "none";

    showResult("Selfie locked");
    updateVerifyButtonState();
};

// =============================
// RETAKE SELFIE (MASTER)
// =============================
retakeBtn.onclick = () => {
    selfieBase64 = null;

    selfieCanvas.style.display = "none";
    video.style.display = "block";

    captureBtn.disabled = false;
    captureBtn.innerText = "Capture Selfie";
    retakeBtn.style.display = "none";

    faceOval.style.display = "block";

    startCamera();
    showResult("Retake selfie");
    updateVerifyButtonState();
};

// =============================
// ID UPLOAD (MASTER)
// =============================
idInput.onchange = function (e) {
    const file = e.target.files[0];
    if (!file) return;

    if (file.size > 10 * 1024 * 1024) {
        showResult("ID too large (max 10MB)");
        return;
    }

    const reader = new FileReader();

    reader.onload = function () {
        idBase64 = reader.result;

        idPreview.src = reader.result;
        idPreview.style.display = "block";

        idFileName.textContent = file.name;

        showResult("ID loaded");
        updateVerifyButtonState();
    };

    reader.onerror = function () {
        showResult("Failed to read ID file");
    };

    reader.readAsDataURL(file);
};

// =============================
// VERIFY (MASTER)
// =============================
verifyBtn.onclick = async () => {
    if (verifying) return;

    if (!selfieBase64 || !idBase64) {
        showResult("Selfie + ID required");
        return;
    }

    verifying = true;
    updateVerifyButtonState();
    showResult("Verifying...");

    try {
        const controller = new AbortController();
        const timeout = setTimeout(() => controller.abort(), 15000); // 15s timeout

        const res = await fetch("/verify", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                selfie: selfieBase64,
                id_image: idBase64
            }),
            signal: controller.signal
        });

        clearTimeout(timeout);

        let data = {};
        try {
            data = await res.json();
        } catch (e) {
            showResult("Invalid server response");
            verifying = false;
            updateVerifyButtonState();
            return;
        }

        if (data.status === true) {
            showResult("Verified");
            setTimeout(() => {
                window.location.href = data.redirect || "https://chemist2door.co.uk/";
            }, 1500);
        } else {
            const msg = data.message || data.code || "Verification failed";
            showResult(msg);
        }

    } catch (err) {
        if (err.name === "AbortError") {
            showResult("Verification timeout. Please try again.");
        } else {
            console.error("Verify error:", err);
            showResult("Server error. Please try again.");
        }
    }

    verifying = false;
    updateVerifyButtonState();
};
