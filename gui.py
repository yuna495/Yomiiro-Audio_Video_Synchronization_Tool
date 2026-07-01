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
    QDialogButtonBox, QSizePolicy, QProgressBar
)
from PySide6.QtCore import Qt, QThread, Signal, QObject, QTimer, QUrl
from PySide6.QtGui import QImage, QPixmap, QFont, QIcon, QPainter, QShortcut, QKeySequence
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput

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
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setStyleSheet("background: transparent;")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(5, 2, 5, 2)
        layout.setSpacing(10)

        self.lbl_idx = QLabel(f"[{index}]")
        self.lbl_idx.setFixedWidth(45)
        self.lbl_idx.setStyleSheet("font-weight: bold; color: #88ff88; background: transparent;")
        layout.addWidget(self.lbl_idx)

        self.lbl_name = QLabel(name)
        if not enabled:
            self.lbl_name.setStyleSheet("text-decoration: line-through; color: #666666; background: transparent;")
        else:
            self.lbl_name.setStyleSheet("color: #ffffff; background: transparent;")
        layout.addWidget(self.lbl_name, stretch=1)

        self.lbl_dur = QLabel(f"{duration:.2f}s")
        self.lbl_dur.setFixedWidth(60)
        self.lbl_dur.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.lbl_dur.setStyleSheet("color: #a0a0a0; background: transparent;")
        layout.addWidget(self.lbl_dur)

class BVolumeWidget(QWidget):
    valueChanged = Signal(float)
    def __init__(self, initial_vol, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0, 200)
        self.slider.setValue(int(initial_vol * 100))
        layout.addWidget(self.slider, stretch=1)

        self.spin = QDoubleSpinBox()
        self.spin.setRange(0.00, 2.00)
        self.spin.setSingleStep(0.05)
        self.spin.setDecimals(2)
        self.spin.setFixedWidth(55)
        self.spin.setValue(initial_vol)
        layout.addWidget(self.spin)

        self.slider.valueChanged.connect(self.on_slider_changed)
        self.spin.valueChanged.connect(self.on_spin_changed)

    def on_slider_changed(self, val):
        vol = val / 100.0
        self.spin.blockSignals(True)
        self.spin.setValue(vol)
        self.spin.blockSignals(False)
        self.valueChanged.emit(vol)

    def on_spin_changed(self, val):
        self.slider.blockSignals(True)
        self.slider.setValue(int(val * 100))
        self.slider.blockSignals(False)
        self.valueChanged.emit(val)

