const video = document.getElementById("video");
const canvas = document.getElementById("selfieCanvas");
const captureBtn = document.getElementById("captureBtn");
const verifyBtn = document.getElementById("verifyBtn");
const idInput = document.getElementById("idInput");
const idPreview = document.getElementById("idPreview");
const idFileName = document.getElementById("idFileName");
const resultText = document.getElementById("resultText");
const faceOval = document.getElementById("faceOval");

let selfieBase64 = null;
let idBase64 = null;
let stream = null;
let verifying = false;

function showResult(message) {
    if (resultText) {
        resultText.textContent = message;
    }
}

function updateButton() {
    if (!verifyBtn) return;
    verifyBtn.disabled = !(selfieBase64 && idBase64 && !verifying);
}

async function startCamera() {
    try {
        if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
            showResult("Camera not supported on this device");
            return;
        }

        stream = await navigator.mediaDevices.getUserMedia({
            video: { facingMode: "user" },
            audio: false
        });

        video.srcObject = stream;
        await video.play();

        showResult("Camera ready");

        if (faceOval) {
            faceOval.style.borderColor = "#00aa00";
        }
    } catch (error) {
        console.error("Camera error:", error);
        showResult("Camera permission denied");
    }
}

function stopCamera() {
    if (stream) {
        stream.getTracks().forEach((track) => track.stop());
        stream = null;
    }
}

if (captureBtn) {
    captureBtn.onclick = function () {
        if (!video || !video.videoWidth) {
            showResult("Camera loading");
            return;
        }

        const width = video.videoWidth;
        const height = video.videoHeight;

        canvas.width = width;
        canvas.height = height;

        const ctx = canvas.getContext("2d");
        ctx.drawImage(video, 0, 0, width, height);

        selfieBase64 = canvas.toDataURL("image/jpeg", 0.85);

        stopCamera();

        video.style.display = "none";
        canvas.style.display = "block";

        if (faceOval) {
            faceOval.style.display = "none";
        }

        captureBtn.disabled = true;
        captureBtn.textContent = "Captured";

        showResult("Selfie captured");
        updateButton();
    };
}

if (idInput) {
    idInput.onchange = function () {
        const file = this.files && this.files[0];

        if (!file) return;

        if (!file.type.startsWith("image/")) {
            showResult("Only image files allowed");
            this.value = "";
            return;
        }

        const maxSize = 5 * 1024 * 1024;
        if (file.size > maxSize) {
            showResult("Image too large. Max 5MB allowed");
            this.value = "";
            return;
        }

        const reader = new FileReader();

        reader.onload = function (e) {
            idBase64 = e.target.result;

            if (idPreview) {
                idPreview.src = idBase64;
                idPreview.style.display = "block";
            }

            if (idFileName) {
                idFileName.textContent = file.name;
            }

            showResult("ID loaded");
            updateButton();
        };

        reader.onerror = function () {
            showResult("Could not read ID image");
        };

        reader.readAsDataURL(file);
    };
}

if (verifyBtn) {
    verifyBtn.onclick = async function () {
        if (verifying) return;

        if (!selfieBase64 || !idBase64) {
            showResult("Please capture selfie and upload ID first");
            return;
        }

        verifying = true;
        updateButton();
        showResult("Verification running...");

        try {
            const response = await fetch("https://verify.chemist2door.co.uk/verify", {

                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    selfie: selfieBase64,
                    id_image: idBase64
                })
            });

            const rawText = await response.text();
            let data = null;

            try {
                data = JSON.parse(rawText);
            } catch (parseError) {
                console.error("Invalid JSON response:", rawText);
                showResult("Invalid server response");
                verifying = false;
                updateButton();
                return;
            }

            if (data.status === true) {
                showResult("Verification successful");

                if (data.redirect) {
                    setTimeout(() => {
                        window.location.href = data.redirect;
                    }, 1000);
                }
            } else {
                showResult(data.message || "Verification failed");
            }
        } catch (error) {
            console.error("Verification error:", error);
            showResult("Server error");
        }

        verifying = false;
        updateButton();
    };
}

updateButton();
startCamera();
