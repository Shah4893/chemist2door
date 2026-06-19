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

// Camera
navigator.mediaDevices.getUserMedia({ video: true })
    .then(stream => video.srcObject = stream)
    .catch(err => console.error("Camera error:", err));

// Capture selfie
captureBtn.onclick = () => {
    const ctx = selfieCanvas.getContext("2d");
    selfieCanvas.width = video.videoWidth;
    selfieCanvas.height = video.videoHeight;
    ctx.drawImage(video, 0, 0);
    selfieBase64 = selfieCanvas.toDataURL("image/jpeg");
    resultText.style.color = "#e0f7ff";
    resultText.textContent = "Selfie captured. Ready to verify.";
};

// ID upload
idInput.onchange = () => {
    const file = idInput.files[0];
    if (!file) return;
    idFileName.textContent = file.name;

    const reader = new FileReader();
    reader.onload = () => {
        idBase64 = reader.result;
        idPreview.src = reader.result;
        resultText.style.color = "#e0f7ff";
        resultText.textContent = "ID loaded. Capture selfie and start verification.";
    };
    reader.readAsDataURL(file);
};

// Verify
verifyBtn.onclick = async () => {
    if (!selfieBase64) {
        resultText.style.color = "#ff4444";
        resultText.textContent = "Please capture a selfie.";
        return;
    }
    if (!idBase64) {
        resultText.style.color = "#ff4444";
        resultText.textContent = "Please upload an ID image.";
        return;
    }

    resultText.style.color = "#e0f7ff";
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
            resultText.style.color = "#00ff99";
            resultText.textContent = "✔ Verification Successful";

            setTimeout(() => {
                window.location.href = "/";   // change to /home or /order if needed
            }, 2000);
        } else {
            resultText.style.color = "#ff4444";
            resultText.textContent = "✘ Verification Failed";

            setTimeout(() => {
                window.location.href = "/";   // reload same page to retry
            }, 2500);
        }
    } catch (e) {
        console.error(e);
        resultText.style.color = "#ff4444";
        resultText.textContent = "Request error.";
    }
};
