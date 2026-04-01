import ctypes
import re
import subprocess
import sys
from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtGui import QIntValidator
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QMessageBox, QComboBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QTextEdit, QLineEdit
)

if sys.platform == "win32":

    def is_admin():
        try:
            return ctypes.windll.shell32.IsUserAnAdmin()  # type: ignore[attr-defined]
        except:
            return False


    if not is_admin():
        if "--elevated" not in sys.argv:
            script = sys.argv[0]
            params = [script] + sys.argv[1:] + ["--elevated"]
            params_str = " ".join(f'"{p}"' for p in params)

            ctypes.windll.shell32.ShellExecuteW(  # type: ignore[attr-defined]
                None, "runas", sys.executable, params_str, None, 1
            )
            sys.exit(0)


# ---------------- 基础命令工具 ----------------

def run_cmd(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True, shell=True)
    return r.stdout.strip(), r.stderr.strip(), r.returncode


# ---------------- 端口排除解析 ----------------

def get_excluded_ports(protocol="tcp"):
    """
    返回列表: (协议, 起始端口, 结束端口, 数量, 是否手动添加)
    """
    cmd = f"netsh int ipv4 show excludedportrange protocol={protocol}"
    out, _, _ = run_cmd(cmd)
    ranges = []

    for line in out.splitlines():
        m = re.match(r'\s*(\d+)\s+(\d+)(\s+\*)?', line.strip())
        if m:
            start = int(m.group(1))
            end = int(m.group(2))
            count = end - start + 1
            manual = bool(m.group(3))
            ranges.append((protocol.upper(), start, end, count, manual))
    return ranges


# ---------------- GUI 主窗口 ----------------

