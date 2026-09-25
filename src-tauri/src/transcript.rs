use crate::{app_error::AppError, diarization::SpeakerLabelConfidence};
use rusqlite::{params, Connection};
use serde::{Deserialize, Serialize};
use std::{
    fs,
    path::PathBuf,
    sync::{
        atomic::{AtomicBool, AtomicU64, Ordering},
        mpsc::{self, SyncSender},
        Arc, Mutex,
    },
    time::{SystemTime, UNIX_EPOCH},
};

const SETTINGS_FILE_NAME: &str = "transcript-settings.json";
const DATABASE_FILE_NAME: &str = "transcripts.db";
const STORAGE_LIMIT: u64 = 64 * 1024 * 1024;
const SAVE_ERROR: &str = "Transcript saving stopped. Free disk space or delete saved transcripts in Settings, then enable saving again.";

type StoreTask = Box<dyn FnOnce(&mut TranscriptStoreState) + Send>;

#[derive(Clone)]
pub struct TranscriptService {
    sender: SyncSender<StoreTask>,
    // Odd generations permit saving. Every consent/session boundary invalidates queued audio.
    generation: Arc<AtomicU64>,
    error: Arc<Mutex<Option<String>>>,
    queue_failed: Arc<AtomicBool>,
    #[cfg(test)]
    database_path: PathBuf,
}

impl std::fmt::Debug for TranscriptService {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("TranscriptService").finish_non_exhaustive()
    }
}

impl TranscriptService {
    pub fn new(data_dir: PathBuf) -> Self {
        let generation = Arc::new(AtomicU64::new(0));
        let error = Arc::new(Mutex::new(None));
        let queue_failed = Arc::new(AtomicBool::new(false));
        let worker_queue_failed = queue_failed.clone();
        let mut store = TranscriptStoreState::new(data_dir.clone());
        store.generation = generation.clone();
        store.error = error.clone();
        match store.load_settings() {
            Ok(settings) => generation.store(u64::from(settings.saving_enabled), Ordering::SeqCst),
            Err(_) => {
                *error.lock().unwrap() =
                    Some("Transcript settings could not be read. Saving is off.".into())
            }
        }
        let (sender, receiver) = mpsc::sync_channel::<StoreTask>(32);
        std::thread::Builder::new()
            .name("feelsay-transcripts".into())
            .spawn(move || {
                while let Ok(task) = receiver.recv() {
                    if worker_queue_failed.swap(false, Ordering::SeqCst) {
                        store.fail_saving();
                    }
                    task(&mut store);
                }
                let _ = store.finish_session();
            })
            .expect("start transcript worker");
        Self {
            sender,
            generation,
            error,
            queue_failed,
            #[cfg(test)]
            database_path: data_dir.join(DATABASE_FILE_NAME),
        }
    }

