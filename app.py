"""
app.py — Podcast Clip Tool (Ladrando Ideas + FTBP)

Flujo:
  1. Seleccionar podcast (Ladrando Ideas / Fuck The Business Plan)
  2. Subir imagen de fondo para ese podcast
  3. Subir episodio completo en MP3 (o M4A/WAV)
  4. Ingresar número de episodio
  5. Analizar → Whisper transcribe + Claude detecta 3 momentos de ~60s
  6. Revisar momentos (timestamps editables), seleccionar
  7. Generar clips → video 1080×1920 con imagen de fondo + subtítulos + caption Instagram
  8. Descargar MP4 + SRT
"""

import json
import os
import pathlib
import tempfile
import atexit
import shutil
from datetime import date

import streamlit as st

from config import (
    APP_TITLE,
    CLIP_DURATION_SECONDS,
    CLIP_DURATION_TOLERANCE,
    MAX_UPLOAD_MB,
    MAX_VIRAL_MOMENTS,
    OUTPUT_SUBTITLE_EXT,
    OUTPUT_VIDEO_EXT,
    PODCAST_DISPLAY_NAMES,
    PODCASTS,
    SUPPORTED_AUDIO_FORMATS,
    WHISPER_LANGUAGE,
)

# Formato LinkedIn — definidos aquí para no depender de versión de config.py
LINKEDIN_WIDTH            = 1080
LINKEDIN_HEIGHT           = 1080
SUBTITLE_LINKEDIN_FONT_SIZE = 72
SUBTITLE_LINKEDIN_MARGIN_V  = 120
from cutter import normalize_audio, cut_audio, create_video_from_audio
from transcriber import transcribe, format_for_claude, get_words_in_range, get_text_in_range, snap_to_word_boundaries
from subtitles import generate_word_ass, words_to_srt
from ai_agent import (
    detect_viral_moments,
    generate_instagram_caption,
    generate_episode_description,
    generate_linkedin_clip_copy,
    generate_podcast_script,
)
from exporter import package_clip_output


# ── Helpers ───────────────────────────────────────────────────────────────────

def _hhmmss_to_seconds(time_str: str) -> float:
    """Convierte HH:MM:SS o MM:SS a segundos flotantes."""
    parts = time_str.strip().split(":")
    try:
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
        elif len(parts) == 2:
            return int(parts[0]) * 60 + float(parts[1])
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


def _get_podcast_slug(display_name: str) -> str:
    """Retorna el slug del podcast dado su nombre de display."""
    for slug, info in PODCASTS.items():
        if info["display_name"] == display_name:
            return slug
    return "podcast"


def _get_or_create_temp_dir() -> str:
    """Retorna (o crea) el directorio temporal de la sesión."""
    if "temp_dir" not in st.session_state or not os.path.isdir(st.session_state.temp_dir):
        temp_dir = tempfile.mkdtemp(prefix="podcast_clip_")
        st.session_state.temp_dir = temp_dir
        atexit.register(shutil.rmtree, temp_dir, ignore_errors=True)
    return st.session_state.temp_dir


def _save_upload(uploaded_file, prefix: str = "upload") -> str:
    """Guarda un archivo subido en el directorio temporal y retorna la ruta."""
    temp_dir = _get_or_create_temp_dir()
    suffix = os.path.splitext(uploaded_file.name)[1].lower() or ".bin"
    dest = os.path.join(temp_dir, f"{prefix}{suffix}")
    with open(dest, "wb") as f:
        f.write(uploaded_file.getbuffer())
    return dest


def _save_image_bytes(image_bytes: bytes, suffix: str = ".jpg") -> str:
    """Guarda bytes de imagen en un archivo temporal y retorna la ruta."""
    temp_dir = _get_or_create_temp_dir()
    dest = os.path.join(temp_dir, f"bg{suffix}")
    with open(dest, "wb") as f:
        f.write(image_bytes)
    return dest


