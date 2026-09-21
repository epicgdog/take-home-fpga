import "./style.css";

const OFFER_URL = "http://127.0.0.1:8000/offer";
const video = document.querySelector("#camera");
const status = document.querySelector("#status");
const peer = new RTCPeerConnection();

// this basically means that the browser for video will only get from the remote, it will never send its own. 
peer.addTransceiver("video", { direction: "recvonly" });

// when a new track or basicaly on a fresh connectino the track will be streamed
peer.addEventListener("track", (event) => {
  video.srcObject = event.streams[0] ?? new MediaStream([event.track]);
});

// when dropped, we show the status
peer.addEventListener("connectionstatechange", () => {
  status.textContent = `WebRTC: ${peer.connectionState}`;
});


// ice gathering is basically when we try to find which ips and ports we can reach the remote. 
// this occurs every time we setup the local description offer. We basically configure an ICE to send to the server so it can reach us. 
async function waitForIceGathering() {
  if (peer.iceGatheringState === "complete") {
    return;
  }

  await new Promise((resolve) => {
    function checkState() {
      if (peer.iceGatheringState === "complete") {
        peer.removeEventListener("icegatheringstatechange", checkState);
        resolve();
      }
    }

    peer.addEventListener("icegatheringstatechange", checkState);
  });
}

async function connect() {
  const offer = await peer.createOffer();
  await peer.setLocalDescription(offer);
  await waitForIceGathering();

  const response = await fetch(OFFER_URL, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      sdp: peer.localDescription.sdp,
      type: peer.localDescription.type,
    }),
  });

  if (!response.ok) {
    throw new Error(`Offer failed with HTTP ${response.status}`);
  }

  const answer = await response.json();
  await peer.setRemoteDescription(answer);
}

connect().catch((error) => {
  console.error(error);
  status.textContent = error.message;
});

window.addEventListener("beforeunload", () => {
  peer.close();
});