    fn request<T: Send + 'static>(
        &self,
        task: impl FnOnce(&mut TranscriptStoreState) -> Result<T, AppError> + Send + 'static,
    ) -> Result<T, AppError> {
        let (sender, receiver) = mpsc::channel();
        self.sender
            .send(Box::new(move |store| {
                let _ = sender.send(task(store));
            }))
            .map_err(|_| AppError::Io(SAVE_ERROR.into()))?;
        receiver
            .recv()
            .map_err(|_| AppError::Io(SAVE_ERROR.into()))?
    }

    pub fn generation(&self) -> u64 {
        self.generation.load(Ordering::SeqCst)
    }

    pub fn load_settings(&self) -> Result<TranscriptSettings, AppError> {
        Ok(TranscriptSettings {
            saving_enabled: self.generation() % 2 == 1,
        })
    }

    pub fn status(&self) -> TranscriptStatus {
        TranscriptStatus {
            saving_enabled: self.generation() % 2 == 1,
            error: self.error.lock().unwrap().clone(),
        }
    }

    pub fn save_settings(
        &self,
        settings: TranscriptSettings,
    ) -> Result<TranscriptSettings, AppError> {
        // Close the consent gate immediately. Only the newest settings request may reopen it.
        let previous = self
            .generation
            .fetch_update(Ordering::SeqCst, Ordering::SeqCst, |old| {
                Some((old + 2) & !1)
            })
            .unwrap();
        let revision = (previous + 2) & !1;
        self.request(move |store| {
            if store.generation.load(Ordering::SeqCst) != revision {
                return Ok(TranscriptSettings {
                    saving_enabled: store.generation.load(Ordering::SeqCst) % 2 == 1,
                });
            }
            store.save_settings(settings.clone())?;
            let _ = store.generation.compare_exchange(
                revision,
                revision | u64::from(settings.saving_enabled),
                Ordering::SeqCst,
                Ordering::SeqCst,
            );
            *store.error.lock().unwrap() = None;
            Ok(settings)
        })
    }

    pub fn start_session(&self, source_summary: String) -> Result<Option<i64>, AppError> {
        self.request(move |store| {
            if store.finish_session().is_err() {
                store.fail_saving();
            }
            store.generation.fetch_add(2, Ordering::SeqCst);
            store.source_summary = Some(source_summary.clone());
            store.session_started_at_ms = now_ms();
            match store.start_session(source_summary) {
                Ok(session) => Ok(session),
                Err(_) => {
                    store.fail_saving();
                    Ok(None)
                }
            }
        })
    }

    pub fn finish_session(&self) -> Result<(), AppError> {
        self.request(|store| {
            store.source_summary = None;
            store.finish_session()
        })
    }

    pub fn append_segment(&self, segment: TranscriptSegment) -> Result<(), AppError> {
        let generation = self.generation();
        self.request(move |store| store.append_if_current(segment, generation))
    }

    pub fn enqueue_segment(&self, segment: TranscriptSegment, generation: u64) {
        if generation & 1 == 0 || generation != self.generation() {
            return;
        }
        if self
            .sender
            .try_send(Box::new(move |store| {
                if store.append_if_current(segment, generation).is_err() {
                    store.fail_saving();
                }
            }))
            .is_err()
        {
            self.queue_failed.store(true, Ordering::SeqCst);
            self.generation.fetch_and(!1, Ordering::SeqCst);
            *self.error.lock().unwrap() = Some(SAVE_ERROR.into());
        }
    }

    pub fn runtime_config(&self) -> Option<TranscriptRuntimeConfig> {
        Some(TranscriptRuntimeConfig {
            service: self.clone(),
        })
    }

    pub fn exports_directory(&self) -> Result<PathBuf, AppError> {
        self.request(|store| {
            fs::create_dir_all(&store.exports_dir)?;
            Ok(store.exports_dir.clone())
        })
    }

    pub fn list_sessions(&self, limit: u32) -> Result<Vec<TranscriptSessionSummary>, AppError> {
        self.request(move |store| store.list_sessions(limit))
    }

    pub fn read_session(&self, session_id: i64) -> Result<String, AppError> {
        self.request(move |store| {
            let connection = store.open_connection()?;
            render_export(
                &load_session(&connection, session_id)?,
                &load_segments(&connection, session_id)?,
                TranscriptExportFormat::Txt,
            )
        })
    }

    pub fn export_session(
        &self,
        session_id: i64,
        format: TranscriptExportFormat,
    ) -> Result<String, AppError> {
        self.request(move |store| store.export_session(session_id, format))
    }

    pub fn delete_session(&self, session_id: i64) -> Result<(), AppError> {
        self.request(move |store| {
            let connection = store.open_connection()?;
            let session = load_session(&connection, session_id)?;
            for format in [
                TranscriptExportFormat::Txt,
                TranscriptExportFormat::Srt,
                TranscriptExportFormat::Vtt,
                TranscriptExportFormat::Json,
            ] {
                let path = store.exports_dir.join(format!(
                    "feelsay-transcript-{}-{}.{}",
                    session.id,
                    session.started_at_ms,
                    format.extension()
                ));
                if path.exists() {
                    fs::remove_file(path)?;
                }
            }
            connection.execute(
                "DELETE FROM transcript_sessions WHERE id = ?1",
                params![session_id],
            )?;
            let mut active = store.active_session_id.lock().unwrap();
            if *active == Some(session_id) {
                *active = None;
                store.generation.fetch_add(2, Ordering::SeqCst);
            }
            Ok(())
        })
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct TranscriptStatus {
    pub saving_enabled: bool,
    pub error: Option<String>,
}

#[derive(Debug)]
struct TranscriptStoreState {
    settings_path: PathBuf,
    database_path: PathBuf,
    exports_dir: PathBuf,
    active_session_id: Mutex<Option<i64>>,
    source_summary: Option<String>,
    session_started_at_ms: u64,
    generation: Arc<AtomicU64>,
    error: Arc<Mutex<Option<String>>>,
}

impl TranscriptStoreState {
    pub fn new(data_dir: PathBuf) -> Self {
        Self {
            settings_path: data_dir.join(SETTINGS_FILE_NAME),
            database_path: data_dir.join(DATABASE_FILE_NAME),
            exports_dir: data_dir.join("transcript-exports"),
            active_session_id: Mutex::new(None),
            source_summary: None,
            session_started_at_ms: 0,
            generation: Arc::new(AtomicU64::new(0)),
            error: Arc::new(Mutex::new(None)),
        }
    }

    pub fn load_settings(&self) -> Result<TranscriptSettings, AppError> {
        if !self.settings_path.exists() {
            return Ok(TranscriptSettings::default());
        }

        let content = fs::read_to_string(&self.settings_path)?;
        let content = content.trim_start_matches('\u{feff}');
        if content.trim().is_empty() {
            return Ok(TranscriptSettings::default());
        }

        let settings = serde_json::from_str::<TranscriptSettings>(content).map_err(|error| {
            AppError::Io(format!(
                "could not read transcript settings at {}: {error}",
                self.settings_path.display()
            ))
        })?;

        Ok(settings)
    }

    pub fn save_settings(
        &self,
        settings: TranscriptSettings,
    ) -> Result<TranscriptSettings, AppError> {
        if let Some(parent) = self.settings_path.parent() {
            fs::create_dir_all(parent)?;
        }

        let content = serde_json::to_string_pretty(&settings)
            .map_err(|error| AppError::Io(error.to_string()))?;
        crate::persistence::write_bytes(&self.settings_path, content.as_bytes())?;

        Ok(settings)
    }

    pub fn start_session(&self, source_summary: String) -> Result<Option<i64>, AppError> {
        if self.generation.load(Ordering::SeqCst) & 1 == 0 {
            *self
                .active_session_id
                .lock()
                .expect("transcript session lock") = None;
            return Ok(None);
        }

        let connection = self.open_connection()?;
        let count: u32 =
            connection.query_row("SELECT COUNT(*) FROM transcript_sessions", [], |row| {
                row.get(0)
            })?;
        if count >= 100 {
            return Err(AppError::Io(SAVE_ERROR.into()));
        }
        connection.execute(
            "INSERT INTO transcript_sessions (started_at_ms, source_summary) VALUES (?1, ?2)",
            params![self.session_started_at_ms, clean_text(&source_summary)],
        )?;
        let session_id = connection.last_insert_rowid();

        *self
            .active_session_id
            .lock()
            .expect("transcript session lock") = Some(session_id);

        Ok(Some(session_id))
    }

    fn append_if_current(
        &self,
        mut segment: TranscriptSegment,
        generation: u64,
    ) -> Result<(), AppError> {
        if generation & 1 == 0
            || generation != self.generation.load(Ordering::SeqCst)
            || !segment.is_final
        {
            return Ok(());
        }

        if self.active_session_id.lock().unwrap().is_none() {
            let Some(source) = &self.source_summary else {
                return Ok(());
            };
            self.start_session(source.clone())?;
        }

        let session_id = match *self
            .active_session_id
            .lock()
            .expect("transcript session lock")
        {
            Some(session_id) => session_id,
            None => return Ok(()),
        };

        let connection = self.open_connection()?;
        if segment.start_ms >= self.session_started_at_ms && self.session_started_at_ms > 0 {
            segment.start_ms = segment.start_ms.saturating_sub(self.session_started_at_ms);
            segment.end_ms = segment.end_ms.saturating_sub(self.session_started_at_ms);
        }
        insert_segment(&connection, session_id, segment)
    }

    pub fn finish_session(&self) -> Result<(), AppError> {
        let session_id = self
            .active_session_id
            .lock()
            .expect("transcript session lock")
            .take();

        let Some(session_id) = session_id else {
            return Ok(());
        };

        let connection = self.open_connection()?;
        connection.execute(
            "UPDATE transcript_sessions SET ended_at_ms = ?1 WHERE id = ?2",
            params![now_ms(), session_id],
        )?;

        Ok(())
    }

    fn fail_saving(&self) {
        self.generation.fetch_and(!1, Ordering::SeqCst);
        *self.error.lock().unwrap() = Some(SAVE_ERROR.into());
        let _ = self.save_settings(TranscriptSettings::default());
    }

    pub fn list_sessions(&self, limit: u32) -> Result<Vec<TranscriptSessionSummary>, AppError> {
        if !self.database_path.exists() {
            return Ok(Vec::new());
        }

        let connection = self.open_connection()?;
        let mut statement = connection.prepare(
            "
            SELECT
                sessions.id,
                sessions.started_at_ms,
                sessions.ended_at_ms,
                sessions.source_summary,
                COUNT(segments.id) AS segment_count
            FROM transcript_sessions sessions
            LEFT JOIN transcript_segments segments ON segments.session_id = sessions.id
            GROUP BY sessions.id
            ORDER BY sessions.started_at_ms DESC
            LIMIT ?1
            ",
        )?;

        let sessions = statement
            .query_map(params![limit.clamp(1, 100)], |row| {
                Ok(TranscriptSessionSummary {
                    id: row.get(0)?,
                    started_at_ms: row.get(1)?,
                    ended_at_ms: row.get(2)?,
                    source_summary: row.get(3)?,
                    segment_count: row.get(4)?,
                })
            })?
            .collect::<Result<Vec<_>, _>>()?;

        Ok(sessions)
    }

    pub fn export_session(
        &self,
        session_id: i64,
        format: TranscriptExportFormat,
    ) -> Result<String, AppError> {
        let connection = self.open_connection()?;
        let session = load_session(&connection, session_id)?;
        let segments = load_segments(&connection, session_id)?;
        let content = render_export(&session, &segments, format)?;

        fs::create_dir_all(&self.exports_dir)?;

        let file_name = format!(
            "feelsay-transcript-{}-{}.{}",
            session.id,
            session.started_at_ms,
            format.extension()
        );
        let path = self.exports_dir.join(file_name);
        let used = fs::read_dir(&self.exports_dir)?
            .try_fold(0u64, |total, entry| -> Result<u64, std::io::Error> {
                Ok(total + entry?.metadata()?.len())
            })?;
        let replaced = fs::metadata(&path).map(|meta| meta.len()).unwrap_or(0);
        if used.saturating_sub(replaced) + content.len() as u64 > STORAGE_LIMIT {
            return Err(AppError::Io(
                "Transcript exports are full. Delete saved transcripts to free space.".into(),
            ));
        }
        fs::write(&path, content)?;

        Ok(path.to_string_lossy().to_string())
    }

    fn open_connection(&self) -> Result<Connection, AppError> {
        if let Some(parent) = self.database_path.parent() {
            fs::create_dir_all(parent)?;
        }

        let connection = Connection::open(&self.database_path)?;
        initialize_schema(&connection)?;
        let page_size: u64 = connection.query_row("PRAGMA page_size", [], |row| row.get(0))?;
        connection.pragma_update(None, "max_page_count", STORAGE_LIMIT / page_size)?;
        Ok(connection)
    }
}

#[derive(Debug, Clone)]
pub struct TranscriptRuntimeConfig {
    service: TranscriptService,
}

impl TranscriptRuntimeConfig {
    pub fn generation(&self) -> u64 {
        self.service.generation()
    }
    pub fn append_segment(&self, segment: TranscriptSegment, generation: u64) {
        self.service.enqueue_segment(segment, generation);
    }
}

#[derive(Debug, Clone, Default, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "camelCase")]
pub struct TranscriptSettings {
    #[serde(default)]
    pub saving_enabled: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "camelCase")]
