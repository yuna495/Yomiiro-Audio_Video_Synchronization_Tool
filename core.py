import os
import json
import shutil
import subprocess
import imageio_ffmpeg

AUDIO_EXTS = {".wav"}
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}
BGM_EXTS = {".wav", ".mp3", ".m4a", ".aac", ".ogg", ".flac"}
DEFAULT_OUTPUT_PATH = "reading_video.mp4"


def _is_within_dir(base_dir, path):
    base_real = os.path.realpath(base_dir)
    path_real = os.path.realpath(path)
    try:
        return os.path.commonpath([base_real, path_real]) == base_real
    except ValueError:
        return False


def _normalize_relative_path(path):
    if not isinstance(path, str):
        raise ValueError("path must be a string")

    path = path.strip()
    if not path:
        raise ValueError("path is empty")

    drive, _ = os.path.splitdrive(path)
    if drive or os.path.isabs(path):
        raise ValueError("absolute paths are not allowed")

    normalized = os.path.normpath(path)
    if normalized in (".", "..") or normalized.startswith(".." + os.sep) or normalized.startswith("../"):
        raise ValueError("path escapes the project directory")

    return normalized.replace("\\", "/")


def sanitize_asset_path(path, subfolder, allowed_exts, project_dir=None):
    normalized = _normalize_relative_path(path)
    parts = normalized.split("/")
    if not parts or parts[0].lower() != subfolder.lower() or len(parts) < 2:
        raise ValueError(f"asset path must be under {subfolder}/")

    ext = os.path.splitext(parts[-1])[1].lower()
    if ext not in allowed_exts:
        raise ValueError(f"unsupported asset extension: {ext}")

    if project_dir:
        abspath = os.path.abspath(os.path.join(project_dir, normalized))
        if not _is_within_dir(project_dir, abspath):
            raise ValueError("asset path escapes the project directory")

    return normalized


def resolve_asset_path(project_dir, path, subfolder, allowed_exts):
    normalized = sanitize_asset_path(path, subfolder, allowed_exts, project_dir)
    abspath = os.path.abspath(os.path.join(project_dir, normalized))
    if not _is_within_dir(project_dir, abspath):
        raise ValueError("asset path escapes the project directory")
    return abspath


def sanitize_output_path(path, project_dir, allow_absolute=False):
    if not isinstance(path, str) or not path.strip():
        return DEFAULT_OUTPUT_PATH

    path = path.strip()
    ext = os.path.splitext(path)[1].lower()
    if ext != ".mp4":
        raise ValueError("output path must be an .mp4 file")

    if os.path.isabs(path):
        if not allow_absolute:
            raise ValueError("absolute output paths from project files are not allowed")
        return os.path.abspath(path)

    normalized = _normalize_relative_path(path)
    abspath = os.path.abspath(os.path.join(project_dir, normalized))
    if not _is_within_dir(project_dir, abspath):
        raise ValueError("output path escapes the project directory")

    return normalized


class AudioClip:
    def __init__(self, clip_id, file_path, display_name, subtitle="", gap_after=0.5, volume=1.0, enabled=True):
        self.id = clip_id
        self.file_path = file_path  # プロジェクト相対パス (audio/clip_xxxx.wav)
        self.display_name = display_name
        self.subtitle = subtitle
        self.gap_after = gap_after
        self.volume = volume
        self.enabled = enabled

    def to_dict(self):
        return {
            "id": self.id,
            "file_path": self.file_path,
            "display_name": self.display_name,
            "subtitle": self.subtitle,
            "gap_after": self.gap_after,
            "volume": self.volume,
            "enabled": self.enabled
        }

    @classmethod
    def from_dict(cls, d):
        return cls(
            clip_id=d["id"],
            file_path=d["file_path"],
            display_name=d["display_name"],
            subtitle=d.get("subtitle", ""),
            gap_after=d.get("gap_after", 0.5),
            volume=d.get("volume", 1.0),
            enabled=d.get("enabled", True)
        )

