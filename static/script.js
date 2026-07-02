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

/* ---------------- CAMERA ---------------- */
async function startCamera() {
    try {
        const stream = await navigator.mediaDevices.getUserMedia({
            video: { facingMode: "user" }
        });

        video.srcObject = stream;
        await video.play();

    } catch (err) {
        console.error(err);
        resultText.textContent = "Camera error";
    }
}

startCamera();

/* ---------------- SELFIE ---------------- */
captureBtn.onclick = () => {
    const ctx = selfieCanvas.getContext("2d");

    selfieCanvas.width = video.videoWidth;
    selfieCanvas.height = video.videoHeight;

    ctx.drawImage(video, 0, 0);

    const raw = selfieCanvas.toDataURL("image/jpeg", 0.7);

    if (!raw || raw.length < 10000) {
        resultText.textContent = "Selfie capture failed";
        return;
    }

    selfieBase64 = raw;

    // freeze view on captured selfie
    video.style.display = "none";
    selfieCanvas.style.display = "block";

    resultText.textContent = "Selfie captured";
};

/* ---------------- ID UPLOAD ---------------- */
idInput.onchange = () => {
    const file = idInput.files[0];
    if (!file) return;

    const reader = new FileReader();

    reader.onload = () => {
        idBase64 = reader.result;
        idPreview.src = reader.result;
        idFileName.textContent = file.name;
        resultText.textContent = "ID loaded";
    };

    reader.readAsDataURL(file);
};

/* ---------------- VERIFY ---------------- */
verifyBtn.onclick = async () => {

    if (verifyLocked) return;
    verifyLocked = true;

    setTimeout(() => {
        verifyLocked = false;
    }, 15000);

    if (!selfieBase64 || !idBase64) {
        resultText.textContent = "Missing images";
        verifyLocked = false;
        return;
    }

    resultText.textContent = "Processing...";

    try {
        const controller = new AbortController();
        const timeout = setTimeout(() => controller.abort(), 15000);

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

        const data = await res.json();

        if (!res.ok) {
            resultText.textContent = data.message || "Failed";
            return;
        }

        if (data.status) {
            resultText.textContent = "✔ Verified – redirecting...";
            // redirect to main Chemist2Door homepage
            setTimeout(() => {
                window.location.href = "https://chemist2door.co.uk/";
            }, 2000);
        } else {
            resultText.textContent = "✘ " + (data.code || "Verification failed");
        }

    } catch (err) {
        console.error(err);
        resultText.textContent =
            err.name === "AbortError"
                ? "Request timeout"
                : "Request failed";
    } finally {
        verifyLocked = false;
    }
};