pub struct TranscriptSegment {
    pub start_ms: u64,
    pub end_ms: u64,
    pub original_text: String,
    pub translated_text: Option<String>,
    pub source_label: Option<String>,
    #[serde(default)]
    pub speaker_label: Option<String>,
    #[serde(default)]
    pub speaker_confidence: Option<SpeakerLabelConfidence>,
    pub is_final: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "camelCase")]
pub struct TranscriptSessionSummary {
    pub id: i64,
    pub started_at_ms: u64,
    pub ended_at_ms: Option<u64>,
    pub source_summary: String,
    pub segment_count: u32,
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "lowercase")]
pub enum TranscriptExportFormat {
    Txt,
    Srt,
    Vtt,
    Json,
}

impl TranscriptExportFormat {
    fn extension(self) -> &'static str {
        match self {
            Self::Txt => "txt",
            Self::Srt => "srt",
            Self::Vtt => "vtt",
            Self::Json => "json",
        }
    }
}

pub trait TranscriptStore {
    fn commit_segment(&self, segment: TranscriptSegment) -> Result<(), AppError>;
}

impl TranscriptStore for TranscriptService {
    fn commit_segment(&self, segment: TranscriptSegment) -> Result<(), AppError> {
        self.append_segment(segment)
    }
}

fn initialize_schema(connection: &Connection) -> Result<(), AppError> {
    connection.execute_batch(
        "
        PRAGMA foreign_keys = ON;
        PRAGMA secure_delete = ON;
        PRAGMA journal_mode = DELETE;
        PRAGMA temp_store = MEMORY;

        CREATE TABLE IF NOT EXISTS transcript_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            started_at_ms INTEGER NOT NULL,
            ended_at_ms INTEGER,
            source_summary TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS transcript_segments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL,
            start_ms INTEGER NOT NULL,
            end_ms INTEGER NOT NULL,
            source_label TEXT NOT NULL,
            speaker_label TEXT,
            speaker_confidence TEXT,
            original_text TEXT NOT NULL,
            translated_text TEXT,
            is_final INTEGER NOT NULL,
            created_at_ms INTEGER NOT NULL,
            FOREIGN KEY (session_id) REFERENCES transcript_sessions(id) ON DELETE CASCADE
        );
        ",
    )?;
    ensure_text_column(connection, "transcript_segments", "speaker_label")?;
    ensure_text_column(connection, "transcript_segments", "speaker_confidence")?;

    Ok(())
}

