use crate::{
    app_error::AppError,
    asr::{AsrCaptureWorker, AsrRuntimeConfig},
    performance_settings::VadRuntimeConfig,
};
use serde::Serialize;
use std::{
    collections::VecDeque,
    ffi::c_void,
    sync::{
        atomic::{AtomicBool, Ordering},
        Arc, Mutex,
    },
    thread::{self, JoinHandle},
    time::{Duration, Instant, SystemTime, UNIX_EPOCH},
};
use tauri::{AppHandle, Emitter};

const AUDIO_LEVEL_EVENT: &str = "audio-level";
const CAPTURE_SOURCE_PREFIX: &str = "capture:";
const RENDER_SOURCE_PREFIX: &str = "render:";
const SYSTEM_AUDIO_SOURCE_ID: &str = "system-audio";
const CAPTURE_FRAME_QUEUE_CAPACITY: usize = 24;

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct AudioLevelEvent {
    pub source_ids: Vec<String>,
    pub level: f32,
    pub status: AudioLevelStatus,
    pub is_mock: bool,
    pub speech_detected: bool,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub message: Option<String>,
}

#[derive(Debug, Clone, Copy, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum AudioLevelStatus {
    Idle,
    Starting,
    Active,
    Error,
}

pub trait AudioCaptureSession {
    fn stop(&mut self);
}

#[derive(Debug, Clone)]
pub struct PcmAudioFrame {
    pub source_ids: Vec<String>,
    pub samples: Vec<f32>,
    pub sample_rate: u32,
    pub channels: u16,
    pub timestamp_ms: u64,
}

impl PcmAudioFrame {
    fn level(&self) -> f32 {
        rms_f32(&self.samples)
    }
}

pub fn capture_default_loopback_frame(duration: Duration) -> Result<PcmAudioFrame, AppError> {
    capture_windows_default_loopback_frame(duration)
}

pub struct DiagnosticVoiceActivityDetector {
    detector: VoiceActivityDetector,
}

impl DiagnosticVoiceActivityDetector {
    pub fn new() -> Self {
        Self {
            detector: VoiceActivityDetector::new(VadRuntimeConfig::default()),
        }
    }

    pub fn update_frame(&mut self, frame: &PcmAudioFrame) -> bool {
        self.detector.update(frame.level())
    }
}

impl Default for DiagnosticVoiceActivityDetector {
    fn default() -> Self {
        Self::new()
    }
}

#[derive(Debug)]
struct CaptureFrameQueue {
    frames: VecDeque<PcmAudioFrame>,
    capacity: usize,
    dropped_frames: u64,
}

impl CaptureFrameQueue {
    fn new(capacity: usize) -> Self {
        Self {
            frames: VecDeque::with_capacity(capacity),
            capacity,
            dropped_frames: 0,
        }
    }

    fn push(&mut self, frame: PcmAudioFrame) {
        if self.capacity == 0 {
            self.dropped_frames += 1;
            return;
        }

        if self.frames.len() == self.capacity {
            self.frames.pop_front();
            self.dropped_frames += 1;
        }

        self.frames.push_back(frame);
    }

    fn latest_level(&self) -> f32 {
        self.frames.back().map(PcmAudioFrame::level).unwrap_or(0.0)
    }

    #[cfg(test)]
    fn len(&self) -> usize {
        self.frames.len()
    }

    #[cfg(test)]
    fn dropped_frames(&self) -> u64 {
        self.dropped_frames
    }
}

#[derive(Debug, Clone)]
struct VoiceActivityDetector {
    config: VadRuntimeConfig,
    speech_frames: u8,
    silence_frames: u8,
    speech_detected: bool,
}

impl VoiceActivityDetector {
    fn new(config: VadRuntimeConfig) -> Self {
        Self {
            config,
            speech_frames: 0,
            silence_frames: 0,
            speech_detected: false,
        }
    }

    fn update(&mut self, level: f32) -> bool {
        if level >= self.config.speech_level_threshold {
            self.speech_frames = self.speech_frames.saturating_add(1);
            self.silence_frames = 0;
        } else if level <= self.config.silence_level_threshold {
            self.silence_frames = self.silence_frames.saturating_add(1);
            self.speech_frames = 0;
        }

        if self.speech_frames >= self.config.speech_frames {
            self.speech_detected = true;
        } else if self.silence_frames >= self.config.silence_frames {
            self.speech_detected = false;
        }

        self.speech_detected
    }

    #[cfg(test)]
    fn should_forward_to_asr(&self) -> bool {
        self.speech_detected
    }
}

