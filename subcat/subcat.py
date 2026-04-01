import re
import sys
import urllib.parse

import requests
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QComboBox,
    QScrollArea, QFrame, QGridLayout, QMessageBox
)
from bs4 import BeautifulSoup


class DownloadThread(QThread):
    finished = Signal(str, str)

    def __init__(self, url, filename, lang_code, headers, base_url):
        super().__init__()
        self.url = url
        self.filename = filename
        self.lang_code = lang_code
        self.headers = headers
        self.base_url = base_url

    def run(self):
        sanitized_name = re.sub(r'[<>:"/\\|?*]', '', self.filename)[:50] + ".srt"
        try:
            with requests.get(self.url, headers=self.headers, timeout=10) as response:
                response.raise_for_status()
                soup = BeautifulSoup(response.content, 'html.parser')
                down_a = soup.find("a", id=f"download_{self.lang_code}")
                if not down_a:
                    self.finished.emit("无该字幕", "")
                    return
                down_url = self.base_url + down_a.get('href')
                with requests.get(down_url, headers=self.headers, timeout=10) as dl_response:
                    dl_response.raise_for_status()
                    with open(sanitized_name, "wb") as f:
                        f.write(dl_response.content)
                    self.finished.emit("下载完成", "")
        except requests.RequestException as e:
            self.finished.emit("下载失败", str(e))
        except Exception as e:
            self.finished.emit("下载失败", str(e))


class SearchThread(QThread):
    finished = Signal(list, str)  # results: list of (name, url), error_msg

    def __init__(self, key, headers, web_url):
        super().__init__()
        self.key = key
        self.headers = headers
        self.web_url = web_url

    def run(self):
        search_url = self.web_url + "index.php?search=" + urllib.parse.quote(self.key)
        results = []
        error_msg = ""
        try:
            with requests.get(search_url, headers=self.headers, timeout=10) as response:
                response.raise_for_status()
                soup = BeautifulSoup(response.text, 'html.parser')
                t_body = soup.find("tbody")
                if t_body:
                    for tr in t_body.find_all("tr"):
                        td_list = tr.find_all("td")
                        for td in td_list:
                            a = td.find("a", recursive=False)
                            if a:
                                name = a.text.strip() + td.get_text(strip=True).replace(a.text.strip(), "").strip()
                                url = self.web_url + a["href"].lstrip("/")
                                results.append((name, url))
                                break
        except requests.RequestException:
            error_msg = "搜索请求失败，请检查网络"
        except Exception as e:
            error_msg = f"搜索异常：{str(e)}"

        self.finished.emit(results, error_msg)


class SubCatDownloader(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SubCat 字幕下载工具")
        self.resize(800, 600)
        self.language_dic = {"中文": "zh-CN", "日语": "ja"}
        self.web_url = "https://www.subtitlecat.com/"
        self.headers = {
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36"
        }
        self.init_ui()

    def init_ui(self):
        main_layout = QVBoxLayout(self)

        # 顶部搜索栏
        top_frame = QFrame(self)
        top_frame.setContentsMargins(0, 0, 0, 0)
        top_layout = QHBoxLayout(top_frame)
        top_layout.setContentsMargins(0, 0, 0, 0)

        self.search_input = QLineEdit()
        self.search_input.setFont(QFont("Arial", 12))
        self.search_input.setPlaceholderText("输入搜索关键词...")
        self.search_input.returnPressed.connect(self.sure_search)
        self.search_input.setFixedHeight(30)
        top_layout.addWidget(self.search_input, stretch=1)

        self.sure_button = QPushButton("确认搜索")
        self.sure_button.setFont(QFont("Arial", 12))
        self.sure_button.clicked.connect(self.sure_search)
        self.sure_button.setFixedHeight(30)
        top_layout.addWidget(self.sure_button)

        self.language_combo = QComboBox()
        self.language_combo.setFont(QFont("Arial", 12))
        self.language_combo.addItems(list(self.language_dic.keys()))
        self.language_combo.setFixedHeight(30)
        top_layout.addWidget(self.language_combo)

        main_layout.addWidget(top_frame)

        # 结果区域（可滚动）
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self.results_widget = QWidget(self)
        self.results_layout = QGridLayout(self.results_widget)
        self.results_layout.setColumnStretch(0, 1)
        self.results_layout.setColumnMinimumWidth(1, 30)
        self.results_layout.setColumnMinimumWidth(2, 100)

        scroll.setWidget(self.results_widget)
        main_layout.addWidget(scroll)

    def clear_results(self):
        for i in reversed(range(self.results_layout.count())):
            item = self.results_layout.itemAt(i)
            if item and item.widget():
                item.widget().deleteLater()

    def sure_search(self):
        key = self.search_input.text().strip()
        if not key:
            QMessageBox.information(self, "提示", "请输入搜索关键词")
            return

        self.clear_results()

        loading_label = QLabel("搜索中，请稍候...")
        loading_label.setFont(QFont("Arial", 14))
        loading_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.results_layout.addWidget(loading_label, 0, 0, 1, 3)

        self.sure_button.setEnabled(False)
        self.search_input.setEnabled(False)

        self.search_thread = SearchThread(key, self.headers, self.web_url)
        self.search_thread.finished.connect(self.on_search_finished)
        self.search_thread.start()

    def on_search_finished(self, results, error_msg):
        self.sure_button.setEnabled(True)
        self.search_input.setEnabled(True)

        self.clear_results()

        if error_msg:
            QMessageBox.warning(self, "错误", error_msg)
            no_label = QLabel("搜索失败")
            no_label.setFont(QFont("Arial", 12))
            self.results_layout.addWidget(no_label, 0, 0, 1, 3)
            return

        if not results:
            no_label = QLabel("未找到匹配的字幕")
            no_label.setFont(QFont("Arial", 12))
            self.results_layout.addWidget(no_label, 0, 0, 1, 3)
            return

        lang_code = self.language_dic[self.language_combo.currentText()]

        for i, (name, url) in enumerate(results):
            name_label = QLabel(name)
            name_label.setFont(QFont("Arial", 12))
            name_label.setWordWrap(True)
            self.results_layout.addWidget(name_label, i, 0)

            download_btn = QPushButton("下载")
            download_btn.setFont(QFont("Arial", 12))
            download_btn.setFixedWidth(80)

            thread = DownloadThread(url, name, lang_code, self.headers, self.web_url)
            thread.finished.connect(lambda text, err, btn=download_btn: self.on_download_finished(text, err, btn))
            download_btn.clicked.connect(lambda checked, t=thread, b=download_btn: self.start_download(t, b))

            self.results_layout.addWidget(download_btn, i, 2, alignment=Qt.AlignmentFlag.AlignRight)

    def start_download(self, thread: DownloadThread, button: QPushButton):
        button.setText("下载中...")
        button.setEnabled(False)
        thread.start()

    def on_download_finished(self, text: str, error: str, button: QPushButton):
        button.setText(text if text != "下载完成" else "下载")
        button.setEnabled(True)
        if error:
            QMessageBox.warning(self, "下载错误", f"下载失败：{error}")
        elif "完成" in text:
            QMessageBox.information(self, "成功", "字幕下载完成！")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = SubCatDownloader()
    window.show()
    sys.exit(app.exec())
