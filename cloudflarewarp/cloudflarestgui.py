import datetime
import json
import re
import subprocess
import sys
import time
from pathlib import Path

import requests
import yaml
from PySide6 import QtGui
from PySide6.QtCore import QProcess, QUrl, QThread, Signal, QTimer
from PySide6.QtGui import QColor, QDesktopServices, QTextCursor
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                               QHBoxLayout, QPushButton, QTextEdit, QTableWidget,
                               QTableWidgetItem, QHeaderView, QLineEdit, QLabel,
                               QFileDialog, QCheckBox, QGridLayout,
                               QMessageBox, QComboBox)
# import ctypes
#
# if sys.platform == "win32":
#
#     def is_admin():
#         try:
#             return ctypes.windll.shell32.IsUserAnAdmin()  # type: ignore[attr-defined]
#         except:
#             return False
#
#
#     if not is_admin():
#         if "--elevated" not in sys.argv:
#             script = sys.argv[0]
#
#             params = [script] + sys.argv[1:] + ["--elevated"]
#             params_str = " ".join(f'"{p}"' for p in params)
#
#             ctypes.windll.shell32.ShellExecuteW(  # type: ignore[attr-defined]
#                 None,
#                 "runas",
#                 sys.executable,
#                 params_str,
#                 None,
#                 1
#             )
#             sys.exit(0)


class SpeedTestWorker(QThread):
    log_signal = Signal(str)
    finished_signal = Signal()

    def __init__(self, proxy_url):
        super().__init__()
        self.proxy_url = proxy_url
        self._is_running = True

    def stop(self):
        self._is_running = False

    def run(self):

        proxies = {"http": self.proxy_url, "https": self.proxy_url}
        latency = 0.0
        colo = "未知"

        try:
            trace_url = "https://1.1.1.1/cdn-cgi/trace"
            start = time.perf_counter()
            resp = requests.get(trace_url, proxies=proxies, timeout=5)
            if resp.status_code == 200:
                latency = (time.perf_counter() - start) * 1000
                for line in resp.text.split('\n'):
                    if line.startswith('colo='):
                        colo = line.split('=')[1]

            self.log_signal.emit(f"当前IP: {self.proxy_url} 数据中心: {colo} 延迟: {latency:.2f}ms")
            self.log_signal.emit("开始测试下载速度 (100MB)...")

            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36",
                "Referer": "https://speed.cloudflare.com",
                "Accept": "*/*",
                "Connection": "keep-alive"
            }

            download_size = 100 * 1024 * 1024
            speed_url = f"https://speed.cloudflare.com/__down?bytes={download_size}"
            start = time.perf_counter()
            with requests.get(speed_url, proxies=proxies, timeout=20, stream=True, headers=headers) as r:
                r.raise_for_status()
                downloaded = 0
                for chunk in r.iter_content(chunk_size=512 * 1024):
                    if not self._is_running:
                        self.log_signal.emit("测试被用户取消")
                        return
                    if chunk:
                        downloaded += len(chunk)
                        duration = time.perf_counter() - start
                        speed = downloaded / (duration * 1024 * 1024)
                        self.log_signal.emit(
                            f"PROGRESS| 下载进度 :{(downloaded / download_size * 100):.2f} % 平均下载速度: {speed:.2f} MB/s")

            duration = time.perf_counter() - start
            speed = downloaded / (duration * 1024 * 1024)
            self.log_signal.emit(f"测试完成！平均下载速度: {speed:.2f} MB/s")

        except Exception as e:
            self.log_signal.emit(f"测试出错: {str(e)}")

        finally:
            self.finished_signal.emit()


