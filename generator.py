import os
import wave
import json
import math
import subprocess
import numpy as np
import imageio.v2 as imageio
import imageio_ffmpeg
from PIL import Image, ImageDraw, ImageFont, ImageFilter

# 定数
WIDTH = 1920
HEIGHT = 1080
FPS = 30

# タイトルアニメーション設定
TITLE_APPEAR_DURATION = 3
TITLE_HOLD_DURATION = 1.5
BLACKEN_DURATION = 2
DARK_PAUSE_DURATION = 0.5
CREDIT_APPEAR_DURATION = 1.5
CREDIT_HOLD_DURATION = 2
CREDIT_FADE_DURATION = 1.5
FINAL_BLACK_DURATION = 1

TITLE_FONT_SIZE = 380
CREDIT_FONT_SIZE = 120
TITLE_COLOR = (232, 236, 246, 255)
CREDIT_COLOR = (218, 224, 238, 255)
TITLE_GLOW_COLOR = (150, 165, 210, 120)
CREDIT_GLOW_COLOR = (130, 145, 190, 90)

# 字幕設定
SUBTITLE_FONT_SIZE = 58
SUBTITLE_MARGIN_BOTTOM = 95
SUBTITLE_BOX_PADDING_X = 42
SUBTITLE_BOX_PADDING_Y = 26
SUBTITLE_MAX_WIDTH = 1500
SUBTITLE_LINE_SPACING = 16
SUBTITLE_COLOR = (238, 241, 248, 255)
SUBTITLE_SHADOW_COLOR = (0, 0, 0, 190)
SUBTITLE_BOX_COLOR = (0, 0, 0, 125)

BACKGROUND_DARKEN_ALPHA = 55
BG_FADE_DURATION = 0.8

FONT_CANDIDATES = [
    r"C:\Windows\Fonts\yumin.ttf",
    r"C:\Windows\Fonts\YuMincho.ttc",
    r"C:\Windows\Fonts\msmincho.ttc",
    r"C:\Windows\Fonts\BIZ-UDMinchoM.ttc",
    r"C:\Windows\Fonts\msgothic.ttc",
]

def find_font():
    for path in FONT_CANDIDATES:
        if os.path.exists(path):
            return path
    raise FileNotFoundError("日本語フォントが見つかりません。")

# =========================
# イージングと描画共通
# =========================
def ease(t):
    t = max(0.0, min(1.0, t))
    return 0.5 - 0.5 * math.cos(math.pi * t)

def make_background(strength=1.0):
    noise = np.random.normal(0, 2 * strength, (HEIGHT, WIDTH)).astype(np.int16)
    base = np.clip(noise + 2, 0, 14).astype(np.uint8)
    arr = np.zeros((HEIGHT, WIDTH, 4), dtype=np.uint8)
    arr[..., 0] = base
    arr[..., 1] = base
    arr[..., 2] = base
    arr[..., 3] = 255
    return Image.fromarray(arr, "RGBA")

def create_text_layer(text, font, color, y_offset=0):
    layer = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    bbox = draw.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    x = (WIDTH - text_w) // 2 - bbox[0]
    y = (HEIGHT - text_h) // 2 - bbox[1] + y_offset
    draw.text((x, y), text, font=font, fill=color)
    return layer

def apply_alpha_to_color(alpha, color):
    layer = Image.new("RGBA", (WIDTH, HEIGHT), color)
    layer.putalpha(alpha)
    return layer

def fade_alpha(base_alpha, strength):
    strength = max(0.0, min(1.0, strength))
    return base_alpha.point(lambda p: int(p * strength))

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

def darken_background(bg):
    veil = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, BACKGROUND_DARKEN_ALPHA))
    return Image.alpha_composite(bg, veil)