class AppConfig:
    def __init__(self):
        self.config_path = os.path.abspath(os.path.join(os.getcwd(), "app_config.json"))
        self.default_interval = 0.5
        self.font_family = "Yu Mincho"
        self.font_size = 58
        self.position = "bottom"
        self.text_color = "#EEF1F8"
        self.box_color = "#000000"
        self.box_opacity = 0.5
        self.margin_bottom = 95
        self.direction = "horizontal"
        self.load()

    def load(self):
        if os.path.exists(self.config_path):
            try:
                import json
                with open(self.config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.default_interval = data.get("default_interval", 0.5)
                style = data.get("subtitle_style", {})
                self.font_family = style.get("font_family", "Yu Mincho")
                self.font_size = style.get("font_size", 58)
                self.position = style.get("position", "bottom")
                self.text_color = style.get("text_color", "#EEF1F8")
                self.box_color = style.get("box_color", "#000000")
                self.box_opacity = style.get("box_opacity", 0.5)
                self.margin_bottom = style.get("margin_bottom", 95)
                self.direction = style.get("direction", "horizontal")
            except Exception:
                pass

    def save(self):
        import json
        data = {
            "default_interval": self.default_interval,
            "subtitle_style": {
                "font_family": self.font_family,
                "font_size": self.font_size,
                "position": self.position,
                "text_color": self.text_color,
                "box_color": self.box_color,
                "box_opacity": self.box_opacity,
                "margin_bottom": self.margin_bottom,
                "direction": self.direction
            }
        }
        try:
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

class ConfigDialog(QDialog):
    def __init__(self, app_config, project, parent=None):
        super().__init__(parent)
        self.app_config = app_config
        self.project = project
        self.setWindowTitle("アプリ・プロジェクト設定")
        self.resize(500, 560)

        # システムフォント一覧の取得
        self.system_fonts = []
        try:
            self.system_fonts = sorted(list(renderer.get_system_font_paths().keys()))
        except Exception:
            pass
        if not self.system_fonts:
            self.system_fonts = ["Yu Gothic", "Yu Mincho", "MS Gothic", "MS Mincho", "Meiryo"]

        # デフォルトの明朝体フォントを決定
        self.default_mincho = "Yu Mincho"
        if self.default_mincho not in self.system_fonts:
            alternatives = ["YuMincho", "MS Mincho", "Hiragino Mincho ProN", "游明朝", "游明朝体", "ＭＳ 明朝"]
            for alt in alternatives:
                if alt in self.system_fonts:
                    self.default_mincho = alt
                    break

        layout = QVBoxLayout(self)

        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        # 1. プロジェクト個別設定タブ
        self.proj_tab = QWidget()
        self.build_proj_tab()
        self.tabs.addTab(self.proj_tab, "現在のプロジェクト設定")

        # 2. アプリ全体のデフォルト設定タブ
        self.app_tab = QWidget()
        self.build_app_tab()
        self.tabs.addTab(self.app_tab, "アプリ初期設定")

        # ボタン
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            parent=self
        )
        self.buttons.accepted.connect(self.accept_and_save)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

        # プロジェクトが無い場合はプロジェクトタブを非活性に (インデックス0)
        if not self.project:
            self.tabs.setTabEnabled(0, False)
            self.proj_chk.setEnabled(False)
            self.proj_chk.setChecked(False)

    def build_app_tab(self):
        lay = QVBoxLayout(self.app_tab)
        form = QGridLayout()
        lay.addLayout(form)

        form.addWidget(QLabel("デフォルト音声間隔:"), 0, 0)
        self.app_gap_spin = QDoubleSpinBox()
        self.app_gap_spin.setRange(0.0, 60.0)
        self.app_gap_spin.setSuffix("s")
        self.app_gap_spin.setValue(self.app_config.default_interval)
        form.addWidget(self.app_gap_spin, 0, 1)

        form.addWidget(QLabel("字幕フォント:"), 1, 0)
        self.app_font_combo = QComboBox()
        self.app_font_combo.addItems(self.system_fonts)
        if self.app_config.font_family in self.system_fonts:
            self.app_font_combo.setCurrentText(self.app_config.font_family)
        else:
            self.app_font_combo.setCurrentText(self.default_mincho)
        form.addWidget(self.app_font_combo, 1, 1)

        form.addWidget(QLabel("字幕フォントサイズ:"), 2, 0)
        self.app_font_size = QSpinBox()
        self.app_font_size.setRange(10, 200)
        self.app_font_size.setValue(self.app_config.font_size)
        form.addWidget(self.app_font_size, 2, 1)

        form.addWidget(QLabel("字幕表示位置:"), 3, 0)
        self.app_position = QComboBox()
        self.app_position.addItems(["top", "center", "bottom"])
        self.app_position.setCurrentText(self.app_config.position)
        form.addWidget(self.app_position, 3, 1)

        form.addWidget(QLabel("字幕文字色:"), 4, 0)
        self.app_text_color = QLineEdit(self.app_config.text_color)
        form.addWidget(self.app_text_color, 4, 1)

        form.addWidget(QLabel("背景ボックス色:"), 5, 0)
        self.app_box_color = QLineEdit(self.app_config.box_color)
        form.addWidget(self.app_box_color, 5, 1)

        form.addWidget(QLabel("ボックス不透明度:"), 6, 0)
        self.app_box_opacity = QDoubleSpinBox()
        self.app_box_opacity.setRange(0.0, 1.0)
        self.app_box_opacity.setSingleStep(0.1)
        self.app_box_opacity.setValue(self.app_config.box_opacity)
        form.addWidget(self.app_box_opacity, 6, 1)

        form.addWidget(QLabel("下マージン:"), 7, 0)
        self.app_margin = QSpinBox()
        self.app_margin.setRange(0, 500)
        self.app_margin.setValue(self.app_config.margin_bottom)
        form.addWidget(self.app_margin, 7, 1)

        form.addWidget(QLabel("字幕書字方向:"), 8, 0)
        self.app_direction_combo = QComboBox()
        self.app_direction_combo.addItems(["横書き", "縦書き"])
        self.app_direction_combo.setCurrentText("縦書き" if self.app_config.direction == "vertical" else "横書き")
        form.addWidget(self.app_direction_combo, 8, 1)

        lay.addStretch()

    def build_proj_tab(self):
        lay = QVBoxLayout(self.proj_tab)

        self.proj_chk = QCheckBox("このプロジェクトで個別の設定を使用する（アプリ設定を上書き）")
        lay.addWidget(self.proj_chk)

        self.proj_form_widget = QWidget()
        self.proj_form = QGridLayout(self.proj_form_widget)
        lay.addWidget(self.proj_form_widget)

        self.proj_form.addWidget(QLabel("デフォルト音声間隔:"), 0, 0)
        self.proj_gap_spin = QDoubleSpinBox()
        self.proj_gap_spin.setRange(0.0, 60.0)
        self.proj_gap_spin.setSuffix("s")
        self.proj_form.addWidget(self.proj_gap_spin, 0, 1)

        self.proj_form.addWidget(QLabel("字幕フォント:"), 1, 0)
        self.proj_font_combo = QComboBox()
        self.proj_font_combo.addItems(self.system_fonts)
        self.proj_form.addWidget(self.proj_font_combo, 1, 1)

        self.proj_form.addWidget(QLabel("字幕フォントサイズ:"), 2, 0)
        self.proj_font_size = QSpinBox()
        self.proj_font_size.setRange(10, 200)
        self.proj_form.addWidget(self.proj_font_size, 2, 1)

        self.proj_form.addWidget(QLabel("字幕表示位置:"), 3, 0)
        self.proj_position = QComboBox()
        self.proj_position.addItems(["top", "center", "bottom"])
        self.proj_form.addWidget(self.proj_position, 3, 1)

        self.proj_form.addWidget(QLabel("字幕文字色:"), 4, 0)
        self.proj_text_color = QLineEdit()
        self.proj_form.addWidget(self.proj_text_color, 4, 1)

        self.proj_form.addWidget(QLabel("背景ボックス色:"), 5, 0)
        self.proj_box_color = QLineEdit()
        self.proj_form.addWidget(self.proj_box_color, 5, 1)

        self.proj_form.addWidget(QLabel("ボックス不透明度:"), 6, 0)
        self.proj_box_opacity = QDoubleSpinBox()
        self.proj_box_opacity.setRange(0.0, 1.0)
        self.proj_box_opacity.setSingleStep(0.1)
        self.proj_form.addWidget(self.proj_box_opacity, 6, 1)

        self.proj_form.addWidget(QLabel("下マージン:"), 7, 0)
        self.proj_margin = QSpinBox()
        self.proj_margin.setRange(0, 500)
        self.proj_form.addWidget(self.proj_margin, 7, 1)

        self.proj_form.addWidget(QLabel("字幕書字方向:"), 8, 0)
        self.proj_direction_combo = QComboBox()
        self.proj_direction_combo.addItems(["横書き", "縦書き"])
        self.proj_form.addWidget(self.proj_direction_combo, 8, 1)

        lay.addStretch()

        # 連動設定
        self.proj_chk.toggled.connect(self.on_proj_chk_toggled)

        if self.project:
            self.proj_chk.setChecked(self.project.use_project_settings)
            self.proj_gap_spin.setValue(self.project.default_interval)
            style = self.project.subtitle_style
            if style.font_family in self.system_fonts:
                self.proj_font_combo.setCurrentText(style.font_family)
            else:
                self.proj_font_combo.setCurrentText(self.default_mincho)
            self.proj_font_size.setValue(style.font_size)
            self.proj_position.setCurrentText(style.position)
            self.proj_text_color.setText(style.text_color)
            self.proj_box_color.setText(style.box_color)
            self.proj_box_opacity.setValue(style.box_opacity)
            self.proj_margin.setValue(style.margin_bottom)
            self.proj_direction_combo.setCurrentText("縦書き" if style.direction == "vertical" else "横書き")

        self.on_proj_chk_toggled(self.proj_chk.isChecked())

    def on_proj_chk_toggled(self, checked):
        self.proj_form_widget.setEnabled(checked)

    def accept_and_save(self):
        # 1. アプリ設定を保存
        self.app_config.default_interval = self.app_gap_spin.value()
        self.app_config.font_family = self.app_font_combo.currentText()
        self.app_config.font_size = self.app_font_size.value()
        self.app_config.position = self.app_position.currentText()
        self.app_config.text_color = self.app_text_color.text().strip()
        self.app_config.box_color = self.app_box_color.text().strip()
        self.app_config.box_opacity = self.app_box_opacity.value()
        self.app_config.margin_bottom = self.app_margin.value()
        self.app_config.direction = "vertical" if self.app_direction_combo.currentText() == "縦書き" else "horizontal"
        self.app_config.save()

        # 2. プロジェクト個別設定を保存
        if self.project:
            self.project.use_project_settings = self.proj_chk.isChecked()
            if self.project.use_project_settings:
                self.project.default_interval = self.proj_gap_spin.value()
                style = self.project.subtitle_style
                style.font_family = self.proj_font_combo.currentText()
                style.font_size = self.proj_font_size.value()
                style.position = self.proj_position.currentText()
                style.text_color = self.proj_text_color.text().strip()
                style.box_color = self.proj_box_color.text().strip()
                style.box_opacity = self.proj_box_opacity.value()
                style.margin_bottom = self.proj_margin.value()
                style.direction = "vertical" if self.proj_direction_combo.currentText() == "縦書き" else "horizontal"
            self.project.save()

        self.accept()

