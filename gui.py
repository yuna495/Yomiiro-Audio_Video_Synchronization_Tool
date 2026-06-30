import os
import sys
import re
from PIL import Image

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QGridLayout, QSplitter, QListWidget, QListWidgetItem, QLabel,
    QPushButton, QTextEdit, QLineEdit, QSlider, QCheckBox, QGroupBox,
    QSpinBox, QDoubleSpinBox, QComboBox, QTabWidget, QTableWidget,
    QTableWidgetItem, QHeaderView, QFileDialog, QMessageBox, QDialog,
    QDialogButtonBox, QSizePolicy
)
from PySide6.QtCore import Qt, QThread, Signal, QObject
from PySide6.QtGui import QImage, QPixmap, QFont, QIcon, QPainter

import core
import renderer

def pil_to_qpixmap(pil_img):
    rgb_img = pil_img.convert("RGB")
    data = rgb_img.tobytes("raw", "RGB")
    qimg = QImage(data, rgb_img.size[0], rgb_img.size[1], QImage.Format.Format_RGB888)
    return QPixmap.fromImage(qimg)

class PreviewWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.pixmap = None
        self.text = "クリップが選択されていません"
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumSize(160, 90)
        
    def set_pixmap(self, pixmap):
        self.pixmap = pixmap
        self.text = ""
        self.update()

    def set_text(self, text):
        self.pixmap = None
        self.text = text
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), Qt.GlobalColor.black)
        
        if self.pixmap and not self.pixmap.isNull():
            w = self.width()
            h = self.height()
            
            if w / 16.0 > h / 9.0:
                new_h = h
                new_w = int(new_h * 16 / 9)
            else:
                new_w = w
                new_h = int(new_w * 9 / 16)
                
            x = (w - new_w) // 2
            y = (h - new_h) // 2
            
            scaled_pixmap = self.pixmap.scaled(
                new_w, new_h,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            painter.drawPixmap(x, y, scaled_pixmap)
        elif self.text:
            painter.setPen(Qt.GlobalColor.gray)
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self.text)
            
        painter.setPen(Qt.GlobalColor.darkGray)
        painter.drawRect(0, 0, self.width() - 1, self.height() - 1)