# =========================
# タイトルアニメーションフレーム生成
# =========================
def frame_title_appear(t, title_alpha):
    t = ease(t)
    bg = make_background()
    blur_amount = int((1.0 - t) * 28)
    alpha = fade_alpha(title_alpha, t)
    text = apply_alpha_to_color(alpha, TITLE_COLOR)
    if blur_amount > 0:
        text = text.filter(ImageFilter.GaussianBlur(blur_amount))
    glow_alpha = alpha.filter(ImageFilter.GaussianBlur(24))
    glow = apply_alpha_to_color(glow_alpha, TITLE_GLOW_COLOR)
    wide_glow_alpha = alpha.filter(ImageFilter.GaussianBlur(70))
    wide_glow = apply_alpha_to_color(wide_glow_alpha, (80, 100, 150, 55))
    sharp_strength = max(0.0, (t - 0.55) / 0.45)
    sharp_alpha = fade_alpha(title_alpha, sharp_strength)
    sharp = apply_alpha_to_color(sharp_alpha, TITLE_COLOR)

    frame = Image.alpha_composite(bg, wide_glow)
    frame = Image.alpha_composite(frame, glow)
    frame = Image.alpha_composite(frame, text)
    frame = Image.alpha_composite(frame, sharp)
    return frame.convert("RGB")

def frame_title_blacken(t, title_alpha):
    t_eased = ease(t)
    bg = make_background(strength=1.2)
    white_strength = max(0.0, 1.0 - t_eased * 1.25)
    white_blur = int(4 + t_eased * 18)
    white_alpha = fade_alpha(title_alpha, white_strength)
    white_alpha = white_alpha.filter(ImageFilter.GaussianBlur(white_blur))
    white_text = apply_alpha_to_color(white_alpha, TITLE_COLOR)

    black_peak = math.sin(math.pi * t_eased)
    black_alpha_strength = 0.95 * black_peak
    black_blur = int(8 + t_eased * 42)
    black_alpha = title_alpha.filter(ImageFilter.GaussianBlur(black_blur))
    black_alpha = fade_alpha(black_alpha, black_alpha_strength)
    black_ink = apply_alpha_to_color(black_alpha, (0, 0, 0, 245))

    shadow_alpha = title_alpha.filter(ImageFilter.GaussianBlur(80))
    shadow_alpha = fade_alpha(shadow_alpha, black_peak * 0.45)
    shadow = apply_alpha_to_color(shadow_alpha, (5, 8, 18, 160))

    veil_strength = max(0.0, (t_eased - 0.55) / 0.45)
    veil_alpha = int(255 * veil_strength)
    veil = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, veil_alpha))

    frame = Image.alpha_composite(bg, shadow)
    frame = Image.alpha_composite(frame, white_text)
    frame = Image.alpha_composite(frame, black_ink)
    frame = Image.alpha_composite(frame, veil)
    return frame.convert("RGB")

def frame_dark_pause():
    bg = make_background(strength=0.6)
    veil = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 220))
    frame = Image.alpha_composite(bg, veil)
    return frame.convert("RGB")

def frame_credit_appear(t, credit_alpha):
    t = ease(t)
    bg = make_background(strength=0.8)
    blur_amount = int((1.0 - t) * 18)
    alpha = fade_alpha(credit_alpha, t)
    credit = apply_alpha_to_color(alpha, CREDIT_COLOR)
    if blur_amount > 0:
        credit = credit.filter(ImageFilter.GaussianBlur(blur_amount))
    glow_alpha = alpha.filter(ImageFilter.GaussianBlur(18))
    glow = apply_alpha_to_color(glow_alpha, CREDIT_GLOW_COLOR)
    wide_glow_alpha = alpha.filter(ImageFilter.GaussianBlur(52))
    wide_glow = apply_alpha_to_color(wide_glow_alpha, (70, 85, 135, 40))
    sharp_strength = max(0.0, (t - 0.55) / 0.45)
    sharp_alpha = fade_alpha(credit_alpha, sharp_strength)
    sharp = apply_alpha_to_color(sharp_alpha, CREDIT_COLOR)

    frame = Image.alpha_composite(bg, wide_glow)
    frame = Image.alpha_composite(frame, glow)
    frame = Image.alpha_composite(frame, credit)
    frame = Image.alpha_composite(frame, sharp)
    return frame.convert("RGB")

