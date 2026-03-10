import * as THREE from "three";
import { OrbitControls } from "https://cdn.jsdelivr.net/npm/three@0.178.0/examples/jsm/controls/OrbitControls.js";
import { PointerLockControls } from "https://cdn.jsdelivr.net/npm/three@0.178.0/examples/jsm/controls/PointerLockControls.js";
import { SparkRenderer, SplatMesh } from "@sparkjsdev/spark";

const inputPathField = document.getElementById("input-path");
const deviceField = document.getElementById("device");
const runButton = document.getElementById("run-button");
const jumpToRunsButton = document.getElementById("jump-to-runs");
const refreshRunsButton = document.getElementById("refresh-runs");
const refreshRunsTopButton = document.getElementById("runs-refresh-top");
const openLatestRunButton = document.getElementById("open-latest-run");
const runStatus = document.getElementById("run-status");
const processTitle = document.getElementById("process-title");
const processingBadge = document.getElementById("processing-badge");
const processingStateText = document.getElementById("processing-state-text");
const processingElapsed = document.getElementById("processing-elapsed");
const processingDetail = document.getElementById("processing-detail");
const processingSpinner = document.getElementById("processing-spinner");
const progressBar = document.getElementById("progress-bar");
const workspacePath = document.getElementById("workspace-path");
const sharpStatus = document.getElementById("sharp-status");
const checkpointStatus = document.getElementById("checkpoint-status");
const runCount = document.getElementById("run-count");
const latestRunTitle = document.getElementById("latest-run-title");
const latestRunSummary = document.getElementById("latest-run-summary");
const runsList = document.getElementById("runs-list");
const viewerTitle = document.getElementById("viewer-title");
const editorStatus = document.getElementById("editor-status");
const editorRunId = document.getElementById("editor-run-id");
const editorSource = document.getElementById("editor-source");
const editorOutput = document.getElementById("editor-output");
const editorFile = document.getElementById("editor-file");
const canvasWrap = document.getElementById("canvas-wrap");
const refitCameraButton = document.getElementById("refit-camera");
const toggleFlyModeButton = document.getElementById("toggle-fly-mode");
const flipXButton = document.getElementById("flip-x");
const flipYButton = document.getElementById("flip-y");
const flipZButton = document.getElementById("flip-z");
const turnLeftButton = document.getElementById("turn-left");
const turnRightButton = document.getElementById("turn-right");
const resetPoseButton = document.getElementById("reset-pose");
const artifactSelect = document.getElementById("artifact-select");
const decimationRatio = document.getElementById("decimation-ratio");
const decimationValue = document.getElementById("decimation-value");
const decimateRunButton = document.getElementById("decimate-run");
const downloadPlyButton = document.getElementById("download-ply");
const copyOutputPathButton = document.getElementById("copy-output-path");

const viewButtons = [...document.querySelectorAll("[data-view-target]")];
const viewPanels = [...document.querySelectorAll("[data-view]")];

const scene = new THREE.Scene();
scene.background = new THREE.Color("#141a20");
scene.fog = new THREE.Fog("#141a20", 10, 42);

const renderer = new THREE.WebGLRenderer({ antialias: false, alpha: false });
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
renderer.setSize(Math.max(canvasWrap.clientWidth, 1), Math.max(canvasWrap.clientHeight, 1));
canvasWrap.appendChild(renderer.domElement);

const camera = new THREE.PerspectiveCamera(55, 1, 0.1, 1000);
camera.position.set(0, 0.8, 4.6);

const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;
controls.dampingFactor = 0.07;
controls.target.set(0, 0.2, 0);

const flyControls = new PointerLockControls(camera, renderer.domElement);

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
let activeArtifactName = null;
let currentRuns = [];
let processingStartedAt = null;
let processingTimerId = null;
const flyMovement = {
  forward: false,
  backward: false,
  left: false,
  right: false,
  up: false,
  down: false,
  boost: false,
};
const flyClock = new THREE.Clock();
let flyModeEnabled = false;

function formatElapsed(totalSeconds) {
  const minutes = String(Math.floor(totalSeconds / 60)).padStart(2, "0");
  const seconds = String(totalSeconds % 60).padStart(2, "0");
  return `${minutes}:${seconds}`;
}

function getActiveRun() {
  return currentRuns.find((entry) => entry.run_id === activeRunId) ?? null;
}