fn insert_segment(
    connection: &Connection,
    session_id: i64,
    segment: TranscriptSegment,
) -> Result<(), AppError> {
    if !segment.is_final {
        return Ok(());
    }
    let text_size =
        segment.original_text.len() + segment.translated_text.as_ref().map_or(0, String::len);
    if text_size > 64 * 1024 {
        return Err(AppError::Io(SAVE_ERROR.into()));
    }
    connection.execute(
        "INSERT INTO transcript_segments (
            session_id,
            start_ms,
            end_ms,
            source_label,
            speaker_label,
            speaker_confidence,
            original_text,
            translated_text,
            is_final,
            created_at_ms
        ) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10)",
        params![
            session_id,
            segment.start_ms,
            segment.end_ms,
            clean_text(&segment.source_label.unwrap_or_default()),
            segment.speaker_label.map(|label| clean_text(&label)),
            segment.speaker_confidence.map(speaker_confidence_value),
            clean_text(&segment.original_text),
            segment.translated_text.map(|text| clean_text(&text)),
            segment.is_final,
            now_ms(),
        ],
    )?;

    Ok(())
}

fn load_session(
    connection: &Connection,
    session_id: i64,
) -> Result<TranscriptSessionSummary, AppError> {
    let session = connection.query_row(
        "
        SELECT
            sessions.id,
            sessions.started_at_ms,
            sessions.ended_at_ms,
            sessions.source_summary,
            COUNT(segments.id) AS segment_count
        FROM transcript_sessions sessions
        LEFT JOIN transcript_segments segments ON segments.session_id = sessions.id
        WHERE sessions.id = ?1
        GROUP BY sessions.id
        ",
        params![session_id],
        |row| {
            Ok(TranscriptSessionSummary {
                id: row.get(0)?,
                started_at_ms: row.get(1)?,
                ended_at_ms: row.get(2)?,
                source_summary: row.get(3)?,
                segment_count: row.get(4)?,
            })
        },
    )?;

    Ok(session)
}