def frame_credit_fade(t, credit_alpha):
    t = ease(t)
    bg = make_background(strength=0.6)
    alpha_strength = max(0.0, 1.0 - t * 1.15)
    blur_amount = int(2 + t * 28)
    alpha = fade_alpha(credit_alpha, alpha_strength)
    credit = apply_alpha_to_color(alpha, CREDIT_COLOR)
    if blur_amount > 0:
        credit = credit.filter(ImageFilter.GaussianBlur(blur_amount))
    glow_alpha = alpha.filter(ImageFilter.GaussianBlur(18 + int(t * 14)))
    glow = apply_alpha_to_color(glow_alpha, CREDIT_GLOW_COLOR)
    wide_glow_alpha = alpha.filter(ImageFilter.GaussianBlur(52 + int(t * 22)))
    wide_glow = apply_alpha_to_color(wide_glow_alpha, (70, 85, 135, 35))

    veil_strength = max(0.0, (t - 0.35) / 0.65)
    veil = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, int(255 * veil_strength)))

    frame = Image.alpha_composite(bg, wide_glow)
    frame = Image.alpha_composite(frame, glow)
    frame = Image.alpha_composite(frame, credit)
    frame = Image.alpha_composite(frame, veil)
    return frame.convert("RGB")

def frame_final_black():
    return Image.new("RGB", (WIDTH, HEIGHT), (0, 0, 0))

# =========================
# 字幕描画
# =========================
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

def draw_subtitle(frame, text, font):
    if not text:
        return frame
    frame = frame.convert("RGBA")
    overlay = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    lines = wrap_text_japanese(text, font, SUBTITLE_MAX_WIDTH)

    line_bboxes = [draw.textbbox((0, 0), line, font=font) for line in lines]
    line_widths = [bbox[2] - bbox[0] for bbox in line_bboxes]
    line_heights = [bbox[3] - bbox[1] for bbox in line_bboxes]

    text_w = max(line_widths)
    text_h = sum(line_heights) + SUBTITLE_LINE_SPACING * (len(lines) - 1)

    box_w = text_w + SUBTITLE_BOX_PADDING_X * 2
    box_h = text_h + SUBTITLE_BOX_PADDING_Y * 2
    box_x = (WIDTH - box_w) // 2
    box_y = HEIGHT - SUBTITLE_MARGIN_BOTTOM - box_h

    draw.rounded_rectangle(
        (box_x, box_y, box_x + box_w, box_y + box_h),
        radius=22,
        fill=SUBTITLE_BOX_COLOR,
    )

    y = box_y + SUBTITLE_BOX_PADDING_Y
    for idx, line in enumerate(lines):
        line_w = line_widths[idx]
        line_h = line_heights[idx]
        x = (WIDTH - line_w) // 2
        draw.text((x + 3, y + 3), line, font=font, fill=SUBTITLE_SHADOW_COLOR)
        draw.text((x, y), line, font=font, fill=SUBTITLE_COLOR)
        y += line_h + SUBTITLE_LINE_SPACING

    return Image.alpha_composite(frame, overlay)

# =========================
# 音声ミックス・マージ処理
# =========================
def mix_title_audio(title_wav, credit_wav, output_wav, total_duration):
    with wave.open(title_wav, "rb") as w1:
        params = w1.getparams()
        framerate = params.framerate
        nchannels = params.nchannels
        sampwidth = params.sampwidth
        data1 = w1.readframes(w1.getnframes())

    with wave.open(credit_wav, "rb") as w2:
        data2 = w2.readframes(w2.getnframes())

    dtype = np.int16 if sampwidth == 2 else np.uint8
    total_samples = int(total_duration * framerate)
    mixed = np.zeros(total_samples * nchannels, dtype=dtype)

    arr1 = np.frombuffer(data1, dtype=dtype)
    arr2 = np.frombuffer(data2, dtype=dtype)

    offset1 = int(1.0 * framerate) * nchannels
    offset2 = int(7.5 * framerate) * nchannels

    mixed[offset1 : offset1 + len(arr1)] = arr1[:len(mixed) - offset1]
    mixed[offset2 : offset2 + len(arr2)] = arr2[:len(mixed) - offset2]

    with wave.open(output_wav, "wb") as out:
        out.setnchannels(nchannels)
        out.setsampwidth(sampwidth)
        out.setframerate(framerate)
        out.writeframes(mixed.tobytes())