function getArtifactForRun(run, preferredFilename = activeArtifactName) {
  if (!run?.viewer_urls?.length || !run?.ply_files?.length) {
    return null;
  }

  const requestedIndex = preferredFilename ? run.ply_files.findIndex((name) => name === preferredFilename) : -1;
  const activeIndex = requestedIndex >= 0 ? requestedIndex : 0;
  return {
    filename: run.ply_files[activeIndex],
    url: run.viewer_urls[activeIndex],
  };
}

function updateDecimationValue() {
  decimationValue.textContent = `${decimationRatio.value}%`;
}

function updateProcessingClock() {
  if (!processingStartedAt) {
    processingElapsed.textContent = "00:00";
    return;
  }
  const elapsedSeconds = Math.max(0, Math.floor((Date.now() - processingStartedAt) / 1000));
  processingElapsed.textContent = formatElapsed(elapsedSeconds);
}

function startProcessingClock() {
  processingStartedAt = Date.now();
  updateProcessingClock();
  clearInterval(processingTimerId);
  processingTimerId = window.setInterval(updateProcessingClock, 1000);
}

function stopProcessingClock() {
  processingStartedAt = null;
  clearInterval(processingTimerId);
  processingTimerId = null;
  processingElapsed.textContent = "00:00";
}

function setProcessingState(state, message, detail) {
  processingBadge.classList.remove("is-running", "is-complete", "is-error");
  processingStateText.textContent = state;
  runStatus.textContent = message;
  processingDetail.textContent = detail;
  processTitle.textContent = state === "Running" ? "Processing in progress" : state === "Complete" ? "Run completed" : state === "Error" ? "Run failed" : "Ready to run";

  if (state === "Running") {
    processingBadge.textContent = "Running";
    processingBadge.classList.add("is-running");
    processingSpinner.hidden = false;
    progressBar.style.transform = "scaleX(0.68)";
    startProcessingClock();
    return;
  }

  processingSpinner.hidden = true;
  if (state === "Complete") {
    processingBadge.textContent = "Complete";
    processingBadge.classList.add("is-complete");
    progressBar.style.transform = "scaleX(1)";
  } else if (state === "Error") {
    processingBadge.textContent = "Error";
    processingBadge.classList.add("is-error");
    progressBar.style.transform = "scaleX(1)";
  } else {
    processingBadge.textContent = "Idle";
    progressBar.style.transform = "scaleX(0.18)";
  }
  stopProcessingClock();
}

function setBusy(isBusy) {
  runButton.disabled = isBusy;
  jumpToRunsButton.disabled = isBusy;
  refreshRunsButton.disabled = isBusy;
  refreshRunsTopButton.disabled = isBusy;
  openLatestRunButton.disabled = isBusy || !findLatestCompletedRun(currentRuns);
  inputPathField.disabled = isBusy;
  deviceField.disabled = isBusy;
}

