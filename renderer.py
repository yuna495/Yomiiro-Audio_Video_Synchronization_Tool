import os
import wave
import math
import subprocess
import numpy as np
import imageio.v2 as imageio
import imageio_ffmpeg
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from core import Project, AudioClip, BackgroundSetting, BgmSetting, SubtitleStyle

import winreg

def get_system_font_paths():
    font_map = {}
    system_fonts_dir = os.path.join(os.environ.get("SystemRoot", "C:\\Windows"), "Fonts")
    user_fonts_dir = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft\\Windows\\Fonts")
    
    targets = [
        (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows NT\CurrentVersion\Fonts"),
        (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows NT\CurrentVersion\Fonts")
    ]
    
    for hkey, subkey in targets:
        try:
            with winreg.OpenKey(hkey, subkey) as key:
                for i in range(10000):
                    try:
                        name, value, _ = winreg.EnumValue(key, i)
                        family = name.split(" (")[0]
                        families = [f.strip() for f in family.split("&")]
                        if not os.path.isabs(value):
                            full_path = os.path.join(user_fonts_dir, value)
                            if not os.path.exists(full_path):
                                full_path = os.path.join(system_fonts_dir, value)
                        else:
                            full_path = value
                        if os.path.exists(full_path):
                            for f in families:
                                font_map[f] = full_path
                    except OSError:
                        break
        except Exception:
            pass
    return font_map

def find_font(font_family=None):
    # ユーザー指定のファミリー名がある場合、システムフォントから優先検索
    if font_family:
        font_map = get_system_font_paths()
        if font_family in font_map:
            return font_map[font_family]

    # 1. アプリのディレクトリ直下、または fonts/ フォルダ内の日本語フォントを優先探索
    script_dir = os.path.dirname(os.path.abspath(__file__))
    exts = (".ttf", ".otf", ".ttc")
    
    # アプリ直下を探索
    if os.path.exists(script_dir):
        for file in os.listdir(script_dir):
            if file.lower().endswith(exts):
                return os.path.join(script_dir, file)
                
    # fonts サブフォルダを探索
    fonts_dir = os.path.join(script_dir, "fonts")
    if os.path.exists(fonts_dir):
        for file in os.listdir(fonts_dir):
            if file.lower().endswith(exts):
                return os.path.join(fonts_dir, file)

    # 2. Windowsシステム標準フォントの候補
    system_candidates = [
        r"C:\Windows\Fonts\yumin.ttf",
        r"C:\Windows\Fonts\YuMincho.ttc",
        r"C:\Windows\Fonts\msmincho.ttc",
        r"C:\Windows\Fonts\BIZ-UDMinchoM.ttc",
        r"C:\Windows\Fonts\msgothic.ttc",
    ]
    for path in system_candidates:
        if os.path.exists(path):
            return path
            
    raise FileNotFoundError("日本語フォントが見つかりません。")

def hex_to_rgba(hex_str, opacity=1.0):
    hex_str = hex_str.lstrip('#')
    lv = len(hex_str)
    if lv == 6:
        r, g, b = tuple(int(hex_str[i:i+2], 16) for i in (0, 2, 4))
    elif lv == 3:
        r, g, b = tuple(int(hex_str[i:i+1], 16) * 17 for i in (0, 1, 2))
    else:
        r, g, b = 255, 255, 255
    return (r, g, b, int(255 * opacity))

def get_wav_duration(path):
    if not os.path.exists(path):
        return 0.0
    try:
        with wave.open(path, "rb") as wf:
            return wf.getnframes() / float(wf.getframerate())
    except Exception:
        return 0.0

def fit_cover(image, width, height):
    image = image.convert("RGB")
    src_w, src_h = image.size
    scale = max(width / src_w, height / src_h)
    new_w = int(src_w * scale)
    new_h = int(src_h * scale)
    resized = image.resize((new_w, new_h), Image.LANCZOS)
    left = (new_w - width) // 2
    top = (new_h - height) // 2
    cropped = resized.crop((left, top, left + width, top + height))
    return cropped.convert("RGBA")

def wrap_text_japanese(text, font, max_width):
    lines = []
    current = ""
    dummy = Image.new("RGBA", (10, 10), (0, 0, 0, 0))
    draw = ImageDraw.Draw(dummy)

    for ch in text:
        test = current + ch
        bbox = draw.textbbox((0, 0), test, font=font)
        w = bbox[2] - bbox[0]
        if w <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = ch
    if current:
        lines.append(current)
    return lines

def draw_subtitle_on_frame(frame, text, style, font, width, height):
    if not text:
        return frame
    
    frame = frame.convert("RGBA")
    overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    
    lines = wrap_text_japanese(text, font, style.max_width)
    
    line_bboxes = [draw.textbbox((0, 0), line, font=font) for line in lines]
    line_widths = [bbox[2] - bbox[0] for bbox in line_bboxes]
    line_heights = [bbox[3] - bbox[1] for bbox in line_bboxes]
    
    text_w = max(line_widths) if line_widths else 0
    text_h = sum(line_heights) + style.line_spacing * (len(lines) - 1) if line_heights else 0
    
    padding_x = 42
    padding_y = 26
    
    box_w = text_w + padding_x * 2
    box_h = text_h + padding_y * 2
    box_x = (width - box_w) // 2
    
    # 位置の設定
    if style.position == "top":
        box_y = style.margin_bottom
    elif style.position == "center":
        box_y = (height - box_h) // 2
    else: # bottom
        box_y = height - style.margin_bottom - box_h
        
    box_color_rgba = hex_to_rgba(style.box_color, style.box_opacity)
    
    draw.rounded_rectangle(
        (box_x, box_y, box_x + box_w, box_y + box_h),
        radius=22,
        fill=box_color_rgba,
    )
    
    text_color_rgba = hex_to_rgba(style.text_color, 1.0)
    shadow_color_rgba = hex_to_rgba(style.shadow_color, 0.75)
    
    y = box_y + padding_y
    for idx, line in enumerate(lines):
        line_w = line_widths[idx]
        line_h = line_heights[idx]
        x = (width - line_w) // 2
        # シャドウ/エッジ
        draw.text((x + 3, y + 3), line, font=font, fill=shadow_color_rgba)
        draw.text((x, y), line, font=font, fill=text_color_rgba)
        y += line_h + style.line_spacing
        
    return Image.alpha_composite(frame, overlay)

class VideoTimeline:
    def __init__(self, project: Project):
        self.project = project
        self.clips_timeline = [] # [{'clip': AudioClip, 'start': float, 'end': float, 'total': float, 'duration': float}]
        self.total_duration = 0.0
        self.calculate()

    def calculate(self):
        current_time = 0.0
        enabled_clips = [c for c in self.project.audio_clips if c.enabled]
        
        for idx, clip in enumerate(enabled_clips):
            abspath = os.path.abspath(os.path.join(self.project.project_dir, clip.file_path))
            dur = get_wav_duration(abspath)
            
            start = current_time
            end = current_time + dur
            
            # gap_after
            gap = clip.gap_after if idx < len(enabled_clips) - 1 else 5.0 # 最後のクリップの後に5秒余韻
            total = end + gap
            
            self.clips_timeline.append({
                "clip": clip,
                "start": start,
                "end": end,
                "total": total,
                "duration": dur
            })
            current_time = total
            
        self.total_duration = current_time

    def get_clip_times(self, clip_id):
        for entry in self.clips_timeline:
            if entry["clip"].id == clip_id:
                return entry["start"], entry["end"], entry["total"]
        return None

def generate_preview_image(project: Project, clip_id: str):
    """特定のクリップにおける背景画像＋字幕の静止画プレビュー画像を生成する"""
    timeline = VideoTimeline(project)
    times = timeline.get_clip_times(clip_id)
    if not times:
        # クリップが見つからない場合は黒背景
        return Image.new("RGB", (project.width, project.height), (30, 30, 30))
    
    start_time, _, _ = times
    
    # 該当する背景画像を探索
    bg_image_path = None
    for bg_set in project.backgrounds:
        if bg_set.enabled:
            # clip_idが適用範囲内にあるか判定
            start_times = timeline.get_clip_times(bg_set.start_clip_id)
            end_times = timeline.get_clip_times(bg_set.end_clip_id)
            if start_times and end_times:
                if start_times[0] <= start_time < end_times[2]:
                    bg_image_path = os.path.abspath(os.path.join(project.project_dir, bg_set.file_path))
                    break
                    
    # 画像生成
    if bg_image_path and os.path.exists(bg_image_path):
        try:
            bg_img = Image.open(bg_image_path)
            frame = fit_cover(bg_img, project.width, project.height)
        except Exception:
            frame = Image.new("RGB", (project.width, project.height), (0, 0, 0))
    else:
        frame = Image.new("RGB", (project.width, project.height), (0, 0, 0))
        
    # 暗幕
    veil = Image.new("RGBA", (project.width, project.height), (0, 0, 0, 55))
    frame = Image.alpha_composite(frame.convert("RGBA"), veil)
    
    # 字幕描画
    target_clip = next((c for c in project.audio_clips if c.id == clip_id), None)
    if target_clip and target_clip.subtitle:
        try:
            font_path = find_font(project.subtitle_style.font_family)
            font = ImageFont.truetype(font_path, project.subtitle_style.font_size)
            frame = draw_subtitle_on_frame(frame, target_clip.subtitle, project.subtitle_style, font, project.width, project.height)
        except Exception as e:
            print(f"Preview subtitle error: {e}")
            
    return frame.convert("RGB")

def render_movie(project: Project, log_callback=print):
    log_callback("動画レンダリングパラメータの計算中...")
    timeline = VideoTimeline(project)
    
    if not timeline.clips_timeline:
        raise ValueError("有効な音声クリップがありません。")
        
    font_path = find_font(project.subtitle_style.font_family)
    
    temp_voice_wav = os.path.join(project.project_dir, "temp_voice_combined.wav")
    temp_video_no_audio = os.path.join(project.project_dir, "temp_video_no_audio.mp4")
    output_mp4 = project.get_output_abspath()
    
    # 1. 音声ファイルの連結
    log_callback("音声ファイルを連結中...")
    first_clip_path = os.path.abspath(os.path.join(project.project_dir, timeline.clips_timeline[0]["clip"].file_path))
    with wave.open(first_clip_path, "rb") as wf:
        params = wf.getparams()
        nchannels = params.nchannels
        sampwidth = params.sampwidth
        framerate = params.framerate
        
    audio_segments = []
    for idx, entry in enumerate(timeline.clips_timeline):
        clip = entry["clip"]
        clip_abspath = os.path.abspath(os.path.join(project.project_dir, clip.file_path))
        
        with wave.open(clip_abspath, "rb") as wf:
            # クリップごとの音量を調整（必要なら）
            data = wf.readframes(wf.getnframes())
            if clip.volume != 1.0:
                dtype = np.int16 if sampwidth == 2 else np.uint8
                arr = np.frombuffer(data, dtype=dtype).astype(np.float32)
                arr *= clip.volume
                arr = np.clip(arr, np.iinfo(dtype).min, np.iinfo(dtype).max).astype(dtype)
                data = arr.tobytes()
            audio_segments.append(data)
            
        # gap_after（無音）の挿入
        gap = clip.gap_after if idx < len(timeline.clips_timeline) - 1 else 5.0
        if gap > 0:
            silence_frames = int(gap * framerate)
            silence_bytes = b"\x00" * silence_frames * nchannels * sampwidth
            audio_segments.append(silence_bytes)
            
    combined_audio = b"".join(audio_segments)
    with wave.open(temp_voice_wav, "wb") as out:
        out.setparams(params)
        out.writeframes(combined_audio)
        
    # 2. 映像フレームの生成
    log_callback("映像レンダリングを開始します...")
    
    # 背景画像のキャッシュ
    bg_cache = {}
    for bg_set in project.backgrounds:
        if bg_set.enabled:
            img_abspath = os.path.abspath(os.path.join(project.project_dir, bg_set.file_path))
            if os.path.exists(img_abspath):
                try:
                    img = Image.open(img_abspath)
                    bg_cache[bg_set.id] = fit_cover(img, project.width, project.height)
                except Exception as e:
                    log_callback(f"警告: 画像の読み込みに失敗しました: {img_abspath} ({e})")
                    
    def get_bg_for_time(t):
        # 現在時刻に適用される背景設定を特定
        active_bg_set = None
        for bg_set in project.backgrounds:
            if bg_set.enabled:
                start_times = timeline.get_clip_times(bg_set.start_clip_id)
                end_times = timeline.get_clip_times(bg_set.end_clip_id)
                if start_times and end_times:
                    if start_times[0] <= t < end_times[2]:
                        active_bg_set = bg_set
                        break
        return active_bg_set

    def get_transition_background(t):
        curr_bg_set = get_bg_for_time(t)
        if not curr_bg_set or curr_bg_set.id not in bg_cache:
            return None, 0.0, None
            
        # 切り替えタイミング（現在の背景設定が開始されるクリップの開始時間）
        start_times = timeline.get_clip_times(curr_bg_set.start_clip_id)
        change_time = start_times[0] if start_times else 0.0
        
        # クロスフェード用の直前の背景を探索
        prev_bg_set = None
        # change_time直前(少し前)の時刻で背景を調べる
        if change_time > 0.05:
            prev_bg_set = get_bg_for_time(change_time - 0.05)
            
        if prev_bg_set and prev_bg_set.id != curr_bg_set.id and prev_bg_set.id in bg_cache:
            dt = t - change_time
            if 0 <= dt < curr_bg_set.transition_duration:
                return bg_cache[curr_bg_set.id], dt / curr_bg_set.transition_duration, bg_cache[prev_bg_set.id]
                
        return bg_cache[curr_bg_set.id], 1.0, None

    # imageio ライターの開始
    writer = imageio.get_writer(temp_video_no_audio, fps=project.fps, codec="libx264", quality=8, macro_block_size=16)
    subtitle_font = ImageFont.truetype(font_path, project.subtitle_style.font_size)
    
    total_frames = int(timeline.total_duration * project.fps)
    
    try:
        for f_idx in range(total_frames):
            t = f_idx / project.fps
            
            # 背景の取得と合成
            bg_img, blend_ratio, prev_bg_img = get_transition_background(t)
            if bg_img:
                if prev_bg_img and blend_ratio < 1.0:
                    # イージング
                    ratio = 0.5 - 0.5 * math.cos(math.pi * blend_ratio)
                    frame = Image.blend(prev_bg_img, bg_img, ratio)
                else:
                    frame = bg_img.copy()
            else:
                # 背景が無い場合は黒
                frame = Image.new("RGBA", (project.width, project.height), (0, 0, 0, 255))
                
            # 暗幕 (全体を少し暗くして字幕の視認性を上げる)
            veil = Image.new("RGBA", (project.width, project.height), (0, 0, 0, 55))
            frame = Image.alpha_composite(frame, veil)
            
            # 字幕の描画 (該当クリップの音声が鳴っている間のみ)
            active_clip_entry = None
            for entry in timeline.clips_timeline:
                if entry["start"] <= t < entry["end"]:
                    active_clip_entry = entry
                    break
                    
            if active_clip_entry:
                text = active_clip_entry["clip"].subtitle
                frame = draw_subtitle_on_frame(frame, text, project.subtitle_style, subtitle_font, project.width, project.height)
                
            # 最後の余韻部分での全体フェードアウト (最後の5秒)
            last_clip_end = timeline.clips_timeline[-1]["end"]
            if t >= last_clip_end:
                dt = t - last_clip_end
                fade_len = 5.0
                ratio = min(1.0, max(0.0, dt / fade_len))
                ratio = 0.5 - 0.5 * math.cos(math.pi * ratio)
                black_veil = Image.new("RGBA", (project.width, project.height), (0, 0, 0, int(255 * ratio)))
                frame = Image.alpha_composite(frame, black_veil)
                
            writer.append_data(np.array(frame.convert("RGB")))
            
            if (f_idx + 1) % max(1, total_frames // 20) == 0:
                percent = int((f_idx + 1) / total_frames * 100)
                log_callback(f"PROGRESS:{percent}")
    finally:
        writer.close()
        
    # 3. 音声とBGMの合成
    log_callback("音声とBGMを最終動画へマージ中...")
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    
    cmd = [ffmpeg_exe, "-y", "-i", temp_video_no_audio, "-i", temp_voice_wav]
    
    # 有効なBGMトラックの入力アセットを追加
    active_bgms = [bgm for bgm in project.bgm_tracks if bgm.enabled]
    for bgm in active_bgms:
        bgm_abspath = os.path.abspath(os.path.join(project.project_dir, bgm.file_path))
        if bgm.loop:
            # ループ設定
            cmd.extend(["-stream_loop", "-1"])
        cmd.extend(["-i", bgm_abspath])
        
    # オーディオフィルタの設定
    filter_parts = []
    # 連結音声はインデックス 1
    filter_parts.append("[1:a]volume=1.0[main_a]")
    amix_inputs = ["[main_a]"]
    
    for idx, bgm in enumerate(active_bgms):
        # BGMのインデックスは 2 以降
        in_label = f"[{idx + 2}:a]"
        out_label = f"[bgm_proc{idx}]"
        
        # タイムライン上でのBGM適用開始・終了時刻
        start_times = timeline.get_clip_times(bgm.start_clip_id)
        end_times = timeline.get_clip_times(bgm.end_clip_id)
        
        abs_start = start_times[0] if start_times else 0.0
        abs_end = end_times[2] if end_times else timeline.total_duration
        duration = abs_end - abs_start
        
        delay_ms = int(abs_start * 1000)
        
        # フェードアウトの設定
        fade_out_start = duration - bgm.fade_out
        if fade_out_start < 0:
            fade_out_start = 0.0
            
        # トリム -> フェードイン -> フェードアウト -> 音量設定 -> ディレイ
        filter_parts.append(
            f"{in_label}atrim=0:{duration:.2f},"
            f"afade=t=in:st=0:d={bgm.fade_in:.2f},"
            f"afade=t=out:st={fade_out_start:.2f}:d={bgm.fade_out:.2f},"
            f"volume={bgm.volume:.4f},"
            f"adelay={delay_ms}|{delay_ms}"
            f"{out_label}"
        )
        amix_inputs.append(out_label)
        
    mix_inputs_str = "".join(amix_inputs)
    # amixで全音声をミックス
    filter_parts.append(f"{mix_inputs_str}amix=inputs={len(amix_inputs)}:duration=first:dropout_transition=2[a]")
    
    filter_complex = "; ".join(filter_parts)
    
    # ffmpegの最終結合コマンドを組み立て
    cmd.extend([
        "-filter_complex", filter_complex,
        "-map", "0:v",
        "-map", "[a]",
        "-c:v", "copy",
        "-c:a", "aac",
        "-b:a", "192k",
        output_mp4
    ])
    
    try:
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        log_callback(f"動画の出力が完了しました！ -> {output_mp4}")
    finally:
        # 一時ファイルの削除
        for f in [temp_voice_wav, temp_video_no_audio]:
            if os.path.exists(f):
                try:
                    os.remove(f)
                except Exception:
                    pass
                    
    return output_mp4