fn load_segments(
    connection: &Connection,
    session_id: i64,
) -> Result<Vec<TranscriptSegment>, AppError> {
    let mut statement = connection.prepare(
        "
        SELECT
            start_ms,
            end_ms,
            original_text,
            translated_text,
            source_label,
            speaker_label,
            speaker_confidence,
            is_final
        FROM transcript_segments
        WHERE session_id = ?1
        ORDER BY start_ms ASC, id ASC
        ",
    )?;

    let segments = statement
        .query_map(params![session_id], |row| {
            Ok(TranscriptSegment {
                start_ms: row.get(0)?,
                end_ms: row.get(1)?,
                original_text: row.get(2)?,
                translated_text: row.get(3)?,
                source_label: row.get(4)?,
                speaker_label: row.get(5)?,
                speaker_confidence: parse_speaker_confidence(row.get::<_, Option<String>>(6)?),
                is_final: row.get(7)?,
            })
        })?
        .collect::<Result<Vec<_>, _>>()?;

    Ok(segments)
}

fn render_export(
    session: &TranscriptSessionSummary,
    segments: &[TranscriptSegment],
    format: TranscriptExportFormat,
) -> Result<String, AppError> {
    match format {
        TranscriptExportFormat::Txt => Ok(render_txt(session, segments)),
        TranscriptExportFormat::Srt => Ok(render_srt(segments)),
        TranscriptExportFormat::Vtt => Ok(render_vtt(segments)),
        TranscriptExportFormat::Json => {
            serde_json::to_string_pretty(&TranscriptExport { session, segments })
                .map_err(|error| AppError::Io(error.to_string()))
        }
    }
}

fn render_txt(session: &TranscriptSessionSummary, segments: &[TranscriptSegment]) -> String {
    let mut lines = vec![format!("FeelSay transcript - {}", session.source_summary)];

    if segments.is_empty() {
        lines.push("No transcript segments saved.".to_string());
    } else {
        lines.push(format!(
            "Session start (Unix milliseconds): {}",
            session.started_at_ms
        ));
        lines.extend(segments.iter().map(|segment| {
            format!(
                "[{} – {}] {}",
                format_vtt_time(segment.start_ms),
                format_vtt_time(segment.end_ms),
                segment_export_text(segment)
            )
        }));
    }

    lines.join("\n")
}

fn render_srt(segments: &[TranscriptSegment]) -> String {
    segments
        .iter()
        .enumerate()
        .map(|(index, segment)| {
            format!(
                "{}\n{} --> {}\n{}\n",
                index + 1,
                format_srt_time(segment.start_ms),
                format_srt_time(segment.end_ms),
                segment_export_text(segment)
            )
        })
        .collect::<Vec<_>>()
        .join("\n")
}

