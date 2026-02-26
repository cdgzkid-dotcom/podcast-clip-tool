# CLAUDE.md — Podcast Clip Tool · Ladrando Ideas

## Descripción del Proyecto

**Podcast Clip Tool** es una web app para el podcast **Ladrando Ideas** que automatiza la creación de clips optimizados para TikTok e Instagram Reels a partir de videos de episodios.

### Problema que resuelve
Crear clips de podcast de forma manual es tedioso: hay que cortar el video, agregar subtítulos, escribir captions, etc. Esta app automatiza todo ese proceso.

### Usuarios
- El host del podcast
- La hermana del host (co-productora de contenido)

---

## Stack Tecnológico

| Componente | Tecnología | Versión mínima |
|---|---|---|
| UI / Hosting | Streamlit + Streamlit Cloud | >=1.32.0 |
| Transcripción | OpenAI Whisper API | openai>=1.14.0 |
| IA viral + captions | Anthropic Claude API | anthropic>=0.25.0 |
| Corte y subtítulos | ffmpeg (binario del sistema) | - |
| Python wrapper ffmpeg | ffmpeg-python | >=0.2.0 |
| Secrets local | python-dotenv | >=1.0.0 |

### Modelos de IA
- **Whisper**: `whisper-1` (transcripción en español)
- **Claude**: `claude-sonnet-4-6` — NO cambiar a otros modelos sin consultar

---

## Arquitectura y Flujo de Datos

```
[Usuario sube video (MOV/MP4)]
        ↓
[cutter.py] → detecta orientación (ffprobe)
        ↓
[cutter.py] → corta clip por timestamps (ffmpeg)
        ↓ (si horizontal)
[cutter.py] → center crop 16:9 → 9:16 (ffmpeg)
        ↓
[transcriber.py] → extrae audio MP3 16kHz (ffmpeg)
        ↓
[transcriber.py] → Whisper API → transcript con word timestamps
        ↓
[subtitles.py] → genera ASS palabra-por-palabra (estilo TikTok karaoke)
        ↓
[subtitles.py] → quema subtítulos en video (ffmpeg ass filter)
        ↓
[ai_agent.py] → Claude genera captions TikTok + Instagram
        ↓ (modo automático)
[ai_agent.py] → Claude detecta 3 mejores momentos virales
        ↓
[exporter.py] → naming limpio + empaqueta outputs
        ↓
[app.py] → st.download_button para cada archivo
```

---

## Módulos y Responsabilidades

### `app.py` — Punto de entrada Streamlit
- Interfaz principal: upload, modo manual/auto, configuración
- Orquesta el flujo llamando a los demás módulos
- Maneja session state y progress bar
- **Nunca** contiene lógica de negocio

### `config.py` — Configuración global
- `get_secret(key)`: primero busca en `st.secrets`, luego en `os.environ`
- Constantes de subtítulos, video, audio, naming
- **Todas las constantes deben modificarse aquí**, no en otros módulos

### `cutter.py` — Procesamiento de video
- `detect_orientation(path)`: ffprobe → "vertical" | "horizontal"
- `cut_clip(input, start, end, output)`: corte por timestamps
- `crop_to_vertical(input, output)`: center crop 16:9→9:16
- `process_video(input, start, end, output)`: orquesta detección + corte + crop

### `transcriber.py` — Transcripción
- `extract_audio(video, audio_path)`: extrae MP3 16kHz mono (workaround límite 25MB Whisper)
- `transcribe(video, language="es")`: retorna `{text, segments, words}`
  - `segments`: `[{start, end, text}]`
  - `words`: `[{start, end, word}]`
- `format_for_claude(transcription)`: formatea transcript para prompt de Claude

### `subtitles.py` — Subtítulos TikTok
- `generate_word_ass(words, output_path)`: ASS palabra-por-palabra (karaoke)
- `words_to_srt(words, output_path)`: SRT para descarga
- `burn_subtitles(video, ass_path, output)`: quema con `ffmpeg -vf ass=...`

