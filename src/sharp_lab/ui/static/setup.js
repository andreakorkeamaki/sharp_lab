const heroHint = document.getElementById("hero-hint");
const setupShell = document.querySelector(".setup-shell");
const wizardPanel = document.querySelector(".wizard-panel");
const workspacePath = document.getElementById("workspace-path");
const activityTitle = document.getElementById("activity-title");
const activityBadge = document.getElementById("activity-badge");
const activityMessage = document.getElementById("activity-message");
const activityDetail = document.getElementById("activity-detail");

const runtimeStep = document.getElementById("runtime-step");
const runtimeStatus = document.getElementById("runtime-status");
const runtimeHint = document.getElementById("runtime-hint");
const runtimeProgressBlock = document.getElementById("runtime-progress-block");
const runtimeProgressBar = document.getElementById("runtime-progress-bar");
const runtimeProgressText = document.getElementById("runtime-progress-text");
const installRuntimeButton = document.getElementById("install-runtime");

const modelStep = document.getElementById("model-step");
const modelStatus = document.getElementById("model-status");
const modelHint = document.getElementById("model-hint");
const modelProgressBlock = document.getElementById("model-progress-block");
const modelProgressBar = document.getElementById("model-progress-bar");
const modelProgressText = document.getElementById("model-progress-text");
const downloadModelButton = document.getElementById("download-model");

const blenderStep = document.getElementById("blender-step");
const blenderStatus = document.getElementById("blender-status");
const blenderHint = document.getElementById("blender-hint");
const blenderProgressBlock = document.getElementById("blender-progress-block");
const blenderProgressBar = document.getElementById("blender-progress-bar");
const blenderProgressText = document.getElementById("blender-progress-text");
const downloadBlenderAddonButton = document.getElementById("download-blender-addon");

const studioStep = document.getElementById("studio-step");
const studioStatus = document.getElementById("studio-status");
const studioHint = document.getElementById("studio-hint");
const openStudioButton = document.getElementById("open-studio");

let currentConfig = null;
let runtimePoller = null;
let modelPoller = null;
let blenderPoller = null;

function setActivity(title, message, detail, badge = "Preparing") {
  activityTitle.textContent = title;
  activityMessage.textContent = message;
  activityDetail.textContent = detail;
  activityBadge.textContent = badge;
}

function formatBytes(value) {
  if (value == null) {
    return "";
  }
  if (value < 1024) {
    return `${value} B`;
  }
  const units = ["KB", "MB", "GB"];
  let size = value / 1024;
  let unit = units[0];
  for (const nextUnit of units) {
    unit = nextUnit;
    if (size < 1024 || nextUnit === units[units.length - 1]) {
      break;
    }
    size /= 1024;
  }
  return `${size.toFixed(size >= 100 ? 0 : 1)} ${unit}`;
}

function setStepState(element, state) {
  element.classList.toggle("is-active", state === "active");
  element.classList.toggle("is-done", state === "done");
  element.classList.toggle("is-locked", state === "locked");
}

function renderTask(task, progressBlock, progressBar, progressText, idleText) {
  progressBar.classList.remove("is-indeterminate");

  if (!task || task.status === "idle") {
    progressBlock.classList.add("is-hidden");
    progressBar.style.width = "0%";
    progressText.textContent = idleText;
    return;
  }

  progressBlock.classList.remove("is-hidden");

  if (task.status === "running") {
    if (task.percent != null) {
      progressBar.style.width = `${task.percent}%`;
      progressText.textContent = task.total_bytes != null
        ? `${task.percent}% · ${formatBytes(task.bytes_downloaded)} / ${formatBytes(task.total_bytes)}`
        : task.detail
          ? `${task.percent}% · ${task.message} ${task.detail}`
          : `${task.percent}% · ${task.message}`;
      return;
    }

    progressBar.style.width = "34%";
    progressBar.classList.add("is-indeterminate");
    progressText.textContent = formatBytes(task.bytes_downloaded)
      ? `${formatBytes(task.bytes_downloaded)} downloaded`
      : "Starting...";
    return;
  }

  progressBar.style.width = task.status === "completed" ? "100%" : "0%";
  if (task.status === "completed") {
    progressText.textContent = task.total_bytes
      ? `${formatBytes(task.total_bytes)} downloaded`
      : "Completed.";
    return;
  }

  progressText.textContent = task.error || task.message || "Failed.";
}

