import os
import sys
import numpy as np
import imageio.v3 as imageio
import piexif
import rawpy
import pillow_heif
from concurrent.futures import ThreadPoolExecutor, as_completed
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QRadioButton,
   QFileDialog, QMessageBox, QTextEdit, QGroupBox, QProgressBar
)

# 注册 HEIF 解码器
pillow_heif.register_heif_opener()


class ConvertThread(QThread):
    log_signal = Signal(str, str)  # 修改信号：(消息内容, 颜色)
    progress_signal = Signal(int)
    finished_signal = Signal(int)

    def __init__(self, input_dir, output_dir, out_format):
        super().__init__()
        self.input_dir = input_dir
        self.output_dir = output_dir
        self.out_format = out_format
        self.raw_exts = (".arw",)
        self.hif_exts = (".hif", ".heic")
        self.max_workers = max(1, (os.cpu_count() or 4) - 1)
        self.failed_list = []  # 记录失败列表

    def slim_exif(self, exif_bytes):
        try:
            if not exif_bytes: return None
            exif_dict = piexif.load(exif_bytes)
            if "Exif" in exif_dict and piexif.ExifIFD.MakerNote in exif_dict["Exif"]:
                del exif_dict["Exif"][piexif.ExifIFD.MakerNote]
            return piexif.dump(exif_dict)
        except Exception as e:
            self.log_signal.emit(f"  [警告] EXIF 解析/瘦身失败: {e}", "#FFA500")  # 橙色警告
            return None

    def process_single_file(self, file):
        file_path = os.path.join(self.input_dir, file)
        ext = os.path.splitext(file)[1].lower()
        self.log_signal.emit(f"正在处理：{file}", "#00FF00")

        try:
            rgb = None
            exif_bytes = None
            if ext in self.raw_exts:
                with rawpy.imread(file_path) as raw:
                    rgb = raw.postprocess()
                exif_bytes = piexif.dump(piexif.load(file_path))
            elif ext in self.hif_exts:
                heif_file = pillow_heif.read_heif(file_path)
                rgb = np.array(heif_file)
                exif_bytes = heif_file.info.get("exif")

            if rgb is None: return False, file, "读取失败"

            processed_exif = exif_bytes
            if self.out_format == "jpg" and exif_bytes and len(exif_bytes) > 60000:
                processed_exif = self.slim_exif(exif_bytes)

            base_name = os.path.splitext(file)[0]
            output_path = os.path.join(self.output_dir, f"{base_name}.{self.out_format}")
            write_params = {"quality": 100}
            if self.out_format == "jpg": write_params["subsampling"] = 0

            if processed_exif:
                imageio.imwrite(output_path, rgb, exif=processed_exif, **write_params)
            else:
                imageio.imwrite(output_path, rgb, **write_params)

            stat = os.stat(file_path)
            os.utime(output_path, (stat.st_atime, stat.st_mtime))
            self.log_signal.emit(f"  成功：{os.path.basename(output_path)}", "#00FF00")
            return True, file, None
        except Exception as e:
            return False, file, str(e)

    def run(self):
        os.makedirs(self.output_dir, exist_ok=True)
        files = [f for f in os.listdir(self.input_dir) if f.lower().endswith(self.raw_exts + self.hif_exts)]

        total_files = len(files)
        if total_files == 0:
            self.finished_signal.emit(0)
            return

        count = 0
        completed = 0
        self.failed_list = []

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_file = {executor.submit(self.process_single_file, f): f for f in files}
            for future in as_completed(future_to_file):
                success, filename, error_msg = future.result()
                completed += 1
                if success:
                    count += 1
                else:
                    self.failed_list.append((filename, error_msg))
                    self.log_signal.emit(f"  失败 {filename}：{error_msg}", "#FF0000")

                self.progress_signal.emit(int((completed / total_files) * 100))

        # 最终汇总
        self.log_signal.emit(f"\n--- 转换完成，共处理 {count} 个文件 ---", "#00FF00")

        # 统一红色打印失败列表
        if self.failed_list:
            self.log_signal.emit("\n以下文件转换失败：", "#FF0000")
            for f_name, err in self.failed_list:
                self.log_signal.emit(f"  [X] {f_name} 原因: {err}", "#FF0000")

        self.finished_signal.emit(count)