fn render_vtt(segments: &[TranscriptSegment]) -> String {
    let body = segments
        .iter()
        .map(|segment| {
            format!(
                "{} --> {}\n{}\n",
                format_vtt_time(segment.start_ms),
                format_vtt_time(segment.end_ms),
                segment_export_text(segment)
            )
        })
        .collect::<Vec<_>>()
        .join("\n");

    if body.is_empty() {
        "WEBVTT\n".to_string()
    } else {
        format!("WEBVTT\n\n{body}")
    }
}

fn format_srt_time(milliseconds: u64) -> String {
    format_timestamp(milliseconds, ',')
}

fn format_vtt_time(milliseconds: u64) -> String {
    format_timestamp(milliseconds, '.')
}

fn format_timestamp(milliseconds: u64, separator: char) -> String {
    let hours = milliseconds / 3_600_000;
    let minutes = (milliseconds % 3_600_000) / 60_000;
    let seconds = (milliseconds % 60_000) / 1_000;
    let millis = milliseconds % 1_000;

    format!("{hours:02}:{minutes:02}:{seconds:02}{separator}{millis:03}")
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct TranscriptExport<'a> {
    session: &'a TranscriptSessionSummary,
    segments: &'a [TranscriptSegment],
}

fn segment_export_text(segment: &TranscriptSegment) -> String {
    let mut text = clean_text(&segment.original_text);
    if let Some(translation) = &segment.translated_text {
        if !text.is_empty() {
            text.push('\n');
        }
        text.push_str(&clean_text(translation));
    }
    let labels = segment_export_labels(segment);

    if labels.is_empty() {
        return text;
    }

    format!("[{}] {text}", labels.join(" | "))
}

fn clean_text(value: &str) -> String {
    value.split_whitespace().collect::<Vec<_>>().join(" ")
}

fn segment_export_labels(segment: &TranscriptSegment) -> Vec<String> {
    let mut labels = Vec::new();

    if let Some(source_label) = segment
        .source_label
        .as_deref()
        .map(clean_text)
        .filter(|label| !label.is_empty())
    {
        labels.push(source_label);
    }

    if let Some(speaker_label) = segment
        .speaker_label
        .as_deref()
        .map(clean_text)
        .filter(|label| !label.is_empty())
    {
        let label = match segment.speaker_confidence {
            Some(confidence) => format!(
                "{} ({})",
                speaker_label,
                crate::diarization::speaker_confidence_label(confidence)
            ),
            None => speaker_label,
        };
        labels.push(label);
    }

    labels
}

fn ensure_text_column(connection: &Connection, table: &str, column: &str) -> Result<(), AppError> {
    let mut statement = connection.prepare(&format!("PRAGMA table_info({table})"))?;
    let existing_columns = statement
        .query_map([], |row| row.get::<_, String>(1))?
        .collect::<Result<Vec<_>, _>>()?;

    if existing_columns.iter().any(|existing| existing == column) {
        return Ok(());
    }

    connection.execute(&format!("ALTER TABLE {table} ADD COLUMN {column} TEXT"), [])?;
    Ok(())
}

fn speaker_confidence_value(confidence: SpeakerLabelConfidence) -> &'static str {
    match confidence {
        SpeakerLabelConfidence::Low => "low",
        SpeakerLabelConfidence::Medium => "medium",
    }
}

fn parse_speaker_confidence(value: Option<String>) -> Option<SpeakerLabelConfidence> {
    match value.as_deref() {
        Some("low") => Some(SpeakerLabelConfidence::Low),
        Some("medium") => Some(SpeakerLabelConfidence::Medium),
        _ => None,
    }
}

