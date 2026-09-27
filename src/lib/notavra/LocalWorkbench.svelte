<script lang="ts">
  import { onDestroy, onMount } from "svelte";

  type User = { id: string; username: string; role: string };
  type Meeting = { id: string; title: string; recordedAt: string; status: string; outputLanguage: string; transcriptRevision: number };
  type Segment = { id: string; startMs: number; endMs: number; text: string; language: string };
  type Profile = { id: string; hardware: { gpu: string; vram_gb: number }; asrFilesPresent: boolean; llmFilePresent: boolean };
  type Detail = { meeting: Meeting; asset: { durationMs: number; decodeWarning?: string } | null; segments: Segment[]; decisions: any };

  let user = $state<User | null>(null);
  let setupRequired = $state(false);
  let username = $state("");
  let password = $state("");
  let error = $state("");
  let meetings = $state<Meeting[]>([]);
  let total = $state(0);
  let query = $state("");
  let offset = $state(0);
  let detail = $state<Detail | null>(null);
  let profiles = $state<Profile[]>([]);
  let profileId = $state("laptop8");
  let language = $state("ro");
  let busy = $state(false);
  let status = $state("");
  let editingSegment = $state<string | null>(null);
  let editText = $state("");
  let progressTimer: ReturnType<typeof setInterval> | undefined;
  let searchTimer: ReturnType<typeof setTimeout> | undefined;

  async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
    const response = await fetch(`/api${path}`, {
      credentials: "same-origin",
      ...options,
      headers: { ...(options.body instanceof FormData ? {} : { "Content-Type": "application/json" }), ...options.headers },
    });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(body.message || body.code || `Request failed (${response.status})`);
    return body as T;
  }

  async function initialize() {
    try {
      const health = await request<{ setupRequired: boolean }>("/health");
      setupRequired = health.setupRequired;
      if (!setupRequired) {
        const me = await request<{ user: User }>("/auth/me");
        user = me.user;
        await Promise.all([loadMeetings(), loadProfiles()]);
      }
    } catch (e) {
      error = e instanceof Error ? e.message : "Local service is unavailable";
    }
  }

  async function authenticate(event: SubmitEvent) {
    event.preventDefault();
    error = "";
    try {
      const path = setupRequired ? "/auth/setup" : "/auth/login";
      const result = await request<{ user: User }>(path, { method: "POST", body: JSON.stringify({ username, password }) });
      user = result.user;
      setupRequired = false;
      password = "";
      await Promise.all([loadMeetings(), loadProfiles()]);
    } catch (e) { error = e instanceof Error ? e.message : "Sign in failed"; }
  }

  async function loadMeetings() {
    const result = await request<{ meetings: Meeting[]; total: number }>(`/meetings?q=${encodeURIComponent(query)}&limit=10&offset=${offset}`);
    meetings = result.meetings;
    total = result.total;
  }

  async function loadProfiles() {
    const result = await request<{ profiles: Profile[] }>("/profiles");
    profiles = result.profiles;
  }

  async function openMeeting(id: string) {
    stopPolling();
    detail = await request<Detail>(`/meetings/${id}`);
    editingSegment = null;
    error = "";
  }

  async function saveSegment(segment: Segment) {
    if (!detail) return;
    try {
      await request(`/meetings/${detail.meeting.id}/segments/${segment.id}`, {
        method: "PUT", body: JSON.stringify({ transcriptRevision: detail.meeting.transcriptRevision, text: editText }),
      });
      await openMeeting(detail.meeting.id);
      status = "Transcript correction saved. Recheck extracted actions before approval.";
    } catch (e) { showError(e); }
  }

  async function createMeeting(event: SubmitEvent) {
    event.preventDefault();
    const form = new FormData(event.currentTarget as HTMLFormElement);
    busy = true; error = "";
    try {
      const meeting = await request<Meeting>("/meetings", { method: "POST", body: JSON.stringify({
        contractVersion: "1.0", title: String(form.get("title")),
        recordedAt: new Date().toISOString(), timeZone: Intl.DateTimeFormat().resolvedOptions().timeZone,
        outputLanguage: language === "auto" ? "ro" : language, patientLinkIds: [], meetingType: "Clinical consultation",
      }) });
      await loadMeetings(); await openMeeting(meeting.id);
    } catch (e) { error = e instanceof Error ? e.message : "Could not create meeting"; }
    finally { busy = false; }
  }

  async function upload(event: SubmitEvent) {
    event.preventDefault();
    if (!detail) return;
    const form = new FormData(event.currentTarget as HTMLFormElement);
    const file = form.get("audio");
    if (!(file instanceof File) || !file.size) { error = "Choose an audio or video file first."; return; }
    busy = true; error = ""; status = "Uploading and preparing audio…";
    try {
      const payload = new FormData(); payload.set("file", file);
      const asset = await request<{ id: string }>(`/meetings/${detail.meeting.id}/audio`, { method: "POST", body: payload });
      status = "Starting local transcription and decision extraction…";
      const job = await request<{ id: string }>(`/meetings/${detail.meeting.id}/jobs`, {
        method: "POST", body: JSON.stringify({ profileId, language }),
      });
      void asset;
      watchJob(job.id);
    } catch (e) { error = e instanceof Error ? e.message : "Processing could not start"; status = ""; busy = false; }
  }

  function watchJob(jobId: string) {
    stopPolling();
    progressTimer = setInterval(async () => {
      try {
        const job = await request<{ state: string; stage: string; errorCode?: string; progressMs?: number }>(`/jobs/${jobId}`);
        status = job.state === "ready" ? "Transcript and decisions are ready for review." : job.state === "failed" ? `Processing failed: ${job.errorCode || "unknown error"}` : `${job.stage}: ${job.state}…`;
        if (job.state === "ready" || job.state === "failed") {
          stopPolling(); busy = false;
          if (job.state === "ready" && detail) await openMeeting(detail.meeting.id);
          await loadMeetings();
        }
      } catch (e) { status = e instanceof Error ? e.message : "Lost connection to the local service"; stopPolling(); busy = false; }
    }, 1800);
  }

  function stopPolling() { if (progressTimer) clearInterval(progressTimer); progressTimer = undefined; }
  function searchChanged() { offset = 0; if (searchTimer) clearTimeout(searchTimer); searchTimer = setTimeout(() => void loadMeetings().catch(showError), 250); }
  function showError(e: unknown) { error = e instanceof Error ? e.message : "Request failed"; }
  function formatTime(ms: number) { return new Date(ms).toISOString().slice(11, 19); }
  async function logout() { await request("/auth/logout", { method: "POST" }); user = null; detail = null; await initialize(); }

  onMount(() => { void initialize(); });
  onDestroy(() => { stopPolling(); if (searchTimer) clearTimeout(searchTimer); });