def _process_single_clip(
    audio_path: str,
    start_sec: float,
    end_sec: float,
    background_image_path: str,
    clip_index: int,
    season_number: int,
    episode_number: int,
    podcast_slug: str,
    transcription: dict,
    temp_dir: str,
) -> dict:
    """
    Pipeline completo para un clip — genera dos videos:
      - Instagram (1080×1920 vertical)
      - LinkedIn  (1080×1080 cuadrado)
    Corta el audio UNA sola vez (WAV, sin encoder delay) y lo reutiliza.
    """
    base           = f"clip_{clip_index:02d}_ep{episode_number:02d}"
    tmp_wav        = os.path.join(temp_dir, f"{base}_audio.wav")
    ass_ig_path    = os.path.join(temp_dir, f"{base}_ig.ass")
    ass_li_path    = os.path.join(temp_dir, f"{base}_li.ass")
    srt_path       = os.path.join(temp_dir, f"{base}{OUTPUT_SUBTITLE_EXT}")
    video_ig       = os.path.join(temp_dir, f"{base}_instagram{OUTPUT_VIDEO_EXT}")
    video_li       = os.path.join(temp_dir, f"{base}_linkedin{OUTPUT_VIDEO_EXT}")

    # 1. Palabras y texto del clip
    words     = get_words_in_range(transcription, start_sec, end_sec)
    clip_text = get_text_in_range(transcription, start_sec, end_sec)

    # 2. Cortar audio UNA vez como WAV (sin encoder delay → timing perfecto)
    cut_audio(audio_path, start_sec, end_sec, tmp_wav)

    # 3. Generar ASS y SRT
    if words:
        generate_word_ass(words, ass_ig_path)                          # 1080×1920
        generate_word_ass(                                              # 1080×1080
            words, ass_li_path,
            play_res_x=LINKEDIN_WIDTH,
            play_res_y=LINKEDIN_HEIGHT,
            font_size=SUBTITLE_LINKEDIN_FONT_SIZE,
            margin_v=SUBTITLE_LINKEDIN_MARGIN_V,
        )
        words_to_srt(words, srt_path)
    else:
        ass_ig_path = ass_li_path = None
        with open(srt_path, "w", encoding="utf-8") as f:
            f.write("")

    # 4. Crear video Instagram (9:16) + video LinkedIn (1:1) en paralelo (secuencial)
    create_video_from_audio(background_image_path, tmp_wav, video_ig, ass_ig_path)
    create_video_from_audio(
        background_image_path, tmp_wav, video_li, ass_li_path,
        width=LINKEDIN_WIDTH, height=LINKEDIN_HEIGHT,
    )

    # 5. Limpiar WAV temporal
    if os.path.exists(tmp_wav):
        os.unlink(tmp_wav)

    # 6. Captions
    podcast_display   = PODCASTS[podcast_slug]["display_name"]
    instagram_caption = generate_instagram_caption(clip_text, season_number, episode_number, podcast_display)
    linkedin_caption  = generate_linkedin_clip_copy(clip_text, season_number, episode_number, podcast_display)

    # 7. Empaquetar resultado base (Instagram)
    result = package_clip_output(
        clip_index=clip_index,
        season_number=season_number,
        episode_number=episode_number,
        podcast_slug=podcast_slug,
        video_path=video_ig,
        srt_path=srt_path,
        transcript_text=clip_text,
        instagram_caption=instagram_caption,
    )

    # 8. Leer LinkedIn video a memoria y borrar del disco inmediatamente
    with open(video_li, "rb") as f:
        result["linkedin_video_bytes"] = f.read()
    os.unlink(video_li)

    # 9. Limpiar archivos ASS del disco
    for p in [ass_ig_path, ass_li_path]:
        if p and os.path.exists(p):
            os.unlink(p)

    result["linkedin_caption"] = linkedin_caption
    result["linkedin_filename"] = f"{result['filename_base']}_linkedin.mp4"

    return result


