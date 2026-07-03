// -----------------------------
// ELEMENTS
// -----------------------------
const video = document.getElementById("video");
const selfieCanvas = document.getElementById("selfieCanvas");
const captureBtn = document.getElementById("captureBtn");
const verifyBtn = document.getElementById("verifyBtn");
const resultText = document.getElementById("resultText");
const faceOval = document.getElementById("faceOval");
const idInput = document.getElementById("idInput");

let selfieBase64 = null;
let idBase64 = null;
let verifying = false;

// -----------------------------
// CAMERA START (user permission)
// -----------------------------
async function startCamera() {
    try {
        const stream = await navigator.mediaDevices.getUserMedia({ video: true });
        video.srcObject = stream;
        await video.play();
    } catch (err) {
        console.log("Camera error:", err);
        resultText.textContent = "Camera access blocked, please allow camera.";
    }
}

startCamera();

// -----------------------------
// FACE OVAL DETECTION
// -----------------------------
async function detectFace() {
    if (!("FaceDetector" in window)) {
        // agar browser support nahi karta to simple blue oval
        faceOval.style.borderColor = "rgba(0,180,255,0.8)";
        faceOval.style.boxShadow = "0 0 25px rgba(0,180,255,0.4)";
        return;
    }

    const faceDetector = new FaceDetector({ fastMode: true });

    const loop = async () => {
        try {
            const faces = await faceDetector.detect(video);

            if (faces.length > 0) {
                // FACE FOUND → GREEN OVAL
                faceOval.style.borderColor = "#00ff00";
                faceOval.style.boxShadow = "0 0 25px #00ff00";
            } else {
                // NO FACE → BLUE OVAL
                faceOval.style.borderColor = "rgba(0,180,255,0.8)";
                faceOval.style.boxShadow = "0 0 25px rgba(0,180,255,0.4)";
            }
        } catch (e) {
            console.log("FaceDetector error:", e);
        }

        requestAnimationFrame(loop);
    };

    loop();
}

detectFace();

// -----------------------------
// SELFIE HOLD FUNCTION
// -----------------------------
captureBtn.onclick = () => {
    if (!video.srcObject) {
        resultText.textContent = "Camera not ready.";
        return;
    }

    const ctx = selfieCanvas.getContext("2d");
    selfieCanvas.width = video.videoWidth;
    selfieCanvas.height = video.videoHeight;

    // current frame draw
    ctx.drawImage(video, 0, 0);

    // Base64 convert
    selfieBase64 = selfieCanvas.toDataURL("image/jpeg", 0.9);

    // CAMERA LOCK
    const stream = video.srcObject;
    if (stream) {
        const tracks = stream.getTracks();
        tracks.forEach(track => track.stop());
    }

    video.style.display = "none";            // live video hide
    selfieCanvas.style.display = "block";    // frozen selfie show

    captureBtn.disabled = true;
    captureBtn.innerText = "Selfie Captured";
    faceOval.style.display = "none";

    resultText.textContent = "Selfie captured and locked.";
};

// -----------------------------
// ID UPLOAD
// -----------------------------
// ID UPLOAD (MASTER FIXED VERSION)
const idPreview = document.getElementById("idPreview");
const idFileName = document.getElementById("idFileName");

idInput.onchange = function (e) {
    const file = e.target.files[0];

    if (!file) {
        resultText.textContent = "Please select ID image.";
        idPreview.style.display = "none";
        idFileName.textContent = "No file selected";
        return;
    }

    // Size limit (5MB)
    if (file.size > 5 * 1024 * 1024) {
        resultText.textContent = "ID image too large (max 5MB).";
        idInput.value = "";
        idPreview.style.display = "none";
        idFileName.textContent = "No file selected";
        return;
    }

    const reader = new FileReader();

    reader.onload = function () {
        idBase64 = reader.result;

        // ID preview show
        idPreview.src = reader.result;
        idPreview.style.display = "block";

        // File name show
        idFileName.textContent = file.name;

        resultText.textContent = "ID loaded.";
    };

    reader.onerror = function () {
        resultText.textContent = "Error reading ID file.";
        idPreview.style.display = "none";
        idFileName.textContent = "No file selected";
    };

    reader.readAsDataURL(file);
};

// -----------------------------
// VERIFY BUTTON
// -----------------------------
verifyBtn.onclick = async () => {
    if (verifying) return; // double click block

    if (!selfieBase64 || !idBase64) {
        resultText.textContent = "Please capture selfie and upload ID.";
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

        let data;
        try {
            data = await res.json();
        } catch (e) {
            resultText.textContent = "Server response error.";
            verifying = false;
            verifyBtn.disabled = false;
            return;
        }

        if (data.status) {
            resultText.textContent = "✔ Verified – redirecting...";
            setTimeout(() => {
                // backend agar redirect field bheje to use, warna homepage
                if (data.redirect) {
                    window.location.href = data.redirect;
                } else {
                    window.location.href = "https://chemist2door.co.uk/";
                }
            }, 1500);
        } else {
            // backend ka code show karein taake debugging easy ho
            const msg = data.message || "Verification failed";
            const code = data.code ? ` (${data.code})` : "";
            resultText.textContent = `✘ ${msg}${code}`;
            verifyBtn.disabled = false;
            verifying = false;
        }
    } catch (err) {
        console.log("Verify error:", err);
        resultText.textContent = "Network / server error.";
        verifyBtn.disabled = false;
        verifying = false;
    }
};
