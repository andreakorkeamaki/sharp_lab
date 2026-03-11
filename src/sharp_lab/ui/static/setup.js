const buildFlavor = document.getElementById("build-flavor");
const buildHint = document.getElementById("build-hint");
const runtimeStatus = document.getElementById("runtime-status");
const runtimeHint = document.getElementById("runtime-hint");
const runtimeProgressBar = document.getElementById("runtime-progress-bar");
const runtimeProgressText = document.getElementById("runtime-progress-text");
const modelStatus = document.getElementById("model-status");
const modelHint = document.getElementById("model-hint");
const modelProgressBar = document.getElementById("model-progress-bar");
const modelProgressText = document.getElementById("model-progress-text");
const workspacePath = document.getElementById("workspace-path");
const activityTitle = document.getElementById("activity-title");
const activityMessage = document.getElementById("activity-message");
const activityDetail = document.getElementById("activity-detail");
const installRuntimeButton = document.getElementById("install-runtime");
const downloadModelButton = document.getElementById("download-model");
const openStudioButton = document.getElementById("open-studio");

let currentConfig = null;
let runtimePoller = null;
let modelPoller = null;

function setActivity(title, message, detail) {
  activityTitle.textContent = title;
  activityMessage.textContent = message;
  activityDetail.textContent = detail;
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

function renderTask(task, progressBar, progressText, idleText) {
  progressBar.classList.remove("is-indeterminate");

  if (!task || task.status === "idle") {
    progressBar.style.width = "0%";
    progressText.textContent = idleText;
    return;
  }

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
      : "Starting download...";
    return;
  }

  progressBar.style.width = task.status === "completed" ? "100%" : "0%";
  if (task.status === "completed") {
    progressText.textContent = task.total_bytes
      ? `${formatBytes(task.total_bytes)} downloaded`
      : "Download completed.";
    return;
  }

  progressText.textContent = task.error || task.message || "Download failed.";
}

function applyStatus(payload) {
  currentConfig = payload;
  const { sharp, release } = payload;

  workspacePath.textContent = payload.workspace;
  buildFlavor.textContent = release.build_flavor === "lite" ? "Lite build" : "Full build";
  buildHint.textContent = release.runtime_install_mode === "windows-local"
    ? "This app bootstraps Python and SHARP locally inside the app folder."
    : release.can_install_runtime
      ? "This app knows where to fetch the portable runtime for this release."
      : "This build has no runtime installer configured.";

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
      release.runtime_install_mode === "windows-local"
        ? "The Lite build will download Python, install SHARP locally, and validate everything before opening the studio."
        : "The Lite build keeps the runtime out of the zip so the first download stays smaller.",
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
    renderTask(payload.task, runtimeProgressBar, runtimeProgressText, "No runtime download in progress.");
  } else {
    renderTask(payload.task, modelProgressBar, modelProgressText, "No model download in progress.");
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
  } else {
    downloadModelButton.disabled = true;
  }
  const runner = async () => {
    try {
      const task = await refreshTask(kind);
      if (task.status !== "running") {
        stopPolling(kind);
        await refreshStatus();
        installRuntimeButton.disabled = !currentConfig?.release?.can_download_runtime;
        downloadModelButton.disabled = !currentConfig?.sharp?.runtime_ready;
        if (kind === "runtime" && task.status === "completed") {
          setActivity("Runtime installed", `Installed the runtime to ${task.result_path}.`, "You can now open the studio or download the model.");
        } else if (kind === "model" && task.status === "completed") {
          setActivity("Model installed", `Saved the Apple model to ${task.result_path}.`, "The studio can now run predictions without waiting for a first-run download.");
        } else if (task.status === "failed") {
          const title = kind === "runtime" ? "Install failed" : "Model download failed";
          const detail = kind === "runtime"
            ? "Check the network or release metadata, then try again."
            : "You can also place the model file in the runtime models folder manually.";
          setActivity(title, task.error || task.message, detail);
        }
      } else if (kind === "runtime") {
        setActivity(
          "Installing runtime",
          task.message,
          currentConfig?.release?.runtime_install_mode === "windows-local"
            ? "The Lite build is preparing a local Python + SHARP runtime inside this app folder."
            : "The Lite build is fetching the portable runtime into this app folder.",
        );
      } else {
        setActivity("Downloading model", task.message, "The Apple SHARP model is being saved into the runtime folder.");
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
    "This can take a while on the Lite build.",
  );

  try {
    const response = await fetch("/api/setup/install-runtime", { method: "POST" });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.error || "Could not install the runtime.");
    }
    renderTask(payload.task, runtimeProgressBar, runtimeProgressText, "No runtime download in progress.");
    startPolling("runtime");
  } catch (error) {
    console.error(error);
    setActivity("Install failed", error.message, "Check the network or release metadata, then try again.");
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
    renderTask(payload.task, modelProgressBar, modelProgressText, "No model download in progress.");
    startPolling("model");
  } catch (error) {
    console.error(error);
    setActivity("Model download failed", error.message, "You can also place the model file in the runtime models folder manually.");
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
