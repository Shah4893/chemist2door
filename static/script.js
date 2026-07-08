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



function showResult(message){

    resultText.textContent = message;

}



function updateButton(){

    if(
        selfieBase64 &&
        idBase64 &&
        !verifying
    ){

        verifyBtn.disabled = false;

    }
    else{

        verifyBtn.disabled = true;

    }

}



// ==============================
// CAMERA START
// ==============================

async function startCamera(){

    try{

        stream = await navigator.mediaDevices.getUserMedia({

            video:{
                facingMode:"user"
            },

            audio:false

        });


        video.srcObject = stream;

        await video.play();


        showResult(
            "Camera ready"
        );


        faceOval.style.borderColor="#00aa00";


    }

    catch(error){

        showResult(
            "Camera permission denied"
        );

    }

}


startCamera();



// ==============================
// STOP CAMERA
// ==============================

function stopCamera(){

    if(stream){

        stream
        .getTracks()
        .forEach(track=>{
            track.stop();
        });


        stream=null;

    }

}



// ==============================
// SELFIE CAPTURE
// ==============================

captureBtn.onclick=function(){


    if(!video.videoWidth){

        showResult(
            "Camera loading"
        );

        return;

    }



    const width = video.videoWidth;
    const height = video.videoHeight;


    canvas.width = width;
    canvas.height = height;


    const ctx =
    canvas.getContext("2d");


    ctx.drawImage(
        video,
        0,
        0,
        width,
        height
    );



    selfieBase64 =
    canvas.toDataURL(
        "image/jpeg",
        0.65
    );



    stopCamera();



    video.style.display="none";

    canvas.style.display="block";

    faceOval.style.display="none";


    captureBtn.disabled=true;

    captureBtn.textContent=
    "Captured";


    showResult(
        "Selfie captured"
    );


    updateButton();


};




// ==============================
// ID UPLOAD
// ==============================


idInput.onchange=function(){


    const file=this.files[0];


    if(!file)
        return;



    if(
        !file.type.startsWith("image/")
    ){

        showResult(
            "Only image files allowed"
        );

        return;

    }




    const reader =
    new FileReader();



    reader.onload=function(e){


        idBase64=e.target.result;


        idPreview.src=
        idBase64;


        idPreview.style.display=
        "block";


        idFileName.textContent=
        file.name;



        showResult(
            "ID loaded"
        );


        updateButton();


    };



    reader.readAsDataURL(file);


};




// ==============================
// VERIFY
// ==============================


verifyBtn.onclick=async function(){


    if(verifying)
        return;



    verifying=true;

    updateButton();


    showResult(
        "Verification running..."
    );



    try{


        const response =
        await fetch(
            "/verify",
            {

                method:"POST",

                headers:{

                    "Content-Type":
                    "application/json"

                },


                body:JSON.stringify({

                    selfie:selfieBase64,

                    id_image:idBase64

                })


            }
        );



        const data =
        await response.json();



        if(data.status===true){


            showResult(
                "✔ Verification successful"
            );



            if(data.redirect){

                setTimeout(()=>{

                    window.location.href =
                    data.redirect;

                },1000);

            }


        }


        else{


            showResult(

                data.message ||
                "Verification failed"

            );


        }



    }


    catch(error){


        showResult(
            "Server error"
        );


    }



    verifying=false;

    updateButton();


};
