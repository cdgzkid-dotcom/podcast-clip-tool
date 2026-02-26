"""
app.py — Interfaz principal del Podcast Clip Tool.

Modos:
  - Manual:    el usuario proporciona timestamps de inicio y fin
  - Automático: Claude detecta los 3 mejores momentos virales

Flujo:
  1. Subir video (MOV o MP4, hasta 500 MB)
  2. Seleccionar modo y configurar parámetros
  3. Generar clips → video + SRT + captions + transcript
  4. Descargar resultados
"""

import os
import tempfile
import atexit
import shutil

import streamlit as st

from config import (
    APP_TITLE,
    DEFAULT_MAX_DURATION,
    DEFAULT_MIN_DURATION,
    MAX_UPLOAD_MB,
    MAX_VIRAL_MOMENTS,
    OUTPUT_AUDIO_EXT,
    OUTPUT_SUBTITLE_EXT,
    OUTPUT_VIDEO_EXT,
    WHISPER_LANGUAGE,
)
from cutter import process_video
from transcriber import transcribe, transcribe_clip, format_for_claude, get_words_in_range, get_text_in_range
from subtitles import generate_word_ass, words_to_srt, segments_to_srt, burn_subtitles
from ai_agent import detect_viral_moments, generate_both_captions
from exporter import package_clip_output


# ── Helpers ───────────────────────────────────────────────────────────────────

def _hhmmss_to_seconds(time_str: str) -> float:
    """Convierte HH:MM:SS o MM:SS a segundos flotantes."""
    parts = time_str.strip().split(":")
    try:
        if len(parts) == 3:
            h, m, s = parts
            return int(h) * 3600 + int(m) * 60 + float(s)
        elif len(parts) == 2:
            m, s = parts
            return int(m) * 60 + float(s)
        else:
            return float(parts[0])
    except (ValueError, IndexError):
        raise ValueError(f"Formato de tiempo inválido: '{time_str}'. Usa HH:MM:SS o MM:SS.")


def _seconds_to_hhmmss(seconds: float) -> str:
    """Convierte segundos a string HH:MM:SS."""
    h = int(seconds) // 3600
    m = (int(seconds) % 3600) // 60
    s = int(seconds) % 60
    return f"{h:02d}:{m:02d}:{s:02d}"


def _get_or_create_temp_dir() -> str:
    """Retorna (o crea) el directorio temporal de la sesión."""
    if "temp_dir" not in st.session_state or not os.path.isdir(st.session_state.temp_dir):
        temp_dir = tempfile.mkdtemp(prefix="podcast_clip_")
        st.session_state.temp_dir = temp_dir
        # Limpiar al cerrar la sesión (best-effort en Streamlit Cloud)
        atexit.register(shutil.rmtree, temp_dir, ignore_errors=True)
    return st.session_state.temp_dir


def _save_upload(uploaded_file) -> str:
    """Guarda el archivo subido en el directorio temporal y retorna la ruta."""
    temp_dir = _get_or_create_temp_dir()
    suffix = os.path.splitext(uploaded_file.name)[1].lower() or ".mp4"
    dest = os.path.join(temp_dir, f"source{suffix}")
    with open(dest, "wb") as f:
        f.write(uploaded_file.getbuffer())
    return dest