def create_full_audio(title_wav, credit_wav, body_wav, output_wav, opening_duration):
    with wave.open(title_wav, "rb") as w1:
        params = w1.getparams()
        framerate = params.framerate
        nchannels = params.nchannels
        sampwidth = params.sampwidth
        data1 = w1.readframes(w1.getnframes())

    with wave.open(credit_wav, "rb") as w2:
        data2 = w2.readframes(w2.getnframes())

    with wave.open(body_wav, "rb") as w_body:
        body_data = w_body.readframes(w_body.getnframes())

    dtype = np.int16 if sampwidth == 2 else np.uint8
    opening_samples = int(opening_duration * framerate)
    opening_audio = np.zeros(opening_samples * nchannels, dtype=dtype)

    arr1 = np.frombuffer(data1, dtype=dtype)
    arr2 = np.frombuffer(data2, dtype=dtype)

    offset1 = int(1.0 * framerate) * nchannels
    offset2 = int(7.5 * framerate) * nchannels

    opening_audio[offset1 : offset1 + len(arr1)] = arr1[:len(opening_audio) - offset1]
    opening_audio[offset2 : offset2 + len(arr2)] = arr2[:len(opening_audio) - offset2]

    opening_bytes = opening_audio.tobytes()

    with wave.open(output_wav, "wb") as dst:
        dst.setparams(params)
        dst.writeframes(opening_bytes)
        dst.writeframes(body_data)

def mux_audio(video_no_audio, audio_wav, output_mp4):
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    cmd = [
        ffmpeg, "-y",
        "-i", video_no_audio,
        "-i", audio_wav,
        "-c:v", "copy",
        "-c:a", "aac",
        "-b:a", "192k",
        "-shortest",
        output_mp4,
    ]
    subprocess.run(cmd, check=True)

