const buildFlavor = document.getElementById("build-flavor");
const buildHint = document.getElementById("build-hint");
const runtimeStatus = document.getElementById("runtime-status");
const runtimeHint = document.getElementById("runtime-hint");
const modelStatus = document.getElementById("model-status");
const modelHint = document.getElementById("model-hint");
const workspacePath = document.getElementById("workspace-path");
const activityTitle = document.getElementById("activity-title");
const activityMessage = document.getElementById("activity-message");
const activityDetail = document.getElementById("activity-detail");
const installRuntimeButton = document.getElementById("install-runtime");
const downloadModelButton = document.getElementById("download-model");
const openStudioButton = document.getElementById("open-studio");

let currentConfig = null;

function setActivity(title, message, detail) {
  activityTitle.textContent = title;
  activityMessage.textContent = message;
  activityDetail.textContent = detail;
}

function applyStatus(payload) {
  currentConfig = payload;
  const { sharp, release } = payload;

  workspacePath.textContent = payload.workspace;
  buildFlavor.textContent = release.build_flavor === "lite" ? "Lite build" : "Full build";
  buildHint.textContent = release.can_download_runtime
    ? "This app knows where to fetch the portable runtime for this release."
    : "This build has no runtime download URL embedded.";

  runtimeStatus.textContent = sharp.executable_exists ? "Installed" : "Missing";
  runtimeHint.textContent = sharp.executable_exists
    ? `Runtime ready at ${sharp.executable}.`
    : "Install the portable runtime into this app folder before opening the studio.";

  modelStatus.textContent = sharp.checkpoint_exists ? "Installed" : "Optional";
  modelHint.textContent = sharp.checkpoint_exists
    ? `Model ready at ${sharp.checkpoint}.`
    : sharp.preferred_checkpoint
      ? `The Apple model will be saved to ${sharp.preferred_checkpoint}.`
      : "Install the runtime first, then download or place the model manually.";

  installRuntimeButton.disabled = !release.can_download_runtime;
  downloadModelButton.disabled = !sharp.runtime_ready;
  openStudioButton.disabled = !sharp.runtime_ready;

  if (!sharp.executable_exists) {
    setActivity(
      "Runtime required",
      "Install the SHARP runtime first.",
      "The Lite build keeps the runtime out of the zip so the first download stays smaller.",
    );
    return;
  }

  if (!sharp.checkpoint_exists) {
    setActivity(
      "Runtime ready",
      "The app can open the studio now.",
      "You can also download the Apple model first so prediction runs do not pause on first fetch.",
    );
    return;
  }

  setActivity("Ready", "Everything needed for local runs is installed.", "Open the studio and start a new SHARP run.");
}

async function refreshStatus() {
  const response = await fetch("/api/config");
  if (!response.ok) {
    throw new Error("Could not load setup status.");
  }
  const payload = await response.json();
  applyStatus(payload);
}

async function installRuntime() {
  installRuntimeButton.disabled = true;
  setActivity("Installing runtime", "Downloading the portable SHARP runtime.", "This can take a while on the Lite build.");

  try {
    const response = await fetch("/api/setup/install-runtime", { method: "POST" });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.error || "Could not install the runtime.");
    }
    await refreshStatus();
    setActivity("Runtime installed", `Installed the runtime to ${payload.runtime_path}.`, "You can now open the studio or download the model.");
  } catch (error) {
    console.error(error);
    setActivity("Install failed", error.message, "Check the network or release metadata, then try again.");
  } finally {
    if (currentConfig?.release?.can_download_runtime) {
      installRuntimeButton.disabled = false;
    }
  }
}

async function downloadModel() {
  downloadModelButton.disabled = true;
  setActivity("Downloading model", "Fetching the Apple SHARP model.", "The file will be saved inside the local runtime folder.");

  try {
    const response = await fetch("/api/setup/download-checkpoint", { method: "POST" });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.error || "Could not download the Apple model.");
    }
    await refreshStatus();
    setActivity("Model installed", `Saved the Apple model to ${payload.checkpoint_path}.`, "The studio can now run predictions without waiting for a first-run download.");
  } catch (error) {
    console.error(error);
    setActivity("Model download failed", error.message, "You can also place the model file in the runtime models folder manually.");
  } finally {
    downloadModelButton.disabled = !currentConfig?.sharp?.runtime_ready;
  }
}

function openStudio() {
  const path = currentConfig?.release?.studio_path || "/studio";
  window.location.href = path;
}

installRuntimeButton.addEventListener("click", installRuntime);
downloadModelButton.addEventListener("click", downloadModel);
openStudioButton.addEventListener("click", openStudio);

refreshStatus().catch((error) => {
  console.error(error);
  setActivity("Setup unavailable", error.message, "Reload the page after the local app finishes starting.");
});
