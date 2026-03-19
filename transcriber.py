"""
transcriber.py — Transcripción de audio con OpenAI Whisper API.

Responsabilidades:
- Re-encodar audio a 16kHz mono 32k (workaround para límite 25MB de Whisper API)
- Transcribir en español con timestamps por palabra y por segmento
- Formatear transcripción para prompts de Claude
- Ajustar timestamps a límites naturales de palabras (snap_to_word_boundaries)
"""

import os
import subprocess
import tempfile

import openai

from config import (
    AUDIO_BITRATE,
    AUDIO_CHANNELS,
    AUDIO_FORMAT,
    AUDIO_SAMPLE_RATE,
    WHISPER_LANGUAGE,
    WHISPER_MODEL,
    get_secret,
)


def extract_audio(audio_path: str, audio_output_path: str) -> str:
    """
    Re-encodea el audio a MP3 mono 16kHz 32kbps para la Whisper API.

    Un episodio de podcast típico (1h, 128kbps) pesa ~55MB.
    Re-encodado a 16kHz mono 32k queda en ~7MB — bajo el límite de 25MB de Whisper.

    Args:
        audio_path:        ruta al audio fuente (MP3, M4A, WAV, etc.)
        audio_output_path: ruta de destino para el MP3

    Returns:
        audio_output_path
    """
    cmd = [
        "ffmpeg",
        "-y",
        "-i", audio_path,
        "-vn",                            # sin video (no-op si ya es audio)
        "-ar", str(AUDIO_SAMPLE_RATE),    # 16000 Hz
        "-ac", str(AUDIO_CHANNELS),       # mono
        "-b:a", AUDIO_BITRATE,            # 32k
        "-f", AUDIO_FORMAT,               # mp3
        audio_output_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"ffmpeg falló al extraer audio.\n"
            f"Error: {result.stderr}"
        )
    return audio_output_path


def transcribe(audio_path: str, language: str = WHISPER_LANGUAGE) -> dict:
    """
    Transcribe el audio usando la Whisper API de OpenAI.

    Flujo:
        1. Re-encodea audio a MP3 16kHz mono (evita límite 25MB)
        2. Envía a Whisper API con verbose_json y timestamps por palabra
        3. Retorna dict estructurado con texto, segmentos y palabras
        4. Limpia el archivo temporal de audio

    Args:
        audio_path: ruta al audio (MP3, M4A, WAV)
        language:   código de idioma ISO 639-1 (default: "es")

    Returns:
        {
            "text":     str   — transcript completo,
            "segments": list  — [{start, end, text}, ...] por oración/segmento,
            "words":    list  — [{start, end, word}, ...] por palabra
        }
    """
    client = openai.OpenAI(api_key=get_secret("OPENAI_API_KEY"))

    # Crear archivo temporal para el audio
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
        tmp_audio_path = tmp.name

    try:
        extract_audio(audio_path, tmp_audio_path)

        with open(tmp_audio_path, "rb") as audio_file:
            result = client.audio.transcriptions.create(
                model=WHISPER_MODEL,
                file=audio_file,
                response_format="verbose_json",
                language=language,
                timestamp_granularities=["segment", "word"],
            )

        # Normalizar la respuesta a dict consistente
        segments = []
        if hasattr(result, "segments") and result.segments:
            for seg in result.segments:
                segments.append({
                    "start": float(seg.start),
                    "end":   float(seg.end),
                    "text":  seg.text.strip(),
                })

        words = []
        if hasattr(result, "words") and result.words:
            for w in result.words:
                words.append({
                    "start": float(w.start),
                    "end":   float(w.end),
                    "word":  w.word.strip(),
                })

        return {
            "text":     result.text,
            "segments": segments,
            "words":    words,
        }

    finally:
        if os.path.exists(tmp_audio_path):
            os.unlink(tmp_audio_path)