def _process_clip(
    video_path: str,
    start_sec: float,
    end_sec: float,
    clip_index: int,
    episode_number: int,
    transcription: dict,
    temp_dir: str,
) -> dict:
    """
    Pipeline completo para un clip:
      cut → crop → transcribe clip → subtítulos → burn → captions → package

    Args:
        video_path:     ruta al video original
        start_sec:      inicio del clip en segundos
        end_sec:        fin del clip en segundos
        clip_index:     índice (1-based) para el nombre de archivo
        episode_number: número del episodio
        transcription:  dict de transcripción del video completo (puede ser None)
        temp_dir:       directorio temporal de la sesión

    Returns:
        Dict retornado por package_clip_output()
    """
    base = f"clip_{clip_index:02d}_ep{episode_number:02d}"

    # Rutas de archivos temporales
    video_out     = os.path.join(temp_dir, f"{base}_video{OUTPUT_VIDEO_EXT}")
    ass_path      = os.path.join(temp_dir, f"{base}.ass")
    srt_path      = os.path.join(temp_dir, f"{base}{OUTPUT_SUBTITLE_EXT}")
    final_video   = os.path.join(temp_dir, f"{base}_final{OUTPUT_VIDEO_EXT}")

    # 1. Cortar y hacer crop si es necesario
    process_video(video_path, start_sec, end_sec, video_out)

    # 2. Obtener palabras del clip (del transcript del video completo o transcribir el clip)
    if transcription and transcription.get("words"):
        words = get_words_in_range(transcription, start_sec, end_sec)
        clip_text = get_text_in_range(transcription, start_sec, end_sec)
    else:
        # Transcribir directamente el clip recortado
        clip_transcription = transcribe_clip(video_out, language=WHISPER_LANGUAGE)
        words = clip_transcription.get("words", [])
        clip_text = clip_transcription.get("text", "")

    # 3. Generar subtítulos
    if words:
        generate_word_ass(words, ass_path)
        words_to_srt(words, srt_path)
    else:
        # Fallback a segmentos si no hay word-level timestamps
        if transcription and transcription.get("segments"):
            segs = [
                s for s in transcription["segments"]
                if s["start"] >= start_sec and s["end"] <= end_sec
            ]
            # Re-normalizar tiempos al inicio del clip
            segs_norm = [
                {"start": s["start"] - start_sec, "end": s["end"] - start_sec, "text": s["text"]}
                for s in segs
            ]
            segments_to_srt(segs_norm, srt_path)
        else:
            # SRT vacío como fallback final
            with open(srt_path, "w", encoding="utf-8") as f:
                f.write("")
        # Sin ASS → no quemar subtítulos
        ass_path = None

    # 4. Quemar subtítulos en el video (si hay ASS)
    if ass_path and os.path.exists(ass_path):
        burn_subtitles(video_out, ass_path, final_video)
    else:
        # Sin subtítulos → usar el video tal cual
        final_video = video_out

    # 5. Generar captions con Claude
    captions = generate_both_captions(clip_text, episode_number)

    # 6. Empaquetar para descarga
    return package_clip_output(
        clip_index=clip_index,
        episode_number=episode_number,
        video_path=final_video,
        srt_path=srt_path,
        transcript_text=clip_text,
        tiktok_caption=captions["tiktok"],
        instagram_caption=captions["instagram"],
    )


def _render_clip_result(result: dict, clip_number: int) -> None:
    """Renderiza los resultados de un clip (video, descargas, captions, transcript)."""
    st.subheader(f"Clip {clip_number}: `{result['filename_base']}`")

    # Preview del video
    st.video(result["video_bytes"])

    # Botones de descarga
    col1, col2 = st.columns(2)
    col1.download_button(
        label="⬇️ Descargar MP4",
        data=result["video_bytes"],
        file_name=f"{result['filename_base']}.mp4",
        mime="video/mp4",
        key=f"dl_video_{clip_number}",
    )
    col2.download_button(
        label="⬇️ Descargar SRT",
        data=result["srt_bytes"],
        file_name=f"{result['filename_base']}.srt",
        mime="text/plain",
        key=f"dl_srt_{clip_number}",
    )

    # Captions
    with st.expander("📱 Caption TikTok", expanded=True):
        st.code(result["tiktok_caption"], language=None)

    with st.expander("📸 Caption Instagram"):
        st.code(result["instagram_caption"], language=None)

    # Transcript
    with st.expander("📝 Transcript del clip"):
        st.text(result["transcript"] or "(sin transcript disponible)")

    st.divider()


# ── Configuración de página ───────────────────────────────────────────────────

st.set_page_config(
    page_title=APP_TITLE,
    page_icon="🎙️",
    layout="wide",
)

st.title(APP_TITLE)


# ── Inicialización de session state ──────────────────────────────────────────