function setView(viewName) {
  if (viewName !== "editor" && flyControls.isLocked) {
    flyControls.unlock();
  }
  for (const button of viewButtons) {
    button.classList.toggle("active", button.dataset.viewTarget === viewName);
  }
  for (const panel of viewPanels) {
    panel.classList.toggle("active", panel.dataset.view === viewName);
  }
  if (viewName === "editor") {
    window.requestAnimationFrame(() => {
      onResize();
      controls.update();
    });
  }
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

function syncOrbitTarget() {
  const direction = new THREE.Vector3();
  camera.getWorldDirection(direction);
  controls.target.copy(camera.position).add(direction.multiplyScalar(3));
  controls.update();
}

function setFlyMode(enabled) {
  flyModeEnabled = enabled;
  controls.enabled = !enabled;
  toggleFlyModeButton.textContent = enabled ? "Exit Fly Mode" : "Enter Fly Mode";
  toggleFlyModeButton.classList.toggle("secondary", !enabled);
  flyClock.getDelta();
  if (!enabled) {
    syncOrbitTarget();
  }
}

function onFlyLockChange() {
  setFlyMode(flyControls.isLocked);
  if (!flyControls.isLocked) {
    for (const key of Object.keys(flyMovement)) {
      flyMovement[key] = false;
    }
  }
}

function updateFlyMovement() {
  if (!flyModeEnabled || !flyControls.isLocked) {
    flyClock.getDelta();
    return;
  }

  const delta = Math.min(flyClock.getDelta(), 0.05);
  const speed = (flyMovement.boost ? 4.8 : 1.8) * delta;

  if (flyMovement.forward) {
    flyControls.moveForward(speed);
  }
  if (flyMovement.backward) {
    flyControls.moveForward(-speed);
  }
  if (flyMovement.left) {
    flyControls.moveRight(-speed);
  }
  if (flyMovement.right) {
    flyControls.moveRight(speed);
  }
  if (flyMovement.up) {
    camera.position.y += speed;
  }
  if (flyMovement.down) {
    camera.position.y -= speed;
  }
}

function onMovementKey(event, pressed) {
  if (!flyModeEnabled) {
    return;
  }

  switch (event.code) {
    case "KeyW":
      flyMovement.forward = pressed;
      break;
    case "KeyS":
      flyMovement.backward = pressed;
      break;
    case "KeyA":
      flyMovement.left = pressed;
      break;
    case "KeyD":
      flyMovement.right = pressed;
      break;
    case "KeyE":
      flyMovement.up = pressed;
      break;
    case "KeyQ":
      flyMovement.down = pressed;
      break;
    case "ShiftLeft":
    case "ShiftRight":
      flyMovement.boost = pressed;
      break;
    default:
      return;
  }

  event.preventDefault();
}

function applyCurrentRotation() {
  if (!currentSplat) {
    return;
  }
  currentSplat.rotation.copy(currentRotation);
}

function rotateCurrent(axis, radians) {
  if (!currentSplat) {
    editorStatus.textContent = "Open a run in the editor first.";
    return;
  }
  currentRotation[axis] += radians;
  applyCurrentRotation();
  editorStatus.textContent = `Adjusted orientation on ${axis.toUpperCase()}.`;
}

function resetPose() {
  if (!currentSplat) {
    editorStatus.textContent = "Open a run in the editor first.";
    return;
  }
  currentRotation.set(0, 0, 0);
  applyCurrentRotation();
  if (currentBounds) {
    frameBounds(currentBounds);
  }
  editorStatus.textContent = "Reset orientation.";
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
  editorStatus.textContent = "Splat loaded.";
}

function findLatestCompletedRun(runs) {
  return runs.find((run) => run.viewer_urls?.length);
}

function formatRunSummary(run) {
  if (!run) {
    return "No runs yet.";
  }
  return `${run.status} on ${run.device} in ${run.duration_seconds}s`;
}

function updateLatestRun(run) {
  runCount.textContent = String(currentRuns.length);
  if (!run) {
    latestRunTitle.textContent = "No run yet";
    latestRunSummary.textContent = "Your latest run will appear here with a shortcut into the editor.";
    openLatestRunButton.disabled = true;
    return;
  }

  latestRunTitle.textContent = run.run_id;
  latestRunSummary.textContent = `${formatRunSummary(run)}${run.error ? ` · ${run.error}` : ""}`;
  openLatestRunButton.disabled = !run.viewer_urls?.length;
}

function updateEditorMeta(run) {
  if (!run) {
    activeArtifactName = null;
    viewerTitle.textContent = "No splat loaded";
    editorRunId.textContent = "-";
    editorSource.textContent = "-";
    editorOutput.textContent = "-";
    editorFile.textContent = "-";
    editorStatus.textContent = "Choose a completed run from the Runs page to start editing.";
    artifactSelect.innerHTML = '<option value="">No output yet</option>';
    artifactSelect.disabled = true;
    decimateRunButton.disabled = true;
    downloadPlyButton.disabled = true;
    copyOutputPathButton.disabled = true;
    return;
  }

  editorRunId.textContent = run.run_id;
  editorSource.textContent = run.input_path;
  editorOutput.textContent = run.output_dir;
  const activeArtifact = getArtifactForRun(run);
  activeArtifactName = activeArtifact?.filename || null;
  editorFile.textContent = activeArtifact?.filename || "-";
  artifactSelect.innerHTML = "";
  if (run.ply_files?.length) {
    for (const filename of run.ply_files) {
      const option = document.createElement("option");
      option.value = filename;
      option.textContent = filename;
      artifactSelect.appendChild(option);
    }
    artifactSelect.value = activeArtifact?.filename || run.ply_files[0];
    artifactSelect.disabled = false;
  } else {
    artifactSelect.innerHTML = '<option value="">No output yet</option>';
    artifactSelect.disabled = true;
  }
  decimateRunButton.disabled = !run.viewer_urls?.length;
  downloadPlyButton.disabled = !activeArtifact;
  copyOutputPathButton.disabled = false;
}

function renderRuns(runs) {
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

    const openButton = document.createElement("button");
    openButton.type = "button";
    openButton.className = "secondary";
    openButton.textContent = run.viewer_urls?.length ? "Open Editor" : "No Output";
    openButton.disabled = !run.viewer_urls?.length;
    openButton.addEventListener("click", async () => {
      await openRunInEditor(run.run_id);
    });
    actions.appendChild(openButton);

    const copyLogButton = document.createElement("button");
    copyLogButton.type = "button";
    copyLogButton.className = "secondary";
    copyLogButton.textContent = "Copy Log Path";
    copyLogButton.addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(run.log_path);
        setView("runs");
        editorStatus.textContent = `Copied log path for ${run.run_id}.`;
      } catch (error) {
        console.error(error);
      }
    });
    actions.appendChild(copyLogButton);

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
  currentRuns = payload.runs;
  renderRuns(currentRuns);
  updateLatestRun(currentRuns[0] ?? null);
  updateEditorMeta(getActiveRun());
  setBusy(false);
  return currentRuns;
}