function applyStatus(payload) {
  currentConfig = payload;
  const { sharp, release, blender_addon: blenderAddon } = payload;
  const isComplete = sharp.runtime_ready && sharp.checkpoint_exists;
  const canInstallRuntime = Boolean(release.can_download_runtime);
  const canDownloadBlenderAddon = Boolean(blenderAddon?.available);
  const blenderAddonDownloaded = Boolean(blenderAddon?.downloaded);

  workspacePath.textContent = payload.workspace;
  setupShell?.classList.toggle("is-complete", isComplete);
  wizardPanel?.classList.toggle("is-complete", isComplete);
  heroHint.textContent = !canInstallRuntime
    ? "This build expects an existing local SHARP runtime or a manually bundled runtime folder."
    : release.runtime_install_mode === "windows-local"
      ? "This build installs Python and SHARP locally inside the app folder, then unlocks the studio."
      : "This build installs only the runtime and model pieces needed on this machine.";

  installRuntimeButton.textContent = sharp.runtime_ready
    ? "Runtime Installed"
    : canInstallRuntime
      ? "Install Runtime"
      : "Runtime Not Bundled";
  downloadModelButton.textContent = sharp.checkpoint_exists ? "Model Installed" : "Download Model";
  downloadBlenderAddonButton.textContent = blenderAddonDownloaded ? "Add-on Downloaded" : "Download Add-on";

  installRuntimeButton.disabled = sharp.runtime_ready || !canInstallRuntime;
  downloadModelButton.disabled = !sharp.runtime_ready || sharp.checkpoint_exists;
  downloadBlenderAddonButton.disabled = !canDownloadBlenderAddon || blenderAddonDownloaded;
  openStudioButton.disabled = !sharp.runtime_ready;

  runtimeStatus.textContent = sharp.runtime_ready ? "Installed" : "Required";
  runtimeHint.textContent = sharp.runtime_ready
    ? `Runtime ready at ${sharp.executable}.`
    : !canInstallRuntime
      ? "No runtime installer is bundled with this build. Add runtime/run-sharp here or point the config at an existing SHARP install."
      : release.runtime_install_mode === "windows-local"
        ? "The app will download Python, install SHARP locally, and validate the runtime here."
        : "Install the runtime into this app folder before continuing.";

  modelStatus.textContent = sharp.checkpoint_exists ? "Installed" : sharp.runtime_ready ? "Optional" : "Waiting";
  modelHint.textContent = sharp.checkpoint_exists
    ? `Model ready at ${sharp.checkpoint}.`
    : sharp.runtime_ready
      ? (sharp.preferred_checkpoint
          ? `The Apple model will be saved to ${sharp.preferred_checkpoint}.`
          : "The Apple model can be downloaded after runtime install.")
      : "Install the runtime first, then this step becomes available.";

  blenderStatus.textContent = blenderAddonDownloaded ? "Downloaded" : canDownloadBlenderAddon ? "Optional" : "Unavailable";
  blenderHint.textContent = blenderAddonDownloaded
    ? `Add-on zip ready at ${blenderAddon.path}. Install it from Blender Preferences when you need Blender import.`
    : canDownloadBlenderAddon
      ? `Download the Blender add-on zip into ${blenderAddon.folder}.`
      : "This build does not declare a Blender add-on download for this platform.";

  studioStatus.textContent = sharp.runtime_ready ? "Ready" : "Locked";
  studioHint.textContent = sharp.runtime_ready
    ? sharp.checkpoint_exists
      ? "Everything is installed. Open the studio and run SHARP."
      : "The studio is ready now. You can also download the model first if you want."
    : "The studio unlocks as soon as the runtime install completes.";

  setStepState(runtimeStep, sharp.runtime_ready ? "done" : "active");
  setStepState(modelStep, !sharp.runtime_ready ? "locked" : sharp.checkpoint_exists ? "done" : "active");
  setStepState(blenderStep, blenderAddonDownloaded ? "done" : canDownloadBlenderAddon ? "active" : "locked");
  setStepState(studioStep, !sharp.runtime_ready ? "locked" : "active");

  if (!sharp.runtime_ready) {
    setActivity(
      canInstallRuntime ? "Install the runtime" : "Runtime not found",
      canInstallRuntime
        ? "Start with Step 1. The app will prepare this machine for local SHARP runs."
        : "This build cannot install SHARP for you. Add a bundled runtime or point the config at an existing SHARP install first.",
      canInstallRuntime
        ? (release.runtime_install_mode === "windows-local"
            ? "On Windows Lite this includes local Python setup, SHARP install, and validation before the studio opens."
            : "The runtime will be downloaded into the app folder so the initial build stays smaller.")
        : "After the runtime exists, refresh this page and the studio will unlock automatically.",
      "Step 1",
    );
    return;
  }

  if (!sharp.checkpoint_exists) {
    setActivity(
      "Runtime ready",
      "Step 1 is complete. You can open the studio now or install the Apple model first.",
      "The model step is optional, but installing it now avoids a first-run download later.",
      "Step 2",
    );
    return;
  }

  setActivity(
    "Setup complete",
    blenderAddonDownloaded
      ? "Everything needed for local runs is installed on this machine, and the Blender add-on zip is ready."
      : "Everything needed for local runs is installed on this machine.",
    blenderAddonDownloaded
      ? "Open the studio, or install the downloaded zip from Blender Preferences when you want to use Blender."
      : "Open the studio and start a new SHARP run. You can always come back here later if you want the Blender add-on.",
    "Ready",
  );
}

