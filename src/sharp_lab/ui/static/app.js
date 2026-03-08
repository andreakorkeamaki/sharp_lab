import * as THREE from "three";
import { OrbitControls } from "https://cdn.jsdelivr.net/npm/three@0.178.0/examples/jsm/controls/OrbitControls.js";
import { SparkRenderer, SplatMesh } from "@sparkjsdev/spark";

const inputPathField = document.getElementById("input-path");
const deviceField = document.getElementById("device");
const runButton = document.getElementById("run-button");
const refreshRunsButton = document.getElementById("refresh-runs");
const runStatus = document.getElementById("run-status");
const workspacePath = document.getElementById("workspace-path");
const sharpStatus = document.getElementById("sharp-status");
const checkpointStatus = document.getElementById("checkpoint-status");
const runCount = document.getElementById("run-count");
const runsList = document.getElementById("runs-list");
const viewerTitle = document.getElementById("viewer-title");
const canvasWrap = document.getElementById("canvas-wrap");
const refitCameraButton = document.getElementById("refit-camera");
const flipXButton = document.getElementById("flip-x");
const flipYButton = document.getElementById("flip-y");
const flipZButton = document.getElementById("flip-z");
const turnLeftButton = document.getElementById("turn-left");
const turnRightButton = document.getElementById("turn-right");
const resetPoseButton = document.getElementById("reset-pose");

const scene = new THREE.Scene();
scene.background = new THREE.Color("#141a20");
scene.fog = new THREE.Fog("#141a20", 10, 42);

const renderer = new THREE.WebGLRenderer({ antialias: false, alpha: false });
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
renderer.setSize(canvasWrap.clientWidth, canvasWrap.clientHeight);
canvasWrap.appendChild(renderer.domElement);

const camera = new THREE.PerspectiveCamera(55, canvasWrap.clientWidth / Math.max(canvasWrap.clientHeight, 1), 0.1, 1000);
camera.position.set(0, 0.8, 4.6);

const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;
controls.dampingFactor = 0.07;
controls.target.set(0, 0.2, 0);

const spark = new SparkRenderer({ renderer });
scene.add(spark);

const keyLight = new THREE.DirectionalLight("#fff5da", 1.2);
keyLight.position.set(4, 7, 5);
scene.add(keyLight);

const rimLight = new THREE.DirectionalLight("#87b2ff", 0.55);
rimLight.position.set(-5, 3, -5);
scene.add(rimLight);

const floor = new THREE.Mesh(
  new THREE.CircleGeometry(9, 64),
  new THREE.MeshBasicMaterial({ color: "#20313d", transparent: true, opacity: 0.35, side: THREE.DoubleSide }),
);
floor.rotation.x = -Math.PI / 2;
floor.position.y = -1.6;
scene.add(floor);

let currentSplat = null;
let currentBounds = null;
let currentRotation = new THREE.Euler(0, 0, 0, "XYZ");
let activeRunId = null;

function setBusy(isBusy, message) {
  runButton.disabled = isBusy;
  refreshRunsButton.disabled = isBusy;
  inputPathField.disabled = isBusy;
  deviceField.disabled = isBusy;
  runStatus.textContent = message;
}

function frameBounds(box) {
  const center = box.getCenter(new THREE.Vector3());
  const size = box.getSize(new THREE.Vector3());
  const maxDimension = Math.max(size.x, size.y, size.z, 0.5);
  const fitDistance = maxDimension / Math.tan(THREE.MathUtils.degToRad(camera.fov * 0.5));

  camera.near = Math.max(0.01, fitDistance / 100);
  camera.far = fitDistance * 100;
  camera.updateProjectionMatrix();

  camera.position.copy(center).add(new THREE.Vector3(maxDimension * 0.08, maxDimension * 0.2, fitDistance * 0.72));
  controls.target.copy(center);
  controls.update();
}

function applyCurrentRotation() {
  if (!currentSplat) {
    return;
  }
  currentSplat.rotation.copy(currentRotation);
}

function rotateCurrent(axis, radians) {
  if (!currentSplat) {
    runStatus.textContent = "Load a run first.";
    return;
  }
  currentRotation[axis] += radians;
  applyCurrentRotation();
  runStatus.textContent = `Adjusted orientation on ${axis.toUpperCase()}.`;
}

function resetPose() {
  if (!currentSplat) {
    runStatus.textContent = "Load a run first.";
    return;
  }
  currentRotation.set(0, 0, 0);
  applyCurrentRotation();
  if (currentBounds) {
    frameBounds(currentBounds);
  }
  runStatus.textContent = "Reset orientation.";
}

async function mountSplat(url, title) {
  if (currentSplat) {
    scene.remove(currentSplat);
    currentSplat.dispose();
    currentSplat = null;
    currentBounds = null;
  }

  const splat = new SplatMesh({ url });
  currentRotation.set(0, 0, 0);
  currentSplat = splat;
  scene.add(splat);
  await splat.initialized;

  currentBounds = splat.getBoundingBox(false);
  frameBounds(currentBounds);
  viewerTitle.textContent = title;
  runStatus.textContent = "Splat loaded.";
}

