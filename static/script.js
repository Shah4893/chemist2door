// Elements
const video = document.getElementById("video");
const selfieCanvas = document.getElementById("selfieCanvas");
const captureBtn = document.getElementById("captureBtn");
const verifyBtn = document.getElementById("verifyBtn");
const resultText = document.getElementById("resultText");
const faceOval = document.getElementById("faceOval");

let selfieBase64 = null;
let idBase64 = null;

// Start camera
async function startCamera() {
    try {
        const stream = await navigator.mediaDevices.getUserMedia({ video: true });
        video.srcObject = stream;
        video.play();
    } catch (err) {
        console.log("Camera error:", err);
    }
}

startCamera();


// FACE OVAL DETECTION
async function detectFace() {
    const faceDetector = new FaceDetector({ fastMode: true });

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
        console.log("FaceDetector not supported");
    }

    requestAnimationFrame(detectFace);
}

detectFace();


// SELFIE HOLD FUNCTION
captureBtn.onclick = () => {

    // Canvas setup
    const ctx = selfieCanvas.getContext("2d");
    selfieCanvas.width = video.videoWidth;
    selfieCanvas.height = video.videoHeight;

    // Draw current frame
    ctx.drawImage(video, 0, 0);

    // Convert to Base64
    selfieBase64 = selfieCanvas.toDataURL("image/jpeg", 0.8);

    // HOLD MODE (THIS IS THE IMPORTANT PART)
    const stream = video.srcObject;
    const tracks = stream.getTracks();
    tracks.forEach(track => track.stop());   // camera OFF

    video.style.display = "none";            // hide video
    selfieCanvas.style.display = "block";    // show frozen selfie

    captureBtn.disabled = true;
    captureBtn.innerText = "Selfie Captured";

    faceOval.style.display = "none";         // hide oval frame

    resultText.textContent = "Selfie captured and locked.";
};



// ID UPLOAD
document.getElementById("idInput").onchange = function (e) {
    const file = e.target.files[0];
    const reader = new FileReader();

    reader.onload = function () {
        idBase64 = reader.result;
        resultText.textContent = "ID loaded.";
    };

    reader.readAsDataURL(file);
};


// VERIFY BUTTON
verifyBtn.onclick = async () => {
    if (!selfieBase64 || !idBase64) {
        resultText.textContent = "Please capture selfie and upload ID.";
        return;
    }

    resultText.textContent = "Verifying...";

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
        resultText.textContent = "✔ Verified – redirecting...";
        setTimeout(() => {
            window.location.href = "https://chemist2door.co.uk/";
        }, 2000);
    } else {
        resultText.textContent = "✘ Verification failed";
    }
};