pub struct AudioMeterService {
    session: Mutex<Option<MeterSession>>,
}

impl AudioMeterService {
    pub fn new() -> Self {
        Self {
            session: Mutex::new(None),
        }
    }

    pub fn start_capture(
        &self,
        app: AppHandle,
        source_ids: Vec<String>,
        asr_config: Option<AsrRuntimeConfig>,
    ) -> Result<(), AppError> {
        self.stop()?;
        if source_ids.len() != 1 {
            return Err(AppError::Audio(
                "unsupported source selection; choose one source".into(),
            ));
        }

        if let Some(endpoint_id) = microphone_endpoint_id(&source_ids) {
            return self.start_microphone_meter(app, source_ids, endpoint_id, asr_config);
        }

        if let Some(endpoint_id) = loopback_endpoint_id(&source_ids) {
            return self.start_loopback_meter(app, source_ids, endpoint_id, asr_config);
        }

        #[cfg(target_os = "windows")]
        if source_ids.len() == 1 {
            if let Some(process_id) = crate::application_audio::process_id(&source_ids[0]) {
                if !crate::application_audio::source_is_alive(&source_ids[0]) {
                    return Err(AppError::Audio("selected application closed".into()));
                }
                return self.start_application_meter(app, source_ids, process_id, asr_config);
            }
        }
        Err(AppError::Audio(
            "unsupported audio source; select system audio, a microphone, or one application"
                .into(),
        ))
    }

    #[cfg(target_os = "windows")]
    fn start_application_meter(
        &self,
        app: AppHandle,
        source_ids: Vec<String>,
        process_id: u32,
        asr_config: Option<AsrRuntimeConfig>,
    ) -> Result<(), AppError> {
        let mut session = self
            .session
            .lock()
            .map_err(|error| AppError::Audio(error.to_string()))?;
        let stop_requested = Arc::new(AtomicBool::new(false));
        let stop = stop_requested.clone();
        let handle = thread::Builder::new()
            .name("feelsay-application-audio".into())
            .spawn(move || {
                let _ = emit_audio_level(
                    &app,
                    &source_ids,
                    0.0,
                    AudioLevelStatus::Starting,
                    false,
                    false,
                    None,
                );
                let result =
                    run_application_capture(&app, &source_ids, process_id, &stop, asr_config);
                match result {
                    Ok(()) => {
                        let _ = emit_audio_level(
                            &app,
                            &source_ids,
                            0.0,
                            AudioLevelStatus::Idle,
                            false,
                            false,
                            None,
                        );
                    }
                    Err(error) => {
                        let _ = emit_audio_level(
                            &app,
                            &source_ids,
                            0.0,
                            AudioLevelStatus::Error,
                            false,
                            false,
                            Some(error.user_message()),
                        );
                    }
                }
            })
            .map_err(|error| AppError::Audio(error.to_string()))?;
        *session = Some(MeterSession::Microphone(RealAudioMeterSession {
            stop_requested,
            handle: Some(handle),
        }));
        Ok(())
    }

    fn start_microphone_meter(
        &self,
        app: AppHandle,
        source_ids: Vec<String>,
        endpoint_id: String,
        asr_config: Option<AsrRuntimeConfig>,
    ) -> Result<(), AppError> {
        let mut session = self
            .session
            .lock()
            .map_err(|error| AppError::Audio(error.to_string()))?;
        let stop_requested = Arc::new(AtomicBool::new(false));
        let thread_stop_requested = Arc::clone(&stop_requested);
        let thread_source_ids = source_ids.clone();

        let handle = thread::Builder::new()
            .name("feelsay-microphone-meter".to_string())
            .spawn(move || {
                let _ = emit_audio_level(
                    &app,
                    &thread_source_ids,
                    0.0,
                    AudioLevelStatus::Starting,
                    false,
                    false,
                    None,
                );

                if let Err(error) = run_windows_microphone_meter(
                    &app,
                    &thread_source_ids,
                    &endpoint_id,
                    &thread_stop_requested,
                    asr_config,
                ) {
                    let message = error.user_message();
                    let _ = emit_audio_level(
                        &app,
                        &thread_source_ids,
                        0.0,
                        AudioLevelStatus::Error,
                        false,
                        false,
                        Some(message),
                    );
                }
            })
            .map_err(|error| AppError::Audio(error.to_string()))?;

        *session = Some(MeterSession::Microphone(RealAudioMeterSession {
            stop_requested,
            handle: Some(handle),
        }));

        Ok(())
    }

