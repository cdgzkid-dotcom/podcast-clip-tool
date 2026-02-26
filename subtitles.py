"""
subtitles.py — Generación y quemado de subtítulos estilo TikTok.

Estilo: palabra por palabra (efecto karaoke), fuente grande, blanco con
outline negro, centrado en la parte inferior.

Responsabilidades:
- Generar archivo ASS con una palabra por evento (karaoke)
- Generar archivo SRT para descarga
- Quemar subtítulos en el video con ffmpeg
"""

import os
import subprocess

from config import (
    AUDIO_CODEC,
    SUBTITLE_ALIGNMENT,
    SUBTITLE_BOLD,
    SUBTITLE_FONT_COLOR,
    SUBTITLE_FONT_SIZE,
    SUBTITLE_MARGIN_V,
    SUBTITLE_OUTLINE_COLOR,
    SUBTITLE_OUTLINE_WIDTH,
    VIDEO_CODEC,
    VIDEO_CRF,
    VIDEO_PRESET,
)

# ── Plantilla ASS ─────────────────────────────────────────────────────────────
# PlayResX/Y = resolución de referencia para el posicionado de subtítulos.
# Usamos 1080x1920 (9:16 estándar TikTok). Si el video tiene otra resolución,
# ffmpeg escala las posiciones automáticamente.
_ASS_HEADER = """\
[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,{fontsize},{primary},{secondary},{outline},{back},{bold},0,0,0,100,100,0,0,1,{outline_w},0,{alignment},10,10,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

_ASS_DIALOGUE = "Dialogue: 0,{start},{end},Default,,0,0,0,,{text}\n"


# ── Helpers de tiempo ─────────────────────────────────────────────────────────

def _seconds_to_srt_time(seconds: float) -> str:
    """Convierte segundos a formato SRT: HH:MM:SS,mmm"""
    h = int(seconds) // 3600
    m = (int(seconds) % 3600) // 60
    s = int(seconds) % 60
    ms = int(round((seconds - int(seconds)) * 1000))
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _seconds_to_ass_time(seconds: float) -> str:
    """Convierte segundos a formato ASS: H:MM:SS.cc (centisegundos)"""
    h = int(seconds) // 3600
    m = (int(seconds) % 3600) // 60
    s = int(seconds) % 60
    cs = int(round((seconds - int(seconds)) * 100))
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


# ── Generación de ASS (karaoke palabra por palabra) ───────────────────────────

def generate_word_ass(words: list, output_path: str) -> str:
    """
    Genera un archivo ASS con una palabra por evento de diálogo.

    Cada palabra aparece sola en pantalla durante su duración (efecto karaoke).
    Las palabras se muestran en MAYÚSCULAS para mayor impacto visual TikTok.

    Args:
        words:       lista de dicts {start: float, end: float, word: str}
        output_path: ruta de destino del archivo .ass

    Returns:
        output_path
    """
    if not words:
        raise ValueError("La lista de palabras está vacía. ¿El transcript falló?")

    # Construir header
    header = _ASS_HEADER.format(
        fontsize=SUBTITLE_FONT_SIZE,
        primary=SUBTITLE_FONT_COLOR,
        secondary=SUBTITLE_FONT_COLOR,
        outline=SUBTITLE_OUTLINE_COLOR,
        back="&H00000000",
        bold=SUBTITLE_BOLD,
        outline_w=SUBTITLE_OUTLINE_WIDTH,
        alignment=SUBTITLE_ALIGNMENT,
        margin_v=SUBTITLE_MARGIN_V,
    )

    # Construir eventos (un Dialogue por palabra)
    events = []
    for w in words:
        start = _seconds_to_ass_time(w["start"])
        # Extender ligeramente el fin para que la palabra no desaparezca
        # demasiado abruptamente (mínimo 0.1s extra, máximo hasta la sig. palabra)
        end_secs = w["end"] + 0.05
        end = _seconds_to_ass_time(end_secs)

        # Texto en mayúsculas, escape de caracteres especiales ASS
        text = w["word"].upper().replace("{", "\\{").replace("}", "\\}")

        events.append(_ASS_DIALOGUE.format(start=start, end=end, text=text))

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(header)
        f.writelines(events)

    return output_path


# ── Generación de SRT (para descarga) ────────────────────────────────────────

def words_to_srt(words: list, output_path: str) -> str:
    """
    Genera un archivo SRT con una palabra por cue.

    Args:
        words:       lista de dicts {start: float, end: float, word: str}
        output_path: ruta de destino del archivo .srt

    Returns:
        output_path
    """
    if not words:
        raise ValueError("La lista de palabras está vacía.")

    lines = []
    for i, w in enumerate(words, start=1):
        start = _seconds_to_srt_time(w["start"])
        end = _seconds_to_srt_time(w["end"] + 0.05)
        lines.append(f"{i}\n{start} --> {end}\n{w['word'].upper()}\n")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    return output_path


def segments_to_srt(segments: list, output_path: str) -> str:
    """
    Genera un SRT desde segmentos (frases) en lugar de palabras individuales.
    Útil como fallback si no hay word-level timestamps.

    Args:
        segments:    lista de dicts {start: float, end: float, text: str}
        output_path: ruta de destino del archivo .srt

    Returns:
        output_path
    """
    lines = []
    for i, seg in enumerate(segments, start=1):
        start = _seconds_to_srt_time(seg["start"])
        end = _seconds_to_srt_time(seg["end"])
        text = seg["text"].strip().upper()
        lines.append(f"{i}\n{start} --> {end}\n{text}\n")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    return output_path


# ── Quemado de subtítulos ─────────────────────────────────────────────────────

def burn_subtitles(video_path: str, ass_path: str, output_path: str) -> str:
    """
    Quema los subtítulos ASS en el video usando ffmpeg.

    Usa el filtro 'ass' de ffmpeg que renderiza el ASS con estilos completos.
    No requiere fonts instalados en el sistema: los estilos están en el header.

    Args:
        video_path:  video sin subtítulos (resultado de process_video)
        ass_path:    archivo .ass generado por generate_word_ass
        output_path: video final con subtítulos quemados

    Returns:
        output_path
    """
    # En Linux/Streamlit Cloud los paths no necesitan escaping especial
    # pero escapamos los dos puntos por seguridad en el filtro ffmpeg
    safe_ass_path = ass_path.replace("\\", "/").replace(":", "\\:")

    cmd = [
        "ffmpeg",
        "-y",
        "-i", video_path,
        "-vf", f"ass={safe_ass_path}",
        "-c:v", VIDEO_CODEC,
        "-crf", str(VIDEO_CRF),
        "-preset", VIDEO_PRESET,
        "-c:a", AUDIO_CODEC,
        output_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"ffmpeg falló al quemar subtítulos.\n"
            f"Comando: {' '.join(cmd)}\n"
            f"Error: {result.stderr}"
        )
    return output_path