class RatioTableWidget(QTableWidget):
    def __init__(self, ratios, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.ratios = ratios

        # 垂直ヘッダー(行番号)を非表示にする(白い背景とダブる番号の解消)
        self.verticalHeader().setVisible(False)

        # 選択モードをセル選択にし、IDとファイル名のみハイライト制限する
        self.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectItems)
        self.itemSelectionChanged.connect(self.limit_selection_to_id_and_name)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        total_width = self.viewport().width()
        total_ratio = sum(self.ratios)
        if total_ratio > 0:
            for col, ratio in enumerate(self.ratios):
                w = int(total_width * ratio / total_ratio)
                self.setColumnWidth(col, w)

    def mousePressEvent(self, event):
        # 何もないエリアをクリックしたら選択をクリア
        item = self.itemAt(event.position().toPoint())
        if item is None:
            self.clearSelection()
            self.setCurrentItem(None)
        else:
            super().mousePressEvent(event)

    def limit_selection_to_id_and_name(self):
        from PySide6.QtCore import QTimer
        QTimer.singleShot(0, self._do_limit_selection)

    def _do_limit_selection(self):
        # 既にID(0)とファイル名(1)のみが正しく選択されている場合は、無限登録ループを防ぐため処理をスルー
        selected_items = self.selectedItems()
        if not selected_items:
            return

        selected_rows = set()
        already_limited = True
        for item in selected_items:
            selected_rows.add(item.row())
            if item.column() not in (0, 1):
                already_limited = False

        if already_limited:
            all_ok = True
            for row in selected_rows:
                i0 = self.item(row, 0)
                i1 = self.item(row, 1)
                if not (i0 and i0.isSelected() and i1 and i1.isSelected()):
                    all_ok = False
                    break
            if all_ok:
                return # 無限再帰を遮断

        self.blockSignals(True)
        self.clearSelection()
        for row in selected_rows:
            item0 = self.item(row, 0)
            item1 = self.item(row, 1)
            if item0:
                item0.setSelected(True)
            if item1:
                item1.setSelected(True)
        self.blockSignals(False)
        self.itemSelectionChanged.emit()