    fn start_loopback_meter(
        &self,
        app: AppHandle,
        source_ids: Vec<String>,
        endpoint_id: Option<String>,
        asr_config: Option<AsrRuntimeConfig>,
    ) -> Result<(), AppError> {
        let mut session = self
            .session
            .lock()
            .map_err(|error| AppError::Audio(error.to_string()))?;
        let stop_requested = Arc::new(AtomicBool::new(false));
        let thread_stop_requested = Arc::clone(&stop_requested);
        let thread_source_ids = source_ids.clone();

        let handle = thread::Builder::new()
            .name("feelsay-loopback-meter".to_string())
            .spawn(move || {
                let _ = emit_audio_level(
                    &app,
                    &thread_source_ids,
                    0.0,
                    AudioLevelStatus::Starting,
                    false,
                    false,
                    None,
                );

                if let Err(error) = run_windows_loopback_meter(
                    &app,
                    &thread_source_ids,
                    endpoint_id.as_deref(),
                    &thread_stop_requested,
                    asr_config,
                ) {
                    let message = error.user_message();
                    let _ = emit_audio_level(
                        &app,
                        &thread_source_ids,
                        0.0,
                        AudioLevelStatus::Error,
                        false,
                        false,
                        Some(message),
                    );
                }
            })
            .map_err(|error| AppError::Audio(error.to_string()))?;

        *session = Some(MeterSession::Microphone(RealAudioMeterSession {
            stop_requested,
            handle: Some(handle),
        }));

        Ok(())
    }

    pub fn stop(&self) -> Result<(), AppError> {
        let session = self
            .session
            .lock()
            .map_err(|error| AppError::Audio(error.to_string()))?
            .take();

        if let Some(mut session) = session {
            session.stop();
        }

        Ok(())
    }
}

impl Default for AudioMeterService {
    fn default() -> Self {
        Self::new()
    }
}

enum MeterSession {
    Microphone(RealAudioMeterSession),
}

impl AudioCaptureSession for MeterSession {
    fn stop(&mut self) {
        match self {
            Self::Microphone(session) => session.stop(),
        }
    }
}

struct RealAudioMeterSession {
    stop_requested: Arc<AtomicBool>,
    handle: Option<JoinHandle<()>>,
}

impl AudioCaptureSession for RealAudioMeterSession {
    fn stop(&mut self) {
        self.stop_requested.store(true, Ordering::Relaxed);

        if let Some(handle) = self.handle.take() {
            let _ = handle.join();
        }
    }
}

impl Drop for RealAudioMeterSession {
    fn drop(&mut self) {
        self.stop();
    }
}

fn emit_audio_level(
    app: &AppHandle,
    source_ids: &[String],
    level: f32,
    status: AudioLevelStatus,
    is_mock: bool,
    speech_detected: bool,
    message: Option<String>,
) -> Result<(), tauri::Error> {
    app.emit(
        AUDIO_LEVEL_EVENT,
        AudioLevelEvent {
            source_ids: source_ids.to_vec(),
            level,
            status,
            is_mock,
            speech_detected,
            message,
        },
    )
}

fn microphone_endpoint_id(source_ids: &[String]) -> Option<String> {
    source_ids
        .iter()
        .find_map(|source_id| source_id.strip_prefix(CAPTURE_SOURCE_PREFIX))
        .map(str::to_string)
}

fn loopback_endpoint_id(source_ids: &[String]) -> Option<Option<String>> {
    if source_ids
        .iter()
        .any(|source_id| source_id == SYSTEM_AUDIO_SOURCE_ID)
    {
        return Some(None);
    }

    source_ids
        .iter()
        .find_map(|source_id| source_id.strip_prefix(RENDER_SOURCE_PREFIX))
        .map(|endpoint_id| Some(endpoint_id.to_string()))
}

#[cfg(target_os = "windows")]
fn capture_windows_default_loopback_frame(duration: Duration) -> Result<PcmAudioFrame, AppError> {
    use windows::Win32::{
        Media::Audio::{eConsole, eRender, IMMDeviceEnumerator, MMDeviceEnumerator},
        System::Com::{
            CoCreateInstance, CoInitializeEx, CoUninitialize, CLSCTX_ALL, COINIT_MULTITHREADED,
        },
    };

    unsafe {
        CoInitializeEx(None, COINIT_MULTITHREADED)
            .ok()
            .map_err(|error| AppError::Audio(error.to_string()))?;
    }

    let result = unsafe {
        let enumerator = CoCreateInstance::<_, IMMDeviceEnumerator>(
            &MMDeviceEnumerator,
            None::<&windows::core::IUnknown>,
            CLSCTX_ALL,
        )
        .map_err(|error| AppError::Audio(error.to_string()))?;
        let device = enumerator
            .GetDefaultAudioEndpoint(eRender, eConsole)
            .map_err(|error| AppError::Audio(error.to_string()))?;

        capture_loopback_samples(device, duration)
    };

    unsafe {
        CoUninitialize();
    }

    result
}

