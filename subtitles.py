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
    SUBTITLE_FONT_NAME,
    SUBTITLE_FONT_SIZE,
    SUBTITLE_MARGIN_V,
    SUBTITLE_MAX_GROUP,
    SUBTITLE_OUTLINE_COLOR,
    SUBTITLE_OUTLINE_WIDTH,
    SUBTITLE_PAUSE_GAP,
    TARGET_WIDTH,
    TARGET_HEIGHT,
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
PlayResX: {play_res_x}
PlayResY: {play_res_y}
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{fontname},{fontsize},{primary},{secondary},{outline},{back},{bold},0,0,0,100,100,0,0,1,{outline_w},0,{alignment},10,10,{margin_v},1

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


# ── Agrupación de palabras ────────────────────────────────────────────────────

def _group_words(words: list) -> list[list]:
    """
    Agrupa palabras por pausas naturales o por tamaño máximo.
    Cada grupo se mostrará como un bloque acumulativo en pantalla.
    """
    groups, current = [], []
    for i, w in enumerate(words):
        current.append(w)
        is_last = i == len(words) - 1
        gap = (words[i + 1]["start"] - w["end"]) if not is_last else 999
        if len(current) >= SUBTITLE_MAX_GROUP or gap >= SUBTITLE_PAUSE_GAP or is_last:
            groups.append(current)
            current = []
    return groups


# ── Generación de ASS — efecto "grow" palabra por palabra ────────────────────

def generate_word_ass(
    words: list,
    output_path: str,
    play_res_x: int = TARGET_WIDTH,
    play_res_y: int = TARGET_HEIGHT,
    font_size: int = SUBTITLE_FONT_SIZE,
    margin_v: int = SUBTITLE_MARGIN_V,
) -> str:
    """
    Genera ASS con efecto "grow": las palabras aparecen una por una exactamente
    cuando se hablan y se QUEDAN acumuladas en pantalla.

    Técnica: un evento Dialogue por cada palabra nueva.
    - Evento de palabra j = texto acumulado "w0 w1 ... wj"
    - Start  = w_j.start  (cuando se empieza a hablar esa palabra)
    - End    = w_{j+1}.start  (cuando empieza la siguiente)
    - Último evento del grupo: End = siguiente_grupo.start (o w_n.end + 0.5)

    Resultado: el texto crece palabra a palabra, sin desaparecer en medio.
    Al final del grupo toda la pantalla se limpia y empieza el siguiente grupo.
    """
    if not words:
        raise ValueError("La lista de palabras está vacía.")

    header = _ASS_HEADER.format(
        play_res_x=play_res_x,
        play_res_y=play_res_y,
        fontname=SUBTITLE_FONT_NAME,
        fontsize=font_size,
        primary=SUBTITLE_FONT_COLOR,
        secondary=SUBTITLE_FONT_COLOR,   # mismo color, sin efecto karaoke
        outline=SUBTITLE_OUTLINE_COLOR,
        back="&H00000000",
        bold=SUBTITLE_BOLD,
        outline_w=SUBTITLE_OUTLINE_WIDTH,
        alignment=SUBTITLE_ALIGNMENT,
        margin_v=margin_v,
    )

    groups = _group_words(words)
    events = []

    for gi, group in enumerate(groups):
        # Inicio del grupo siguiente (para saber hasta cuándo dura el último evento)
        if gi < len(groups) - 1:
            group_end_sec = groups[gi + 1][0]["start"]
        else:
            group_end_sec = group[-1]["end"] + 0.5

        for j, w in enumerate(group):
            # Texto acumulado: todas las palabras del grupo hasta j (inclusive)
            accumulated = " ".join(
                gw["word"].lower().replace("{", "\\{").replace("}", "\\}")
                for gw in group[: j + 1]
            )

            start_sec = w["start"]
            if j < len(group) - 1:
                end_sec = group[j + 1]["start"]
            else:
                end_sec = group_end_sec

            # Evitar eventos de duración cero o negativa
            if end_sec <= start_sec:
                end_sec = start_sec + 0.05

            events.append(_ASS_DIALOGUE.format(
                start=_seconds_to_ass_time(start_sec),
                end=_seconds_to_ass_time(end_sec),
                text=accumulated,
            ))

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(header)
        f.writelines(events)

    return output_path


# ── Generación de SRT (para descarga) ────────────────────────────────────────

def words_to_srt(words: list, output_path: str) -> str:
    """
    Genera un archivo SRT agrupando palabras en líneas de SUBTITLE_WORDS_PER_LINE.

    Consistente con el karaoke ASS: cada cue SRT = una línea completa de N palabras,
    lo que hace el archivo SRT legible como subtítulo externo.

    Args:
        words:       lista de dicts {start: float, end: float, word: str}
        output_path: ruta de destino del archivo .srt

    Returns:
        output_path
    """
    if not words:
        raise ValueError("La lista de palabras está vacía.")

    groups = _group_words(words)

    cues = []
    for idx, group in enumerate(groups, start=1):
        start = _seconds_to_srt_time(group[0]["start"])
        end   = _seconds_to_srt_time(group[-1]["end"] + 0.1)
        text  = " ".join(w["word"].lower() for w in group)
        cues.append(f"{idx}\n{start} --> {end}\n{text}\n")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(cues))

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
        text = seg["text"].strip().lower()
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