class CloudflareSTGui(QMainWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("CloudflareST GUI - 优选加速")
        self.resize(1400, 800)

        self.config_file = Path("Config.yaml")
        self.config = {}
        self.load_config()

        self.current_output_file = None

        self.worker = None

        self.process = QProcess(self)
        self.process.readyReadStandardOutput.connect(self.handle_stdout)
        self.process.readyReadStandardError.connect(self.handle_stderr)
        self.process.finished.connect(self.process_finished)

        self.init_ui()

        QTimer.singleShot(500, self.update_info)

    def init_ui(self):

        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(10, 10, 10, 10)

        params_widget = QWidget(self)
        params_grid = QGridLayout(params_widget)
        params_grid.setColumnStretch(1, 1)
        params_grid.setColumnStretch(3, 1)
        params_grid.setHorizontalSpacing(20)
        params_grid.setVerticalSpacing(12)

        row = 0

        params_grid.addWidget(QLabel("CloudflareST 可执行文件:"), row, 0)
        exe_layout = QHBoxLayout()
        self.exe_input = QLineEdit()
        self.exe_input.setText(self.config.get('exe_path', 'CloudflareST.exe'))
        exe_layout.addWidget(self.exe_input)
        browse_exe_btn = QPushButton("浏览...")
        browse_exe_btn.clicked.connect(self.browse_exe)
        exe_layout.addWidget(browse_exe_btn)
        params_grid.addLayout(exe_layout, row, 1)

        params_grid.addWidget(QLabel("上次使用 IP:"), row, 2)

        last_ip_layout = QHBoxLayout()

        self.last_ip_combo = QComboBox()
        self.last_ip_combo.setEditable(True)

        last_ip_list = self.config.get('last_ip', [])

        if last_ip_list:
            self.last_ip_combo.addItems(last_ip_list)
            self.last_ip_combo.setCurrentIndex(0)
        else:
            self.last_ip_combo.setPlaceholderText("")

        last_ip_layout.addWidget(self.last_ip_combo)

        self.replace_last_btn = QPushButton("替换当前IP")
        self.replace_last_btn.setFixedWidth(80)
        self.replace_last_btn.clicked.connect(
            lambda: self.replace_ip(self.last_ip_combo.currentText())
        )
        last_ip_layout.addWidget(self.replace_last_btn)

        self.delete_ip_btn = QPushButton("删除历史IP")
        self.delete_ip_btn.setFixedWidth(80)
        self.delete_ip_btn.clicked.connect(self.delete_selected_ip)
        last_ip_layout.addWidget(self.delete_ip_btn)

        if not last_ip_list:
            self.delete_ip_btn.setEnabled(False)
            self.replace_last_btn.setEnabled(False)

        params_grid.addLayout(last_ip_layout, row, 3)
        row += 1

        params_grid.addWidget(QLabel("IP 数据文件 (-f):"), row, 0)
        ip_layout = QHBoxLayout()
        self.ip_input = QLineEdit()
        self.ip_input.setText(self.config.get('ip_file', 'ip.txt'))
        ip_layout.addWidget(self.ip_input)
        browse_ip_btn = QPushButton("浏览...")
        browse_ip_btn.clicked.connect(self.browse_ip_file)
        ip_layout.addWidget(browse_ip_btn)
        params_grid.addLayout(ip_layout, row, 1)

        params_grid.addWidget(QLabel("结果输出目录 (-o):"), row, 2)
        output_layout = QHBoxLayout()
        self.output_input = QLineEdit()
        self.output_input.setText(self.config.get('output_dir', '.'))
        output_layout.addWidget(self.output_input)
        browse_output_btn = QPushButton("浏览...")
        browse_output_btn.clicked.connect(self.browse_output_dir)
        output_layout.addWidget(browse_output_btn)
        params_grid.addLayout(output_layout, row, 3)

        row += 1

        params_grid.addWidget(QLabel("指定 IP 段 (-ip):"), row, 0)
        self.ip_seg_input = QLineEdit()
        self.ip_seg_input.setText(self.config.get('ip_seg', ''))
        self.ip_seg_input.setPlaceholderText("例如: 1.1.1.1,2.2.2.2/24")
        params_grid.addWidget(self.ip_seg_input, row, 1)

        params_grid.addWidget(QLabel("延迟测速线程 (-n):"), row, 2)
        self.thread_input = QLineEdit(self.config.get('n', '200'))
        params_grid.addWidget(self.thread_input, row, 3)
        row += 1

        params_grid.addWidget(QLabel("延迟测速次数 (-t):"), row, 0)
        self.t_input = QLineEdit(self.config.get('t', '4'))
        params_grid.addWidget(self.t_input, row, 1)

        params_grid.addWidget(QLabel("下载测速数量 (-dn):"), row, 2)
        self.dn_input = QLineEdit(self.config.get('dn', '10'))
        params_grid.addWidget(self.dn_input, row, 3)
        row += 1

        params_grid.addWidget(QLabel("下载测速时间 (-dt 秒):"), row, 0)
        self.dt_input = QLineEdit(self.config.get('dt', '10'))
        params_grid.addWidget(self.dt_input, row, 1)

        params_grid.addWidget(QLabel("测速端口 (-tp):"), row, 2)
        self.tp_input = QLineEdit(self.config.get('tp', '443'))
        params_grid.addWidget(self.tp_input, row, 3)
        row += 1

        params_grid.addWidget(QLabel("测速地址 (-url):"), row, 0)
        self.url_input = QLineEdit(self.config.get('url', 'https://cf.xiu2.xyz/url'))
        params_grid.addWidget(self.url_input, row, 1)

        params_grid.addWidget(QLabel("有效 HTTP 状态码 (-httping-code):"), row, 2)
        self.httping_code_input = QLineEdit(self.config.get('httping_code', '200'))
        self.httping_code_input.setPlaceholderText("默认")
        params_grid.addWidget(self.httping_code_input, row, 3)
        row += 1

        params_grid.addWidget(QLabel("匹配地区 (-cfcolo):"), row, 0)
        self.cfcolo_input = QLineEdit(self.config.get('cfcolo', ''))
        self.cfcolo_input.setPlaceholderText("例如: HKG,LAX,SEA")
        params_grid.addWidget(self.cfcolo_input, row, 1)

        params_grid.addWidget(QLabel("平均延迟上限 (-tl ms):"), row, 2)
        self.tl_input = QLineEdit(self.config.get('tl', '9999'))
        params_grid.addWidget(self.tl_input, row, 3)
        row += 1

        params_grid.addWidget(QLabel("平均延迟下限 (-tll ms):"), row, 0)
        self.tll_input = QLineEdit(self.config.get('tll', '0'))
        params_grid.addWidget(self.tll_input, row, 1)

        params_grid.addWidget(QLabel("丢包率上限 (-tlr):"), row, 2)
        self.tlr_input = QLineEdit(self.config.get('tlr', '1.00'))
        params_grid.addWidget(self.tlr_input, row, 3)
        row += 1

        params_grid.addWidget(QLabel("下载速度下限 (-sl MB/s):"), row, 0)
        self.sl_input = QLineEdit(self.config.get('sl', '0.00'))
        params_grid.addWidget(self.sl_input, row, 1)

        params_grid.addWidget(QLabel("显示结果数量 (-p):"), row, 2)
        self.p_input = QLineEdit(self.config.get('p', '10'))
        params_grid.addWidget(self.p_input, row, 3)
        row += 1

        switch_layout = QHBoxLayout()
        self.httping_cb = QCheckBox("使用 HTTPing 模式 (-httping)")
        self.httping_cb.setChecked(self.config.get('httping', False))
        switch_layout.addWidget(self.httping_cb)

        self.dd_cb = QCheckBox("禁用下载测速 (-dd)")
        self.dd_cb.setChecked(self.config.get('dd', False))
        switch_layout.addWidget(self.dd_cb)

        self.allip_cb = QCheckBox("测速全部 IP (-allip)")
        self.allip_cb.setChecked(self.config.get('allip', False))
        switch_layout.addWidget(self.allip_cb)

        self.debug_cb = QCheckBox("调试输出模式 (-debug)")
        self.debug_cb.setChecked(self.config.get('debug', False))
        switch_layout.addWidget(self.debug_cb)

        switch_layout.addStretch()
        params_grid.addLayout(switch_layout, row, 0, 1, 4)

        main_layout.addWidget(params_widget)

        btn_layout = QHBoxLayout()
        self.save_btn = QPushButton("保存配置")
        self.save_btn.clicked.connect(self.save_config)
        btn_layout.addWidget(self.save_btn)

        self.test_btn = QPushButton("开始测速")
        self.test_btn.clicked.connect(self.toggle_test)
        btn_layout.addWidget(self.test_btn)

        self.load_result_btn = QPushButton("加载结果文件")
        self.load_result_btn.clicked.connect(self.load_manual_result)
        btn_layout.addWidget(self.load_result_btn)

        self.load_ip_btn = QPushButton("当前IP信息")
        self.load_ip_btn.clicked.connect(self.get_now_ip)
        btn_layout.addWidget(self.load_ip_btn)

        self.test_now_ip_btn = QPushButton("测试当前IP")
        self.test_now_ip_btn.clicked.connect(self.test_now_ip)
        btn_layout.addWidget(self.test_now_ip_btn)

        self.best_replace_btn = QPushButton("替换最优IP")
        self.best_replace_btn.clicked.connect(self.replace_best_ip)
        btn_layout.addWidget(self.best_replace_btn)

        self.warp_proxy_btn = QPushButton("启动 WARP代理")
        self.warp_proxy_btn.clicked.connect(self.toggle_warp_proxy)
        btn_layout.addWidget(self.warp_proxy_btn)

        self.warp_mode_btn = QPushButton("WARP模式")
        self.warp_mode_btn.clicked.connect(self.toggle_warp_mode)
        btn_layout.addWidget(self.warp_mode_btn)

        self.system_proxy_btn = QPushButton("启动 系统代理")
        self.system_proxy_btn.clicked.connect(self.toggle_system_proxy)
        btn_layout.addWidget(self.system_proxy_btn)

        # self.lan_proxy_btn = QPushButton("启动局域网代理")
        # self.lan_proxy_btn.clicked.connect(self.toggle_lan_proxy)
        # btn_layout.addWidget(self.lan_proxy_btn)

        btn_layout.addStretch()

        self.useful_test_ip_btn = QPushButton("常用测速网址")
        self.useful_test_ip_btn.clicked.connect(self.useful_test_ips)
        btn_layout.addWidget(self.useful_test_ip_btn)

        self.cloudflare_ip_btn = QPushButton("CloudflareIP 数据")
        self.cloudflare_ip_btn.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl("https://www.cloudflare-cn.com/ips/")))
        btn_layout.addWidget(self.cloudflare_ip_btn)

        main_layout.addLayout(btn_layout)

        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setPlaceholderText("等待任务开始...")
        self.log_output.setMaximumHeight(220)
        self.log_output.setStyleSheet("background-color: #1e1e1e; color: #d4d4d4; font-family: Consolas;")
        main_layout.addWidget(self.log_output)

        self.table = QTableWidget()
        self.table.setColumnCount(8)
        self.table.setHorizontalHeaderLabels(
            ["IP 地址", "已发送", "已接收", "丢包率", "平均延迟", "下载速度(MB / s)", "地区码", "操作"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setSortingEnabled(True)
        main_layout.addWidget(self.table, stretch=1)

    def delete_selected_ip(self):
        current_index = self.last_ip_combo.currentIndex()
        if current_index == -1:
            return

        current_text = self.last_ip_combo.currentText()

        self.last_ip_combo.removeItem(current_index)

        if 'last_ip' in self.config and current_text in self.config['last_ip']:
            self.config['last_ip'].remove(current_text)

            try:
                with open(self.config_file, 'w', encoding='utf-8') as f:
                    yaml.safe_dump(self.config, f, allow_unicode=True, sort_keys=False)
            except Exception as ex:
                self.log_output.append(f"历史ip写入失败\n错误::{ex}")

        if self.last_ip_combo.count() == 0:
            self.last_ip_combo.setPlaceholderText("")
            self.delete_ip_btn.setEnabled(False)
            self.replace_last_btn.setEnabled(False)
        else:

            self.last_ip_combo.setCurrentIndex(0)
            self.delete_ip_btn.setEnabled(True)
            self.replace_last_btn.setEnabled(True)

    def useful_test_ips(self):
        msg_box = QMessageBox()
        msg_box.setWindowTitle("常用测速链接")
        msg = "http_code是200 : \nCloudflare :\thttps://speed.cloudflare.com/__down?bytes=104857600\n" \
              "CacheFly :\thttp://cachefly.cachefly.net/100mb.test\n" \
              "Vultr首尔 :\thttps://sel-kor-ping.vultr.com/vultr.com.100MB.bin\n" \
              "自带测速 :\thttps://cf.xiu2.xyz/url\n" \
              "\n" \
              "http_code是204 : \nCloudflare :\thttps://cp.cloudflare.com/generate_204\n" \
              "\n" \
              f"当前http_code :\t{self.httping_code_input.text()}\n"
        msg_box.setText(msg)
        msg_box.setStandardButtons(QMessageBox.StandardButton.Ok)
        msg_box.setStyleSheet("QDialogButtonBox { qproperty-centerButtons: true; }")
        labels = msg_box.findChildren(QLabel)
        for label in labels:
            if label.text():
                label.setTextInteractionFlags(QtGui.Qt.TextInteractionFlag.TextSelectableByMouse)
        msg_box.exec()

    def update_info(self):
        # self.update_lan_proxy_button_text(self.check_lan_proxy_status())
        self.update_warp_proxy_button_text(self.check_warp_status())
        self.update_system_proxy_button_text(self.check_system_status())
        self.update_warp_mode_button_text(self.check_warp_mode())

    def replace_best_ip(self):
        if self.table.rowCount() == 0:
            QMessageBox.warning(self, "无结果", "测速结果表格为空，无法选择最优IP")
            return

        best_row = 0
        if self.dd_cb.isChecked():
            best_value = float('inf')
            compare_col = 4
            better = lambda current, best: current < best
        else:
            best_value = 0.0
            compare_col = 5
            better = lambda current, best: current > best

        for r in range(self.table.rowCount()):
            item = self.table.item(r, compare_col)
            if item:
                try:
                    value = float(item.text().replace(',', ''))
                    if better(value, best_value):
                        best_value = value
                        best_row = r
                except:
                    pass

        ip_item = self.table.item(best_row, 0)
        if ip_item:
            best_ip = ip_item.text().strip()
            self.replace_ip(best_ip)
            self.log_output.append(f"已自动替换最优IP: {best_ip}")
        else:
            QMessageBox.warning(self, "错误", "无法获取最优IP")

    def check_warp_status(self):
        try:
            result = subprocess.run(
                ["warp-cli", "status"],
                capture_output=True, text=True, check=True, creationflags=subprocess.CREATE_NO_WINDOW
            )
            output = result.stdout.lower()  # 转小写便于匹配
            if "disconnected" in output:
                return False
            elif "connected" in output:
                return True
            elif "connecting" in output:
                time.sleep(1)
                return self.check_warp_status()
        except FileNotFoundError:
            self.log_output.append("错误: 未找到 warp-cli 命令，请确保 Cloudflare WARP 已安装")
            return False
        except subprocess.CalledProcessError:
            self.log_output.append("错误: warp-cli status 执行失败")
            return False
        except Exception:
            return False

    def check_warp_mode(self):
        try:
            result = subprocess.run(
                ["warp-cli", "settings"],
                capture_output=True, text=True, check=True, creationflags=subprocess.CREATE_NO_WINDOW
            )
            output = result.stdout
            match = re.search(r"Mode\s*:\s*(\S+)", output)
            if match:
                return match.group(1).lower().strip()
        except FileNotFoundError:
            self.log_output.append("错误: 未找到 warp-cli 命令，请确保 Cloudflare WARP 已安装")
            return None
        except subprocess.CalledProcessError:
            self.log_output.append("错误: warp-cli status 执行失败")
            return None
        except Exception:
            return None

    def check_system_status(self):
        try:
            result = subprocess.run(
                r'reg query "HKCU\Software\Microsoft\Windows\CurrentVersion\Internet Settings" /v ProxyEnable',
                capture_output=True, text=True, check=True, creationflags=subprocess.CREATE_NO_WINDOW
            )
            output = result.stdout.lower()  # 转小写便于匹配
            if "0x0" in output:
                return False
            elif "0x1" in output:
                return True
            else:
                return False
        except subprocess.CalledProcessError:
            self.log_output.append("错误: 查询注册表系统代理状态失败 执行失败")
            return False
        except Exception:
            return False

    def check_lan_proxy_status(self):
        try:
            result = subprocess.run(
                ["netsh", "interface", "portproxy", "show", "v4tov4"],
                capture_output=True, text=True, check=True, creationflags=subprocess.CREATE_NO_WINDOW
            )
            output = result.stdout
            if "0.0.0.0" in output and "7897" in output and "127.0.0.1" in output and "7897" in output:
                return True
            return False
        except Exception:
            self.log_output.append("错误: 查询局域网代理状态失败 执行失败")
            return False

    def update_warp_proxy_button_text(self, status):
        if status:
            self.warp_proxy_btn.setText("关闭 WARP代理")
        else:
            self.warp_proxy_btn.setText("启动 WARP代理")

    def update_warp_mode_button_text(self, name):
        if name:
            self.warp_mode_btn.setText(f"当前模式: {name}")

    def update_system_proxy_button_text(self, status):
        if status:
            self.system_proxy_btn.setText("关闭 系统代理")
        else:
            self.system_proxy_btn.setText("启动 系统代理")

    # def update_lan_proxy_button_text(self, status):
    #     if status:
    #         self.lan_proxy_btn.setText("关闭局域网代理")
    #     else:
    #         self.lan_proxy_btn.setText("启动局域网代理")

    def toggle_warp_proxy(self):
        try:
            if self.check_warp_status():
                # 当前已连接 → 执行关闭
                self.log_output.append("正在关闭 WARP代理...")
                subprocess.run(["warp-cli", "disconnect"], check=True, capture_output=True,
                               creationflags=subprocess.CREATE_NO_WINDOW)
                self.log_output.append("WARP代理 关闭成功")
            else:
                # 当前断开 → 执行启动
                self.log_output.append("正在启动 WARP代理...")

                if "warpproxy" == self.check_warp_mode():

                    if not self.check_proxy_port():
                        QMessageBox.critical(self, "错误", f"端口7897被占用:\n")
                        return

                    self.log_output.append("WARP代理 启动中（端口 7897）")
                    subprocess.run(["warp-cli", "proxy", "port", "7897"], check=True, capture_output=True,
                                   creationflags=subprocess.CREATE_NO_WINDOW)
                else:
                    self.log_output.append("WARP代理 启动中")

                subprocess.run(["warp-cli", "connect"], check=True, capture_output=True,
                               creationflags=subprocess.CREATE_NO_WINDOW)

        except subprocess.CalledProcessError as e:
            error_msg = e.stderr.decode('utf-8', errors='ignore') if e.stderr else str(e)
            self.log_output.append(f"WARP代理 操作失败: {error_msg}")
            QMessageBox.critical(self, "错误", f"操作失败:\n{error_msg}")
        except FileNotFoundError:
            self.log_output.append("错误: 未找到 warp-cli 命令，请确保 Cloudflare WARP 已安装并配置正确")
            QMessageBox.critical(self, "错误", "未找到 warp-cli，请安装 Cloudflare WARP")
        except Exception as e:
            self.log_output.append(f"WARP代理 操作异常: {str(e)}")
            QMessageBox.critical(self, "错误", str(e))
        finally:
            status = self.check_warp_status()
            self.update_warp_proxy_button_text(status)

    def check_proxy_port(self):
        self.log_output.append("正在检查端口 : 7897 占用 ...")
        result = subprocess.run(
            "netstat -ano | findstr \"7897\"",
            shell=True,
            capture_output=True,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW)
        output = result.stdout.strip()
        if output == "":
            return True
        self.log_output.append(f"端口使用情况 : \n\n  {output}")
        return False

    def toggle_warp_mode(self):
        try:
            if "warpproxy" == self.check_warp_mode():
                self.log_output.append("正在切换代理模式 proxy 切换到 warp ...")
                subprocess.run(["warp-cli", "mode", "warp"], check=True, capture_output=True,
                               creationflags=subprocess.CREATE_NO_WINDOW)
            else:
                subprocess.run(["warp-cli", "proxy", "port", "7897"], check=True, capture_output=True,
                               creationflags=subprocess.CREATE_NO_WINDOW)
                self.log_output.append("正在切换代理模式 warp 切换到 proxy ...")
                subprocess.run(["warp-cli", "mode", "proxy"], check=True, capture_output=True,
                               creationflags=subprocess.CREATE_NO_WINDOW)
            self.log_output.append("代理模式 切换成功")
        except subprocess.CalledProcessError as e:
            error_msg = e.stderr.decode('utf-8', errors='ignore') if e.stderr else str(e)
            self.log_output.append(f"WARP代理 操作失败: {error_msg}")
            QMessageBox.critical(self, "错误", f"操作失败:\n{error_msg}")
        except FileNotFoundError:
            self.log_output.append("错误: 未找到 warp-cli 命令，请确保 Cloudflare WARP 已安装并配置正确")
            QMessageBox.critical(self, "错误", "未找到 warp-cli，请安装 Cloudflare WARP")
        except Exception as e:
            self.log_output.append(f"WARP代理 操作异常: {str(e)}")
            QMessageBox.critical(self, "错误", str(e))
        finally:
            name = self.check_warp_mode()
            self.update_warp_mode_button_text(name)

    def toggle_system_proxy(self):
        try:
            if self.check_system_status():
                # 当前已连接 → 执行关闭
                self.log_output.append("正在关闭 系统代理...")
                subprocess.run(
                    r'reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Internet Settings" /v ProxyEnable /t REG_DWORD /d 0 /f',
                    check=True, capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
                self.log_output.append("系统代理 关闭成功")
            else:
                # 当前断开 → 执行启动
                self.log_output.append("正在启动 系统代理...")
                subprocess.run(
                    r'reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Internet Settings" /v ProxyEnable /t REG_DWORD /d 1 /f',
                    check=True, capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
                self.log_output.append("系统代理 启动中（端口 7897）")
        except subprocess.CalledProcessError as e:
            error_msg = e.stderr.decode('utf-8', errors='ignore') if e.stderr else str(e)
            self.log_output.append(f"注册表 系统代理 操作失败: {error_msg}")
            QMessageBox.critical(self, "错误", f"操作失败:\n{error_msg}")
        except Exception as e:
            self.log_output.append(f"注册表 系统代理 操作异常: {str(e)}")
            QMessageBox.critical(self, "错误", str(e))
        finally:
            status = self.check_system_status()
            self.update_system_proxy_button_text(status)

    # def toggle_lan_proxy(self):
    #     try:
    #         if self.check_lan_proxy_status():
    #             # 关闭
    #             self.log_output.append("正在关闭局域网代理...")
    #             subprocess.run(
    #                 ["netsh", "interface", "portproxy", "delete", "v4tov4", "listenport=7897", "listenaddress=0.0.0.0"],
    #                 capture_output=True, text=True, check=True, creationflags=subprocess.CREATE_NO_WINDOW)
    #             subprocess.run(["netsh", "advfirewall", "firewall", "delete", "rule", "name=WARP LAN Proxy 7897"],
    #                            capture_output=True, text=True, check=True, creationflags=subprocess.CREATE_NO_WINDOW)
    #             self.log_output.append("局域网代理已关闭")
    #         else:
    #             # 启动
    #             self.log_output.append("正在启动局域网代理...")
    #             subprocess.run(
    #                 ["netsh", "interface", "portproxy", "add", "v4tov4", "listenport=7897", "listenaddress=0.0.0.0",
    #                  "connectport=7897", "connectaddress=127.0.0.1"], capture_output=True, text=True, check=True,
    #                 creationflags=subprocess.CREATE_NO_WINDOW)
    #
    #             subprocess.run([
    #                 "netsh", "advfirewall", "firewall", "add", "rule",
    #                 "name=WARP LAN Proxy 7897", "dir=in", "action=allow",
    #                 "protocol=TCP", "localport=7897"
    #             ], capture_output=True, text=True, check=True, creationflags=subprocess.CREATE_NO_WINDOW)
    #             self.log_output.append("局域网代理已启动（监听 0.0.0.0:7897）")
    #     except subprocess.CalledProcessError as e:
    #         if "Run as administrator" in e.stdout:
    #             self.log_output.append("局域网代理操作失败: 当前操作需要管理员权限")
    #             QMessageBox.critical(self, "错误", "当前操作需要管理员权限")
    #         else:
    #             error_msg = e.stderr.decode('utf-8', errors='ignore') if e.stderr else str(e)
    #             self.log_output.append(f"局域网代理操作失败: {error_msg}")
    #             QMessageBox.critical(self, "错误", f"操作失败:\n{error_msg}")
    #     except Exception as e:
    #         self.log_output.append(f"局域网代理操作异常: {str(e)}")
    #         QMessageBox.critical(self, "错误", str(e))
    #     finally:
    #         self.update_lan_proxy_button_text(self.check_lan_proxy_status())

    def browse_exe(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "选择 CloudflareST 可执行文件", "",
                                                   "Executable Files (*.exe);;All Files (*)")
        if file_path:
            self.exe_input.setText(file_path)

    def browse_ip_file(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "选择 IP 数据文件", "", "Text Files (*.txt);;All Files (*)")
        if file_path:
            self.ip_input.setText(file_path)

    def browse_output_dir(self):
        dir_path = QFileDialog.getExistingDirectory(self, "选择结果输出目录", self.output_input.text())
        if dir_path:
            self.output_input.setText(dir_path)

    def load_config(self):
        if self.config_file.exists():
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    loaded = yaml.safe_load(f) or {}
                self.config = loaded
            except Exception as ex:
                QMessageBox.warning(self, "配置加载错误", f"读取 Config.yaml 失败\n错误: {ex}")

    def save_config(self):
        self.config['exe_path'] = self.exe_input.text().strip()
        self.config['ip_file'] = self.ip_input.text().strip()
        self.config['output_dir'] = self.output_input.text().strip()

        self.config['n'] = self.thread_input.text().strip()
        self.config['t'] = self.t_input.text().strip()
        self.config['dn'] = self.dn_input.text().strip()
        self.config['dt'] = self.dt_input.text().strip()
        self.config['tp'] = self.tp_input.text().strip()
        self.config['url'] = self.url_input.text().strip()
        self.config['httping'] = self.httping_cb.isChecked()
        self.config['httping_code'] = self.httping_code_input.text().strip()
        self.config['cfcolo'] = self.cfcolo_input.text().strip()
        self.config['tl'] = self.tl_input.text().strip()
        self.config['tll'] = self.tll_input.text().strip()
        self.config['tlr'] = self.tlr_input.text().strip()
        self.config['sl'] = self.sl_input.text().strip()
        self.config['p'] = self.p_input.text().strip()
        self.config['ip_seg'] = self.ip_seg_input.text().strip()
        self.config['dd'] = self.dd_cb.isChecked()
        self.config['allip'] = self.allip_cb.isChecked()
        self.config['debug'] = self.debug_cb.isChecked()

        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                yaml.safe_dump(self.config, f, allow_unicode=True, sort_keys=False)
            QMessageBox.information(self, "保存配置", "配置已保存到 Config.yaml")
        except Exception as e:
            QMessageBox.critical(self, "保存失败", f"无法写入 Config.yaml\n错误: {e}")

    def toggle_test(self):

        self.test_btn.setEnabled(False)

        if self.process.state() == QProcess.ProcessState.Running:
            self.process.kill()
            self.test_btn.setText("开始测速")
            self.log_output.append("\n任务已被强制停止。")
        else:
            self.log_output.clear()
            self.log_output.append("任务初始化...")
            self.table.setRowCount(0)
            self.current_output_file = None

            program = self.exe_input.text().strip()
            if not program:
                self.log_output.append("错误: 未指定 CloudflareST 可执行文件路径")
                return

            program_path = Path(program)
            if not program_path.exists():
                self.log_output.append(f"错误: 可执行文件不存在: {program}")
                return

            args = []

            def add_arg(flag, value):
                if value := value.strip():
                    args.extend([flag, value])

            add_arg("-n", self.thread_input.text())
            add_arg("-t", self.t_input.text())
            add_arg("-dn", self.dn_input.text())
            add_arg("-dt", self.dt_input.text())
            add_arg("-tp", self.tp_input.text())
            add_arg("-url", self.url_input.text())

            if self.httping_cb.isChecked():
                args.append("-httping")
            add_arg("-httping-code", self.httping_code_input.text())
            add_arg("-cfcolo", self.cfcolo_input.text())

            add_arg("-tl", self.tl_input.text())
            add_arg("-tll", self.tll_input.text())
            add_arg("-tlr", self.tlr_input.text())
            add_arg("-sl", self.sl_input.text())
            add_arg("-p", self.p_input.text())

            ip_file = self.ip_input.text().strip()
            if ip_file:
                ip_file_path = Path(ip_file)
                if ip_file_path.exists():
                    args.extend(["-f", ip_file])
                else:
                    self.log_output.append(f"警告: IP 文件不存在，将不添加 -f: {ip_file}")

            add_arg("-ip", self.ip_seg_input.text())

            output_dir = self.output_input.text().strip()
            if output_dir:
                output_dir_path = Path(output_dir)
                if output_dir_path.is_dir():
                    split = self.ip_input.text().split("/")
                    timestamp = datetime.datetime.now().strftime("%Y-%m-%d-%H-%M")
                    output_file = output_dir_path / f"{timestamp}-{split[-1]}"
                    self.current_output_file = str(output_file)
                    args.extend(["-o", self.current_output_file])
                    self.log_output.append(f"结果将保存到: {self.current_output_file}")
                else:
                    self.log_output.append(f"警告: 输出目录不存在，将不使用 -o 参数: {output_dir}")
            else:
                self.log_output.append("未指定输出目录，将不保存结果文件")

            if self.dd_cb.isChecked():
                args.append("-dd")
            if self.allip_cb.isChecked():
                args.append("-allip")
            if self.debug_cb.isChecked():
                args.append("-debug")

            self.test_btn.setText("关闭测速")
            self.log_output.append(f"正在启动测速任务...\n命令: {program} {' '.join(args)}\n")

            self.process.start(program, args)

        self.test_btn.setEnabled(True)

    def handle_stdout(self):
        data = self.process.readAllStandardOutput().data()
        stdout = data.decode("utf-8", errors="ignore")

        if "回车键" in stdout or "Ctrl+C" in stdout:
            self.process.write(b"\n")

        self.log_output.append(stdout.strip())

        self.log_output.ensureCursorVisible()

    def handle_stderr(self):
        data = self.process.readAllStandardError().data()
        stderr = data.decode("utf-8", errors="ignore")

        progress_pattern = r'(\d+ / \d+\s*\[.*?\][ 可用:]*\s*\d*)'
        matches = re.findall(progress_pattern, stderr)

        if matches:

            latest_progress = matches[-1]
            cursor = self.log_output.textCursor()
            cursor.movePosition(QtGui.QTextCursor.MoveOperation.End)

            cursor.movePosition(QtGui.QTextCursor.MoveOperation.StartOfLine, QtGui.QTextCursor.MoveMode.KeepAnchor)

            cursor.insertText(latest_progress)
            self.log_output.setTextCursor(cursor)
        else:
            self.log_output.append(stderr.strip())

        self.log_output.ensureCursorVisible()

    def process_finished(self, exit_code):
        if exit_code != 0:
            self.log_output.append(f"\n进程异常退出，退出码: {exit_code}")
        else:
            self.log_output.append("\n测速完成！正在加载结果...")
        self.test_btn.setText("开始测速")

        if self.current_output_file and Path(self.current_output_file).exists():
            self.log_output.append("正在加载本次测速结果...")
            self.parse_and_load_results(self.current_output_file)

    def parse_and_load_results(self, file_path: str):
        file_path = Path(file_path)
        if not file_path.exists():
            self.log_output.append(f"结果文件不存在: {file_path}")
            return

        try:
            rows = []
            with file_path.open('r', encoding='utf-8') as f:
                lines = f.readlines()

            data_lines = [line.strip() for line in lines[1:] if line.strip()]

            for line in data_lines:

                parts = [cell.strip() for cell in line.split(',')]
                if len(parts) >= 7:
                    rows.append(parts)

            if self.dd_cb.isChecked():
                def get_delay(row):
                    try:
                        return float(row[4])
                    except:
                        return float('inf')

                rows.sort(key=get_delay)
            else:
                def get_speed(row):
                    try:
                        return float(row[5])
                    except:
                        return 0.0

                rows.sort(key=get_speed, reverse=True)

            self.table.setRowCount(0)
            self.table.setSortingEnabled(False)

            for row_data in rows:
                r = self.table.rowCount()
                self.table.insertRow(r)

                for i in range(7):
                    item = QTableWidgetItem(row_data[i])
                    self.table.setItem(r, i, item)

                replace_btn = QPushButton("替换IP")

                current_ip = row_data[0]
                replace_btn.clicked.connect(lambda checked=False, ip=current_ip: self.replace_ip(ip))
                self.table.setCellWidget(r, 7, replace_btn)

            self.table.setSortingEnabled(True)

            if self.table.rowCount() > 0:
                for col in range(8):
                    item = self.table.item(0, col)
                    if item: item.setBackground(QColor("#90EE90"))

        except Exception as e:
            self.log_output.append(f"\n加载结果文件失败: {str(e)}")

    def load_manual_result(self):

        file_path, _ = QFileDialog.getOpenFileName(self, "选择结果文件", self.output_input.text(),
                                                   "Text Files (*.txt);;All Files (*)")
        if file_path:
            self.log_output.append(f"正在手动加载结果文件: {file_path}")
            self.parse_and_load_results(file_path)

    def replace_ip(self, ip):
        conf_path = Path(r"C:\ProgramData\Cloudflare\conf.json")
        if not conf_path.exists():
            QMessageBox.warning(self, "文件不存在", "未找到配置文件")
            return

        is_ipv6 = ":" in ip

        try:
            with conf_path.open('r', encoding='utf-8') as f:
                data = json.load(f)

            modified = False
            ports_list = ["443", "500", "1701", "4500", "4443", "8443", "8095"]
            ports_iter = iter(ports_list)
            for endpoint in data.get("endpoints", []):
                if is_ipv6:
                    endpoint.pop("v4", None)
                    if "v6" in endpoint:
                        old_v6 = endpoint["v6"]
                        if old_v6.startswith("[") and "]" in old_v6:
                            host, sep, port = old_v6.rpartition("]:")
                            if sep:
                                endpoint["v6"] = f"[{ip}]:{port}"
                            else:
                                endpoint["v6"] = f"[{ip}]"
                        else:
                            endpoint["v6"] = f"[{ip}]"
                        modified = True
                else:
                    if "v4" in endpoint:
                        old_v4 = endpoint["v4"]
                        if ":" in old_v4:
                            host, port = old_v4.rsplit(":", 1)
                            endpoint["v4"] = f"{ip}:{port}"
                        else:
                            endpoint["v4"] = ip
                        modified = True
                    else:
                        endpoint["v4"] = f"{ip}:{next(ports_iter, "443")}"

            if modified:
                with conf_path.open('w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, separators=(',', ':'))
                try:
                    subprocess.run(["ipconfig", "/flushdns"], check=True, capture_output=True,
                                   creationflags=subprocess.CREATE_NO_WINDOW)
                except:
                    self.log_output.append("刷新DNS失败")

                current_list = self.config.get('last_ip', [])

                if ip in current_list:
                    current_list.remove(ip)
                current_list.insert(0, ip)
                self.config['last_ip'] = current_list

                try:
                    with open(self.config_file, 'w', encoding='utf-8') as f:
                        yaml.safe_dump(self.config, f, allow_unicode=True, sort_keys=False)
                except Exception as ex:
                    self.log_output.append(f"历史ip写入失败\n错误::{ex}")

                QMessageBox.information(self, "成功", f"IP 已替换为: {ip}")

        except PermissionError as ep:
            QMessageBox.critical(self, "错误",
                                 "C:/ProgramData/Cloudflare/conf.json\n当前文件没有修改权限\n请到目录下,右击文件,选择属性中的安全标签\n选择当前用户增加修改权限\n或者直接用管理员权限运行此文件")
        except Exception as ex:
            QMessageBox.critical(self, "错误", str(ex))

    def get_now_ip_set(self):
        conf_path = Path(r"C:\ProgramData\Cloudflare\conf.json")
        if not conf_path.exists():
            QMessageBox.warning(self, "文件不存在", "未找到配置文件")
            return

        v4_ips = set()
        v6_ips = set()

        try:
            with conf_path.open('r', encoding='utf-8') as f:
                data = json.load(f)

            for endpoint in data.get("endpoints", []):
                if "v4" in endpoint:
                    v4_ip = endpoint["v4"].split(":")[0]
                    v4_ips.add(v4_ip)

                if "v6" in endpoint:
                    v6_full = endpoint["v6"]
                    v6_ip = v6_full.lstrip("[").split("]:")[0]
                    v6_ips.add(v6_ip)

            return v4_ips, v6_ips
        except json.JSONDecodeError:
            QMessageBox.warning(self, "文件错误", "配置文件不是有效的JSON格式")
        except Exception as e:
            QMessageBox.warning(self, "读取失败", f"读取配置文件时出错：{str(e)}")

    def get_now_ip(self):

        v4_ips, v6_ips = self.get_now_ip_set()

        v4_str = "\n".join("\t" + ip for ip in sorted(v4_ips)) if v4_ips else "\t无"
        v6_str = "\n".join("\t" + ip for ip in sorted(v6_ips)) if v6_ips else "\t无"

        msg = (f"IPv4地址:\n{v4_str}\t\n\n"
               f"IPv6地址:\n{v6_str}\t")

        box = QMessageBox(self)
        box.setWindowTitle("当前IP")
        box.setText(msg)
        box.setIcon(QMessageBox.Icon.NoIcon)
        box.setStandardButtons(QMessageBox.StandardButton.Ok)
        box.setStyleSheet("QDialogButtonBox { qproperty-centerButtons: true; }")
        labels = box.findChildren(QLabel)
        for label in labels:
            if label.text():
                label.setTextInteractionFlags(QtGui.Qt.TextInteractionFlag.TextSelectableByMouse)
        box.exec()

    def test_now_ip(self):

        test_url = None

        if self.worker and self.worker.isRunning():
            self.log_output.append("正在尝试停止测试，请稍候...")
            self.worker.stop()  # 发出停止指令
            self.test_now_ip_btn.setText("测试当前IP")
            return
        else:
            if not self.check_warp_status():
                QMessageBox.information(self, "测速异常", "Warp代理未启动,先启动代理")
                return
            try:
                result = subprocess.run(
                    ["warp-cli", "settings"],
                    capture_output=True, text=True, check=True, creationflags=subprocess.CREATE_NO_WINDOW
                )
                output = result.stdout
                if "Mode: WarpProxy" in output:
                    test_url = "socks5h://127.0.0.1:7897"
            except:
                self.log_output.append("错误: 查询当前代理模式失败")
                return

            self.worker = SpeedTestWorker(test_url)
            self.worker.log_signal.connect(self.handle_log)
            self.worker.finished_signal.connect(self.on_test_finished)
            self.worker.start()
            self.test_now_ip_btn.setText("停止测试")

    def on_test_finished(self):
        self.log_output.append("--- 测试流程结束 ---")
        self.test_now_ip_btn.setText("测试当前IP")

    def handle_log(self, text):
        if text.startswith("PROGRESS|"):
            # 获取进度条内容
            progress_text = text.split("|")[1]
            # 移动光标到最后一行并替换
            cursor = self.log_output.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End)
            cursor.select(QTextCursor.SelectionType.LineUnderCursor)
            cursor.removeSelectedText()
            cursor.insertText(progress_text)
        else:
            self.log_output.append(text)


if __name__ == "__main__":
    try:
        app = QApplication(sys.argv)
        window = CloudflareSTGui()
        window.show()
        sys.exit(app.exec())
    except Exception as e:
        import traceback
    traceback.print_exc()
    input("按回车键退出...")
