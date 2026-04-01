import json
import re
import sqlite3
import sys
import time
from collections import deque
from dataclasses import dataclass, fields
from datetime import datetime
from pathlib import Path
from typing import List

import requests
from PySide6.QtCore import QThread, Signal, Qt, QUrl, QTimer
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout,
    QHBoxLayout, QLineEdit, QPushButton, QTableWidget,
    QTableWidgetItem, QHeaderView, QPlainTextEdit,
    QLabel, QFileDialog, QMessageBox, QProgressBar,
    QCheckBox, QDialog, QFormLayout, QAbstractItemView
)


# ==================== 数据模型 ====================
@dataclass
class FileItem:
    owner: str = ""
    repo: str = ""
    platform: str = ""
    file_pattern: str = ""
    file_format: str = ""
    local_path: str = ""
    current_tag: str = ""
    sha: str = ""
    last_updated: str = ""
    update_timestamp: str = ""
    delete_old_version: bool = True
    confirm: bool = False
    include_prerelease: bool = False
    status: str = "待检查"
    latest_tag: str = ""
    latest_asset: str = ""
    latest_check_time: str = ""

    @staticmethod
    def from_dict(d):
        if not isinstance(d, dict):
            return FileItem()
        valid_keys = {f.name for f in fields(FileItem)}
        filtered_data = {k: v for k, v in d.items() if k in valid_keys}
        return FileItem(**filtered_data)

    def to_dict(self):
        return {
            "owner": self.owner,
            "repo": self.repo,
            "platform": self.platform,
            "file_pattern": self.file_pattern,
            "file_format": self.file_format,
            "local_path": self.local_path,
            "current_tag": self.current_tag,
            "sha": self.sha,
            "last_updated": self.last_updated,
            "update_timestamp": self.update_timestamp,
            "delete_old_version": self.delete_old_version,
            "confirm": self.confirm,
            "include_prerelease": self.include_prerelease,
            "status": self.status,
            "latest_tag": self.latest_tag,
            "latest_asset": self.latest_asset,
            "latest_check_time": self.latest_check_time,
        }


@dataclass
class LinkFileItem:
    url: str = ""
    down_type: int = 0
    file_name: str = ""
    current_version: str = ""
    local_path: str = ""
    last_updated: str = ""
    file_size: int = 0

    @staticmethod
    def from_dict(d):
        if not isinstance(d, dict):
            return LinkFileItem()
        valid_keys = {f.name for f in fields(LinkFileItem)}
        filtered_data = {k: v for k, v in d.items() if k in valid_keys}
        return LinkFileItem(**filtered_data)

    def to_dict(self):
        return {
            "url": self.url,
            "down_type": self.down_type,
            "file_name": self.file_name,
            "current_version": self.current_version,
            "local_path": self.local_path,
            "last_updated": self.last_updated,
            "file_size": self.file_size,
        }