class ClipRowWidget(QWidget):
    def __init__(self, index, name, duration, enabled=True, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(5, 2, 5, 2)
        layout.setSpacing(10)
        
        self.lbl_idx = QLabel(f"[{index}]")
        self.lbl_idx.setFixedWidth(45)
        self.lbl_idx.setStyleSheet("font-weight: bold; color: #88ff88;")
        layout.addWidget(self.lbl_idx)
        
        self.lbl_name = QLabel(name)
        if not enabled:
            self.lbl_name.setStyleSheet("text-decoration: line-through; color: #666666;")
        else:
            self.lbl_name.setStyleSheet("color: #ffffff;")
        layout.addWidget(self.lbl_name, stretch=1)
        
        self.lbl_dur = QLabel(f"{duration:.2f}s")
        self.lbl_dur.setFixedWidth(60)
        self.lbl_dur.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.lbl_dur.setStyleSheet("color: #a0a0a0;")
        layout.addWidget(self.lbl_dur)

class BVolumeWidget(QWidget):
    valueChanged = Signal(float)
    def __init__(self, initial_vol, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(6)
        
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0, 100)
        self.slider.setValue(int(initial_vol * 100))
        self.slider.setFixedWidth(70)
        layout.addWidget(self.slider)
        
        self.label = QLabel(f"{initial_vol:.2f}")
        self.label.setFixedWidth(30)
        layout.addWidget(self.label)
        
        self.slider.valueChanged.connect(self.on_value_changed)
        
    def on_value_changed(self, val):
        vol = val / 100.0
        self.label.setText(f"{vol:.2f}")
        self.valueChanged.emit(vol)

class DragDropListWidget(QListWidget):
    order_changed = Signal()
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDragDropMode(QListWidget.DragDropMode.InternalMove)
        self.setSelectionMode(QListWidget.SelectionMode.SingleSelection)

    def dropEvent(self, event):
        super().dropEvent(event)
        self.order_changed.emit()

class RenderWorker(QObject):
    log_signal = Signal(str)
    finished_signal = Signal(bool, str)

    def __init__(self, project):
        super().__init__()
        self.project = project

    def run(self):
        try:
            output = renderer.render_movie(self.project, log_callback=self.log_signal.emit)
            self.finished_signal.emit(True, output)
        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            self.finished_signal.emit(False, f"{e}\n{tb}")

class ReadingVideoApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("朗読動画作成アプリ")
        self.resize(1280, 950)
        
        self.project = None
        self.selected_clip_id = None
        self.is_generating = False
        
        self.thread = None
        self.worker = None
        
        self.apply_dark_theme()
        self.build_ui()
        
        temp_dir = os.path.abspath(os.path.join(os.getcwd(), "untitled_project"))
        self.project = core.Project(temp_dir)
        self.update_project_ui()

    def apply_dark_theme(self):
        self.setStyleSheet("""
            QWidget {
                background-color: #1e1e1e;
                color: #ffffff;
                font-family: 'Yu Gothic', sans-serif;
                font-size: 12px;
            }
            QMainWindow {
                background-color: #1a1a1a;
            }
            QMenuBar {
                background-color: #2d2d2d;
                color: #ffffff;
            }
            QMenuBar::item:selected {
                background-color: #3d3d3d;
            }
            QToolBar {
                background-color: #2d2d2d;
                border: none;
                spacing: 10px;
                padding: 5px;
            }
            QPushButton {
                background-color: #3c3f41;
                border: none;
                border-radius: 4px;
                padding: 6px 12px;
                color: #ffffff;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #4c5052;
            }
            QPushButton:pressed {
                background-color: #2b2b2b;
            }
            QPushButton#action_btn {
                background-color: #2a5a2a;
            }
            QPushButton#action_btn:hover {
                background-color: #3a7a3a;
            }
            QLineEdit, QTextEdit, QSpinBox, QDoubleSpinBox {
                background-color: #2d2d2d;
                border: 1px solid #404040;
                border-radius: 4px;
                padding: 4px;
                color: #ffffff;
                selection-background-color: #404040;
            }
            QLineEdit:focus, QTextEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus {
                border: 1px solid #5a5a5a;
            }
            QComboBox {
                background-color: #2d2d2d;
                border: 1px solid #404040;
                border-radius: 4px;
                padding: 4px;
                color: #ffffff;
            }
            QComboBox::drop-down {
                border: none;
            }
            QComboBox QAbstractItemView {
                background-color: #2d2d2d;
                selection-background-color: #404040;
                color: #ffffff;
            }
            QGroupBox {
                border: 1px solid #404040;
                border-radius: 6px;
                margin-top: 12px;
                padding: 10px;
                font-weight: bold;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                left: 10px;
                color: #a0a0a0;
            }
            QListWidget, QTableWidget {
                background-color: #2d2d2d;
                border: 1px solid #404040;
                border-radius: 4px;
                gridline-color: #404040;
            }
            QHeaderView::section {
                background-color: #252525;
                color: #ffffff;
                padding: 5px;
                border: 1px solid #404040;
            }
            QTableWidget QComboBox {
                background-color: #1e1e1e;
            }
            QTabWidget::pane {
                border: 1px solid #404040;
                background-color: #1e1e1e;
            }
            QTabBar::tab {
                background-color: #2d2d2d;
                color: #a0a0a0;
                padding: 8px 16px;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                margin-right: 2px;
            }
            QTabBar::tab:selected {
                background-color: #1e1e1e;
                color: #ffffff;
                border: 1px solid #404040;
                border-bottom: none;
            }
            QScrollBar:vertical {
                background-color: #1e1e1e;
                width: 12px;
                margin: 0px;
            }
            QScrollBar::handle:vertical {
                background-color: #3d3d3d;
                min-height: 20px;
                border-radius: 6px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                background: none;
            }
            QSlider::groove:horizontal {
                border: 1px solid #404040;
                height: 6px;
                background: #2d2d2d;
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                background: #a0a0a0;
                width: 14px;
                margin: -4px 0;
                border-radius: 7px;
            }
        """)

    def build_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)
        
        # 1. 最上部: 操作バー
        top_bar = QHBoxLayout()
        main_layout.addLayout(top_bar)
        
        btn_open = QPushButton("📁 プロジェクトを開く")
        btn_open.clicked.connect(self.open_project)
        top_bar.addWidget(btn_open)
        
        btn_new = QPushButton("➕ 新規プロジェクト")
        btn_new.clicked.connect(self.new_project)
        top_bar.addWidget(btn_new)
        
        btn_save = QPushButton("💾 プロジェクト保存")
        btn_save.clicked.connect(self.save_project)
        top_bar.addWidget(btn_save)
        
        btn_clean = QPushButton("🧹 未使用ファイルを整理")
        btn_clean.clicked.connect(self.clean_unused_files)
        top_bar.addWidget(btn_clean)
        
        self.project_label = QLabel("プロジェクト: 未設定")
        self.project_label.setStyleSheet("font-style: italic; color: #a0a0a0; margin-left: 10px;")
        top_bar.addWidget(self.project_label)
        top_bar.addStretch()
        
        # 2. 中部領域: QSplitterによる分割
        splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(splitter, stretch=1)
        
        # 左ペイン: クリップリスト
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        
        group_clips = QGroupBox(" 音声クリップ一覧 ")
        group_clips_layout = QVBoxLayout(group_clips)
        
        clip_btn_bar = QHBoxLayout()
        group_clips_layout.addLayout(clip_btn_bar)
        
        btn_add_clip = QPushButton("➕ 音声追加")
        btn_add_clip.clicked.connect(self.add_audio_clips)
        clip_btn_bar.addWidget(btn_add_clip)
        
        btn_del_clip = QPushButton("❌ 削除")
        btn_del_clip.clicked.connect(self.remove_selected_clip)
        clip_btn_bar.addWidget(btn_del_clip)
        clip_btn_bar.addStretch()
        
        self.clip_list = DragDropListWidget()
        self.clip_list.order_changed.connect(self.on_clips_reordered)
        self.clip_list.itemSelectionChanged.connect(self.on_clip_selected)
        self.clip_list.itemDoubleClicked.connect(self.on_clip_double_clicked)
        group_clips_layout.addWidget(self.clip_list)
        
        left_layout.addWidget(group_clips)
        splitter.addWidget(left_widget)
        
        # 中央ペイン: プレビュー
        center_widget = QWidget()
        center_layout = QVBoxLayout(center_widget)
        center_layout.setContentsMargins(0, 0, 0, 0)
        
        group_preview = QGroupBox(" プレビュー ")
        group_preview_layout = QVBoxLayout(group_preview)
        
        self.preview_widget = PreviewWidget()
        group_preview_layout.addWidget(self.preview_widget)
        
        center_layout.addWidget(group_preview)
        splitter.addWidget(center_widget)
        
        # 右ペイン: クリップ詳細 & 全体スタイル
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        
        group_detail = QGroupBox(" クリップ詳細・字幕編集 ")
        group_detail_layout = QVBoxLayout(group_detail)
        
        group_detail_layout.addWidget(QLabel("字幕テキスト:"))
        self.subtitle_text = QTextEdit()
        self.subtitle_text.textChanged.connect(self.on_subtitle_changed)
        group_detail_layout.addWidget(self.subtitle_text)
        
        # 個別無音時間・音量スライダー・有効/無効
        grid_opts = QGridLayout()
        group_detail_layout.addLayout(grid_opts)
        
        grid_opts.addWidget(QLabel("個別待ち時間:"), 0, 0)
        self.clip_gap_spin = QDoubleSpinBox()
        self.clip_gap_spin.setRange(0.0, 60.0)
        self.clip_gap_spin.setSingleStep(0.5)
        self.clip_gap_spin.setSuffix("s")
        self.clip_gap_spin.valueChanged.connect(self.on_clip_gap_changed)
        grid_opts.addWidget(self.clip_gap_spin, 0, 1)
        
        grid_opts.addWidget(QLabel("個別音量:"), 1, 0)
        vol_lay = QHBoxLayout()
        self.clip_vol_scale = QSlider(Qt.Orientation.Horizontal)
        self.clip_vol_scale.setRange(0, 200)
        self.clip_vol_scale.setValue(100)
        self.clip_vol_scale.valueChanged.connect(self.on_clip_vol_changed)
        vol_lay.addWidget(self.clip_vol_scale)
        self.lbl_clip_vol_val = QLabel("1.00")
        self.lbl_clip_vol_val.setFixedWidth(30)
        vol_lay.addWidget(self.lbl_clip_vol_val)
        grid_opts.addLayout(vol_lay, 1, 1)
        
        self.clip_enabled_chk = QCheckBox("有効")
        self.clip_enabled_chk.setChecked(True)
        self.clip_enabled_chk.stateChanged.connect(self.on_clip_enabled_changed)
        grid_opts.addWidget(self.clip_enabled_chk, 0, 2)
        
        right_layout.addWidget(group_detail, stretch=2)
        
        # 基本待ち時間設定（追加）
        group_gap_config = QGroupBox(" 基本待ち時間設定 ")
        group_gap_layout = QHBoxLayout(group_gap_config)
        group_gap_layout.addWidget(QLabel("デフォルト無音秒数:"))
        self.default_gap_spin = QDoubleSpinBox()
        self.default_gap_spin.setRange(0.0, 60.0)
        self.default_gap_spin.setSingleStep(0.5)
        self.default_gap_spin.setSuffix("s")
        self.default_gap_spin.valueChanged.connect(self.on_default_gap_changed)
        group_gap_layout.addWidget(self.default_gap_spin)
        group_gap_layout.addStretch()
        right_layout.addWidget(group_gap_config)
        
        # 字幕スタイル設定
        group_style = QGroupBox(" 字幕スタイル（全体） ")
        group_style_grid = QGridLayout(group_style)
        
        group_style_grid.addWidget(QLabel("フォントサイズ:"), 0, 0)
        self.font_size_spin = QSpinBox()
        self.font_size_spin.setRange(20, 150)
        self.font_size_spin.setValue(58)
        self.font_size_spin.valueChanged.connect(self.on_style_changed)
        group_style_grid.addWidget(self.font_size_spin, 0, 1)
        
        group_style_grid.addWidget(QLabel("表示位置:"), 0, 2)
        self.pos_combo = QComboBox()
        self.pos_combo.addItems(["top", "center", "bottom"])
        self.pos_combo.setCurrentText("bottom")
        self.pos_combo.currentTextChanged.connect(self.on_style_changed)
        group_style_grid.addWidget(self.pos_combo, 0, 3)
        
        group_style_grid.addWidget(QLabel("文字色:"), 1, 0)
        self.text_color_ent = QLineEdit("#EEF1F8")
        self.text_color_ent.textChanged.connect(self.on_style_changed)
        group_style_grid.addWidget(self.text_color_ent, 1, 1)
        
        group_style_grid.addWidget(QLabel("背景ボックス色:"), 1, 2)
        self.box_color_ent = QLineEdit("#000000")
        self.box_color_ent.textChanged.connect(self.on_style_changed)
        group_style_grid.addWidget(self.box_color_ent, 1, 3)
        
        group_style_grid.addWidget(QLabel("不透明度:"), 2, 0)
        self.box_opacity_spin = QDoubleSpinBox()
        self.box_opacity_spin.setRange(0.0, 1.0)
        self.box_opacity_spin.setSingleStep(0.1)
        self.box_opacity_spin.setValue(0.5)
        self.box_opacity_spin.valueChanged.connect(self.on_style_changed)
        group_style_grid.addWidget(self.box_opacity_spin, 2, 1)
        
        group_style_grid.addWidget(QLabel("下マージン:"), 2, 2)
        self.margin_spin = QSpinBox()
        self.margin_spin.setRange(10, 300)
        self.margin_spin.setValue(95)
        self.margin_spin.valueChanged.connect(self.on_style_changed)
        group_style_grid.addWidget(self.margin_spin, 2, 3)
        
        right_layout.addWidget(group_style, stretch=1)
        splitter.addWidget(right_widget)
        
        splitter.setSizes([350, 480, 450])
        
        # 3. 下部: 背景画像とBGMのタイムライン設定タブ
        bottom_tabs = QTabWidget()
        bottom_tabs.setMaximumHeight(320)
        main_layout.addWidget(bottom_tabs)
        
        # 背景画像タブ
        bg_widget = QWidget()
        bg_layout = QVBoxLayout(bg_widget)
        bg_layout.setContentsMargins(5, 5, 5, 5)
        
        bg_btn_bar = QHBoxLayout()
        bg_layout.addLayout(bg_btn_bar)
        btn_add_bg = QPushButton("➕ 画像追加")
        btn_add_bg.clicked.connect(self.add_background)
        bg_btn_bar.addWidget(btn_add_bg)
        btn_del_bg = QPushButton("❌ 削除")
        btn_del_bg.clicked.connect(self.remove_selected_bg)
        bg_btn_bar.addWidget(btn_del_bg)
        bg_btn_bar.addStretch()
        
        self.bg_table = QTableWidget(0, 5)
        self.bg_table.setHorizontalHeaderLabels(["ID", "ファイル名", "開始クリップ", "終了クリップ", "有効"])
        self.bg_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.bg_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.bg_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        # 列幅を少し狭くすっきりさせる
        self.bg_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.bg_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        bg_layout.addWidget(self.bg_table)
        
        bottom_tabs.addTab(bg_widget, "背景画像")
        
        # BGMタブ
        bgm_widget = QWidget()
        bgm_layout = QVBoxLayout(bgm_widget)
        bgm_layout.setContentsMargins(5, 5, 5, 5)
        
        bgm_btn_bar = QHBoxLayout()
        bgm_layout.addLayout(bgm_btn_bar)
        btn_add_bgm = QPushButton("➕ BGM追加")
        btn_add_bgm.clicked.connect(self.add_bgm)
        bgm_btn_bar.addWidget(btn_add_bgm)
        btn_del_bgm = QPushButton("❌ 削除")
        btn_del_bgm.clicked.connect(self.remove_selected_bgm)
        bgm_btn_bar.addWidget(btn_del_bgm)
        bgm_btn_bar.addStretch()
        
        self.bgm_table = QTableWidget(0, 9)
        self.bgm_table.setHorizontalHeaderLabels(["ID", "ファイル名", "開始クリップ", "終了クリップ", "音量", "フェードイン", "フェードアウト", "ループ", "有効"])
        self.bgm_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.bgm_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.bgm_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.bgm_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.bgm_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.bgm_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        self.bgm_table.horizontalHeader().setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)
        self.bgm_table.horizontalHeader().setSectionResizeMode(7, QHeaderView.ResizeMode.ResizeToContents)
        self.bgm_table.horizontalHeader().setSectionResizeMode(8, QHeaderView.ResizeMode.ResizeToContents)
        bgm_layout.addWidget(self.bgm_table)
        
        bottom_tabs.addTab(bgm_widget, "BGM / 環境音")
        
        # 4. 最下部: ログエリアと書き出しコントロール
        footer_layout = QHBoxLayout()
        main_layout.addLayout(footer_layout)
        
        log_group = QGroupBox(" 実行ログ ")
        log_group_layout = QVBoxLayout(log_group)
        self.log_area = QTextEdit()
        self.log_area.setReadOnly(True)
        self.log_area.setMaximumHeight(120)
        log_group_layout.addWidget(self.log_area)
        footer_layout.addWidget(log_group, stretch=2)
        
        export_widget = QWidget()
        export_widget.setMaximumHeight(135)
        export_layout = QVBoxLayout(export_widget)
        export_layout.setContentsMargins(0, 10, 0, 0)
        
        out_path_layout = QHBoxLayout()
        export_layout.addLayout(out_path_layout)
        out_path_layout.addWidget(QLabel("出力ファイル名:"))
        self.output_ent = QLineEdit()
        self.output_ent.textChanged.connect(self.on_output_changed)
        out_path_layout.addWidget(self.output_ent)
        btn_browse_out = QPushButton("参照...")
        btn_browse_out.clicked.connect(self.browse_output_path)
        out_path_layout.addWidget(btn_browse_out)
        
        self.gen_btn = QPushButton("🎬 動画生成を開始")
        self.gen_btn.setObjectName("action_btn")
        self.gen_btn.setFixedHeight(50)
        self.gen_btn.clicked.connect(self.start_generation)
        export_layout.addWidget(self.gen_btn)
        
        footer_layout.addWidget(export_widget, stretch=1)

    # ------------------
    # 音声クリップ操作・並び替えリナンバリング
    # ------------------
    def renumber_clips(self):
        if not self.project:
            return
            
        old_to_new = {}
        for idx, clip in enumerate(self.project.audio_clips):
            new_id = f"clip_{idx+1:04d}"
            old_to_new[clip.id] = new_id
            clip.id = new_id
            
        clip_ids = [c.id for c in self.project.audio_clips]
        
        for bg in self.project.backgrounds:
            bg.start_clip_id = old_to_new.get(bg.start_clip_id, bg.start_clip_id)
            bg.end_clip_id = old_to_new.get(bg.end_clip_id, bg.end_clip_id)
            if bg.start_clip_id not in clip_ids and clip_ids:
                bg.start_clip_id = clip_ids[0]
            if bg.end_clip_id not in clip_ids and clip_ids:
                bg.end_clip_id = clip_ids[-1]
                
        for bgm in self.project.bgm_tracks:
            bgm.start_clip_id = old_to_new.get(bgm.start_clip_id, bgm.start_clip_id)
            bgm.end_clip_id = old_to_new.get(bgm.end_clip_id, bgm.end_clip_id)
            if bgm.start_clip_id not in clip_ids and clip_ids:
                bgm.start_clip_id = clip_ids[0]
            if bgm.end_clip_id not in clip_ids and clip_ids:
                bgm.end_clip_id = clip_ids[-1]
                
        self.project.save()

    def refresh_clip_list(self):
        self.clip_list.blockSignals(True)
        self.clip_list.clear()
        
        if self.project:
            timeline = renderer.VideoTimeline(self.project)
            for idx, clip in enumerate(self.project.audio_clips):
                item = QListWidgetItem()
                item.setData(Qt.ItemDataRole.UserRole, clip.id)
                
                # 長さの特定
                clip_entry = next((t for t in timeline.clips_timeline if t["clip"].id == clip.id), None)
                dur = clip_entry["duration"] if clip_entry else 0.0
                
                # カスタムウィジェットの生成
                row_widget = ClipRowWidget(idx + 1, clip.display_name, dur, clip.enabled)
                item.setSizeHint(row_widget.sizeHint())
                
                self.clip_list.addItem(item)
                self.clip_list.setItemWidget(item, row_widget)
                
        self.clip_list.blockSignals(False)

    def on_clips_reordered(self):
        if not self.project:
            return
            
        new_clips = []
        for i in range(self.clip_list.count()):
            item = self.clip_list.item(i)
            clip_id = item.data(Qt.ItemDataRole.UserRole)
            clip = next((c for c in self.project.audio_clips if c.id == clip_id), None)
            if clip:
                new_clips.append(clip)
                
        self.project.audio_clips = new_clips
        self.renumber_clips()
        
        self.refresh_clip_list()
        self.refresh_bg_table()
        self.refresh_bgm_table()
        self.update_preview()
        
        if self.selected_clip_id:
            for i in range(self.clip_list.count()):
                if self.clip_list.item(i).data(Qt.ItemDataRole.UserRole) == self.selected_clip_id:
                    self.clip_list.setCurrentRow(i)
                    break

    def on_clip_selected(self):
        items = self.clip_list.selectedItems()
        if not items:
            self.selected_clip_id = None
            self.update_preview()
            return
            
        clip_id = items[0].data(Qt.ItemDataRole.UserRole)
        self.selected_clip_id = clip_id
        
        clip = next((c for c in self.project.audio_clips if c.id == clip_id), None)
        if clip:
            self.subtitle_text.blockSignals(True)
            self.subtitle_text.setText(clip.subtitle)
            self.subtitle_text.blockSignals(False)
            
            self.clip_vol_scale.blockSignals(True)
            self.clip_vol_scale.setValue(int(clip.volume * 100))
            self.lbl_clip_vol_val.setText(f"{clip.volume:.2f}")
            self.clip_vol_scale.blockSignals(False)
            
            self.clip_gap_spin.blockSignals(True)
            self.clip_gap_spin.setValue(clip.gap_after)
            self.clip_gap_spin.blockSignals(False)
            
            self.clip_enabled_chk.blockSignals(True)
            self.clip_enabled_chk.setChecked(clip.enabled)
            self.clip_enabled_chk.blockSignals(False)
            
        self.update_preview()

    def on_clip_double_clicked(self, item):
        # 表形式に統合したため、ダブルクリックイベントでは何もしない
        pass

    def on_subtitle_changed(self):
        if not self.project or not self.selected_clip_id:
            return
        clip = next((c for c in self.project.audio_clips if c.id == self.selected_clip_id), None)
        if clip:
            clip.subtitle = self.subtitle_text.toPlainText().strip()
            self.update_preview()

    def on_clip_vol_changed(self, val):
        if not self.project or not self.selected_clip_id:
            return
        clip = next((c for c in self.project.audio_clips if c.id == self.selected_clip_id), None)
        if clip:
            vol = val / 100.0
            clip.volume = vol
            self.lbl_clip_vol_val.setText(f"{vol:.2f}")
            self.refresh_clip_list()

    def on_clip_gap_changed(self, val):
        if not self.project or not self.selected_clip_id:
            return
        clip = next((c for c in self.project.audio_clips if c.id == self.selected_clip_id), None)
        if clip:
            clip.gap_after = val
            self.refresh_clip_list()
            self.project.save()

    def on_clip_enabled_changed(self, state):
        if not self.project or not self.selected_clip_id:
            return
        clip = next((c for c in self.project.audio_clips if c.id == self.selected_clip_id), None)
        if clip:
            clip.enabled = (state == Qt.CheckState.Checked.value)
            self.refresh_clip_list()
            self.refresh_bg_table()
            self.refresh_bgm_table()
            self.update_preview()

    def on_default_gap_changed(self, val):
        if self.project:
            self.project.default_interval = val
            self.project.save()

    def on_style_changed(self):
        if not self.project:
            return
            
        style = self.project.subtitle_style
        style.font_size = self.font_size_spin.value()
        style.position = self.pos_combo.currentText()
        style.text_color = self.text_color_ent.text()
        style.box_color = self.box_color_ent.text()
        style.box_opacity = self.box_opacity_spin.value()
        style.margin_bottom = self.margin_spin.value()
        
        self.update_preview()

    def on_output_changed(self, text):
        if self.project:
            self.project.output_path = text.strip()

    # ------------------
    # 背景・BGM のテーブル内直接編集
    # ------------------
    def refresh_bg_table(self):
        self.bg_table.blockSignals(True)
        self.bg_table.setRowCount(0)
        
        if not self.project:
            self.bg_table.blockSignals(False)
            return
            
        # 番号選択用のリスト [1, 2, 3...]
        nums = [str(i + 1) for i in range(len(self.project.audio_clips))]
        
        for idx, bg in enumerate(self.project.backgrounds):
            row = self.bg_table.rowCount()
            self.bg_table.insertRow(row)
            
            # 1. 番号 (ID)
            num_item = QTableWidgetItem(str(idx + 1))
            num_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            num_item.setFlags(num_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.bg_table.setItem(row, 0, num_item)
            
            # 2. ファイル名
            file_item = QTableWidgetItem(os.path.basename(bg.file_path))
            file_item.setFlags(file_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.bg_table.setItem(row, 1, file_item)
            
            # 3. 開始クリップ (QComboBox)
            combo_start = QComboBox()
            combo_start.addItems(nums)
            # クリップIDを番号文字列に変換して設定
            start_num = self.clip_id_to_num_str(bg.start_clip_id)
            combo_start.setCurrentText(start_num)
            combo_start.currentTextChanged.connect(
                lambda val, bg_set=bg: self.on_bg_start_changed(bg_set, val)
            )
            self.bg_table.setCellWidget(row, 2, combo_start)
            
            # 4. 終了クリップ (QComboBox)
            combo_end = QComboBox()
            combo_end.addItems(nums)
            end_num = self.clip_id_to_num_str(bg.end_clip_id)
            combo_end.setCurrentText(end_num)
            combo_end.currentTextChanged.connect(
                lambda val, bg_set=bg: self.on_bg_end_changed(bg_set, val)
            )
            self.bg_table.setCellWidget(row, 3, combo_end)
            
            # 5. 有効 (QCheckBox)
            chk = QCheckBox()
            chk.setChecked(bg.enabled)
            # 中央揃えにするため、コンテナWidgetに入れる
            chk_widget = QWidget()
            chk_lay = QHBoxLayout(chk_widget)
            chk_lay.addWidget(chk)
            chk_lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
            chk_lay.setContentsMargins(0, 0, 0, 0)
            
            chk.stateChanged.connect(
                lambda state, bg_set=bg: self.on_bg_enabled_changed(bg_set, state)
            )
            self.bg_table.setCellWidget(row, 4, chk_widget)
            
        self.bg_table.blockSignals(False)

    def clip_id_to_num_str(self, clip_id):
        m = re.search(r'\d+', clip_id)
        if m:
            return str(int(m.group(0)))
        return "1"

    def num_str_to_clip_id(self, num_str):
        try:
            val = int(num_str)
            return f"clip_{val:04d}"
        except ValueError:
            return "clip_0001"

    def on_bg_start_changed(self, bg, val):
        bg.start_clip_id = self.num_str_to_clip_id(val)
        self.update_preview()
        self.project.save()

    def on_bg_end_changed(self, bg, val):
        bg.end_clip_id = self.num_str_to_clip_id(val)
        self.update_preview()
        self.project.save()

    def on_bg_enabled_changed(self, bg, state):
        bg.enabled = (state == Qt.CheckState.Checked.value)
        self.update_preview()
        self.project.save()

    def refresh_bgm_table(self):
        self.bgm_table.blockSignals(True)
        self.bgm_table.setRowCount(0)
        
        if not self.project:
            self.bgm_table.blockSignals(False)
            return
            
        nums = [str(i + 1) for i in range(len(self.project.audio_clips))]
        
        for idx, bgm in enumerate(self.project.bgm_tracks):
            row = self.bgm_table.rowCount()
            self.bgm_table.insertRow(row)
            
            # 1. 番号 (ID)
            num_item = QTableWidgetItem(str(idx + 1))
            num_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            num_item.setFlags(num_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.bgm_table.setItem(row, 0, num_item)
            
            # 2. ファイル名
            file_item = QTableWidgetItem(os.path.basename(bgm.file_path))
            file_item.setFlags(file_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.bgm_table.setItem(row, 1, file_item)
            
            # 3. 開始クリップ
            combo_start = QComboBox()
            combo_start.addItems(nums)
            combo_start.setCurrentText(self.clip_id_to_num_str(bgm.start_clip_id))
            combo_start.currentTextChanged.connect(
                lambda val, bgm_set=bgm: self.on_bgm_start_changed(bgm_set, val)
            )
            self.bgm_table.setCellWidget(row, 2, combo_start)
            
            # 4. 終了クリップ
            combo_end = QComboBox()
            combo_end.addItems(nums)
            combo_end.setCurrentText(self.clip_id_to_num_str(bgm.end_clip_id))
            combo_end.currentTextChanged.connect(
                lambda val, bgm_set=bgm: self.on_bgm_end_changed(bgm_set, val)
            )
            self.bgm_table.setCellWidget(row, 3, combo_end)
            
            # 5. 音量 (BVolumeWidget)
            vol_widget = BVolumeWidget(bgm.volume)
            vol_widget.valueChanged.connect(
                lambda val, bgm_set=bgm: self.on_bgm_volume_changed(bgm_set, val)
            )
            self.bgm_table.setCellWidget(row, 4, vol_widget)
            
            # 6. フェードイン (QDoubleSpinBox + s)
            spin_in = QDoubleSpinBox()
            spin_in.setRange(0.0, 10.0)
            spin_in.setSingleStep(0.5)
            spin_in.setSuffix("s")
            spin_in.setValue(bgm.fade_in)
            spin_in.valueChanged.connect(
                lambda val, bgm_set=bgm: self.on_bgm_fade_in_changed(bgm_set, val)
            )
            self.bgm_table.setCellWidget(row, 5, spin_in)
            
            # 7. フェードアウト (QDoubleSpinBox + s)
            spin_out = QDoubleSpinBox()
            spin_out.setRange(0.0, 10.0)
            spin_out.setSingleStep(0.5)
            spin_out.setSuffix("s")
            spin_out.setValue(bgm.fade_out)
            spin_out.valueChanged.connect(
                lambda val, bgm_set=bgm: self.on_bgm_fade_out_changed(bgm_set, val)
            )
            self.bgm_table.setCellWidget(row, 6, spin_out)
            
            # 8. ループ
            chk_loop = QCheckBox()
            chk_loop.setChecked(bgm.loop)
            chk_loop_widget = QWidget()
            chk_loop_lay = QHBoxLayout(chk_loop_widget)
            chk_loop_lay.addWidget(chk_loop)
            chk_loop_lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
            chk_loop_lay.setContentsMargins(0, 0, 0, 0)
            chk_loop.stateChanged.connect(
                lambda state, bgm_set=bgm: self.on_bgm_loop_changed(bgm_set, state)
            )
            self.bgm_table.setCellWidget(row, 7, chk_loop_widget)
            
            # 9. 有効
            chk_enabled = QCheckBox()
            chk_enabled.setChecked(bgm.enabled)
            chk_enabled_widget = QWidget()
            chk_enabled_lay = QHBoxLayout(chk_enabled_widget)
            chk_enabled_lay.addWidget(chk_enabled)
            chk_enabled_lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
            chk_enabled_lay.setContentsMargins(0, 0, 0, 0)
            chk_enabled.stateChanged.connect(
                lambda state, bgm_set=bgm: self.on_bgm_enabled_changed(bgm_set, state)
            )
            self.bgm_table.setCellWidget(row, 8, chk_enabled_widget)
            
        self.bgm_table.blockSignals(False)

    def on_bgm_start_changed(self, bgm, val):
        bgm.start_clip_id = self.num_str_to_clip_id(val)
        self.project.save()

    def on_bgm_end_changed(self, bgm, val):
        bgm.end_clip_id = self.num_str_to_clip_id(val)
        self.project.save()

    def on_bgm_volume_changed(self, bgm, val):
        bgm.volume = val
        self.project.save()

    def on_bgm_fade_in_changed(self, bgm, val):
        bgm.fade_in = val
        self.project.save()

    def on_bgm_fade_out_changed(self, bgm, val):
        bgm.fade_out = val
        self.project.save()

    def on_bgm_loop_changed(self, bgm, state):
        bgm.loop = (state == Qt.CheckState.Checked.value)
        self.project.save()

    def on_bgm_enabled_changed(self, bgm, state):
        bgm.enabled = (state == Qt.CheckState.Checked.value)
        self.project.save()

    # ------------------
    # アセットの追加・削除 (テーブル再描画)
    # ------------------
    def add_background(self):
        if not self.project:
            return
        file, _ = QFileDialog.getOpenFileName(
            self, "背景画像を追加", "",
            "Image Files (*.png *.jpg *.jpeg *.webp)"
        )
        if file:
            self.project.add_background_image(file)
            self.refresh_bg_table()
            self.update_preview()
            self.project.save()

    def remove_selected_bg(self):
        sel = self.bg_table.selectedItems()
        if not sel or not self.project:
            return
        row = sel[0].row()
        # 番号に基づいて元の backgrounds リストから削除
        if row < len(self.project.backgrounds):
            self.project.backgrounds.pop(row)
            self.refresh_bg_table()
            self.update_preview()
            self.project.save()

    def add_bgm(self):
        if not self.project:
            return
        file, _ = QFileDialog.getOpenFileName(
            self, "BGMアセットを追加", "",
            "Audio Files (*.wav *.mp3 *.m4a *.aac *.ogg *.flac)"
        )
        if file:
            self.project.add_bgm_track(file)
            self.refresh_bgm_table()
            self.project.save()

    def remove_selected_bgm(self):
        sel = self.bgm_table.selectedItems()
        if not sel or not self.project:
            return
        row = sel[0].row()
        if row < len(self.project.bgm_tracks):
            self.project.bgm_tracks.pop(row)
            self.refresh_bgm_table()
            self.project.save()

    def add_audio_clips(self):
        if not self.project:
            return
        files, _ = QFileDialog.getOpenFileNames(
            self, "音声アセットを追加", "",
            "Audio Files (*.wav *.mp3 *.m4a *.aac *.ogg *.flac)"
        )
        if files:
            for f in files:
                self.project.add_audio_clip(f, self.log_write)
            self.renumber_clips()
            self.refresh_clip_list()
            self.refresh_bg_table()
            self.refresh_bgm_table()
            self.update_preview()
            self.project.save()

    def remove_selected_clip(self):
        if not self.selected_clip_id or not self.project:
            return
        self.project.audio_clips = [c for c in self.project.audio_clips if c.id != self.selected_clip_id]
        self.selected_clip_id = None
        self.renumber_clips()
        self.refresh_clip_list()
        self.refresh_bg_table()
        self.refresh_bgm_table()
        self.update_preview()
        self.project.save()

    # ------------------
    # プロジェクトロード・UI同期
    # ------------------
    def update_project_ui(self):
        if not self.project:
            self.project_label.setText("プロジェクト: 未設定")
            return
            
        self.project_label.setText(f"フォルダ: {os.path.basename(self.project.project_dir)}")
        self.output_ent.setText(self.project.output_path)
        
        # 字幕スタイル
        style = self.project.subtitle_style
        self.font_size_spin.setValue(style.font_size)
        self.pos_combo.setCurrentText(style.position)
        self.text_color_ent.setText(style.text_color)
        self.box_color_ent.setText(style.box_color)
        self.box_opacity_spin.setValue(style.box_opacity)
        self.margin_spin.setValue(style.margin_bottom)
        
        # 基本待ち時間
        self.default_gap_spin.blockSignals(True)
        # core.Projectにdefault_intervalフィールドが無い場合を考慮
        val = getattr(self.project, "default_interval", 0.5)
        self.default_gap_spin.setValue(val)
        self.default_gap_spin.blockSignals(False)
        
        self.refresh_clip_list()
        self.refresh_bg_table()
        self.refresh_bgm_table()
        self.update_preview()

    def update_comboboxes(self):
        # 各行のセルウィジェットComboBoxを更新するためにテーブルをリフレッシュする
        self.refresh_bg_table()
        self.refresh_bgm_table()

    def update_preview(self):
        if not self.project or not self.selected_clip_id:
            self.preview_widget.set_pixmap(QPixmap())
            self.preview_widget.set_text("クリップが選択されていません")
            return
            
        try:
            preview_img = renderer.generate_preview_image(self.project, self.selected_clip_id)
            pix = pil_to_qpixmap(preview_img)
            self.preview_widget.set_pixmap(pix)
        except Exception as e:
            self.preview_widget.set_text(f"プレビューエラー:\n{e}")

    # ------------------
    # ログ出力・動画生成スレッド
    # ------------------
    def log_write(self, msg):
        self.log_area.append(str(msg))

    def start_generation(self):
        if not self.project:
            return
        if self.is_generating:
            return
            
        enabled_clips = [c for c in self.project.audio_clips if c.enabled]
        if not enabled_clips:
            QMessageBox.critical(self, "エラー", "有効な音声クリップがありません。")
            return
            
        if not self.project.backgrounds:
            QMessageBox.critical(self, "エラー", "背景画像が登録されていません。")
            return
            
        self.is_generating = True
        self.gen_btn.setEnabled(False)
        self.gen_btn.setText("⏳ 動画生成中...")
        self.log_area.clear()
        
        # default_intervalがProjectモデルにセットされていることを確認
        self.project.default_interval = self.default_gap_spin.value()
        self.project.save()
        
        self.thread = QThread()
        self.worker = RenderWorker(self.project)
        self.worker.moveToThread(self.thread)
        
        self.thread.started.connect(self.worker.run)
        self.worker.log_signal.connect(self.log_write)
        self.worker.finished_signal.connect(self.on_generation_finished)
        
        self.thread.start()

    def on_generation_finished(self, success, result_msg):
        self.thread.quit()
        self.thread.wait()
        
        self.is_generating = False
        self.gen_btn.setEnabled(True)
        self.gen_btn.setText("🎬 動画生成を開始")
        
        if success:
            QMessageBox.information(self, "完了", f"動画生成が完了しました！\n出力先: {result_msg}")
        else:
            QMessageBox.critical(self, "エラー", f"動画生成に失敗しました:\n{result_msg}")

    def closeEvent(self, event):
        if self.thread and self.thread.isRunning():
            self.thread.quit()
            self.thread.wait()
        event.accept()

    def new_project(self):
        path = QFileDialog.getExistingDirectory(self, "新規プロジェクトの保存先フォルダを選択")
        if path:
            self.project = core.Project(path)
            self.project.save()
            self.selected_clip_id = None
            self.update_project_ui()
            self.log_write(f"新規プロジェクトを作成しました: {path}")

    def open_project(self):
        path = QFileDialog.getExistingDirectory(self, "プロジェクトフォルダを選択")
        if path:
            if not os.path.exists(os.path.join(path, "project.json")):
                reply = QMessageBox.question(
                    self, "確認", "指定フォルダに project.json がありません。新規作成しますか？",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                )
                if reply == QMessageBox.StandardButton.No:
                    return
            self.project = core.Project.load(path)
            self.selected_clip_id = None
            self.update_project_ui()
            self.log_write(f"プロジェクトをロードしました: {path}")

    def save_project(self):
        if self.project:
            self.on_style_changed()
            self.project.output_path = self.output_ent.text().strip()
            self.project.default_interval = self.default_gap_spin.value()
            self.project.save()
            self.log_write("プロジェクト設定を保存しました。")
            QMessageBox.information(self, "保存完了", "プロジェクトを保存しました。")

    def clean_unused_files(self):
        if self.project:
            self.project.clean_unused_files()
            self.log_write("未使用ファイルをクリーンアップしました。")
            QMessageBox.information(self, "完了", "未使用ファイルを削除しました。")

    def browse_output_path(self):
        if not self.project:
            return
        file, _ = QFileDialog.getSaveFileName(
            self, "動画出力先の指定",
            os.path.join(self.project.project_dir, self.project.output_path),
            "MP4 Video (*.mp4)"
        )
        if file:
            try:
                rel = os.path.relpath(file, self.project.project_dir)
                if not rel.startswith(".."):
                    file = rel
            except ValueError:
                pass
            self.output_ent.setText(file)
            self.project.output_path = file

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = ReadingVideoApp()
    window.show()
    sys.exit(app.exec())