def _render_clip_result(result: dict, clip_number: int) -> None:
    """Renderiza los resultados de un clip — Instagram (9:16) y LinkedIn (1:1)."""
    st.subheader(f"Clip {clip_number}")

    # ── Videos lado a lado ────────────────────────────────────────────────────
    col_ig, col_li = st.columns(2)

    with col_ig:
        st.caption("📱 Instagram Reels (9:16)")
        vid_col, _ = st.columns([1, 2])
        with vid_col:
            st.video(result["video_bytes"])
        st.download_button(
            label="⬇️ Descargar Instagram MP4",
            data=result["video_bytes"],
            file_name=f"{result['filename_base']}.mp4",
            mime="video/mp4",
            key=f"dl_ig_{clip_number}",
            use_container_width=True,
        )

    with col_li:
        st.caption("💼 LinkedIn (1:1)")
        vid_col2, _ = st.columns([1, 1])
        with vid_col2:
            st.video(result["linkedin_video_bytes"])
        st.download_button(
            label="⬇️ Descargar LinkedIn MP4",
            data=result["linkedin_video_bytes"],
            file_name=result["linkedin_filename"],
            mime="video/mp4",
            key=f"dl_li_{clip_number}",
            use_container_width=True,
        )

    # ── Descarga SRT ─────────────────────────────────────────────────────────
    st.download_button(
        label="⬇️ Descargar SRT",
        data=result["srt_bytes"],
        file_name=f"{result['filename_base']}.srt",
        mime="text/plain",
        key=f"dl_srt_{clip_number}",
    )

    # ── Copies ───────────────────────────────────────────────────────────────
    col_copy1, col_copy2 = st.columns(2)
    with col_copy1:
        with st.expander("📸 Copy Instagram", expanded=True):
            st.code(result["instagram_caption"], language=None)
    with col_copy2:
        with st.expander("💼 Copy LinkedIn", expanded=True):
            st.code(result["linkedin_caption"], language=None)

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

for key, default in {
    "audio_path":           None,
    "audio_filename":       None,
    "normalized_bytes":     None,
    "transcription":        None,
    "viral_moments":        None,
    "clips_ready":          [],
    "episode_number":       1,
    "season_number":        1,
    "bg_ladrando":          None,
    "bg_ftbp":              None,
    "episode_description":  None,
}.items():
    if key not in st.session_state:
        st.session_state[key] = default

# Directorio en home del usuario — sobrevive redeployments de Streamlit Cloud
# (a diferencia de assets/ en el directorio del proyecto que se resetea en cada push).
_PERSISTENT_DIR = pathlib.Path.home() / ".podcast_clip_bg"
_PERSISTENT_DIR.mkdir(exist_ok=True)

_BG_PATHS = {
    "ladrando-ideas": str(_PERSISTENT_DIR / "bg_ladrando.jpg"),
    "ftbp":           str(_PERSISTENT_DIR / "bg_ftbp.jpg"),
}
_EP_STATE_PATH = str(_PERSISTENT_DIR / "episode_state.json")

def _load_bg(slug: str, state_key: str) -> None:
    if st.session_state[state_key] is not None:
        return
    path = _BG_PATHS[slug]
    if os.path.exists(path):
        with open(path, "rb") as f:
            st.session_state[state_key] = f.read()

def _save_bg(slug: str, data: bytes) -> None:
    with open(_BG_PATHS[slug], "wb") as f:
        f.write(data)

def _load_all_episode_states() -> dict:
    """Retorna el dict completo de estados guardados {slug: {season, episode}}."""
    if os.path.exists(_EP_STATE_PATH):
        try:
            import json as _json
            with open(_EP_STATE_PATH) as f:
                return _json.load(f)
        except Exception:
            pass
    return {}

def _save_episode_state(slug: str, season: int, episode: int) -> None:
    try:
        import json as _json
        states = _load_all_episode_states()
        states[slug] = {"season": season, "episode": episode}
        with open(_EP_STATE_PATH, "w") as f:
            _json.dump(states, f)
    except Exception:
        pass

def _get_episode_defaults(slug: str) -> tuple:
    """Retorna (season, episode) guardados para ese podcast, o (1, 1) si no hay."""
    states = _load_all_episode_states()
    saved = states.get(slug, {})
    return saved.get("season", 1), saved.get("episode", 1)

_load_bg("ladrando-ideas", "bg_ladrando")
_load_bg("ftbp", "bg_ftbp")

# ── Archivo de episodios ──────────────────────────────────────────────────────

_ARCHIVE_PATH = str(_PERSISTENT_DIR / "episode_archive.json")


def _load_archive() -> dict:
    if os.path.exists(_ARCHIVE_PATH):
        try:
            with open(_ARCHIVE_PATH, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"episodes": {}}


