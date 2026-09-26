// Seed data for the in-browser demo backend. Fictional people and content.
// Times are in 16 kHz samples, as the Notavra API uses.

export const RATE = 16000;

export const PEOPLE = ["Dr. A. Rusu", "Dr. M. Ivanov", "Dr. E. Ciobanu", "S. Popa", "V. Lungu"];

// [start seconds, end seconds, speaker (null = not identified), text]
export const SCRIPT: [number, number, string | null, string][] = [
  [0, 7.4, "Dr. A. Rusu", "Bună ziua, colegi. Începem consiliul medical: pe agendă avem protocolul de CT cu contrast și lista de așteptare pentru RMN."],
  [7.4, 15.8, "Dr. M. Ivanov", "Pentru protocolul de contrast propun screening de creatinină la toți pacienții peste 60 de ani — basically a mandatory eGFR check before the scan."],
  [15.8, 22.9, "Dr. E. Ciobanu", "Согласна, но нужно учитывать пациентов с сахарным диабетом: у них риск контраст-индуцированной нефропатии выше."],
  [22.9, 30.1, "Dr. M. Ivanov", "Da, corect. Pentru pacienții diabetici — отдельный протокол гидратации до и после процедуры."],
  [30.1, 38.6, "Dr. A. Rusu", "Bine. Decizia: introducem screeningul obligatoriu de eGFR înainte de orice CT cu contrast, începând de luni."],
  [38.6, 45.2, "S. Popa", "I can update the order set in the hospital information system, but I need the final wording from cardiology first."],
  [45.2, 52.8, "Dr. A. Rusu", "Doamna doctor Ciobanu, puteți trimite formularea finală până vineri?"],
  [52.8, 58.1, "Dr. E. Ciobanu", "Да, до пятницы пришлю."],
  [58.1, 66.9, "Dr. A. Rusu", "Al doilea punct: lista de așteptare RMN. Avem 140 de pacienți, iar timpul mediu de așteptare este de 23 de zile."],
  [66.9, 75.4, "Dr. M. Ivanov", "Propun să extindem programul RMN seara, până la ora 22 — but we need extra staffing for the evening shift."],
  [75.4, 82.0, null, "Это надо согласовать с администрацией и с бюджетом, не уверен, что это реально в этом месяце."],
  [82.0, 90.3, "Dr. A. Rusu", "Azi nu luăm decizia privind extinderea programului. Cineva trebuie să pregătească o estimare de cost până la sfârșitul lunii."],
  [90.3, 97.8, "S. Popa", "And the proposal to outsource MRI reads to an external clinic — I think we should drop it, patient data cannot leave the hospital."],
  [97.8, 104.0, "Dr. A. Rusu", "De acord, respingem externalizarea. Totul rămâne intern."],
  [104.0, 110.5, "Dr. A. Rusu", "Mulțumesc tuturor, ședința s-a încheiat. Спасибо."],
];

export const SCRIPT_SECONDS = 110.5;

// Segment index (0-based) → processing annotations shown by the transcript view.
export const BOUNDARY_REVIEW = new Set([9]);
export const ALTERNATIVES: Record<number, { engine: string; text: string }[]> = {
  2: [{ engine: "parakeet", text: "Согласна, но нужно учитывать пациентов с сахарным диабетом, у них риск контрастной нефропатии выше." }],
};

type Field = "text" | "owner" | "due" | "condition" | "value";
type Ref = [segment: number, field: Field, quote?: string];

export interface CandidateSeed {
  subject: string;
  category: "action" | "decision" | "information";
  kind: "propose" | "confirm" | "amend" | "reject" | "cancel" | "reopen" | "inform";
  text: string;
  owner: string | null;
  due: string | null;
  condition: string | null;
  value: string | null;
  uncertainties: string[];
  review: "unreviewed" | "needs_review";
  refs: Ref[];
}