class ARWConverterGUI(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Sony ARW/HIF 批量转换工具")
        self.resize(700, 550)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        input_group = QGroupBox("路径设置")
        input_vbox = QVBoxLayout()

        # 输入
        input_layout = QHBoxLayout()
        input_layout.addWidget(QLabel("输入文件夹:"))
        self.input_entry = QLineEdit()
        self.input_entry.setPlaceholderText("选择包含 .ARW / .HIF 的文件夹")
        input_layout.addWidget(self.input_entry)
        input_btn = QPushButton("选择")
        input_btn.clicked.connect(self.select_input_dir)
        input_layout.addWidget(input_btn)
        input_vbox.addLayout(input_layout)

        # 输出
        output_layout = QHBoxLayout()
        output_layout.addWidget(QLabel("输出文件夹:"))
        self.output_entry = QLineEdit()
        self.output_entry.setPlaceholderText("选择图片保存位置")
        output_layout.addWidget(self.output_entry)
        output_btn = QPushButton("选择")
        output_btn.clicked.connect(self.select_output_dir)
        output_layout.addWidget(output_btn)
        input_vbox.addLayout(output_layout)

        input_group.setLayout(input_vbox)
        layout.addWidget(input_group)

        # 格式
        format_group = QGroupBox("输出格式")
        format_layout = QHBoxLayout()
        self.jpg_radio = QRadioButton("JPEG (高兼容性，自动压缩EXIF)")
        self.png_radio = QRadioButton("PNG (无损，支持大EXIF)")
        self.jpg_radio.setChecked(True)
        format_layout.addWidget(self.jpg_radio)
        format_layout.addWidget(self.png_radio)
        format_group.setLayout(format_layout)
        layout.addWidget(format_group)

        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)

        # 按钮
        self.start_btn = QPushButton("开始转换")
        self.start_btn.setFixedHeight(40)
        self.start_btn.setStyleSheet("font-size: 15px; font-weight: bold; background-color: #2E7D32; color: white;")
        self.start_btn.clicked.connect(self.start_conversion)
        layout.addWidget(self.start_btn)

        # 日志
        layout.addWidget(QLabel("处理日志:"))
        self.status_text = QTextEdit()
        self.status_text.setReadOnly(True)
        self.status_text.setStyleSheet("background-color: #1E1E1E; color: #00FF00; font-family: Consolas;")
        layout.addWidget(self.status_text)

    def select_input_dir(self):
        path = QFileDialog.getExistingDirectory(self, "选择输入文件夹")
        if path: self.input_entry.setText(path)

    def select_output_dir(self):
        path = QFileDialog.getExistingDirectory(self, "选择输出文件夹")
        if path: self.output_entry.setText(path)

    def log(self, message, color="#00FF00"):
        # 使用 HTML 标签来实现颜色区分
        self.status_text.append(f'<span style="color:{color};">{message}</span>')
        self.status_text.ensureCursorVisible()

    def start_conversion(self):
        input_dir = self.input_entry.text().strip()
        output_dir = self.output_entry.text().strip()
        if not os.path.isdir(input_dir) or not os.path.isdir(output_dir):
            QMessageBox.critical(self, "错误", "请检查输入和输出路径是否正确！")
            return

        out_format = "jpg" if self.jpg_radio.isChecked() else "png"
        self.start_btn.setEnabled(False)
        self.start_btn.setText("正在处理...")
        self.status_text.clear()
        self.progress_bar.setValue(0)

        self.thread = ConvertThread(input_dir, output_dir, out_format)
        self.thread.log_signal.connect(self.log)
        self.thread.progress_signal.connect(self.progress_bar.setValue)
        self.thread.finished_signal.connect(self.on_finished)
        self.thread.start()

    def on_finished(self, count):
        self.start_btn.setEnabled(True)
        self.start_btn.setText("开始转换")
        QMessageBox.information(self, "完成", f"转换任务已结束！\n成功处理 {count} 个文件。")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = ARWConverterGUI()
    window.show()
    sys.exit(app.exec())