def _save_archive(archive: dict) -> None:
    with open(_ARCHIVE_PATH, "w", encoding="utf-8") as f:
        json.dump(archive, f, ensure_ascii=False, indent=2)


def _ep_key(slug: str, season: int, episode: int) -> str:
    return f"{slug}_t{season:02d}_ep{episode:02d}"


def _archive_ensure_episode(slug: str, display: str, season: int, episode: int) -> dict:
    """Obtiene o crea la entrada del episodio en el archivo."""
    archive = _load_archive()
    key = _ep_key(slug, season, episode)
    if key not in archive["episodes"]:
        archive["episodes"][key] = {
            "id": key,
            "podcast": display,
            "podcast_slug": slug,
            "season": season,
            "episode": episode,
            "date": date.today().isoformat(),
            "guest_name": "",
            "script": "",
            "spotify_title": "",
            "spotify_description": "",
            "clips": [],
        }
        _save_archive(archive)
    return archive


def _archive_set_script(slug, display, season, episode, guest_name, script):
    archive = _archive_ensure_episode(slug, display, season, episode)
    key = _ep_key(slug, season, episode)
    archive["episodes"][key]["guest_name"] = guest_name
    archive["episodes"][key]["script"] = script
    _save_archive(archive)


def _archive_set_spotify(slug, display, season, episode, title, description):
    archive = _archive_ensure_episode(slug, display, season, episode)
    key = _ep_key(slug, season, episode)
    archive["episodes"][key]["spotify_title"] = title
    archive["episodes"][key]["spotify_description"] = description
    _save_archive(archive)


def _archive_set_clips(slug, display, season, episode, clips_results):
    archive = _archive_ensure_episode(slug, display, season, episode)
    key = _ep_key(slug, season, episode)
    archive["episodes"][key]["clips"] = [
        {
            "index": i,
            "transcript":        r.get("transcript", ""),
            "instagram_caption": r.get("instagram_caption", ""),
            "linkedin_caption":  r.get("linkedin_caption", ""),
        }
        for i, r in enumerate(clips_results, start=1)
    ]
    _save_archive(archive)


def _archive_to_text(archive: dict) -> str:
    """Exporta todo el archivo como texto plano."""
    lines = []
    episodes = sorted(
        archive["episodes"].values(),
        key=lambda x: (x["podcast_slug"], x["season"], x["episode"]),
    )
    for ep in episodes:
        sep = "=" * 60
        lines += [sep, f"{ep['podcast']}  —  T{ep['season']:02d}E{ep['episode']:02d}"]
        if ep.get("guest_name"):
            lines.append(f"Invitado: {ep['guest_name']}")
        if ep.get("date"):
            lines.append(f"Fecha: {ep['date']}")
        lines.append("")
        if ep.get("script"):
            lines += ["── GUIÓN ──", ep["script"], ""]
        if ep.get("spotify_title"):
            lines += [
                "── SPOTIFY ──",
                f"Título: {ep['spotify_title']}",
                ep.get("spotify_description", ""),
                "",
            ]
        for clip in ep.get("clips", []):
            lines += [
                f"── CLIP {clip['index']} ──",
                "Transcript:", clip.get("transcript", ""), "",
                "Instagram:",  clip.get("instagram_caption", ""), "",
                "LinkedIn:",   clip.get("linkedin_caption", ""), "",
            ]
        lines.append("")
    return "\n".join(lines)


# ── Sidebar ───────────────────────────────────────────────────────────────────