#[cfg(not(target_os = "windows"))]
fn capture_windows_default_loopback_frame(_duration: Duration) -> Result<PcmAudioFrame, AppError> {
    Err(AppError::Audio(
        "system audio capture diagnostic is Windows-only for now".to_string(),
    ))
}

#[cfg(target_os = "windows")]
fn run_windows_microphone_meter(
    app: &AppHandle,
    source_ids: &[String],
    endpoint_id: &str,
    stop_requested: &AtomicBool,
    asr_config: Option<AsrRuntimeConfig>,
) -> Result<(), AppError> {
    use windows::{
        core::HSTRING,
        Win32::{
            Media::Audio::{eCapture, eConsole, IMMDeviceEnumerator, MMDeviceEnumerator},
            System::Com::{
                CoCreateInstance, CoInitializeEx, CoUninitialize, CLSCTX_ALL, COINIT_MULTITHREADED,
            },
        },
    };

    unsafe {
        CoInitializeEx(None, COINIT_MULTITHREADED)
            .ok()
            .map_err(|error| AppError::Audio(error.to_string()))?;
    }

    let result = unsafe {
        let enumerator = CoCreateInstance::<_, IMMDeviceEnumerator>(
            &MMDeviceEnumerator,
            None::<&windows::core::IUnknown>,
            CLSCTX_ALL,
        )
        .map_err(|error| AppError::Audio(error.to_string()))?;
        let device = if endpoint_id.is_empty() {
            enumerator
                .GetDefaultAudioEndpoint(eCapture, eConsole)
                .map_err(|error| AppError::Audio(error.to_string()))?
        } else {
            enumerator
                .GetDevice(&HSTRING::from(endpoint_id))
                .map_err(|error| AppError::Audio(error.to_string()))?
        };

        capture_audio_levels(app, source_ids, stop_requested, device, false, asr_config)
    };

    unsafe {
        CoUninitialize();
    }

    result
}

#[cfg(target_os = "windows")]
fn run_windows_loopback_meter(
    app: &AppHandle,
    source_ids: &[String],
    endpoint_id: Option<&str>,
    stop_requested: &AtomicBool,
    asr_config: Option<AsrRuntimeConfig>,
) -> Result<(), AppError> {
    use windows::{
        core::HSTRING,
        Win32::{
            Media::Audio::{eConsole, eRender, IMMDeviceEnumerator, MMDeviceEnumerator},
            System::Com::{
                CoCreateInstance, CoInitializeEx, CoUninitialize, CLSCTX_ALL, COINIT_MULTITHREADED,
            },
        },
    };

    unsafe {
        CoInitializeEx(None, COINIT_MULTITHREADED)
            .ok()
            .map_err(|error| AppError::Audio(error.to_string()))?;
    }

    let result = unsafe {
        let enumerator = CoCreateInstance::<_, IMMDeviceEnumerator>(
            &MMDeviceEnumerator,
            None::<&windows::core::IUnknown>,
            CLSCTX_ALL,
        )
        .map_err(|error| AppError::Audio(error.to_string()))?;
        let device = if let Some(endpoint_id) = endpoint_id {
            enumerator
                .GetDevice(&HSTRING::from(endpoint_id))
                .map_err(|error| AppError::Audio(error.to_string()))?
        } else {
            enumerator
                .GetDefaultAudioEndpoint(eRender, eConsole)
                .map_err(|error| AppError::Audio(error.to_string()))?
        };

        capture_audio_levels(app, source_ids, stop_requested, device, true, asr_config)
    };

    unsafe {
        CoUninitialize();
    }

    result
}

#[cfg(not(target_os = "windows"))]
fn run_windows_loopback_meter(
    _app: &AppHandle,
    _source_ids: &[String],
    _endpoint_id: Option<&str>,
    _stop_requested: &AtomicBool,
    _asr_config: Option<AsrRuntimeConfig>,
) -> Result<(), AppError> {
    Err(AppError::Audio(
        "system audio meter is Windows-only for now".to_string(),
    ))
}

