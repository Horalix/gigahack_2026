<script lang="ts">
  import { page } from "$app/state";
  import StatusChip from "$lib/components/meetings/status-chip.svelte";
  import { formatDateTime, meetingHref, meetingStatus, MEETING_TYPE_LABEL } from "$lib/prototype/format";
  import { getPatient, meetingsForPatient } from "$lib/prototype/store.svelte";

  const patient = $derived(getPatient(page.params.id ?? ""));
  const meetings = $derived(patient ? meetingsForPatient(patient.id) : []);
</script>

<svelte:head><title>{patient?.displayName ?? "Patient"} · Secure MOM</title></svelte:head>

<div class="page">
  <a class="back subtle" href="/dashboard">← Dashboard</a>

  {#if !patient}
    <!-- Same answer for "does not exist" and "not yours to see", so the page
         does not reveal which patient IDs exist (PBI-005/006). -->
    <div class="card empty">
      <h1>Patient not found</h1>
      <p>This patient does not exist or you do not have access.</p>
    </div>
  {:else}
    <div class="page-head">
      <div>
        <h1>{patient.displayName}</h1>
        <p class="muted meta">
          Reference <span class="mono">{patient.reference ?? "none recorded"}</span> · {patient.status}
        </p>
      </div>
      <div class="actions">
        <a class="btn" href="/meetings/new?mode=upload&patient={patient.id}">⤒ Upload recording</a>
        <a class="btn btn-primary" href="/meetings/new?mode=record&patient={patient.id}">● Record meeting</a>
      </div>
    </div>

    <section class="card" aria-labelledby="linked-title">
      <div class="card-head">
        <h2 id="linked-title">Linked meetings</h2>
        <span class="subtle">Only meetings explicitly linked to this patient</span>
      </div>
      <ul class="list">
        {#each meetings as meeting (meeting.id)}
          {@const status = meetingStatus(meeting)}
          <li>
            <a class="row-link" href={meetingHref(meeting)}>
              <span>
                <span class="title">{meeting.title}</span><br />
                <span class="subtle">{MEETING_TYPE_LABEL[meeting.meetingType]} · {formatDateTime(meeting.recordedAt)}</span>
              </span>
              <StatusChip {...status} />
            </a>
          </li>
        {:else}
          <li class="empty">
            No meetings linked yet. Start one with the buttons above and it will be linked to {patient.displayName}.
          </li>
        {/each}
      </ul>
    </section>
  {/if}
</div>

<style>
  .back {
    text-decoration: none;
    align-self: flex-start;
  }
  .title {
    font-weight: 500;
  }
</style>
