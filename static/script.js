// =============================
// ELEMENTS
// =============================
const video = document.getElementById("video");
const selfieCanvas = document.getElementById("selfieCanvas");
const captureBtn = document.getElementById("captureBtn");
const verifyBtn = document.getElementById("verifyBtn");
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
// CAMERA START (FIXED)
// =============================
async function startCamera() {
    try {
        streamRef = await navigator.mediaDevices.getUserMedia({ video: true });

        video.srcObject = streamRef;

        await new Promise(resolve => {
            video.onloadedmetadata = () => resolve();
        });

        await video.play();

        resultText.textContent = "Camera ready";

        detectFace(); // start AFTER video ready

    } catch (err) {
        console.log("Camera error:", err);
        resultText.textContent = "Camera access blocked";
    }
}

startCamera();

// =============================
function detectFace() {

    const loop = () => {

        if (!video.videoWidth) {
            requestAnimationFrame(loop);
            return;
        }

        // SIMPLE STABLE RULE (no crash, no NO_FACE bug)
        const w = video.videoWidth;
        const h = video.videoHeight;

        // assume face present if camera active
        const active = w > 0 && h > 0;

        if (active) {
            faceOval.style.borderColor = "#00ff00";
            faceOval.style.boxShadow = "0 0 25px #00ff00";
        } else {
            faceOval.style.borderColor = "rgba(0,180,255,0.8)";
            faceOval.style.boxShadow = "0 0 25px rgba(0,180,255,0.4)";
        }

        requestAnimationFrame(loop);
    };

    loop();
}

// =============================
// SELFIE CAPTURE (FIXED)
// =============================
captureBtn.onclick = () => {

    if (!video.videoWidth) {
        resultText.textContent = "Camera still loading...";
        return;
    }

    const ctx = selfieCanvas.getContext("2d");

    selfieCanvas.width = video.videoWidth;
    selfieCanvas.height = video.videoHeight;

    ctx.drawImage(video, 0, 0);

    selfieBase64 = selfieCanvas.toDataURL("image/jpeg", 0.9);

    // STOP CAMERA (SAFE)
    if (streamRef) {
        streamRef.getTracks().forEach(t => t.stop());
    }

    video.style.display = "none";
    selfieCanvas.style.display = "block";

    captureBtn.disabled = true;
    captureBtn.innerText = "Captured";

    faceOval.style.display = "none";

    resultText.textContent = "Selfie locked";
};

// =============================
// ID UPLOAD
// =============================
idInput.onchange = function (e) {
    const file = e.target.files[0];

    if (!file) return;

    if (file.size > 5 * 1024 * 1024) {
        resultText.textContent = "File too large";
        return;
    }

    const reader = new FileReader();

    reader.onload = function () {
        idBase64 = reader.result;

        idPreview.src = reader.result;
        idPreview.style.display = "block";

        idFileName.textContent = file.name;

        resultText.textContent = "ID loaded";
    };

    reader.readAsDataURL(file);
};

// =============================
// VERIFY
// =============================
verifyBtn.onclick = async () => {

    if (verifying) return;

    if (!selfieBase64 || !idBase64) {
        resultText.textContent = "Selfie + ID required";
        return;
    }

    verifying = true;
    verifyBtn.disabled = true;

    resultText.textContent = "Verifying...";

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
            resultText.textContent = "Verified";

            setTimeout(() => {
                window.location.href = data.redirect || "https://chemist2door.co.uk/";
            }, 1500);

        } else {
            resultText.textContent = data.message || "Failed";
        }

    } catch (err) {
        resultText.textContent = "Server error";
    }

    verifying = false;
    verifyBtn.disabled = false;
};