#[cfg(not(target_os = "windows"))]
fn run_windows_microphone_meter(
    _app: &AppHandle,
    _source_ids: &[String],
    _endpoint_id: &str,
    _stop_requested: &AtomicBool,
    _asr_config: Option<AsrRuntimeConfig>,
) -> Result<(), AppError> {
    Err(AppError::Audio(
        "real microphone meter is Windows-only for now".to_string(),
    ))
}

#[cfg(target_os = "windows")]
unsafe fn capture_audio_levels(
    app: &AppHandle,
    source_ids: &[String],
    stop_requested: &AtomicBool,
    device: windows::Win32::Media::Audio::IMMDevice,
    loopback: bool,
    asr_config: Option<AsrRuntimeConfig>,
) -> Result<(), AppError> {
    use windows::Win32::{
        Media::Audio::{
            IAudioCaptureClient, IAudioClient, AUDCLNT_SHAREMODE_SHARED,
            AUDCLNT_STREAMFLAGS_LOOPBACK, AUDCLNT_STREAMFLAGS_NOPERSIST,
        },
        System::Com::CLSCTX_ALL,
    };

    let audio_client = device
        .Activate::<IAudioClient>(CLSCTX_ALL, None)
        .map_err(|error| AppError::Audio(error.to_string()))?;
    // Request a known PCM format; WASAPI performs shared-mode conversion.
    let format = windows::Win32::Media::Audio::WAVEFORMATEX {
        wFormatTag: 1,
        nChannels: 2,
        nSamplesPerSec: 48_000,
        nAvgBytesPerSec: 192_000,
        nBlockAlign: 4,
        wBitsPerSample: 16,
        cbSize: 0,
    };
    let stream_flags = AUDCLNT_STREAMFLAGS_NOPERSIST
        | windows::Win32::Media::Audio::AUDCLNT_STREAMFLAGS_AUTOCONVERTPCM
        | if loopback {
            AUDCLNT_STREAMFLAGS_LOOPBACK
        } else {
            0
        };
    audio_client
        .Initialize(
            AUDCLNT_SHAREMODE_SHARED,
            stream_flags,
            1_000_000,
            0,
            &format,
            None,
        )
        .map_err(|error| AppError::Audio(error.to_string()))?;

    let capture_client = audio_client
        .GetService::<IAudioCaptureClient>()
        .map_err(|error| AppError::Audio(error.to_string()))?;
    let result = poll_microphone_packets(
        app,
        source_ids,
        stop_requested,
        &audio_client,
        &capture_client,
        format,
        asr_config,
    );
    let _ = audio_client.Stop();
    let _ = emit_audio_level(
        app,
        source_ids,
        0.0,
        AudioLevelStatus::Idle,
        false,
        false,
        None,
    );

    result
}

#[cfg(target_os = "windows")]
unsafe fn capture_loopback_samples(
    device: windows::Win32::Media::Audio::IMMDevice,
    duration: Duration,
) -> Result<PcmAudioFrame, AppError> {
    use windows::Win32::{
        Media::Audio::{
            IAudioCaptureClient, IAudioClient, AUDCLNT_SHAREMODE_SHARED,
            AUDCLNT_STREAMFLAGS_LOOPBACK, AUDCLNT_STREAMFLAGS_NOPERSIST,
        },
        System::Com::{CoTaskMemFree, CLSCTX_ALL},
    };

    let audio_client = device
        .Activate::<IAudioClient>(CLSCTX_ALL, None)
        .map_err(|error| AppError::Audio(error.to_string()))?;
    let mix_format = audio_client
        .GetMixFormat()
        .map_err(|error| AppError::Audio(error.to_string()))?;
    let format = *mix_format;

    audio_client
        .Initialize(
            AUDCLNT_SHAREMODE_SHARED,
            AUDCLNT_STREAMFLAGS_NOPERSIST | AUDCLNT_STREAMFLAGS_LOOPBACK,
            1_000_000,
            0,
            mix_format,
            None,
        )
        .map_err(|error| {
            CoTaskMemFree(Some(mix_format.cast::<c_void>()));
            AppError::Audio(error.to_string())
        })?;

    CoTaskMemFree(Some(mix_format.cast::<c_void>()));

    let capture_client = audio_client
        .GetService::<IAudioCaptureClient>()
        .map_err(|error| AppError::Audio(error.to_string()))?;
    audio_client
        .Start()
        .map_err(|error| AppError::Audio(error.to_string()))?;

    let started_at = Instant::now();
    let source_ids = vec!["diagnostic:system-audio".to_string()];
    let mut samples = Vec::new();

    while started_at.elapsed() < duration {
        let mut packet_size = capture_client
            .GetNextPacketSize()
            .map_err(|error| AppError::Audio(error.to_string()))?;

        if packet_size == 0 {
            thread::sleep(Duration::from_millis(20));
            continue;
        }

        while packet_size > 0 {
            let mut data = std::ptr::null_mut();
            let mut frames = 0;
            let mut flags = 0;
            capture_client
                .GetBuffer(&mut data, &mut frames, &mut flags, None, None)
                .map_err(|error| AppError::Audio(error.to_string()))?;

            if flags & windows::Win32::Media::Audio::AUDCLNT_BUFFERFLAGS_SILENT.0 as u32 == 0 {
                if let Some(frame) = pcm_frame_from_buffer(data, frames, format, &source_ids) {
                    samples.extend(frame.samples);
                }
            }

            capture_client
                .ReleaseBuffer(frames)
                .map_err(|error| AppError::Audio(error.to_string()))?;
            packet_size = capture_client
                .GetNextPacketSize()
                .map_err(|error| AppError::Audio(error.to_string()))?;
        }
    }

    let _ = audio_client.Stop();

    Ok(PcmAudioFrame {
        source_ids,
        samples,
        sample_rate: format.nSamplesPerSec,
        channels: format.nChannels,
        timestamp_ms: current_timestamp_ms(),
    })
}