def mux_audio_with_ambient(video_no_audio, audio_wav, bgm_list, output_mp4, opening_duration, body_duration, voice_dir, work_dir, timeline):
    """
    bgm_list: [{'file_name': str, 'start': int, 'end': int, 'volume': float, 'in_bgm_folder': bool}]
    """
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    
    valid_bgm_inputs = []
    for item in bgm_list:
        bgm_file = item['file_name']
        if item.get('in_bgm_folder', False):
            p = os.path.join(voice_dir, "BGM", bgm_file)
        else:
            paths_to_check = [
                os.path.join(voice_dir, bgm_file),
                os.path.join(work_dir, bgm_file)
            ]
            p = None
            for check in paths_to_check:
                if os.path.exists(check):
                    p = check
                    break
        
        if p and os.path.exists(p):
            start_idx = item['start']
            end_idx = item['end']
            
            # 開始時間の決定
            if start_idx == "title":
                abs_start = 0.0
            elif start_idx == "margin":
                abs_start = opening_duration + body_duration
            else:
                start_t = None
                for entry in timeline:
                    if entry['index'] == start_idx:
                        start_t = entry['start']
                        break
                if start_t is None:
                    start_t = timeline[0]['start']
                abs_start = opening_duration + start_t
            
            # 終了時間の決定
            is_end_margin = False
            if end_idx == "title":
                abs_end = opening_duration
            elif end_idx == "margin":
                abs_end = opening_duration + body_duration
                is_end_margin = True
            else:
                end_t = None
                for entry in timeline:
                    if entry['index'] == end_idx:
                        end_t = entry['end']
                        break
                if end_t is None:
                    end_t = timeline[-1]['end']
                abs_end = opening_duration + end_t
            
            valid_bgm_inputs.append({
                'path': p,
                'abs_start': abs_start,
                'abs_end': abs_end,
                'volume': item['volume'],
                'is_end_margin': is_end_margin
            })
            
    if valid_bgm_inputs:
        cmd = [ffmpeg, "-y", "-i", video_no_audio, "-i", audio_wav]
        for bgm in valid_bgm_inputs:
            cmd.extend(["-i", bgm['path']])
            
        filter_parts = []
        filter_parts.append("[1:a]volume=1.0[a1]")
        amix_inputs = ["[a1]"]
        
        for idx, bgm in enumerate(valid_bgm_inputs):
            in_label = f"[{idx + 2}:a]"
            out_label = f"[bgm{idx}]"
            
            duration = bgm['abs_end'] - bgm['abs_start']
            delay_ms = int(bgm['abs_start'] * 1000)
            
            # フェードアウト時間（最後の余韻指定の場合は5.0秒、それ以外は最後の2秒、またはBGMの長さが短い場合はその半分）
            if bgm.get('is_end_margin', False):
                fade_len = 5.0
            else:
                fade_len = min(2.0, duration / 2.0)
            
            filter_parts.append(
                f"{in_label}atrim=0:{duration:.2f},"
                f"afade=t=out:st={duration - fade_len:.2f}:d={fade_len:.2f},"
                f"adelay={delay_ms}|{delay_ms},"
                f"volume={bgm['volume']:.4f}{out_label}"
            )
            amix_inputs.append(out_label)
            
        mix_inputs_str = "".join(amix_inputs)
        filter_parts.append(f"{mix_inputs_str}amix=inputs={len(amix_inputs)}:duration=first:dropout_transition=2[a]")
        
        filter_complex = "; ".join(filter_parts)
        
        cmd.extend([
            "-filter_complex", filter_complex,
            "-map", "0:v",
            "-map", "[a]",
            "-c:v", "copy",
            "-c:a", "aac",
            "-b:a", "192k",
            output_mp4
        ])
    else:
        cmd = [
            ffmpeg, "-y",
            "-i", video_no_audio,
            "-i", audio_wav,
            "-c:v", "copy",
            "-c:a", "aac",
            "-b:a", "192k",
            "-shortest",
            output_mp4
        ]
        
    subprocess.run(cmd, check=True)