with st.sidebar:
    st.header("🎙️ Configuración")

    # Selección de podcast
    podcast_display = st.selectbox(
        "Podcast",
        options=PODCAST_DISPLAY_NAMES,
        help="Cada podcast usa su propia imagen de fondo.",
    )
    podcast_slug = _get_podcast_slug(podcast_display)

    st.markdown("---")

    # Imágenes de fondo por podcast
    st.subheader("🖼️ Imágenes de fondo")
    st.caption("Se guardan automáticamente. Solo súbelas una vez.")

    col_a, col_b = st.columns(2)

    with col_a:
        st.markdown("**Ladrando Ideas**")
        if st.session_state.bg_ladrando:
            st.image(st.session_state.bg_ladrando, use_container_width=True)
        img_ladrando = st.file_uploader(
            "Cambiar imagen LI" if st.session_state.bg_ladrando else "Subir imagen LI",
            type=["jpg", "jpeg", "png"],
            key="upload_bg_ladrando",
            label_visibility="collapsed",
        )
        if img_ladrando:
            data = img_ladrando.getvalue()
            st.session_state.bg_ladrando = data
            _save_bg("ladrando-ideas", data)

    with col_b:
        st.markdown("**FTBP**")
        if st.session_state.bg_ftbp:
            st.image(st.session_state.bg_ftbp, use_container_width=True)
        img_ftbp = st.file_uploader(
            "Cambiar imagen FTBP" if st.session_state.bg_ftbp else "Subir imagen FTBP",
            type=["jpg", "jpeg", "png"],
            key="upload_bg_ftbp",
            label_visibility="collapsed",
        )
        if img_ftbp:
            data = img_ftbp.getvalue()
            st.session_state.bg_ftbp = data
            _save_bg("ftbp", data)

    st.markdown("---")

    # Temporada y episodio — valores por podcast
    _default_season, _default_episode = _get_episode_defaults(podcast_slug)

    col_ep1, col_ep2 = st.columns(2)
    season_number = col_ep1.number_input(
        "Temporada",
        min_value=1,
        max_value=99,
        value=_default_season,
        step=1,
        key=f"season_{podcast_slug}",
    )
    episode_number = col_ep2.number_input(
        "Episodio",
        min_value=1,
        max_value=999,
        value=_default_episode,
        step=1,
        key=f"episode_{podcast_slug}",
    )
    _save_episode_state(podcast_slug, season_number, episode_number)

    st.markdown("---")
    st.caption(
        f"Clips: **{CLIP_DURATION_SECONDS}s** · "
        f"Formatos: {', '.join(SUPPORTED_AUDIO_FORMATS[:3])} · "
        f"Límite: {MAX_UPLOAD_MB} MB"
    )


# ── Tabs principales ──────────────────────────────────────────────────────────

bg_bytes = st.session_state.bg_ladrando if podcast_slug == "ladrando-ideas" else st.session_state.bg_ftbp

tab_clips, tab_script, tab_archive = st.tabs(["🎬 Clips", "✍️ Guión", "📚 Archivo"])


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 1 — CLIPS
# ═══════════════════════════════════════════════════════════════════════════════

