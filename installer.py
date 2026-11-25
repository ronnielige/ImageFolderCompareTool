#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""图片对比工具 - 图形安装程序 (专业化界面)

打包时把 onedir 应用目录作为 payload 嵌入:
  PyInstaller --add-data "dist/图片对比工具;payload"
安装时把 payload 复制到用户选择的目录, 并创建桌面/开始菜单快捷方式。
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QIcon, QPixmap, QFont
from PySide6.QtWidgets import (QApplication, QFileDialog, QFrame, QHBoxLayout,
                               QLabel, QLineEdit, QMessageBox, QProgressBar,
                               QPushButton, QVBoxLayout, QWidget)

APP_NAME = '图片对比工具'
INSTALLER_TITLE = '图片文件夹对比工具'
DEFAULT_DIR = os.path.join(
    os.environ.get('LOCALAPPDATA', os.path.expanduser('~')),
    'Programs', APP_NAME)
CREATE_NO_WINDOW = 0x08000000

# ----------------------------------------------------------- 界面样式 (QSS)
QSS = '''
#root { background: #f5f6f8; }
#banner {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                stop:0 #16324f, stop:0.55 #24527d, stop:1 #2d6ca3);
    border-radius: 0px;
}
#bannerTitle { color: #ffffff; font-size: 21px; font-weight: 600; }
#bannerSub   { color: #b9d0e6; font-size: 12px; }
#bodyTitle   { color: #2b3440; font-size: 14px; font-weight: 600; }
#hint        { color: #6b7684; font-size: 12px; }
#feature     { color: #35507a; font-size: 12px; }
QLineEdit {
    border: 1px solid #cfd6dd; border-radius: 4px;
    padding: 6px 9px; background: #ffffff; font-size: 13px;
}
QLineEdit:focus { border: 1px solid #2d6ca3; }
#browseBtn {
    background: #ffffff; border: 1px solid #cfd6dd; border-radius: 4px;
    padding: 6px 16px; color: #2b3440;
}
#browseBtn:hover { border-color: #2d6ca3; color: #1b4b7a; }
#primaryBtn {
    background: #2563eb; color: #ffffff; border: none; border-radius: 4px;
    padding: 8px 34px; font-size: 14px; font-weight: 600;
}
#primaryBtn:hover  { background: #1d4ed8; }
#primaryBtn:pressed{ background: #1e40af; }
#primaryBtn:disabled { background: #a9c0ea; color: #eef2fb; }
#secondaryBtn {
    background: #ffffff; border: 1px solid #cfd6dd; border-radius: 4px;
    padding: 8px 24px; color: #2b3440; font-size: 14px;
}
#secondaryBtn:hover { border-color: #9aa6b4; background: #f0f2f5; }
QProgressBar {
    border: none; background: #e2e7ee; border-radius: 5px;
    min-height: 10px; max-height: 10px;
}
QProgressBar::chunk {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 #2563eb, stop:1 #3b82f6);
    border-radius: 5px;
}
#statusLabel { color: #55606e; font-size: 12px; }
#divider { background: #e4e8ee; max-height: 1px; border: none; }
'''


def payload_dir():
    base = getattr(sys, '_MEIPASS', Path(__file__).resolve().parent)
    return Path(base) / 'payload'


def find_app_icon():
    """从 payload 的应用目录里找 icon.ico (打包后存在; 直接运行脚本时可能没有)。"""
    app_dir = payload_dir() / APP_NAME
    for name in ('icon.ico', 'icon.png'):
        p = app_dir / name
        if p.exists():
            return p
    return None