# =========================
# 動画生成メインエンジン
# =========================
def run_generation(work_dir, title_text, credit_text, default_interval, intervals_dict, bg_ranges, bgm_settings, log_callback=print):
    """
    work_dir: 作品フォルダの絶対パス
    title_text: タイトルテキスト
    credit_text: 作者テキスト
    default_interval: デフォルト無音秒数
    intervals_dict: 個別無音時間の設定辞書 {音声ファイル番号(int): 秒数(float)}
    bg_ranges: 背景画像設定のリスト [{'image_name': '...', 'start': 3, 'end': 10}, ...]
    bgm_settings: BGM設定 {'enabled': True, 'volume': 0.12}
    """
    log_callback("動画生成タスクを開始します...")
    
    # フォルダ存在確認
    voice_dir = os.path.join(work_dir, "音声ファイル")
    bg_dir = os.path.join(work_dir, "背景画像")
    subtitle_json_path = os.path.join(work_dir, "字幕.json")
    
    if not (os.path.exists(voice_dir) and os.path.exists(bg_dir) and os.path.exists(subtitle_json_path)):
        raise FileNotFoundError("作品フォルダの構成（音声ファイル, 背景画像, 字幕.json）が正しくありません。")
        
    font_path = find_font()
    log_callback(f"フォントを使用します: {font_path}")

    # 出力ファイル定義
    temp_title_no_audio = os.path.join(work_dir, "temp_title_no_audio.mp4")
    temp_title_audio = os.path.join(work_dir, "temp_title_audio.wav")
    temp_title_final = os.path.join(work_dir, "gekka_title_to_credit.mp4")
    
    temp_body_audio = os.path.join(work_dir, "temp_body_audio.wav")
    temp_final_no_audio = os.path.join(work_dir, "temp_final_no_audio.mp4")
    temp_padded_audio = os.path.join(work_dir, "temp_padded_audio.wav")
    output_mp4 = os.path.join(work_dir, "reading_video_final.mp4")

    # 音声ファイルの整理
    title_wav = os.path.join(voice_dir, "001_暁記ミタマ（ノーマル）_げっか。.wav")
    credit_wav = os.path.join(voice_dir, "002_暁記ミタマ（ノーマル）_作、白蛇。.wav")
    
    # ファイル名が異なる場合があるので、001と002で始まるファイルをスキャン
    for filename in os.listdir(voice_dir):
        if filename.endswith(".wav"):
            if filename.startswith("001"):
                title_wav = os.path.join(voice_dir, filename)
            elif filename.startswith("002"):
                credit_wav = os.path.join(voice_dir, filename)

    if not (os.path.exists(title_wav) and os.path.exists(credit_wav)):
        raise FileNotFoundError("タイトル音声(001)、または作者音声(002)が見つかりません。")

    # 1. タイトル＆作者動画の生成
    log_callback("【1/4】タイトル動画のフレームをレンダリング中...")
    title_font = ImageFont.truetype(font_path, TITLE_FONT_SIZE)
    credit_font = ImageFont.truetype(font_path, CREDIT_FONT_SIZE)
    
    title_layer = create_text_layer(title_text, title_font, TITLE_COLOR, y_offset=0)
    title_alpha = title_layer.split()[-1]
    credit_layer = create_text_layer(credit_text, credit_font, CREDIT_COLOR, y_offset=40)
    credit_alpha = credit_layer.split()[-1]

    writer = imageio.get_writer(temp_title_no_audio, fps=FPS, codec="libx264", quality=8, macro_block_size=16)
    
    def append_title_frames(w, duration, frame_func):
        cnt = int(FPS * duration)
        for i in range(cnt):
            t = 1.0 if cnt <= 1 else i / (cnt - 1)
            frame = frame_func(t)
            w.append_data(np.array(frame))

    def append_title_hold(w, duration, frame):
        cnt = int(FPS * duration)
        arr = np.array(frame)
        for _ in range(cnt):
            w.append_data(arr)

    try:
        append_title_frames(writer, TITLE_APPEAR_DURATION, lambda t: frame_title_appear(t, title_alpha))
        append_title_hold(writer, TITLE_HOLD_DURATION, frame_title_appear(1.0, title_alpha))
        append_title_frames(writer, BLACKEN_DURATION, lambda t: frame_title_blacken(t, title_alpha))
        append_title_hold(writer, DARK_PAUSE_DURATION, frame_dark_pause())
        append_title_frames(writer, CREDIT_APPEAR_DURATION, lambda t: frame_credit_appear(t, credit_alpha))
        append_title_hold(writer, CREDIT_HOLD_DURATION, frame_credit_appear(1.0, credit_alpha))
        append_title_frames(writer, CREDIT_FADE_DURATION, lambda t: frame_credit_fade(t, credit_alpha))
        append_title_hold(writer, FINAL_BLACK_DURATION, frame_final_black())
    finally:
        writer.close()

    title_duration = (
        TITLE_APPEAR_DURATION + TITLE_HOLD_DURATION + BLACKEN_DURATION + DARK_PAUSE_DURATION +
        CREDIT_APPEAR_DURATION + CREDIT_HOLD_DURATION + CREDIT_FADE_DURATION + FINAL_BLACK_DURATION
    )
    
    log_callback("タイトル音声を合成中...")
    mix_title_audio(title_wav, credit_wav, temp_title_audio, title_duration)
    
    log_callback("タイトル映像と音声をマージ中...")
    mux_audio(temp_title_no_audio, temp_title_audio, temp_title_final)

    # クリーンアップ
    for f in [temp_title_no_audio, temp_title_audio]:
        if os.path.exists(f):
            os.remove(f)

    # 2. 本文用音声の連結
    log_callback("【2/4】本文音声ファイルを連結中...")
    with open(subtitle_json_path, "r", encoding="utf-8") as f:
        subtitles_data = json.load(f)

    wav_files = {}
    for filename in os.listdir(voice_dir):
        if filename.endswith(".wav"):
            prefix = filename[:3]
            if prefix.isdigit():
                idx = int(prefix)
                if idx >= 3:
                    wav_files[idx] = os.path.join(voice_dir, filename)

    if not wav_files:
        raise ValueError("本文音声ファイル（003〜）が見つかりません。")

    sorted_keys = sorted(wav_files.keys())
    first_key = sorted_keys[0]
    with wave.open(wav_files[first_key], "rb") as wf:
        params = wf.getparams()
        nchannels = params.nchannels
        sampwidth = params.sampwidth
        framerate = params.framerate

    timeline = []
    current_time = 0.0
    audio_segments = []

    for idx, key in enumerate(sorted_keys):
        path = wav_files[key]
        with wave.open(path, "rb") as wf:
            data = wf.readframes(wf.getnframes())
            duration = wf.getnframes() / float(wf.getframerate())
            timeline.append({
                "index": key,
                "start": current_time,
                "end": current_time + duration,
            })
            audio_segments.append(data)
            current_time += duration
            
            # 再生間隔（無音）の挿入
            if idx < len(sorted_keys) - 1:
                interval = intervals_dict.get(key, default_interval)
                if interval > 0:
                    silence_frames = int(interval * framerate)
                    silence_bytes = b"\x00" * silence_frames * nchannels * sampwidth
                    audio_segments.append(silence_bytes)
                    current_time += interval
            else:
                # 最後のフェードアウト用5秒余韻
                final_margin = 5.0
                silence_frames = int(final_margin * framerate)
                silence_bytes = b"\x00" * silence_frames * nchannels * sampwidth
                audio_segments.append(silence_bytes)
                current_time += final_margin

    combined_data = b"".join(audio_segments)
    with wave.open(temp_body_audio, "wb") as out:
        out.setparams(params)
        out.writeframes(combined_data)

    voice_duration = current_time
    log_callback(f"本文音声の連結完了。長さ: {voice_duration:.2f} 秒")

    # 3. 本文映像フレームのレンダリング
    log_callback("【3/4】本文映像のレンダリングを開始します...")
    
    # 背景画像のロードとキャッシュ
    bg_cache = {}
    for r in bg_ranges:
        img_name = r["image_name"]
        if img_name not in bg_cache:
            img_path = os.path.join(bg_dir, img_name)
            if not os.path.exists(img_path):
                raise FileNotFoundError(f"背景画像が見つかりません: {img_path}")
            img = Image.open(img_path)
            bg_cache[img_name] = fit_cover(img, WIDTH, HEIGHT)

    def get_bg_image_name(t):
        # 現在時刻に対応する音声インデックス
        active_item = None
        for item in timeline:
            if item["start"] <= t:
                active_item = item
            else:
                break
        if not active_item and timeline:
            active_item = timeline[0]
            
        if active_item:
            idx = active_item["index"]
            # bg_rangesから合致するものを探索
            for r in bg_ranges:
                if r["start"] <= idx <= r["end"]:
                    return r["image_name"]
            # 合致しなければ最初の画像
            if bg_ranges:
                return bg_ranges[0]["image_name"]
        return list(bg_cache.keys())[0] if bg_cache else None

    def get_prev_bg_image_name(t):
        curr_bg = get_bg_image_name(t)
        prev_bg = None
        for item in reversed(timeline):
            if item["start"] <= t:
                # 逆方向に辿って、現在の背景と異なる最初の背景画像を取得
                idx = item["index"]
                bg_name = None
                for r in bg_ranges:
                    if r["start"] <= idx <= r["end"]:
                        bg_name = r["image_name"]
                        break
                if bg_name and bg_name != curr_bg:
                    prev_bg = bg_name
                    break
        return prev_bg

    def get_bg_change_time(t):
        last_time = 0.0
        last_bg = None
        for item in timeline:
            if item["start"] <= t:
                idx = item["index"]
                bg_name = None
                for r in bg_ranges:
                    if r["start"] <= idx <= r["end"]:
                        bg_name = r["image_name"]
                        break
                if bg_name and bg_name != last_bg:
                    last_time = item["start"]
                    last_bg = bg_name
            else:
                break
        return last_time

    def render_bg_frame(t):
        bg_name = get_bg_image_name(t)
        bg = bg_cache[bg_name]
        
        prev_name = get_prev_bg_image_name(t)
        change_time = get_bg_change_time(t)
        
        if prev_name and prev_name in bg_cache:
            dt = t - change_time
            if 0 <= dt < BG_FADE_DURATION:
                ratio = dt / BG_FADE_DURATION
                ratio = 0.5 - 0.5 * math.cos(math.pi * ratio)
                prev = bg_cache[prev_name]
                bg = Image.blend(prev, bg, ratio)
                
        darkened = darken_background(bg)
        
        # 最終暗転
        last_audio_end = timeline[-1]["end"]
        if t >= last_audio_end:
            fade_len = 5.0
            dt = t - last_audio_end
            ratio = min(1.0, max(0.0, dt / fade_len))
            ratio = 0.5 - 0.5 * math.cos(math.pi * ratio)
            black_veil = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, int(255 * ratio)))
            darkened = Image.alpha_composite(darkened, black_veil)
            
        return darkened

    # ビデオライター
    writer = imageio.get_writer(temp_final_no_audio, fps=FPS, codec="libx264", quality=8, macro_block_size=16)
    subtitle_font = ImageFont.truetype(font_path, SUBTITLE_FONT_SIZE)

    try:
        # 1. オープニング動画の結合
        reader = imageio.get_reader(temp_title_final)
        meta = reader.get_meta_data()
        op_fps = meta.get("fps", FPS)
        op_frames = 0
        for frame in reader:
            img = Image.fromarray(frame).convert("RGB")
            img = fit_cover(img, WIDTH, HEIGHT).convert("RGB")
            writer.append_data(np.array(img))
            op_frames += 1
        reader.close()
        opening_duration = op_frames / float(op_fps)
        log_callback(f"オープニング動画の結合完了。秒数: {opening_duration:.2f} 秒")

        # 2. 本文フレーム描画
        frame_count = int(voice_duration * FPS)
        for f_idx in range(frame_count):
            t = f_idx / FPS
            frame = render_bg_frame(t)
            
            # 字幕 (音声再生中のみ)
            active_item = None
            for item in timeline:
                if item["start"] <= t < item["end"]:
                    active_item = item
                    break
            
            if active_item:
                str_key = f"{active_item['index']:03d}"
                text = subtitles_data.get(str_key, "")
                frame = draw_subtitle(frame, text, subtitle_font)
                
            writer.append_data(np.array(frame.convert("RGB")))
            
            if (f_idx + 1) % (frame_count // 10 or 1) == 0:
                percent = int((f_idx + 1) / frame_count * 100)
                log_callback(f"映像レンダリング中... {percent}%")
    finally:
        writer.close()

    # 4. 音声とBGMの結合
    log_callback("【4/4】最終音声ファイルの合成とマージ中...")
    create_full_audio(title_wav, credit_wav, temp_body_audio, temp_padded_audio, opening_duration)
    
    mux_audio_with_ambient(
        video_no_audio=temp_final_no_audio,
        audio_wav=temp_padded_audio,
        bgm_list=bgm_settings,
        output_mp4=output_mp4,
        opening_duration=opening_duration,
        body_duration=voice_duration,
        voice_dir=voice_dir,
        work_dir=work_dir,
        timeline=timeline
    )

    # 一時ファイルの削除
    log_callback("一時ファイルを削除中...")
    for f in [temp_body_audio, temp_final_no_audio, temp_padded_audio]:
        if os.path.exists(f):
            os.remove(f)
            
    log_callback(f"動画生成完了！出力先: {output_mp4}")
    return output_mp4