with tab_clips:

    if not bg_bytes:
        st.warning(f"⚠️ Sube la imagen de fondo para **{podcast_display}** en el sidebar antes de continuar.")

    # ── Upload de audio ───────────────────────────────────────────────────────
    uploaded_audio = st.file_uploader(
        "🎵 Sube el episodio completo (MP3, M4A o WAV)",
        type=SUPPORTED_AUDIO_FORMATS,
        help=f"El audio exportado para Spotify funciona directo. Máximo {MAX_UPLOAD_MB} MB.",
    )

    if uploaded_audio:
        if st.session_state.audio_filename != uploaded_audio.name:
            st.session_state.audio_filename   = uploaded_audio.name
            st.session_state.normalized_bytes = None
            st.session_state.audio_path       = _save_upload(uploaded_audio, prefix="episode_raw")
            st.session_state.transcription    = None
            st.session_state.viral_moments    = None
            st.session_state.clips_ready      = []

        st.success(f"✅ **{uploaded_audio.name}** cargado.")

        col_norm, col_skip = st.columns(2)
        if col_norm.button("🔊 Normalizar volumen antes de analizar", use_container_width=True):
            temp_dir = _get_or_create_temp_dir()
            normalized_path = os.path.join(temp_dir, "episode_normalized.mp3")
            with st.spinner("Normalizando volumen... (puede tardar 1-2 min)"):
                try:
                    normalize_audio(st.session_state.audio_path, normalized_path)
                    st.session_state.audio_path = normalized_path
                    with open(normalized_path, "rb") as f:
                        st.session_state.normalized_bytes = f.read()
                    st.session_state.transcription = None
                    st.session_state.viral_moments = None
                    st.session_state.clips_ready   = []
                except Exception as e:
                    st.warning(f"Normalización falló, se usará el audio original: {e}")

        if st.session_state.get("normalized_bytes"):
            base_name = os.path.splitext(uploaded_audio.name)[0]
            st.caption("✅ Audio normalizado.")
            col_skip.download_button(
                label="⬇️ Descargar normalizado",
                data=st.session_state.normalized_bytes,
                file_name=f"{base_name}_normalizado.mp3",
                mime="audio/mpeg",
                key="dl_normalized",
                use_container_width=True,
            )

    # ── Análisis ──────────────────────────────────────────────────────────────
    if st.session_state.audio_path and bg_bytes:
        if st.button("🔍 Analizar episodio", type="primary"):
            st.session_state.viral_moments = None
            st.session_state.clips_ready   = []

            with st.spinner("🎙️ Transcribiendo con Whisper..."):
                try:
                    transcription = transcribe(st.session_state.audio_path, language=WHISPER_LANGUAGE)
                    st.session_state.transcription = transcription
                except Exception as e:
                    st.error(f"Error en la transcripción: {e}")
                    st.stop()

            with st.spinner("🧠 Detectando mejores momentos con Claude..."):
                try:
                    transcript_text = format_for_claude(st.session_state.transcription)
                    moments = detect_viral_moments(
                        transcript_text=transcript_text,
                        episode_number=episode_number,
                        podcast_name=podcast_display,
                    )
                    words_full = st.session_state.transcription.get("words", [])
                    max_clip = CLIP_DURATION_SECONDS + CLIP_DURATION_TOLERANCE
                    for m in moments:
                        snapped_start, snapped_end = snap_to_word_boundaries(
                            m["start_time"], m["end_time"], words_full
                        )
                        if snapped_end - snapped_start > max_clip:
                            snapped_end = snapped_start + CLIP_DURATION_SECONDS
                        m["start_time"]       = snapped_start
                        m["end_time"]         = snapped_end
                        m["duration_seconds"] = round(snapped_end - snapped_start, 1)
                    st.session_state.viral_moments = moments
                    if not moments:
                        st.warning("Claude no detectó momentos virales.")
                except Exception as e:
                    st.error(f"Error al detectar momentos virales: {e}")
                    st.stop()

    # ── Transcript + Spotify ──────────────────────────────────────────────────
    if st.session_state.transcription:
        st.divider()
        st.subheader("📄 Transcript y Spotify")

        full_text = st.session_state.transcription.get("text", "")
        if full_text:
            st.download_button(
                label="⬇️ Descargar transcript completo (.txt)",
                data=full_text,
                file_name=f"transcript_s{season_number:02d}e{episode_number:02d}.txt",
                mime="text/plain",
                key="dl_transcript_full",
            )

        episode_title_input = st.text_input(
            "Título del episodio",
            placeholder="Ej: Cómo fracasar bien y aprender de ello",
            key="episode_title_input",
        )
        if st.button("✍️ Generar título y descripción para Spotify", key="btn_spotify_desc", type="secondary"):
            with st.spinner("Generando con Claude..."):
                try:
                    sp_result = generate_episode_description(
                        transcript_text=st.session_state.transcription.get("text", ""),
                        episode_title=episode_title_input or "Sin título",
                        podcast_name=podcast_display,
                        season_number=season_number,
                        episode_number=episode_number,
                    )
                    st.session_state.episode_description = sp_result
                    # Guardar en archivo
                    _archive_set_spotify(
                        podcast_slug, podcast_display, season_number, episode_number,
                        sp_result["title"], sp_result["description"],
                    )
                except Exception as e:
                    st.error(f"Error al generar descripción: {e}")

        if st.session_state.episode_description:
            d = st.session_state.episode_description
            st.text_input("Título sugerido", value=d["title"], key="spotify_title_out")
            st.text_area("Descripción para Spotify", value=d["description"], height=160, key="spotify_desc_output")

    # ── Momentos y clips ──────────────────────────────────────────────────────
    if st.session_state.viral_moments:
        st.header(f"🎯 {len(st.session_state.viral_moments)} momentos detectados")
        st.caption("Ajusta los timestamps si necesitas, luego genera los clips.")

        selected_clips = []
        for i, moment in enumerate(st.session_state.viral_moments):
            with st.expander(
                f"Momento {i+1}  ·  Score {moment.get('viral_score','—')}/10  ·  {moment.get('duration_seconds','—')}s",
                expanded=True,
            ):
                st.markdown(f"**Hook:** _{moment.get('hook', '')}_")
                st.markdown(f"**Por qué funciona:** {moment.get('reason', '')}")
                c1, c2, c3 = st.columns([2, 2, 1])
                start_edited = c1.text_input("Inicio", value=_seconds_to_hhmmss(moment.get("start_time", 0)), key=f"start_{i}")
                end_edited   = c2.text_input("Fin",    value=_seconds_to_hhmmss(moment.get("end_time",   0)), key=f"end_{i}")
                if c3.checkbox("Incluir", value=True, key=f"include_{i}"):
                    selected_clips.append({"start": start_edited, "end": end_edited})

        if selected_clips and st.button(f"🎬 Generar {len(selected_clips)} clip(s)", type="primary"):
            temp_dir = _get_or_create_temp_dir()
            bg_path  = _save_image_bytes(
                st.session_state.bg_ladrando if podcast_slug == "ladrando-ideas" else st.session_state.bg_ftbp
            )
            results  = []
            progress = st.progress(0)
            clip_num = 0

            for pos, clip_info in enumerate(selected_clips, start=1):
                progress.progress(int((pos-1)/len(selected_clips)*100), text=f"Generando clip {pos}/{len(selected_clips)}...")
                try:
                    start_sec = _hhmmss_to_seconds(clip_info["start"])
                    end_sec   = _hhmmss_to_seconds(clip_info["end"])
                except ValueError as e:
                    st.error(f"Clip {pos}: {e}"); continue
                if end_sec <= start_sec:
                    st.error(f"Clip {pos}: el fin debe ser posterior al inicio."); continue
                if end_sec - start_sec > CLIP_DURATION_SECONDS + CLIP_DURATION_TOLERANCE:
                    end_sec = start_sec + CLIP_DURATION_SECONDS
                clip_num += 1
                try:
                    result = _process_single_clip(
                        audio_path=st.session_state.audio_path,
                        start_sec=start_sec, end_sec=end_sec,
                        background_image_path=bg_path,
                        clip_index=clip_num,
                        season_number=season_number, episode_number=episode_number,
                        podcast_slug=podcast_slug,
                        transcription=st.session_state.transcription,
                        temp_dir=temp_dir,
                    )
                    results.append(result)
                except Exception as e:
                    st.error(f"Error en clip {pos}: {e}"); continue

            progress.progress(100, text="¡Listo!")
            progress.empty()
            st.session_state.clips_ready = results
            # Guardar copies en archivo (sin video ni audio)
            if results:
                _archive_set_clips(podcast_slug, podcast_display, season_number, episode_number, results)

    # ── Resultados ────────────────────────────────────────────────────────────
    if st.session_state.clips_ready:
        st.header("🎉 Clips listos")
        for i, result in enumerate(st.session_state.clips_ready, start=1):
            _render_clip_result(result, i)
    elif not st.session_state.audio_path:
        st.info("👆 Sube el audio del episodio para comenzar.")
    elif not bg_bytes:
        st.info(f"👈 Sube la imagen de fondo para {podcast_display} en el sidebar.")


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 2 — GUIÓN
# ═══════════════════════════════════════════════════════════════════════════════

