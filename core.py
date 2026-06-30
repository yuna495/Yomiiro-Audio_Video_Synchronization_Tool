import os
import json
import shutil
import subprocess
import imageio_ffmpeg

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
    def __init__(self, bg_id, file_path, start_clip_id, end_clip_id, enabled=True, transition_type="fade", transition_duration=0.8):
        self.id = bg_id
        self.file_path = file_path  # プロジェクト相対パス (images/bg_xxxx.png)
        self.start_clip_id = start_clip_id
        self.end_clip_id = end_clip_id
        self.enabled = enabled
        self.transition_type = transition_type
        self.transition_duration = transition_duration

    def to_dict(self):
        return {
            "id": self.id,
            "file_path": self.file_path,
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
            start_clip_id=d["start_clip_id"],
            end_clip_id=d["end_clip_id"],
            enabled=d.get("enabled", True),
            transition_type=trans.get("type", "fade"),
            transition_duration=trans.get("duration", 0.8)
        )

class BgmSetting:
    def __init__(self, bgm_id, file_path, start_clip_id, end_clip_id, volume=0.12, fade_in=1.0, fade_out=3.0, loop=True, enabled=True):
        self.id = bgm_id
        self.file_path = file_path  # プロジェクト相対パス (bgm/bgm_xxxx.mp3)
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
            start_clip_id=d["start_clip_id"],
            end_clip_id=d["end_clip_id"],
            volume=d.get("volume", 0.12),
            fade_in=d.get("fade_in", 1.0),
            fade_out=d.get("fade_out", 3.0),
            loop=d.get("loop", True),
            enabled=d.get("enabled", True)
        )

class SubtitleStyle:
    def __init__(self, font_family="Yu Gothic", font_size=58, text_color="#EEF1F8", shadow_color="#000000", box_color="#000000", box_opacity=0.5, position="bottom", margin_bottom=95, max_width=1500, line_spacing=16):
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
            "line_spacing": self.line_spacing
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
            line_spacing=d.get("line_spacing", 16)
        )

class Project:
    def __init__(self, project_dir, name="新規プロジェクト"):
        self.project_dir = project_dir
        self.name = name
        self.width = 1920
        self.height = 1080
        self.fps = 30
        self.output_path = "reading_video.mp4"
        self.default_interval = 0.5
        self.audio_clips = []
        self.backgrounds = []
        self.bgm_tracks = []
        self.subtitle_style = SubtitleStyle()

    def get_output_abspath(self):
        if os.path.isabs(self.output_path):
            return self.output_path
        return os.path.abspath(os.path.join(self.project_dir, self.output_path))

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
        proj.output_path = video.get("output_path", "reading_video.mp4")
        proj.default_interval = data.get("default_interval", 0.5)
        
        proj.audio_clips = [AudioClip.from_dict(c) for c in data.get("audio_clips", [])]
        proj.backgrounds = [BackgroundSetting.from_dict(b) for b in data.get("backgrounds", [])]
        proj.bgm_tracks = [BgmSetting.from_dict(bgm) for bgm in data.get("bgm_tracks", [])]
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
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception as e:
            log_callback(f"FFmpegによる変換に失敗したため、直接コピーを試みます: {e}")
            shutil.copy2(src_path, dest_path)

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
        
        bg = BackgroundSetting(bg_id, f"images/{dest_filename}", start_clip, end_clip)
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
        
        bgm = BgmSetting(bgm_id, f"bgm/{dest_filename}", start_clip, end_clip)
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
