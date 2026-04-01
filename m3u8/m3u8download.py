import json
import re
import subprocess
import sys
import threading
from collections import deque
from pathlib import Path
from typing import Any, Dict, List, Optional

import unicodedata
import yaml
from PySide6.QtCore import Qt, QTimer, Signal, QUrl, QPoint
from PySide6.QtGui import QIcon, QColor, QPixmap, QFontMetrics, QAction
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QTableWidget,
    QHeaderView, QTextEdit, QTableWidgetItem, QFileDialog, QMainWindow, QMessageBox,
    QApplication, QScrollArea, QGridLayout, QGraphicsDropShadowEffect, QMenu, QAbstractItemView
)

from flask import Flask, request, jsonify
from flask_cors import CORS


def sanitize_filename(filename):
    invalid_chars = re.compile(r'[<>:"/\\|?*\u30FB\u2022\u00B7\u0387\u16EB\u2219\u22C4\u25CF\uFF0E]')
    filename = re.sub(invalid_chars, '', filename)
    filename = ''.join(c for c in filename if unicodedata.category(c)[0] != 'C')
    filename = filename.strip().strip('.')
    reserved_names = {'CON', 'PRN', 'AUX', 'NUL', 'COM1', 'COM2', 'COM3', 'COM4',
                      'COM5', 'COM6', 'COM7', 'COM8', 'COM9', 'LPT1', 'LPT2',
                      'LPT3', 'LPT4', 'LPT5', 'LPT6', 'LPT7', 'LPT8', 'LPT9'}
    if filename.upper() in reserved_names:
        filename = f"{filename}_file"
    max_length = 100

    if len(filename) > max_length:
        filename = filename[:max_length]
    return filename


def generate_pic_url(save_name: str) -> str:
    if not save_name:
        return ""
    code = save_name.split(' ', 1)[0].strip().lower()
    return f"https://fourhoi.com/{code}/cover-n.jpg"