fn now_ms() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|duration| duration.as_millis() as u64)
        .unwrap_or_default()
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::path::Path;

    fn test_service(name: &str) -> TranscriptService {
        let data_dir =
            std::env::temp_dir().join(format!("feelsay-transcript-{name}-{}", std::process::id()));
        let _ = fs::remove_dir_all(&data_dir);
        TranscriptService::new(data_dir)
    }

    fn count_rows(database_path: &Path, table: &str) -> i64 {
        let connection = Connection::open(database_path).expect("open database");
        connection
            .query_row(&format!("SELECT COUNT(*) FROM {table}"), [], |row| {
                row.get::<_, i64>(0)
            })
            .expect("count rows")
    }

    #[test]
    fn transcript_saving_is_disabled_by_default() {
        let service = test_service("disabled-default");

        assert_eq!(
            service.load_settings().unwrap(),
            TranscriptSettings::default()
        );
        assert_eq!(
            service
                .start_session("Default Microphone".to_string())
                .unwrap(),
            None
        );
    }

    #[test]
    fn transcript_session_and_segments_round_trip_to_sqlite() {
        let service = test_service("round-trip");
        service
            .save_settings(TranscriptSettings {
                saving_enabled: true,
            })
            .unwrap();

        let session_id = service
            .start_session(" Default   Microphone ".to_string())
            .unwrap();

        assert!(session_id.is_some());

        service
            .append_segment(TranscriptSegment {
                start_ms: 10,
                end_ms: 900,
                original_text: " hello   world ".to_string(),
                translated_text: None,
                source_label: Some(" mic ".to_string()),
                speaker_label: Some(" Speaker 1 ".to_string()),
                speaker_confidence: Some(SpeakerLabelConfidence::Low),
                is_final: true,
            })
            .unwrap();
        service.finish_session().unwrap();

        assert_eq!(count_rows(&service.database_path, "transcript_sessions"), 1);
        assert_eq!(count_rows(&service.database_path, "transcript_segments"), 1);
    }

    #[test]
    fn disabled_saving_does_not_create_transcript_rows() {
        let service = test_service("disabled-no-rows");

        service
            .start_session("Default Microphone".to_string())
            .unwrap();
        service
            .append_segment(TranscriptSegment {
                start_ms: 0,
                end_ms: 1,
                original_text: "ignored".to_string(),
                translated_text: None,
                source_label: None,
                speaker_label: None,
                speaker_confidence: None,
                is_final: true,
            })
            .unwrap();

        assert!(!service.database_path.exists());
    }

    #[test]
    fn exports_saved_session_as_vtt() {
        let service = test_service("export-vtt");
        service
            .save_settings(TranscriptSettings {
                saving_enabled: true,
            })
            .unwrap();
        let session_id = service
            .start_session("Default Microphone".to_string())
            .unwrap()
            .unwrap();

        service
            .append_segment(TranscriptSegment {
                start_ms: 1_000,
                end_ms: 2_500,
                original_text: "hello world".to_string(),
                translated_text: None,
                source_label: None,
                speaker_label: None,
                speaker_confidence: None,
                is_final: true,
            })
            .unwrap();

        let path = service
            .export_session(session_id, TranscriptExportFormat::Vtt)
            .unwrap();
        let content = fs::read_to_string(path).unwrap();

        assert!(content.starts_with("WEBVTT"));
        assert!(content.contains("00:00:01.000 --> 00:00:02.500"));
        assert!(content.contains("hello world"));
    }

    #[test]
    fn exports_source_labels_with_segments() {
        let service = test_service("export-labels");
        service
            .save_settings(TranscriptSettings {
                saving_enabled: true,
            })
            .unwrap();
        let session_id = service
            .start_session("Multiple sources".to_string())
            .unwrap()
            .unwrap();

        service
            .append_segment(TranscriptSegment {
                start_ms: 0,
                end_ms: 1_000,
                original_text: "hello world".to_string(),
                translated_text: None,
                source_label: Some("Default Microphone".to_string()),
                speaker_label: Some("Speaker 1".to_string()),
                speaker_confidence: Some(SpeakerLabelConfidence::Low),
                is_final: true,
            })
            .unwrap();

        let path = service
            .export_session(session_id, TranscriptExportFormat::Txt)
            .unwrap();
        let content = fs::read_to_string(path).unwrap();

        assert!(content.contains("[Default Microphone | Speaker 1 (low confidence)] hello world"));
    }

    fn segment(text: &str) -> TranscriptSegment {
        TranscriptSegment {
            start_ms: 100,
            end_ms: 900,
            original_text: text.into(),
            translated_text: Some("translated words".into()),
            source_label: Some("Test source".into()),
            speaker_label: None,
            speaker_confidence: None,
            is_final: true,
        }
    }

    #[test]
    fn running_session_can_enable_disable_and_reenable_without_backfill() {
        let service = test_service("live-consent");
        service.start_session("Test source".into()).unwrap();
        let runtime = service.runtime_config().unwrap();
        let disabled = runtime.generation();
        service
            .save_settings(TranscriptSettings {
                saving_enabled: true,
            })
            .unwrap();
        let first = runtime.generation();
        runtime.append_segment(segment("before consent"), disabled);
        runtime.append_segment(segment("saved first"), first);
        assert_eq!(service.list_sessions(100).unwrap()[0].segment_count, 1);
        service
            .save_settings(TranscriptSettings::default())
            .unwrap();
        runtime.append_segment(segment("late inference"), first);
        service
            .save_settings(TranscriptSettings {
                saving_enabled: true,
            })
            .unwrap();
        runtime.append_segment(segment("old generation"), first);
        runtime.append_segment(segment("saved second"), runtime.generation());
        service.finish_session().unwrap();
        let sessions = service.list_sessions(100).unwrap();
        assert_eq!(sessions.len(), 1);
        assert_eq!(sessions[0].segment_count, 2);
        let text = service.read_session(sessions[0].id).unwrap();
        assert!(text.contains("saved first") && text.contains("saved second"));
        assert!(
            !text.contains("before consent")
                && !text.contains("late inference")
                && !text.contains("old generation")
        );
    }

    #[test]
    fn interim_is_rejected_and_all_exports_include_translation() {
        let service = test_service("final-only");
        service
            .save_settings(TranscriptSettings {
                saving_enabled: true,
            })
            .unwrap();
        let id = service
            .start_session("Test source".into())
            .unwrap()
            .unwrap();
        let mut interim = segment("unstable");
        interim.is_final = false;
        service.append_segment(interim).unwrap();
        service.append_segment(segment("complete words")).unwrap();
        for format in [
            TranscriptExportFormat::Txt,
            TranscriptExportFormat::Srt,
            TranscriptExportFormat::Vtt,
            TranscriptExportFormat::Json,
        ] {
            let path = service.export_session(id, format).unwrap();
            let text = fs::read_to_string(path).unwrap();
            assert!(text.contains("translated words"));
            assert!(!text.contains("unstable"));
        }
        assert_eq!(service.list_sessions(100).unwrap()[0].segment_count, 1);
    }

    #[test]
    fn delete_clears_database_exports_and_invalidates_inflight_segments() {
        let service = test_service("delete-privacy");
        service
            .save_settings(TranscriptSettings {
                saving_enabled: true,
            })
            .unwrap();
        let id = service
            .start_session("Test source".into())
            .unwrap()
            .unwrap();
        let runtime = service.runtime_config().unwrap();
        let old = runtime.generation();
        service
            .append_segment(segment("private_unique_phrase_394720"))
            .unwrap();
        let export = service
            .export_session(id, TranscriptExportFormat::Txt)
            .unwrap();
        service.delete_session(id).unwrap();
        runtime.append_segment(segment("resurrected deleted text"), old);
        assert!(service.list_sessions(100).unwrap().is_empty());
        assert!(!Path::new(&export).exists());
        let bytes = fs::read(&service.database_path).unwrap();
        assert!(!bytes
            .windows(b"private_unique_phrase_394720".len())
            .any(|bytes| bytes == b"private_unique_phrase_394720"));
        runtime.append_segment(segment("future speech"), runtime.generation());
        let sessions = service.list_sessions(100).unwrap();
        assert_eq!(sessions.len(), 1);
        assert_ne!(sessions[0].id, id);
    }

    #[test]
    fn storage_failure_stops_saving_without_stopping_captions() {
        let service = test_service("bounded-storage");
        service
            .save_settings(TranscriptSettings {
                saving_enabled: true,
            })
            .unwrap();
        service.start_session("Test source".into()).unwrap();
        service.enqueue_segment(segment(&"x".repeat(65 * 1024)), service.generation());
        service.list_sessions(100).unwrap(); // Writer barrier.
        assert!(!service.status().saving_enabled);
        assert!(service.status().error.is_some());
        assert_eq!(count_rows(&service.database_path, "transcript_segments"), 0);
    }

    #[test]
    fn unavailable_storage_does_not_prevent_caption_session_start() {
        let service = test_service("unavailable-storage");
        service
            .save_settings(TranscriptSettings {
                saving_enabled: true,
            })
            .unwrap();
        fs::create_dir_all(&service.database_path).unwrap();
        assert_eq!(service.start_session("Test source".into()).unwrap(), None);
        assert!(!service.status().saving_enabled);
        assert!(service.status().error.is_some());
    }

    #[test]
    fn full_writer_queue_stops_immediately_and_persists_disabled_state() {
        let service = test_service("writer-overload");
        service
            .save_settings(TranscriptSettings {
                saving_enabled: true,
            })
            .unwrap();
        service.start_session("Test source".into()).unwrap();
        let (entered, waiting) = mpsc::channel();
        let (release, blocked) = mpsc::channel();
        service
            .sender
            .send(Box::new(move |_| {
                entered.send(()).unwrap();
                blocked.recv().unwrap();
            }))
            .unwrap();
        waiting.recv().unwrap();
        for _ in 0..32 {
            service.sender.try_send(Box::new(|_| {})).unwrap();
        }
        service.enqueue_segment(segment("must never reach disk"), service.generation());
        assert!(!service.status().saving_enabled);
        release.send(()).unwrap();
        service.list_sessions(100).unwrap();
        let settings: TranscriptSettings = serde_json::from_str(
            &fs::read_to_string(service.database_path.with_file_name(SETTINGS_FILE_NAME)).unwrap(),
        )
        .unwrap();
        assert!(!settings.saving_enabled);
        assert_eq!(count_rows(&service.database_path, "transcript_segments"), 0);
    }
}