defaults = {
    "video_path":     None,
    "transcription":  None,
    "viral_moments":  None,
    "clips_ready":    [],
    "episode_number": 1,
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v


# ── Sidebar ───────────────────────────────────────────────────────────────────

with st.sidebar:
    st.header("⚙️ Configuración")

    episode_number = st.number_input(
        "Número de episodio",
        min_value=1,
        max_value=999,
        value=st.session_state.episode_number,
        step=1,
    )
    st.session_state.episode_number = episode_number

    mode = st.radio(
        "Modo",
        options=["Manual", "Automático"],
        help="**Manual**: proporciona timestamps exactos.\n\n**Automático**: Claude detecta los mejores momentos virales.",
    )

    if mode == "Automático":
        st.markdown("---")
        st.subheader("Duración del clip")
        min_dur = st.slider(
            "Mínimo (segundos)",
            min_value=10,
            max_value=60,
            value=DEFAULT_MIN_DURATION,
            step=5,
        )
        max_dur = st.slider(
            "Máximo (segundos)",
            min_value=30,
            max_value=180,
            value=DEFAULT_MAX_DURATION,
            step=5,
        )
        if min_dur >= max_dur:
            st.warning("La duración mínima debe ser menor que la máxima.")

    st.markdown("---")
    st.caption(f"Límite de subida: {MAX_UPLOAD_MB} MB · Formatos: MOV, MP4")


# ── Upload ────────────────────────────────────────────────────────────────────

uploaded_file = st.file_uploader(
    "📤 Sube tu video del podcast",
    type=["mp4", "mov", "MOV", "MP4"],
    help=f"Máximo {MAX_UPLOAD_MB} MB. iPhone (MOV vertical) o Zoom (MP4 horizontal).",
)

if uploaded_file:
    # Guardar si es un archivo nuevo
    if (
        "uploaded_filename" not in st.session_state
        or st.session_state.uploaded_filename != uploaded_file.name
    ):
        st.session_state.uploaded_filename = uploaded_file.name
        st.session_state.video_path = _save_upload(uploaded_file)
        # Resetear estado derivado al cambiar el video
        st.session_state.transcription = None
        st.session_state.viral_moments = None
        st.session_state.clips_ready = []

    st.success(f"✅ Video cargado: **{uploaded_file.name}**")


# ── Modo Manual ───────────────────────────────────────────────────────────────

if mode == "Manual" and st.session_state.video_path:
    st.header("✂️ Modo Manual")

    col1, col2 = st.columns(2)
    start_input = col1.text_input(
        "Inicio del clip",
        value="00:00:00",
        help="Formato: HH:MM:SS o MM:SS",
        key="manual_start",
    )
    end_input = col2.text_input(
        "Fin del clip",
        value="00:01:00",
        help="Formato: HH:MM:SS o MM:SS",
        key="manual_end",
    )

    if st.button("🎬 Generar Clip", type="primary", key="btn_manual"):
        try:
            start_sec = _hhmmss_to_seconds(start_input)
            end_sec   = _hhmmss_to_seconds(end_input)
        except ValueError as e:
            st.error(str(e))
            st.stop()

        if end_sec <= start_sec:
            st.error("El fin debe ser posterior al inicio.")
            st.stop()

        temp_dir = _get_or_create_temp_dir()
        progress = st.progress(0, text="Procesando video...")

        try:
            progress.progress(20, text="Transcribiendo audio...")
            transcription = transcribe(
                st.session_state.video_path,
                language=WHISPER_LANGUAGE,
            )
            st.session_state.transcription = transcription

            progress.progress(60, text="Generando subtítulos y captions...")
            result = _process_clip(
                video_path=st.session_state.video_path,
                start_sec=start_sec,
                end_sec=end_sec,
                clip_index=1,
                episode_number=episode_number,
                transcription=transcription,
                temp_dir=temp_dir,
            )

            progress.progress(100, text="¡Listo!")
            st.session_state.clips_ready = [result]

        except Exception as e:
            st.error(f"Error al generar el clip: {e}")
            st.stop()

        finally:
            progress.empty()


# ── Modo Automático ───────────────────────────────────────────────────────────

elif mode == "Automático" and st.session_state.video_path:
    st.header("🤖 Modo Automático")

    # Paso 1: Analizar el video
    if st.button("🔍 Analizar Video", type="primary", key="btn_analyze"):
        st.session_state.viral_moments = None
        st.session_state.clips_ready = []
        temp_dir = _get_or_create_temp_dir()

        with st.spinner("🎙️ Transcribiendo audio con Whisper..."):
            try:
                transcription = transcribe(
                    st.session_state.video_path,
                    language=WHISPER_LANGUAGE,
                )
                st.session_state.transcription = transcription
            except Exception as e:
                st.error(f"Error en la transcripción: {e}")
                st.stop()

        with st.spinner("🧠 Detectando momentos virales con Claude..."):
            try:
                transcript_text = format_for_claude(transcription)
                moments = detect_viral_moments(
                    transcript_text=transcript_text,
                    episode_number=episode_number,
                    min_duration=min_dur,
                    max_duration=max_dur,
                )
                st.session_state.viral_moments = moments
                if not moments:
                    st.warning("Claude no detectó momentos virales. Intenta con otros parámetros de duración.")
            except Exception as e:
                st.error(f"Error al detectar momentos virales: {e}")
                st.stop()

    # Paso 2: Mostrar momentos detectados para ajuste y selección
    if st.session_state.viral_moments:
        st.subheader(f"📊 {len(st.session_state.viral_moments)} momentos detectados — ajusta y selecciona")

        selected_clips = []

        for i, moment in enumerate(st.session_state.viral_moments):
            score = moment.get("viral_score", "—")
            duration = moment.get("duration_seconds", "—")
            hook = moment.get("hook", "")
            reason = moment.get("reason", "")

            with st.expander(
                f"Momento {i + 1} · Score: {score}/10 · {duration}s",
                expanded=True,
            ):
                st.markdown(f"**Hook:** _{hook}_")
                st.markdown(f"**Por qué funciona:** {reason}")

                c1, c2, c3 = st.columns([2, 2, 1])
                start_val = _seconds_to_hhmmss(moment.get("start_time", 0))
                end_val   = _seconds_to_hhmmss(moment.get("end_time", 0))

                start_edited = c1.text_input(
                    "Inicio",
                    value=start_val,
                    key=f"auto_start_{i}",
                )
                end_edited = c2.text_input(
                    "Fin",
                    value=end_val,
                    key=f"auto_end_{i}",
                )
                include = c3.checkbox(
                    "Incluir",
                    value=True,
                    key=f"auto_include_{i}",
                )

                if include:
                    selected_clips.append({
                        "index": i,
                        "start": start_edited,
                        "end":   end_edited,
                    })

        # Paso 3: Generar clips seleccionados
        if selected_clips and st.button(
            f"🎬 Generar {len(selected_clips)} clip(s) seleccionado(s)",
            type="primary",
            key="btn_auto_generate",
        ):
            temp_dir = _get_or_create_temp_dir()
            results = []
            progress = st.progress(0)

            for pos, clip_info in enumerate(selected_clips, start=1):
                pct = int((pos - 1) / len(selected_clips) * 100)
                progress.progress(pct, text=f"Generando clip {pos}/{len(selected_clips)}...")

                try:
                    start_sec = _hhmmss_to_seconds(clip_info["start"])
                    end_sec   = _hhmmss_to_seconds(clip_info["end"])
                except ValueError as e:
                    st.error(f"Clip {pos}: {e}")
                    continue

                if end_sec <= start_sec:
                    st.error(f"Clip {pos}: el fin debe ser posterior al inicio.")
                    continue

                try:
                    result = _process_clip(
                        video_path=st.session_state.video_path,
                        start_sec=start_sec,
                        end_sec=end_sec,
                        clip_index=pos,
                        episode_number=episode_number,
                        transcription=st.session_state.transcription,
                        temp_dir=temp_dir,
                    )
                    results.append(result)
                except Exception as e:
                    st.error(f"Error en clip {pos}: {e}")
                    continue

            progress.progress(100, text="¡Listo!")
            progress.empty()
            st.session_state.clips_ready = results


# ── Resultados ────────────────────────────────────────────────────────────────

if st.session_state.clips_ready:
    st.header("🎉 Clips generados")
    for i, result in enumerate(st.session_state.clips_ready, start=1):
        _render_clip_result(result, i)

elif not st.session_state.video_path:
    st.info("👆 Sube un video para comenzar.")
