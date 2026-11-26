#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
多目录图片对比工具 (Multi-folder Image Compare)
------------------------------------------------
- 选择 N 个文件夹(或自动发现)，左侧列出所有文件夹共有的图片
- 点击图片后主区 N 分屏，每屏显示一个文件夹里的同名图片
- 滚轮缩放(以鼠标为中心)、拖动平移，所有分屏同步显示同一图像区域
- 每屏显示文件夹名、图片尺寸、缩放比例
快捷键: ←/→ 切换图片, F 适配窗口, 1 = 100% 缩放, 空格 下一张
双击图片: 适配窗口 / 100% 显示切换 (100% 时以双击位置为中心, 全部分屏同步)
依赖: pip install PySide6
"""
import math
import re
import sys
import time
from pathlib import Path

from PySide6.QtCore import (Qt, QPointF, QRectF, Signal, QSettings, QTimer,
                            QObject, QRunnable, QThreadPool, QEvent, QSize)
from PySide6.QtGui import (QAction, QBrush, QColor, QPainter, QPixmap,
                           QKeySequence, QShortcut, QIcon, QImageReader,
                           QPalette)
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QFileDialog,
                               QFrame, QGridLayout, QHBoxLayout, QInputDialog,
                               QListWidget, QListWidgetItem, QMainWindow,
                               QMessageBox, QPushButton, QSplitter,
                               QAbstractItemView, QVBoxLayout, QWidget,
                               QListView, QTreeView,
                               QLabel)

IMAGE_EXTS = {'.png', '.jpg', '.jpeg', '.bmp', '.webp', '.tif', '.tiff'}
DEFAULT_BASE = r'\\172.17.35.42\local-disk3\lr\datasets'
ZOOM_MIN, ZOOM_MAX = 0.01, 32.0
MAX_PANES = 9          # 最多同时显示的分屏数 (3x3 网格)
LEFT_LIST_SHORTCUT = 'Ctrl+B'

# ------------------------------------------------- 现代浅色主题 (QSS)
MODERN_QSS = '''
* { font-size: 13px; }
QMainWindow { background: #f5f6f8; }

/* ---------- 按钮 ---------- */
QPushButton {
    background: #ffffff; color: #2b3440;
    border: 1px solid #d4dae2; border-radius: 6px;
    padding: 6px 14px;
}
QPushButton:hover  { border-color: #2d6ca3; color: #1b4b7a; background: #f4f8fc; }
QPushButton:pressed { background: #e4eef8; }
QPushButton:disabled { color: #a5aeb9; border-color: #e2e6ec; background: #f5f6f8; }
QPushButton:focus { outline: none; }

/* 强调按钮: 左右对比 / 全屏 */
QPushButton#btnSplit, QPushButton#btnFs {
    background: #eef4fb; color: #1b4b7a; border-color: #bcd0e4;
}
QPushButton#btnSplit:hover, QPushButton#btnFs:hover { background: #e0edf9; }
QPushButton#btnSplit:checked {
    background: #2563eb; color: #ffffff; border-color: #2563eb; font-weight: 600;
}

/* ---------- 列表 (卡片式) ---------- */
QListWidget {
    background: #ffffff; border: 1px solid #e2e6ec; border-radius: 8px;
    padding: 4px; outline: 0;
}
QListWidget::item { padding: 5px 8px; border-radius: 5px; margin: 1px 2px; color: #2b3440; }
QListWidget::item:hover { background: #f0f4f9; }
QListWidget::item:selected { background: #e1eefc; color: #1b4b7a; }

/* 文件夹列表放的是整行控件(setItemWidget), 不能再挤内边距, 否则文字被裁半截 */
QListWidget#folderList::item { padding: 0px 2px; margin: 0px; }

/* ---------- 复选框 (完全使用原生勾选框, 只调文字可读性) ---------- */
QCheckBox { color: #1f2733; spacing: 6px; background: transparent; }

/* ---------- 左栏 / 工具栏 ---------- */
QFrame#leftPanel { background: #f5f6f8; border: none; border-right: 1px solid #e4e8ee; }
QFrame#toolBar { background: #ffffff; border: none; border-bottom: 1px solid #e4e8ee; }
QLabel#sectionLabel { color: #8a94a2; font-size: 12px; font-weight: 600; padding: 2px; }
QLabel#zoomChip {
    background: #eef4fb; color: #1b4b7a; border: none;
    border-radius: 11px; padding: 4px 12px; font-weight: 600;
}

/* ---------- 分隔手柄 / 状态栏 ---------- */
QSplitter::handle { background: #f5f6f8; }
QSplitter::handle:hover { background: #cfe0f2; }
QStatusBar { background: #f5f6f8; color: #6b7684; border-top: 1px solid #e4e8ee; }
QStatusBar::item { border: none; }

/* ---------- 细滚动条 ---------- */
QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; }
QScrollBar::handle:vertical { background: #c9d2dd; border-radius: 4px; min-height: 30px; }
QScrollBar::handle:vertical:hover { background: #a8b6c6; }
QScrollBar:horizontal { background: transparent; height: 10px; margin: 2px; }
QScrollBar::handle:horizontal { background: #c9d2dd; border-radius: 4px; min-width: 30px; }
QScrollBar::handle:horizontal:hover { background: #a8b6c6; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }

/* ---------- 提示气泡 ---------- */
QToolTip {
    background: #2b3440; color: #ffffff; border: none;
    padding: 6px 9px; border-radius: 4px; font-size: 12px;
}
'''


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def natural_key(s):
    return [int(t) if t.isdigit() else t.lower()
            for t in re.split(r'(\d+)', s)]


def list_image_files(folder: Path):
    try:
        return [f.name for f in folder.iterdir()
                if f.is_file() and f.suffix.lower() in IMAGE_EXTS]
    except OSError:
        return []


def stem_map(folder: Path):
    """{文件名主干(不含扩展名): 实际文件名}，用于跨 png/jpg 匹配同名图。"""
    return {Path(f).stem: f for f in list_image_files(folder)}


def folder_has_images(folder: Path):
    return len(list_image_files(folder)) > 0


def _mem_available():
    """系统当前可用物理内存 (字节); 查询失败返回 None。"""
    try:
        import ctypes

        class _MEMSTATUSEX(ctypes.Structure):
            _fields_ = [
                ('dwLength', ctypes.c_ulong),
                ('dwMemoryLoad', ctypes.c_ulong),
                ('ullTotalPhys', ctypes.c_ulonglong),
                ('ullAvailPhys', ctypes.c_ulonglong),
                ('ullTotalPageFile', ctypes.c_ulonglong),
                ('ullAvailPageFile', ctypes.c_ulonglong),
                ('ullTotalVirtual', ctypes.c_ulonglong),
                ('ullAvailVirtual', ctypes.c_ulonglong),
                ('ullAvailExtendedVirtual', ctypes.c_ulonglong),
            ]

        m = _MEMSTATUSEX()
        m.dwLength = ctypes.sizeof(_MEMSTATUSEX)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m)):
            return int(m.ullAvailPhys)
    except Exception:
        pass
    try:
        import psutil
        return int(psutil.virtual_memory().available)
    except Exception:
        return None


def _estimate_image_bytes(path):
    """只读文件头估算解码后内存占用 (宽×高×4 字节); 读不到返回 None。"""
    try:
        r = QImageReader(str(path))
        r.setAllocationLimit(0)
        s = r.size()
        if s.isValid() and s.width() > 0 and s.height() > 0:
            return s.width() * s.height() * 4
    except Exception:
        pass
    return None


def load_pixmap(path):
    """加载图片为 QPixmap。

    Qt 6 的 QImageReader 默认有 256MB 解码内存上限, 16K 图(约 512MB+)会
    静默加载失败返回空图, 这里显式关闭上限以支持 16K/32K 超大图。
    """
    reader = QImageReader(str(path))
    reader.setAllocationLimit(0)
    img = reader.read()
    if img.isNull():
        return None
    return QPixmap.fromImage(img)


# ------------------------------------------------- 后台加载 (防大图卡死界面)
class _PathJumpFilter(QObject):
    """Look In 输入框的事件过滤器: 拦截回车, 跳转到粘贴的目录而不关闭对话框。"""

    def __init__(self, dlg, combo):
        super().__init__(combo)
        self.dlg = dlg
        self.combo = combo

    def eventFilter(self, obj, ev):
        if ev.type() == QEvent.KeyPress and ev.key() in (Qt.Key_Return,
                                                         Qt.Key_Enter):
            path = self.combo.currentText().strip().strip('"').strip("'")
            if path:
                self.dlg.setDirectory(path)
                le = self.combo.lineEdit()
                if le:
                    le.clear()       # 清空输入, 提示已跳转
            return True              # 吞掉回车, 不传给对话框默认按钮
        return False


class _LoadSignals(QObject):
    """工作线程 -> 主线程的结果信使。

    所有 worker 共用同一个对象 (由主窗口持有), 避免信号发送者
    在排队事件送达前被销毁。
    """
    done = Signal(int, int, object, object)        # gen, folder_index, QImage|None, path_str|None
    scan_done = Signal(int, object, dict)          # gen, folder, {stem: filename}
    discover_done = Signal(int, str, list)         # gen, base_path, [子目录路径]


class _ImageLoadWorker(QRunnable):
    """在后台线程解码一张图片 (QImageReader 可安全用于非 GUI 线程)。"""

    def __init__(self, gen, folder_index, path, sig):
        super().__init__()
        self.gen = gen
        self.folder_index = folder_index
        self.path = path
        self.sig = sig

    def run(self):
        reader = QImageReader(str(self.path))
        reader.setAllocationLimit(0)   # 16K/32K 大图不受 256MB 上限影响
        img = reader.read()
        ok = not img.isNull()
        try:
            self.sig.done.emit(self.gen, self.folder_index,
                               img if ok else None,
                               str(self.path) if ok else None)
        except RuntimeError:
            pass   # 窗口已销毁, 结果无处可投递


class _ScanWorker(QRunnable):
    """在后台线程扫描一个文件夹的图片清单 (网络盘 iterdir 可能很慢)。"""

    def __init__(self, gen, folder, sig):
        super().__init__()
        self.gen = gen
        self.folder = folder
        self.sig = sig

    def run(self):
        try:
            names = stem_map(self.folder)
        except Exception:
            names = {}
        try:
            self.sig.scan_done.emit(self.gen, self.folder, names)
        except RuntimeError:
            pass   # 窗口已销毁, 结果无处可投递


class _DiscoverWorker(QRunnable):
    """在后台线程枚举根目录下所有含图片的子目录 (自动发现)。"""

    def __init__(self, gen, base, sig):
        super().__init__()
        self.gen = gen
        self.base = base
        self.sig = sig

    def run(self):
        subs = []
        try:
            subs = [str(d) for d in sorted(self.base.iterdir())
                    if d.is_dir() and folder_has_images(d)]
        except OSError:
            pass
        try:
            self.sig.discover_done.emit(self.gen, str(self.base), subs)
        except RuntimeError:
            pass   # 窗口已销毁, 结果无处可投递


# ---------------------------------------------------------------- ViewState
class ViewState:
    """缩放 + 视口中心(图像坐标)。所有分屏共享同一个实例即实现同步。"""

    def __init__(self):
        self.zoom = 1.0
        self.center = QPointF(0, 0)   # 视口中心对应的图像坐标

    def copy(self):
        st = ViewState()
        st.zoom = self.zoom
        st.center = QPointF(self.center)
        return st


# ---------------------------------------------------------------- checker
_CHECKER = None


def checker_brush():
    global _CHECKER
    if _CHECKER is None:
        pm = QPixmap(16, 16)
        pm.fill(QColor(230, 230, 230))
        p = QPainter(pm)
        p.fillRect(0, 0, 8, 8, QColor(200, 200, 200))
        p.fillRect(8, 8, 8, 8, QColor(200, 200, 200))
        p.end()
        _CHECKER = QBrush(pm)
    return _CHECKER


# ---------------------------------------------------------------- ImagePane
class ImagePane(QWidget):
    """单分屏：自绘图像，滚轮缩放 / 拖动平移，通过共享 ViewState 同步。

    视图坐标基于"参考分辨率"(通常为最大分辨率那张图, 如 HR)。
    scale = 参考宽 / 本图宽，因此低分辨率图(如 lr)会被自动放大对齐，
    所有分屏在同一参考坐标系下缩放/平移，显示区域严格对齐。
    """
    viewChanged = Signal()
    hoverMoved = Signal(object)   # 鼠标所在参考坐标 (QPointF) 或 None (离开)

    def __init__(self, title, shared_state, parent=None):
        super().__init__(parent)
        self.title = title
        self.shared = shared_state
        self.local = shared_state.copy()
        self.sync = True
        self.pixmap = None
        self.path = None
        self.placeholder = '未选择图片'
        self._panning = False
        self._last_pos = QPointF()
        self._smooth = True
        self._hover_ref = None    # 鼠标位置指示 (参考坐标)
        self.scale = 1.0          # 参考坐标 -> 本图像素 的比例
        self.ref_w = 0
        self.ref_h = 0
        self._loading_t0 = None   # 非 None 表示本屏图片正在后台加载 (计时用)
        self._loading_n = 0       # 加载中的槽位计数 (左右对比有 A/B 两张)
        self.setMinimumSize(160, 120)
        self.setMouseTracking(True)   # 不按键也接收鼠标移动 (跨屏位置指示)
        self.setAttribute(Qt.WA_OpaquePaintEvent)
        self.setFocusPolicy(Qt.NoFocus)

    # ---------- state ----------
    def state(self):
        return self.shared if self.sync else self.local

    def set_sync(self, on):
        if on:
            self.sync = True
        else:
            # 关闭同步时，以当前共享状态为各自起点
            self.local = self.shared.copy()
            self.sync = False
        self.update()

    # ---------- image ----------
    def set_reference(self, w, h):
        """设置参考分辨率(取本批图片中的最大宽/高)。"""
        self.ref_w, self.ref_h = w, h
        if self.pixmap is not None and w:
            self.scale = w / self.pixmap.width()
        self.update()

    def set_image(self, pixmap, path=None, note=None):
        self.pixmap = pixmap
        self.path = path
        # note 优先 (如 '内存不足，未加载'); 否则 path 为空时显示默认占位
        if note is not None:
            self.placeholder = note
        else:
            self.placeholder = '缺少对应图片' if path is None else ''
        if pixmap is not None and self.ref_w:
            self.scale = self.ref_w / pixmap.width()
        else:
            self.scale = 1.0
        self.update()

    # ---------- loading badge ----------
    def set_loading(self, on):
        """本屏图片开始/停止后台加载; 全部槽位完成才熄灭角标 (左右对比 A/B 各计一次)。"""
        if on:
            if self._loading_n == 0:
                self._loading_t0 = time.monotonic()
            self._loading_n += 1
        else:
            self._loading_n = max(0, self._loading_n - 1)
            if self._loading_n == 0:
                self._loading_t0 = None
        self.update()

    def _draw_loading_badge(self, p):
        """右上角橙色角标: '加载中 2.4s', 给用户加载耗时预期。"""
        if self._loading_t0 is None:
            return
        text = f'加载中 {time.monotonic() - self._loading_t0:.1f}s'
        fm = p.fontMetrics()
        tw = fm.horizontalAdvance(text) + 14
        th = fm.height() + 6
        x = self.width() - tw
        p.fillRect(x, 0, tw, th, QColor(214, 106, 20, 230))
        p.setPen(QColor(255, 255, 255))
        p.drawText(QRectF(x, 0, tw, th), Qt.AlignCenter, text)

    # ---------- geometry helpers ----------
    def _ref_size(self):
        if self.pixmap is None:
            return 0, 0
        return (self.ref_w or self.pixmap.width(),
                self.ref_h or self.pixmap.height())

    def _image_rect(self):
        """本屏图像的显示矩形。

        统一映射: widget(r) = w/2 - (r - center)*zoom, r 为参考坐标。
        scale 只影响矩形宽高(低分辨率图拉伸到与参考相同的显示尺寸),
        不影响中心偏移——这样所有屏显示的参考区域严格一致。
        """
        st = self.state()
        z = st.zoom                       # 参考缩放 (widget px / ref px)
        z_img = z * self.scale            # 本图像素缩放
        cx = self.width() / 2 - st.center.x() * z
        cy = self.height() / 2 - st.center.y() * z
        return QRectF(cx, cy, self.pixmap.width() * z_img,
                      self.pixmap.height() * z_img)

    def _clamp_center(self):
        st = self.state()
        if self.pixmap is None:
            return
        w, h = self._ref_size()
        st.center = QPointF(clamp(st.center.x(), 0, w),
                            clamp(st.center.y(), 0, h))

    # ---------- interaction ----------
    def wheelEvent(self, e):
        if self.pixmap is None:
            return
        factor = 1.25 ** (e.angleDelta().y() / 120.0)
        self._zoom_at(QPointF(e.position()), factor)

    def _zoom_at(self, pos, factor):
        st = self.state()
        z0 = st.zoom                      # 全部按参考坐标计算, 与 scale 无关
        z1 = clamp(z0 * factor, ZOOM_MIN, ZOOM_MAX)
        if abs(z1 - z0) < 1e-9:
            return
        vx = pos.x() - self.width() / 2
        vy = pos.y() - self.height() / 2
        ix = st.center.x() + vx / z0
        iy = st.center.y() + vy / z0
        st.zoom = z1
        st.center = QPointF(ix - vx / z1, iy - vy / z1)
        self._clamp_center()
        self.viewChanged.emit()

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton and self.pixmap is not None:
            self._panning = True
            self._last_pos = QPointF(e.position())
            self.setCursor(Qt.ClosedHandCursor)
            self.grabMouse()

    def mouseMoveEvent(self, e):
        pos = QPointF(e.position())
        if self._panning:
            d = pos - self._last_pos
            self._last_pos = pos
            st = self.state()
            z = st.zoom                    # 平移也按参考缩放, 各屏速度天然一致
            st.center = QPointF(st.center.x() - d.x() / z,
                                st.center.y() - d.y() / z)
            self._clamp_center()
            self.viewChanged.emit()
        # 广播鼠标所在参考坐标, 其他分屏在相同内容点上画指示标记
        self.hoverMoved.emit(self._pos_to_ref(pos))

    def _pos_to_ref(self, pos):
        """widget 坐标 -> 参考坐标。"""
        st = self.state()
        return QPointF(st.center.x() + (pos.x() - self.width() / 2) / st.zoom,
                       st.center.y() + (pos.y() - self.height() / 2) / st.zoom)

    def _ref_to_pos(self, ref):
        """参考坐标 -> widget 坐标。"""
        st = self.state()
        return QPointF(self.width() / 2 + (ref.x() - st.center.x()) * st.zoom,
                       self.height() / 2 + (ref.y() - st.center.y()) * st.zoom)

    def set_hover(self, ref):
        """接收其他分屏广播的鼠标位置 (参考坐标), None 表示鼠标离开。"""
        self._hover_ref = QPointF(ref) if ref is not None else None
        self.update()

    def mouseReleaseEvent(self, e):
        if self._panning:
            self._panning = False
            self.setCursor(Qt.ArrowCursor)
            self.releaseMouse()
            self._smooth = True
            self.update()

    def mouseDoubleClickEvent(self, e):
        self.toggle_fit_100(e.position())   # 适配 <-> 100% (鼠标点为中心)

    def enterEvent(self, e):
        self.setCursor(Qt.ArrowCursor)

    def leaveEvent(self, e):
        if not self._panning:
            self.hoverMoved.emit(None)   # 鼠标离开分屏, 清除所有指示标记

    # ---------- actions ----------
    def _fit_zoom(self, padding=8, fill=False):
        """计算适配视口的缩放值 (不应用)。"""
        w, h = self._ref_size()
        if w == 0 or h == 0:
            return None
        vw = max(1, self.width() - padding * 2)
        vh = max(1, self.height() - padding * 2)
        if fill:
            return max(vw / w, vh / h)
        return min(vw / w, vh / h)

    def fit(self, padding=8, fill=False):
        """适配视口。padding=四周留白(像素); fill=True 时铺满并裁剪超出部分
        (边缘顶满, 沉浸模式), fill=False 时完整显示(允许一侧留边)。"""
        w, h = self._ref_size()
        if w == 0 or h == 0:
            return
        st = self.state()
        st.zoom = self._fit_zoom(padding, fill)
        st.center = QPointF(w / 2, h / 2)
        self.viewChanged.emit()

    def toggle_fit_100(self, pos=None):
        """双击切换: 适配窗口 <-> 100% 显示。

        切到 100% 时以鼠标点击位置为视图中心 (ref 坐标), 所有分屏同步。
        """
        w, h = self._ref_size()
        if w == 0 or h == 0:
            return
        st = self.state()
        fz = self._fit_zoom(padding=8)
        if fz and abs(st.zoom - fz) <= fz * 0.06:
            # 当前处于适配状态 -> 切到 100%, 鼠标点作为视图中心
            if pos is not None:
                ref = self._pos_to_ref(QPointF(pos))
            else:
                ref = QPointF(w / 2, h / 2)
            st.zoom = 1.0
            st.center = QPointF(ref)
            self._clamp_center()
            self.viewChanged.emit()
        else:
            self.fit()   # 非适配状态 (100%/放大中) -> 回到适配窗口

    def zoom_100(self):
        st = self.state()
        old = st.zoom
        st.zoom = 1.0
        if self.pixmap is not None and abs(old - 1.0) > 1e-9:
            self._clamp_center()
        self.viewChanged.emit()

    # ---------- painting ----------
    def paintEvent(self, ev):
        p = QPainter(self)
        st = self.state()
        p.fillRect(self.rect(), QColor(45, 45, 48))

        if self.pixmap is None:
            p.setPen(QColor(170, 170, 170))
            p.drawText(self.rect(), Qt.AlignCenter, self.placeholder)
        else:
            target = self._image_rect()
            p.fillRect(target, checker_brush())
            p.setRenderHint(QPainter.SmoothPixmapTransform, self._smooth)
            p.drawPixmap(target, self.pixmap, QRectF(
                0, 0, self.pixmap.width(), self.pixmap.height()))
            # 边框
            p.setPen(QColor(255, 255, 255, 60))
            p.setBrush(Qt.NoBrush)
            p.drawRect(target)

        self._draw_overlays(p, st.zoom)
        self._draw_hover_marker(p)
        self._draw_loading_badge(p)

    def _draw_hover_marker(self, p):
        """跨屏鼠标位置指示: 圆圈 + 十字准星。"""
        if self._hover_ref is None or self.pixmap is None:
            return
        pos = self._ref_to_pos(self._hover_ref)
        # 仅当位置在本屏附近才画 (拖到视口外就没必要画)
        if not (-30 <= pos.x() <= self.width() + 30
                and -30 <= pos.y() <= self.height() + 30):
            return
        p.setRenderHint(QPainter.Antialiasing, True)
        pen = p.pen()
        pen.setColor(QColor(255, 110, 20))     # 橙色, 图像上足够醒目
        pen.setWidthF(2.0)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        r = 9.0
        p.drawEllipse(pos, r, r)
        d = 6.0
        p.drawLine(QPointF(pos.x() - d - 4, pos.y()), QPointF(pos.x() - d, pos.y()))
        p.drawLine(QPointF(pos.x() + d, pos.y()), QPointF(pos.x() + d + 4, pos.y()))
        p.drawLine(QPointF(pos.x(), pos.y() - d - 4), QPointF(pos.x(), pos.y() - d))
        p.drawLine(QPointF(pos.x(), pos.y() + d), QPointF(pos.x(), pos.y() + d + 4))
        p.setRenderHint(QPainter.Antialiasing, False)

    def _draw_overlays(self, p, zoom):
        p.setRenderHint(QPainter.Antialiasing, False)
        f = p.font()
        f.setPointSize(9)
        p.setFont(f)

        # 左上角: 文件夹名 + 尺寸
        title = self.title
        if self.pixmap is not None:
            title += f'   {self.pixmap.width()}×{self.pixmap.height()}'
        fm = p.fontMetrics()
        tw = fm.horizontalAdvance(title) + 12
        th = fm.height() + 6
        p.fillRect(0, 0, tw, th, QColor(0, 0, 0, 150))
        p.setPen(QColor(235, 235, 235))
        p.drawText(QRectF(6, 2, tw, th), Qt.AlignLeft | Qt.AlignVCenter, title)

        # 右下角: 缩放比例
        ztext = f'{zoom * 100:.1f}%'
        zw = fm.horizontalAdvance(ztext) + 12
        h_ = self.height()
        p.fillRect(self.width() - zw, h_ - th, zw, th, QColor(0, 0, 0, 150))
        p.drawText(QRectF(self.width() - zw, h_ - th, zw, th),
                   Qt.AlignCenter, ztext)


# ---------------------------------------------------------------- SplitComparePane
class SplitComparePane(ImagePane):
    """两文件夹单屏对比: 一块画布, 中间可拖动分割线, 左侧画 A 右侧画 B。

    缩放/平移与普通分屏共用同一 ViewState 和参考坐标系, A/B 严格对齐。
    """

    def __init__(self, title_a, title_b, shared_state, parent=None):
        super().__init__(title_a, shared_state, parent)
        self.title_b = title_b
        self.pixmap_b = None
        self.path_b = None
        self.split = 0.5          # 分割线位置 (占宽度比例 0..1)
        self._drag_div = False

    # ---------- data ----------
    def set_images(self, pa, path_a, pb, path_b):
        self.set_image(pa, path_a)          # 复用基类: pixmap/scale/更新
        self.pixmap_b = pb
        self.path_b = path_b
        self.update()

    # ---------- geometry ----------
    def _ref_size(self):
        if self.pixmap is None:
            if self.pixmap_b is not None:
                return (self.ref_w or self.pixmap_b.width(),
                        self.ref_h or self.pixmap_b.height())
            return (0, 0)
        return (self.ref_w or self.pixmap.width(),
                self.ref_h or self.pixmap.height())

    def _divider_x(self):
        return self.width() * self.split

    def _hit_divider(self, x):
        return abs(x - self._divider_x()) <= 6

    # ---------- interaction ----------
    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton and self._hit_divider(e.position().x()):
            self._drag_div = True
            self.setCursor(Qt.SplitHCursor)
            self.grabMouse()
            return
        super().mousePressEvent(e)          # 其余区域: 正常拖动平移

    def mouseMoveEvent(self, e):
        if self._drag_div:
            self.split = clamp(e.position().x() / max(1, self.width()),
                               0.02, 0.98)
            self.update()
            # 拖分割线时也广播鼠标位置
            self.hoverMoved.emit(self._pos_to_ref(QPointF(e.position())))
            return
        if not self._panning:
            self.setCursor(Qt.SplitHCursor if self._hit_divider(e.position().x())
                           else Qt.ArrowCursor)
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        if self._drag_div:
            self._drag_div = False
            self.setCursor(Qt.ArrowCursor)
            self.releaseMouse()
            return
        super().mouseReleaseEvent(e)

    # ---------- painting ----------
    def paintEvent(self, ev):
        p = QPainter(self)
        st = self.state()
        p.fillRect(self.rect(), QColor(45, 45, 48))

        if self.pixmap is None and self.pixmap_b is None:
            p.setPen(QColor(170, 170, 170))
            p.drawText(self.rect(), Qt.AlignCenter, self.placeholder)
            self._draw_overlays(p, st.zoom)
            return

        target = self._image_rect()
        half = self._divider_x()

        # 左侧: A (clip 后绘制, 分割线两侧各画一次完整图像)
        if self.pixmap is not None:
            p.save()
            p.setClipRect(QRectF(0, 0, half, self.height()))
            p.fillRect(target, checker_brush())
            p.setRenderHint(QPainter.SmoothPixmapTransform, self._smooth)
            p.drawPixmap(target, self.pixmap, QRectF(
                0, 0, self.pixmap.width(), self.pixmap.height()))
            p.restore()
        # 右侧: B
        if self.pixmap_b is not None:
            p.save()
            p.setClipRect(QRectF(half, 0, self.width() - half, self.height()))
            p.fillRect(target, checker_brush())
            p.setRenderHint(QPainter.SmoothPixmapTransform, self._smooth)
            p.drawPixmap(target, self.pixmap_b, QRectF(
                0, 0, self.pixmap_b.width(), self.pixmap_b.height()))
            p.restore()

        # 分割线 (白线 + 中心小把手)
        p.setRenderHint(QPainter.Antialiasing, True)
        pen = p.pen()
        pen.setColor(QColor(255, 255, 255, 200))
        pen.setWidthF(2.0)
        p.setPen(pen)
        p.drawLine(QPointF(half, 0), QPointF(half, self.height()))
        p.setBrush(QColor(255, 255, 255, 200))
        p.setPen(Qt.NoPen)
        p.drawEllipse(QPointF(half, self.height() / 2), 7, 7)
        p.setRenderHint(QPainter.Antialiasing, False)

        self._draw_split_overlays(p, st.zoom)
        self._draw_hover_marker(p)
        self._draw_loading_badge(p)

    def _draw_split_overlays(self, p, zoom):
        """左上 A 名 / 右上 B 名 / 右下缩放比例。"""
        p.setRenderHint(QPainter.Antialiasing, False)
        f = p.font()
        f.setPointSize(9)
        p.setFont(f)
        fm = p.fontMetrics()

        def tag(text, x, align_right=False):
            tw = fm.horizontalAdvance(text) + 12
            th = fm.height() + 6
            if align_right:
                x -= tw
            p.fillRect(int(x), 0, tw, th, QColor(0, 0, 0, 150))
            p.setPen(QColor(235, 235, 235))
            p.drawText(QRectF(x, 2, tw, th),
                       Qt.AlignLeft | Qt.AlignVCenter, text)

        title_a = self.title
        title_b = self.title_b
        if self.pixmap is not None:
            title_a += f'   {self.pixmap.width()}×{self.pixmap.height()}'
        if self.pixmap_b is not None:
            title_b = (f'{self.pixmap_b.width()}×{self.pixmap_b.height()}'
                       f'   {title_b}')
        tag(title_a, 6)
        tag(title_b, self.width() - 6, align_right=True)
        # 缩放比例画在右下角 (复用基类样式)
        ztext = f'{zoom * 100:.1f}%'
        zw = fm.horizontalAdvance(ztext) + 12
        th = fm.height() + 6
        h_ = self.height()
        p.fillRect(self.width() - zw, h_ - th, zw, th, QColor(0, 0, 0, 150))
        p.setPen(QColor(235, 235, 235))
        p.drawText(QRectF(self.width() - zw, h_ - th, zw, th),
                   Qt.AlignCenter, ztext)


# ---------------------------------------------------------------- FolderList
class FolderList(QListWidget):
    """支持拖动重排序的文件夹列表 (分屏顺序跟随列表顺序)。"""

    def __init__(self, win, parent=None):
        super().__init__(parent)
        self.win = win
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setDefaultDropAction(Qt.MoveAction)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)

    def dropEvent(self, e):
        # 接管 drop: 默认的 InternalMove 会删掉 setItemWidget 的内容,
        # 所以自己计算插入位置并重排 folders, 然后重建列表 UI
        e.accept()
        src = self.currentRow()
        if src < 0 or src >= len(self.win.folders):
            return
        pos = e.position().toPoint()
        target_item = self.itemAt(pos)
        if target_item is None:
            dst = self.count()
        else:
            r = self.visualItemRect(target_item)
            dst = self.row(target_item)
            if pos.y() > r.center().y():
                dst += 1
        if dst > src:
            dst -= 1
        if dst == src:
            return
        entry = self.win.folders.pop(src)
        self.win.folders.insert(dst, entry)
        self.win.rebuild_folder_list()
        self.win.rebuild_panes()


# ---------------------------------------------------------------- FolderItem
class FolderItemWidget(QWidget):
    removeClicked = Signal(object)

    def __init__(self, path: Path, checked=True, parent=None):
        super().__init__(parent)
        self.path = path
        lay = QHBoxLayout(self)
        lay.setContentsMargins(6, 3, 2, 3)
        lay.setSpacing(6)
        self.checkbox = QCheckBox(path.name)
        self.checkbox.setChecked(checked)
        self.checkbox.setCursor(Qt.PointingHandCursor)
        lay.addWidget(self.checkbox, 1)
        btn = QPushButton('✕')
        btn.setFixedSize(20, 20)
        btn.setStyleSheet('QPushButton{border:none;color:#888;}'
                          'QPushButton:hover{color:#e55;}')
        btn.setToolTip('移除该文件夹')
        btn.clicked.connect(lambda: self.removeClicked.emit(self))
        lay.addWidget(btn)


# ---------------------------------------------------------------- MainWindow
class CompareWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('图片对比工具 - 多目录同步缩放')
        self.resize(1500, 900)
        self.settings = QSettings('ArcVideo', 'ImageCompare')

        self.folders = []          # [(Path, FolderItemWidget)]
        self.panes = []
        self.shared = ViewState()
        self.current_file = None
        self._fs_mode = False      # 全屏对比模式
        self._fs_prev_left = None
        self._first_image_load = True   # 首次载入图片时自动适配窗口(居中)
        self.split_mode = False    # 左右单屏对比模式 (仅 2 个文件夹时可用)

        # ---- 后台图片加载 ----
        self._load_gen = 0         # 加载代数: 快速切换文件时丢弃过期结果
        self._pending = 0          # 本代尚未完成的加载数
        self._load_total = 0
        self._load_any = False     # 本代是否加载到过图片
        self._load_stem = ''
        self._mem_warn = ''        # 内存不足时状态栏附带的警告文案
        self._ref_w_seen = 0       # 本代已加载图片的最大尺寸 (渐进更新参考系)
        self._ref_h_seen = 0
        self._load_sig = _LoadSignals()
        self._load_sig.done.connect(self._on_image_loaded)
        self._load_timer = QTimer(self)
        self._load_timer.setInterval(200)
        self._load_timer.timeout.connect(self._tick_loading)

        # ---- 后台文件夹扫描 ----
        self._scan_gen = 0
        self._scan_maps = {}       # {folder: {stem: filename}} 最新一次扫描缓存
        self._scan_pending = 0
        self._scan_total = 0
        self._scan_t0 = None
        self._scan_prev = None     # 扫描完成后要恢复的选中文件
        self._load_sig.scan_done.connect(self._on_scan_done)
        self._load_sig.discover_done.connect(self._on_discover_done)
        self._scan_timer = QTimer(self)
        self._scan_timer.setInterval(200)
        self._scan_timer.timeout.connect(self._tick_scan)

        self._build_ui()
        # 延迟到窗口显示后再扫描网络盘, 避免启动被 SMB 延迟卡住 (白屏等待)
        QTimer.singleShot(50, self._restore_or_autodiscover)

    # ---------------- UI ----------------
    def _mk_btn(self, text, slot):
        b = QPushButton(text)
        b.clicked.connect(slot)
        return b

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)   # 否则全屏时四周会留 ~10px 白边
        root.setSpacing(0)

        # ---- 左侧: 文件夹列表 + 文件列表 ----
        left = QFrame()
        left.setObjectName('leftPanel')
        lv = QVBoxLayout(left)
        lv.setContentsMargins(8, 8, 8, 8)
        lv.setSpacing(6)

        lab1 = QLabel('文件夹 (勾选 = 显示分屏, 拖动可排序):')
        lab1.setObjectName('sectionLabel')
        lv.addWidget(lab1)
        self.folder_list = FolderList(self)
        self.folder_list.setObjectName('folderList')
        self.folder_list.setToolTip('拖动文件夹可调整分屏顺序')
        lv.addWidget(self.folder_list, 35)    # 上部约 35%

        grid = QGridLayout()
        grid.setSpacing(3)
        grid.addWidget(self._mk_btn('添加文件夹', self.add_folders), 0, 0)
        grid.addWidget(self._mk_btn('自动发现子目录', self.auto_discover), 0, 1)
        b_refresh = self._mk_btn('刷新 (F5)', self.refresh_files)
        b_refresh.setToolTip('重新扫描勾选的文件夹, 更新同名图片列表\n(当前选中图片与缩放/位置保持不变)')
        grid.addWidget(b_refresh, 1, 0)
        grid.addWidget(self._mk_btn('清空', self.clear_folders), 1, 1)
        lv.addLayout(grid)

        lab2 = QLabel('图片 (所有文件夹共有的同名文件):')
        lab2.setObjectName('sectionLabel')
        lv.addWidget(lab2)
        self.file_list = QListWidget()
        self.file_list.currentItemChanged.connect(self.on_file_selected)
        lv.addWidget(self.file_list, 65)      # 下部约 65%
        self.left_panel = left

        # ---- 右侧 (颜色保持默认浅色; 全屏时由 toggle_fullscreen_mode 收边) ----
        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(0, 0, 0, 0)
        rv.setSpacing(0)
        self.rv = rv

        tool = QHBoxLayout()
        self.btn_toggle_left = QPushButton('⟨ 隐藏列表')
        self.btn_toggle_left.setToolTip('隐藏/显示左侧文件夹与图片列表 (%s)' % LEFT_LIST_SHORTCUT)
        self.btn_toggle_left.clicked.connect(self.toggle_left_panel)
        b_prev = QPushButton('◀ 上一张')
        b_next = QPushButton('下一张 ▶')
        b_prev.clicked.connect(self.prev_file)
        b_next.clicked.connect(self.next_file)
        b_fit = QPushButton('适配窗口 (F)')
        b_fit.setToolTip(
            '完整显示整张图片, 居中 (快捷键 F)\n\n'
            '提示: 双击图片可在「适配窗口」和「100% 显示」之间切换,\n'
            '切到 100% 时以双击位置为视图中心 (所有分屏同步)')
        b_fit.clicked.connect(self.apply_fit)
        b_100 = QPushButton('100% (1)')
        b_100.setToolTip(
            '1:1 像素显示, 以图片中心为视图中心 (快捷键 1)\n\n'
            '提示: 双击图片可在「适配窗口」和「100% 显示」之间切换,\n'
            '切到 100% 时以双击位置为视图中心 (所有分屏同步)')
        b_100.clicked.connect(self.apply_100)
        self.zoom_label = QLabel('100.0%')
        self.zoom_label.setObjectName('zoomChip')
        self.zoom_label.setAlignment(Qt.AlignCenter)
        self.zoom_label.setMinimumWidth(86)
        self.sync_check = QCheckBox('缩放/拖动同步')
        self.sync_check.setChecked(True)
        self.sync_check.toggled.connect(self.on_sync_toggled)
        tool.addWidget(self.btn_toggle_left)
        tool.addWidget(b_prev)
        tool.addWidget(b_next)
        tool.addStretch(1)
        tool.addWidget(b_fit)
        tool.addWidget(b_100)
        tool.addWidget(self.zoom_label)
        tool.addWidget(self.sync_check)
        self.btn_split = QPushButton('◐ 左右对比 (S)')
        self.btn_split.setObjectName('btnSplit')
        self.btn_split.setCheckable(True)
        self.btn_split.setToolTip(
            '仅 2 个文件夹时可用: 单屏模式, 中间分割线左边显示 A 右边显示 B,\n'
            '左右拖动分割线对比同一区域')
        self.btn_split.setEnabled(False)
        self.btn_split.clicked.connect(self.toggle_split_mode)
        tool.addSpacing(8)
        tool.addWidget(self.btn_split)
        self.btn_fs = QPushButton('⛶ 全屏对比 (F11)')
        self.btn_fs.setObjectName('btnFs')
        self.btn_fs.setToolTip('只保留分屏，隐藏其他所有界面 (F11 或 Esc 退出)')
        self.btn_fs.clicked.connect(self.toggle_fullscreen_mode)
        tool.addWidget(self.btn_fs)
        tool_widget = QFrame()
        tool_widget.setObjectName('toolBar')
        tool_widget.setLayout(tool)
        tool.setContentsMargins(10, 8, 10, 8)
        tool.setSpacing(6)
        rv.addWidget(tool_widget)
        self.tool_bar_widget = tool_widget

        self.pane_host = QWidget()
        self.pane_layout = QGridLayout(self.pane_host)
        self.pane_layout.setContentsMargins(0, 0, 0, 0)
        self.pane_layout.setSpacing(2)
        rv.addWidget(self.pane_host, 1)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(8)          # 加宽拖动手柄, 方便抓取
        splitter.setChildrenCollapsible(False)   # 不允许拖到完全折叠
        self.left_panel.setMinimumWidth(120)
        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        saved = self.settings.value('splitterSizes')
        default_sizes = [200, 1300]   # 初始左栏 ~200px
        if saved:
            try:
                s = [int(v) for v in saved]
                # 只接受 >=160 的历史值 (过小的视为旧版默认, 直接用新默认)
                if len(s) == 2 and s[0] >= 160:
                    default_sizes = s
            except (TypeError, ValueError):
                pass
        splitter.setSizes(default_sizes)
        self.splitter = splitter
        root.addWidget(splitter)

        self.statusBar().showMessage('就绪')
        self._setup_shortcuts()

    def _setup_shortcuts(self):
        QShortcut(QKeySequence(Qt.Key_Left), self, self.prev_file)
        QShortcut(QKeySequence(Qt.Key_Right), self, self.next_file)
        QShortcut(QKeySequence(Qt.Key_Space), self, self.next_file)
        QShortcut(QKeySequence(Qt.Key_F), self, self.apply_fit)
        QShortcut(QKeySequence(Qt.Key_1), self, self.apply_100)
        QShortcut(QKeySequence(LEFT_LIST_SHORTCUT), self, self.toggle_left_panel)
        QShortcut(QKeySequence(Qt.Key_F5), self, self.refresh_files)
        QShortcut(QKeySequence(Qt.Key_F11), self, self.toggle_fullscreen_mode)
        QShortcut(QKeySequence(Qt.Key_S), self, self._shortcut_split)
        QShortcut(QKeySequence(Qt.Key_Escape), self, self._escape_pressed)

    def toggle_split_mode(self):
        """左右单屏对比模式 (仅 2 个文件夹时可用)。"""
        if not self.btn_split.isEnabled():
            return
        self.split_mode = not self.split_mode
        self.btn_split.setChecked(self.split_mode)
        for pane in self.panes:
            pane.set_hover(None)          # 避免残留旧准星
        self.rebuild_panes()

    def _shortcut_split(self):
        if self.btn_split.isEnabled():
            self.toggle_split_mode()

    def update_split_button(self):
        """勾选文件夹数变化后维护按钮可用性; 数量≠2 时强制退出单屏对比。"""
        n = len(self.active_folders())
        if self.split_mode and n != 2:
            self.split_mode = False
            self.btn_split.setChecked(False)
        self.btn_split.setEnabled(n == 2)

    def _escape_pressed(self):
        if self._fs_mode:
            self.toggle_fullscreen_mode()

    def toggle_fullscreen_mode(self):
        """全屏对比模式: 隐藏列表/工具栏/状态栏/标题栏, 只留分屏。F11 切换。"""
        if not self._fs_mode:
            self._fs_prev_left = self.left_panel.isVisible()
            self.left_panel.setVisible(False)
            self.tool_bar_widget.setVisible(False)
            self.statusBar().setVisible(False)
            self.rv.setContentsMargins(0, 0, 0, 0)     # 全屏收掉边距
            self.pane_layout.setSpacing(2)             # 分屏间留 2px 缝
            # 缝隙显示为深灰分隔线 (pane_host 平时透明, 全屏才填色)
            self.pane_host.setAutoFillBackground(True)
            pal = self.pane_host.palette()
            pal.setColor(QPalette.Window, QColor(45, 45, 48))
            self.pane_host.setPalette(pal)
            self.showFullScreen()
            # 不做任何 fit: 缩放比例和观察位置 (共享 ViewState) 原样保留,
            # 视口变大只会显示更多周围区域。需要铺满可手动按 F。
            self.btn_fs.setText('退出全屏 (F11)')
            self._fs_mode = True
        else:
            self._exit_fullscreen_mode()

    def _exit_fullscreen_mode(self):
        self.showNormal()
        self.rv.setContentsMargins(0, 0, 0, 0)        # 工具栏顶格, 无需边距
        self.pane_host.setAutoFillBackground(False)  # 恢复透明缝隙
        self.pane_layout.setSpacing(2)
        self.tool_bar_widget.setVisible(True)
        self.statusBar().setVisible(True)
        if self._fs_prev_left is not None:
            self.left_panel.setVisible(self._fs_prev_left)
        self.btn_fs.setText('⛶ 全屏对比 (F11)')
        self._fs_mode = False

    def toggle_left_panel(self):
        vis = self.left_panel.isVisible()
        self.left_panel.setVisible(not vis)
        self.btn_toggle_left.setText('⟩ 显示列表' if vis else '⟨ 隐藏列表')

    def closeEvent(self, e):
        # 记住列表宽度; 左侧隐藏时不保存(否则下次启动列表会变成 0 宽)
        if self.left_panel.isVisible():
            self.settings.setValue('splitterSizes', self.splitter.sizes())
        super().closeEvent(e)

    # ---------------- folders ----------------
    def _restore_or_autodiscover(self):
        """启动恢复: 读取上次保存的文件夹列表和勾选状态。

        首次使用(无保存记录)时不自动选择任何文件夹, 由用户手动选择,
        选择结果会被记住, 以后每次启动自动恢复。
        """
        self.statusBar().showMessage('正在恢复上次的文件夹...')
        saved = self.settings.value('folderPaths')
        if isinstance(saved, str):            # 单条目时 QSettings 返回 str
            saved = [saved]
        if not saved:
            self.statusBar().showMessage(
                '初次使用: 请点 "添加文件夹" 或 "自动发现子目录" 选择对比目录 (选择会被记住)')
            return
        checked = self.settings.value('checkedFolders')
        if isinstance(checked, str):
            checked = [checked]
        checked_set = set(checked) if checked else set()
        n_checked = 0
        for pth in saved:
            p = Path(pth)
            if not p.is_dir():
                continue                       # 文件夹已被移动/删除则跳过
            is_checked = str(p) in checked_set
            n_checked += is_checked
            self._add_folder(p, checked=is_checked, quiet=True)
        self.refresh_files()
        self.statusBar().showMessage(
            f'已恢复上次的 {len(self.folders)} 个文件夹 ({n_checked} 个勾选分屏)')

    def save_checked_state(self):
        """把当前文件夹列表(含顺序)和勾选状态存入配置, 启动时恢复。"""
        paths = [str(p) for p, w in self.folders]
        checked = [str(p) for p, w in self.folders if w.checkbox.isChecked()]
        self.settings.setValue('folderPaths', paths)
        self.settings.setValue('checkedFolders', checked)

    def on_folder_toggled(self, _checked=False):
        self.rebuild_panes()
        self.save_checked_state()

    def _add_folder(self, path: Path, checked=True, quiet=False):
        if any(str(p) == str(path) for p, _ in self.folders):
            return
        item = QListWidgetItem()
        self.folder_list.addItem(item)
        w = FolderItemWidget(path, checked)
        w.checkbox.toggled.connect(self.on_folder_toggled)
        w.removeClicked.connect(self.remove_folder_widget)
        item.setSizeHint(QSize(w.sizeHint().width() + 8,
                               max(w.sizeHint().height(), 28)))
        self.folder_list.setItemWidget(item, w)
        self.folders.append((path, w))
        if not quiet:
            self.refresh_files()

    def _pick_dirs_multi(self, title, start):
        """目录多选对话框 (Qt 原生对话框不支持目录多选, 用非原生 + MultiSelection)。"""
        dlg = QFileDialog(self, title, start)
        dlg.setFileMode(QFileDialog.Directory)
        dlg.setOption(QFileDialog.ShowDirsOnly, True)
        dlg.setOption(QFileDialog.DontUseNativeDialog, True)
        # 把内置的列表/树视图都切成多选
        for name in ('listView', 'treeView'):
            v = dlg.findChild(QListView, name) or dlg.findChild(QTreeView, name)
            if v:
                v.setSelectionMode(QAbstractItemView.MultiSelection)
        # "Look In" 位置栏改为可编辑: 支持直接粘贴路径 + 回车跳转。
        # 回车会被对话框当成"确定"导致直接关闭 (焦点在 ComboBox 上时
        # 事件穿透到默认 OK 按钮), 用事件过滤器在 combo 和其输入框上
        # 同时拦截: 回车 = 跳转到粘贴的目录并列出其中的文件夹, 不关闭。
        for combo in dlg.findChildren(QComboBox, 'lookInCombo'):
            combo.setEditable(True)
            combo.setInsertPolicy(QComboBox.NoInsert)
            le = combo.lineEdit()
            le.setPlaceholderText('粘贴路径, 回车跳转')
            flt = _PathJumpFilter(dlg, combo)
            combo.installEventFilter(flt)   # 焦点在 combo 上时拦截回车
            le.installEventFilter(flt)     # 焦点在内部输入框上时拦截回车
        if dlg.exec():
            return [f for f in dlg.selectedFiles() if Path(f).is_dir()]
        return []

    def add_folders(self):
        # 记忆功能: 直接打开上次添加时用过的目录
        start = self.settings.value('lastAddDir', str(Path.home()))
        dirs = self._pick_dirs_multi('选择文件夹 (可按住 Ctrl 多选, 选择会被记住)', str(start))
        if dirs:
            self.settings.setValue('lastAddDir', dirs[0])
            added = 0
            for d in dirs:
                before = len(self.folders)
                self._add_folder(Path(d), quiet=True)
                added += len(self.folders) - before
            self.refresh_files()
            self.save_checked_state()
            if added != len(dirs):
                self.statusBar().showMessage(
                    f'新添加 {added} 个文件夹 ({len(dirs) - added} 个已在列表中, 自动跳过)')

    def auto_discover(self):
        start = self.settings.value('lastBase', DEFAULT_BASE)
        base = QFileDialog.getExistingDirectory(
            self, '选择数据集根目录 (将列出其下所有含图片的子目录)', str(start))
        if not base:
            return
        base = Path(base)
        self.settings.setValue('lastBase', str(base))
        # 子目录枚举+图片检测放后台线程 (网络盘可能很慢)
        self._scan_gen += 1
        self._scan_t0 = time.monotonic()
        self.statusBar().showMessage(f'正在扫描 {base} 下的子目录 ...')
        QThreadPool.globalInstance().start(
            _DiscoverWorker(self._scan_gen, base, self._load_sig))

    def _on_discover_done(self, gen, base, subs):
        """自动发现完成 (主线程)。"""
        if gen != self._scan_gen:
            return
        self._scan_timer.stop()
        if not subs:
            QMessageBox.information(self, '提示', '该目录下没有含图片的子目录。')
            return
        self.clear_folders()
        for d in subs:
            self._add_folder(Path(d), checked=True, quiet=True)
        self.refresh_files()
        self.statusBar().showMessage(f'已加载 {len(subs)} 个文件夹 (来自 {base})')

    def clear_folders(self):
        self.folders.clear()
        self.folder_list.clear()
        self.refresh_files()
        self.save_checked_state()

    def rebuild_folder_list(self):
        """按 self.folders 当前顺序重建列表 UI (拖动重排序后调用)。"""
        states = [(p, w.checkbox.isChecked()) for p, w in self.folders]
        self.folder_list.clear()          # 会删除旧 widget, 必须重建
        self.folders = []
        for p, checked in states:
            self._add_folder(p, checked=checked, quiet=True)
        self.save_checked_state()

    def remove_folder_widget(self, widget):
        self.folders = [(p, w) for p, w in self.folders if w is not widget]
        for i in range(self.folder_list.count()):
            if self.folder_list.itemWidget(self.folder_list.item(i)) is widget:
                self.folder_list.takeItem(i)
                break
        self.refresh_files()
        self.save_checked_state()

    def active_folders(self):
        return [p for p, w in self.folders if w.checkbox.isChecked()]

    # ---------------- files ----------------
    def refresh_files(self):
        """后台扫描勾选文件夹, 更新共有图片列表; 保持当前选中图片与视图状态。

        网络盘上 iterdir 很慢, 放后台线程并显示进度提示, 界面不卡死。
        """
        folders = self.active_folders()
        self._scan_gen += 1
        gen = self._scan_gen
        self._scan_prev = self.current_file
        self._scan_pending = len(folders)
        self._scan_total = len(folders)
        self.file_list.blockSignals(True)
        self.file_list.clear()
        if folders:
            # 占位提示 (扫描完成会被真实列表替换)
            it = QListWidgetItem('正在扫描文件夹, 请稍候...')
            it.setFlags(Qt.NoItemFlags)
            self.file_list.addItem(it)
        self.file_list.blockSignals(False)
        if not folders:
            self._scan_timer.stop()
            self._scan_maps = {}
            self.statusBar().showMessage('未选择文件夹')
            self.on_file_selected(None, None)
            self._check_pane_count(folders)
            return
        self._scan_t0 = time.monotonic()
        self.statusBar().showMessage(
            f'正在扫描 {len(folders)} 个文件夹 (0/{len(folders)}) ...')
        self._scan_timer.start()
        for f in folders:
            QThreadPool.globalInstance().start(
                _ScanWorker(gen, f, self._load_sig))

    def _check_pane_count(self, folders):
        """仅当可见分屏数变化时才重建分屏网格 (单屏对比模式下分屏数为 1)。"""
        expected = 1 if (self.split_mode and len(folders) == 2) \
            else min(len(folders), MAX_PANES)
        if len(self.panes) != expected:
            self.rebuild_panes()

    def _on_scan_done(self, gen, folder, names):
        """单个文件夹扫描完成 (主线程)。"""
        if gen != self._scan_gen:
            return
        self._scan_maps[folder] = names
        self._scan_pending = max(0, self._scan_pending - 1)
        if self._scan_pending == 0:
            self._finish_scan()

    def _finish_scan(self):
        """全部文件夹扫描完毕: 计算共有图片, 填充列表并恢复选中。"""
        self._scan_timer.stop()
        folders = self.active_folders()
        maps = [self._scan_maps.get(f, {}) for f in folders]
        sets = [set(m.keys()) for m in maps]
        common = set.intersection(*sets) if sets else set()
        names = sorted(common, key=natural_key)   # 主干名(不含扩展名)
        self.file_list.blockSignals(True)
        self.file_list.clear()
        self.file_list.addItems(names)
        self.file_list.blockSignals(False)
        elapsed = time.monotonic() - self._scan_t0
        self.statusBar().showMessage(
            f'{len(folders)} 个文件夹, {len(names)} 张共有图片 '
            f'(扫描 {elapsed:.1f}s, 按文件名主干匹配, 不区分扩展名)')

        # 恢复选中: 优先保持之前的图片, 否则选第一张
        prev = self._scan_prev
        if names:
            found = self.file_list.findItems(prev, Qt.MatchExactly) if prev else []
            if found:
                self.file_list.setCurrentItem(found[0])   # 触发 on_file_selected
            else:
                self.file_list.setCurrentRow(0)
        else:
            self.on_file_selected(None, None)
        self._check_pane_count(folders)

    def _tick_scan(self):
        """扫描进度提示 (每 200ms)。"""
        if self._scan_pending:
            n, total = self._scan_total - self._scan_pending, self._scan_total
            elapsed = time.monotonic() - self._scan_t0
            self.statusBar().showMessage(
                f'正在扫描 {total} 个文件夹 ({n}/{total}) {elapsed:.1f}s ...')

    def on_file_selected(self, cur, _prev):
        if cur is None:
            self.current_file = None
            for pane in self.panes:
                if isinstance(pane, SplitComparePane):
                    pane.set_images(None, None, None, None)
                else:
                    pane.set_image(None)
            return
        stem = cur.text()
        # 同一文件正在加载时忽略重复触发 (列表信号/刷新会多次调用,
        # 否则同一张大图会被重复解码多份, 角标计数也会漏清)
        if stem == self._load_stem and self._pending > 0:
            return
        self.current_file = stem
        folders = self.active_folders()
        # 大图解码放到后台线程池, 界面保持可交互; 分屏右上角显示加载角标
        n_load = min(len(folders), MAX_PANES)
        # 匹配文件名用扫描缓存 (不再现场 iterdir, 否则每次选图都卡网络盘)
        scan_maps = self._scan_maps
        self._load_gen += 1
        gen = self._load_gen
        self._pending = 0
        self._load_total = 0
        self._load_any = False
        self._load_stem = stem
        self._ref_w_seen = 0
        self._ref_h_seen = 0
        # 重置角标计数: 上一代的结果即使没回来也作废 (gen 不匹配直接丢弃)
        for pane in self.panes:
            pane._loading_n = 0
            pane._loading_t0 = None
            pane.update()

        # ---- 先收集各文件夹要加载的图片 ----
        candidates = []
        for i in range(n_load):
            fname = scan_maps.get(folders[i], {}).get(stem)
            path = (folders[i] / fname) if fname else None
            if path is not None and not path.exists():
                path = None
            candidates.append((i, path))

        # ---- 内存保护: 只读文件头估算解码后占用, 超预算的分屏不加载 ----
        # 预算 = 可用物理内存的 50% (余量留给系统 + 当前显示的旧图 + 其他程序)
        est_unknown = 512 * 1024 * 1024    # 文件头读不到时按 512MB 保守估计
        avail = _mem_available()
        budget = int(avail * 0.5) if avail else None
        plan = []                # (i, path, note)
        used = 0
        n_skip = 0
        est_total = 0
        for i, path in candidates:
            if path is None:
                plan.append((i, None, None))
                continue
            est = _estimate_image_bytes(path)
            acct = est if est is not None else est_unknown
            est_total += acct
            if budget is not None and used + acct > budget:
                plan.append((i, path, '内存不足，未加载'))
                n_skip += 1
            else:
                used += acct
                plan.append((i, path, None))

        if n_skip:
            # 内存吃紧: 先清掉当前显示的旧图, 降低峰值占用
            for pane in self.panes:
                if isinstance(pane, SplitComparePane):
                    pane.set_image(None, None, '')
                    pane.pixmap_b = None
                    pane.path_b = None
                    pane.update()
                else:
                    pane.set_image(None, None, '')
            avail_gb = avail / (1 << 30) if avail else 0
            self._mem_warn = (f'⚠ 内存不足: 本图 {n_load} 屏共需约 '
                              f'{est_total / (1 << 30):.1f}GB, 可用 '
                              f'{avail_gb:.1f}GB, 已跳过 {n_skip} 屏')
        else:
            self._mem_warn = ''

        for i, path, note in plan:
            if path is None and note is None:
                # 无对应文件: 立即清屏显示"缺少对应图片", 无需等待
                self._clear_loading(i)
                self._apply_pane_image(i, None, None)
            elif note is not None:
                # 内存预算不足: 不派发解码, 显示提示占位
                self._clear_loading(i)
                self._apply_pane_image(i, None, path, note=note)
            else:
                self._pending += 1
                self._mark_loading(i, True)
                w = _ImageLoadWorker(gen, i, path, self._load_sig)
                QThreadPool.globalInstance().start(w)
        self._load_total = self._pending
        idx = self.file_list.row(cur) + 1
        self._load_pos = f'({idx}/{self.file_list.count()})'
        if self._pending:
            self.statusBar().showMessage(
                f'正在加载 {stem} {self._load_pos} (0/{self._pending}) ...')
            self._load_timer.start()
        else:
            if n_skip:
                self.statusBar().showMessage(
                    f'{stem} {self._load_pos} {self._mem_warn}', 8000)
            else:
                self.statusBar().showMessage(
                    f'{stem} {self._load_pos}: 各文件夹中未找到对应图片', 4000)
            self._load_timer.stop()

    # ---------------- async loading ----------------
    def _each_target_pane(self, folder_index):
        """遍历负责第 folder_index 个文件夹的画格。"""
        for pane in self.panes:
            if isinstance(pane, SplitComparePane):
                if folder_index in (0, 1):
                    yield pane
            elif pane.folder_index == folder_index:
                yield pane

    def _mark_loading(self, folder_index, on):
        for pane in self._each_target_pane(folder_index):
            pane.set_loading(on)

    def _clear_loading(self, folder_index):
        self._mark_loading(folder_index, False)

    def _apply_pane_image(self, folder_index, pixmap, path, note=None):
        """把加载结果应用到对应画格 (支持普通分屏与左右对比两种布局)。"""
        for pane in self._each_target_pane(folder_index):
            if isinstance(pane, SplitComparePane):
                if folder_index == 0:
                    pane.set_image(pixmap, path, note)      # 左侧 A
                else:
                    pane.pixmap_b = pixmap            # 右侧 B
                    pane.path_b = path
                    pane.update()
            else:
                pane.set_image(pixmap, path, note)

    def _on_image_loaded(self, gen, folder_index, img, path_str):
        """后台解码完成 (主线程): 过期代数直接丢弃。"""
        if gen != self._load_gen:
            return
        pm = QPixmap.fromImage(img) if img is not None else None
        self._pending = max(0, self._pending - 1)
        self._clear_loading(folder_index)
        self._apply_pane_image(folder_index, pm,
                               Path(path_str) if path_str else None)
        # 参考分辨率 = 本批最大宽/高, 渐进更新 (HR 通常最后加载完)
        if pm is not None:
            self._load_any = True
            self._ref_w_seen = max(self._ref_w_seen, pm.width())
            self._ref_h_seen = max(self._ref_h_seen, pm.height())
            for pane in self.panes:
                pane.set_reference(self._ref_w_seen, self._ref_h_seen)
        done = self._pending == 0
        if done:
            self._load_timer.stop()
            n = self._load_total
            pos = getattr(self, '_load_pos', '')
            if self._load_any:
                msg = f'{self._load_stem} {pos} 加载完成 ({n}/{n})'
                if getattr(self, '_mem_warn', ''):
                    msg += f'  |  {self._mem_warn}'
                self.statusBar().showMessage(msg, 8000)
            else:
                self.statusBar().showMessage(
                    f'{self._load_stem} {pos}: 未找到可加载的图片', 4000)
            # 首次载入: 图片就绪后自动适配居中 (保留重试机制)
            if self._first_image_load and self._load_any:
                QTimer.singleShot(0, self._apply_first_fit)

    def _tick_loading(self):
        """角标计时刷新 (每 200ms), 状态栏同步进度。"""
        n, total = self._load_total - self._pending, self._load_total
        if self._pending:
            msg = (f'正在加载 {self._load_stem} {self._load_pos} '
                   f'({n}/{total}) ...')
            if getattr(self, '_mem_warn', ''):
                msg += f'  |  {self._mem_warn}'
            self.statusBar().showMessage(msg)
        for pane in self.panes:
            if pane._loading_t0 is not None:
                pane.update()

    def _step(self, delta):
        n = self.file_list.count()
        if n == 0:
            return
        row = self.file_list.currentRow()
        row = clamp(row + delta, 0, n - 1) if row >= 0 else (0 if delta > 0 else n - 1)
        self.file_list.setCurrentRow(row)

    def next_file(self):
        self._step(1)

    def prev_file(self):
        self._step(-1)

    # ---------------- panes ----------------
    def rebuild_panes(self):
        self.update_split_button()        # 勾选数≠2 时强制退出单屏对比
        # 清空旧分屏
        for pane in self.panes:
            pane.viewChanged.disconnect(self.on_view_changed)
            pane.hoverMoved.disconnect(self.on_hover_moved)
            self.pane_layout.removeWidget(pane)
            pane.deleteLater()
        self.panes.clear()
        while self.pane_layout.count():
            it = self.pane_layout.takeAt(0)
            if it.widget():
                it.widget().deleteLater()

        folders_all = self.active_folders()
        folders = folders_all[:MAX_PANES]
        if len(folders_all) > MAX_PANES:
            self.statusBar().showMessage(
                f'勾选了 {len(folders_all)} 个文件夹，只显示前 {MAX_PANES} 个分屏'
                f'（多余: {", ".join(Path(f).name for f in folders_all[MAX_PANES:])}）')
        n = len(folders)
        # 清掉旧布局残留的行列拉伸, 否则减少分屏后空列/空行仍占空间 (4 分屏填不满窗口)
        for c in range(self.pane_layout.columnCount()):
            self.pane_layout.setColumnStretch(c, 0)
        for r in range(self.pane_layout.rowCount()):
            self.pane_layout.setRowStretch(r, 0)

        if self.split_mode and n == 2:
            # 左右单屏对比: 一块画布, 中间可拖动分割线
            pane = SplitComparePane(Path(folders[0]).name,
                                    Path(folders[1]).name,
                                    self.shared, self.pane_host)
            pane.folder_index = 0
            pane.viewChanged.connect(self.on_view_changed)
            pane.hoverMoved.connect(self.on_hover_moved)
            self.panes.append(pane)
            self.pane_layout.addWidget(pane, 0, 0)
            self.pane_layout.setColumnStretch(0, 1)
            self.pane_layout.setRowStretch(0, 1)
        else:
            for i, folder in enumerate(folders):
                pane = ImagePane(Path(folder).name, self.shared, self.pane_host)
                pane.folder_index = i
                pane.viewChanged.connect(self.on_view_changed)
                pane.hoverMoved.connect(self.on_hover_moved)
                self.panes.append(pane)
            if n:
                cols = max(1, math.ceil(math.sqrt(n)))
                rows = math.ceil(n / cols)
                for i, pane in enumerate(self.panes):
                    r, c = divmod(i, cols)
                    self.pane_layout.addWidget(pane, r, c)
                for c in range(cols):
                    self.pane_layout.setColumnStretch(c, 1)
                for r in range(rows):
                    self.pane_layout.setRowStretch(r, 1)
        # 重新载入当前文件 (清掉去重标记, 强制重放)
        self._load_stem = ''
        if self.current_file:
            cur = self.file_list.findItems(
                self.current_file, Qt.MatchExactly)
            if cur:
                self.on_file_selected(cur[0], None)
        else:
            self.on_file_selected(None, None)

    # ---------------- sync / zoom ----------------
    def on_view_changed(self):
        for pane in self.panes:
            pane.update()
        self.zoom_label.setText(f'{self.shared.zoom * 100:.1f}%')

    def on_hover_moved(self, ref):
        """某个分屏内鼠标移动 → 其他分屏在对应内容点画指示标记。

        - 鼠标所在的本屏不画 (那里有真实光标, 画了反而挡视野)
        - 左右单屏对比模式整屏只有一块画布, 完全不需要准星
        """
        if ref is None or self.split_mode:
            for pane in self.panes:
                pane.set_hover(None)
            return
        src = self.sender()
        for pane in self.panes:
            if pane is not src:
                pane.set_hover(ref)

    def on_sync_toggled(self, on):
        for pane in self.panes:
            pane.set_sync(on)
        if on:
            self.on_view_changed()

    def apply_fit(self):
        if self.panes:
            self.panes[0].fit(padding=8)

    def _apply_first_fit(self):
        """首次载入的自动居中: 图片就绪才执行, 否则下一拍重试。"""
        if not self._first_image_load:
            return
        for pane in self.panes:
            ready = (pane.pixmap is not None
                     or getattr(pane, 'pixmap_b', None) is not None)
            if ready and pane._ref_size() != (0, 0):
                self._first_image_load = False
                pane.fit(padding=8)
                return
        QTimer.singleShot(0, self._apply_first_fit)   # 还没就绪, 下一拍再试

    def apply_100(self):
        if self.panes:
            self.panes[0].zoom_100()


# ---------------------------------------------------------------- main
def resource_path(rel):
    """兼容源码运行与 PyInstaller onefile (sys._MEIPASS)。"""
    base = getattr(sys, '_MEIPASS', None)
    if base:
        return Path(base) / rel
    return Path(__file__).resolve().parent / rel


def main():
    # 设置 AppUserModelID, 让任务栏图标显示自己的图标而不是 pythonw 的
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            'ArcVideo.ImageCompare.1')
    except Exception:
        pass
    app = QApplication(sys.argv)
    app.setApplicationName('ImageCompare')
    app.setStyle('Fusion')          # 统一基线风格, QSS 覆盖出现代观感
    app.setStyleSheet(MODERN_QSS)
    for name in ('icon.ico', 'icon.png'):
        p = resource_path(name)
        if p.exists():
            app.setWindowIcon(QIcon(str(p)))
            break
    win = CompareWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