class BackgroundSetting:
    def __init__(self, bg_id, file_path, display_name, start_clip_id, end_clip_id, enabled=True, transition_type="fade", transition_duration=0.8):
        self.id = bg_id
        self.file_path = file_path  # プロジェクト相対パス (images/bg_xxxx.png)
        self.display_name = display_name
        self.start_clip_id = start_clip_id
        self.end_clip_id = end_clip_id
        self.enabled = enabled
        self.transition_type = transition_type
        self.transition_duration = transition_duration

    def to_dict(self):
        return {
            "id": self.id,
            "file_path": self.file_path,
            "display_name": self.display_name,
            "start_clip_id": self.start_clip_id,
            "end_clip_id": self.end_clip_id,
            "enabled": self.enabled,
            "transition": {
                "type": self.transition_type,
                "duration": self.transition_duration
            }
        }

    @classmethod
    def from_dict(cls, d):
        trans = d.get("transition", {})
        return cls(
            bg_id=d["id"],
            file_path=d["file_path"],
            display_name=d.get("display_name", os.path.basename(d["file_path"])),
            start_clip_id=d["start_clip_id"],
            end_clip_id=d["end_clip_id"],
            enabled=d.get("enabled", True),
            transition_type=trans.get("type", "fade"),
            transition_duration=trans.get("duration", 0.8)
        )

class BgmSetting:
    def __init__(self, bgm_id, file_path, display_name, start_clip_id, end_clip_id, volume=0.12, fade_in=1.0, fade_out=3.0, loop=True, enabled=True):
        self.id = bgm_id
        self.file_path = file_path  # プロジェクト相対パス (bgm/bgm_xxxx.mp3)
        self.display_name = display_name
        self.start_clip_id = start_clip_id
        self.end_clip_id = end_clip_id
        self.volume = volume
        self.fade_in = fade_in
        self.fade_out = fade_out
        self.loop = loop
        self.enabled = enabled

    def to_dict(self):
        return {
            "id": self.id,
            "file_path": self.file_path,
            "display_name": self.display_name,
            "start_clip_id": self.start_clip_id,
            "end_clip_id": self.end_clip_id,
            "volume": self.volume,
            "fade_in": self.fade_in,
            "fade_out": self.fade_out,
            "loop": self.loop,
            "enabled": self.enabled
        }

    @classmethod
    def from_dict(cls, d):
        return cls(
            bgm_id=d["id"],
            file_path=d["file_path"],
            display_name=d.get("display_name", os.path.basename(d["file_path"])),
            start_clip_id=d["start_clip_id"],
            end_clip_id=d["end_clip_id"],
            volume=d.get("volume", 0.12),
            fade_in=d.get("fade_in", 1.0),
            fade_out=d.get("fade_out", 3.0),
            loop=d.get("loop", True),
            enabled=d.get("enabled", True)
        )

class SubtitleStyle:
    def __init__(self, font_family="Yu Mincho", font_size=58, text_color="#EEF1F8", shadow_color="#000000", box_color="#000000", box_opacity=0.5, position="bottom", margin_bottom=95, max_width=1500, line_spacing=16, direction="horizontal"):
        self.font_family = font_family
        self.font_size = font_size
        self.text_color = text_color
        self.shadow_color = shadow_color
        self.box_color = box_color
        self.box_opacity = box_opacity
        self.position = position
        self.margin_bottom = margin_bottom
        self.max_width = max_width
        self.line_spacing = line_spacing
        self.direction = direction

    def to_dict(self):
        return {
            "font_family": self.font_family,
            "font_size": self.font_size,
            "text_color": self.text_color,
            "shadow_color": self.shadow_color,
            "box_color": self.box_color,
            "box_opacity": self.box_opacity,
            "position": self.position,
            "margin_bottom": self.margin_bottom,
            "max_width": self.max_width,
            "line_spacing": self.line_spacing,
            "direction": self.direction
        }

    @classmethod
    def from_dict(cls, d):
        return cls(
            font_family=d.get("font_family", "Yu Gothic"),
            font_size=d.get("font_size", 58),
            text_color=d.get("text_color", "#EEF1F8"),
            shadow_color=d.get("shadow_color", "#000000"),
            box_color=d.get("box_color", "#000000"),
            box_opacity=d.get("box_opacity", 0.5),
            position=d.get("position", "bottom"),
            margin_bottom=d.get("margin_bottom", 95),
            max_width=d.get("max_width", 1500),
            line_spacing=d.get("line_spacing", 16),
            direction=d.get("direction", "horizontal")
        )

