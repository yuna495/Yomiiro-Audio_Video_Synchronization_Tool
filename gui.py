import os
import sys
import json
import math
import wave
import threading
import queue
import re
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from tkinter import scrolledtext

# 同一ディレクトリの generator モジュールをインポート
import generator

class ReadingVideoApp(tk.Tk):
    def __init__(self):
        super().__init__()
        
        self.title("朗読動画作成ツール (GUI)")
        self.geometry("1100x900")
        
        # 変数定義
        self.work_dir = tk.StringVar()
        self.title_text = tk.StringVar(value="")
        self.credit_text = tk.StringVar(value="")
        self.default_interval = tk.DoubleVar(value=0.5)
        self.has_section = tk.BooleanVar(value=False)
        self.section_text = tk.StringVar(value="")
        self.title_hold = tk.DoubleVar(value=1.5)
        self.credit_hold = tk.DoubleVar(value=2.0)
        self.section_hold = tk.DoubleVar(value=3.0)
        self.title_wav_duration = 0.0
        self.credit_wav_duration = 0.0
        self.section_wav_duration = 0.0
        
        # フォールバック用BGM変数
        self.bgm_enabled = tk.BooleanVar(value=True)
        self.bgm_file = tk.StringVar(value="ambient_main.wav")
        self.bgm_volume = tk.DoubleVar(value=0.12)
        
        # 各種動的データ
        self.voice_list = []      # [3, 4, 5, ...] (音声ファイル番号のリスト)
        self.subtitles = {}       # {"003": "本文..."}
        self.bg_images = []       # ["003~010.png", ...]
        self.bgm_files = []       # BGMフォルダ内のファイルリスト ["bgm1.wav", ...]
        self.has_bgm_folder = False
        self.loaded_config = {}   # 保存されたプロジェクト設定データ
        
        # UI上のコンポーネント参照用
        self.interval_entries = {}  # {idx: Entry}
        self.bg_range_controls = [] # [{'enabled_var': BooleanVar, 'image_combo': Combobox, 'start_combo': Combobox, 'end_combo': Combobox, 'frame': Frame}]
        self.bgm_range_controls = [] # [{'file_name': str, 'enabled_var': BooleanVar, 'start_combo': Combobox, ...}]
        
        # ログキューとスレッド管理
        self.log_queue = queue.Queue()
        self.is_generating = False
        
        # スタイル設定（ダークテーマ風フラットデザイン）
        self.configure_styles()
        
        # レイアウト構築
        self.build_ui()
        
        # セクション入力欄の状態を初期設定
        self.update_section_entry_state()
        
        # ログ監視タイマー開始
        self.after(100, self.poll_log_queue)

    def configure_styles(self):
        self.configure(bg="#1e1e1e")
        
        style = ttk.Style()
        style.theme_use("clam")
        
        # 全体ダークスタイル
        style.configure(".", background="#1e1e1e", foreground="#ffffff", fieldbackground="#2d2d2d")
        
        # 各コンポーネントのスタイル
        style.configure("TFrame", background="#1e1e1e")
        style.configure("Labelframe", background="#1e1e1e", foreground="#a0a0a0", bordercolor="#404040")
        style.configure("Labelframe.Label", background="#1e1e1e", foreground="#a0a0a0")
        
        style.configure("TLabel", background="#1e1e1e", foreground="#ffffff")
        style.configure("Header.TLabel", font=("Yu Gothic", 12, "bold"))
        
        style.configure("TButton", background="#3c3f41", foreground="#ffffff", borderwidth=0, padding=6)
        style.map("TButton", background=[("active", "#4c5052")])
        
        style.configure("Action.TButton", background="#2a5a2a", foreground="#ffffff", font=("Yu Gothic", 11, "bold"))
        style.map("Action.TButton", background=[("active", "#3a7a3a")])
        
        style.configure("TEntry", fieldbackground="#2d2d2d", foreground="#ffffff", insertcolor="#ffffff")
        
        # スライダー(Scale)のスタイル
        style.configure("Horizontal.TScale",
                        background="#1e1e1e",      # 余白・ベース背景を背景と同化
                        troughcolor="#2d2d2d",     # 溝を明るいグレーに設定して視認性確保
                        bordercolor="#808080",     # つまみの外枠線
                        lightcolor="#a0a0a0",      # つまみの立体ハイライト
                        darkcolor="#404040",       # つまみのシャドウ
                        borderwidth=1,
                        sliderlength=14)
        style.map("Horizontal.TScale",
                  background=[("active", "#4c5052")])
        
        # Combobox の選択文字が見えにくい問題の修正
        style.configure("TCombobox", fieldbackground="#2d2d2d", foreground="#ffffff", selectbackground="#404040", selectforeground="#ffffff")
        style.map("TCombobox",
                  fieldbackground=[("readonly", "#2d2d2d"), ("active", "#3d3d3d")],
                  foreground=[("readonly", "#ffffff"), ("active", "#ffffff")],
                  selectbackground=[("readonly", "#404040")],
                  selectforeground=[("readonly", "#ffffff")])
                  
        # リストボックス（ドロップダウン）の色を強制
        self.option_add("*TCombobox*Listbox.background", "#2d2d2d")
        self.option_add("*TCombobox*Listbox.foreground", "#ffffff")
        self.option_add("*TCombobox*Listbox.selectBackground", "#404040")
        self.option_add("*TCombobox*Listbox.selectForeground", "#ffffff")

    def build_ui(self):
        # メインフレーム（左右＋下部の3カラム構成）
        main_container = ttk.Frame(self, padding=12)
        main_container.pack(fill=tk.BOTH, expand=True)
        
        # 上部：フォルダ選択と基本設定
        top_lf = ttk.LabelFrame(main_container, text=" 基本設定 ", padding=10)
        top_lf.pack(fill=tk.X, pady=(0, 10))
        
        # フォルダ選択行
        folder_frame = ttk.Frame(top_lf)
        folder_frame.pack(fill=tk.X, pady=4)
        ttk.Label(folder_frame, text="対象作品フォルダ:").pack(side=tk.LEFT, padx=(0, 10))
        ttk.Entry(folder_frame, textvariable=self.work_dir, width=80).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))
        ttk.Button(folder_frame, text="参照...", command=self.browse_folder).pack(side=tk.LEFT)
        
        # タイトル・作者設定行（1行目）
        line1_frame = ttk.Frame(top_lf)
        line1_frame.pack(fill=tk.X, pady=4)
        
        ttk.Label(line1_frame, text="タイトル表示:").pack(side=tk.LEFT)
        ttk.Entry(line1_frame, textvariable=self.title_text, width=15).pack(side=tk.LEFT, padx=(0, 10))
        
        ttk.Label(line1_frame, text="ホールド(秒):").pack(side=tk.LEFT)
        ttk.Entry(line1_frame, textvariable=self.title_hold, width=6).pack(side=tk.LEFT, padx=(0, 20))
        
        ttk.Label(line1_frame, text="作者クレジット:").pack(side=tk.LEFT)
        ttk.Entry(line1_frame, textvariable=self.credit_text, width=15).pack(side=tk.LEFT, padx=(0, 10))
        
        ttk.Label(line1_frame, text="ホールド(秒):").pack(side=tk.LEFT)
        ttk.Entry(line1_frame, textvariable=self.credit_hold, width=6).pack(side=tk.LEFT)

        # 間隔・セクション設定行（2行目）
        line2_frame = ttk.Frame(top_lf)
        line2_frame.pack(fill=tk.X, pady=4)
        
        ttk.Label(line2_frame, text="デフォルト音声間隔(秒):").pack(side=tk.LEFT)
        ttk.Entry(line2_frame, textvariable=self.default_interval, width=8).pack(side=tk.LEFT, padx=(0, 20))

        ttk.Checkbutton(line2_frame, text="セクションあり (003)", variable=self.has_section, command=self.on_section_toggle).pack(side=tk.LEFT)
        
        self.section_lbl = ttk.Label(line2_frame, text="セクション名:")
        self.section_lbl.pack(side=tk.LEFT, padx=(10, 0))
        self.section_ent = ttk.Entry(line2_frame, textvariable=self.section_text, width=15)
        self.section_ent.pack(side=tk.LEFT, padx=(0, 10))
        
        self.section_hold_lbl = ttk.Label(line2_frame, text="ホールド(秒):")
        self.section_hold_lbl.pack(side=tk.LEFT)
        self.section_hold_ent = ttk.Entry(line2_frame, textvariable=self.section_hold, width=6)
        self.section_hold_ent.pack(side=tk.LEFT)

        # 下部：実行ログと生成ボタン（確実に表示されるよう先にBOTTOMへ配置）
        bottom_frame = ttk.Frame(main_container)
        bottom_frame.pack(side=tk.BOTTOM, fill=tk.X)
        
        # ログ枠
        log_lf = ttk.LabelFrame(bottom_frame, text=" 実行ログ ", padding=5)
        log_lf.pack(fill=tk.X, pady=(0, 10))
        self.log_area = scrolledtext.ScrolledText(log_lf, height=8, bg="#2d2d2d", fg="#ffffff", font=("MS Gothic", 9), insertbackground="white")
        self.log_area.pack(fill=tk.X)
        
        # 生成ボタン
        self.gen_btn = ttk.Button(bottom_frame, text="🎬 動画生成を開始", style="Action.TButton", command=self.start_generation)
        self.gen_btn.pack(side=tk.RIGHT, ipadx=20, ipady=4)
        
        # 保存ボタン
        self.save_btn = ttk.Button(bottom_frame, text="💾 設定を保存", command=self.manual_save_settings)
        self.save_btn.pack(side=tk.RIGHT, ipadx=20, ipady=4, padx=(0, 10))

        # 中部：左右分割パネル（残りの全領域を占有）
        middle_paned = ttk.Frame(main_container)
        middle_paned.pack(side=tk.TOP, fill=tk.BOTH, expand=True, pady=(0, 10))
        
        # 左側：音声ファイル＆個別インターバル設定 (Scrollable)
        self.left_lf = ttk.LabelFrame(middle_paned, text=" 音声リストと個別インターバル設定 ", padding=8)
        self.left_lf.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 6))
        
        # スクロール用キャンバス
        self.canvas = tk.Canvas(self.left_lf, bg="#1e1e1e", highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(self.left_lf, orient="vertical", command=self.canvas.yview)
        self.scrollable_frame = ttk.Frame(self.canvas)
        
        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )
        self.canvas_window = self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        
        # 横幅を自動調整
        self.canvas.bind('<Configure>', lambda e: self.canvas.itemconfig(self.canvas_window, width=e.width))
        
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        
        # マウスホイールイベントのバインド（リストの上下スクロール）
        self.canvas.bind("<MouseWheel>", self.on_list_mousewheel)
        self.scrollable_frame.bind("<MouseWheel>", self.on_list_mousewheel)
        
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # 初期状態プレースホルダー
        self.voice_placeholder = ttk.Label(self.scrollable_frame, text="フォルダを選択すると、ここに音声ファイルが一覧表示されます。", foreground="#808080")
        self.voice_placeholder.pack(pady=40)
        
        # 右側：背景画像＆BGMの範囲指定
        right_lf = ttk.LabelFrame(middle_paned, text=" 画像・BGM 適用範囲設定 ", padding=8)
        right_lf.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(6, 0))
        
        # 背景画像の設定エリア (スクロール化)
        self.bg_lf = ttk.LabelFrame(right_lf, text=" 背景画像適用範囲 ")
        self.bg_lf.pack(fill=tk.BOTH, expand=True, pady=(0, 5))
        
        # 操作用上部ボタンエリア
        bg_ctrl_frame = ttk.Frame(self.bg_lf, padding=2)
        bg_ctrl_frame.pack(fill=tk.X, side=tk.TOP)
        ttk.Button(bg_ctrl_frame, text="➕ 範囲を追加", command=self.add_new_bg_range).pack(side=tk.LEFT, padx=5, pady=2)
        
        self.bg_canvas = tk.Canvas(self.bg_lf, bg="#1e1e1e", highlightthickness=0)
        self.bg_scrollbar = ttk.Scrollbar(self.bg_lf, orient="vertical", command=self.bg_canvas.yview)
        self.bg_scrollable_frame = ttk.Frame(self.bg_canvas)
        
        self.bg_scrollable_frame.bind(
            "<Configure>",
            lambda e: self.bg_canvas.configure(scrollregion=self.bg_canvas.bbox("all"))
        )
        self.bg_canvas_window = self.bg_canvas.create_window((0, 0), window=self.bg_scrollable_frame, anchor="nw")
        self.bg_canvas.bind('<Configure>', lambda e: self.bg_canvas.itemconfig(self.bg_canvas_window, width=e.width))
        self.bg_canvas.configure(yscrollcommand=self.bg_scrollbar.set)
        
        self.bg_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.bg_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.bg_placeholder = ttk.Label(self.bg_scrollable_frame, text="背景画像がここにリストアップされます。", foreground="#808080")
        self.bg_placeholder.pack(pady=40)
        
        # BGMの設定エリア (スクロール化)
        self.bgm_lf = ttk.LabelFrame(right_lf, text=" BGM/環境音設定 ")
        self.bgm_lf.pack(fill=tk.BOTH, expand=True, pady=(5, 0))
        
        self.bgm_canvas = tk.Canvas(self.bgm_lf, bg="#1e1e1e", highlightthickness=0)
        self.bgm_scrollbar = ttk.Scrollbar(self.bgm_lf, orient="vertical", command=self.bgm_canvas.yview)
        self.bgm_scrollable_frame = ttk.Frame(self.bgm_canvas)
        
        self.bgm_scrollable_frame.bind(
            "<Configure>",
            lambda e: self.bgm_canvas.configure(scrollregion=self.bgm_canvas.bbox("all"))
        )
        self.bgm_canvas_window = self.bgm_canvas.create_window((0, 0), window=self.bgm_scrollable_frame, anchor="nw")
        self.bgm_canvas.bind('<Configure>', lambda e: self.bgm_canvas.itemconfig(self.bgm_canvas_window, width=e.width))
        self.bgm_canvas.configure(yscrollcommand=self.bgm_scrollbar.set)
        
        self.bgm_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.bgm_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.bgm_placeholder = ttk.Label(self.bgm_scrollable_frame, text="BGMファイルがここにリストアップされます。", foreground="#808080")
        self.bgm_placeholder.pack(pady=40)
        


    def on_section_toggle(self):
        self.update_section_entry_state()
        path = self.work_dir.get().strip()
        if path and os.path.exists(path):
            voice_dir = os.path.join(path, "音声ファイル")
            if os.path.exists(voice_dir):
                self.voice_list = []
                start_idx = 4 if self.has_section.get() else 3
                for filename in os.listdir(voice_dir):
                    if filename.endswith(".wav"):
                        prefix = filename[:3]
                        if prefix.isdigit() and int(prefix) >= start_idx:
                            self.voice_list.append(int(prefix))
                self.voice_list.sort()
                
                # UIの更新
                self.update_voice_list_ui()
                self.update_bg_ranges_ui()
                self.update_bgm_ui()
                
                # 再帰的にホイールバインドを設定
                self.bind_mousewheel_recursive(self.scrollable_frame, self.on_list_mousewheel)
                self.bind_mousewheel_recursive(self.bg_scrollable_frame, self.on_bg_mousewheel)
                self.bind_mousewheel_recursive(self.bgm_scrollable_frame, self.on_bgm_mousewheel)

    def update_section_entry_state(self):
        if self.has_section.get():
            self.section_ent.configure(state=tk.NORMAL)
            self.section_hold_ent.configure(state=tk.NORMAL)
        else:
            self.section_ent.configure(state=tk.DISABLED)
            self.section_hold_ent.configure(state=tk.DISABLED)

    def browse_folder(self):
        initial_dir = r"D:\Games\Python\朗読動画"
        if not os.path.exists(initial_dir):
            initial_dir = os.getcwd()
        path = filedialog.askdirectory(initialdir=initial_dir)
        if path:
            self.work_dir.set(path)
            self.load_project_resources(path)

    def load_project_resources(self, path):
        # ディレクトリパス定義
        voice_dir = os.path.join(path, "音声ファイル")
        bg_dir = os.path.join(path, "背景画像")
        sub_json = os.path.join(path, "字幕.json")
        
        if not (os.path.exists(voice_dir) and os.path.exists(bg_dir) and os.path.exists(sub_json)):
            messagebox.showerror("エラー", "指定されたフォルダは正しい作品フォルダ構成ではありません。\n（音声ファイル/、背景画像/、字幕.json が必要です）")
            return
            
        # 基本設定の初期化（前回のフォルダの設定が残らないようにリセット）
        self.title_text.set("")
        self.credit_text.set("")
        self.default_interval.set(0.5)
        self.has_section.set(False)
        self.section_text.set("")
        self.title_hold.set(1.5)
        self.credit_hold.set(2.0)
        self.section_hold.set(3.0)
        self.title_wav_duration = 0.0
        self.credit_wav_duration = 0.0
        self.section_wav_duration = 0.0
            
        self.log_write(f"プロジェクト「{os.path.basename(path)}」を読み込みました。")
        
        # 先に設定ファイルの has_section の状態を読み込んでおく（音声ファイルのロード開始位置を決めるため）
        config_path = os.path.join(path, "project_config.json")
        if os.path.exists(config_path):
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    tmp_config = json.load(f)
                    if "has_section" in tmp_config:
                        self.has_section.set(tmp_config["has_section"])
            except Exception:
                pass
        
        # 1. 字幕のロード
        try:
            with open(sub_json, "r", encoding="utf-8") as f:
                self.subtitles = json.load(f)
        except Exception as e:
            messagebox.showerror("エラー", f"字幕.json の読み込みに失敗しました: {e}")
            return
            
        # 2. 音声ファイルのロード
        self.voice_list = []
        start_idx = 4 if self.has_section.get() else 3
        for filename in os.listdir(voice_dir):
            if filename.endswith(".wav"):
                prefix = filename[:3]
                if prefix.isdigit() and int(prefix) >= start_idx:
                    self.voice_list.append(int(prefix))
        self.voice_list.sort()
        
        # 3. 背景画像のロード
        self.bg_images = []
        for filename in os.listdir(bg_dir):
            if filename.lower().endswith(('.png', '.jpg', '.jpeg')):
                self.bg_images.append(filename)
        self.bg_images.sort()
        
        # 4. BGMファイルの検出
        bgm_dir = os.path.join(voice_dir, "BGM")
        self.bgm_files = []
        self.has_bgm_folder = False
        if os.path.exists(bgm_dir) and os.path.isdir(bgm_dir):
            self.has_bgm_folder = True
            for filename in os.listdir(bgm_dir):
                if filename.lower().endswith(('.wav', '.mp3', '.ogg', '.m4a')):
                    self.bgm_files.append(filename)
            self.bgm_files.sort()
            
        self.log_write(f"検出された本文音声: {len(self.voice_list)} 個, 背景画像: {len(self.bg_images)} 枚, 複数BGM: {len(self.bgm_files) if self.has_bgm_folder else '無'}")
        
        # 各種オープニング・セクション音声ファイルの秒数計測とデフォルト設定
        def get_wav_duration(prefix):
            for fname in os.listdir(voice_dir):
                if fname.endswith(".wav") and fname.startswith(prefix):
                    try:
                        p = os.path.join(voice_dir, fname)
                        with wave.open(p, "rb") as wf:
                            return wf.getnframes() / float(wf.getframerate())
                    except Exception:
                        pass
            return 0.0

        self.title_wav_duration = get_wav_duration("001")
        self.credit_wav_duration = get_wav_duration("002")
        self.section_wav_duration = get_wav_duration("003")

        self.title_hold.set(max(1.5, self.title_wav_duration))
        self.credit_hold.set(max(2.0, self.credit_wav_duration))
        self.section_hold.set(max(3.0, self.section_wav_duration))

        # 5. プロジェクト設定ファイルのロード
        self.loaded_config = {}
        config_path = os.path.join(path, "project_config.json")
        if os.path.exists(config_path):
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    self.loaded_config = json.load(f)
                self.log_write("保存された設定データ project_config.json を読み込みました。")
                
                # 基本設定の復元
                if "title_text" in self.loaded_config:
                    self.title_text.set(self.loaded_config["title_text"])
                if "credit_text" in self.loaded_config:
                    self.credit_text.set(self.loaded_config["credit_text"])
                if "default_interval" in self.loaded_config:
                    try:
                        self.default_interval.set(float(self.loaded_config["default_interval"]))
                    except (ValueError, tk.TclError):
                        pass
                if "has_section" in self.loaded_config:
                    self.has_section.set(self.loaded_config["has_section"])
                if "section_text" in self.loaded_config:
                    self.section_text.set(self.loaded_config["section_text"])
                if "title_hold" in self.loaded_config:
                    try:
                        self.title_hold.set(max(self.title_wav_duration, float(self.loaded_config["title_hold"])))
                    except (ValueError, tk.TclError):
                        pass
                if "credit_hold" in self.loaded_config:
                    try:
                        self.credit_hold.set(max(self.credit_wav_duration, float(self.loaded_config["credit_hold"])))
                    except (ValueError, tk.TclError):
                        pass
                if "section_hold" in self.loaded_config:
                    try:
                        self.section_hold.set(max(self.section_wav_duration, float(self.loaded_config["section_hold"])))
                    except (ValueError, tk.TclError):
                        pass
            except Exception as e:
                self.log_write(f"設定データの読み込みに失敗しました: {e}")
                
        # UIの更新
        self.update_section_entry_state()
        self.update_voice_list_ui()
        self.update_bg_ranges_ui()
        self.update_bgm_ui()
        
        # 再帰的にホイールバインドを設定（子ウィジェット上でもスクロールを効かせるため）
        self.bind_mousewheel_recursive(self.scrollable_frame, self.on_list_mousewheel)
        self.bind_mousewheel_recursive(self.bg_scrollable_frame, self.on_bg_mousewheel)
        self.bind_mousewheel_recursive(self.bgm_scrollable_frame, self.on_bgm_mousewheel)

    def update_voice_list_ui(self):
        # 古いコンポーネントをクリア
        for child in self.scrollable_frame.winfo_children():
            child.destroy()
            
        self.interval_entries = {}
        
        if not self.voice_list:
            return
            
        # ヘッダー
        header_f = ttk.Frame(self.scrollable_frame)
        header_f.pack(fill=tk.X, pady=2)
        ttk.Label(header_f, text="番号", font=("Yu Gothic", 9, "bold"), width=6).pack(side=tk.LEFT)
        ttk.Label(header_f, text="字幕（プレビュー）", font=("Yu Gothic", 9, "bold"), width=35).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Label(header_f, text="次までの無音間隔(秒)", font=("Yu Gothic", 9, "bold"), width=18).pack(side=tk.RIGHT)
        
        # 各行生成
        for idx in self.voice_list:
            row = ttk.Frame(self.scrollable_frame)
            row.pack(fill=tk.X, pady=2)
            row.bind("<MouseWheel>", self.on_list_mousewheel)
            
            # 間隔入力（後続のラベルで参照するため先に定義して pack は最後に行う）
            ent = ttk.Entry(row, width=8, justify=tk.RIGHT)
            loaded_val = ""
            if self.loaded_config and "intervals" in self.loaded_config:
                loaded_val = self.loaded_config["intervals"].get(str(idx), "")
            ent.insert(0, loaded_val)
            
            # 番号
            num_lbl = ttk.Label(row, text=f"[{idx:03d}]", width=6)
            num_lbl.pack(side=tk.LEFT)
            num_lbl.bind("<MouseWheel>", self.on_list_mousewheel)
            
            # 字幕プレビュー
            sub_text = self.subtitles.get(f"{idx:03d}", "")
            preview_text = sub_text[:25] + "..." if len(sub_text) > 25 else sub_text
            preview_lbl = ttk.Label(row, text=preview_text, width=35, anchor=tk.W, font=("Honoka Shin Mincho L", 10))
            preview_lbl.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)
            preview_lbl.bind("<MouseWheel>", self.on_list_mousewheel)
            
            # 間隔入力の配置とバインド
            ent.pack(side=tk.RIGHT, padx=(0, 20))
            ent.bind("<MouseWheel>", self.on_list_mousewheel)
            self.interval_entries[idx] = ent

    def parse_range_from_filename(self, filename):
        voice_opts = [f"{v:03d}" for v in self.voice_list]
        name, ext = os.path.splitext(filename)
        
        # "none" または "none(X)" の場合は無効（チェックOFF）とする
        if name.lower().startswith("none"):
            return True, False, (voice_opts[0] if voice_opts else ""), (voice_opts[-1] if voice_opts else "")
            
        # 波ダッシュやチルダ、ハイフンで区切られた2つの数字を探す
        match = re.search(r"(\d+)\s*[~〜-]\s*(\d+)", name)
        if match:
            start_val = f"{int(match.group(1)):03d}"
            end_val = f"{int(match.group(2)):03d}"
            if start_val in voice_opts and end_val in voice_opts:
                return True, True, start_val, end_val
                
        # 単一の数字を探す
        match_single = re.search(r"(\d+)", name)
        if match_single:
            val = f"{int(match_single.group(1)):03d}"
            if val in voice_opts:
                return True, True, val, val
                
        # 解析できない場合はデフォルトで最初〜最後に割り当て、パース成功フラグは False にする
        return False, True, (voice_opts[0] if voice_opts else ""), (voice_opts[-1] if voice_opts else "")

    def add_new_bg_range(self):
        if not self.bg_images or not self.voice_list:
            messagebox.showwarning("警告", "対象作品フォルダを読み込んでから追加してください。")
            return
        self.add_bg_range_row(enabled=True)

    def add_bg_range_row(self, enabled=True, image_name=None, start_val=None, end_val=None):
        row = ttk.Frame(self.bg_scrollable_frame, padding=4)
        row.pack(fill=tk.X)
        
        # 有効化チェックボックス
        enabled_var = tk.BooleanVar(value=enabled)
        chk = ttk.Checkbutton(row, variable=enabled_var, width=2)
        chk.pack(side=tk.LEFT)
        
        # 画像名選択 Combobox
        image_combo = ttk.Combobox(row, values=self.bg_images, width=20, state="readonly")
        image_combo.pack(side=tk.LEFT, padx=3)
        if image_name and image_name in self.bg_images:
            image_combo.set(image_name)
        elif self.bg_images:
            image_combo.set(self.bg_images[0])
            
        # 開始音声 Combobox
        voice_opts = [f"{v:03d}" for v in self.voice_list]
        start_combo = ttk.Combobox(row, values=voice_opts, width=8, state="readonly")
        start_combo.pack(side=tk.LEFT, padx=3)
        if start_val and start_val in voice_opts:
            start_combo.set(start_val)
        elif voice_opts:
            start_combo.set(voice_opts[0])
            
        # 終了音声 Combobox
        end_combo = ttk.Combobox(row, values=voice_opts, width=8, state="readonly")
        end_combo.pack(side=tk.LEFT, padx=3)
        if end_val and end_val in voice_opts:
            end_combo.set(end_val)
        elif voice_opts:
            end_combo.set(voice_opts[-1])
            
        # 削除ボタン
        del_btn = ttk.Button(row, text="❌", width=3)
        del_btn.pack(side=tk.LEFT, padx=5)
        
        control_item = {
            'enabled_var': enabled_var,
            'image_combo': image_combo,
            'start_combo': start_combo,
            'end_combo': end_combo,
            'frame': row
        }
        
        del_btn.configure(command=lambda: self.remove_bg_range_row(control_item))
        
        self.bg_range_controls.append(control_item)
        
        # マウスホイールイベントのバインド
        self.bind_mousewheel_recursive(row, self.on_bg_mousewheel)

    def remove_bg_range_row(self, control_item):
        control_item['frame'].destroy()
        if control_item in self.bg_range_controls:
            self.bg_range_controls.remove(control_item)

    def update_bg_ranges_ui(self):
        for child in self.bg_scrollable_frame.winfo_children():
            child.destroy()
            
        self.bg_range_controls = []
        
        if not self.bg_images or not self.voice_list:
            self.bg_placeholder = ttk.Label(self.bg_scrollable_frame, text="背景画像がここにリストアップされます。", foreground="#808080")
            self.bg_placeholder.pack(pady=40)
            return
            
        # 音声番号のドロップダウン選択肢 (文字列)
        voice_opts = [f"{v:03d}" for v in self.voice_list]
        
        # ヘッダー
        header_f = ttk.Frame(self.bg_scrollable_frame, padding=5)
        header_f.pack(fill=tk.X, pady=2)
        ttk.Label(header_f, text="画像ファイル名", font=("Yu Gothic", 9, "bold"), width=20).pack(side=tk.LEFT, padx=(25, 0)) # チェックボックス分ずらす
        ttk.Label(header_f, text="開始音声", font=("Yu Gothic", 9, "bold"), width=10).pack(side=tk.LEFT, padx=5)
        ttk.Label(header_f, text="終了音声", font=("Yu Gothic", 9, "bold"), width=10).pack(side=tk.LEFT, padx=5)
        
        # 保存データがあればそれから復元
        bg_ranges_to_show = []
        loaded_image_names = set()
        if self.loaded_config and "bg_ranges" in self.loaded_config:
            bg_ranges_data = self.loaded_config["bg_ranges"]
            if isinstance(bg_ranges_data, list) and len(bg_ranges_data) > 0:
                for bg_item in bg_ranges_data:
                    img_name = bg_item.get("image_name")
                    if img_name in self.bg_images:
                        # ファイル名から優先パースを試みる
                        success, enabled_parsed, s_parsed, e_parsed = self.parse_range_from_filename(img_name)
                        if success:
                            bg_item["start"] = s_parsed
                            bg_item["end"] = e_parsed
                            if "enabled" not in bg_item:
                                bg_item["enabled"] = enabled_parsed
                                
                        bg_ranges_to_show.append(bg_item)
                        loaded_image_names.add(img_name)
        
        if self.loaded_config and "bg_ranges" in self.loaded_config and len(bg_ranges_to_show) > 0:
            # 設定に存在しない新しい画像ファイルを読み込んで追加
            for img_name in self.bg_images:
                if img_name not in loaded_image_names:
                    parsed, enabled, start_val, end_val = self.parse_range_from_filename(img_name)
                    bg_ranges_to_show.append({
                        "image_name": img_name,
                        "start": start_val,
                        "end": end_val,
                        "enabled": enabled
                    })
        else:
            # 設定データがない、または設定が空の場合
            # すべての画像についてパースを試みる
            parsed_items = []
            any_success = False
            for img_name in self.bg_images:
                success, enabled, start_val, end_val = self.parse_range_from_filename(img_name)
                if success:
                    any_success = True
                parsed_items.append({
                    "image_name": img_name,
                    "start": start_val,
                    "end": end_val,
                    "enabled": enabled
                })
            
            if any_success:
                # 1つでもパースに成功した画像があれば、パース結果を採用
                bg_ranges_to_show.extend(parsed_items)
            else:
                # すべての画像でパース失敗した場合は均等分割のデフォルト範囲計算
                n_images = len(self.bg_images)
                n_voices = len(self.voice_list)
                chunk_size = math.ceil(n_voices / n_images) if n_images > 0 else 1
                
                for idx, img_name in enumerate(self.bg_images):
                    def_start_idx = min(idx * chunk_size, n_voices - 1)
                    def_end_idx = min((idx + 1) * chunk_size - 1, n_voices - 1)
                    if def_start_idx > def_end_idx:
                        def_start_idx = def_end_idx
                    start_val = voice_opts[def_start_idx]
                    end_val = voice_opts[def_end_idx]
                    bg_ranges_to_show.append({
                        "image_name": img_name,
                        "start": start_val,
                        "end": end_val,
                        "enabled": True
                    })
                
        # フォルダ内の画像名順、および開始音声番号順にソート
        def get_image_sort_key(item):
            name = item.get("image_name", "")
            try:
                img_idx = self.bg_images.index(name)
            except ValueError:
                img_idx = len(self.bg_images)
            
            s_raw = item.get("start", 0)
            try:
                start_num = int(s_raw)
            except ValueError:
                start_num = 999
            return (img_idx, start_num)
        
        sorted_bg_ranges = sorted(bg_ranges_to_show, key=get_image_sort_key)
        
        for bg_item in sorted_bg_ranges:
            img_name = bg_item.get("image_name")
            enabled = bg_item.get("enabled", True)
            
            s_raw = bg_item.get("start")
            e_raw = bg_item.get("end")
            if isinstance(s_raw, int) or (isinstance(s_raw, str) and s_raw.isdigit()):
                s_val = f"{int(s_raw):03d}"
            else:
                s_val = str(s_raw)
                
            if isinstance(e_raw, int) or (isinstance(e_raw, str) and e_raw.isdigit()):
                e_val = f"{int(e_raw):03d}"
            else:
                e_val = str(e_raw)
                
            if img_name in self.bg_images and s_val in voice_opts and e_val in voice_opts:
                self.add_bg_range_row(enabled=enabled, image_name=img_name, start_val=s_val, end_val=e_val)

    def update_bgm_ui(self):
        for child in self.bgm_scrollable_frame.winfo_children():
            child.destroy()
            
        self.bgm_range_controls = []
        
        if not self.voice_list:
            self.bgm_placeholder = ttk.Label(self.bgm_scrollable_frame, text="BGMファイルがここにリストアップされます。", foreground="#808080")
            self.bgm_placeholder.pack(pady=40)
            return
            
        voice_opts = [f"{v:03d}" for v in self.voice_list]
        bgm_voice_opts = ["タイトル(冒頭)"] + voice_opts + ["余韻(ラスト)"]
        
        if self.has_bgm_folder and self.bgm_files:
            self.bgm_lf.configure(text=" BGM適用範囲設定 (BGMフォルダ内) ")
            
            # ヘッダー
            header_f = ttk.Frame(self.bgm_scrollable_frame, padding=4)
            header_f.pack(fill=tk.X, pady=2)
            ttk.Label(header_f, text="BGMファイル名", font=("Yu Gothic", 9, "bold"), width=20).pack(side=tk.LEFT)
            ttk.Label(header_f, text="開始", font=("Yu Gothic", 9, "bold"), width=12).pack(side=tk.LEFT, padx=3)
            ttk.Label(header_f, text="終了", font=("Yu Gothic", 9, "bold"), width=12).pack(side=tk.LEFT, padx=3)
            ttk.Label(header_f, text="音量", font=("Yu Gothic", 9, "bold"), width=15).pack(side=tk.LEFT, padx=5)
            
            for bgm_name in self.bgm_files:
                row = ttk.Frame(self.bgm_scrollable_frame, padding=4)
                row.pack(fill=tk.X)
                
                # デフォルト値
                is_enabled = True
                start_val = "タイトル(冒頭)"
                end_val = bgm_voice_opts[-1]
                volume_val = 0.12
                
                # 保存データがあれば適用
                if self.loaded_config and "bgm_settings" in self.loaded_config:
                    for bgm_item in self.loaded_config["bgm_settings"]:
                        if bgm_item.get("file_name") == bgm_name and bgm_item.get("in_bgm_folder", True):
                            is_enabled = bgm_item.get("enabled", True)
                            
                            s_raw = bgm_item.get("start")
                            e_raw = bgm_item.get("end")
                            
                            if s_raw == "title":
                                s_val = "タイトル(冒頭)"
                            elif s_raw == "margin":
                                s_val = "余韻(ラスト)"
                            elif isinstance(s_raw, int) or (isinstance(s_raw, str) and s_raw.isdigit()):
                                s_val = f"{int(s_raw):03d}"
                            else:
                                s_val = s_raw
                                
                            if e_raw == "title":
                                e_val = "タイトル(冒頭)"
                            elif e_raw == "margin":
                                e_val = "余韻(ラスト)"
                            elif isinstance(e_raw, int) or (isinstance(e_raw, str) and e_raw.isdigit()):
                                e_val = f"{int(e_raw):03d}"
                            else:
                                e_val = e_raw
                                
                            if s_val in bgm_voice_opts:
                                start_val = s_val
                            if e_val in bgm_voice_opts:
                                end_val = e_val
                                
                            volume_val = float(bgm_item.get("volume", 0.12))
                            break

                # 有効化チェックボックス
                enabled_var = tk.BooleanVar(value=is_enabled)
                chk = ttk.Checkbutton(row, variable=enabled_var, width=2)
                chk.pack(side=tk.LEFT)
                
                lbl = ttk.Label(row, text=bgm_name, width=18, anchor=tk.W)
                lbl.pack(side=tk.LEFT)
                
                # 開始コンボ
                start_combo = ttk.Combobox(row, values=bgm_voice_opts, width=12, state="readonly")
                start_combo.pack(side=tk.LEFT, padx=3)
                start_combo.set(start_val)
                
                # 終了コンボ
                end_combo = ttk.Combobox(row, values=bgm_voice_opts, width=12, state="readonly")
                end_combo.pack(side=tk.LEFT, padx=3)
                end_combo.set(end_val)
                
                # 音量スライダー
                vol_var = tk.DoubleVar(value=volume_val)
                vol_scale = ttk.Scale(row, from_=0.0, to=0.5, variable=vol_var, orient=tk.HORIZONTAL, length=80)
                vol_scale.pack(side=tk.LEFT, padx=5)
                
                # 音量数値ラベル
                vol_label = ttk.Label(row, text=f"{volume_val:.2f}", width=5)
                vol_label.pack(side=tk.LEFT)
                
                # スライダー値更新コールバック
                def make_update_callback(lbl_comp):
                    return lambda val: lbl_comp.configure(text=f"{float(val):.2f}")
                vol_scale.configure(command=make_update_callback(vol_label))
                
                self.bgm_range_controls.append({
                    'file_name': bgm_name,
                    'enabled_var': enabled_var,
                    'start_combo': start_combo,
                    'end_combo': end_combo,
                    'volume_var': vol_var,
                    'in_bgm_folder': True
                })
        else:
            self.bgm_lf.configure(text=" BGM/環境音設定 (フォールバック) ")
            
            # ambient_main.wav が存在するか確認
            ambient_exists = False
            for p in [os.path.join(self.work_dir.get(), "ambient_main.wav"), os.path.join(self.work_dir.get(), "音声ファイル", "ambient_main.wav")]:
                if os.path.exists(p):
                    ambient_exists = True
                    break
                    
            status_text = "検出" if ambient_exists else "未検出"
            
            # デフォルト値
            bgm_enabled_val = True
            bgm_volume_val = 0.12
            
            # 保存データがあれば適用
            if self.loaded_config and "bgm_settings" in self.loaded_config:
                for bgm_item in self.loaded_config["bgm_settings"]:
                    if not bgm_item.get("in_bgm_folder", False):
                        bgm_enabled_val = bgm_item.get("enabled", True)
                        bgm_volume_val = float(bgm_item.get("volume", 0.12))
                        break
            
            self.bgm_enabled.set(bgm_enabled_val)
            self.bgm_volume.set(bgm_volume_val)
            
            grid = ttk.Frame(self.bgm_scrollable_frame, padding=8)
            grid.pack(fill=tk.X)
            
            # チェックボタン
            chk = ttk.Checkbutton(grid, text=f"BGMを重ねる (ファイル: {self.bgm_file.get()} - {status_text})", variable=self.bgm_enabled)
            chk.grid(row=0, column=0, columnspan=3, sticky=tk.W, pady=4)
            
            # 音量ラベル
            lbl = ttk.Label(grid, text="音量 (0.0-0.5):")
            lbl.grid(row=1, column=0, sticky=tk.W, pady=4)
            
            # スライダー
            vol_scale = ttk.Scale(grid, from_=0.0, to=0.5, variable=self.bgm_volume, orient=tk.HORIZONTAL, length=120)
            vol_scale.grid(row=1, column=1, sticky=tk.W, pady=4, padx=5)
            
            # 数値ラベル
            vol_label = ttk.Label(grid, text=f"{self.bgm_volume.get():.2f}", width=5)
            vol_label.grid(row=1, column=2, sticky=tk.W, pady=4)
            
            vol_scale.configure(command=lambda val: vol_label.configure(text=f"{float(val):.2f}"))
            
            self.bgm_range_controls.append({
                'file_name': self.bgm_file.get(),
                'enabled_var': self.bgm_enabled,
                'start_combo': None,
                'end_combo': None,
                'volume_var': self.bgm_volume,
                'in_bgm_folder': False
            })

    def log_write(self, msg):
        self.log_queue.put(str(msg) + "\n")

    def poll_log_queue(self):
        while not self.log_queue.empty():
            try:
                msg = self.log_queue.get_nowait()
                self.log_area.insert(tk.END, msg)
                self.log_area.see(tk.END)
            except queue.Empty:
                break
        self.after(100, self.poll_log_queue)

    def save_project_settings(self):
        work_dir = self.work_dir.get().strip()
        if not work_dir or not os.path.exists(work_dir):
            return
            
        # インターバルの収集
        intervals = {}
        for idx, ent in self.interval_entries.items():
            val_str = ent.get().strip()
            if val_str:
                intervals[str(idx)] = val_str
                
        # 背景画像の実ファイルリネームと収集
        import shutil
        bg_dir = os.path.join(work_dir, "背景画像")
        
        # 1. 各コントロールの設定を収集
        settings_to_rename = []
        for item in self.bg_range_controls:
            is_enabled = item['enabled_var'].get()
            old_name = item['image_combo'].get()
            start_val = item['start_combo'].get()
            end_val = item['end_combo'].get()
            settings_to_rename.append({
                'is_enabled': is_enabled,
                'old_name': old_name,
                'start_val': start_val,
                'end_val': end_val,
                'control_item': item
            })

        # 2. 実ファイルをテンポラリ退避して衝突を防止
        temp_files = {} # {old_name: temp_path}
        existing_images = []
        if os.path.exists(bg_dir):
            existing_images = [f for f in os.listdir(bg_dir) if f.lower().endswith(('.png', '.jpg', '.jpeg'))]
            
        for idx, filename in enumerate(existing_images):
            old_path = os.path.join(bg_dir, filename)
            ext = os.path.splitext(filename)[1]
            temp_name = f"__temp_{idx}{ext}"
            temp_path = os.path.join(bg_dir, temp_name)
            try:
                os.rename(old_path, temp_path)
                temp_files[filename] = temp_path
            except Exception as e:
                self.log_write(f"背景画像ファイルの一時退避エラー ({filename} -> {temp_name}): {e}")

        # 3. none(X) の名前重複を避けるための番号管理
        none_counter = 1
        def get_next_none_name(ext):
            nonlocal none_counter
            while True:
                candidate = f"none({none_counter}){ext}"
                if not os.path.exists(os.path.join(bg_dir, candidate)):
                    none_counter += 1
                    return candidate
                none_counter += 1

        # 4. 新しい名前でファイルを配置 (移動/コピー)
        bg_ranges = []
        created_files = set() # 既に作成された新しいファイル名
        
        for item_data in settings_to_rename:
            old_name = item_data['old_name']
            ext = os.path.splitext(old_name)[1] if old_name else ".png"
            if not ext:
                ext = ".png"
                
            # 新ファイル名の決定
            if item_data['is_enabled']:
                s = item_data['start_val']
                e = item_data['end_val']
                if s == e:
                    new_name = f"{s}{ext}"
                else:
                    new_name = f"{s}~{e}{ext}"
            else:
                new_name = get_next_none_name(ext)
                
            # テンポラリファイルから配置
            temp_path = temp_files.get(old_name)
            if temp_path and os.path.exists(temp_path):
                new_path = os.path.join(bg_dir, new_name)
                try:
                    if new_name in created_files:
                        # すでに同じファイルが作成されている場合はコピーする (複製)
                        shutil.copy(temp_path, new_path)
                    else:
                        shutil.move(temp_path, new_path)
                        created_files.add(new_name)
                except Exception as e:
                    self.log_write(f"ファイルリネームエラー ({new_name}): {e}")
            
            # 設定情報とGUI Comboboxの表示名を更新
            item_data['control_item']['image_combo'].set(new_name)
            bg_ranges.append({
                'image_name': new_name,
                'start': item_data['start_val'],
                'end': item_data['end_val'],
                'enabled': item_data['is_enabled']
            })

        # 5. 不要になったテンポラリファイルをクリーンアップ
        for t_path in temp_files.values():
            if os.path.exists(t_path):
                try:
                    os.remove(t_path)
                except Exception:
                    pass

        # 6. self.bg_images (フォルダ内の画像名リスト) を再スキャンして更新
        self.bg_images = []
        if os.path.exists(bg_dir):
            for filename in os.listdir(bg_dir):
                if filename.lower().endswith(('.png', '.jpg', '.jpeg')):
                    self.bg_images.append(filename)
            self.bg_images.sort()

        # すべてのコントロールの選択肢を新しいリストで更新
        for item in self.bg_range_controls:
            item['image_combo'].configure(values=self.bg_images)

        # 7. 保存リストをソート
        def get_image_sort_key(item):
            name = item.get("image_name", "")
            try:
                img_idx = self.bg_images.index(name)
            except ValueError:
                img_idx = len(self.bg_images)
            
            s_raw = item.get("start", 0)
            try:
                start_num = int(s_raw)
            except ValueError:
                start_num = 999
            return (img_idx, start_num)
            
        bg_ranges.sort(key=get_image_sort_key)
            
        # BGM設定の収集
        bgm_settings = []
        for item in self.bgm_range_controls:
            is_enabled = item['enabled_var'].get()
            if item['start_combo'] is not None:
                start_val = item['start_combo'].get()
                end_val = item['end_combo'].get()
                
                if start_val == "タイトル(冒頭)":
                    s_data = "title"
                elif start_val == "余韻(ラスト)":
                    s_data = "margin"
                else:
                    s_data = int(start_val) if start_val.isdigit() else start_val
                    
                if end_val == "タイトル(冒頭)":
                    e_data = "title"
                elif end_val == "余韻(ラスト)":
                    e_data = "margin"
                else:
                    e_data = int(end_val) if end_val.isdigit() else end_val
                    
                bgm_settings.append({
                    'file_name': item['file_name'],
                    'enabled': is_enabled,
                    'start': s_data,
                    'end': e_data,
                    'volume': item['volume_var'].get(),
                    'in_bgm_folder': True
                })
            else:
                bgm_settings.append({
                    'file_name': item['file_name'],
                    'enabled': is_enabled,
                    'start': "title",
                    'end': "margin",
                    'volume': item['volume_var'].get(),
                    'in_bgm_folder': False
                })
                
        config_data = {
            'title_text': self.title_text.get(),
            'credit_text': self.credit_text.get(),
            'default_interval': self.default_interval.get(),
            'has_section': self.has_section.get(),
            'section_text': self.section_text.get(),
            'title_hold': self.title_hold.get(),
            'credit_hold': self.credit_hold.get(),
            'section_hold': self.section_hold.get(),
            'intervals': intervals,
            'bg_ranges': bg_ranges,
            'bgm_settings': bgm_settings
        }
        
        config_path = os.path.join(work_dir, "project_config.json")
        try:
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(config_data, f, ensure_ascii=False, indent=2)
            self.log_write("設定データを project_config.json に保存しました。")
        except Exception as e:
            self.log_write(f"設定データの保存に失敗しました: {e}")

    def manual_save_settings(self):
        work_dir = self.work_dir.get().strip()
        if not work_dir:
            messagebox.showwarning("警告", "対象作品フォルダを選択してください。")
            return
        if not os.path.exists(work_dir):
            messagebox.showerror("エラー", "対象作品フォルダが存在しません。")
            return
            
        self.save_project_settings()
        messagebox.showinfo("完了", "設定データを保存しました。")

    def on_list_mousewheel(self, event):
        try:
            # コンテンツの高さがキャンバスの表示領域より小さい場合はスクロールさせない
            canvas_height = self.canvas.winfo_height()
            bbox = self.canvas.bbox("all")
            content_height = bbox[3] if bbox else 0
            if content_height <= canvas_height:
                return
                
            # Windows環境向けのスクロール処理 (event.deltaは通常120の倍数)
            scroll_units = -1 * int(event.delta / 120)
            self.canvas.yview_scroll(scroll_units, "units")
        except Exception:
            pass

    def on_bg_mousewheel(self, event):
        try:
            # コンテンツの高さがキャンバスの表示領域より小さい場合はスクロールさせない
            canvas_height = self.bg_canvas.winfo_height()
            bbox = self.bg_canvas.bbox("all")
            content_height = bbox[3] if bbox else 0
            if content_height <= canvas_height:
                return
                
            # Windows環境向けのスクロール処理
            scroll_units = -1 * int(event.delta / 120)
            self.bg_canvas.yview_scroll(scroll_units, "units")
        except Exception:
            pass

    def on_bgm_mousewheel(self, event):
        try:
            # コンテンツの高さがキャンバスの表示領域より小さい場合はスクロールさせない
            canvas_height = self.bgm_canvas.winfo_height()
            bbox = self.bgm_canvas.bbox("all")
            content_height = bbox[3] if bbox else 0
            if content_height <= canvas_height:
                return
                
            # Windows環境向けのスクロール処理
            scroll_units = -1 * int(event.delta / 120)
            self.bgm_canvas.yview_scroll(scroll_units, "units")
        except Exception:
            pass

    def bind_mousewheel_recursive(self, widget, handler):
        widget.bind("<MouseWheel>", handler)
        for child in widget.winfo_children():
            self.bind_mousewheel_recursive(child, handler)

    def start_generation(self):
        if self.is_generating:
            return
            
        work_dir = self.work_dir.get().strip()
        if not work_dir:
            messagebox.showwarning("警告", "対象作品フォルダを選択してください。")
            return
            
        # 生成開始前に自動的に設定を保存
        self.save_project_settings()
            
        # 入力値の検証と収集
        try:
            default_int = self.default_interval.get()
        except tk.TclError:
            messagebox.showerror("エラー", "デフォルト音声間隔には数値を入力してください。")
            return

        try:
            t_hold = self.title_hold.get()
            if t_hold < self.title_wav_duration:
                messagebox.showerror("エラー", f"タイトルホールド時間にはタイトル音声秒数（{self.title_wav_duration:.2f}秒）以上の値を設定してください。")
                return
        except tk.TclError:
            messagebox.showerror("エラー", "タイトルホールド時間には数値を入力してください。")
            return

        try:
            c_hold = self.credit_hold.get()
            if c_hold < self.credit_wav_duration:
                messagebox.showerror("エラー", f"クレジットホールド時間にはクレジット音声秒数（{self.credit_wav_duration:.2f}秒）以上の値を設定してください。")
                return
        except tk.TclError:
            messagebox.showerror("エラー", "クレジットホールド時間には数値を入力してください。")
            return

        s_hold = 0.0
        if self.has_section.get():
            try:
                s_hold = self.section_hold.get()
                if s_hold < self.section_wav_duration:
                    messagebox.showerror("エラー", f"セクションホールド時間にはセクション音声秒数（{self.section_wav_duration:.2f}秒）以上の値を設定してください。")
                    return
            except tk.TclError:
                messagebox.showerror("エラー", "セクションホールド時間には数値を入力してください。")
                return
            
        intervals = {}
        for idx, ent in self.interval_entries.items():
            val_str = ent.get().strip()
            if val_str:
                try:
                    intervals[idx] = float(val_str)
                except ValueError:
                    messagebox.showerror("エラー", f"音声 [{idx:03d}] の間隔設定値が不正です（数値を入力してください）。")
                    return
                    
        # 背景画像範囲の収集とバリデーション
        bg_ranges = []
        for item in self.bg_range_controls:
            if item['enabled_var'].get():
                img_name = item['image_combo'].get()
                if not img_name:
                    messagebox.showerror("エラー", "画像が選択されていない範囲設定があります。")
                    return
                
                try:
                    start_val = int(item['start_combo'].get())
                    end_val = int(item['end_combo'].get())
                except ValueError:
                    messagebox.showerror("エラー", f"画像「{img_name}」の範囲設定（開始/終了）が不正です。")
                    return
                
                if start_val > end_val:
                    messagebox.showerror("エラー", f"画像「{img_name}」の範囲設定が不正です。\n（開始音声番号が終了音声番号より大きくなっています）")
                    return
                    
                bg_ranges.append({
                    'image_name': img_name,
                    'start': start_val,
                    'end': end_val
                })
                
        if not bg_ranges:
            messagebox.showerror("エラー", "少なくとも1つの背景画像を有効にしてください。")
            return
            
        # BGM設定の収集
        bgm_settings = []
        for item in self.bgm_range_controls:
            if item['enabled_var'].get():
                if item['start_combo'] is not None:
                    # 複数指定
                    start_combo_val = item['start_combo'].get()
                    end_combo_val = item['end_combo'].get()
                    
                    if start_combo_val == "タイトル(冒頭)":
                        start_val = "title"
                    elif start_combo_val == "余韻(ラスト)":
                        start_val = "margin"
                    else:
                        start_val = int(start_combo_val)
                        
                    if end_combo_val == "タイトル(冒頭)":
                        end_val = "title"
                    elif end_combo_val == "余韻(ラスト)":
                        end_val = "margin"
                    else:
                        end_val = int(end_combo_val)
                    
                    # 比較用の数値化（"title" を 0, "margin" を 999 とみなす）
                    start_num = 0 if start_val == "title" else (999 if start_val == "margin" else start_val)
                    end_num = 0 if end_val == "title" else (999 if end_val == "margin" else end_val)
                    
                    if start_num > end_num:
                        messagebox.showerror("エラー", f"BGM「{item['file_name']}」の範囲設定が不正です。")
                        return
                    bgm_settings.append({
                        'file_name': item['file_name'],
                        'start': start_val,
                        'end': end_val,
                        'volume': item['volume_var'].get(),
                        'in_bgm_folder': True
                    })
                else:
                    # 単一フォールバック（全体）
                    bgm_settings.append({
                        'file_name': item['file_name'],
                        'start': "title",
                        'end': "margin",
                        'volume': item['volume_var'].get(),
                        'in_bgm_folder': False
                    })
        
        # ボタンのロック
        self.is_generating = True
        self.gen_btn.configure(state=tk.DISABLED, text="⏳ 動画生成中...")
        
        # ログクリア
        self.log_area.delete("1.0", tk.END)
        
        # 非同期スレッドで生成を開始
        t = threading.Thread(
            target=self.generation_thread_target,
            args=(work_dir, self.title_text.get(), self.credit_text.get(), default_int, intervals, bg_ranges, bgm_settings, self.has_section.get(), self.section_text.get(), t_hold, c_hold, s_hold)
        )
        t.daemon = True
        t.start()

    def generation_thread_target(self, work_dir, title_txt, credit_txt, def_int, intervals, bg_ranges, bgm_settings, has_section, section_txt, title_h, credit_h, section_h):
        try:
            generator.run_generation(
                work_dir=work_dir,
                title_text=title_txt,
                credit_text=credit_txt,
                default_interval=def_int,
                intervals_dict=intervals,
                bg_ranges=bg_ranges,
                bgm_settings=bgm_settings,
                has_section=has_section,
                section_text=section_txt,
                title_hold=title_h,
                credit_hold=credit_h,
                section_hold=section_h,
                log_callback=self.log_write
            )
            self.log_write("\n動画生成が正常に完了しました！")
            self.after(0, lambda: messagebox.showinfo("完了", "動画の生成が完了しました！"))
        except Exception as e:
            err_msg = str(e)
            self.log_write(f"\nエラーが発生しました: {err_msg}")
            self.after(0, lambda msg=err_msg: messagebox.showerror("エラー", f"動画の生成中にエラーが発生しました:\n{msg}"))
        finally:
            self.after(0, self.on_generation_finished)

    def on_generation_finished(self):
        self.is_generating = False
        self.gen_btn.configure(state=tk.NORMAL, text="🎬 動画生成を開始")

if __name__ == "__main__":
    app = ReadingVideoApp()
    app.mainloop()