class PortExcludeGUI(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Windows 端口排除范围管理工具 (PySide6)")
        self.resize(900, 600)

        layout = QVBoxLayout(self)

        title = QLabel("Windows 端口排除范围检测与管理工具（优化版）")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 20px; font-weight: bold; padding: 10px;")
        layout.addWidget(title)

        # 表格
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["协议", "起始端口", "结束端口", "数量", "手动添加"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setSortingEnabled(True)
        self.table.setAlternatingRowColors(True)
        layout.addWidget(self.table)

        # 按钮区
        btn_layout = QHBoxLayout()
        self.btn_refresh = QPushButton("刷新列表")
        self.btn_add = QPushButton("添加排除范围")
        self.btn_delete = QPushButton("删除选中范围")
        btn_layout.addWidget(self.btn_refresh)
        btn_layout.addWidget(self.btn_add)
        btn_layout.addWidget(self.btn_delete)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        # 输入区
        form_layout = QHBoxLayout()
        self.protocol_combo = QComboBox()
        self.protocol_combo.addItems(["tcp", "udp"])
        self.protocol_combo.setFixedWidth(80)

        self.start_input = QLineEdit()
        self.start_input.setPlaceholderText("例如: 50000")
        self.start_input.setValidator(QIntValidator(1, 65535))

        self.count_input = QLineEdit()
        self.count_input.setPlaceholderText("例如: 1000")
        self.count_input.setValidator(QIntValidator(1, 65536))

        form_layout.addWidget(QLabel("协议:"))
        form_layout.addWidget(self.protocol_combo)
        form_layout.addSpacing(20)
        form_layout.addWidget(QLabel("起始端口:"))
        form_layout.addWidget(self.start_input)
        form_layout.addSpacing(20)
        form_layout.addWidget(QLabel("端口数量:"))
        form_layout.addWidget(self.count_input)
        form_layout.addStretch()

        layout.addLayout(form_layout)

        # 日志区
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumHeight(150)
        layout.addWidget(QLabel("操作日志:"))
        layout.addWidget(self.log)

        # 信号连接
        self.btn_refresh.clicked.connect(self.refresh)
        self.btn_add.clicked.connect(self.add_range)
        self.btn_delete.clicked.connect(self.delete_range)

        self.log_msg("工具启动成功（已获取管理员权限）。")
        self.refresh()

    # ---------------- 辅助函数 ----------------

    def log_msg(self, msg):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.log.append(f"[{timestamp}] {msg}")
        self.log.ensureCursorVisible()

    # ---------------- 功能实现 ----------------

    def refresh(self):
        self.table.setRowCount(0)
        self.table.setSortingEnabled(False)
        all_ranges = get_excluded_ports("tcp") + get_excluded_ports("udp")
        all_ranges.sort(key=lambda x: (x[0], x[1]))

        for row_idx, data in enumerate(all_ranges):
            proto, start, end, count, manual = data
            self.table.insertRow(row_idx)
            self.table.setItem(row_idx, 0, QTableWidgetItem(str(proto)))
            self.table.setItem(row_idx, 1, QTableWidgetItem(str(start)))
            self.table.setItem(row_idx, 2, QTableWidgetItem(str(end)))
            self.table.setItem(row_idx, 3, QTableWidgetItem(str(count)))

            # 逻辑判断
            if manual:
                status_text = "是"
                color = Qt.GlobalColor.green
            else:
                status_text = "否"
                color = Qt.GlobalColor.red

            item = QTableWidgetItem(status_text)
            item.setForeground(color)
            self.table.setItem(row_idx, 4, item)

        self.table.setSortingEnabled(True)
        self.log_msg(f"刷新完成，共找到 {len(all_ranges)} 条排除范围。")

    def add_range(self):
        protocol = self.protocol_combo.currentText().lower()
        try:
            start = int(self.start_input.text())
            count = int(self.count_input.text())
        except ValueError:
            QMessageBox.warning(self, "输入错误", "起始端口和数量必须为有效整数。")
            return

        if count <= 0:
            QMessageBox.warning(self, "输入错误", "端口数量必须大于 0。")
            return

        end = start + count - 1
        if start < 1 or end > 65535:
            QMessageBox.warning(self, "输入错误", "端口范围必须在 1-65535 之间。")
            return

        # 检查与现有范围冲突（同一协议）
        existing = get_excluded_ports(protocol)
        for _, s, e, _, _ in existing:
            if not (end < s or start > e):
                QMessageBox.critical(self, "冲突检测", f"新增范围与现有范围 {s}-{e} 重叠，无法添加。")
                return

        self.log_msg(f"正在添加 {protocol.upper()} 范围 {start}-{end}（数量 {count}）...")

        # 停止 WinNAT
        self.log_msg("停止 WinNAT 服务...")
        run_cmd("net stop winnat")

        # 执行添加
        cmd = f"netsh int ipv4 add excludedportrange protocol={protocol} startport={start} numberofports={count}"
        out, err, code = run_cmd(cmd)
        if out or err:
            self.log_msg(out + "\n" + err if out and err else out or err)

        # 启动 WinNAT
        self.log_msg("启动 WinNAT 服务...")
        run_cmd("net start winnat")

        if code == 0:
            QMessageBox.information(self, "成功", f"排除范围 {start}-{end} 添加成功。")
            self.start_input.clear()
            self.count_input.clear()
        else:
            QMessageBox.critical(self, "失败", "添加排除范围失败（可能有端口被占用或系统限制）。")

        self.refresh()

    def delete_range(self):
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.warning(self, "选择错误", "请先在表格中选中一条要删除的范围。")
            return

        proto = self.table.item(row, 0).text().lower()
        start = int(self.table.item(row, 1).text())
        end = int(self.table.item(row, 2).text())
        count = end - start + 1
        manual = self.table.item(row, 4).text() == "是"

        if not manual:
            reply = QMessageBox.question(
                self, "警告",
                "该范围为系统自动保留（非手动添加），删除可能导致 Hyper-V/WSL/Docker 等功能异常。\n\n是否继续？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        reply = QMessageBox.question(
            self, "确认删除",
            f"确定删除 {proto.upper()} 端口排除范围：\n{start} - {end}（数量 {count}）？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        self.log_msg(f"正在删除 {proto.upper()} 范围 {start}-{end}...")

        # 停止 WinNAT
        self.log_msg("停止 WinNAT 服务...")
        run_cmd("net stop winnat")

        # 执行删除
        cmd = f"netsh int ipv4 delete excludedportrange protocol={proto} startport={start} numberofports={count}"
        out, err, code = run_cmd(cmd)
        if out or err:
            self.log_msg(out + "\n" + err if out and err else out or err)

        # 启动 WinNAT
        self.log_msg("启动 WinNAT 服务...")
        run_cmd("net start winnat")

        if code == 0:
            QMessageBox.information(self, "成功", f"排除范围 {start}-{end} 删除成功。")
        else:
            QMessageBox.critical(self, "失败", "删除排除范围失败。")

        self.refresh()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = PortExcludeGUI()
    win.show()
    sys.exit(app.exec())