</script>

<svelte:head><title>Notavra · Clinical workspace</title></svelte:head>

{#if !user}
  <main class="auth-shell">
    <form class="auth-card" onsubmit={authenticate}>
      <img src="/brand/lockup.png" alt="Notavra" />
      <h1>{setupRequired ? "Set up your local workspace" : "Sign in to Notavra"}</h1>
      <p>Audio and transcripts stay on this computer.</p>
      <label>Username<input bind:value={username} required minlength="3" autocomplete="username" /></label>
      <label>Password<input bind:value={password} type="password" required minlength={setupRequired ? 12 : 1} autocomplete={setupRequired ? "new-password" : "current-password"} /></label>
      {#if setupRequired}<small>First account becomes the local administrator. Use at least 12 characters.</small>{/if}
      {#if error}<p class="error" role="alert">{error}</p>{/if}
      <button class="primary" disabled={!username || !password}>{setupRequired ? "Create administrator" : "Sign in"}</button>
    </form>
  </main>
{:else}
  <main class="workspace">
    <header><div><img src="/brand/symbol.svg" alt="" /><span><b>Notavra</b><small>LOCAL CLINICAL WORKSPACE</small></span></div><span>{user.username} · {user.role}</span><button class="quiet" onclick={logout}>Sign out</button></header>
    {#if error}<p class="error" role="alert">{error}</p>{/if}
    <div class="columns">
      <aside>
        <div class="panel-head"><h2>Meetings</h2><button class="quiet" onclick={() => { detail = null; }}>New</button></div>
        <input aria-label="Search meetings" placeholder="Search meetings" bind:value={query} oninput={searchChanged} />
        <ul class="meeting-list">{#each meetings as item (item.id)}<li><button class:chosen={detail?.meeting.id === item.id} onclick={() => openMeeting(item.id).catch(showError)}><b>{item.title}</b><small>{new Date(item.recordedAt).toLocaleString()} · {item.status}</small></button></li>{/each}</ul>
        <div class="pager"><button disabled={offset === 0} onclick={() => { offset = Math.max(0, offset - 10); loadMeetings().catch(showError); }}>←</button><span>{total ? offset + 1 : 0}–{Math.min(offset + 10, total)} of {total}</span><button disabled={offset + 10 >= total} onclick={() => { offset += 10; loadMeetings().catch(showError); }}>→</button></div>
        {#if !detail}<form class="new-meeting" onsubmit={createMeeting}><h3>Start a meeting</h3><label>Meeting title<input name="title" required maxlength="240" placeholder="Patient consultation" /></label><label>Transcript language<select bind:value={language}><option value="ro">Romanian</option><option value="ru">Russian</option><option value="en">English</option><option value="auto">Auto-detect</option></select></label><button class="primary" disabled={busy}>Create meeting</button></form>{/if}
      </aside>
      <section class="content">
        {#if detail}
          <div class="panel-head"><div><p class="eyebrow">{new Date(detail.meeting.recordedAt).toLocaleString()}</p><h1>{detail.meeting.title}</h1></div><button class="quiet" onclick={() => (detail = null)}>← Meetings</button></div>
          {#if detail.asset}<p class="muted">Audio length: {(detail.asset.durationMs / 60000).toFixed(1)} min {#if detail.asset.decodeWarning}<span class="warning">· Audio decode warning</span>{/if}</p>{/if}
          <section class="panel"><h2>Add recording</h2><p>Upload audio or video for local transcription and meeting action extraction.</p><form class="upload-form" onsubmit={upload}>
            <label class="file-input">Recording file<input name="audio" type="file" accept="audio/*,video/*,.m4a,.mp3,.wav,.mp4,.mov,.webm" required /></label>
            <label>Hardware profile<select bind:value={profileId}>{#each profiles as p (p.id)}<option value={p.id}>{p.id === "laptop8" ? "Laptop · RTX 3070 Ti · 8 GB" : p.id === "hospital16" ? "Workstation · RTX 5080 · 16 GB" : p.id} {p.asrFilesPresent && p.llmFilePresent ? "· ready" : "· models missing"}</option>{/each}</select></label>
            <label>ASR language<select bind:value={language}><option value="ro">Romanian</option><option value="ru">Russian</option><option value="en">English</option><option value="auto">Auto-detect</option></select></label>
            <button class="primary" disabled={busy || !profiles.find((p) => p.id === profileId)?.asrFilesPresent || !profiles.find((p) => p.id === profileId)?.llmFilePresent}>{busy ? "Processing…" : "Transcribe recording"}</button>
          </form>{#if status}<p role="status" class="status">{status}</p>{/if}</section>
          {#if detail.segments.length}<section class="panel"><h2>Transcript <span>{detail.segments.length} passages · click edit to correct</span></h2><div class="transcript">{#each detail.segments as segment (segment.id)}<p><time>{formatTime(segment.startMs)}</time>{#if editingSegment === segment.id}<span class="edit-cell"><textarea bind:value={editText} rows="2"></textarea><button class="primary" onclick={() => saveSegment(segment)}>Save correction</button><button class="quiet" onclick={() => (editingSegment = null)}>Cancel</button></span>{:else}<span>{segment.text}</span>{#if user.role !== "reviewer"}<button class="edit-button" onclick={() => { editingSegment = segment.id; editText = segment.text; }}>Edit</button>{/if}{/if}<small>{segment.language}</small></p>{/each}</div></section>{/if}
          {#if detail.decisions}<section class="panel"><h2>Decisions and actions · review required</h2><pre>{JSON.stringify(detail.decisions, null, 2)}</pre></section>{/if}
          {#if !detail.segments.length}<div class="empty"><span>01</span><h2>Upload the recording</h2><p>Notavra processes the audio locally, then shows the transcript and evidence-backed actions here.</p></div>{/if}
        {:else}<div class="empty"><span>01</span><h1>Clinical meetings, ready to review</h1><p>Choose a meeting, or start one and upload its audio. Transcription and action extraction run locally on the selected profile.</p></div>{/if}
      </section>
    </div>
    <footer>Local inference · No runtime cloud calls · Verify every transcript and action before clinical use</footer>
  </main>
{/if}

<style>
  :global(body){margin:0;background:#f4f6f8;color:#17212b;font:15px/1.5 "Noto Sans",system-ui,sans-serif} :global(button),:global(input),:global(select){font:inherit} :global(button){cursor:pointer}
  .auth-shell{min-height:100vh;display:grid;place-items:center}.auth-card{display:grid;gap:16px;background:white;border:1px solid #e0e6ec;border-radius:18px;padding:36px;width:min(420px,calc(100vw - 48px));box-shadow:0 18px 60px #182d4212}.auth-card img{width:166px}.auth-card h1,.auth-card p{margin:0}.auth-card>p,.muted{color:#667583}.auth-card label,.new-meeting label,.upload-form label{display:grid;gap:6px;font-weight:600}.auth-card input,.new-meeting input,.workspace input,.workspace select{box-sizing:border-box;width:100%;border:1px solid #d7e0e7;border-radius:9px;background:#fff;padding:10px 12px;color:#17212b}.primary{border:0;border-radius:9px;background:#126a62;color:white;font-weight:700;padding:11px 16px}.primary:disabled{opacity:.5;cursor:not-allowed}.error{margin:16px;padding:12px 14px;border-radius:8px;background:#ffeded;color:#a12b2b}
  .workspace{max-width:1440px;margin:auto;padding:22px 32px;min-height:100vh;box-sizing:border-box;display:grid;grid-template-rows:auto 1fr auto;gap:20px}.workspace header{display:flex;align-items:center;gap:16px;border-bottom:1px solid #dfe5e9;padding-bottom:16px}.workspace header>div{display:flex;align-items:center;gap:10px;margin-right:auto}.workspace header img{width:34px;height:36px}.workspace header span{display:grid}.workspace header small{font-size:10px;letter-spacing:.1em;color:#71808b}.quiet{background:white;border:1px solid #d9e0e5;border-radius:8px;padding:8px 12px;color:#37505d}.columns{display:grid;grid-template-columns:330px minmax(0,1fr);gap:22px;min-height:0}.columns aside,.content{min-width:0}.columns aside{border-right:1px solid #dfe5e9;padding-right:20px}.panel-head{display:flex;align-items:center;justify-content:space-between;gap:12px}.panel-head h1,.panel-head h2{margin:0}.meeting-list{list-style:none;padding:0;margin:12px 0}.meeting-list button{width:100%;display:grid;text-align:left;border:0;border-radius:8px;background:transparent;padding:12px;color:inherit;gap:4px}.meeting-list button:hover,.meeting-list button.chosen{background:#e7f2f0}.meeting-list small,.muted,.eyebrow{color:#71808b}.pager{display:flex;justify-content:space-between;align-items:center;color:#6c7a85;font-size:13px}.pager button{border:1px solid #d9e0e5;border-radius:6px;background:white;padding:5px 10px}.pager button:disabled{opacity:.4}.new-meeting{display:grid;gap:12px;border-top:1px solid #dfe5e9;margin-top:18px;padding-top:18px}.new-meeting h3{margin:0}.content{display:grid;align-content:start;gap:16px}.eyebrow{margin:0 0 3px;font-size:13px}.panel{background:white;border:1px solid #e1e6ea;border-radius:12px;padding:18px 20px}.panel h2{font-size:18px;margin:0 0 8px}.panel h2 span{font-size:12px;font-weight:400;color:#71808b;margin-left:8px}.panel>p{margin:0 0 14px;color:#687985}.upload-form{display:grid;grid-template-columns:minmax(180px,1fr) 220px 155px auto;align-items:end;gap:12px}.upload-form input[type=file]{padding:8px}.upload-form label{font-size:13px}.status{color:#17675f;margin:14px 0 0}.transcript{max-height:55vh;overflow:auto}.transcript p{display:grid;grid-template-columns:76px 1fr 35px;gap:12px;border-bottom:1px solid #eef1f3;padding:10px 0;margin:0}.transcript time,.transcript small{color:#82909a;font-size:12px}.warning{color:#9a6512}.panel pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f5f7f8;border-radius:8px;padding:12px;max-height:260px;overflow:auto}.empty{align-self:center;justify-self:center;max-width:560px;text-align:center;padding:56px 20px}.empty>span{display:inline-grid;place-items:center;background:#dcefea;color:#14655c;border-radius:50%;width:42px;height:42px;font-weight:800}.empty p{color:#6e7d87}.workspace footer{text-align:center;color:#81909a;font-size:12px;border-top:1px solid #dfe5e9;padding-top:12px}
  .transcript p{grid-template-columns:76px 1fr 52px 35px}.edit-button{border:0;background:transparent;color:#17675f;font-size:12px}.edit-cell{display:grid;grid-template-columns:1fr auto auto;gap:8px}.edit-cell textarea{width:100%;box-sizing:border-box;border:1px solid #d7e0e7;border-radius:6px;padding:8px;font:inherit}
  @media(max-width:900px){.columns{grid-template-columns:1fr}.columns aside{border:0;padding:0}.upload-form{grid-template-columns:1fr 1fr}.workspace{padding:18px}.transcript p{grid-template-columns:62px 1fr}}
</style>
