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

/* CAMERA FIX */
async function startCamera() {
    try {
        const stream = await navigator.mediaDevices.getUserMedia({
            video: {
                facingMode: "user",
                width: { min: 640, ideal: 1280, max: 1920 },
                height: { min: 480, ideal: 720, max: 1080 }
            }
        });

        video.srcObject = stream;
        await video.play();
        video.setAttribute("playsinline", true);

    } catch (err) {
        resultText.style.color = "#ff4444";
        resultText.textContent = "Camera not accessible.";
    }
}

startCamera();

/* SELFIE CAPTURE */
captureBtn.onclick = () => {
    const ctx = selfieCanvas.getContext("2d");

    selfieCanvas.width = video.videoWidth;
    selfieCanvas.height = video.videoHeight;

    ctx.drawImage(video, 0, 0, video.videoWidth, video.videoHeight);

    selfieBase64 = selfieCanvas.toDataURL("image/jpeg", 1.0);

    resultText.textContent = "Selfie captured. Ready to verify.";
};

/* ID UPLOAD */
idInput.onchange = () => {
    const file = idInput.files[0];
    if (!file) return;

    idFileName.textContent = file.name;

    const reader = new FileReader();
    reader.onload = () => {
        idBase64 = reader.result;
        idPreview.src = reader.result;

        resultText.textContent = "ID loaded. Capture selfie and start verification.";
    };

    reader.readAsDataURL(file);
};

/* VERIFY */
verifyBtn.onclick = async () => {

    if (!selfieBase64) {
        resultText.textContent = "Please capture a selfie.";
        return;
    }

    if (!idBase64) {
        resultText.textContent = "Please upload an ID image.";
        return;
    }

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

        const data = await res.json();

        if (data.status === true) {
            resultText.textContent = "✔ Verification Successful";
            setTimeout(() => window.location.href = "/", 2000);
        } else {
            resultText.textContent = "✘ Verification Failed";
            setTimeout(() => window.location.href = "/", 2500);
        }

    } catch (e) {
        resultText.textContent = "Request error.";
    }
};
