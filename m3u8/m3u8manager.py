import json
import os
import re
import threading
from pathlib import Path

import unicodedata
from flask import Flask, request, jsonify
from flask_cors import CORS


class JSONStoreManager:
    def __init__(self, json_dir: Path):
        self.json_dir = json_dir.resolve()  # 确保是绝对路径
        if not self.json_dir.is_dir():
            self.json_dir.mkdir(parents=True, exist_ok=True)
        self.stores = {}
        self.lock = threading.Lock()

    def get_store(self, filename: str):
        # 安全化文件名，只取最后一部分，强制 .json 结尾
        safe_name = os.path.basename(str(filename).strip())
        if not safe_name:
            safe_name = "AV.json"
        if not safe_name.lower().endswith('.json'):
            safe_name += '.json'

        # 永远使用 JSON_DIR 作为父目录
        full_path = self.json_dir / safe_name

        key = str(full_path)  # 用字符串绝对路径做 key，避免 Path 对象比较问题
        with self.lock:
            if key not in self.stores:
                self.stores[key] = JSONStore(full_path)
            return self.stores[key]


class JSONStore:
    def __init__(self, filepath: Path):
        self.filepath = filepath.resolve()  # 强制绝对路径
        self.lock = threading.RLock()
        self._data = []
        self._last_mtime = 0
        self._load()

    def _load(self):
        with self.lock:
            if not self.filepath.exists():
                self._data = []
                self._save()  # 创建空文件
                return

            current_mtime = self.filepath.stat().st_mtime
            if current_mtime == self._last_mtime:
                return  # 无需重复加载

            try:
                with open(self.filepath, "r", encoding="utf-8") as f:
                    self._data = json.load(f)
                self._last_mtime = current_mtime
            except Exception as e:

                self._data = []

    def _reload_if_needed(self):
        """检查文件是否被外部修改，如果是则重新加载"""
        with self.lock:
            if os.path.exists(self.filepath):
                current_mtime = os.path.getmtime(self.filepath)
                if current_mtime > self._last_mtime:
                    print(f"检测到文件 {self.filepath} 被外部修改，正在重新加载...")
                    self._load()

    def get_all(self):
        with self.lock:
            self._reload_if_needed()  # 读取前检查
            return list(self._data)

    def add_task(self, url: str, name: str, pic: str = ""):
        with self.lock:
            self._reload_if_needed()  # 写入前先同步外部修改
            if any(item['url'] == url for item in self._data):
                return False, "该URL已存在"
            new_id = max((item['id'] for item in self._data), default=0) + 1
            new_item = {'id': new_id, 'url': url, 'name': name, 'pic': pic, 'status': '待下载'}
            self._data.append(new_item)
            self._save()
            return True, new_item

    def _save(self):
        with self.lock:
            with open(self.filepath, "w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False, indent=2)
            self._last_mtime = self.filepath.stat().st_mtime

    def delete_by_url(self, url: str):
        with self.lock:
            self._reload_if_needed()
            original_len = len(self._data)
            self._data = [item for item in self._data if item.get('url') != url]

            if len(self._data) < original_len:
                try:
                    self._save()
                    return True, "删除成功"
                except Exception as e:

                    return False, "删除失败（保存出错）"
            return False, "没有找到该 url"


JSON_DIR =Path("/www/tvbox/json")

app = Flask(__name__,static_folder='/www/tvbox/json', static_url_path='/json')
CORS(app)
manager = JSONStoreManager(JSON_DIR)
DEFAULT_FILE = "AV.json"


def get_params():
    """统一获取参数，支持 GET 和 POST JSON"""
    if request.is_json:
        return request.get_json()
    return request.args


def generate_pic_url(save_name: str) -> str:
    if not save_name:
        return ""
    code = save_name.split(' ', 1)[0].strip().lower()
    return f"https://fourhoi.com/{code}/cover-n.jpg"


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


@app.route('/add', methods=['GET', 'POST'])
def add():
    params = get_params()
    filename = params.get('file', DEFAULT_FILE)
    url = params.get('url', '').strip()
    name = params.get('name', '').strip()
    pic = params.get('pic', '').strip()

    if not url or not name:
        return jsonify({"status": "error", "message": "url 和 name 必填"}), 400

    name = sanitize_filename(name)

    if not pic:
        pic = generate_pic_url(name)

    store = manager.get_store(filename)
    success, result = store.add_task(url, name, pic)
    return jsonify({"status": "success" if success else "error", "data": result, "file": filename})


@app.route('/delete', methods=['GET', 'POST'])
def delete():
    params = get_params()
    filename = params.get('file', DEFAULT_FILE)
    url = params.get('url', '').strip()

    if not url:
        return jsonify({"status": "error", "message": "缺少 url 参数"}), 400

    store = manager.get_store(filename)
    if store.delete_by_url(url):
        return jsonify({"status": "success", "message": "删除成功", "file": filename})
    return jsonify({"status": "error", "message": "未找到该 URL", "file": filename}), 404


@app.route('/list', methods=['GET'])
def list_tasks():
    filename = request.args.get('file', DEFAULT_FILE)
    store = manager.get_store(filename)
    return jsonify({"file": filename, "list": store.get_all()})


@app.route('/files', methods=['GET'])
def list_files():
    try:
        # 只列出 DATA_DIR 下的 .json 文件
        json_files = [
            f for f in os.listdir(JSON_DIR)
            if f.endswith('.json') and Path(JSON_DIR, f).is_file()
        ]

        json_files = sorted(set(json_files))  # 去重 + 排序

        return jsonify({"files": json_files})

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


# ============================================================


if __name__ == "__main__":
    app.run(host='0.0.0.0', port=8088)