with tab_script:
    st.subheader("✍️ Generador de Guión")
    st.caption(f"Podcast: **{podcast_display}** · T{season_number:02d}E{episode_number:02d}")

    guest_name = st.text_input("Nombre del invitado", placeholder="Ej: Iván Vázquez", key="script_guest_name")
    guest_bio  = st.text_area(
        "Bio del invitado",
        placeholder="Quién es, qué hace, por qué es relevante para el podcast...",
        height=120,
        key="script_guest_bio",
    )
    topics = st.text_area(
        "Temas a cubrir",
        placeholder="Ej:\n- Cómo nació su empresa después de una bancarrota\n- La decisión de no tener plan B\n- Expansión a mercado USA",
        height=120,
        key="script_topics",
    )
    duration_min = st.slider("Duración estimada del episodio (minutos)", 30, 120, 60, step=15, key="script_duration")

    if st.button("📝 Generar guión", type="primary", key="btn_generate_script"):
        if not guest_name.strip():
            st.warning("Escribe el nombre del invitado para continuar.")
        else:
            with st.spinner("Escribiendo guión con Claude..."):
                try:
                    hosts_str = PODCASTS[podcast_slug].get("hosts", "")
                    script = generate_podcast_script(
                        guest_name=guest_name,
                        guest_bio=guest_bio or "Sin bio proporcionada.",
                        topics=topics or "Temas generales del podcast.",
                        podcast_name=podcast_display,
                        hosts=hosts_str,
                        season_number=season_number,
                        episode_number=episode_number,
                        duration_minutes=duration_min,
                    )
                    st.session_state["generated_script"] = script
                    st.session_state["script_guest_name_saved"] = guest_name
                    # Guardar en archivo
                    _archive_set_script(podcast_slug, podcast_display, season_number, episode_number, guest_name, script)
                    st.success("✅ Guión guardado en el Archivo automáticamente.")
                except Exception as e:
                    st.error(f"Error al generar guión: {e}")

    if st.session_state.get("generated_script"):
        st.divider()
        st.code(st.session_state["generated_script"], language="markdown")
        st.download_button(
            label="⬇️ Descargar guión (.md)",
            data=st.session_state["generated_script"],
            file_name=f"guion_{podcast_slug}_t{season_number:02d}_ep{episode_number:02d}.md",
            mime="text/markdown",
            key="dl_script",
        )


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 3 — ARCHIVO
# ═══════════════════════════════════════════════════════════════════════════════