async function createRun() {
  const inputPath = inputPathField.value.trim();
  if (!inputPath) {
    setProcessingState("Error", "Enter an input image or folder path first.", "The run cannot start until an input path is provided.");
    return;
  }

  setView("process");
  setBusy(true);
  setProcessingState("Running", "Running SHARP locally. This can take a while on CPU.", "You can stay here while the process runs, then jump into Runs or the Editor when it completes.");

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
    updateLatestRun(currentRuns[0] ?? run);
    setProcessingState("Complete", `Created run ${run.run_id}.`, "Open the latest run or browse the full run history to continue in the editor.");
  } catch (error) {
    console.error(error);
    setProcessingState("Error", error.message, "Check the run log path in the Runs page if SHARP failed before producing output.");
  } finally {
    setBusy(false);
  }
}

async function openRunInEditor(runId, preferredFilename = null) {
  const run = currentRuns.find((entry) => entry.run_id === runId);
  if (!run) {
    return;
  }

  activeRunId = run.run_id;
  activeArtifactName = preferredFilename;
  updateEditorMeta(run);
  renderRuns(currentRuns);
  setView("editor");

  const artifact = getArtifactForRun(run);
  if (!artifact) {
    editorStatus.textContent = "This run has no viewable output.";
    return;
  }

  try {
    editorStatus.textContent = "Loading splat...";
    activeArtifactName = artifact.filename;
    editorFile.textContent = artifact.filename;
    artifactSelect.value = artifact.filename;
    await mountSplat(artifact.url, artifact.filename);
    syncOrbitTarget();
  } catch (error) {
    console.error(error);
    editorStatus.textContent = "Failed to load the selected splat.";
  }
}

function downloadCurrentPly() {
  const run = getActiveRun();
  const artifact = getArtifactForRun(run);
  if (!artifact) {
    editorStatus.textContent = "No exported `.ply` is available for this run.";
    return;
  }

  const link = document.createElement("a");
  link.href = artifact.url;
  link.download = artifact.filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  editorStatus.textContent = "Started download for the current `.ply`.";
}

async function copyOutputPath() {
  const run = getActiveRun();
  if (!run) {
    editorStatus.textContent = "Open a run first.";
    return;
  }
  try {
    await navigator.clipboard.writeText(run.output_dir);
    editorStatus.textContent = `Copied output path for ${run.run_id}.`;
  } catch (error) {
    console.error(error);
    editorStatus.textContent = "Could not copy the output path.";
  }
}