async function refreshStatus() {
  const response = await fetch("/api/config");
  if (!response.ok) {
    throw new Error("Could not load setup status.");
  }
  const payload = await response.json();
  applyStatus(payload);
}

async function fetchTask(kind) {
  const response = await fetch(`/api/setup/downloads/${kind}`);
  if (!response.ok) {
    throw new Error(`Could not load ${kind} download progress.`);
  }
  return response.json();
}

async function refreshTask(kind) {
  const payload = await fetchTask(kind);
  if (payload.sharp && payload.release && currentConfig) {
    applyStatus({
      ...currentConfig,
      sharp: payload.sharp,
      release: payload.release,
      blender_addon: payload.blender_addon || currentConfig.blender_addon,
    });
  }

  if (kind === "runtime") {
    renderTask(payload.task, runtimeProgressBlock, runtimeProgressBar, runtimeProgressText, "No runtime install in progress.");
  } else if (kind === "model") {
    renderTask(payload.task, modelProgressBlock, modelProgressBar, modelProgressText, "No model download in progress.");
  } else {
    renderTask(payload.task, blenderProgressBlock, blenderProgressBar, blenderProgressText, "No Blender add-on download in progress.");
  }

  return payload.task;
}

function stopPolling(kind) {
  if (kind === "runtime" && runtimePoller) {
    clearInterval(runtimePoller);
    runtimePoller = null;
  }
  if (kind === "model" && modelPoller) {
    clearInterval(modelPoller);
    modelPoller = null;
  }
  if (kind === "blender-addon" && blenderPoller) {
    clearInterval(blenderPoller);
    blenderPoller = null;
  }
}

function startPolling(kind) {
  stopPolling(kind);

  if (kind === "runtime") {
    installRuntimeButton.disabled = true;
    setStepState(runtimeStep, "active");
  } else if (kind === "model") {
    downloadModelButton.disabled = true;
    setStepState(modelStep, "active");
  } else {
    downloadBlenderAddonButton.disabled = true;
    setStepState(blenderStep, "active");
  }

  const runner = async () => {
    try {
      const task = await refreshTask(kind);
      if (task.status !== "running") {
        stopPolling(kind);
        await refreshStatus();

        if (kind === "runtime" && task.status === "completed") {
          setActivity(
            "Runtime installed",
            `Step 1 finished. Runtime installed to ${task.result_path}.`,
            "Continue to the optional model step or open the studio now.",
            "Step 1",
          );
        } else if (kind === "model" && task.status === "completed") {
          setActivity(
            "Model installed",
            `Step 2 finished. Model saved to ${task.result_path}.`,
            "The studio can now run without waiting for a first-run model fetch.",
            "Step 2",
          );
        } else if (kind === "blender-addon" && task.status === "completed") {
          setActivity(
            "Blender add-on downloaded",
            `Step 3 finished. Add-on saved to ${task.result_path}.`,
            "Install this zip from Blender Preferences when you want Blender to read the same Sharp Lab workspace.",
            "Step 3",
          );
        } else if (task.status === "failed") {
          const isRuntime = kind === "runtime";
          const isBlender = kind === "blender-addon";
          setActivity(
            isRuntime ? "Runtime install failed" : isBlender ? "Blender add-on download failed" : "Model download failed",
            task.error || task.message,
            isRuntime
              ? "Retry Step 1 after checking the network and local folder permissions."
              : isBlender
                ? "Retry Step 3 after checking the network and local folder permissions."
                : "Retry Step 2, or place the model manually into the runtime models folder.",
            isRuntime ? "Step 1" : isBlender ? "Step 3" : "Step 2",
          );
        }
      } else if (kind === "runtime") {
        setActivity(
          "Installing runtime",
          task.message,
          task.detail || (
            currentConfig?.release?.runtime_install_mode === "windows-local"
              ? "The app is preparing local Python, installing SHARP, and validating the runtime."
              : "The app is downloading the runtime into this folder."
          ),
          "Step 1",
        );
      } else if (kind === "model") {
        setActivity(
          "Downloading model",
          task.message,
          task.detail || "The Apple SHARP model is being saved into the local runtime folder.",
          "Step 2",
        );
      } else if (kind === "blender-addon") {
        setActivity(
          "Downloading Blender add-on",
          task.message,
          task.detail || "The Blender add-on zip is being saved next to this Sharp Lab app.",
          "Step 3",
        );
      }
    } catch (error) {
      console.error(error);
      stopPolling(kind);
    }
  };

  runner();
  const intervalId = window.setInterval(runner, 700);
  if (kind === "runtime") {
    runtimePoller = intervalId;
  } else if (kind === "model") {
    modelPoller = intervalId;
  } else {
    blenderPoller = intervalId;
  }
}

