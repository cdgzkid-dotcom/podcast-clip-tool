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
    SUBTITLE_OUTLINE_COLOR,
    SUBTITLE_OUTLINE_WIDTH,
    SUBTITLE_SECONDARY_COLOR,
    SUBTITLE_WORDS_PER_LINE,
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


# ── Generación de ASS (karaoke por líneas, estilo CapCut) ────────────────────

def generate_word_ass(
    words: list,
    output_path: str,
    play_res_x: int = TARGET_WIDTH,
    play_res_y: int = TARGET_HEIGHT,
    font_size: int = SUBTITLE_FONT_SIZE,
    margin_v: int = SUBTITLE_MARGIN_V,
) -> str:
    """
    Genera un archivo ASS con karaoke por líneas.

    Agrupa palabras en líneas de SUBTITLE_WORDS_PER_LINE palabras.
    Cada línea es UN ÚNICO evento Dialogue — esto elimina la superposición
    de eventos que causaba el "apilamiento vertical" de palabras en pantalla.

    Efecto visual (\\kf):
    - Todas las palabras de la línea visibles en blanco (PrimaryColour)
    - La palabra activa se va "llenando" de amarillo de izq. a der. (SecondaryColour)
    - Las palabras ya dichas quedan en amarillo
    → Lectura natural de izquierda a derecha y de arriba hacia abajo

    Args:
        words:       lista de dicts {start: float, end: float, word: str}
        output_path: ruta de destino del archivo .ass

    Returns:
        output_path
    """
    if not words:
        raise ValueError("La lista de palabras está vacía. ¿El transcript falló?")

    header = _ASS_HEADER.format(
        play_res_x=play_res_x,
        play_res_y=play_res_y,
        fontname=SUBTITLE_FONT_NAME,
        fontsize=font_size,
        primary=SUBTITLE_FONT_COLOR,        # amarillo → palabra activa
        secondary=SUBTITLE_SECONDARY_COLOR, # blanco   → palabras inactivas (visibles)
        outline=SUBTITLE_OUTLINE_COLOR,
        back="&H00000000",
        bold=SUBTITLE_BOLD,
        outline_w=SUBTITLE_OUTLINE_WIDTH,
        alignment=SUBTITLE_ALIGNMENT,
        margin_v=margin_v,
    )

    n     = SUBTITLE_WORDS_PER_LINE
    lines = [words[i : i + n] for i in range(0, len(words), n)]

    events = []
    for li, line_words in enumerate(lines):
        if not line_words:
            continue

        # Grupo empieza cuando se habla la primera palabra
        line_start = _seconds_to_ass_time(line_words[0]["start"])

        # Grupo termina justo cuando empieza el siguiente (transición instantánea,
        # sin huecos ni overlaps — exactamente como CapCut).
        if li < len(lines) - 1:
            line_end = _seconds_to_ass_time(lines[li + 1][0]["start"])
        else:
            line_end = _seconds_to_ass_time(line_words[-1]["end"] + 0.5)

        # \k{cs}: en el estilo CapCut el secondary es BLANCO (todas las palabras
        # del grupo son visibles desde que aparece el grupo). La palabra activa
        # se ilumina en amarillo (primary). Las ya dichas quedan amarillas.
        # cs = centisegundos que esta palabra está activa (hasta que empieza la siguiente).
        parts = []
        for i, w in enumerate(line_words):
            if i < len(line_words) - 1:
                cs = max(1, int(round((line_words[i + 1]["start"] - w["start"]) * 100)))
            else:
                # Última palabra: activa hasta el fin del grupo
                if li < len(lines) - 1:
                    cs = max(1, int(round((lines[li + 1][0]["start"] - w["start"]) * 100)))
                else:
                    cs = max(1, int(round((w["end"] - w["start"]) * 100)))
            text = w["word"].lower().replace("{", "\\{").replace("}", "\\}")
            parts.append(f"{{\\k{cs}}}{text}")

        events.append(_ASS_DIALOGUE.format(
            start=line_start,
            end=line_end,
            text=" ".join(parts),
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

    n = SUBTITLE_WORDS_PER_LINE
    groups = [words[i : i + n] for i in range(0, len(words), n)]

    cues = []
    for idx, group in enumerate(groups, start=1):
        start = _seconds_to_srt_time(group[0]["start"])
        end   = _seconds_to_srt_time(group[-1]["end"] + 0.05)
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
