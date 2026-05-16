const addonSummary = document.getElementById("addon-summary");
const addonFile = document.getElementById("addon-file");
const addonStatus = document.getElementById("addon-status");
const addonDownloadLink = document.getElementById("addon-download-link");
const installLocation = document.getElementById("install-location");
const addonNote = document.getElementById("addon-note");

function filenameFromUrl(url) {
  try {
    const parsed = new URL(url);
    const parts = parsed.pathname.split("/").filter(Boolean);
    return decodeURIComponent(parts[parts.length - 1] || "sharp-lab-blender-addon.zip");
  } catch {
    return "sharp-lab-blender-addon.zip";
  }
}

async function loadAddonDownload() {
  const response = await fetch("/api/config");
  if (!response.ok) {
    throw new Error("Could not load the add-on download link.");
  }

  const payload = await response.json();
  const addon = payload.blender_addon;
  const url = addon?.url;
  if (!url) {
    addonStatus.textContent = "Unavailable";
    addonSummary.textContent = "This build does not declare a Blender add-on zip for this platform.";
    addonFile.textContent = payload.workspace || "-";
    addonDownloadLink.hidden = true;
    return;
  }

  const filename = filenameFromUrl(url);
  addonStatus.textContent = addon.downloaded ? "Downloaded" : "Available";
  addonSummary.textContent = "Download the Sharp Lab Blender add-on zip, then install it manually in Blender.";
  addonFile.textContent = filename;
  addonDownloadLink.href = url;
  addonDownloadLink.setAttribute("download", filename);
  installLocation.textContent = `Select ${filename} from your browser downloads, then enable the Sharp Lab add-on.`;

  if (addon.downloaded && addon.path) {
    addonNote.textContent = `A copy already exists at ${addon.path}. You can install that file or download a fresh copy here.`;
  }
}

loadAddonDownload().catch((error) => {
  console.error(error);
  addonStatus.textContent = "Error";
  addonSummary.textContent = error.message;
  addonDownloadLink.hidden = true;
});
