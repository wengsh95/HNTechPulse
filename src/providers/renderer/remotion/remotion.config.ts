import { Config } from "@remotion/cli/config";
import { existsSync } from "node:fs";

Config.setEntryPoint("src/index.ts");
Config.setCachingEnabled(false);

// Use local Chrome instead of downloading Chrome Headless Shell
const browserCandidates = [
  process.env.CHROME_PATH,
  process.env.BROWSER_EXECUTABLE,
  "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
  "C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe",
  "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
  "C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe",
  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
  "/usr/bin/google-chrome",
  "/usr/bin/google-chrome-stable",
  "/usr/bin/chromium-browser",
  "/usr/bin/chromium",
].filter(Boolean) as string[];

const found = browserCandidates.find((p) => existsSync(p));
if (found) {
  Config.setBrowserExecutable(found);
  console.log(`Using browser: ${found}`);
} else {
  console.warn("No local Chrome/Chromium found — Remotion will download Chrome Headless Shell");
}