#[cfg(target_os = "windows")]
fn run_application_capture(
    app: &AppHandle,
    source_ids: &[String],
    process_id: u32,
    stop: &AtomicBool,
    config: Option<AsrRuntimeConfig>,
) -> Result<(), AppError> {
    use windows::Win32::{
        Media::Audio::*,
        System::Com::{CoInitializeEx, CoUninitialize, COINIT_MULTITHREADED},
    };
    unsafe {
        CoInitializeEx(None, COINIT_MULTITHREADED)
            .ok()
            .map_err(|error| AppError::Audio(error.to_string()))?;
        let result = (|| {
            let client = crate::application_audio::activate(process_id)?;
            let format = WAVEFORMATEX {
                wFormatTag: 1,
                nChannels: 2,
                nSamplesPerSec: 48_000,
                nAvgBytesPerSec: 192_000,
                nBlockAlign: 4,
                wBitsPerSample: 16,
                cbSize: 0,
            };
            client
                .Initialize(
                    AUDCLNT_SHAREMODE_SHARED,
                    AUDCLNT_STREAMFLAGS_LOOPBACK | AUDCLNT_STREAMFLAGS_AUTOCONVERTPCM,
                    1_000_000,
                    0,
                    &format,
                    None,
                )
                .map_err(|error| AppError::Audio(error.to_string()))?;
            let capture = client
                .GetService::<IAudioCaptureClient>()
                .map_err(|error| AppError::Audio(error.to_string()))?;
            let result =
                poll_microphone_packets(app, source_ids, stop, &client, &capture, format, config);
            let _ = client.Stop();
            result
        })();
        CoUninitialize();
        result
    }
}