class VideoCard(QWidget):
    def __init__(self, item_data: Dict[str, Any], parent: 'M3U8Downloader'):
        super().__init__(parent)
        if not isinstance(parent, M3U8Downloader):
            raise TypeError("VideoCard 的 parent 必须是 M3U8Downloader 实例")
        self.downloader: M3U8Downloader = parent
        self.item_data = item_data
        self._valid = True

        self.setFixedSize(200, 150)
        self.setStyleSheet("""
            VideoCard {background: #2d2d2d; border-radius: 8px;}
            VideoCard:hover {background: #383838; border: 2px solid #0078d7;}
        """)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(8)
        shadow.setXOffset(0)
        shadow.setYOffset(0)
        shadow.setColor(QColor(0, 0, 0, 200))
        self.setGraphicsEffect(shadow)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.image_container = QWidget(self)
        self.image_container.setFixedSize(200, 134)
        self.image_container.setStyleSheet("background: #1e1e1e;")

        image_layout = QVBoxLayout(self.image_container)
        image_layout.setContentsMargins(0, 0, 0, 0)

        self.pic_label = QLabel()
        self.pic_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.pic_label.setFixedSize(200, 134)
        image_layout.addWidget(self.pic_label)

        self.title_label = QLabel()
        self.title_label.setFixedHeight(16)
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title_label.setStyleSheet("""
            QLabel {color: gray; font-size: 14px; font-weight: bold; padding: 0 0px; background: #1e1e1e; }
        """)
        self.original_title = item_data['name']

        layout.addWidget(self.image_container)
        layout.addWidget(self.title_label)

        self.load_image(item_data['pic'])
        QTimer.singleShot(100, self.update_elided_title)

        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_context_menu)

    def show_context_menu(self, pos: QPoint):
        if not self._valid:
            return

        menu = QMenu(self)

        play_action = QAction("播放", self)
        play_action.triggered.connect(self.on_play)
        menu.addAction(play_action)

        delete_action = QAction("删除", self)
        delete_action.triggered.connect(self.on_delete)
        menu.addAction(delete_action)

        global_pos = self.mapToGlobal(pos)
        menu.exec(global_pos)

    def on_play(self):
        self.downloader.stream_with_potplayer(self.item_data['url'], self.item_data['name'])

    def on_delete(self):
        reply = QMessageBox.question(
            self,
            "确认删除",
            f"确定删除《{self.item_data['name']}》吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.downloader.task_signal.emit("delete", self.item_data['id'])

    def update_elided_title(self):
        if not self._valid:
            return
        try:
            fm = QFontMetrics(self.title_label.font())
            elided = fm.elidedText(self.original_title, Qt.TextElideMode.ElideRight, self.title_label.width() - 16)
            self.title_label.setText(elided)
        except RuntimeError:
            pass

    def load_image(self, url: str):
        if not url:
            self.pic_label.setText("无封面")
            return
        match = re.search(r'fourhoi\.com/([^/]+)/cover-n\.jpg', url)
        if not match:
            self.pic_label.setText("无效URL")
            return
        pic_name = match.group(1)
        cache_path = self.downloader.pic_cache_dir / f"{pic_name}.jpg"

        if cache_path.exists():
            pixmap = QPixmap(str(cache_path))
            if not pixmap.isNull():
                self.set_pixmap_safe(pixmap)
                return

        request = QNetworkRequest(QUrl(url))
        request.setAttribute(QNetworkRequest.Attribute.RedirectPolicyAttribute, True)
        reply = self.downloader.network_manager.get(request)
        reply.finished.connect(lambda r=reply: self.on_image_finished(r, cache_path))

    def on_image_finished(self, reply: QNetworkReply, cache_path: Path):
        if not self._valid:
            reply.deleteLater()
            return
        try:
            if reply.error() == QNetworkReply.NetworkError.NoError:
                data = reply.readAll()
                pixmap = QPixmap()
                if pixmap.loadFromData(data) and not pixmap.isNull():
                    pixmap.save(str(cache_path), "JPG", quality=90)
                    self.set_pixmap_safe(pixmap)
                else:
                    self.pic_label.setText("加载失败")
            else:
                self.pic_label.setText("网络错误")
        except RuntimeError:
            pass
        finally:
            reply.deleteLater()

    def set_pixmap_safe(self, pixmap: QPixmap):
        try:
            if self._valid and self.pic_label:
                scaled = pixmap.scaled(200, 134, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                                       Qt.TransformationMode.SmoothTransformation)
                cropped = scaled.copy((scaled.width() - 200) // 2, (scaled.height() - 134) // 2, 200, 134)
                self.pic_label.setPixmap(cropped)
        except RuntimeError:
            pass


class JSONStore:
    def __init__(self, filepath: str):
        self.filepath = filepath
        self.lock = threading.RLock()
        self._data: List[Dict[str, Any]] = []
        self._load()

    def _load(self):
        with self.lock:
            path = Path(self.filepath)
            if not path.exists():
                self._data = []
                self._save()
                return

            try:
                with open(self.filepath, "r", encoding="utf-8") as f:
                    raw = json.load(f)
            except (FileNotFoundError, json.JSONDecodeError):
                return

            cleaned = []
            for item in raw:
                try:
                    save_name = item.get("name", "未命名视频")
                    save_name = sanitize_filename(save_name)
                    cleaned.append({
                        "id": int(item.get("id", 0)),
                        "url": str(item.get("url", "")).strip(),
                        "name": save_name,
                        "pic": item.get("pic") or generate_pic_url(save_name),
                        "status": str(item.get("status", "待下载"))
                    })
                except:
                    continue

            valid_items = [x for x in cleaned if x["id"] > 0]
            valid_items.sort(key=lambda x: x["id"])

            self._data = valid_items
            if len(self._data) != len(raw):
                self._save()

    def check_id_continuity(self) -> tuple[bool, int]:
        with self.lock:
            if not self._data:
                return True, 0

            ids = sorted(item["id"] for item in self._data)
            max_id = ids[-1]
            expected = set(range(1, max_id + 1))
            actual = set(ids)
            is_continuous = (len(ids) == max_id) and (actual == expected)
            return is_continuous, max_id

    def renumber_ids(self) -> List[Dict[str, Any]]:
        with self.lock:
            new_data = []
            for new_id, item in enumerate(self._data, start=1):
                item = item.copy()
                item["id"] = new_id
                new_data.append(item)
            self._data = new_data
            self._save()
            return new_data

    def _save(self):
        with self.lock:
            with open(self.filepath, "w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False, indent=2)

    def get_all(self) -> List[Dict[str, Any]]:
        with self.lock:
            return list(self._data)

    def get_by_id(self, item_id: int) -> Optional[Dict[str, Any]]:
        with self.lock:
            for item in self._data:
                if item.get("id") == item_id:
                    return item.copy()
            return None

    def add(self, item: Dict[str, Any]) -> List[Dict[str, Any]]:
        with self.lock:
            self._data.append(item)
            self._save()
            return list(self._data)

    def update(self, item_id: int, **kwargs) -> List[Dict[str, Any]]:
        with self.lock:
            for entry in self._data:
                if entry.get("id") == item_id:
                    for k, v in kwargs.items():
                        if k in ["url", "name", "status"]:
                            entry[k] = v
            self._save()
            return list(self._data)

    def update_by_status(
            self,
            preserve_statuses: Optional[str | List[str]],
            new_status: str
    ) -> List[Dict[str, Any]]:
        with self.lock:
            if self._data:
                changed = False
                if preserve_statuses is None:
                    preserve_set = set()
                elif isinstance(preserve_statuses, str):
                    preserve_set = {preserve_statuses}
                else:
                    preserve_set = set(preserve_statuses)

                for entry in self._data:
                    current_status = entry.get("status")
                    if current_status in preserve_set:
                        continue
                    if current_status != new_status:
                        entry["status"] = new_status
                        changed = True

                if changed:
                    self._save()

            return list(self._data)

    def delete(self, item_id: int) -> List[Dict[str, Any]]:
        with self.lock:
            self._data = [entry for entry in self._data if entry.get("id") != item_id]
            self._save()
            return list(self._data)

    def delete_by_status(self, status: str) -> List[Dict[str, Any]]:
        with self.lock:
            self._data = [entry for entry in self._data if entry.get("status") != status]
            self._save()
            return list(self._data)


class M3U8Downloader(QMainWindow):
    task_signal = Signal(str, int)
    api_add_task_signal = Signal(str, str, str)
    download_signal = Signal(str, int)
    refresh_signal = Signal()

    def __init__(self):
        super().__init__()

        self.setWindowTitle("N_m3u8DL-RE 下载工具")
        self.setWindowIcon(QIcon(":/icons/resources/icon.ico"))
        self.setGeometry(100, 100, 1110, 720)

        self.network_manager = QNetworkAccessManager(self)

        self.input_widget = None

        self.log_dict = {0: deque(maxlen=1000)}

        self.match_rows = []
        self.current_match_index = -1

        self.current_item_id = 0

        self.log_refresh_timer = QTimer(self)
        self.log_refresh_timer.setInterval(100)
        self.log_refresh_timer.timeout.connect(self.update_log_display)

        self.config_file = Path("config.yaml")
        self.config = {}

        self.load_config()

        self.auth_key = self.config.get('auth_key', "")
        self.port = self.config.get('port', "8088")
        self.tmp_dir = self.config.get('tmp_dir', "D:/")
        self.save_dir = self.config.get('save_dir', "E:/")
        self.exe_path = self.config.get('exe_path', "")
        self.ffmpeg_path = self.config.get('ffmpeg_path', "")
        self.thread_count = self.config.get('thread_count', "32")
        self.max_speed = self.config.get('max_speed', "")
        self.use_system_proxy = self.config.get('use_system_proxy', True)
        self.max_concurrency = self.config.get('max_concurrency', "3")
        self.m3u8_file = self.config.get('m3u8_file', "m3u8.json")
        self.potplayer_path = self.config.get('potplayer_path', "")

        json_path = Path(self.m3u8_file).resolve()
        self.pic_cache_dir = json_path.parent / "Tmp" / f"{json_path.stem}_pic"

        self.json_store = JSONStore(self.m3u8_file)

        self.downloads_data = self.json_store.get_all()

        self.running_downloads = dict()

        self.pending_downloads = deque()

        self.task_signal.connect(self.handle_task_signal, type=Qt.ConnectionType.QueuedConnection)
        self.download_signal.connect(self.handle_download_signal, type=Qt.ConnectionType.QueuedConnection)
        self.refresh_signal.connect(self.build_download_list, type=Qt.ConnectionType.QueuedConnection)

        self.api_add_task_signal.connect(self.save_download_info, type=Qt.ConnectionType.QueuedConnection)

        self.task_lock = threading.Lock()

        self.edit_mode = False
        self.cards: List[VideoCard] = []
        self.card_by_url: Dict[str, VideoCard] = {}
        self.visible_card_ids: List[int] = []

        self._last_columns: Optional[int] = None
        self.scroll_area = None
        self.cards_widget = None
        self.cards_layout = None

        self.create_widgets()
        self.build_download_list()
        self.update_button_states()

        QTimer.singleShot(0, self.adjust_column_widths)

    def load_config(self):
        if self.config_file.exists():
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    loaded = yaml.safe_load(f) or {}
                self.config = loaded
            except Exception as ex:
                QMessageBox.warning(self, "配置加载错误", f"读取 config.yaml 失败\n错误: {ex}")

    def create_widgets(self):
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setSpacing(5)

        input_widget = QWidget(self)
        input_layout = QVBoxLayout(input_widget)

        exe_ffmpeg_layout = QHBoxLayout()

        n_m3u8dl_re_label = QLabel("N_m3u8DL-RE:")
        n_m3u8dl_re_label.setMinimumWidth(100)
        exe_ffmpeg_layout.addWidget(n_m3u8dl_re_label)

        self.exe_entry = QLineEdit(self.exe_path)
        exe_ffmpeg_layout.addWidget(self.exe_entry, 7)
        exe_button = QPushButton("选择m3u8DL")
        exe_button.clicked.connect(self.choose_exe_path)
        exe_ffmpeg_layout.addWidget(exe_button, 3)

        ffmpeg_label = QLabel("FFmpeg:")
        ffmpeg_label.setMinimumWidth(100)
        exe_ffmpeg_layout.addWidget(ffmpeg_label)

        self.ffmpeg_entry = QLineEdit(self.ffmpeg_path)
        exe_ffmpeg_layout.addWidget(self.ffmpeg_entry, 7)
        ffmpeg_button = QPushButton("选择FFmpeg")
        ffmpeg_button.clicked.connect(self.choose_ffmpeg_path)
        exe_ffmpeg_layout.addWidget(ffmpeg_button, 3)
        input_layout.addLayout(exe_ffmpeg_layout)

        tmp_save_layout = QHBoxLayout()

        tmp_dir_label = QLabel("临时文件目录:")
        tmp_dir_label.setMinimumWidth(100)
        tmp_save_layout.addWidget(tmp_dir_label)

        self.tmp_entry = QLineEdit(self.tmp_dir)
        tmp_save_layout.addWidget(self.tmp_entry, 7)
        tmp_button = QPushButton("选择临时目录")
        tmp_button.clicked.connect(self.choose_tmp_dir)
        tmp_save_layout.addWidget(tmp_button, 3)

        save_dir_label = QLabel("保存文件目录:")
        save_dir_label.setMinimumWidth(100)
        tmp_save_layout.addWidget(save_dir_label)

        self.save_entry = QLineEdit(self.save_dir)
        tmp_save_layout.addWidget(self.save_entry, 7)
        save_button = QPushButton("选择保存目录")
        save_button.clicked.connect(self.choose_save_dir)
        tmp_save_layout.addWidget(save_button, 3)
        input_layout.addLayout(tmp_save_layout)

        m3u8_url_layout = QHBoxLayout()

        m3u8_dir_label = QLabel("JSON文件:")
        m3u8_dir_label.setMinimumWidth(100)
        m3u8_url_layout.addWidget(m3u8_dir_label)

        self.m3u8_entry = QLineEdit(self.m3u8_file)
        self.m3u8_entry.setReadOnly(True)
        m3u8_url_layout.addWidget(self.m3u8_entry, 7)
        m3u8_button = QPushButton("选择JSON文件")
        m3u8_button.clicked.connect(self.choose_json_file)
        m3u8_url_layout.addWidget(m3u8_button, 3)

        m3u8_dir_label = QLabel("PotPlayer:")
        m3u8_dir_label.setMinimumWidth(100)
        m3u8_url_layout.addWidget(m3u8_dir_label)

        self.potplayer_entry = QLineEdit(self.potplayer_path)

        m3u8_url_layout.addWidget(self.potplayer_entry, 7)
        potplayer_button = QPushButton("选择PotPlayer")
        potplayer_button.clicked.connect(self.choose_potplayer_path)
        m3u8_url_layout.addWidget(potplayer_button, 3)

        input_layout.addLayout(m3u8_url_layout)

        name_pic_layout = QHBoxLayout()

        m3u8_link_label = QLabel("M3U8链接:")
        m3u8_link_label.setMinimumWidth(100)
        name_pic_layout.addWidget(m3u8_link_label)

        self.url_entry = QLineEdit()
        name_pic_layout.addWidget(self.url_entry)

        pic_link_label = QLabel("pic链接:")
        pic_link_label.setMinimumWidth(100)
        name_pic_layout.addWidget(pic_link_label)

        self.pic_entry = QLineEdit()
        name_pic_layout.addWidget(self.pic_entry)

        save_name_label = QLabel("保存文件名:")
        save_name_label.setMinimumWidth(100)
        name_pic_layout.addWidget(save_name_label)

        self.save_name_entry = QLineEdit()
        name_pic_layout.addWidget(self.save_name_entry)
        input_layout.addLayout(name_pic_layout)

        auth_port_layout = QHBoxLayout()

        auth_key_label = QLabel("认证口令:")
        auth_key_label.setMinimumWidth(100)
        auth_port_layout.addWidget(auth_key_label)

        self.auth_entry = QLineEdit(self.auth_key)
        self.auth_entry.textChanged.connect(self.update_auth_key)
        auth_port_layout.addWidget(self.auth_entry)

        port_label = QLabel("服务端口:")
        port_label.setMinimumWidth(100)
        auth_port_layout.addWidget(port_label)

        self.port_entry = QLineEdit(str(self.port))
        self.port_entry.textChanged.connect(self.update_port)
        auth_port_layout.addWidget(self.port_entry)

        thread_count_label = QLabel("下载线程数:")
        thread_count_label.setMinimumWidth(100)
        auth_port_layout.addWidget(thread_count_label)

        self.thread_entry = QLineEdit(str(self.thread_count))
        self.thread_entry.textChanged.connect(self.update_thread_count)
        auth_port_layout.addWidget(self.thread_entry)

        input_layout.addLayout(auth_port_layout)

        thread_count_label_layout = QHBoxLayout()

        max_speed_label = QLabel("下载限速(非实时):")
        max_speed_label.setMinimumWidth(100)
        thread_count_label_layout.addWidget(max_speed_label)

        self.speed_entry = QLineEdit(str(self.max_speed))
        self.speed_entry.textChanged.connect(self.update_max_speed)
        thread_count_label_layout.addWidget(self.speed_entry)

        max_concurrency_label = QLabel("最大并发数:")
        max_concurrency_label.setMinimumWidth(100)
        thread_count_label_layout.addWidget(max_concurrency_label)

        self.concurrency_entry = QLineEdit(self.max_concurrency)
        self.concurrency_entry.textChanged.connect(self.update_max_concurrency)
        thread_count_label_layout.addWidget(self.concurrency_entry)

        system_proxy_label = QLabel("是否系统代理:")
        system_proxy_label.setMinimumWidth(100)
        thread_count_label_layout.addWidget(system_proxy_label)

        self.proxy_entry = QLineEdit(str(self.use_system_proxy))
        self.proxy_entry.textChanged.connect(self.update_use_system_proxy)
        thread_count_label_layout.addWidget(self.proxy_entry)
        input_layout.addLayout(thread_count_label_layout)

        self.input_widget = input_widget

        main_layout.addWidget(input_widget)

        button_layout = QHBoxLayout()
        button_layout.setContentsMargins(10, 0, 10, 0)

        action_label = QLabel("操作:")
        action_label.setMinimumWidth(100)
        button_layout.addWidget(action_label)

        button_layout.addStretch(5)

        self.search_entry = QLineEdit()
        self.search_entry.setPlaceholderText("实时搜索")
        self.search_entry.textChanged.connect(self.on_search_changed)
        button_layout.addWidget(self.search_entry)

        self.save_button_main = QPushButton("保存链接")
        self.save_button_main.clicked.connect(self.save_download)
        button_layout.addWidget(self.save_button_main)
        button_layout.addStretch()

        self.save_config_button = QPushButton("保存配置")
        self.save_config_button.clicked.connect(self.save_config)
        button_layout.addWidget(self.save_config_button)
        button_layout.addStretch()

        self.download_all_button = QPushButton("下载全部")
        self.download_all_button.clicked.connect(self.download_all)
        button_layout.addWidget(self.download_all_button)
        button_layout.addStretch()

        self.stop_all_button = QPushButton("全部停止")
        self.stop_all_button.clicked.connect(self.stop_all)
        button_layout.addWidget(self.stop_all_button)
        button_layout.addStretch()

        self.kill_all_button = QPushButton("杀死进程")
        self.kill_all_button.clicked.connect(self.kill_all)
        button_layout.addWidget(self.kill_all_button)
        button_layout.addStretch()

        self.delete_completed_button = QPushButton("删除已完成")
        self.delete_completed_button.clicked.connect(self.delete_completed)
        button_layout.addWidget(self.delete_completed_button)
        button_layout.addStretch()

        self.view_log_button = QPushButton("日志")
        self.view_log_button.clicked.connect(lambda: self.view_item_log(0))
        button_layout.addWidget(self.view_log_button)
        button_layout.addStretch()

        self.edit_mode_button = QPushButton("编辑模式")
        self.edit_mode_button.setCheckable(True)
        self.edit_mode_button.clicked.connect(self.toggle_edit_mode)
        button_layout.addWidget(self.edit_mode_button)
        button_layout.addStretch()

        main_layout.addLayout(button_layout)

        self.downloads_table = QTableWidget()
        self.downloads_table.setColumnCount(5)
        self.downloads_table.setHorizontalHeaderLabels(["ID", "保存文件名", "URL", "状态", "操作"])
        header = self.downloads_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setMinimumSectionSize(30)
        self.downloads_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.downloads_table.verticalHeader().setVisible(False)
        main_layout.addWidget(self.downloads_table, stretch=1)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setVisible(False)

        self.cards_widget = QWidget(self)
        self.cards_layout = QGridLayout(self.cards_widget)
        self.cards_layout.setSpacing(15)
        self.cards_layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.scroll_area.setWidget(self.cards_widget)
        main_layout.addWidget(self.scroll_area, stretch=1)

        self.download_log = QTextEdit()
        self.download_log.setReadOnly(True)
        main_layout.addWidget(self.download_log, stretch=1)
        main_layout.addStretch(0)

    def toggle_edit_mode(self):
        self.edit_mode = self.edit_mode_button.isChecked()
        self.edit_mode_button.setText("表格模式" if self.edit_mode else "编辑模式")

        self.downloads_table.setVisible(not self.edit_mode)

        self.download_log.setVisible(not self.edit_mode)

        self.scroll_area.setVisible(self.edit_mode)

        if self.input_widget:
            self.input_widget.setVisible(not self.edit_mode)

        if self.edit_mode:
            self.pic_cache_dir.mkdir(exist_ok=True, parents=True)
            self.build_cards_view()
        else:
            for i in reversed(range(self.cards_layout.count())):
                layout_item = self.cards_layout.takeAt(i)
                if layout_item.widget():
                    layout_item.widget().hide()

        self.on_search_changed(self.search_entry.text())

    def build_cards_view(self):
        if not self.edit_mode:
            return

        current_urls = {item['url'] for item in self.downloads_data}

        to_remove = [url for url in list(self.card_by_url.keys()) if url not in current_urls]
        for url in to_remove:
            card = self.card_by_url.pop(url)
            card._valid = False
            card.hide()
            card.setParent(None)
            card.deleteLater()
            if card in self.cards:
                self.cards.remove(card)

        for item in self.downloads_data:
            url = item['url']
            if url not in self.card_by_url:
                card = VideoCard(item, self)
                self.cards.append(card)
                self.card_by_url[url] = card
            else:
                card = self.card_by_url[url]
                card.item_data = item
                card.original_title = item['name']
                card.load_image(item['pic'])
                QTimer.singleShot(100, card.update_elided_title)

        self.update_visible_cards_and_rearrange()

    def update_visible_cards_and_rearrange(self):
        if not self.edit_mode:
            return

        keyword = self.search_entry.text().strip().lower()

        if not keyword:
            self.visible_card_ids = [item['id'] for item in self.downloads_data]
        else:
            self.visible_card_ids = [
                item['id'] for item in self.downloads_data
                if keyword in item['name'].lower() or keyword in item['url'].lower()
            ]

        for i in reversed(range(self.cards_layout.count())):
            layout_item = self.cards_layout.takeAt(i)
            if layout_item.widget():
                layout_item.widget().hide()

        columns = max(4, self.width() // 215)
        self._last_columns = columns

        for index, item_id in enumerate(self.visible_card_ids):
            item = next((it for it in self.downloads_data if it['id'] == item_id), None)
            if item:
                card = self.card_by_url.get(item['url'])
                if card:
                    card.show()
                    row = index // columns
                    col = index % columns
                    self.cards_layout.addWidget(card, row, col)

    def rearrange_cards(self):
        if not self.edit_mode or not self.visible_card_ids:
            return

        new_columns = max(4, self.width() // 215)
        if self._last_columns == new_columns:
            return
        self._last_columns = new_columns
        self.update_visible_cards_and_rearrange()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.adjust_column_widths()
        if self.edit_mode:
            self.rearrange_cards()

    def adjust_column_widths(self):
        table_width = self.downloads_table.width() - 15
        if table_width <= 0:
            table_width = self.width() - 15
        header = self.downloads_table.horizontalHeader()
        header.resizeSection(0, max(30, int(table_width * 0.04)))
        header.resizeSection(1, max(100, int(table_width * 0.30)))
        header.resizeSection(2, max(100, int(table_width * 0.30)))
        header.resizeSection(3, max(50, int(table_width * 0.06)))
        header.resizeSection(4, max(200, int(table_width * 0.30)))

    def update_button_states(self):
        is_exe_valid = bool(self.exe_path and Path(self.exe_path).exists())
        is_ffmpeg_valid = bool(self.ffmpeg_path and Path(self.ffmpeg_path).exists())
        is_valid = is_exe_valid and is_ffmpeg_valid
        self.download_all_button.setEnabled(is_valid)
        self.delete_completed_button.setEnabled(is_valid)
        self.stop_all_button.setEnabled(is_valid)
        for row in range(self.downloads_table.rowCount()):
            actions_widget = self.downloads_table.cellWidget(row, 4)
            if actions_widget:
                for btn in actions_widget.findChildren(QPushButton):
                    btn.setEnabled(is_valid)

    def build_download_list(self):
        self.downloads_table.setRowCount(len(self.downloads_data))
        for row_idx, item in enumerate(self.downloads_data):
            id_item = QTableWidgetItem(str(item['id']))
            id_item.setTextAlignment(Qt.AlignmentFlag.AlignRight)
            self.downloads_table.setItem(row_idx, 0, id_item)

            self.downloads_table.setItem(row_idx, 1, QTableWidgetItem(item['name']))
            self.downloads_table.setItem(row_idx, 2, QTableWidgetItem(item['url']))

            status_item = QTableWidgetItem(item['status'])
            status_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.downloads_table.setItem(row_idx, 3, status_item)

            actions_widget = QWidget(self)
            actions_layout = QHBoxLayout(actions_widget)
            actions_layout.setContentsMargins(2, 2, 2, 2)
            actions_layout.setSpacing(2)

            download_btn = QPushButton("下载")
            download_btn.setMinimumWidth(60)
            download_btn.clicked.connect(lambda _, rid=item['id']: self.task_signal.emit("add", rid))
            actions_layout.addWidget(download_btn)

            stop_btn = QPushButton("停止")
            stop_btn.setMinimumWidth(60)
            stop_btn.clicked.connect(lambda _, rid=item['id']: self.task_signal.emit("remove", rid))
            actions_layout.addWidget(stop_btn)

            delete_btn = QPushButton("删除")
            delete_btn.setMinimumWidth(60)
            delete_btn.clicked.connect(lambda _, rid=item['id']: self.task_signal.emit("delete", rid))
            actions_layout.addWidget(delete_btn)

            log_btn = QPushButton("日志")
            log_btn.setMinimumWidth(60)
            log_btn.clicked.connect(lambda _, rid=item['id']: self.view_item_log(rid))
            actions_layout.addWidget(log_btn)

            stream_btn = QPushButton("播放")
            stream_btn.setMinimumWidth(60)
            stream_btn.clicked.connect(lambda _, url=item['url'], name=item['name']:
                                       self.stream_with_potplayer(url, name))
            actions_layout.addWidget(stream_btn)

            self.downloads_table.setCellWidget(row_idx, 4, actions_widget)

        self.downloads_table.resizeColumnToContents(0)
        self.downloads_table.resizeColumnToContents(3)
        self.update_button_states()
        self.adjust_column_widths()

        if self.edit_mode:
            self.build_cards_view()

    def update_auth_key(self, text):
        self.auth_key = text

    def update_thread_count(self, text):
        self.thread_count = text

    def update_max_speed(self, text):
        self.max_speed = text

    def update_port(self, text):
        self.port = text

    def update_max_concurrency(self, text):
        self.max_concurrency = text

    def update_use_system_proxy(self, text):
        self.use_system_proxy = text

    def choose_exe_path(self):
        path = QFileDialog.getOpenFileName(self, "选择 N_m3u8DL-RE.exe", "", "可执行文件 (*.exe)")[0]
        if path:
            self.exe_path = path
            self.exe_entry.setText(self.exe_path)
            self.update_button_states()

    def choose_potplayer_path(self):
        path = QFileDialog.getOpenFileName(self, "选择 PotPlayer.exe", "", "可执行文件 (*.exe)")[0]
        if path:
            self.potplayer_path = path
            self.potplayer_entry.setText(self.potplayer_path)
            self.update_button_states()

    def choose_ffmpeg_path(self):
        path = QFileDialog.getOpenFileName(self, "选择 FFmpeg 可执行文件", "", "可执行文件 (*.exe)")[0]
        if path:
            self.ffmpeg_path = path
            self.ffmpeg_entry.setText(self.ffmpeg_path)
            self.update_button_states()

    def choose_tmp_dir(self):
        directory = QFileDialog.getExistingDirectory(self, "选择临时目录")
        if directory:
            self.tmp_dir = directory
            self.tmp_entry.setText(self.tmp_dir)

    def choose_save_dir(self):
        directory = QFileDialog.getExistingDirectory(self, "选择保存目录")
        if directory:
            self.save_dir = directory
            self.save_entry.setText(self.save_dir)

    def choose_json_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "选择新的JSON文件",
            self.m3u8_file,
            "JSON Files (*.json);;All Files (*)"
        )

        if not file_path:
            return

        if not file_path.lower().endswith('.json'):
            file_path += '.json'

        if file_path == self.m3u8_file:
            return

        try:
            temp_store = JSONStore(file_path)
            is_continuous, max_id = temp_store.check_id_continuity()

            if not is_continuous and temp_store._data:
                reply = QMessageBox.question(
                    self,
                    "ID 不连续检测",
                    f"检测到任务 ID 不连续（当前最大 ID: {max_id}，任务数: {len(temp_store._data)}）\n\n"
                    f"是否重新整理为从 1 开始的连续 ID？\n"
                    f"（推荐点击“是”，可避免潜在的 ID 冲突问题）",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.Yes
                )
                if reply == QMessageBox.StandardButton.Yes:
                    temp_store.renumber_ids()
                    QMessageBox.information(self, "ID 已修复", "任务 ID 已重新整理为连续自增（从 1 开始）")

            self.m3u8_file = file_path
            self.m3u8_entry.setText(file_path)

            self.json_store = temp_store

            json_path = Path(file_path).resolve()
            self.pic_cache_dir = json_path.parent / "Tmp" / f"{json_path.stem}_pic"
            self.pic_cache_dir.mkdir(exist_ok=True, parents=True)

        except Exception as e:
            QMessageBox.critical(self, "错误", f"无法打开/创建文件：\n{file_path}\n\n{e}")
            return

        self.downloads_data = self.json_store.get_all()

        self.refresh_signal.emit()

    def on_search_changed(self, text):
        keyword = text.strip().lower()
        self.match_rows = []

        table = self.downloads_table
        for row in range(table.rowCount()):
            name_item = table.item(row, 1)
            url_item = table.item(row, 2)

            name_text = (name_item.text() if name_item else "").lower()
            url_text = (url_item.text() if url_item else "").lower()

            matched = keyword in name_text or keyword in url_text

            table.setRowHidden(row, not matched)

            if matched:
                self.match_rows.append(row)

                for col in range(table.columnCount()):
                    item = table.item(row, col)
                    if item:
                        item.setBackground(QColor("#263850") if keyword else Qt.GlobalColor.transparent)

        if self.match_rows:
            first_row = self.match_rows[0]
            table.scrollToItem(table.item(first_row, 0))
            table.selectRow(first_row)
            self.current_match_index = 0
        else:
            self.current_match_index = -1

        if self.edit_mode:
            self.update_visible_cards_and_rearrange()

    def stream_with_potplayer(self, m3u8_url: str, video_name: str = ""):
        if not m3u8_url.strip():
            QMessageBox.warning(self, "播放失败", "URL 为空，无法播放")
            return

        potplayer_exe = self.potplayer_path
        if not potplayer_exe:
            return

        title = video_name.strip() or "m3u8 在线播放"

        pot_url = f'{potplayer_exe} "{m3u8_url}" /title="{title}" '

        try:
            subprocess.Popen(pot_url, creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | 0x00000008)
            self.log_dict.setdefault(0, deque(maxlen=1000)).append(
                f"PotPlayer 播放 → {title}"
            )
            self.update_log_display()
        except Exception as e:
            QMessageBox.critical(self, "播放失败", f"无法启动 PotPlayer：\n{e}")

    def view_item_log(self, item_id):
        self.current_item_id = item_id
        self.update_log_display()

    def update_log_display(self):
        self.download_log.clear()
        if self.current_item_id == 0:
            if 0 in self.log_dict:
                for log in self.log_dict[0]:
                    self.download_log.append(log)
            for item in self.downloads_data:
                item_id = item['id']
                if item_id != 0 and item_id in self.log_dict and self.log_dict[item_id]:
                    self.download_log.append(self.log_dict[item_id][-1])
        else:
            log_deque = self.log_dict.get(self.current_item_id, deque(maxlen=1000))
            for log in log_deque:
                self.download_log.append(log)

    def save_config(self):
        self.config['auth_key'] = self.auth_key
        self.config['port'] = self.port
        self.config['tmp_dir'] = self.tmp_dir
        self.config['save_dir'] = self.save_dir
        self.config['exe_path'] = self.exe_path
        self.config['ffmpeg_path'] = self.ffmpeg_path
        self.config['thread_count'] = self.thread_count
        self.config['max_speed'] = self.max_speed
        self.config['use_system_proxy'] = self.use_system_proxy
        self.config['max_concurrency'] = self.max_concurrency
        self.config['m3u8_file'] = self.m3u8_file
        self.config['potplayer_path'] = self.potplayer_path

        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                yaml.safe_dump(self.config, f, allow_unicode=True, sort_keys=False)
            QMessageBox.information(self, "保存配置", "配置已保存到 config.yaml")
        except Exception as e:
            QMessageBox.critical(self, "保存失败", f"无法写入 config.yaml\n错误: {e}")

    def is_m3u8_url(self, url):
        is_m3u8 = bool(re.match(r'^(https?|ftp)://[^\s/$.?#].[^\s]*\.m3u8$', url, re.IGNORECASE))
        if not is_m3u8:
            self.log_dict.setdefault(0, deque(maxlen=1000)).append(f"接收到非m3u8链接:  {url}")
        return is_m3u8

    def get_command(self, url, save_name):
        cmd_parts = [
            f"\"{self.exe_path}\"",
            f"\"{url}\"",
            f"--save-name \"{save_name}\"",
            f"--tmp-dir \"{self.tmp_dir}\"",
            f"--save-dir \"{self.save_dir}\"",
            f"--ffmpeg-binary-path \"{self.ffmpeg_path}\"",
            "--check-segments-count false",
            "--no-log",
            "--header \"User-Agent:Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36\"",
        ]
        optional_args = {
            "--max-speed": self.max_speed,
            "--thread-count": self.thread_count,
            "--use-system-proxy": self.use_system_proxy,
        }
        for key, value in optional_args.items():
            if value:
                cmd_parts.append(f"{key} {value}")
        return " ".join(cmd_parts)

    def save_download(self):
        url = self.url_entry.text().strip()
        name = self.save_name_entry.text().strip()
        pic = self.pic_entry.text().strip()

        if not url or not name:
            QMessageBox.critical(self, "错误", "请输入有效的 URL 和保存文件名。")
            return

        if self.is_m3u8_url(url):
            QMessageBox.critical(self, "错误", "请输入正确的 m3u8 URL。")
            return

        if any(item['url'] == url for item in self.downloads_data):
            QMessageBox.critical(self, "错误", "输入的 URL 已存在。")
            return

        self.save_download_info(url, name, pic)

    def save_download_info(self, url, name, custom_pic=None):
        save_name = sanitize_filename(name)

        if custom_pic and custom_pic.strip():
            pic_url = custom_pic.strip()
        else:
            pic_url = generate_pic_url(save_name)

        new_id = max((item['id'] for item in self.downloads_data), default=0) + 1

        self.downloads_data = self.json_store.add({
            'id': new_id,
            'url': url,
            'name': save_name,
            'pic': pic_url,
            'status': '待下载'
        })

        self.url_entry.clear()
        self.save_name_entry.clear()
        self.pic_entry.clear()
        self.refresh_signal.emit()

    def delete_completed(self):
        self.downloads_data = self.json_store.delete_by_status("已完成")
        self.build_download_list()

    def kill_all(self):
        try:
            subprocess.run(
                "taskkill /F /IM N_m3u8DL-RE.exe",
                shell=True,
                capture_output=True,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW)
            self.log_dict.setdefault(0, deque(maxlen=1000)).append(
                f"杀死 N_m3u8DL-RE.exe 进程 成功"
            )
        except Exception as e:
            self.log_dict.setdefault(0, deque(maxlen=1000)).append(
                f"杀死 N_m3u8DL-RE.exe 进程 失败:→ {e}"
            )

    def stop_all(self):
        self.task_signal.emit("removeAll", 0)

    def download_all(self):
        self.task_signal.emit("addAll", 0)

    def handle_task_signal(self, operation, item_id):
        with self.task_lock:
            if operation == "add":
                if item_id not in self.pending_downloads and item_id not in self.running_downloads:
                    item = self.json_store.get_by_id(item_id)
                    if item['status'] in ['待下载', '已停止', '失败']:
                        self.pending_downloads.append(item_id)
                        self.downloads_data = self.json_store.update(item_id, status="待下载")

            if operation == "addAll":
                self.downloads_data = self.json_store.update_by_status(["已完成", "下载中"], "待下载")
                for item in self.downloads_data:
                    if item['status'] == '待下载':
                        self.pending_downloads.append(item['id'])

            elif operation == "delete":
                if item_id in self.pending_downloads:
                    self.pending_downloads.remove(item_id)
                elif item_id in self.running_downloads:
                    self.download_signal.emit("stop", item_id)
                    self.log_dict.pop(item_id, None)

                if item_id in self.log_dict:
                    del self.log_dict[item_id]

                self.downloads_data = self.json_store.delete(item_id)

            elif operation == "removeAll":
                self.pending_downloads.clear()
                for item_id, process in list(self.running_downloads.items()):
                    if process is not None:
                        try:
                            subprocess.run(f"taskkill /PID {process.pid} /F /T", shell=True, check=False,
                                           creationflags=subprocess.CREATE_NO_WINDOW)
                            self.log_dict.setdefault(item_id, deque(maxlen=1000)).append(
                                f"[任务 {item_id}] 已强制停止（全部停止）")
                        except Exception as e:
                            self.log_dict.setdefault(item_id, deque(maxlen=1000)).append(
                                f"[任务 {item_id}] 停止失败: {e}")
                    self.running_downloads.pop(item_id, None)
                self.downloads_data = self.json_store.update_by_status(["已完成"], "已停止")
                self.refresh_signal.emit()
                self.log_refresh_timer.stop()

            elif operation == "remove":
                if item_id in self.pending_downloads:
                    self.pending_downloads.remove(item_id)
                    self.downloads_data = self.json_store.update(item_id, status="已停止")
                elif item_id in self.running_downloads:
                    self.download_signal.emit("stop", item_id)
                else:
                    self.downloads_data = self.json_store.update(item_id, status="已停止")
            elif operation in ["已完成", "失败", "已停止"]:
                if item_id in self.running_downloads:
                    self.running_downloads.pop(item_id)
                    self.downloads_data = self.json_store.update(item_id, status=operation)

            self.build_download_list()

            while self.pending_downloads and len(self.running_downloads) < int(self.max_concurrency):
                item_id = self.pending_downloads.popleft()
                self.running_downloads[item_id] = None
                self.log_dict.setdefault(item_id, deque(maxlen=1000))
                self.download_signal.emit("start", item_id)

    def handle_download_signal(self, operation, item_id):
        if operation == "start":
            self.start_download(item_id)
            self.log_dict.get(0, deque(maxlen=1000)).append(f"任务{item_id} 正在开始下载")
        elif operation == "stop":
            self.log_dict.get(0, deque(maxlen=1000)).append(f"任务{item_id} 正在停止下载")
            self.stop_download(item_id)
            self.json_store.update(item_id, status="已停止")
            self.build_download_list()
        self.view_item_log(0)
        if len(self.running_downloads) != 0 or len(self.pending_downloads) != 0:
            self.log_refresh_timer.start()
        else:
            self.log_refresh_timer.stop()

    def stop_download(self, item_id):
        if item_id not in self.running_downloads:
            log_deque = self.log_dict.get(item_id, deque(maxlen=1000))
            log_deque.append(f"[任务 {item_id}] 未找到运行中的进程")
            return
        process = self.running_downloads[item_id]
        try:
            subprocess.run(f"taskkill /PID {process.pid} /F /T", shell=True, check=False,
                           creationflags=subprocess.CREATE_NO_WINDOW)
            log_deque = self.log_dict.get(item_id, deque(maxlen=1000))
            log_deque.append(f"[任务 {item_id}] 已成功停止")
        except Exception as e:
            log_deque = self.log_dict.get(item_id, deque(maxlen=1000))
            log_deque.append(f"[任务 {item_id}] 停止失败: {str(e)}")
        finally:
            self.running_downloads.pop(item_id)

    def start_download(self, item_id):
        def download_task():
            item = self.json_store.get_by_id(item_id)

            command = self.get_command(item.get("url"), item.get("name"))

            log_deque = self.log_dict.get(item_id, deque(maxlen=1000))
            log_deque.append(f"[任务 {item_id}] 开始 下载: {command}")
            self.json_store.update(item_id, status="下载中")
            self.refresh_signal.emit()
            success = False
            try:
                process = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                           text=True, encoding='utf-8')

                self.running_downloads[item_id] = process
                for line in process.stdout:
                    if not line or line.isspace():
                        continue
                    formatted_output = f"[任务 {item_id}] {line.strip()}"
                    if line.strip().startswith("Vid Kbps"):
                        if log_deque and log_deque[-1].startswith(f"[任务 {item_id}] Vid Kbps"):
                            log_deque[-1] = formatted_output
                        else:
                            log_deque.append(formatted_output)
                    else:
                        log_deque.append(formatted_output)
                for line in process.stderr:
                    if not line or line.isspace():
                        continue
                    log_deque.append(f"[任务 {item_id}] {line.strip()}")
                process.communicate()
                return_code = process.returncode
                if return_code == 0:
                    success = True
                    log_deque.append(f"[任务 {item_id}] 命令执行成功")
                else:
                    log_deque.append(f"[任务 {item_id}] 命令执行失败，返回码: {return_code}")
            except OSError as e:
                log_deque.append(f"[任务 {item_id}] 命令执行失败: {str(e)}")
            except Exception as e:
                log_deque.append(f"[任务 {item_id}] 发生错误: {str(e)}")
            finally:
                log_deque.append(f"[任务 {item_id}] 结束 : {'下载成功' if success else '下载失败'}")
                self.task_signal.emit('已完成' if success else '失败', item_id)

        thread = threading.Thread(target=download_task, daemon=True)
        thread.start()


def start_flask_server(downloader_instance: M3U8Downloader):
    app = Flask(__name__)
    CORS(app)

    @app.route('/add', methods=['GET', 'POST'])
    def handle_task():
        # --- 1. 数据获取适配 ---
        if request.method == 'POST':
            # 从 JSON 体获取
            data = request.get_json() or {}
            url = data.get("url", "").strip()
            name = data.get("name", "").strip()
            pic = data.get("pic", "").strip()
        else:
            # 从 URL 参数获取 (例如: /?url=xxx&name=xxx)
            url = request.args.get("url", "").strip()
            name = request.args.get("name", "").strip()
            pic = request.args.get("pic", "").strip()

        # --- 2. 鉴权逻辑 ---
        auth = request.headers.get('Authorization') or request.args.get('auth')
        if downloader_instance.auth_key and auth != downloader_instance.auth_key:
            return jsonify({"status": "error", "message": "无效授权"}), 401

        # --- 3. 核心业务逻辑 (通用) ---
        if not url or not name:
            return jsonify({"status": "error", "message": "url 和 name 必填"}), 400

        # 验证是否为有效 m3u8
        if not downloader_instance.is_m3u8_url(url):
            return jsonify({"status": "error", "message": "无效的m3u8链接"}), 400

        # 查重
        if any(item['url'] == url for item in downloader_instance.downloads_data):
            return jsonify({"status": "error", "message": "该URL已存在"}), 400

        # 发送信号添加任务
        downloader_instance.api_add_task_signal.emit(url, name, pic)

        return jsonify({"status": "success", "message": f"{request.method} 请求成功"}), 200

    app.run(host='127.0.0.1', port=int(downloader_instance.port), threaded=True)


def main():
    app = QApplication(sys.argv)
    downloader = M3U8Downloader()

    threading.Thread(target=start_flask_server, args=(downloader,), daemon=True).start()

    downloader.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