class Project:
    def __init__(self, project_dir, name="新規プロジェクト"):
        self.project_dir = project_dir
        self.name = name
        self.width = 1920
        self.height = 1080
        self.fps = 30
        self.output_path = DEFAULT_OUTPUT_PATH
        self.allow_external_output = False
        self.default_interval = 0.5
        self.use_project_settings = False
        self.audio_clips = []
        self.backgrounds = []
        self.bgm_tracks = []
        self.subtitle_style = SubtitleStyle()

    def set_output_path(self, output_path, allow_external=False):
        self.output_path = sanitize_output_path(output_path, self.project_dir, allow_absolute=allow_external)
        self.allow_external_output = allow_external and os.path.isabs(self.output_path)

    def is_trusted_external_output(self, output_path):
        return self.allow_external_output and os.path.abspath(output_path) == os.path.abspath(self.output_path)

    def get_output_abspath(self):
        safe_path = sanitize_output_path(
            self.output_path,
            self.project_dir,
            allow_absolute=self.allow_external_output
        )
        if os.path.isabs(safe_path):
            return safe_path
        return os.path.abspath(os.path.join(self.project_dir, safe_path))

    def save(self):
        os.makedirs(self.project_dir, exist_ok=True)
        data = {
            "app_version": "0.1.0",
            "project_name": self.name,
            "video": {
                "width": self.width,
                "height": self.height,
                "fps": self.fps,
                "output_path": self.output_path
            },
            "default_interval": self.default_interval,
            "use_project_settings": self.use_project_settings,
            "audio_clips": [c.to_dict() for c in self.audio_clips],
            "backgrounds": [b.to_dict() for b in self.backgrounds],
            "bgm_tracks": [bgm.to_dict() for bgm in self.bgm_tracks],
            "subtitle_style": self.subtitle_style.to_dict()
        }
        config_path = os.path.join(self.project_dir, "project.json")
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    @classmethod
    def load(cls, project_dir):
        config_path = os.path.join(project_dir, "project.json")
        if not os.path.exists(config_path):
            return cls(project_dir)

        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        proj = cls(project_dir, data.get("project_name", "新規プロジェクト"))
        video = data.get("video", {})
        proj.width = video.get("width", 1920)
        proj.height = video.get("height", 1080)
        proj.fps = video.get("fps", 30)
        try:
            proj.output_path = sanitize_output_path(
                video.get("output_path", DEFAULT_OUTPUT_PATH),
                project_dir,
                allow_absolute=False
            )
        except ValueError:
            proj.output_path = DEFAULT_OUTPUT_PATH
        proj.default_interval = data.get("default_interval", 0.5)
        proj.use_project_settings = data.get("use_project_settings", False)

        proj.audio_clips = []
        for c in data.get("audio_clips", []):
            try:
                item = dict(c)
                item["file_path"] = sanitize_asset_path(item["file_path"], "audio", AUDIO_EXTS, project_dir)
                proj.audio_clips.append(AudioClip.from_dict(item))
            except Exception:
                continue

        proj.backgrounds = []
        for b in data.get("backgrounds", []):
            try:
                item = dict(b)
                item["file_path"] = sanitize_asset_path(item["file_path"], "images", IMAGE_EXTS, project_dir)
                proj.backgrounds.append(BackgroundSetting.from_dict(item))
            except Exception:
                continue

        proj.bgm_tracks = []
        for bgm in data.get("bgm_tracks", []):
            try:
                item = dict(bgm)
                item["file_path"] = sanitize_asset_path(item["file_path"], "bgm", BGM_EXTS, project_dir)
                proj.bgm_tracks.append(BgmSetting.from_dict(item))
            except Exception:
                continue
        proj.subtitle_style = SubtitleStyle.from_dict(data.get("subtitle_style", {}))

        return proj

    def add_audio_clip(self, src_path, log_callback=print):
        audio_dir = os.path.join(self.project_dir, "audio")
        os.makedirs(audio_dir, exist_ok=True)

        used_ids = {c.id for c in self.audio_clips}
        num = 1
        while f"clip_{num:04d}" in used_ids:
            num += 1
        clip_id = f"clip_{num:04d}"

        dest_filename = f"{clip_id}.wav"
        dest_path = os.path.join(audio_dir, dest_filename)

        log_callback(f"音声ファイルを正規化してコピー中: {os.path.basename(src_path)} -> {dest_filename}")

        # FFmpegで正規化 (48kHz, PCM 16bit, stereo)
        ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
        cmd = [
            ffmpeg_exe, "-y",
            "-i", src_path,
            "-acodec", "pcm_s16le",
            "-ar", "48000",
            "-ac", "2",
            dest_path
        ]

        try:
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, errors="replace")
        except Exception as e:
            if os.path.exists(dest_path):
                try:
                    os.remove(dest_path)
                except Exception:
                    pass
            detail = (getattr(e, "stderr", "") or "").strip().splitlines()
            msg = detail[-1] if detail else str(e)
            raise RuntimeError(f"音声ファイルの変換に失敗しました: {os.path.basename(src_path)} ({msg})") from e

        display_name = os.path.basename(src_path)
        clip = AudioClip(clip_id, f"audio/{dest_filename}", display_name, gap_after=self.default_interval)
        self.audio_clips.append(clip)
        return clip

    def add_background_image(self, src_path):
        images_dir = os.path.join(self.project_dir, "images")
        os.makedirs(images_dir, exist_ok=True)

        used_ids = {b.id for b in self.backgrounds}
        num = 1
        while f"bg_{num:04d}" in used_ids:
            num += 1
        bg_id = f"bg_{num:04d}"

        ext = os.path.splitext(src_path)[1]
        dest_filename = f"{bg_id}{ext}"
        dest_path = os.path.join(images_dir, dest_filename)
        shutil.copy2(src_path, dest_path)

        start_clip = self.audio_clips[0].id if self.audio_clips else ""
        end_clip = self.audio_clips[-1].id if self.audio_clips else ""

        bg = BackgroundSetting(bg_id, f"images/{dest_filename}", os.path.basename(src_path), start_clip, end_clip)
        self.backgrounds.append(bg)
        return bg

    def add_bgm_track(self, src_path):
        bgm_dir = os.path.join(self.project_dir, "bgm")
        os.makedirs(bgm_dir, exist_ok=True)

        used_ids = {bgm.id for bgm in self.bgm_tracks}
        num = 1
        while f"bgm_{num:04d}" in used_ids:
            num += 1
        bgm_id = f"bgm_{num:04d}"

        ext = os.path.splitext(src_path)[1]
        dest_filename = f"{bgm_id}{ext}"
        dest_path = os.path.join(bgm_dir, dest_filename)
        shutil.copy2(src_path, dest_path)

        start_clip = self.audio_clips[0].id if self.audio_clips else ""
        end_clip = self.audio_clips[-1].id if self.audio_clips else ""

        bgm = BgmSetting(bgm_id, f"bgm/{dest_filename}", os.path.basename(src_path), start_clip, end_clip)
        self.bgm_tracks.append(bgm)
        return bgm

    def clean_unused_files(self):
        active_files = set()
        for c in self.audio_clips:
            active_files.add(os.path.normpath(c.file_path))
        for b in self.backgrounds:
            active_files.add(os.path.normpath(b.file_path))
        for bgm in self.bgm_tracks:
            active_files.add(os.path.normpath(bgm.file_path))

        for subfolder in ["audio", "images", "bgm"]:
            dir_path = os.path.join(self.project_dir, subfolder)
            if not os.path.exists(dir_path):
                continue
            for file in os.listdir(dir_path):
                rel_path = os.path.normpath(os.path.join(subfolder, file))
                if rel_path not in active_files:
                    try:
                        os.remove(os.path.join(self.project_dir, rel_path))
                    except Exception:
                        pass
