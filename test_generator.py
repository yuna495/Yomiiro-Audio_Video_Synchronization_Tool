import os
import shutil
import json
import struct
import wave
from PIL import Image
import generator

TEST_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_project")

def create_dummy_wav(path, duration=2.0, channels=2, sample_width=2, framerate=44100):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with wave.open(path, 'wb') as w:
        w.setnchannels(channels)
        w.setsampwidth(sample_width)
        w.setframerate(framerate)
        n_samples = int(duration * framerate)
        # 16-bit stereo silent data
        data = struct.pack('<h', 0) * (n_samples * channels)
        w.writeframes(data)

def create_dummy_img(path, color=(50, 50, 50)):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    img = Image.new("RGB", (1920, 1080), color)
    img.save(path)

def setup_test_project(has_bgm_folder=True):
    if os.path.exists(TEST_DIR):
        shutil.rmtree(TEST_DIR)
    os.makedirs(TEST_DIR, exist_ok=True)
    
    # 音声ファイル
    voice_dir = os.path.join(TEST_DIR, "音声ファイル")
    create_dummy_wav(os.path.join(voice_dir, "001_title.wav"), duration=2.0)
    create_dummy_wav(os.path.join(voice_dir, "002_credit.wav"), duration=2.0)
    create_dummy_wav(os.path.join(voice_dir, "003_body1.wav"), duration=3.0)
    create_dummy_wav(os.path.join(voice_dir, "004_body2.wav"), duration=3.0)
    
    if has_bgm_folder:
        bgm_dir = os.path.join(voice_dir, "BGM")
        create_dummy_wav(os.path.join(bgm_dir, "bgm1.wav"), duration=15.0)
        create_dummy_wav(os.path.join(bgm_dir, "bgm2.wav"), duration=15.0)
    else:
        # フォールバック用BGMをルートまたは音声ファイル下に配置
        create_dummy_wav(os.path.join(voice_dir, "ambient_main.wav"), duration=15.0)
        
    # 背景画像
    bg_dir = os.path.join(TEST_DIR, "背景画像")
    create_dummy_img(os.path.join(bg_dir, "bg1.png"), color=(40, 40, 80))
    create_dummy_img(os.path.join(bg_dir, "bg2.png"), color=(80, 40, 40))
    
    # 字幕.json
    subtitles = {
        "003": "これはテスト用の字幕１です。",
        "004": "これはテスト用の字幕２です。"
    }
    with open(os.path.join(TEST_DIR, "字幕.json"), "w", encoding="utf-8") as f:
        json.dump(subtitles, f, ensure_ascii=False, indent=2)

def run_test_case(name, bgm_settings):
    print(f"\n======================================")
    print(f"テスト実行: {name}")
    print(f"======================================")
    
    bg_ranges = [
        {'image_name': 'bg1.png', 'start': 3, 'end': 3},
        {'image_name': 'bg2.png', 'start': 4, 'end': 4}
    ]
    
    # テスト対象フォルダ内の古い成果物を削除
    output_mp4 = os.path.join(TEST_DIR, "reading_video_final.mp4")
    if os.path.exists(output_mp4):
        os.remove(output_mp4)
        
    generator.run_generation(
        work_dir=TEST_DIR,
        title_text="テスト作品",
        credit_text="作　テスト著者",
        default_interval=1.0,
        intervals_dict={3: 1.0},
        bg_ranges=bg_ranges,
        bgm_settings=bgm_settings,
        log_callback=print
    )
    
    if os.path.exists(output_mp4):
        print(f"テスト成功: {output_mp4} が生成されました。")
    else:
        raise FileNotFoundError(f"テスト失敗: {output_mp4} が生成されませんでした。")

def main():
    try:
        # 1. 複数BGM (BGMフォルダあり) のテスト
        setup_test_project(has_bgm_folder=True)
        # bgm1.wav は タイトル(冒頭)から余韻(ラスト)まで。bgm2.wav は 004から余韻(ラスト)まで。
        bgm_settings_multi = [
            {
                'file_name': 'bgm1.wav',
                'start': 'title',
                'end': 'margin',
                'volume': 0.1,
                'in_bgm_folder': True
            },
            {
                'file_name': 'bgm2.wav',
                'start': 4,
                'end': 'margin',
                'volume': 0.15,
                'in_bgm_folder': True
            }
        ]
        run_test_case("複数BGMかつタイトル・余韻指定あり", bgm_settings_multi)
        
        # 2. 単一フォールバックBGMのテスト
        setup_test_project(has_bgm_folder=False)
        bgm_settings_fallback = [
            {
                'file_name': 'ambient_main.wav',
                'start': 'title',
                'end': 'margin',
                'volume': 0.12,
                'in_bgm_folder': False
            }
        ]
        run_test_case("単一フォールバックBGMかつタイトル・余韻指定あり", bgm_settings_fallback)
        
        print("\nすべての自動テストが正常に完了しました！")
    finally:
        # クリーンアップ
        if os.path.exists(TEST_DIR):
            shutil.rmtree(TEST_DIR)
            print("テスト用フォルダをクリーンアップしました。")

if __name__ == "__main__":
    main()
