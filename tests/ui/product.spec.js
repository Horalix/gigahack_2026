import { test, expect } from "@playwright/test";

/** @param {import('@playwright/test').Page} page @param {{ setupRequired?: boolean, failedJob?: boolean }} [options] */
async function installApi(page, { setupRequired = true, failedJob = false } = {}) {
  let needsSetup = setupRequired;
  let patients = setupRequired ? [] : [
    { id: "patient-1", displayName: "Mira Popescu", hospitalReference: "DEMO-001", status: "active", meetings: [] },
    { id: "patient-2", displayName: "Radu Ionescu", hospitalReference: "DEMO-002", status: "active", meetings: [] },
  ];
  /** @type {Record<string, any> | null} */
  let meeting = null;
  let uploaded = false;
  let approved = false;
  let jobState = failedJob ? "failed" : "ready";
  const user = { id: "user-1", username: "doctor", role: "administrator" };
  const segment = { id: "seg-1", startMs: 1000, endMs: 3000, text: "Pacientul va reveni luni.", language: "ro" };
  const decision = {
    id: "decision-1", kind: "action", text: "Pacientul va reveni luni.", status: "confirmed",
    ownerLabel: null, originalDateExpression: "luni",
    taskEvidence: [{ segmentId: "seg-1", quote: segment.text, startMs: 1000, endMs: 3000 }],
  };
  const profiles = [
    { id: "laptop8", hardware: { gpu: "RTX 3070 Ti", vram_gb: 8 }, asrFilesPresent: true, llmFilePresent: true, compatible: true },
    { id: "hospital16", hardware: { gpu: "RTX 5080", vram_gb: 16 }, asrFilesPresent: true, llmFilePresent: true, compatible: false },
    { id: "cpu", hardware: { gpu: null, vram_gb: 0 }, asrFilesPresent: true, llmFilePresent: true, compatible: true },
  ];
  const detail = () => ({
    meeting: { ...meeting, status: uploaded ? "transcript_ready" : "created", transcriptRevision: uploaded ? 1 : 0 },
    permission: "owner", asset: uploaded ? { durationMs: 60_000 } : null,
    segments: uploaded ? [segment] : [],
    latestJob: uploaded ? { id: "job-1", state: jobState, stage: jobState === "failed" ? "extract" : "complete", errorCode: jobState === "failed" ? "LLM_INVALID_EVIDENCE" : null } : null,
    decisions: uploaded && jobState === "ready" ? { items: [decision], requiresHumanReview: true } : null,
    canUndoCorrection: false, captures: [],
    artifact: approved ? { id: "artifact-1", sha256: "abc123", approvedAt: new Date().toISOString(), storageKey: "artifact.html" } : null,
  });
  await page.route("**/api/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname.replace(/^\/api/, "");
    const method = request.method();
    /** @param {unknown} body @param {number} [status] */
    const json = (body, status = 200) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });

    if (path === "/health") return json({ setupRequired: needsSetup });
    if (path === "/auth/setup" && method === "POST") { needsSetup = false; return json({ user }); }
    if (path === "/auth/login" && method === "POST") return json({ user });
    if (path === "/auth/me") return json({ user });
    if (path === "/auth/logout" && method === "POST") return json({ ok: true });
    if (path === "/profiles") return json({ profiles, defaultProfileId: "laptop8" });
    if (path === "/meetings" && method === "GET") return json({ meetings: meeting ? [meeting] : [], total: meeting ? 1 : 0 });
    if (path === "/meetings" && method === "POST") {
      const body = JSON.parse(request.postData() || "{}");
      meeting = { id: "meeting-1", title: body.title, recordedAt: body.recordedAt, status: "created", outputLanguage: body.outputLanguage, transcriptRevision: 0 };
      return json(meeting, 201);
    }
    if (path === "/patients" && method === "GET") {
      const q = (url.searchParams.get("q") || "").toLowerCase();
      const matches = patients.filter((item) => !q || item.displayName.toLowerCase().includes(q) || (item.hospitalReference || "").toLowerCase().includes(q));
      const hasCursor = url.searchParams.has("cursor");
      const results = hasCursor ? matches.slice(1) : matches.slice(0, 1);
      const hasMore = !hasCursor && matches.length > 1;
      return json({ patients: results, total: matches.length, nextCursor: hasMore ? "page-2" : null, hasMore });
    }
    if (path === "/patients" && method === "POST") {
      const body = JSON.parse(request.postData() || "{}");
      const patient = { id: "patient-1", displayName: body.displayName, hospitalReference: body.hospitalReference, status: "active", meetings: [] };
      patients = [patient];
      return json({ patient }, 201);
    }
    if (path.startsWith("/meetings/meeting-1") && path.endsWith("/audio") && method === "POST") {
      uploaded = true;
      return json({ id: "asset-1" }, 201);
    }
    if (path === "/meetings/meeting-1/jobs" && method === "POST") return json({ id: "job-1" }, 202);
    if (path === "/jobs/job-1/retry" && method === "POST") { jobState = "ready"; return json({ id: "job-1", state: "queued", stage: "extract" }, 202); }
    if (path === "/jobs/job-1") return json({ id: "job-1", state: jobState, stage: jobState === "failed" ? "extract" : "complete", errorCode: jobState === "failed" ? "LLM_INVALID_EVIDENCE" : null, progressMs: 60_000 });
    if (path === "/meetings/meeting-1" && method === "GET") return json(detail());
    if (path === "/meetings/meeting-1/artifacts" && method === "POST") { approved = true; return json({ artifact: { id: "artifact-1" } }, 201); }
    if (path === "/artifacts/artifact-1/content") return route.fulfill({ status: 200, contentType: "text/html", body: "<!doctype html><title>Approved Notavra minutes</title>" });
    return json({ code: "UNEXPECTED_FIXTURE_ROUTE", message: `${method} ${path}` }, 500);
  });
}