with tab_archive:
    st.subheader("📚 Archivo de Episodios")
    st.caption("Solo texto: guiones, copies de Instagram y LinkedIn. Sin audio ni video.")

    archive = _load_archive()
    episodes = archive.get("episodes", {})

    if not episodes:
        st.info("El archivo está vacío. Genera guiones o clips para que aparezcan aquí.")
    else:
        # Botón para descargar todo como un solo .txt
        full_text = _archive_to_text(archive)
        st.download_button(
            label=f"⬇️ Descargar archivo completo ({len(episodes)} episodio{'s' if len(episodes) != 1 else ''}) — .txt",
            data=full_text,
            file_name="archivo_episodios.txt",
            mime="text/plain",
            key="dl_archive_full",
        )

        st.divider()

        # Mostrar cada episodio
        for key, ep in sorted(episodes.items(), key=lambda x: (x[1]["podcast_slug"], x[1]["season"], x[1]["episode"]), reverse=True):
            label = f"**{ep['podcast']}** · T{ep['season']:02d}E{ep['episode']:02d}"
            if ep.get("guest_name"):
                label += f" · {ep['guest_name']}"
            if ep.get("date"):
                label += f" · {ep['date']}"

            with st.expander(label, expanded=False):
                if ep.get("script"):
                    st.markdown("**📝 Guión**")
                    st.text_area("", value=ep["script"], height=200, key=f"arc_script_{key}")
                    st.download_button(
                        "⬇️ Guión",
                        data=ep["script"],
                        file_name=f"guion_{key}.txt",
                        mime="text/plain",
                        key=f"dl_arc_script_{key}",
                    )

                if ep.get("spotify_title"):
                    st.markdown("**🎧 Spotify**")
                    st.text(f"Título: {ep['spotify_title']}")
                    st.text_area("", value=ep.get("spotify_description", ""), height=80, key=f"arc_sp_{key}")

                for clip in ep.get("clips", []):
                    st.markdown(f"**🎬 Clip {clip['index']}**")
                    col1, col2 = st.columns(2)
                    with col1:
                        st.caption("Instagram")
                        st.text_area("", value=clip.get("instagram_caption", ""), height=120, key=f"arc_ig_{key}_{clip['index']}")
                    with col2:
                        st.caption("LinkedIn")
                        st.text_area("", value=clip.get("linkedin_caption", ""), height=120, key=f"arc_li_{key}_{clip['index']}")

                # Descargar este episodio solo
                ep_archive = {"episodes": {key: ep}}
                st.download_button(
                    "⬇️ Descargar este episodio (.txt)",
                    data=_archive_to_text(ep_archive),
                    file_name=f"episodio_{key}.txt",
                    mime="text/plain",
                    key=f"dl_arc_ep_{key}",
                )