function renderRuns(runs) {
  runCount.textContent = String(runs.length);
  runsList.innerHTML = "";

  if (!runs.length) {
    runsList.innerHTML = '<p class="hint">No local SHARP runs yet.</p>';
    return;
  }

  for (const run of runs) {
    const item = document.createElement("article");
    item.className = `run-item${run.run_id === activeRunId ? " active" : ""}`;

    const title = document.createElement("h3");
    title.className = "run-title";
    title.textContent = run.run_id;
    item.appendChild(title);

    const meta = document.createElement("p");
    meta.className = "run-meta";
    meta.textContent = `${run.status} · ${run.device} · ${run.duration_seconds}s`;
    item.appendChild(meta);

    const source = document.createElement("p");
    source.className = "run-meta";
    source.textContent = run.input_path;
    item.appendChild(source);

    if (run.error) {
      const error = document.createElement("p");
      error.className = "run-error";
      error.textContent = run.error;
      item.appendChild(error);
    }

    const actions = document.createElement("div");
    actions.className = "run-actions";

    const viewButton = document.createElement("button");
    viewButton.type = "button";
    viewButton.className = "secondary";
    viewButton.textContent = run.viewer_urls?.length ? "Open" : "No Output";
    viewButton.disabled = !run.viewer_urls?.length;
    viewButton.addEventListener("click", async () => {
      activeRunId = run.run_id;
      renderRuns(runs);
      await mountSplat(run.viewer_urls[0], run.ply_files[0]);
    });
    actions.appendChild(viewButton);

    const logLink = document.createElement("button");
    logLink.type = "button";
    logLink.className = "secondary";
    logLink.textContent = "Use Log Path";
    logLink.addEventListener("click", () => {
      navigator.clipboard.writeText(run.log_path).catch(() => {});
      runStatus.textContent = `Copied log path for ${run.run_id}.`;
    });
    actions.appendChild(logLink);

    item.appendChild(actions);
    runsList.appendChild(item);
  }
}

async function fetchConfig() {
  const response = await fetch("/api/config");
  if (!response.ok) {
    throw new Error("Could not load config.");
  }
  const payload = await response.json();
  workspacePath.textContent = payload.workspace;
  sharpStatus.textContent = payload.sharp.executable_exists ? "ready" : "missing executable";
  checkpointStatus.textContent = payload.sharp.checkpoint_exists ? "ready" : "missing checkpoint";
}

async function fetchRuns() {
  const response = await fetch("/api/runs");
  if (!response.ok) {
    throw new Error("Could not load runs.");
  }
  const payload = await response.json();
  renderRuns(payload.runs);
  return payload.runs;
}

async function createRun() {
  const inputPath = inputPathField.value.trim();
  if (!inputPath) {
    runStatus.textContent = "Enter an input image or folder path first.";
    return;
  }

  setBusy(true, "Running SHARP locally. This can take a while on CPU.");
  try {
    const response = await fetch("/api/predict", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ input_path: inputPath, device: deviceField.value || null }),
    });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.error || "SHARP run failed.");
    }

    const run = payload.run;
    activeRunId = run.run_id;
    await fetchRuns();
    if (run.viewer_urls?.length) {
      await mountSplat(run.viewer_urls[0], run.ply_files[0]);
    }
    runStatus.textContent = `Created run ${run.run_id}.`;
  } catch (error) {
    console.error(error);
    runStatus.textContent = error.message;
  } finally {
    setBusy(false, runStatus.textContent);
  }
}

function onResize() {
  const width = canvasWrap.clientWidth;
  const height = canvasWrap.clientHeight;
  camera.aspect = width / Math.max(height, 1);
  camera.updateProjectionMatrix();
  renderer.setSize(width, height);
}

function animate() {
  controls.update();
  renderer.render(scene, camera);
}

runButton.addEventListener("click", createRun);
refreshRunsButton.addEventListener("click", async () => {
  try {
    await fetchRuns();
    runStatus.textContent = "Runs refreshed.";
  } catch (error) {
    console.error(error);
    runStatus.textContent = error.message;
  }
});
refitCameraButton.addEventListener("click", () => {
  if (currentBounds) {
    frameBounds(currentBounds);
  }
});
flipXButton.addEventListener("click", () => rotateCurrent("x", Math.PI));
flipYButton.addEventListener("click", () => rotateCurrent("y", Math.PI));
flipZButton.addEventListener("click", () => rotateCurrent("z", Math.PI));
turnLeftButton.addEventListener("click", () => rotateCurrent("y", Math.PI / 2));
turnRightButton.addEventListener("click", () => rotateCurrent("y", -Math.PI / 2));
resetPoseButton.addEventListener("click", resetPose);
window.addEventListener("resize", onResize);
renderer.setAnimationLoop(animate);
onResize();

(async function bootstrap() {
  try {
    await fetchConfig();
    const runs = await fetchRuns();
    if (runs.length > 0 && runs[0].viewer_urls?.length) {
      activeRunId = runs[0].run_id;
      renderRuns(runs);
      await mountSplat(runs[0].viewer_urls[0], runs[0].ply_files[0]);
      runStatus.textContent = "Loaded latest run.";
    } else {
      runStatus.textContent = "Ready. Create a SHARP run from the left panel.";
    }
  } catch (error) {
    console.error(error);
    runStatus.textContent = error.message;
  }
})();
