// Deterministic minutes document for the demo backend's HTML/PDF/JSON exports.
// Every value from the meeting is escaped; nothing is interpreted as markup.

type Lang = "en" | "ro" | "ru";

const H: Record<Lang, Record<string, string>> = {
  en: { minutes: "Minutes", participants: "Participants", decisions: "Decisions", actions: "Actions", information: "Information", unresolved: "Unresolved matters", amendments: "Amendment history", owner: "Owner", due: "Due", condition: "Condition", none: "None recorded.", unspecified: "Not specified", revision: "Transcript revision" },
  ro: { minutes: "Proces-verbal", participants: "Participanți", decisions: "Decizii", actions: "Acțiuni", information: "Informații", unresolved: "Chestiuni nerezolvate", amendments: "Istoricul modificărilor", owner: "Responsabil", due: "Termen", condition: "Condiție", none: "Nimic înregistrat.", unspecified: "Nespecificat", revision: "Revizia transcrierii" },
  ru: { minutes: "Протокол", participants: "Участники", decisions: "Решения", actions: "Действия", information: "Информация", unresolved: "Нерешённые вопросы", amendments: "История изменений", owner: "Ответственный", due: "Срок", condition: "Условие", none: "Не зафиксировано.", unspecified: "Не указано", revision: "Версия расшифровки" },
};

const esc = (s: unknown) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]!);

export function renderMinutes(meeting: any, participants: string[], items: any[], template: any, revision: number): string {
  const lang: Lang = meeting.language in H ? meeting.language : "en";
  const h = H[lang];
  const accepted = items.filter((i) => i.review === "accepted");
  const by = (category: string) => accepted.filter((i) => i.body.category === category && i.body.kind !== "reject");
  const unresolved = accepted.filter((i) => i.body.category === "action" && (!i.body.owner || !i.body.due));
  const amended = accepted.filter((i) => i.body.human_amendment);
  const heading = template?.titles?.[lang] || h.minutes;

  const list = (rows: any[], detail: (i: any) => string) =>
    rows.length ? `<ul>${rows.map((i) => `<li><strong>${esc(i.body.text)}</strong>${detail(i)}</li>`).join("")}</ul>` : `<p class="none">${h.none}</p>`;
  const actionDetail = (i: any) =>
    `<br>${h.owner}: ${esc(i.body.owner || h.unspecified)} · ${h.due}: ${esc(i.body.due || h.unspecified)}` +
    (i.body.condition ? `<br>${h.condition}: ${esc(i.body.condition)}` : "");

  return `<!doctype html>
<html lang="${lang}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>${esc(heading)} — ${esc(meeting.title)}</title>
<style>
:root{color-scheme:light;font:15px/1.6 'Noto Sans',system-ui,sans-serif;color:#243b40}
body{max-width:46rem;margin:2.5rem auto;padding:0 1.25rem}
h1{font-size:1.7rem;margin:0 0 .25rem}h2{font-size:1.1rem;margin:2rem 0 .5rem;border-bottom:1px solid #dfe6e2;padding-bottom:.3rem}
.meta{color:#587074;margin:0}.intro{margin-top:1rem}li{margin:.6rem 0}.none{color:#61767a}
footer{margin-top:3rem;color:#61767a;font-size:.8rem}
@media print{body{margin:0;max-width:none}}
</style></head><body><main>
<h1>${esc(heading)}</h1>
<p class="meta">${esc(meeting.title)} · ${esc(meeting.classification)} · ${esc(meeting.date || h.unspecified)}${meeting.timezone ? " · " + esc(meeting.timezone) : ""}</p>
${template?.introduction ? `<p class="intro">${esc(template.introduction)}</p>` : ""}
<h2>${h.participants}</h2>${participants.length ? `<p>${participants.map(esc).join(" · ")}</p>` : `<p class="none">${h.none}</p>`}
<h2>${h.decisions}</h2>${list(by("decision"), () => "")}
<h2>${h.actions}</h2>${list(by("action"), actionDetail)}
<h2>${h.information}</h2>${list(by("information"), () => "")}
<h2>${h.unresolved}</h2>${list(unresolved, actionDetail)}
<h2>${h.amendments}</h2>${list(amended, (i) => `<br>${esc(i.body.human_amendment.reason)}`)}
<footer>${h.revision} ${revision} · template ${esc(template?.version ?? 0)}</footer>
</main></body></html>`;
}