async function installRuntime() {
  installRuntimeButton.disabled = true;
  setActivity(
    "Installing runtime",
    currentConfig?.release?.runtime_install_mode === "windows-local"
      ? "Preparing Python and SHARP locally for this machine."
      : "Downloading the portable SHARP runtime.",
    "This is the main setup step. The next steps unlock when it finishes.",
    "Step 1",
  );

  try {
    const response = await fetch("/api/setup/install-runtime", { method: "POST" });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.error || "Could not install the runtime.");
    }
    renderTask(payload.task, runtimeProgressBlock, runtimeProgressBar, runtimeProgressText, "No runtime install in progress.");
    startPolling("runtime");
  } catch (error) {
    console.error(error);
    setActivity("Runtime install failed", error.message, "Retry Step 1 after checking the network and local folder permissions.", "Step 1");
  }
}

async function downloadModel() {
  downloadModelButton.disabled = true;
  setActivity(
    "Downloading model",
    "Fetching the Apple SHARP model.",
    "The file will be stored in the local runtime folder for future runs.",
    "Step 2",
  );

  try {
    const response = await fetch("/api/setup/download-checkpoint", { method: "POST" });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.error || "Could not download the Apple model.");
    }
    renderTask(payload.task, modelProgressBlock, modelProgressBar, modelProgressText, "No model download in progress.");
    startPolling("model");
  } catch (error) {
    console.error(error);
    setActivity("Model download failed", error.message, "Retry Step 2, or place the model manually into the runtime models folder.", "Step 2");
  }
}

async function downloadBlenderAddon() {
  downloadBlenderAddonButton.disabled = true;
  setActivity(
    "Downloading Blender add-on",
    "Fetching the Sharp Lab Blender add-on zip.",
    "The file will be stored next to this Sharp Lab app so Blender can use the same workspace.",
    "Step 3",
  );

  try {
    const response = await fetch("/api/setup/download-blender-addon", { method: "POST" });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.error || "Could not download the Blender add-on.");
    }
    renderTask(payload.task, blenderProgressBlock, blenderProgressBar, blenderProgressText, "No Blender add-on download in progress.");
    startPolling("blender-addon");
  } catch (error) {
    console.error(error);
    setActivity("Blender add-on download failed", error.message, "Retry Step 3 after checking the network and local folder permissions.", "Step 3");
  }
}

function openStudio() {
  const path = currentConfig?.release?.studio_path || "/studio";
  window.location.href = path;
}

installRuntimeButton.addEventListener("click", installRuntime);
downloadModelButton.addEventListener("click", downloadModel);
downloadBlenderAddonButton.addEventListener("click", downloadBlenderAddon);
openStudioButton.addEventListener("click", openStudio);

refreshStatus().catch((error) => {
  console.error(error);
  setActivity("Setup unavailable", error.message, "Reload the page after the local app finishes starting.", "Error");
});

Promise.allSettled([refreshTask("runtime"), refreshTask("model"), refreshTask("blender-addon")]).then((results) => {
  const runtimeTask = results[0].status === "fulfilled" ? results[0].value : null;
  const modelTask = results[1].status === "fulfilled" ? results[1].value : null;
  const blenderTask = results[2].status === "fulfilled" ? results[2].value : null;
  if (runtimeTask?.status === "running") {
    startPolling("runtime");
  }
  if (modelTask?.status === "running") {
    startPolling("model");
  }
  if (blenderTask?.status === "running") {
    startPolling("blender-addon");
  }
});
