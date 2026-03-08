import * as THREE from "three";
import { OrbitControls } from "https://cdn.jsdelivr.net/npm/three@0.178.0/examples/jsm/controls/OrbitControls.js";
import { SparkRenderer, SplatMesh } from "@sparkjsdev/spark";

const DEMO_URL = "https://sparkjs.dev/assets/splats/butterfly.spz";

const canvasWrap = document.getElementById("canvas-wrap");
const dropZone = document.getElementById("drop-zone");
const fileInput = document.getElementById("file-input");
const urlInput = document.getElementById("url-input");
const loadUrlButton = document.getElementById("load-url");
const demoButton = document.getElementById("demo-button");
const resetCameraButton = document.getElementById("reset-camera");
const flipXButton = document.getElementById("flip-x");
const flipYButton = document.getElementById("flip-y");
const flipZButton = document.getElementById("flip-z");
const turnLeftButton = document.getElementById("turn-left");
const turnRightButton = document.getElementById("turn-right");
const resetPoseButton = document.getElementById("reset-pose");
const statusText = document.getElementById("status-text");
const sourceText = document.getElementById("source-text");
const splatCountText = document.getElementById("splat-count");

const scene = new THREE.Scene();
scene.background = new THREE.Color("#161c22");
scene.fog = new THREE.Fog("#161c22", 9, 38);

const renderer = new THREE.WebGLRenderer({ antialias: false, alpha: false });
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
renderer.setSize(canvasWrap.clientWidth, canvasWrap.clientHeight);
canvasWrap.appendChild(renderer.domElement);

const camera = new THREE.PerspectiveCamera(
  55,
  canvasWrap.clientWidth / Math.max(canvasWrap.clientHeight, 1),
  0.1,
  1000,
);
camera.position.set(0, 0.8, 4.6);

const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;
controls.dampingFactor = 0.07;
controls.target.set(0, 0.2, 0);

const spark = new SparkRenderer({ renderer });
scene.add(spark);

const keyLight = new THREE.DirectionalLight("#fff4d9", 1.2);
keyLight.position.set(4, 7, 5);
scene.add(keyLight);

const rimLight = new THREE.DirectionalLight("#8cb9ff", 0.65);
rimLight.position.set(-5, 3, -4);
scene.add(rimLight);

const floor = new THREE.Mesh(
  new THREE.CircleGeometry(8, 64),
  new THREE.MeshBasicMaterial({
    color: "#23303b",
    transparent: true,
    opacity: 0.44,
    side: THREE.DoubleSide,
  }),
);
floor.rotation.x = -Math.PI / 2;
floor.position.y = -1.4;
scene.add(floor);

let currentSplat = null;
let currentBounds = null;
let currentRotation = new THREE.Euler(0, 0, 0, "XYZ");

function setLoading(isLoading, message) {
  fileInput.disabled = isLoading;
  urlInput.disabled = isLoading;
  loadUrlButton.disabled = isLoading;
  demoButton.disabled = isLoading;
  resetCameraButton.disabled = isLoading;
  statusText.textContent = message;
}

function clearSplat() {
  if (!currentSplat) {
    return;
  }

  scene.remove(currentSplat);
  currentSplat.dispose();
  currentSplat = null;
  currentBounds = null;
  currentRotation = new THREE.Euler(0, 0, 0, "XYZ");
  splatCountText.textContent = "-";
}

function applyCurrentRotation() {
  if (!currentSplat) {
    return;
  }

  currentSplat.rotation.copy(currentRotation);
}

function rotateCurrent(axis, radians) {
  if (!currentSplat) {
    statusText.textContent = "Load a splat first.";
    return;
  }

  currentRotation[axis] += radians;
  applyCurrentRotation();
  statusText.textContent = `Adjusted orientation on ${axis.toUpperCase()}.`;
}

function resetPose() {
  if (!currentSplat) {
    statusText.textContent = "Load a splat first.";
    return;
  }

  currentRotation.set(0, 0, 0);
  applyCurrentRotation();
  frameBounds(currentBounds);
  statusText.textContent = "Reset orientation.";
}

function frameBounds(box) {
  const center = box.getCenter(new THREE.Vector3());
  const size = box.getSize(new THREE.Vector3());
  const maxDimension = Math.max(size.x, size.y, size.z, 0.5);
  const fitDistance = maxDimension / Math.tan(THREE.MathUtils.degToRad(camera.fov * 0.5));

  camera.near = Math.max(0.01, fitDistance / 100);
  camera.far = fitDistance * 100;
  camera.updateProjectionMatrix();

  camera.position.copy(center).add(new THREE.Vector3(maxDimension * 0.1, maxDimension * 0.2, fitDistance * 0.72));
  controls.target.copy(center);
  controls.update();
}

async function mountSplat(splat, sourceLabel) {
  clearSplat();
  currentSplat = splat;
  currentRotation.set(0, 0, 0);
  scene.add(splat);

  await splat.initialized;

  currentBounds = splat.getBoundingBox(false);
  frameBounds(currentBounds);

  sourceText.textContent = sourceLabel;
  splatCountText.textContent = String(splat.numSplats ?? "-");
  statusText.textContent = "Loaded. Orbit to inspect the splat.";
}

async function loadFromFile(file) {
  setLoading(true, `Loading ${file.name}...`);

  try {
    const bytes = await file.arrayBuffer();
    const splat = new SplatMesh({ fileBytes: bytes });
    await mountSplat(splat, file.name);
  } catch (error) {
    console.error(error);
    statusText.textContent = "Failed to decode this splat file.";
  } finally {
    setLoading(false, statusText.textContent);
  }
}

async function loadFromUrl(url) {
  setLoading(true, "Fetching remote splat...");

  try {
    const splat = new SplatMesh({ url });
    await mountSplat(splat, url);
  } catch (error) {
    console.error(error);
    statusText.textContent = "Failed to load remote splat. Check the URL and CORS settings.";
  } finally {
    setLoading(false, statusText.textContent);
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

fileInput.addEventListener("change", async (event) => {
  const [file] = event.target.files ?? [];
  if (!file) {
    return;
  }
  await loadFromFile(file);
});

loadUrlButton.addEventListener("click", async () => {
  const url = urlInput.value.trim();
  if (!url) {
    statusText.textContent = "Enter a remote splat URL first.";
    return;
  }
  await loadFromUrl(url);
});

demoButton.addEventListener("click", async () => {
  urlInput.value = DEMO_URL;
  await loadFromUrl(DEMO_URL);
});

resetCameraButton.addEventListener("click", () => {
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

window.addEventListener("dragenter", (event) => {
  event.preventDefault();
  dropZone.classList.add("visible");
});

window.addEventListener("dragover", (event) => {
  event.preventDefault();
});

window.addEventListener("dragleave", (event) => {
  event.preventDefault();
  if (event.target === document.documentElement || event.target === document.body) {
    dropZone.classList.remove("visible");
  }
});

window.addEventListener("drop", async (event) => {
  event.preventDefault();
  dropZone.classList.remove("visible");
  const [file] = [...(event.dataTransfer?.files ?? [])];
  if (!file) {
    return;
  }
  await loadFromFile(file);
});

renderer.setAnimationLoop(animate);
onResize();

const queryUrl = new URLSearchParams(window.location.search).get("url");
if (queryUrl) {
  urlInput.value = queryUrl;
  loadFromUrl(queryUrl);
} else {
  statusText.textContent = "Ready. Load a local file or paste a remote URL.";
}
