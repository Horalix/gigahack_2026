"""Probe and decode uploaded local media without trusting filenames or content type."""

import json
import os
import subprocess
import uuid
from pathlib import Path


MAX_UPLOAD_BYTES = 2 * 1024 * 1024 * 1024
MAX_DURATION_MS = 6 * 60 * 60 * 1000
ALLOWED_FORMATS = {
    "wav", "mp3", "flac", "ogg", "mov,mp4,m4a,3gp,3g2,mj2", "matroska,webm"
}
ALLOWED_AUDIO_CODECS = {
    "aac", "mp3", "flac", "pcm_s16le", "pcm_s24le", "pcm_f32le", "pcm_s32le",
    "opus", "vorbis", "alac"
}


class MediaError(ValueError):
    def __init__(self, code: str, message: str, details: dict | None = None):
        super().__init__(message)
        self.code = code
        self.details = details or {}


def _run(args: list[str], timeout: int) -> subprocess.CompletedProcess:
    try:
        result = subprocess.run(
            args, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=timeout, check=False, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except FileNotFoundError as exc:
        raise MediaError("DECODER_UNAVAILABLE", "Local FFmpeg tools are not installed") from exc
    except subprocess.TimeoutExpired as exc:
        raise MediaError("DECODER_TIMEOUT", "Media decoding exceeded its time limit") from exc
    if result.returncode:
        raise MediaError("INVALID_MEDIA", "The media file could not be decoded")
    return result


def probe(source: Path, selected_track_index: int | None) -> dict:
    result = _run([
        "ffprobe", "-v", "error", "-protocol_whitelist", "file,pipe", "-show_entries",
        "format=format_name,duration,start_time:stream=index,codec_type,codec_name,channels,sample_rate,start_time",
        "-of", "json", str(source)
    ], timeout=20)
    try:
        data = json.loads(result.stdout)
        fmt = data["format"]
        format_name = fmt["format_name"]
        duration = float(fmt["duration"])
    except (ValueError, KeyError, TypeError) as exc:
        raise MediaError("INVALID_MEDIA", "The media duration is unavailable") from exc
    if format_name not in ALLOWED_FORMATS:
        raise MediaError("UNSUPPORTED_MEDIA", "This media container is not supported")
    if not 0 < duration * 1000 <= MAX_DURATION_MS:
        raise MediaError("DURATION_LIMIT", "The media duration is outside the supported range")
    tracks = [s for s in data.get("streams", []) if s.get("codec_type") == "audio"]
    if not tracks:
        raise MediaError("NO_AUDIO_TRACK", "The media has no audio track")
    if selected_track_index is None and len(tracks) > 1:
        raise MediaError("AUDIO_TRACK_REQUIRED", "Select an audio track", {"trackIndices": ",".join(str(s["index"]) for s in tracks)})
    track = next((s for s in tracks if int(s["index"]) == selected_track_index), None) if selected_track_index is not None else tracks[0]
    if track is None:
        raise MediaError("INVALID_AUDIO_TRACK", "The selected audio track does not exist")
    if track.get("codec_name") not in ALLOWED_AUDIO_CODECS:
        raise MediaError("UNSUPPORTED_AUDIO_CODEC", "This audio codec is not supported")
    try:
        format_start = float(fmt.get("start_time", 0) or 0)
        stream_start = float(track.get("start_time", format_start) or format_start)
    except (TypeError, ValueError):
        format_start = stream_start = 0
    has_video = any(s.get("codec_type") == "video" for s in data.get("streams", []))
    if has_video:
        media_type = "video/mp4" if format_name == "mov,mp4,m4a,3gp,3g2,mj2" else "video/webm"
    else:
        media_type = {"wav": "audio/wav", "mp3": "audio/mpeg", "flac": "audio/flac",
                      "ogg": "audio/ogg", "mov,mp4,m4a,3gp,3g2,mj2": "audio/mp4",
                      "matroska,webm": "audio/webm"}[format_name]
    return {
        "duration_ms": round(duration * 1000),
        "kind": "video" if has_video else "audio",
        "audio_track_index": int(track["index"]),
        "source_offset_ms": max(0, round((stream_start - format_start) * 1000)),
        "channels": int(track["channels"]) if track.get("channels") else None,
        "sample_rate_hz": int(track["sample_rate"]) if track.get("sample_rate") else None,
        "media_type": media_type,
    }


def decode(source: Path, decoded: Path, selected_track_index: int | None = None) -> dict:
    info = probe(source, selected_track_index)
    temporary = decoded.with_name(decoded.name + f".{uuid.uuid4().hex}.tmp")
    try:
        result = _run([
            "ffmpeg", "-nostdin", "-v", "error", "-protocol_whitelist", "file,pipe",
            "-threads", "2", "-filter_threads", "2", "-max_alloc", "67108864",
            "-i", str(source), "-map", f"0:{info['audio_track_index']}", "-vn", "-sn", "-dn",
            "-ac", "1", "-ar", "16000", "-f", "wav", str(temporary),
        ], timeout=min(900, max(30, info["duration_ms"] // 5000)))
        if not temporary.is_file() or temporary.stat().st_size <= 44:
            raise MediaError("EMPTY_AUDIO", "The selected audio track has no decodable samples")
        if temporary.stat().st_size > info["duration_ms"] * 34 + 1024 * 1024:
            raise MediaError("DECODE_LIMIT", "Decoded audio exceeded the expected size")
        with temporary.open("r+b") as handle:
            os.fsync(handle.fileno())
        os.replace(temporary, decoded)
        info["decode_warning"] = (
            "The decoder reported errors or warnings. Review the source recording for missing speech."
            if result.stderr.strip() else None
        )
        return info
    finally:
        temporary.unlink(missing_ok=True)
