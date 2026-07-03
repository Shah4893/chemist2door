const video = document.getElementById("video");
const selfieCanvas = document.getElementById("selfieCanvas");
const captureBtn = document.getElementById("captureBtn");
const verifyBtn = document.getElementById("verifyBtn");
const resultText = document.getElementById("resultText");
const faceOval = document.getElementById("faceOval");
const idInput = document.getElementById("idInput");
const idPreview = document.getElementById("idPreview");
const idFileName = document.getElementById("idFileName");

let selfieBase64 = null;
let idBase64 = null;
let verifying = false;
let streamRef = null;

function showResult(msg) {
    resultText.textContent = msg;
}

function updateVerifyButton() {
    const ready = selfieBase64 && idBase64;
    verifyBtn.disabled = !ready || verifying;
}

async function startCamera() {
    try {
        streamRef = await navigator.mediaDevices.getUserMedia({
            video: { facingMode: "user" },
            audio: false
        });

        video.srcObject = streamRef;
        await video.play();

        showResult("Camera ready");
        detectFace();

    } catch (err) {
        showResult("Camera blocked");
    }
}

startCamera();

function detectFace() {
    const loop = () => {
        if (video.readyState >= 2) {
            faceOval.style.borderColor = "#00ff00";
            faceOval.style.boxShadow = "0 0 25px #00ff00";
            resultText.textContent = "Face detected";
        }
        requestAnimationFrame(loop);
    };
    loop();
}

function stopCamera() {
    if (streamRef) {
        streamRef.getTracks().forEach(t => t.stop());
        streamRef = null;
    }
}

captureBtn.onclick = () => {
    if (!video.videoWidth) {
        showResult("Camera loading...");
        return;
    }

    const ctx = selfieCanvas.getContext("2d");
    selfieCanvas.width = video.videoWidth;
    selfieCanvas.height = video.videoHeight;

    ctx.drawImage(video, 0, 0);

    selfieBase64 = selfieCanvas.toDataURL("image/jpeg", 0.9);

    stopCamera();
    video.style.display = "none";
    selfieCanvas.style.display = "block";

    captureBtn.disabled = true;
    captureBtn.textContent = "Captured";

    faceOval.style.display = "none";

    showResult("Selfie locked");
    updateVerifyButton();
};

idInput.onchange = e => {
    const file = e.target.files[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = () => {
        idBase64 = reader.result;
        idPreview.src = reader.result;
        idPreview.style.display = "block";
        idFileName.textContent = file.name;
        showResult("ID loaded");
        updateVerifyButton();
    };
    reader.readAsDataURL(file);
};

verifyBtn.onclick = async () => {
    if (verifying) return;

    verifying = true;
    updateVerifyButton();
    showResult("Verifying...");

    try {
        const res = await fetch("/verify", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                selfie: selfieBase64,
                id_image: idBase64
            })
        });

        const data = await res.json();

        if (data.status) {
            showResult("Verified");
            setTimeout(() => {
                window.location.href = data.redirect || "/";
            }, 1500);
        } else {
            showResult(data.message || "Verification failed");
        }

    } catch (err) {
        showResult("Server error");
    }

    verifying = false;
    updateVerifyButton();
};