def create_shortcut(lnk_path, target):
    """用 WScript.Shell COM 创建 .lnk 快捷方式 (无窗口)。"""
    ps = (
        "$ws=New-Object -ComObject WScript.Shell;"
        f"$s=$ws.CreateShortcut('{lnk_path}');"
        f"$s.TargetPath='{target}';"
        f"$s.WorkingDirectory='{os.path.dirname(target)}';"
        f"$s.IconLocation='{target}';"
        "$s.Save()"
    )
    subprocess.run(['powershell', '-NoProfile', '-Command', ps],
                   creationflags=CREATE_NO_WINDOW,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def desktop_dir():
    ps = "[Environment]::GetFolderPath('Desktop')"
    r = subprocess.run(['powershell', '-NoProfile', '-Command', ps],
                       capture_output=True, text=True,
                       creationflags=CREATE_NO_WINDOW)
    return r.stdout.strip() or os.path.join(
        os.environ.get('USERPROFILE', os.path.expanduser('~')), 'Desktop')


# ------------------------------------------------- 后台复制线程 (不卡界面)
class CopyWorker(QThread):
    progress = Signal(int, int, str)   # 已完成数, 总数, 当前文件名
    finished_ok = Signal(str)          # 安装目标目录
    failed = Signal(str)

    def __init__(self, src, dst, parent=None):
        super().__init__(parent)
        self.src = src
        self.dst = dst

    def run(self):
        try:
            target = self.dst / APP_NAME
            files = [f for f in self.src.rglob('*') if f.is_file()]
            total = len(files)
            done = 0
            for f in files:
                rel = f.relative_to(self.src)
                dest = target / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(f, dest)
                done += 1
                if done % 5 == 0 or done == total:
                    self.progress.emit(done, total, str(rel))
            self.finished_ok.emit(str(target))
        except Exception as e:
            self.failed.emit(str(e))


class InstallerWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setObjectName('root')
        self.setWindowTitle(f'{INSTALLER_TITLE} - 安装向导')
        icon = find_app_icon()
        if icon:
            self.setWindowIcon(QIcon(str(icon)))
        self.setFixedSize(640, 460)
        self.worker = None

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # ---------------- 顶部横幅 ----------------
        banner = QFrame()
        banner.setObjectName('banner')
        banner.setFixedHeight(128)
        bl = QHBoxLayout(banner)
        bl.setContentsMargins(32, 20, 32, 20)
        bl.setSpacing(18)
        icon_lbl = QLabel()
        icon_p = find_app_icon()
        if icon_p:
            pm = QPixmap(str(icon_p)).scaled(
                72, 72, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            icon_lbl.setPixmap(pm)
        icon_lbl.setFixedSize(72, 72)
        bl.addWidget(icon_lbl, 0, Qt.AlignVCenter)
        text_col = QVBoxLayout()
        text_col.setSpacing(6)
        t1 = QLabel(APP_NAME)
        t1.setObjectName('bannerTitle')
        t2 = QLabel('多目录同步缩放对比 · 左右单屏对比 · 大图后台流畅加载')
        t2.setObjectName('bannerSub')
        text_col.addWidget(t1)
        text_col.addWidget(t2)
        bl.addLayout(text_col, 1)
        lay.addWidget(banner)

        # ---------------- 内容区 ----------------
        body = QVBoxLayout()
        body.setContentsMargins(32, 22, 32, 10)
        body.setSpacing(10)

        title = QLabel('选择安装位置')
        title.setObjectName('bodyTitle')
        body.addWidget(title)

        row = QHBoxLayout()
        row.setSpacing(8)
        self.dir_edit = QLineEdit(DEFAULT_DIR)
        b_browse = QPushButton('浏览...')
        b_browse.setObjectName('browseBtn')
        b_browse.setCursor(Qt.PointingHandCursor)
        b_browse.clicked.connect(self.browse)
        row.addWidget(self.dir_edit, 1)
        row.addWidget(b_browse)
        body.addLayout(row)

        hint = QLabel(f'将安装到所选目录下的 "{APP_NAME}" 文件夹, '
                      '并在桌面和开始菜单创建快捷方式 (无需管理员权限)。')
        hint.setObjectName('hint')
        hint.setWordWrap(True)
        body.addWidget(hint)

        feat = QLabel('✓  多文件夹 N 分屏同步缩放拖动    '
                      '✓  LR 自动对齐    '
                      '✓  双击 适配/100% 切换')
        feat.setObjectName('feature')
        body.addWidget(feat)

        body.addStretch(1)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        body.addWidget(self.progress)

        self.status = QLabel('准备就绪')
        self.status.setObjectName('statusLabel')
        body.addWidget(self.status)
        lay.addLayout(body)

        # ---------------- 分隔线 + 底部按钮 ----------------
        divider = QFrame()
        divider.setObjectName('divider')
        divider.setFixedHeight(1)
        lay.addWidget(divider)

        foot = QHBoxLayout()
        foot.setContentsMargins(32, 12, 32, 18)
        foot.setSpacing(10)
        foot.addStretch(1)
        b_exit = QPushButton('退出')
        b_exit.setObjectName('secondaryBtn')
        b_exit.setCursor(Qt.PointingHandCursor)
        b_exit.clicked.connect(self.close)
        self.b_install = QPushButton('立即安装')
        self.b_install.setObjectName('primaryBtn')
        self.b_install.setCursor(Qt.PointingHandCursor)
        self.b_install.clicked.connect(self.install)
        foot.addWidget(b_exit)
        foot.addWidget(self.b_install)
        lay.addLayout(foot)

        self.setStyleSheet(QSS)

    def browse(self):
        d = QFileDialog.getExistingDirectory(self, '选择安装目录',
                                             self.dir_edit.text())
        if d:
            self.dir_edit.setText(d)

    def install(self):
        if self.worker is not None:
            return
        src = payload_dir()
        dst = Path(self.dir_edit.text().strip())
        if not src.is_dir() or not (src / APP_NAME).is_dir():
            QMessageBox.critical(self, '错误',
                                 '安装包数据缺失, 请重新下载安装程序。')
            return
        self.b_install.setEnabled(False)
        self.status.setText('正在安装, 请稍候...')
        self.worker = CopyWorker(src, dst)
        self.worker.progress.connect(self._on_progress)
        self.worker.finished_ok.connect(self._on_done)
        self.worker.failed.connect(self._on_fail)
        self.worker.start()

    def _on_progress(self, done, total, name):
        self.progress.setRange(0, 100)
        self.progress.setValue(int(done * 100 / max(total, 1)))
        self.status.setText(f'复制文件 {done}/{total} ...')

    def _on_fail(self, msg):
        self.worker = None
        self.b_install.setEnabled(True)
        self.progress.setValue(0)
        self.status.setText('安装失败')
        QMessageBox.critical(self, '安装失败', f'错误: {msg}')

    def _on_done(self, target_str):
        self.progress.setValue(100)
        self.status.setText('创建快捷方式...')
        QApplication.processEvents()
        target = Path(target_str)
        exe = target / f'{APP_NAME}.exe'
        try:
            # 写卸载脚本
            uninstall = target / f'卸载{APP_NAME}.cmd'
            uninstall.write_text(
                '@echo off\r\n'
                f'taskkill /f /im "{APP_NAME}.exe" >nul 2>&1\r\n'
                f'rd /s /q "{target}"\r\n'
                'del "%USERPROFILE%\\Desktop\\'
                f'{APP_NAME}.lnk" >nul 2>&1\r\n'
                'del "%APPDATA%\\Microsoft\\Windows\\Start Menu\\Programs\\'
                f'{APP_NAME}.lnk" >nul 2>&1\r\n',
                encoding='gbk')
            # 快捷方式 (桌面 + 开始菜单)
            create_shortcut(os.path.join(desktop_dir(), f'{APP_NAME}.lnk'),
                            str(exe))
            sm = os.path.join(os.environ.get('APPDATA', ''),
                              r'Microsoft\Windows\Start Menu\Programs')
            create_shortcut(os.path.join(sm, f'{APP_NAME}.lnk'), str(exe))
        except Exception as e:
            self.worker = None
            self.b_install.setEnabled(True)
            self.status.setText('安装失败')
            QMessageBox.critical(self, '安装失败', f'错误: {e}')
            return
        self.worker = None
        self.status.setText(f'安装完成: {target}')
        self.b_install.setEnabled(True)
        self.b_install.setText('完成')
        r = QMessageBox.question(
            self, '安装完成',
            f'已安装到:\n{target}\n\n桌面和开始菜单已创建快捷方式。\n\n'
            '是否立即启动?',
            QMessageBox.Yes | QMessageBox.No)
        if r == QMessageBox.Yes:
            subprocess.Popen([str(exe)], cwd=str(target))
            self.close()


def main():
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    win = InstallerWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