#[cfg(target_os = "windows")]
unsafe fn poll_microphone_packets(
    app: &AppHandle,
    source_ids: &[String],
    stop_requested: &AtomicBool,
    audio_client: &windows::Win32::Media::Audio::IAudioClient,
    capture_client: &windows::Win32::Media::Audio::IAudioCaptureClient,
    format: windows::Win32::Media::Audio::WAVEFORMATEX,
    asr_config: Option<AsrRuntimeConfig>,
) -> Result<(), AppError> {
    use windows::Win32::Media::Audio::AUDCLNT_BUFFERFLAGS_SILENT;

    let mut frame_queue = CaptureFrameQueue::new(CAPTURE_FRAME_QUEUE_CAPACITY);
    let vad_config = asr_config
        .as_ref()
        .map(|config| config.performance.vad)
        .unwrap_or_default();
    let mut vad = VoiceActivityDetector::new(vad_config);
    let default_output = if source_ids.iter().any(|id| id == SYSTEM_AUDIO_SOURCE_ID) {
        Some(default_output_id()?)
    } else {
        None
    };
    let asr_worker = match asr_config {
        Some(config) => Some(AsrCaptureWorker::start(config)?),
        None => None,
    };
    if stop_requested.load(Ordering::Relaxed) {
        return Ok(());
    }
    audio_client
        .Start()
        .map_err(|error| AppError::Audio(error.to_string()))?;
    let _ = emit_audio_level(
        app,
        source_ids,
        0.0,
        AudioLevelStatus::Active,
        false,
        false,
        None,
    );
    let mut last_meter_emit = Instant::now();
    let mut last_packet = Instant::now();
    let mut last_source_check = Instant::now();
    while !stop_requested.load(Ordering::Relaxed) {
        if let Some(error) = asr_worker.as_ref().and_then(AsrCaptureWorker::take_error) {
            return Err(error);
        }
        if last_source_check.elapsed() >= Duration::from_secs(1) {
            last_source_check = Instant::now();
            if let Some(original) = &default_output {
                if default_output_id()? != *original {
                    return Err(AppError::Audio("default output changed".into()));
                }
            }
            if source_ids.first().is_some_and(|source| {
                source.starts_with("window:") && !crate::application_audio::source_is_alive(source)
            }) {
                return Err(AppError::Audio("selected application closed".into()));
            }
        }
        let mut packet_size = capture_client
            .GetNextPacketSize()
            .map_err(|error| AppError::Audio(error.to_string()))?;

        if packet_size == 0 {
            if last_packet.elapsed() >= Duration::from_millis(100) {
                if let Some(worker) = &asr_worker {
                    worker.push_frame(
                        &PcmAudioFrame {
                            source_ids: Vec::new(),
                            samples: Vec::new(),
                            sample_rate: 16_000,
                            channels: 1,
                            timestamp_ms: current_timestamp_ms(),
                        },
                        false,
                    );
                }
                if last_meter_emit.elapsed() >= Duration::from_millis(100) {
                    let _ = emit_audio_level(
                        app,
                        source_ids,
                        0.0,
                        AudioLevelStatus::Active,
                        false,
                        false,
                        None,
                    );
                    last_meter_emit = Instant::now();
                }
            }
            thread::sleep(Duration::from_millis(35));
            continue;
        }

        while packet_size > 0 {
            let mut data = std::ptr::null_mut();
            let mut frames = 0;
            let mut flags = 0;
            capture_client
                .GetBuffer(&mut data, &mut frames, &mut flags, None, None)
                .map_err(|error| AppError::Audio(error.to_string()))?;

            let (level, frame) = if flags & AUDCLNT_BUFFERFLAGS_SILENT.0 as u32 != 0 {
                (0.0, None)
            } else if let Some(frame) = pcm_frame_from_buffer(data, frames, format, source_ids) {
                frame_queue.push(frame);
                (frame_queue.latest_level(), frame_queue.frames.back())
            } else {
                (0.0, None)
            };

            capture_client
                .ReleaseBuffer(frames)
                .map_err(|error| AppError::Audio(error.to_string()))?;
            let speech_detected = vad.update(level);
            last_packet = Instant::now();
            if let (Some(worker), Some(frame)) = (asr_worker.as_ref(), frame) {
                worker.push_frame(frame, speech_detected);
            } else if let Some(worker) = &asr_worker {
                worker.push_frame(
                    &PcmAudioFrame {
                        source_ids: Vec::new(),
                        samples: Vec::new(),
                        sample_rate: 16_000,
                        channels: 1,
                        timestamp_ms: current_timestamp_ms(),
                    },
                    false,
                );
            }
            if last_meter_emit.elapsed() >= Duration::from_millis(100) {
                let _ = emit_audio_level(
                    app,
                    source_ids,
                    level,
                    AudioLevelStatus::Active,
                    false,
                    speech_detected,
                    None,
                );
                last_meter_emit = Instant::now();
            }

            packet_size = capture_client
                .GetNextPacketSize()
                .map_err(|error| AppError::Audio(error.to_string()))?;
        }
    }

    Ok(())
}

#[cfg(target_os = "windows")]
fn default_output_id() -> Result<String, AppError> {
    use windows::Win32::{
        Media::Audio::{eConsole, eRender, IMMDeviceEnumerator, MMDeviceEnumerator},
        System::Com::{CoCreateInstance, CoTaskMemFree, CLSCTX_ALL},
    };
    unsafe {
        let enumerator: IMMDeviceEnumerator =
            CoCreateInstance(&MMDeviceEnumerator, None, CLSCTX_ALL)
                .map_err(|error| AppError::Audio(error.to_string()))?;
        let endpoint = enumerator
            .GetDefaultAudioEndpoint(eRender, eConsole)
            .map_err(|error| AppError::Audio(error.to_string()))?;
        let id = endpoint
            .GetId()
            .map_err(|error| AppError::Audio(error.to_string()))?;
        let value = id
            .to_string()
            .map_err(|error| AppError::Audio(error.to_string()));
        CoTaskMemFree(Some(id.0.cast()));
        value
    }
}