class DragDropTableWidget(RatioTableWidget):
    order_changed = Signal(int, int)

    def __init__(self, ratios, *args, **kwargs):
        super().__init__(ratios, *args, **kwargs)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDragDropOverwriteMode(False)
        self.setDragDropMode(QTableWidget.DragDropMode.InternalMove)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)

    def dropEvent(self, event):
        src_item = self.currentItem()
        if not src_item:
            return
        src_row = src_item.row()

        pos = event.position().toPoint()
        dest_item = self.itemAt(pos)

        if dest_item:
            dest_row = dest_item.row()
        else:
            dest_row = self.rowCount() - 1

        if src_row != dest_row:
            self.order_changed.emit(src_row, dest_row)
            event.accept()
        else:
            event.ignore()

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
        self.cancel_requested = False

    def cancel(self):
        self.cancel_requested = True

    def run(self):
        try:
            output = renderer.render_movie(
                self.project,
                log_callback=self.log_signal.emit,
                cancel_callback=lambda: self.cancel_requested
            )
            self.finished_signal.emit(True, output)
        except renderer.RenderCancelled as e:
            self.finished_signal.emit(False, str(e))
        except Exception as e:
            import traceback
            print(traceback.format_exc())
            self.finished_signal.emit(False, str(e) or "動画生成中にエラーが発生しました。")

class ReadingVideoApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Yomiiro")
        self.resize(1280, 950)

        self.project = None
        self.selected_clip_id = None
        self.is_generating = False

        self.thread = None
        self.worker = None
        self.app_config = AppConfig()
        self.preview_cache = {}

        # 字幕テキスト入力遅延プレビュー更新タイマー
        self.subtitle_timer = QTimer(self)
        self.subtitle_timer.setSingleShot(True)
        self.subtitle_timer.setInterval(1000) # 1秒 (1000ms)
        self.subtitle_timer.timeout.connect(self.update_preview_from_timer)

        # 音声プレビュー用のメディアプレイヤーと再生状態管理
        self.active_playback_type = None
        self.current_audition_bgm = None
        self.media_player = QMediaPlayer(self)
        self.audio_output = QAudioOutput(self)
        self.media_player.setAudioOutput(self.audio_output)
        self.media_player.playbackStateChanged.connect(self.on_playback_state_changed)
        self.media_player.positionChanged.connect(self.apply_bgm_fade)

        self.apply_dark_theme()
        self.build_ui()

        temp_dir = os.path.abspath(os.path.join(os.getcwd(), "untitled_project"))
        self.project = core.Project(temp_dir)
        self.update_project_ui()

        # ショートカットキーの登録 (Ctrl+S で保存)
        self.save_shortcut = QShortcut(QKeySequence("Ctrl+S"), self)
        self.save_shortcut.activated.connect(self.save_project)

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
            QListWidget::item:selected, QTableWidget::item:selected {
                background-color: #3a7a3a;
                color: #ffffff;
            }
            QListWidget::item:selected:active, QTableWidget::item:selected:active {
                background-color: #3a7a3a;
                color: #ffffff;
            }
            QListWidget::item:selected:!active, QTableWidget::item:selected:!active {
                background-color: #3a7a3a;
                color: #ffffff;
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

        btn_config = QPushButton("⚙️ 設定")
        btn_config.clicked.connect(self.open_config_dialog)
        top_bar.addWidget(btn_config)

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

        # 中央ペイン: プレビュー
        center_widget = QWidget()
        center_layout = QVBoxLayout(center_widget)
        center_layout.setContentsMargins(0, 0, 0, 0)

        group_preview = QGroupBox(" プレビュー ")
        group_preview_layout = QVBoxLayout(group_preview)

        self.preview_widget = PreviewWidget()
        group_preview_layout.addWidget(self.preview_widget)
        center_layout.addWidget(group_preview)

        # 右ペイン: クリップ詳細 & 全体スタイル
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)

        # splitter への追加順を変更 (プレビューを左、リストを中央、詳細は右)
        splitter.addWidget(center_widget) # インデックス0: 左
        splitter.addWidget(left_widget)   # インデックス1: 中央
        splitter.addWidget(right_widget)  # インデックス2: 右

        group_detail = QGroupBox(" クリップ詳細・字幕編集 ")
        group_detail_layout = QVBoxLayout(group_detail)

        # 有効チェックボックスを最上部に配置
        chk_row = QHBoxLayout()
        group_detail_layout.addLayout(chk_row)
        self.clip_enabled_chk = QCheckBox("このクリップを動画に含める（有効化）")
        self.clip_enabled_chk.setChecked(True)
        self.clip_enabled_chk.stateChanged.connect(self.on_clip_enabled_changed)
        chk_row.addWidget(self.clip_enabled_chk)
        chk_row.addStretch()

        group_detail_layout.addWidget(QLabel("字幕テキスト:"))
        self.subtitle_text = QTextEdit()
        self.subtitle_text.setStyleSheet("font-size: 16px;") # 大きくして視認性を向上
        self.subtitle_text.textChanged.connect(self.on_subtitle_changed)
        group_detail_layout.addWidget(self.subtitle_text, stretch=1)

        # 個別無音時間・音量スライダー (グリッドレイアウト)
        grid_opts = QGridLayout()
        group_detail_layout.addLayout(grid_opts)

        grid_opts.addWidget(QLabel("次の音声までの余白（秒）:"), 0, 0)
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
        self.clip_vol_spin = QDoubleSpinBox()
        self.clip_vol_spin.setRange(0.00, 2.00)
        self.clip_vol_spin.setSingleStep(0.05)
        self.clip_vol_spin.setDecimals(2)
        self.clip_vol_spin.setFixedWidth(60)
        self.clip_vol_spin.valueChanged.connect(self.on_clip_vol_spin_changed)
        vol_lay.addWidget(self.clip_vol_spin)
        grid_opts.addLayout(vol_lay, 1, 1)

        # 個別音量の試聴ボタン
        grid_opts.addWidget(QLabel("個別音量の試聴:"), 2, 0)
        self.play_btn = QPushButton("▶ 試聴")
        self.play_btn.clicked.connect(self.toggle_play_clip)
        grid_opts.addWidget(self.play_btn, 2, 1)

        right_layout.addWidget(group_detail, stretch=1)
        splitter.addWidget(right_widget)

        splitter.setSizes([480, 350, 450])

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

        self.bg_table = DragDropTableWidget([40, 300, 100, 100, 60], 0, 5)
        self.bg_table.setHorizontalHeaderLabels(["ID", "ファイル名", "開始クリップ", "終了クリップ", "有効"])
        self.bg_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.bg_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.bg_table.order_changed.connect(self.on_bg_order_changed)
        self.bg_table.itemSelectionChanged.connect(self.update_preview)
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

        self.bgm_play_btn = QPushButton("▶ 試聴")
        self.bgm_play_btn.setMinimumWidth(150)  # 横幅を2倍程度にして押し間違いを防ぐ
        self.bgm_play_btn.clicked.connect(self.toggle_play_bgm)
        bgm_btn_bar.addWidget(self.bgm_play_btn)
        bgm_btn_bar.addStretch()

        self.bgm_table = DragDropTableWidget([40, 250, 85, 85, 200, 150, 150, 60, 60], 0, 9)
        self.bgm_table.setHorizontalHeaderLabels(["ID", "ファイル名", "開始クリップ", "終了クリップ", "音量", "フェードイン", "フェードアウト", "ループ", "有効"])
        self.bgm_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.bgm_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.bgm_table.order_changed.connect(self.on_bgm_order_changed)
        self.bgm_table.itemSelectionChanged.connect(lambda: self.media_player.stop())
        self.bg_table.itemSelectionChanged.connect(lambda: self.media_player.stop())
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

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid #404040;
                border-radius: 4px;
                text-align: center;
                background-color: #2d2d2d;
                color: #ffffff;
            }
            QProgressBar::chunk {
                background-color: #2a5a2a;
                width: 10px;
            }
        """)
        log_group_layout.addWidget(self.progress_bar)

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

        gen_row = QHBoxLayout()
        export_layout.addLayout(gen_row)

        self.gen_btn = QPushButton("🎬 動画生成を開始")
        self.gen_btn.setObjectName("action_btn")
        self.gen_btn.setFixedHeight(50)
        self.gen_btn.clicked.connect(self.start_generation)
        gen_row.addWidget(self.gen_btn, stretch=2)

        self.open_folder_btn = QPushButton("📁 プロジェクトフォルダを開く")
        self.open_folder_btn.setFixedHeight(50)
        self.open_folder_btn.setEnabled(False)
        self.open_folder_btn.clicked.connect(self.open_output_folder)
        gen_row.addWidget(self.open_folder_btn, stretch=1)

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
        self.media_player.stop() # 試聴停止
        self.subtitle_timer.stop() # 切り替え時にタイマーをキャンセル

        # 背景テーブル・BGMテーブルの選択をクリア (音声側プレビューをアサート)
        if hasattr(self, "bg_table"):
            self.bg_table.blockSignals(True)
            self.bg_table.clearSelection()
            self.bg_table.setCurrentItem(None)
            self.bg_table.blockSignals(False)
        if hasattr(self, "bgm_table"):
            self.bgm_table.blockSignals(True)
            self.bgm_table.clearSelection()
            self.bgm_table.setCurrentItem(None)
            self.bgm_table.blockSignals(False)

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
            self.clip_vol_scale.blockSignals(False)

            self.clip_vol_spin.blockSignals(True)
            self.clip_vol_spin.setValue(clip.volume)
            self.clip_vol_spin.blockSignals(False)

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
            self.subtitle_timer.start() # 1秒後にプレビューを更新

    def update_preview_from_timer(self):
        self.update_preview()

    def on_clip_vol_changed(self, val):
        if not self.project or not self.selected_clip_id:
            return
        clip = next((c for c in self.project.audio_clips if c.id == self.selected_clip_id), None)
        if clip:
            vol = val / 100.0
            clip.volume = vol
            self.clip_vol_spin.blockSignals(True)
            self.clip_vol_spin.setValue(vol)
            self.clip_vol_spin.blockSignals(False)
            self.refresh_clip_list()

    def on_clip_vol_spin_changed(self, val):
        if not self.project or not self.selected_clip_id:
            return
        clip = next((c for c in self.project.audio_clips if c.id == self.selected_clip_id), None)
        if clip:
            clip.volume = val
            self.clip_vol_scale.blockSignals(True)
            self.clip_vol_scale.setValue(int(val * 100))
            self.clip_vol_scale.blockSignals(False)
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
            file_name = getattr(bg, "display_name", os.path.basename(bg.file_path))
            file_item = QTableWidgetItem(file_name)
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
            file_name = getattr(bgm, "display_name", os.path.basename(bgm.file_path))
            file_item = QTableWidgetItem(file_name)
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
        files, _ = QFileDialog.getOpenFileNames(
            self, "背景画像を追加", "",
            "Image Files (*.png *.jpg *.jpeg *.webp)"
        )
        if files:
            for file in files:
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
        files, _ = QFileDialog.getOpenFileNames(
            self, "BGMアセットを追加", "",
            "Audio Files (*.wav *.mp3 *.m4a *.aac *.ogg *.flac)"
        )
        if files:
            for file in files:
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
            errors = []
            for f in files:
                try:
                    self.project.add_audio_clip(f, self.log_write)
                except Exception as e:
                    errors.append(f"{os.path.basename(f)}: {e}")
            self.renumber_clips()
            self.refresh_clip_list()
            self.refresh_bg_table()
            self.refresh_bgm_table()
            self.update_preview()
            self.project.save()
            if errors:
                QMessageBox.critical(self, "音声追加エラー", "\n".join(errors))

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
        if hasattr(self, "media_player"):
            self.media_player.stop()
        if not self.project:
            self.project_label.setText("プロジェクト: 未設定")
            return

        self.project_label.setText(f"フォルダ: {os.path.basename(self.project.project_dir)}")
        self.output_ent.setText(self.project.output_path)

        # 保存先フォルダ開くボタンの活性状態をチェック
        out_file = self.project.get_output_abspath()
        self.open_folder_btn.setEnabled(os.path.exists(out_file))

        # 設定の同期（プロジェクト個別設定を使用しない場合はアプリデフォルトを同期）
        self.sync_project_settings()

        self.refresh_clip_list()
        self.refresh_bg_table()
        self.refresh_bgm_table()
        self.update_preview()

    def update_comboboxes(self):
        # 各行のセルウィジェットComboBoxを更新するためにテーブルをリフレッシュする
        self.refresh_bg_table()
        self.refresh_bgm_table()

    def clear_preview_cache(self):
        self.preview_cache.clear()

    def cache_preview_pixmap(self, key, pixmap):
        if len(self.preview_cache) >= 32:
            oldest_key = next(iter(self.preview_cache))
            self.preview_cache.pop(oldest_key, None)
        self.preview_cache[key] = pixmap

    def file_stamp(self, path):
        try:
            stat = os.stat(path)
            return (stat.st_mtime_ns, stat.st_size)
        except OSError:
            return None

    def subtitle_style_key(self):
        style = self.project.subtitle_style
        return (
            style.font_family,
            style.font_size,
            style.text_color,
            style.shadow_color,
            style.box_color,
            style.box_opacity,
            style.position,
            style.margin_bottom,
            style.max_width,
            style.line_spacing,
            style.direction,
        )

    def preview_background_key(self):
        bg_key = []
        for bg_set in self.project.backgrounds:
            try:
                path = core.resolve_asset_path(self.project.project_dir, bg_set.file_path, "images", core.IMAGE_EXTS)
                stamp = self.file_stamp(path)
            except Exception:
                stamp = None
            bg_key.append((
                bg_set.id,
                bg_set.file_path,
                bg_set.start_clip_id,
                bg_set.end_clip_id,
                bg_set.enabled,
                bg_set.transition_type,
                bg_set.transition_duration,
                stamp,
            ))
        return tuple(bg_key)

    def update_preview(self):
        if not self.project:
            self.preview_widget.set_pixmap(QPixmap())
            self.preview_widget.set_text("プロジェクトが選択されていません")
            return

        # 1. まず背景画像テーブルの選択があるか確認
        bg_selected = self.bg_table.selectedItems() if hasattr(self, "bg_table") else []
        if bg_selected:
            row = bg_selected[0].row()
            if row < len(self.project.backgrounds):
                bg_set = self.project.backgrounds[row]
                img_path = core.resolve_asset_path(self.project.project_dir, bg_set.file_path, "images", core.IMAGE_EXTS)
                if os.path.exists(img_path):
                    key = (
                        "bg",
                        self.project.project_dir,
                        bg_set.id,
                        bg_set.file_path,
                        self.file_stamp(img_path),
                        self.project.width,
                        self.project.height,
                    )
                    cached = self.preview_cache.get(key)
                    if cached is not None:
                        self.preview_widget.set_pixmap(cached)
                        return
                    try:
                        img = Image.open(img_path)
                        fitted = renderer.fit_cover(img, self.project.width, self.project.height)
                        pix = pil_to_qpixmap(fitted)
                        self.cache_preview_pixmap(key, pix)
                        self.preview_widget.set_pixmap(pix)
                        return
                    except Exception as e:
                        self.preview_widget.set_text(f"画像プレビューエラー:\n{e}")
                        return

        # 2. 音声クリップベースのプレビュー
        if not self.selected_clip_id:
            self.preview_widget.set_pixmap(QPixmap())
            self.preview_widget.set_text("クリップが選択されていません")
            return

        try:
            target_clip = next((c for c in self.project.audio_clips if c.id == self.selected_clip_id), None)
            clip_key = None
            if target_clip:
                clip_key = (
                    "clip",
                    self.project.project_dir,
                    self.selected_clip_id,
                    target_clip.subtitle,
                    target_clip.enabled,
                    self.project.width,
                    self.project.height,
                    self.subtitle_style_key(),
                    self.preview_background_key(),
                )
                cached = self.preview_cache.get(clip_key)
                if cached is not None:
                    self.preview_widget.set_pixmap(cached)
                    return
            preview_img = renderer.generate_preview_image(self.project, self.selected_clip_id)
            pix = pil_to_qpixmap(preview_img)
            if clip_key is not None:
                self.cache_preview_pixmap(clip_key, pix)
            self.preview_widget.set_pixmap(pix)
        except Exception as e:
            self.preview_widget.set_text(f"プレビューエラー:\n{e}")

    # ------------------
    # アプリ設定・プロジェクト設定の同期・ダイアログ
    # ------------------
    def open_config_dialog(self):
        dlg = ConfigDialog(self.app_config, self.project, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.clear_preview_cache()
            self.sync_project_settings()
            self.update_preview()
            self.refresh_clip_list()
            self.log_write("設定を更新しました。")

    def sync_project_settings(self):
        if not self.project:
            return
        if not self.project.use_project_settings:
            # アプリ設定のデフォルト値を同期
            self.project.default_interval = self.app_config.default_interval
            style = self.project.subtitle_style
            style.font_family = self.app_config.font_family
            style.font_size = self.app_config.font_size
            style.position = self.app_config.position
            style.text_color = self.app_config.text_color
            style.box_color = self.app_config.box_color
            style.box_opacity = self.app_config.box_opacity
            style.margin_bottom = self.app_config.margin_bottom
            style.direction = self.app_config.direction
            self.project.save()

    # ------------------
    # ログ出力・動画生成スレッド
    # ------------------
    def log_write(self, msg):
        msg_str = str(msg)
        if msg_str.startswith("PROGRESS:"):
            try:
                val = int(msg_str.split(":")[1])
                self.progress_bar.setValue(val)
            except Exception:
                pass
        else:
            self.log_area.append(msg_str)

    def start_generation(self):
        if not self.project:
            return
        if self.is_generating:
            self.cancel_generation()
            return

        enabled_clips = [c for c in self.project.audio_clips if c.enabled]
        if not enabled_clips:
            QMessageBox.critical(self, "エラー", "有効な音声クリップがありません。")
            return

        if not self.project.backgrounds:
            QMessageBox.critical(self, "エラー", "背景画像が登録されていません。")
            return

        output_path = self.output_ent.text().strip()
        try:
            self.project.set_output_path(
                output_path,
                allow_external=self.project.is_trusted_external_output(output_path)
            )
        except ValueError as e:
            QMessageBox.critical(self, "繧ｨ繝ｩ繝ｼ", str(e))
            return

        self.is_generating = True
        self.gen_btn.setEnabled(True)
        self.gen_btn.setText("キャンセル")
        self.open_folder_btn.setEnabled(False)
        self.log_area.clear()
        self.progress_bar.setValue(0)

        # レンダリング前に設定の同期を確認
        self.sync_project_settings()

        self.thread = QThread()
        self.worker = RenderWorker(self.project)
        self.worker.moveToThread(self.thread)

        self.thread.started.connect(self.worker.run)
        self.worker.log_signal.connect(self.log_write)
        self.worker.finished_signal.connect(self.on_generation_finished)

        self.thread.start()

    def cancel_generation(self):
        if self.worker:
            self.worker.cancel()
        self.gen_btn.setEnabled(False)
        self.gen_btn.setText("キャンセル中...")
        self.log_write("動画生成のキャンセルを要求しました。")

    def on_generation_finished(self, success, result_msg):
        self.thread.quit()
        self.thread.wait()
        self.thread = None
        self.worker = None

        self.is_generating = False
        self.gen_btn.setEnabled(True)
        self.gen_btn.setText("🎬 動画生成を開始")
        self.progress_bar.setValue(100 if success else 0)

        if success:
            self.open_folder_btn.setEnabled(True)
            QMessageBox.information(self, "完了", f"動画生成が完了しました！\n出力先: {result_msg}")
        elif "キャンセル" in result_msg:
            self.open_folder_btn.setEnabled(os.path.exists(self.project.get_output_abspath()))
            QMessageBox.information(self, "キャンセル", result_msg)
        else:
            self.open_folder_btn.setEnabled(os.path.exists(self.project.get_output_abspath()))
            QMessageBox.critical(self, "エラー", f"動画生成に失敗しました:\n{result_msg}")

    def open_output_folder(self):
        if not self.project:
            return
        out_file = self.project.get_output_abspath()
        if os.path.exists(out_file):
            import subprocess
            subprocess.run(["explorer", "/select,", os.path.normpath(out_file)])
        else:
            parent_dir = os.path.dirname(out_file)
            if os.path.exists(parent_dir):
                os.startfile(parent_dir)
            else:
                QMessageBox.warning(self, "警告", "出力先フォルダが見つかりません。")

    def closeEvent(self, event):
        if self.thread and self.thread.isRunning():
            if self.worker:
                self.worker.cancel()
            self.thread.quit()
            if not self.thread.wait(3000):
                QMessageBox.information(self, "キャンセル中", "動画生成のキャンセル処理中です。完了後にもう一度閉じてください。")
                event.ignore()
                return
        event.accept()

    def new_project(self):
        path = QFileDialog.getExistingDirectory(self, "新規プロジェクトの保存先フォルダを選択")
        if path:
            self.project = core.Project(path)
            self.project.save()
            self.selected_clip_id = None
            self.clear_preview_cache()
            self.update_project_ui()
            self.log_write(f"新規プロジェクトを作成しました: {path}")

    def open_project(self):
        path = QFileDialog.getExistingDirectory(self, "プロジェクトフォルダを選択")
        if path:
            if not os.path.exists(os.path.join(path, "project.json")):
                reply = QMessageBox.question(
                    self, "確認", "指定フォルダに プロジェクトデータ がありません。新規作成しますか？",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                )
                if reply == QMessageBox.StandardButton.No:
                    return
            self.project = core.Project.load(path)
            self.selected_clip_id = None
            self.clear_preview_cache()
            self.update_project_ui()
            self.log_write(f"プロジェクトをロードしました: {path}")

    def save_project(self):
        if self.project:
            self.sync_project_settings()
            output_path = self.output_ent.text().strip()
            try:
                self.project.set_output_path(
                    output_path,
                    allow_external=self.project.is_trusted_external_output(output_path)
                )
            except ValueError as e:
                QMessageBox.critical(self, "繧ｨ繝ｩ繝ｼ", str(e))
                return
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
            allow_external = True
            try:
                rel = os.path.relpath(file, self.project.project_dir)
                rel_abs = os.path.abspath(os.path.join(self.project.project_dir, rel))
                if os.path.commonpath([os.path.realpath(self.project.project_dir), os.path.realpath(rel_abs)]) == os.path.realpath(self.project.project_dir):
                    file = rel
                    allow_external = False
            except ValueError:
                pass

            try:
                self.project.set_output_path(file, allow_external=allow_external)
            except ValueError as e:
                QMessageBox.critical(self, "繧ｨ繝ｩ繝ｼ", str(e))
                return

            self.output_ent.blockSignals(True)
            self.output_ent.setText(self.project.output_path)
            self.output_ent.blockSignals(False)

    def mousePressEvent(self, event):
        if hasattr(self, "bg_table"):
            self.bg_table.clearSelection()
            self.bg_table.setCurrentItem(None)
        if hasattr(self, "bgm_table"):
            self.bgm_table.clearSelection()
            self.bgm_table.setCurrentItem(None)
        super().mousePressEvent(event)

    def on_bg_order_changed(self, src, dest):
        if not self.project:
            return
        bg = self.project.backgrounds.pop(src)
        self.project.backgrounds.insert(dest, bg)
        self.project.save()
        self.refresh_bg_table()
        self.update_preview()

    def on_bgm_order_changed(self, src, dest):
        if not self.project:
            return
        bgm = self.project.bgm_tracks.pop(src)
        self.project.bgm_tracks.insert(dest, bgm)
        self.project.save()
        self.refresh_bgm_table()

    def toggle_play_clip(self):
        if not self.project or not self.selected_clip_id:
            return
        clip = next((c for c in self.project.audio_clips if c.id == self.selected_clip_id), None)
        if not clip:
            return

        if self.media_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.media_player.stop()
        else:
            self.active_playback_type = "clip"
            clip_abspath = core.resolve_asset_path(self.project.project_dir, clip.file_path, "audio", core.AUDIO_EXTS)
            if not os.path.exists(clip_abspath):
                QMessageBox.warning(self, "警告", "音声ファイルが見つかりません。")
                return

            # QAudioOutputは1.0が最大のため、clip.volume(0.0〜2.0)を0.5倍にスケーリングして等倍とブーストの差が出るようにします
            self.audio_output.setVolume(min(1.0, max(0.0, clip.volume * 0.5)))
            self.media_player.setSource(QUrl.fromLocalFile(clip_abspath))
            self.media_player.play()

    def toggle_play_bgm(self):
        if not self.project:
            return
        sel = self.bgm_table.selectedItems()
        if not sel:
            QMessageBox.warning(self, "警告", "試聴するBGMトラックを選択してください。")
            return
        row = sel[0].row()
        if row >= len(self.project.bgm_tracks):
            return
        bgm = self.project.bgm_tracks[row]

        if self.media_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.media_player.stop()
            self.current_audition_bgm = None
        else:
            self.active_playback_type = "bgm"
            self.current_audition_bgm = bgm
            bgm_abspath = core.resolve_asset_path(self.project.project_dir, bgm.file_path, "bgm", core.BGM_EXTS)
            if not os.path.exists(bgm_abspath):
                QMessageBox.warning(self, "警告", "BGMファイルが見つかりません。")
                return

            # 初期音量をセット(フェードインがある場合は0から開始)
            initial_vol = 0.0 if bgm.fade_in > 0 else bgm.volume * 0.5
            self.audio_output.setVolume(initial_vol)

            self.media_player.setSource(QUrl.fromLocalFile(bgm_abspath))
            self.media_player.play()

    def apply_bgm_fade(self, position_ms):
        if self.active_playback_type != "bgm" or not self.current_audition_bgm:
            return

        bgm = self.current_audition_bgm
        duration_ms = self.media_player.duration()
        if duration_ms <= 0:
            return

        t = position_ms / 1000.0
        dur = duration_ms / 1000.0

        ratio = 1.0

        # 1. フェードイン領域
        if bgm.fade_in > 0 and t < bgm.fade_in:
            ratio = t / bgm.fade_in

        # 2. フェードアウト領域
        if bgm.fade_out > 0 and t > (dur - bgm.fade_out):
            time_left = dur - t
            ratio = min(ratio, time_left / bgm.fade_out)

        ratio = min(1.0, max(0.0, ratio))
        target_vol = min(1.0, max(0.0, bgm.volume * 0.5 * ratio))
        self.audio_output.setVolume(target_vol)

    def on_playback_state_changed(self, state):
        is_playing = (state == QMediaPlayer.PlaybackState.PlayingState)
        if is_playing:
            if self.active_playback_type == "clip":
                self.play_btn.setText("■ 停止")
                self.play_btn.setStyleSheet("background-color: #5a2a2a; font-weight: bold; color: #ffffff;")
            elif self.active_playback_type == "bgm":
                self.bgm_play_btn.setText("■ 停止")
                self.bgm_play_btn.setStyleSheet("background-color: #5a2a2a; font-weight: bold; color: #ffffff;")
        else:
            self.play_btn.setText("▶ 試聴")
            self.play_btn.setStyleSheet("")
            self.bgm_play_btn.setText("▶ 試聴")
            self.bgm_play_btn.setStyleSheet("")
            self.active_playback_type = None
            self.current_audition_bgm = None

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = ReadingVideoApp()
    window.show()
    sys.exit(app.exec())