/** @param {{ page: import('@playwright/test').Page }} fixtures */
test("doctor can upload, review and approve a local transcript", async ({ page }) => {
  await installApi(page);
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Set up your local workspace" })).toBeVisible();
  await page.getByLabel("Username").fill("doctor");
  await page.getByLabel("Password").fill("correct horse battery staple");
  await page.getByRole("button", { name: "Create administrator" }).click();

  await expect(page.getByRole("heading", { name: "Clinical meetings, ready to review" })).toBeVisible();
  await page.getByRole("button", { name: "Patients", exact: true }).click();
  await page.getByLabel("Name").fill("Mira Popescu");
  await page.getByLabel("Hospital reference").fill("DEMO-001");
  await page.getByRole("button", { name: "Save patient" }).click();
  await expect(page.getByRole("heading", { name: "Mira Popescu" })).toBeVisible();

  await page.getByRole("button", { name: "Meetings", exact: true }).click();
  await page.getByLabel("Meeting title").fill("Romanian consultation");
  await page.getByRole("button", { name: "Create meeting" }).click();
  await expect(page.getByRole("heading", { name: "Romanian consultation" })).toBeVisible();
  await page.locator('input[name="audio"]').setInputFiles({ name: "sample.wav", mimeType: "audio/wav", buffer: Buffer.from("sample") });
  await page.getByRole("button", { name: "Transcribe recording" }).click();

  await expect(page.getByText("Transcript and decisions are ready for review.")).toBeVisible({ timeout: 10_000 });
  await expect(page.getByText("Pacientul va reveni luni.").first()).toBeVisible();
  await expect(page.getByRole("heading", { name: /Decisions and actions/ })).toBeVisible();
  await page.locator(".audio-review").evaluate((element) => {
    const audio = /** @type {HTMLAudioElement} */ (element);
    Object.defineProperty(audio, "currentTime", { configurable: true, writable: true, value: 0 });
    audio.play = () => { audio.dataset.played = "true"; return Promise.resolve(); };
  });
  await page.getByRole("button", { name: "Play audio from 00:00:01" }).click();
  await expect(page.locator(".audio-review")).toHaveAttribute("data-played", "true");
  await expect.poll(() => page.locator(".audio-review").evaluate((element) => /** @type {HTMLAudioElement} */ (element).currentTime)).toBe(1);
  const approve = page.getByRole("button", { name: "Approve and download HTML minutes" });
  await expect(approve).toBeDisabled();
  await page.getByRole("checkbox", { name: /I reviewed the transcript/ }).check();
  const download = page.waitForEvent("download");
  await approve.click();
  await expect((await download).suggestedFilename()).toMatch(/^notavra-minutes-.*\.html$/);
  await expect(page.getByText(/Current approved file/)).toBeVisible();
});

/** @param {{ page: import('@playwright/test').Page }} fixtures */
test("existing doctor can search and page through the patient directory", async ({ page }) => {
  await installApi(page, { setupRequired: false });
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Clinical meetings, ready to review" })).toBeVisible();
  await page.getByRole("button", { name: "Patients", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Patient directory" })).toBeVisible();
  await expect(page.getByText("Mira Popescu")).toBeVisible();
  await page.getByRole("button", { name: "Show more" }).click();
  await expect(page.getByText("Radu Ionescu")).toBeVisible();
  await page.getByLabel("Search patients").fill("Mira");
  await expect(page.getByText("Mira Popescu")).toBeVisible();
  await expect(page.getByText("Radu Ionescu")).toHaveCount(0);
});

/** @param {{ page: import('@playwright/test').Page }} fixtures */
test("doctor can retry a failed local extraction from the meeting", async ({ page }) => {
  await installApi(page, { failedJob: true });
  await page.goto("/");
  await page.getByLabel("Username").fill("doctor");
  await page.getByLabel("Password").fill("correct horse battery staple");
  await page.getByRole("button", { name: "Create administrator" }).click();
  await page.getByLabel("Meeting title").fill("Retry extraction");
  await page.getByRole("button", { name: "Create meeting" }).click();
  await page.locator('input[name="audio"]').setInputFiles({ name: "sample.wav", mimeType: "audio/wav", buffer: Buffer.from("sample") });
  await page.getByRole("button", { name: "Transcribe recording" }).click();
  await expect(page.getByText(/Processing failed:/)).toBeVisible({ timeout: 10_000 });
  const retry = page.getByRole("button", { name: "Retry failed step" });
  await expect(retry).toBeVisible();
  await retry.click();
  await expect(page.getByText("Transcript and decisions are ready for review.")).toBeVisible({ timeout: 10_000 });
  await expect(page.getByText("Pacientul va reveni luni.").first()).toBeVisible();
});