# ==================== 数据库 ====================
class DatabaseManager:
    def __init__(self, db_path, lazy=False):
        self.db_path = db_path
        if not lazy:
            self.init()

    def init(self):
        self._init_db()

    def _get_connection(self):
        return sqlite3.connect(self.db_path)

    def _init_db(self):
        with self._get_connection() as conn:
            # 创建设置表（存储 token, proxy 等）
            conn.execute("""
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            """)
            # 创建文件项表
            conn.execute("""
                CREATE TABLE IF NOT EXISTS files (
                    owner TEXT, repo TEXT, platform TEXT, file_pattern TEXT,
                    file_format TEXT, local_path TEXT, current_tag TEXT,
                    sha TEXT, last_updated TEXT, update_timestamp TEXT,
                    delete_old_version INTEGER, confirm INTEGER, include_prerelease INTEGER,
                    status TEXT, latest_tag TEXT, latest_asset TEXT, latest_check_time TEXT,
                    PRIMARY KEY (owner, repo, platform)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS link_files (
                    url TEXT NOT NULL,
                    down_type integer,
                    file_name TEXT,
                    current_version TEXT,
                    local_path TEXT,
                    last_updated TEXT,
                    file_size NUMBER,
                    PRIMARY KEY (url)
                )
            """)
            conn.commit()

    def set_setting(self, key, value):
        with self._get_connection() as conn:
            conn.execute("""
            INSERT INTO settings (key, value) VALUES (?, ?)
                ON CONFLICT(key) 
                DO UPDATE SET value = excluded.value
            """, (key, value))

    def get_setting(self, key, default=""):
        with self._get_connection() as conn:
            row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
            return row[0] if row else default

    def save_file_item(self, item: 'FileItem'):
        data = (
            item.owner,
            item.repo,
            item.platform,
            item.file_pattern,
            item.file_format,
            item.local_path,
            item.current_tag,
            item.sha,
            item.last_updated,
            item.update_timestamp,
            int(item.delete_old_version),
            int(item.confirm),
            int(item.include_prerelease),
            item.status,
            item.latest_tag,
            item.latest_asset,
            item.latest_check_time
        )
        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO files (owner, repo, platform, file_pattern, file_format, local_path, current_tag, sha, last_updated, update_timestamp, 
                    delete_old_version, confirm, include_prerelease, status, latest_tag, latest_asset, latest_check_time) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(owner, repo, platform) 
                    DO UPDATE SET file_pattern = excluded.file_pattern,
                    file_format = excluded.file_format,
                    local_path = excluded.local_path,
                    current_tag = excluded.current_tag,
                    sha = excluded.sha,
                    last_updated = excluded.last_updated,
                    update_timestamp = excluded.update_timestamp,
                    delete_old_version = excluded.delete_old_version,
                    confirm = excluded.confirm,
                    include_prerelease = excluded.include_prerelease,
                    status = excluded.status,
                    latest_tag = excluded.latest_tag,
                    latest_asset = excluded.latest_asset,
                    latest_check_time = excluded.latest_check_time
                """, data)

    def save_link_file_item(self, item: 'LinkFileItem'):
        data = (
            item.url,
            item.down_type,
            item.file_name,
            item.current_version,
            item.local_path,
            item.last_updated,
            item.file_size,
        )
        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO link_files (
                    url,
                    down_type,
                    file_name,
                    current_version,
                    local_path,
                    last_updated,
                    file_size)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(url) 
                DO UPDATE SET 
                    down_type = excluded.down_type,
                    file_name = excluded.file_name,
                    current_version = excluded.current_version,
                    local_path = excluded.local_path,
                    last_updated = excluded.last_updated,
                    file_size = excluded.file_size
            """, data)

    def load_all_files(self):
        files = []
        with self._get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM files ORDER BY file_format ASC")
            for row in cursor.fetchall():
                file = FileItem(
                    owner=row["owner"],
                    repo=row["repo"],
                    platform=row["platform"],
                    file_pattern=row["file_pattern"],
                    file_format=row["file_format"],
                    local_path=row["local_path"],
                    current_tag=row["current_tag"],
                    sha=row["sha"],
                    last_updated=row["last_updated"],
                    update_timestamp=row["update_timestamp"],
                    delete_old_version=bool(row["delete_old_version"]),
                    confirm=bool(row["confirm"]),
                    include_prerelease=bool(row["include_prerelease"]),
                    status=row["status"],
                    latest_tag=row["latest_tag"],
                    latest_asset=row["latest_asset"],
                    latest_check_time=row["latest_check_time"]
                )
                files.append(file)
        return files

    def load_all_link_file(self):
        files = []
        with self._get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM link_files ORDER BY down_type ASC, local_path ASC,  file_name ASC")
            for row in cursor.fetchall():
                file = LinkFileItem(
                    url=row["url"],
                    down_type=row["down_type"],
                    file_name=row["file_name"],
                    current_version=row["current_version"],
                    local_path=row["local_path"],
                    last_updated=row["last_updated"],
                    file_size=row["file_size"],
                )
                files.append(file)
            return files

    def update_all_status(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE files SET status = '待检查'")

    def load_file(self, owner, repo, platform) -> FileItem:
        with self._get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM files WHERE owner = ? AND repo = ? AND platform = ?", (owner, repo, platform))
            files = []
            for row in cursor.fetchall():
                file = FileItem(
                    owner=row["owner"],
                    repo=row["repo"],
                    platform=row["platform"],
                    file_pattern=row["file_pattern"],
                    file_format=row["file_format"],
                    local_path=row["local_path"],
                    current_tag=row["current_tag"],
                    sha=row["sha"],
                    last_updated=row["last_updated"],
                    update_timestamp=row["update_timestamp"],
                    delete_old_version=bool(row["delete_old_version"]),
                    confirm=bool(row["confirm"]),
                    include_prerelease=bool(row["include_prerelease"]),
                    status=row["status"],
                    latest_tag=row["latest_tag"],
                    latest_asset=row["latest_asset"],
                    latest_check_time=row["latest_check_time"]
                )
                files.append(file)
            return files[0] if files else None

    def load_link_file(self, url) -> LinkFileItem:
        with self._get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM link_files WHERE url = ? ", (url,))
            files = []
            for row in cursor.fetchall():
                file = LinkFileItem(
                    url=row["url"],
                    down_type=row["down_type"],
                    file_name=row["file_name"],
                    current_version=row["current_version"],
                    local_path=row["local_path"],
                    last_updated=row["last_updated"],
                    file_size=row["file_size"],
                )
                files.append(file)
            return files[0] if files else None

    def delete_file_item(self, owner, repo, platform):
        with self._get_connection() as conn:
            conn.execute("DELETE FROM files WHERE owner = ? AND repo = ? AND platform = ?", (owner, repo, platform))

    def delete_link_file_item(self, url):
        with self._get_connection() as conn:
            conn.execute("DELETE FROM link_files WHERE url = ?", (url,))

    def reset_latest_info(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE files SET status = '待检查', latest_tag = NULL, latest_asset = NULL, latest_check_time = NULL")


class DbInitWorker(QThread):
    finished = Signal(str, str)

    def __init__(self, db: DatabaseManager):
        super().__init__()
        self.db = db

    def run(self):
        self.db.init()

        token = self.db.get_setting("github_token")

        proxy = self.db.get_setting("proxy")

        self.db.reset_latest_info()

        self.finished.emit(token, proxy)


class FileUnique:
    def __init__(
            self, owner, repo, platform
    ):
        self.owner = owner
        self.repo = repo
        self.platform = platform


# ==================== 代理探测线程 ====================
class ProxyProbeWorker(QThread):
    log_signal = Signal(str, bool)
    proxy_ready = Signal(str)

    def __init__(self, session, targets, silent=False):
        super().__init__()
        self.session = session
        self.targets = targets
        self.silent = silent

    def run(self):
        found = False
        set_proxy_str = ""
        for original_p in self.targets:
            if not original_p:
                continue
            variants = []
            if original_p == "system":
                variants.append(None)
            elif "://" in original_p:
                variants.append(original_p)
            else:
                variants.append(f"socks5://{original_p}")

            for proxy_url in variants:
                try:
                    if proxy_url is None:
                        current_proxies = {}
                        display_type = "直连"
                    else:
                        current_proxies = {'http': proxy_url, 'https': proxy_url}
                        proto = proxy_url.split("://")[0].upper()
                        display_type = f"{proto} 代理"

                    r = requests.get(
                        "https://api.github.com",
                        proxies=current_proxies,
                        timeout=3
                    )
                    if r.status_code in [200, 403]:
                        self.session.proxies.update(current_proxies)
                        set_proxy_str = "" if original_p == "system" else original_p
                        if not self.silent:
                            self.log_signal.emit(
                                f"代理就绪: {display_type}", False
                            )
                        found = True
                        break
                except Exception:
                    continue
            if found:
                break

        if not found:
            self.session.proxies.clear()
            if not self.silent:
                self.log_signal.emit("所有代理探测失败，已切换直连模式", True)

        self.proxy_ready.emit(set_proxy_str)


# ==================== 下载任务 ====================
class DownloadTask:
    def __init__(
            self, owner, repo, platform, url, local_path,
            expected_size, tag, asset_id,
            expected_name, asset_updated_at,
            matched_asset_name, is_prerelease=False
    ):
        self.owner = owner
        self.repo = repo
        self.platform = platform
        self.url = url
        self.local_path = local_path
        self.expected_size = expected_size
        self.tag = tag
        self.asset_id = asset_id
        self.expected_name = expected_name
        self.asset_updated_at = asset_updated_at
        self.matched_asset_name = matched_asset_name
        self.is_prerelease = is_prerelease

    def __eq__(self, other):
        if not isinstance(other, DownloadTask):
            return False
        return (self.owner, self.repo, self.tag, self.asset_id) == (other.owner, other.repo, other.tag, other.asset_id)

    def __hash__(self):
        return hash((self.owner, self.repo, self.tag, self.asset_id))


# ==================== 下载线程 ====================
class DownloadWorker(QThread):
    progress = Signal(int, str)
    finished = Signal(bool, str, object)

    def __init__(self, session, task: DownloadTask):
        super().__init__()
        self.session = session
        self.task = task

    def stop(self):
        self.requestInterruption()  # Qt 原生中断请求

    def run(self):
        max_retries = 3
        retry_delay = 3

        for attempt in range(1, max_retries + 1):
            try:
                dest = Path(self.task.local_path)
                dest.parent.mkdir(parents=True, exist_ok=True)
                tmp_path = dest.with_suffix('.download')

                initial_pos = tmp_path.stat().st_size if tmp_path.exists() else 0
                headers = {'Range': f'bytes={initial_pos}-'} if initial_pos > 0 else {}

                with self.session.get(
                        self.task.url, headers=headers,
                        stream=True, timeout=60
                ) as r:

                    if r.status_code == 416:
                        break
                    r.raise_for_status()

                    total = int(r.headers.get('Content-Length', 0)) + initial_pos
                    mode = 'ab' if initial_pos > 0 else 'wb'

                    with open(tmp_path, mode) as f:
                        curr = initial_pos
                        for chunk in r.iter_content(chunk_size=1024 * 64):

                            # 核心：检查线程中断请求
                            if self.isInterruptionRequested():
                                self.finished.emit(False, "手动停止", self.task)
                                return

                            if not chunk:
                                continue

                            f.write(chunk)
                            curr += len(chunk)

                            if total > 0:
                                percent = int(curr / total * 100)
                                mb_info = f"{curr // (1024 * 1024)}MB / {total // (1024 * 1024)}MB"
                                self.progress.emit(
                                    percent,
                                    f"[{attempt}/{max_retries}] {mb_info}"
                                )

                if self.task.expected_size and tmp_path.stat().st_size != self.task.expected_size:
                    raise Exception("文件大小不匹配")

                if dest.exists():
                    dest.unlink()
                tmp_path.replace(dest)

                self.finished.emit(True, "成功", self.task)
                return

            except Exception as e:
                if self.isInterruptionRequested():
                    self.finished.emit(False, "手动停止", self.task)
                    return

                if attempt < max_retries:
                    self.progress.emit(0, f"下载异常 ({attempt}/{max_retries}): {e}，{retry_delay}s 后重试...")
                    time.sleep(retry_delay)
                else:
                    tmp_path = Path(self.task.local_path).with_suffix('.download')
                    if tmp_path.exists():
                        tmp_path.unlink()
                    self.finished.emit(False, str(e), self.task)


class CheckDownloadTask(QThread):
    progress = Signal(int, str)
    finished = Signal(bool, str, str)

    def __init__(self, session, url: str, db: DatabaseManager):
        super().__init__()
        self.session = session
        self.url = url
        self.db = db

    def stop(self):
        self.requestInterruption()

    def run(self):
        file = self.db.load_link_file(self.url)

        local_dir = Path(file.local_path or ".").resolve()
        local_file = local_dir / file.file_name

        file_exists = local_file.exists()
        local_size = local_file.stat().st_size if file_exists else 0
        config_size = file.file_size or 0

        need_download = not file_exists or local_size != config_size
        expected_size = None

        if not need_download:
            self.progress.emit(0, "开始检查远程文件大小")
            try:
                head_resp = self.session.head(file.url, allow_redirects=True, timeout=30)

                if head_resp.status_code != 200:
                    head_resp = self.session.get(file.url, allow_redirects=True, timeout=30, stream=True)
                    head_resp.close()

                remote_size_str = head_resp.headers.get("Content-Length")
                if remote_size_str:
                    remote_size = int(remote_size_str)
                    if remote_size == config_size:
                        self.finished.emit(True, f"{file.file_name} | 大小一致，无需更新", file.url)
                        return
                    else:
                        self.progress.emit(0, f"远程文件大小变化 ({config_size:,} → {remote_size:,} bytes)，准备更新", )
                        expected_size = remote_size
                        need_download = True
                else:
                    self.progress.emit(0, "HEAD 未返回 Content-Length，保守起见准备下载")
                    need_download = True

            except Exception as e:
                self.progress.emit(0, f"HEAD 检查失败 ({e})，保守起见准备下载")
                need_download = True

        if not need_download:
            self.finished.emit(True, f"{file.file_name} 无需更新", file.url)
            return

        self.progress.emit(0, f"开始下载 → {local_file}")

        local_file.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = local_file.with_suffix(".download")

        max_retries = 3
        retry_delay = 3

        for attempt in range(1, max_retries + 1):
            try:
                initial_pos = tmp_path.stat().st_size if tmp_path.exists() else 0
                headers = {}
                if initial_pos > 0:
                    headers["Range"] = f"bytes={initial_pos}-"
                headers["Accept-Encoding"] = "identity"

                with self.session.get(
                        self.url,
                        headers=headers,
                        stream=True,
                        timeout=60,
                ) as r:

                    if r.status_code not in (200, 206):
                        r.raise_for_status()

                    if r.status_code == 200:
                        initial_pos = 0
                        mode = "wb"
                    else:
                        mode = "ab" if initial_pos > 0 else "wb"

                    total = int(r.headers.get("Content-Length", 0)) + initial_pos

                    with open(tmp_path, mode) as f:
                        curr = initial_pos

                        for chunk in r.iter_content(chunk_size=1024 * 64):
                            if self.isInterruptionRequested():
                                self.finished.emit(False, "手动停止", self.url)
                                return

                            if not chunk:
                                continue

                            f.write(chunk)
                            curr += len(chunk)

                            if total > 0:
                                percent = int(curr / total * 100)
                                mb_info = f"{curr // (1024 * 1024)}MB / {total // (1024 * 1024)}MB"
                                self.progress.emit(percent, f"[{attempt}/{max_retries}] {mb_info}", )

                if expected_size and tmp_path.stat().st_size != expected_size:
                    raise Exception("文件大小不匹配")

                if local_file.exists():
                    local_file.unlink()
                tmp_path.replace(local_file)

                final_size = local_file.stat().st_size

                file.last_updated = datetime.now().isoformat()
                file.file_size = final_size
                file.current_version = "latest"
                self.db.save_link_file_item(file)

                self.finished.emit(True, "成功", self.url)
                return

            except Exception as e:
                if self.isInterruptionRequested():
                    self.finished.emit(False, "手动停止", self.url)
                    return

                if attempt < max_retries:
                    self.progress.emit(f"下载异常 ({attempt}/{max_retries}): {e}，{retry_delay}s 后重试...", )
                    time.sleep(retry_delay)
                else:
                    if tmp_path.exists():
                        tmp_path.unlink()
                    self.finished.emit(False, str(e), self.url)
                    return


# ==================== 检查更新线程 ====================
class CheckWorker(QThread):
    progress = Signal(int, str)
    item_updated = Signal(str, str, str)
    log_signal = Signal(str, bool)
    finished_all = Signal()

    def __init__(self, session, uniques: List[FileUnique], token: str, db: DatabaseManager):
        super().__init__()
        self.session = session
        self.files = uniques
        self.token = token.strip() if token else ""
        self.db = db

    def run(self):
        headers = {"Accept": "application/vnd.github.v3+json"}
        if self.token:
            headers["Authorization"] = f"token {self.token}"

        total = len(self.files)
        if total == 0:
            self.finished_all.emit()
            return

        for idx, f in enumerate(self.files):
            file = self.db.load_file(f.owner, f.repo, f.platform)
            if file is None:
                continue
            try:

                include_pre = file.include_prerelease

                # 获取 release 数据
                if include_pre:
                    api_url = f"https://api.github.com/repos/{file.owner}/{file.repo}/releases"
                    r = self.session.get(api_url, headers=headers, timeout=10)
                    r.raise_for_status()
                    releases = r.json()

                    if not releases:
                        raise Exception("没有找到任何发布版本")

                    # 按发布时间排序，取最新
                    releases.sort(key=lambda x: x.get("created_at", ""), reverse=True)
                    data = releases[0]

                    if data.get("prerelease"):
                        self.log_signal.emit(f"{file.repo} 获取到最新预览版: {data['tag_name']}", False)
                    else:
                        self.log_signal.emit(f"{file.repo} 获取到最新正式版: {data['tag_name']}", False)

                else:
                    api_url = f"https://api.github.com/repos/{file.owner}/{file.repo}/releases/latest"
                    r = self.session.get(api_url, headers=headers, timeout=10)
                    r.raise_for_status()
                    data = r.json()
                    self.log_signal.emit(f"{file.repo} 获取到最新正式版: {data['tag_name']}", False)

                tag_name = data["tag_name"]

                # # 生成期望文件名（使用 file_format）
                expected_name = file.file_format.replace("{tag}", tag_name)

                # 正则匹配 asset
                pattern = re.compile(file.file_pattern, re.IGNORECASE)
                matched_asset = None

                for asset in data.get("assets", []):
                    asset_name = asset["name"]

                    if pattern.fullmatch(asset_name) or pattern.search(asset_name):
                        # 多个匹配时取最新 updated_at
                        if matched_asset is None or asset["updated_at"] > matched_asset["updated_at"]:
                            matched_asset = asset

                # 写回 FileItem
                if matched_asset:
                    file.latest_tag = tag_name
                    file.latest_asset = json.dumps(matched_asset)

                    local_file_path = Path(file.local_path) / expected_name
                    need_update = (
                            not local_file_path.exists() or
                            file.current_tag != tag_name or
                            file.sha != str(matched_asset["id"])
                    )

                    file.status = "有更新" if need_update else "已最新"

                    file.latest_check_time = datetime.now().isoformat()

                else:
                    file.latest_tag = ""
                    file.matched_asset = ""
                    file.status = "未找到匹配文件"
                    file.latest_check_time = datetime.now().isoformat()

                    self.log_signal.emit(f"未找到匹配文件: {expected_name}", True)

                self.db.save_file_item(file)
                # UI 更新
                self.item_updated.emit(f.owner, f.repo, f.platform)
                percent = int((idx + 1) / total * 100)
                self.progress.emit(percent, f"检查 {file.repo} ({idx + 1}/{total})")

            except Exception as e:
                file.latest_tag = "-"
                file.matched_asset = ""
                file.status = "检查失败"
                file.latest_check_time = datetime.now().isoformat()

                self.db.save_file_item(file)

                self.log_signal.emit(f"{file.repo} 检查失败: {str(e)}", True)
                self.item_updated.emit(f.owner, f.repo, f.platform)

        self.finished_all.emit()


# ==================== 编辑弹出窗口 ====================
class EditDialog(QDialog):
    def __init__(self, file_item: FileItem, parent=None):
        super().__init__(parent)
        self.setWindowTitle("修改配置")
        self.setMinimumWidth(300)

        self.file_item = file_item
        layout = QFormLayout(self)

        self.file_pattern = QLineEdit(file_item.file_pattern)
        self.platform = QLineEdit(file_item.platform)

        self.file_format = QLineEdit(file_item.file_format)
        self.local_path = QLineEdit(file_item.local_path)

        self.del_old = QCheckBox()
        self.del_old.setChecked(file_item.delete_old_version)

        self.need_confirm = QCheckBox()
        self.need_confirm.setChecked(file_item.confirm)

        self.include_pre = QCheckBox()
        self.include_pre.setChecked(file_item.include_prerelease)

        layout.addRow("平台名:", self.platform)
        layout.addRow("git文件名正则:", self.file_pattern)
        layout.addRow("输出文件格式化:", self.file_format)
        layout.addRow("保存位置:", self.local_path)
        layout.addRow("删除旧版:", self.del_old)
        layout.addRow("下载前确认:", self.need_confirm)
        layout.addRow("包含预览版:", self.include_pre)

        batons = QHBoxLayout()
        ok = QPushButton("确认")
        ok.clicked.connect(self.accept)
        cancel = QPushButton("取消")
        cancel.clicked.connect(self.reject)
        batons.addWidget(ok)
        batons.addWidget(cancel)

        layout.addRow(batons)
        self.adjustSize()

    def apply(self):
        self.file_item.platform = self.platform.text().strip()
        self.file_item.file_pattern = self.file_pattern.text().strip()
        self.file_item.file_format = self.file_format.text().strip()
        self.file_item.local_path = self.local_path.text().strip()
        self.file_item.delete_old_version = self.del_old.isChecked()
        self.file_item.confirm = self.need_confirm.isChecked()
        self.file_item.include_prerelease = self.include_pre.isChecked()


def format_size(size):
    if size == 0:
        return ""
    units = ["B", "KB", "MB", "GB", "TB", "PB"]
    i = 0
    while size >= 1024 and i < len(units) - 1:
        size /= 1024
        i += 1
    return f"{size:.2f} {units[i]}"


# ==================== 主界面 ====================
class GitHubUpdaterGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("GitHub 项目更新管理终端")
        self.resize(1300, 800)

        self.db_path = "_update_config.db"

        self.github_token = None

        self.config_proxy = None

        self.db = DatabaseManager(self.db_path, lazy=True)

        self.session = requests.Session()

        self.queue = deque()

        self.link_queue = deque()

        self.current_worker = None
        self.current_link_worker = None
        self.current_check_worker = None
        self.db_worker = None
        self.db_ready = False

        self.init_ui()

        QTimer.singleShot(1000, self.init_database_async)

    def init_database_async(self):
        if self.db_worker and self.db_worker.isRunning():
            self.log("数据库正在初始化中，请稍候...", True)
            return

        self.db_ready = False

        self.log("开始初始化数据库...")

        self.db_worker = DbInitWorker(self.db)
        self.db_worker.finished.connect(self.on_database_ready)
        self.db_worker.start()

    def on_database_ready(self, token, proxy):

        self.db_ready = True

        self.github_token = token
        self.config_proxy = proxy

        self.token_in.setText(token or "")
        self.proxy_in.setText(proxy or "")

        self.refresh_table()
        self.refresh_link_table()

        input_p = self.proxy_in.text().strip()
        targets = [input_p] if input_p else ["127.0.0.1:7897", "system"]
        self.start_proxy_probe(targets)

        self.log("数据库初始化完成")

    def init_ui(self):
        central = QWidget(self)
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)

        # --- 行 1 ---
        self.row1_widget = QWidget(self)
        self.row1_widget.setHidden(False)
        row1 = QHBoxLayout(self.row1_widget)
        self.row1_widget.setContentsMargins(0, 0, 0, 0)
        row1.setContentsMargins(0, 0, 0, 0)

        self.url_in = QLineEdit()
        self.url_in.setPlaceholderText("GitHub 项目地址，例如 https://github.com/owner/repo")

        self.file_in = QLineEdit()
        self.file_in.setPlaceholderText("git文件名正则表达式")

        self.platform_in = QLineEdit()
        self.platform_in.setPlaceholderText("平台名(amd64)")

        self.file_out = QLineEdit()
        self.file_out.setPlaceholderText("保存文件名模式，{tag} 会被替换")

        self.save_dir_in = QLineEdit("常用软件/")
        self.save_dir_in.setPlaceholderText("保存目录")

        add_btn = QPushButton("添加项目")
        add_btn.clicked.connect(self.add_item)

        row1.addWidget(QLabel("Git地址:"))
        row1.addWidget(self.url_in, 3)
        row1.addWidget(QLabel("平台名:"))
        row1.addWidget(self.platform_in, 1)
        row1.addWidget(QLabel("Git文件名正则:"))
        row1.addWidget(self.file_in, 1)
        row1.addWidget(QLabel("输出文件格式化:"))
        row1.addWidget(self.file_out, 1)
        row1.addWidget(QLabel("保存位置:"))
        row1.addWidget(self.save_dir_in, 1)
        row1.addWidget(add_btn)

        main_layout.addWidget(self.row1_widget)

        self.link_row1_widget = QWidget(self)
        self.link_row1_widget.setHidden(True)
        link_row1 = QHBoxLayout(self.link_row1_widget)
        self.link_row1_widget.setContentsMargins(0, 0, 0, 0)
        link_row1.setContentsMargins(0, 0, 0, 0)

        self.link_url_in = QLineEdit()
        self.link_url_in.setPlaceholderText("下载地址Url : ")

        self.link_file_in = QLineEdit()
        self.link_file_in.setPlaceholderText("文件名")

        self.link_down_type = QLineEdit()
        self.link_down_type.setPlaceholderText("0 下载,其他 跳转")

        self.link_save_dir_in = QLineEdit("常用软件/")
        self.link_save_dir_in.setPlaceholderText("保存目录")

        link_add_btn = QPushButton("添加项目")
        link_add_btn.clicked.connect(self.add_link_item)

        link_row1.addWidget(QLabel("文件URL地址:"))
        link_row1.addWidget(self.link_url_in, 3)
        link_row1.addWidget(QLabel("文件名:"))
        link_row1.addWidget(self.link_file_in, 1)
        link_row1.addWidget(QLabel("下载方式:"))
        link_row1.addWidget(self.link_down_type, 1)
        link_row1.addWidget(QLabel("保存位置:"))
        link_row1.addWidget(self.link_save_dir_in, 1)
        link_row1.addWidget(link_add_btn)

        main_layout.addWidget(self.link_row1_widget)

        # --- 行 2 ---
        row2 = QHBoxLayout()
        self.proxy_in = QLineEdit()
        self.proxy_in.setText(self.config_proxy)
        self.proxy_in.setPlaceholderText("127.0.0.1:7897 (自动尝试 HTTP 和 SOCKS5)")

        self.token_in = QLineEdit()
        self.token_in.setText(self.github_token)
        self.token_in.setPlaceholderText("github的token")

        test_p_btn = QPushButton("检测代理")
        test_p_btn.clicked.connect(self.test_proxy)

        self.cfg_label = QLineEdit(self.db_path)
        self.cfg_label.setReadOnly(True)

        sel_cfg_btn = QPushButton("选择数据库")
        sel_cfg_btn.clicked.connect(self.select_config)

        row2.addWidget(QLabel("代理:"))
        row2.addWidget(self.proxy_in, 3)
        row2.addWidget(test_p_btn)

        self.q_label = QLabel("token:")
        row2.addWidget(self.q_label)
        row2.addWidget(self.token_in, 3)

        row2.addWidget(QLabel("数据库 :"))
        row2.addWidget(self.cfg_label, 2)
        row2.addWidget(sel_cfg_btn)
        main_layout.addLayout(row2)

        # --- 行 3 ---
        row3 = QHBoxLayout()
        self.config_save_btn = QPushButton("保存配置")
        self.config_save_btn.clicked.connect(self.save_config)

        self.refresh_btn = QPushButton("刷新列表")
        self.refresh_btn.clicked.connect(self.refresh_table)

        self.stop_btn = QPushButton("停止下载")
        self.stop_btn.clicked.connect(self.stop_task)

        self.choose_btn = QPushButton("切换列表")
        self.choose_btn.clicked.connect(self.choose_table)

        self.config_save_btn.setFixedHeight(30)
        self.refresh_btn.setFixedHeight(30)
        self.stop_btn.setFixedHeight(30)
        self.choose_btn.setFixedHeight(30)

        row3.addWidget(self.config_save_btn)
        row3.addWidget(self.stop_btn)
        row3.addWidget(self.refresh_btn)
        row3.addWidget(self.choose_btn)

        row3.addStretch()

        self.check_btn = QPushButton("🔍 检查更新")
        self.check_btn.clicked.connect(self.check_all)

        self.update_all_btn = QPushButton("🚀 顺序更新")
        self.update_all_btn.clicked.connect(self.update_all_action)

        self.check_update_btn = QPushButton("🚀 全下载更新")
        self.check_update_btn.clicked.connect(self.check_update_all)
        self.check_update_btn.setHidden(True)

        self.check_btn.setFixedHeight(30)
        self.update_all_btn.setFixedHeight(30)
        self.check_update_btn.setFixedHeight(30)

        row3.addWidget(self.check_btn)
        row3.addWidget(self.update_all_btn)
        row3.addWidget(self.check_update_btn)

        main_layout.addLayout(row3)

        # --- 表格 ---
        self.headers = ["拥有者", "仓库", "平台", "Git文件名正则", "输出文件格式化", "保存位置", "删除旧版",
                        "当前版本", "目标版本", "状态", "操作"]
        self.table = QTableWidget(0, len(self.headers))
        self.table.setHorizontalHeaderLabels(self.headers)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)

        main_layout.addWidget(self.table)

        self.link_headers = ["链接", "文件名", "版本", "保存位置", "文件大小", "操作"]
        self.link_table = QTableWidget(0, len(self.link_headers))
        self.link_table.setHorizontalHeaderLabels(self.link_headers)
        self.link_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.link_table.setHidden(True)

        main_layout.addWidget(self.link_table)

        # --- 进度条 ---
        self.pbar = QProgressBar()
        self.pbar.setVisible(False)
        main_layout.addWidget(self.pbar)

        # --- 日志 ---
        self.log_area = QPlainTextEdit()
        self.log_area.setReadOnly(True)
        self.log_area.setStyleSheet(
            "background: #1e1e1e; color: #d4d4d4; font-family: Consolas;"
        )
        main_layout.addWidget(self.log_area)

    # ==================== 日志 ====================
    def log(self, msg, is_err=False):
        color = "#f44747" if is_err else "#d4d4d4"
        self.log_area.appendHtml(
            f'<span style="color:{color}">[{datetime.now().strftime("%H:%M:%S")}] {msg}</span>'
        )

    def start_proxy_probe(self, targets):
        if hasattr(self, 'proxy_probe_worker') and self.proxy_probe_worker.isRunning():
            return  # 防止重复启动
        self.log("开始代理探测..." if targets else "开始手动代理探测...")
        self.proxy_probe_worker = ProxyProbeWorker(self.session, targets)
        self.proxy_probe_worker.log_signal.connect(self.log)
        self.proxy_probe_worker.proxy_ready.connect(self.on_proxy_ready)
        self.proxy_probe_worker.start()

    def on_proxy_ready(self, proxy_str):
        if proxy_str:
            self.proxy_in.setText(proxy_str)

    def test_proxy(self):
        input_p = self.proxy_in.text().strip()
        targets = [input_p] if input_p else ["127.0.0.1:7897", "system"]
        self.start_proxy_probe(targets)

        # ==================== 配置 ====================

    def save_config(self):
        self.db.set_setting("proxy", self.proxy_in.text().strip())
        self.db.set_setting("github_token", self.token_in.text().strip())
        self.log("配置已经保存")
        # ==================== 表格刷新 ====================

    def choose_table(self):
        # 当前link_table是隐藏的
        if self.link_table.isHidden() and not self.table.isHidden():
            if self.queue or self.current_worker or self.current_check_worker:
                QMessageBox.warning(self, "任务进行中", "当前有任务在执行,不可切换")
            else:
                self.hider_reverse(True)

                self.refresh_btn.clicked.disconnect()
                self.refresh_btn.clicked.connect(self.refresh_link_table)
                self.stop_btn.clicked.disconnect()
                self.stop_btn.clicked.connect(self.stop_link_task)
        else:
            if self.link_queue or self.current_link_worker:
                QMessageBox.warning(self, "任务进行中", "当前有任务在执行,不可切换")
            else:
                self.hider_reverse(False)
                self.refresh_btn.clicked.disconnect()
                self.refresh_btn.clicked.connect(self.refresh_table)
                self.stop_btn.clicked.disconnect()
                self.stop_btn.clicked.connect(self.stop_task)

    def hider_reverse(self, hidden):
        self.link_table.setHidden(not hidden)
        self.link_row1_widget.setHidden(not hidden)
        self.check_update_btn.setHidden(not hidden)
        self.table.setHidden(hidden)
        self.row1_widget.setHidden(hidden)
        self.update_all_btn.setHidden(hidden)
        self.check_btn.setHidden(hidden)
        self.q_label.setHidden(hidden)
        self.token_in.setHidden(hidden)

    def refresh_table(self):

        self.table.setRowCount(0)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(0, 120)
        self.table.setColumnWidth(1, 120)
        self.table.setColumnWidth(2, 50)
        self.table.setColumnWidth(3, 150)
        self.table.setColumnWidth(4, 150)
        self.table.setColumnWidth(5, 120)
        self.table.setColumnWidth(6, 50)
        self.table.setColumnWidth(7, 120)
        self.table.setColumnWidth(8, 120)
        self.table.setColumnWidth(9, 60)

        self.table.horizontalHeader().setSectionResizeMode(10, QHeaderView.ResizeMode.Stretch)

        files = self.db.load_all_files()
        for i, file in enumerate(files):
            self.table.insertRow(i)
            self.set_table_item_info(file, i)

    def set_table_item_info(self, file, i: int):

        self.table.setItem(i, 0, QTableWidgetItem(file.owner))
        self.table.setItem(i, 1, QTableWidgetItem(file.repo))
        self.table.setItem(i, 2, QTableWidgetItem(file.platform))
        self.table.setItem(i, 3, QTableWidgetItem(file.file_pattern))
        self.table.setItem(i, 4, QTableWidgetItem(file.file_format))
        self.table.setItem(i, 5, QTableWidgetItem(file.local_path))

        cb_del = QCheckBox()
        cb_del.setChecked(file.delete_old_version)
        cb_del.setEnabled(False)

        widget = QWidget(self)
        layout = QHBoxLayout(widget)
        layout.addWidget(cb_del)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.table.setCellWidget(i, 6, widget)

        self.table.setItem(i, 7, QTableWidgetItem(file.current_tag))

        self.table.setItem(i, 8, QTableWidgetItem(file.latest_tag))

        item = QTableWidgetItem(file.status)
        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

        if file.status:
            if file.status == "有更新":
                item.setForeground(Qt.GlobalColor.red)
            elif file.status == "已最新":
                item.setForeground(Qt.GlobalColor.green)

        self.table.setItem(i, 9, item)

        if not self.table.item(i, 7): self.table.setItem(i, 7, QTableWidgetItem(file.current_tag))
        if not self.table.item(i, 8): self.table.setItem(i, 8, QTableWidgetItem(file.latest_tag))
        if not self.table.item(i, 9): self.table.setItem(i, 9, QTableWidgetItem(file.status))

        ops = QWidget(self)
        l = QHBoxLayout(ops)
        l.setContentsMargins(0, 0, 0, 0)

        btn_c = QPushButton("🔍")
        btn_c.setToolTip("单独检查此项目")

        btn_c.clicked.connect(
            lambda _, owner=file.owner, repo=file.repo, platform=file.platform: self.check_single(owner, repo,
                                                                                                  platform))
        l.addWidget(btn_c)

        btn_u = QPushButton("更新")
        can_update = False
        if file.latest_tag:
            expected_name = file.file_format.replace("{tag}", file.latest_tag)
            local_file_path = Path(file.local_path) / expected_name
            asset = json.loads(file.latest_asset)
            if asset:
                can_update = (
                        not local_file_path.exists() or
                        file.current_tag != file.latest_tag or
                        file.sha != str(asset["id"])
                )

        btn_u.setEnabled(can_update)
        btn_u.clicked.connect(
            lambda _, owner=file.owner, repo=file.repo, platform=file.platform: self.enqueue_task(owner, repo,
                                                                                                  platform))
        l.addWidget(btn_u)

        btn_m = QPushButton("修改")
        btn_m.clicked.connect(
            lambda _, owner=file.owner, repo=file.repo, platform=file.platform: self.modify_item(owner, repo, platform))
        l.addWidget(btn_m)

        btn_d = QPushButton("删除")
        btn_d.setStyleSheet("color:red")
        btn_d.clicked.connect(
            lambda _, owner=file.owner, repo=file.repo, platform=file.platform: self.delete_item(owner, repo, platform))
        l.addWidget(btn_d)

        self.table.setCellWidget(i, 10, ops)

    def refresh_row(self, owner, repo, platform, opt):
        if "change" == opt:
            for i in range(self.table.rowCount()):
                if self.table.item(i, 0).text() == owner and self.table.item(i, 1).text() == repo and self.table.item(i,
                                                                                                                      2).text() == platform:
                    file = self.db.load_file(owner, repo, platform)
                    self.set_table_item_info(file, i)
        elif "delete" == opt:
            for i in range(self.table.rowCount()):
                if self.table.item(i, 0).text() == owner and self.table.item(i, 1).text() == repo and self.table.item(i,
                                                                                                                      2).text() == platform:
                    self.table.setRowHidden(i, True)
        elif "add" == opt:
            file = self.db.load_file(owner, repo, platform)
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.set_table_item_info(file, row)

    def refresh_link_table(self):
        self.link_table.setRowCount(0)
        self.link_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        self.link_table.setColumnWidth(0, 400)
        self.link_table.setColumnWidth(1, 200)
        self.link_table.setColumnWidth(2, 150)
        self.link_table.setColumnWidth(3, 150)
        self.link_table.setColumnWidth(4, 100)
        self.link_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        files = self.db.load_all_link_file()
        for i, file in enumerate(files):
            self.link_table.insertRow(i)
            self.set_link_table_item_info(file, i)

    def set_link_table_item_info(self, file: LinkFileItem, i):
        self.link_table.setItem(i, 0, QTableWidgetItem(file.url))
        self.link_table.setItem(i, 1, QTableWidgetItem(file.file_name))
        self.link_table.setItem(i, 2, QTableWidgetItem(file.current_version))
        self.link_table.setItem(i, 3, QTableWidgetItem(file.local_path))
        self.link_table.setItem(i, 4, QTableWidgetItem(format_size(file.file_size)))
        ops = QWidget(self)
        l = QHBoxLayout(ops)
        l.setContentsMargins(0, 0, 0, 0)

        if file.down_type == 0:
            btn_u = QPushButton("下载更新")
            btn_u.clicked.connect(
                lambda _, name=file.file_name, url=file.url: self.check_down_link_file(name, url))
        else:
            btn_u = QPushButton("跳转更新")
            btn_u.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(f"{file.url}")))

        l.addWidget(btn_u)
        btn_d = QPushButton("删除")
        btn_d.setStyleSheet("color:red")
        btn_d.clicked.connect(
            lambda _, url=file.url: self.delete_link_item(url))
        l.addWidget(btn_d)

        self.link_table.setCellWidget(i, 5, ops)

    # ==================== 项目管理 ====================
    def check_down_link_file(self, name, url):
        if url not in self.link_queue:
            self.link_queue.append(url)
            self.log(f"加入下载队列: {name} {url})")
            self.start_next_link_task()

    def check_update_all(self):
        files = self.db.load_all_link_file()
        for file in files:
            if file.down_type == 0:
                self.link_queue.append(file.url)
                self.log(f"加入下载队列: {file.file_name} {file.url})")
        self.start_next_link_task()

    def start_next_link_task(self):
        if self.current_link_worker or not self.link_queue:
            self.pbar.setVisible(False)
            return
        down_url = self.link_queue.popleft()
        self.pbar.setVisible(True)
        self.pbar.setValue(0)
        self.pbar.setFormat(f"下载 {down_url} ...")

        self.current_link_worker = CheckDownloadTask(self.session, url=down_url, db=self.db)
        self.current_link_worker.progress.connect(
            lambda v, t: (self.pbar.setValue(v), self.pbar.setFormat(f"{down_url} {t}"))
        )
        self.current_link_worker.finished.connect(self.on_link_download_finished)
        self.current_link_worker.start()

    def on_link_download_finished(self, success, msg, url):

        worker = self.sender()

        if isinstance(worker, QThread):
            worker.wait()
            worker.deleteLater()

            if worker is self.current_link_worker:
                self.current_link_worker = None

        file = self.db.load_link_file(url)
        if success and file:
            self.log(f"下载成功: {file.file_name} → {file.last_updated} ({format_size(file.file_size)})")
            self.refresh_link_row(url, "change")
        else:
            self.log(f"下载失败 {file.file_name}: {msg}", True)

        self.start_next_link_task()

    def delete_link_item(self, url):
        if QMessageBox.question(self, "确认", "确定移除此项目？") == QMessageBox.StandardButton.Yes:
            self.db.delete_link_file_item(url)
            self.refresh_link_row(url, "delete")

    def refresh_link_row(self, url, opt):
        if "change" == opt:
            for i in range(self.link_table.rowCount()):
                if self.link_table.item(i, 0).text() == url:
                    file = self.db.load_link_file(url)
                    self.set_link_table_item_info(file, i)
        elif "delete" == opt:
            for i in range(self.link_table.rowCount()):
                if self.link_table.item(i, 0).text() == url:
                    self.link_table.setRowHidden(i, True)
        elif "add" == opt:
            file = self.db.load_link_file(url)
            row = self.link_table.rowCount()
            self.link_table.insertRow(row)
            self.set_link_table_item_info(file, row)

    def add_item(self):
        url = self.url_in.text().strip()
        m = re.search(r"github\.com/([^/]+)/([^/]+)", url)
        if not m:
            QMessageBox.warning(self, "错误", "无法解析 GitHub 项目地址")
            return
        owner, repo = m.groups()

        platform = self.platform_in.text().strip() or "amd64"

        file_item = FileItem(
            owner=owner,
            repo=repo,
            platform=platform,
            file_pattern=self.file_in.text().strip() or ".*",
            file_format=self.file_out.text().strip() or "{tag}",
            local_path=self.save_dir_in.text().strip() or "常用软件/"
        )

        self.db.save_file_item(file_item)
        self.refresh_row(owner, repo, platform, "add")
        self.url_in.clear()
        self.platform_in.clear()
        self.file_in.clear()
        self.file_out.clear()
        self.log(f"添加项目: {owner}/{repo}")

    def add_link_item(self):

        file_item = LinkFileItem(
            url=self.link_url_in.text().strip(),
            down_type=int(self.link_down_type.text().strip()),
            file_name=self.link_file_in.text().strip(),
            current_version='',
            local_path=self.link_save_dir_in.text().strip(),
            last_updated='',
            file_size=0,
        )

        self.db.save_link_file_item(file_item)
        self.refresh_link_row(file_item.url, "add")
        self.link_url_in.clear()
        self.link_down_type.clear()
        self.link_file_in.clear()
        self.log(f"添加项目: {file_item.file_name}/{file_item.url}")

    def modify_item(self, owner, repo, platform):
        file_item = self.db.load_file(owner, repo, platform)

        dlg = EditDialog(file_item, self)
        if dlg.exec():
            dlg.apply()
            # self.save_config()
            self.db.save_file_item(file_item)
            self.refresh_row(owner, repo, platform, "change")

    def delete_item(self, owner, repo, platform):
        if QMessageBox.question(self, "确认", "确定移除此项目？") == QMessageBox.StandardButton.Yes:
            self.db.delete_file_item(owner, repo, platform)
            self.refresh_row(owner, repo, platform, "delete")

    def select_config(self):
        if self.db_worker and self.db_worker.isRunning():
            QMessageBox.warning(self, "请稍候", "数据库正在初始化中，请等待完成后再切换")
            return

        file, _ = QFileDialog.getOpenFileName(self, "选择数据库", "", "DB (*.db)")
        if not file:
            return

        self.db_ready = False
        self.db_path = file
        self.cfg_label.setText(file)

        self.db = DatabaseManager(self.db_path, lazy=True)

        self.table.setRowCount(0)
        self.link_table.setRowCount(0)

        self.init_database_async()

    def check_all(self):
        if self.current_check_worker and self.current_check_worker.isRunning():
            self.log("检查任务正在进行中，请等待完成", True)
            return

        all_files = self.db.load_all_files()
        files = []
        for file in all_files:
            files.append(FileItem(file.owner, file.repo, file.platform))

        self.log("开始检查所有项目更新...")
        self.pbar.setVisible(True)
        self.pbar.setValue(0)
        self.pbar.setFormat("检查更新中...")

        self.current_check_worker = CheckWorker(
            self.session,
            files,
            self.token_in.text(),
            self.db
        )

        self.current_check_worker.progress.connect(
            lambda v, m: (self.pbar.setValue(v), self.pbar.setFormat(m))
        )
        self.current_check_worker.item_updated.connect(self.on_item_updated)
        self.current_check_worker.log_signal.connect(self.log)
        self.current_check_worker.finished_all.connect(self.on_check_finished)
        self.current_check_worker.start()

    def check_single(self, owner, repo, platform):
        if self.current_check_worker and self.current_check_worker.isRunning():
            self.log("检查任务正在进行中，请等待完成", True)
            return

        self.log(f"开始单独检查项目: {repo}")

        self.pbar.setVisible(True)
        self.pbar.setValue(0)
        self.pbar.setFormat(f"检查 {repo} ...")

        self.current_check_worker = CheckWorker(
            self.session,
            [FileUnique(owner, repo, platform)],
            self.token_in.text(),
            self.db
        )

        self.current_check_worker.progress.connect(
            lambda v, m: (self.pbar.setValue(v), self.pbar.setFormat(m))
        )

        self.current_check_worker.item_updated.connect(
            lambda o, r, p: self.apply_item_updates(o, r, p)
        )

        self.current_check_worker.log_signal.connect(self.log)
        self.current_check_worker.finished_all.connect(self.on_check_finished)
        self.current_check_worker.start()

    def apply_item_updates(self, owner, repo, platform):
        self.refresh_row(owner, repo, platform, "change")

    def on_item_updated(self, owner, repo, platform):
        self.refresh_row(owner, repo, platform, "change")

    def on_check_finished(self):
        if not self.current_worker:
            self.pbar.setVisible(False)
        self.current_check_worker = None
        self.log("项目检查完成")

    def stop_link_task(self):
        if self.link_queue:
            self.link_queue.clear()
            self.pbar.setVisible(False)
        if self.current_link_worker and self.current_link_worker.isRunning():
            self.current_link_worker.stop()

    def stop_task(self):
        if self.queue:
            self.queue.clear()
            self.pbar.setVisible(False)
        if self.current_worker and self.current_worker.isRunning():
            self.current_worker.stop()

    # ==================== 下载管理 ====================
    def enqueue_task(self, owner, repo, platform):
        file = self.db.load_file(owner, repo, platform)
        self.enqueue_task_file(file)

    def enqueue_task_file(self, file: FileItem):
        asset = json.loads(file.latest_asset)
        expected_name = file.file_format.replace("{tag}", file.latest_tag)
        if not asset or not expected_name:
            self.log(f"{file.repo} 无可用资产或文件名，无法下载", True)
            return

        task = DownloadTask(
            file.owner,
            file.repo,
            file.platform,
            asset['browser_download_url'],
            str(Path(file.local_path) / expected_name),
            asset['size'],
            file.latest_tag,
            str(asset['id']),
            expected_name,
            asset['updated_at'],
            asset['name'],
            file.include_prerelease
        )

        if task not in self.queue:
            pre_tag = " (预览)" if task.is_prerelease else ""
            self.queue.append(task)
            self.log(f"加入下载队列: {file.repo} → {expected_name} ({pre_tag} {task.tag})")
            self.start_next_task()

    def update_all_action(self):
        updated = False
        files = self.db.load_all_files()
        for i, file in enumerate(files):
            if file.status == "有更新":
                self.enqueue_task_file(file)
                updated = True
        if not updated:
            self.log("没有需要更新的项目")

    def start_next_task(self):
        if self.current_worker or not self.queue:
            if not self.queue and not self.current_check_worker:
                self.pbar.setVisible(False)
            return
        task = self.queue.popleft()
        file = self.db.load_file(task.owner, task.repo, task.platform)
        if not file:
            self.start_next_task()
            return

        if file.confirm:
            pre_tag = " (预览版)" if task.is_prerelease else ""
            msg = (f"★ 发现更新: {file.repo}\n\n"
                   f" 当前版本: {file.current_tag or '本地无记录'}\n"
                   f" 最新版本: {pre_tag} {task.tag}\n"
                   f" 下载目标: {task.expected_name}")
            reply = QMessageBox.question(self, "确认下载", msg,
                                         QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if reply != QMessageBox.StandardButton.Yes:
                pre_tag_log = " (预览)" if task.is_prerelease else ""
                self.log(f"用户跳过更新: {file.repo} → {task.expected_name} ({task.tag}{pre_tag_log})")
                self.start_next_task()
                return

        self.pbar.setVisible(True)
        self.pbar.setValue(0)
        self.pbar.setFormat(f"下载 {task.repo} ...")

        self.current_worker = DownloadWorker(self.session, task)
        self.current_worker.progress.connect(
            lambda v, t: (self.pbar.setValue(v), self.pbar.setFormat(f"{task.repo} {t}"))
        )
        self.current_worker.finished.connect(self.on_download_finished)
        self.current_worker.start()

    def on_download_finished(self, success, msg, task):
        worker = self.sender()  # 当前发信号的线程

        if isinstance(worker, QThread):
            worker.wait()
            worker.deleteLater()

            if worker is self.current_worker:
                self.current_worker = None

        file = self.db.load_file(task.owner, task.repo, task.platform)
        if success and file:
            pre_tag = " (预览)" if task.is_prerelease else ""
            self.log(f"下载成功: {task.repo} → {task.expected_name} ({pre_tag} {task.tag})")
            if file.delete_old_version:
                self.clean_old_files(file, task.expected_name)

            file.current_tag = task.tag
            file.sha = task.asset_id
            file.last_updated = task.asset_updated_at
            file.update_timestamp = datetime.now().isoformat()
            file.status = "已最新"

            self.db.save_file_item(file)
            self.refresh_row(file.owner, file.repo, file.platform, "change")
        else:
            self.log(f"下载失败 {task.repo}: {msg}", True)

        self.start_next_task()

    def clean_old_files(self, f, current_name):
        base = Path(f.local_path)
        glob_p = f.file_format.replace('{tag}', '*')
        for old in base.glob(glob_p):
            if old.is_file() and old.name != current_name:
                try:
                    old.unlink()
                    self.log(f"清理旧版本: {old.name}")
                except Exception as e:
                    self.log(f"清理失败 {old.name}: {e}", True)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    w = GitHubUpdaterGUI()
    w.show()
    sys.exit(app.exec())