def snap_to_word_boundaries(
    start_sec: float,
    end_sec: float,
    words: list,
    tolerance: float = 3.0,
) -> tuple:
    """
    Ajusta start_sec y end_sec a los límites naturales de palabras más cercanos.

    Garantiza que los clips no corten a mitad de palabra:
    - start_sec → inicio de la palabra más cercana (dentro de ±tolerance segundos)
    - end_sec   → fin de la palabra más cercana (dentro de ±tolerance segundos)

    Args:
        start_sec:  tiempo de inicio sugerido (segundos)
        end_sec:    tiempo de fin sugerido (segundos)
        words:      lista de words [{start, end, word}] del transcript completo
        tolerance:  margen máximo de ajuste en segundos (default: 3.0)

    Returns:
        (snapped_start, snapped_end) — ambos ajustados a límites de palabras
    """
    if not words:
        return start_sec, end_sec

    # Snap start → inicio de la palabra más cercana a start_sec
    candidates_start = [w for w in words if abs(w["start"] - start_sec) <= tolerance]
    if candidates_start:
        snapped_start = min(candidates_start, key=lambda w: abs(w["start"] - start_sec))["start"]
    else:
        snapped_start = start_sec

    # Snap end → fin de la palabra más cercana a end_sec
    candidates_end = [w for w in words if abs(w["end"] - end_sec) <= tolerance]
    if candidates_end:
        snapped_end = min(candidates_end, key=lambda w: abs(w["end"] - end_sec))["end"]
    else:
        snapped_end = end_sec

    return snapped_start, snapped_end


def format_for_claude(transcription: dict, max_chars: int = 150000) -> str:
    """
    Formatea la transcripción con timestamps para el prompt de Claude.

    Agrupa palabras en líneas de ~10 palabras con timestamp de inicio.
    Útil para que Claude pueda identificar momentos por tiempo.

    Args:
        transcription: dict retornado por transcribe()
        max_chars:     límite de caracteres (Claude tiene ventana de contexto grande
                       pero queremos prompts eficientes)

    Returns:
        Texto formateado:
            [00:05] Y bueno cuando yo empecé a trabajar en esto
            [00:12] me di cuenta de que el problema era mucho más
            ...
    """
    words = transcription.get("words", [])

    if not words:
        # Fallback a segmentos si no hay word-level timestamps
        segments = transcription.get("segments", [])
        lines = []
        for seg in segments:
            t = _seconds_to_mmss(seg["start"])
            lines.append(f"[{t}] {seg['text']}")
        text = "\n".join(lines)
        return text[:max_chars]

    lines = []
    current_line_words = []
    current_line_start = words[0]["start"] if words else 0
    words_per_line = 10

    for i, w in enumerate(words):
        current_line_words.append(w["word"])

        if len(current_line_words) >= words_per_line or i == len(words) - 1:
            t = _seconds_to_mmss(current_line_start)
            lines.append(f"[{t}] {' '.join(current_line_words)}")
            current_line_words = []
            if i + 1 < len(words):
                current_line_start = words[i + 1]["start"]

    text = "\n".join(lines)
    return text[:max_chars]


def get_words_in_range(transcription: dict, start: float, end: float) -> list:
    """
    Filtra las palabras que caen dentro de un rango de tiempo.
    Útil para obtener las palabras del clip seleccionado.

    Args:
        transcription: dict retornado por transcribe()
        start:         tiempo de inicio en segundos
        end:           tiempo de fin en segundos

    Returns:
        Lista de words con timestamps re-normalizados al inicio del clip
    """
    words = transcription.get("words", [])
    clip_words = []
    for w in words:
        if w["start"] >= start and w["end"] <= end:
            clip_words.append({
                "start": round(w["start"] - start, 3),
                "end":   round(w["end"] - start, 3),
                "word":  w["word"],
            })
    return clip_words


def get_text_in_range(transcription: dict, start: float, end: float) -> str:
    """Retorna el texto plano del transcript en el rango de tiempo dado."""
    words = get_words_in_range(transcription, start, end)
    return " ".join(w["word"] for w in words)


def _seconds_to_mmss(seconds: float) -> str:
    """Convierte segundos a formato MM:SS para display."""
    m = int(seconds) // 60
    s = int(seconds) % 60
    return f"{m:02d}:{s:02d}"