#[cfg(target_os = "windows")]
fn pcm_frame_from_buffer(
    data: *mut u8,
    frames: u32,
    format: windows::Win32::Media::Audio::WAVEFORMATEX,
    source_ids: &[String],
) -> Option<PcmAudioFrame> {
    if data.is_null() || frames == 0 || format.nChannels == 0 {
        return None;
    }

    let channels = format.nChannels as usize;
    let samples = frames as usize * channels;
    let normalized_samples = match (format.wBitsPerSample, format.wFormatTag) {
        (32, tag) if tag == 3 || tag == 65534 => unsafe {
            normalize_f32(std::slice::from_raw_parts(data.cast::<f32>(), samples))
        },
        (16, _) => unsafe {
            normalize_i16(std::slice::from_raw_parts(data.cast::<i16>(), samples))
        },
        _ => return None,
    };

    Some(PcmAudioFrame {
        source_ids: source_ids.to_vec(),
        samples: normalized_samples,
        sample_rate: format.nSamplesPerSec,
        channels: format.nChannels,
        timestamp_ms: current_timestamp_ms(),
    })
}

fn current_timestamp_ms() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|duration| duration.as_millis().min(u128::from(u64::MAX)) as u64)
        .unwrap_or(0)
}

fn normalize_f32(samples: &[f32]) -> Vec<f32> {
    samples
        .iter()
        .map(|sample| sample.clamp(-1.0, 1.0))
        .collect()
}

fn normalize_i16(samples: &[i16]) -> Vec<f32> {
    samples
        .iter()
        .map(|sample| (*sample as f32 / i16::MAX as f32).clamp(-1.0, 1.0))
        .collect()
}

fn rms_f32(samples: &[f32]) -> f32 {
    if samples.is_empty() {
        return 0.0;
    }

    let sum = samples
        .iter()
        .map(|sample| sample.clamp(-1.0, 1.0).powi(2))
        .sum::<f32>();

    (sum / samples.len() as f32).sqrt().clamp(0.0, 1.0)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn test_frame(value: f32) -> PcmAudioFrame {
        PcmAudioFrame {
            source_ids: vec!["capture:test".to_string()],
            samples: vec![value],
            sample_rate: 48_000,
            channels: 1,
            timestamp_ms: 1,
        }
    }

    #[test]
    fn capture_frame_queue_drops_oldest_when_full() {
        let mut queue = CaptureFrameQueue::new(2);

        queue.push(test_frame(0.1));
        queue.push(test_frame(0.2));
        queue.push(test_frame(0.3));

        assert_eq!(queue.len(), 2);
        assert_eq!(queue.dropped_frames(), 1);
        assert!((queue.latest_level() - 0.3).abs() < f32::EPSILON);
    }

    #[test]
    fn capture_frame_queue_with_zero_capacity_drops_everything() {
        let mut queue = CaptureFrameQueue::new(0);

        queue.push(test_frame(0.8));

        assert_eq!(queue.len(), 0);
        assert_eq!(queue.dropped_frames(), 1);
        assert_eq!(queue.latest_level(), 0.0);
    }

    #[test]
    fn normalizes_i16_samples_to_unit_float_range() {
        let samples = normalize_i16(&[i16::MIN, 0, i16::MAX]);

        assert_eq!(samples[1], 0.0);
        assert_eq!(samples[2], 1.0);
        assert!(samples[0] >= -1.0);
    }

    #[test]
    fn voice_activity_requires_consecutive_speech_frames() {
        let config = VadRuntimeConfig::default();
        let mut vad = VoiceActivityDetector::new(config);

        assert!(!vad.update(config.speech_level_threshold));
        assert!(vad.update(config.speech_level_threshold));
        assert!(vad.should_forward_to_asr());
    }

    #[test]
    fn voice_activity_releases_after_consecutive_silence_frames() {
        let config = VadRuntimeConfig::default();
        let mut vad = VoiceActivityDetector::new(config);

        assert!(!vad.update(config.speech_level_threshold));
        assert!(vad.update(config.speech_level_threshold));

        for _ in 0..config.silence_frames - 1 {
            assert!(vad.update(config.silence_level_threshold));
        }

        assert!(!vad.update(config.silence_level_threshold));
        assert!(!vad.should_forward_to_asr());
    }
}