### `ai_agent.py` — Claude API
- `detect_viral_moments(transcript, episode, min_dur, max_dur)`: retorna 3 momentos
- `generate_caption(clip_transcript, episode, platform)`: TikTok | Instagram

### `exporter.py` — Outputs
- `build_filename(index, episode)`: `clip_01_ladrando-ideas_ep05`
- `package_clip_output(...)`: retorna dict con paths y textos para download buttons

---

## Reglas Críticas del Proyecto

### 🚫 NUNCA hacer esto:
1. **NO ejecutar localmente** — ni `streamlit run`, ni `pip install`, ni `python script.py`
2. **NO crear scripts de prueba local** ni instrucciones para ejecución local
3. **NO agregar rutas de sistema absolutas** en el código (e.g., `/usr/bin/ffmpeg`)
4. **NO guardar archivos de output en el repo** — todo via `tempfile` y `st.download_button`
5. **NO cambiar el modelo de Claude** sin justificación explícita
6. **NO cambiar el stack tecnológico** — las decisiones ya están tomadas

### ✅ SIEMPRE hacer esto:
1. El entorno de desarrollo **ES Streamlit Cloud**
2. Flujo de cambios: **Editar código → Commit → Push → Streamlit Cloud redeploy automático**
3. Usar `tempfile.mkdtemp()` o `tempfile.NamedTemporaryFile()` para archivos temporales
4. Llamar `get_secret(key)` de `config.py` para API keys
5. Limpiar archivos temporales después de usarlos

---

## Variables de Entorno

### En Streamlit Cloud (Settings → Secrets):
```toml
ANTHROPIC_API_KEY = "sk-ant-..."
OPENAI_API_KEY = "sk-..."
```

### En local (archivo `.env`, NO commitear):
```
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
```

---

## Tipos de Video Soportados

| Formato | Orientación | Transformación |
|---|---|---|
| MOV (iPhone) | Vertical 9:16 | Ninguna — usar directo |
| MP4 (Zoom) | Horizontal 16:9 | Center crop → 9:16 |

**Fórmula de crop**: `crop=ih*9/16:ih:(iw-ih*9/16)/2:0`

---

## Outputs por Clip

```
clip_01_ladrando-ideas_ep05.mp4   ← video con subtítulos quemados
clip_01_ladrando-ideas_ep05.srt   ← subtítulos para descargar
caption_tiktok_clip01.txt         ← caption con hashtags TikTok
caption_instagram_clip01.txt      ← caption Instagram
transcript_clip01.txt             ← transcript completo del clip
```

---

## Flujo de Deploy

```
GitHub (main branch)
    ↓ push
Streamlit Cloud (redeploy automático en ~1-2 min)
    ↓
https://[app-name].streamlit.app
```

**Streamlit Cloud** monitorea el branch `main` y hace redeploy automático en cada push.

---

## Decisiones de Arquitectura (No Cuestionar)

| Decisión | Razón |
|---|---|
| **Whisper API** (no local) | Streamlit Cloud free tier no tiene GPU; la API maneja español perfectamente |
| **Streamlit** (no React/Next.js) | Simplicidad total; no requiere frontend separado; deploy en un click |
| **ASS subtítulos** (no SRT+drawtext) | Mejor control de estilo TikTok; fuente, color, outline en un solo archivo |
| **Whisper verbose_json** | Necesario para `timestamp_granularities=["word"]` — word-level timestamps para karaoke |
| **Extracción de audio antes de Whisper** | Whisper API tiene límite de 25MB; un MP3 16kHz mono es ~10x más pequeño que el video |
| **center crop (no letterbox)** | TikTok/Instagram requieren 9:16 sin barras negras |
| **Download-only outputs** | Streamlit Cloud filesystem es efímero; no hay persistencia entre sesiones |

---

## Contexto del Podcast

**Ladrando Ideas** es un podcast en español. Los videos pueden venir de:
- Grabaciones de iPhone (MOV, vertical, alta calidad)
- Grabaciones de Zoom (MP4, horizontal, calidad variable)

El contenido es conversacional, en español latinoamericano.

---

*Última actualización: Setup inicial del proyecto*
