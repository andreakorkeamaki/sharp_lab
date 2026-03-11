const heroHint = document.getElementById("hero-hint");
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

const studioStep = document.getElementById("studio-step");
const studioStatus = document.getElementById("studio-status");
const studioHint = document.getElementById("studio-hint");
const openStudioButton = document.getElementById("open-studio");

let currentConfig = null;
let runtimePoller = null;
let modelPoller = null;

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
  const { sharp, release } = payload;

  workspacePath.textContent = payload.workspace;
  heroHint.textContent = release.runtime_install_mode === "windows-local"
    ? "This build installs Python and SHARP locally inside the app folder, then unlocks the studio."
    : "This build installs only the runtime and model pieces needed on this machine.";

  installRuntimeButton.textContent = sharp.runtime_ready ? "Runtime Installed" : "Install Runtime";
  downloadModelButton.textContent = sharp.checkpoint_exists ? "Model Installed" : "Download Model";

  installRuntimeButton.disabled = sharp.runtime_ready || !release.can_download_runtime;
  downloadModelButton.disabled = !sharp.runtime_ready || sharp.checkpoint_exists;
  openStudioButton.disabled = !sharp.runtime_ready;

  runtimeStatus.textContent = sharp.runtime_ready ? "Installed" : "Required";
  runtimeHint.textContent = sharp.runtime_ready
    ? `Runtime ready at ${sharp.executable}.`
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

  studioStatus.textContent = sharp.runtime_ready ? "Ready" : "Locked";
  studioHint.textContent = sharp.runtime_ready
    ? sharp.checkpoint_exists
      ? "Everything is installed. Open the studio and run SHARP."
      : "The studio is ready now. You can also download the model first if you want."
    : "The studio unlocks as soon as the runtime install completes.";

  setStepState(runtimeStep, sharp.runtime_ready ? "done" : "active");
  setStepState(modelStep, !sharp.runtime_ready ? "locked" : sharp.checkpoint_exists ? "done" : "active");
  setStepState(studioStep, !sharp.runtime_ready ? "locked" : "active");

  if (!sharp.runtime_ready) {
    setActivity(
      "Install the runtime",
      "Start with Step 1. The app will prepare this machine for local SHARP runs.",
      release.runtime_install_mode === "windows-local"
        ? "On Windows Lite this includes local Python setup, SHARP install, and validation before the studio opens."
        : "The runtime will be downloaded into the app folder so the initial build stays smaller.",
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
    "Everything needed for local runs is installed on this machine.",
    "Open the studio and start a new SHARP run.",
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
    });
  }

  if (kind === "runtime") {
    renderTask(payload.task, runtimeProgressBlock, runtimeProgressBar, runtimeProgressText, "No runtime install in progress.");
  } else {
    renderTask(payload.task, modelProgressBlock, modelProgressBar, modelProgressText, "No model download in progress.");
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
}

function startPolling(kind) {
  stopPolling(kind);

  if (kind === "runtime") {
    installRuntimeButton.disabled = true;
    setStepState(runtimeStep, "active");
  } else {
    downloadModelButton.disabled = true;
    setStepState(modelStep, "active");
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
        } else if (task.status === "failed") {
          const isRuntime = kind === "runtime";
          setActivity(
            isRuntime ? "Runtime install failed" : "Model download failed",
            task.error || task.message,
            isRuntime
              ? "Retry Step 1 after checking the network and local folder permissions."
              : "Retry Step 2, or place the model manually into the runtime models folder.",
            isRuntime ? "Step 1" : "Step 2",
          );
        }
      } else if (kind === "runtime") {
        setActivity(
          "Installing runtime",
          task.message,
          currentConfig?.release?.runtime_install_mode === "windows-local"
            ? "The app is preparing local Python, installing SHARP, and validating the runtime."
            : "The app is downloading the runtime into this folder.",
          "Step 1",
        );
      } else {
        setActivity(
          "Downloading model",
          task.message,
          "The Apple SHARP model is being saved into the local runtime folder.",
          "Step 2",
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
  } else {
    modelPoller = intervalId;
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

function openStudio() {
  const path = currentConfig?.release?.studio_path || "/studio";
  window.location.href = path;
}

installRuntimeButton.addEventListener("click", installRuntime);
downloadModelButton.addEventListener("click", downloadModel);
openStudioButton.addEventListener("click", openStudio);

refreshStatus().catch((error) => {
  console.error(error);
  setActivity("Setup unavailable", error.message, "Reload the page after the local app finishes starting.", "Error");
});

Promise.allSettled([refreshTask("runtime"), refreshTask("model")]).then((results) => {
  const runtimeTask = results[0].status === "fulfilled" ? results[0].value : null;
  const modelTask = results[1].status === "fulfilled" ? results[1].value : null;
  if (runtimeTask?.status === "running") {
    startPolling("runtime");
  }
  if (modelTask?.status === "running") {
    startPolling("model");
  }
});