async function decimateCurrentRun() {
  const run = getActiveRun();
  const artifact = getArtifactForRun(run);
  if (!run || !artifact) {
    editorStatus.textContent = "Open a run with a `.ply` output first.";
    return;
  }

  decimateRunButton.disabled = true;
  editorStatus.textContent = `Creating decimated copy from ${artifact.filename}...`;

  try {
    const response = await fetch(`/api/runs/${encodeURIComponent(run.run_id)}/decimate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        filename: artifact.filename,
        ratio: Number(decimationRatio.value) / 100,
      }),
    });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.error || "Could not decimate the selected PLY.");
    }

    currentRuns = currentRuns.map((entry) => entry.run_id === run.run_id ? payload.run : entry);
    renderRuns(currentRuns);
    updateLatestRun(currentRuns[0] ?? null);
    await openRunInEditor(run.run_id, payload.decimation.output_file);
    editorStatus.textContent = `Created ${payload.decimation.output_file} with ${payload.decimation.decimated_vertices} vertices.`;
  } catch (error) {
    console.error(error);
    editorStatus.textContent = error.message;
  } finally {
    const activeRun = getActiveRun();
    decimateRunButton.disabled = !activeRun?.viewer_urls?.length;
  }
}

function onResize() {
  const width = Math.max(canvasWrap.clientWidth, 1);
  const height = Math.max(canvasWrap.clientHeight, 1);
  camera.aspect = width / height;
  camera.updateProjectionMatrix();
  renderer.setSize(width, height);
}

function animate() {
  updateFlyMovement();
  if (!flyModeEnabled) {
    controls.update();
  }
  renderer.render(scene, camera);
}

runButton.addEventListener("click", createRun);
jumpToRunsButton.addEventListener("click", () => setView("runs"));
refreshRunsButton.addEventListener("click", async () => {
  try {
    await fetchRuns();
    setProcessingState("Idle", "Runs refreshed.", "Browse your history or start another SHARP run.");
  } catch (error) {
    console.error(error);
    setProcessingState("Error", error.message, "The app could not refresh the local run history.");
  }
});
refreshRunsTopButton.addEventListener("click", async () => {
  try {
    await fetchRuns();
  } catch (error) {
    console.error(error);
  }
});
openLatestRunButton.addEventListener("click", async () => {
  const latestRun = findLatestCompletedRun(currentRuns);
  if (latestRun) {
    await openRunInEditor(latestRun.run_id);
  }
});
refitCameraButton.addEventListener("click", () => {
  if (currentBounds) {
    frameBounds(currentBounds);
    editorStatus.textContent = "Refit camera.";
  }
});
toggleFlyModeButton.addEventListener("click", () => {
  if (flyControls.isLocked) {
    flyControls.unlock();
    return;
  }
  if (!activeRunId) {
    editorStatus.textContent = "Open a run in the editor first.";
    return;
  }
  flyControls.lock();
  editorStatus.textContent = "Fly mode enabled. Use mouse look with W A S D, Q/E, and Shift.";
});
flipXButton.addEventListener("click", () => rotateCurrent("x", Math.PI));
flipYButton.addEventListener("click", () => rotateCurrent("y", Math.PI));
flipZButton.addEventListener("click", () => rotateCurrent("z", Math.PI));
turnLeftButton.addEventListener("click", () => rotateCurrent("y", Math.PI / 2));
turnRightButton.addEventListener("click", () => rotateCurrent("y", -Math.PI / 2));
resetPoseButton.addEventListener("click", resetPose);
downloadPlyButton.addEventListener("click", downloadCurrentPly);
copyOutputPathButton.addEventListener("click", copyOutputPath);
artifactSelect.addEventListener("change", async () => {
  const run = getActiveRun();
  if (!run) {
    return;
  }
  await openRunInEditor(run.run_id, artifactSelect.value);
});
decimationRatio.addEventListener("input", updateDecimationValue);
decimateRunButton.addEventListener("click", decimateCurrentRun);

for (const button of viewButtons) {
  button.addEventListener("click", () => setView(button.dataset.viewTarget));
}

flyControls.addEventListener("lock", onFlyLockChange);
flyControls.addEventListener("unlock", onFlyLockChange);
window.addEventListener("keydown", (event) => onMovementKey(event, true));
window.addEventListener("keyup", (event) => onMovementKey(event, false));
window.addEventListener("resize", onResize);
renderer.setAnimationLoop(animate);
updateEditorMeta(null);
updateDecimationValue();
setProcessingState("Idle", "Enter a path and start a SHARP run.", "The app will keep this page focused on processing until the run completes.");
onResize();

(async function bootstrap() {
  try {
    await fetchConfig();
    await fetchRuns();
  } catch (error) {
    console.error(error);
    setProcessingState("Error", error.message, "The local UI could not load its initial configuration.");
  }
})();