export const CANDIDATES: CandidateSeed[] = [
  {
    subject: "eGFR screening before contrast CT",
    category: "decision",
    kind: "confirm",
    text: "Introduce mandatory eGFR screening before every contrast-enhanced CT.",
    owner: null,
    due: "2026-09-28",
    condition: null,
    value: "Patients over 60",
    uncertainties: [],
    review: "unreviewed",
    refs: [[4, "text"], [4, "due", "începând de luni"], [1, "value", "la toți pacienții peste 60 de ani"]],
  },
  {
    subject: "Contrast protocol wording",
    category: "action",
    kind: "confirm",
    text: "Send the final wording of the contrast protocol to IT.",
    owner: "Dr. E. Ciobanu",
    due: "2026-10-02",
    condition: null,
    value: null,
    uncertainties: [],
    review: "unreviewed",
    refs: [[6, "text"], [6, "owner", "Doamna doctor Ciobanu"], [7, "owner"], [6, "due", "până vineri"], [7, "due", "до пятницы"]],
  },
  {
    subject: "Order set update",
    category: "action",
    kind: "confirm",
    text: "Update the order set in the hospital information system with the new screening step.",
    owner: "S. Popa",
    due: null,
    condition: "After cardiology sends the final wording",
    value: null,
    uncertainties: ["No due date was stated for this action."],
    review: "needs_review",
    refs: [[5, "text"], [5, "owner", "I can update the order set in the hospital information system"], [5, "condition", "but I need the final wording from cardiology first"]],
  },
  {
    subject: "MRI evening hours cost estimate",
    category: "action",
    kind: "propose",
    text: "Prepare a cost estimate for extending MRI hours to 22:00.",
    owner: null,
    due: "2026-09-30",
    condition: null,
    value: "Until 22:00",
    uncertainties: ["Owner not named: “Cineva trebuie să pregătească o estimare de cost”."],
    review: "needs_review",
    refs: [[11, "text", "Cineva trebuie să pregătească o estimare de cost până la sfârșitul lunii."], [11, "due", "până la sfârșitul lunii"], [9, "value", "până la ora 22"]],
  },
  {
    subject: "Hydration protocol for diabetic patients",
    category: "information",
    kind: "propose",
    text: "A separate hydration protocol for diabetic patients before and after the procedure was suggested.",
    owner: null,
    due: null,
    condition: null,
    value: null,
    uncertainties: [],
    review: "unreviewed",
    refs: [[3, "text", "отдельный протокол гидратации до и после процедуры"]],
  },
  {
    subject: "Outsourcing MRI reads",
    category: "decision",
    kind: "reject",
    text: "Outsourcing MRI reads to an external clinic was rejected; all reads stay internal.",
    owner: null,
    due: null,
    condition: null,
    value: null,
    uncertainties: [],
    review: "unreviewed",
    refs: [[12, "text", "the proposal to outsource MRI reads to an external clinic"], [13, "text", "respingem externalizarea"]],
  },
  {
    subject: "MRI waiting list",
    category: "information",
    kind: "inform",
    text: "The MRI waiting list has 140 patients with an average wait of 23 days.",
    owner: null,
    due: null,
    condition: null,
    value: "140 patients · 23 days",
    uncertainties: [],
    review: "unreviewed",
    refs: [[8, "text"], [8, "value", "Avem 140 de pacienți, iar timpul mediu de așteptare este de 23 de zile."]],
  },
];

export const GROUPS = [
  { id: "grp-medical", name: "Medical Board", addresses: ["cmo@medpark.local", "surgery.head@medpark.local", "cardiology.head@medpark.local", "med.secretariat@medpark.local"], version: 1 },
  { id: "grp-executive", name: "Executive Board", addresses: ["ceo@medpark.local", "cfo@medpark.local", "coo@medpark.local"], version: 1 },
  { id: "grp-admin", name: "Administrative & Operations", addresses: ["admin.director@medpark.local", "facilities@medpark.local", "procurement@medpark.local", "hr@medpark.local"], version: 1 },
];

export const ALLOWED_DOMAINS = ["medpark.local", "secure-mom.test"];

export const TEMPLATES = [
  { classification: "Administrative", version: 1, titles: { en: "", ro: "", ru: "" }, introduction: "", recipient_group_id: "grp-admin" },
  { classification: "Executive", version: 1, titles: { en: "", ro: "", ru: "" }, introduction: "", recipient_group_id: "grp-executive" },
  { classification: "Medical", version: 1, titles: { en: "", ro: "", ru: "" }, introduction: "", recipient_group_id: "grp-medical" },
];

export const GLOSSARY = ["eGFR", "CT cu contrast", "RMN", "nefropatie", "order set", "creatinină"];
