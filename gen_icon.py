#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成应用图标 icon.png / icon.ico：2x2 四色分屏 + 放大镜。"""
import sys
from pathlib import Path

from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import (QColor, QIcon, QLinearGradient, QPainter,
                           QPen, QPixmap, QBrush, QRadialGradient)

OUT_DIR = Path(__file__).resolve().parent


def draw_icon(size=256):
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    s = size / 256.0

    # 深色圆角背景 (垂直渐变)
    bg = QLinearGradient(0, 0, 0, size)
    bg.setColorAt(0.0, QColor('#2a3446'))
    bg.setColorAt(1.0, QColor('#1a2230'))
    p.setBrush(QBrush(bg))
    p.setPen(Qt.NoPen)
    p.drawRoundedRect(QRectF(14 * s, 14 * s, 228 * s, 228 * s), 52 * s, 52 * s)

    # 2x2 四色分屏
    panes = [
        (50, 50, '#4da3ff'),    # 蓝
        (138, 50, '#3ddc97'),   # 绿
        (50, 138, '#ff8a5c'),   # 橙
        (138, 138, '#b388ff'),  # 紫
    ]
    for x, y, c in panes:
        grad = QLinearGradient(x * s, y * s, x * s, (y + 68) * s)
        grad.setColorAt(0.0, QColor(c))
        grad.setColorAt(1.0, QColor(c).darker(118))
        p.setBrush(QBrush(grad))
        p.setPen(QPen(QColor(0, 0, 0, 70), 3 * s))
        p.drawRoundedRect(QRectF(x * s, y * s, 68 * s, 68 * s), 15 * s, 15 * s)

    # 放大镜 (叠在右下, 象征缩放对比)
    cx, cy, r = 168 * s, 168 * s, 40 * s
    ring = QRadialGradient(cx, cy, r)
    ring.setColorAt(0.55, QColor(255, 255, 255, 20))
    ring.setColorAt(0.95, QColor(255, 255, 255, 70))
    p.setBrush(QBrush(ring))
    p.setPen(QPen(QColor(255, 255, 255, 235), 13 * s))
    p.drawEllipse(QPointF(cx, cy), r, r)
    # 镜柄
    p.setPen(QPen(QColor(255, 255, 255, 235), 15 * s, Qt.SolidLine, Qt.RoundCap))
    p.drawLine(QPointF(cx + r * 0.74, cy + r * 0.74),
               QPointF(cx + r * 1.30, cy + r * 1.30))
    # 镜片高光
    p.setPen(QPen(QColor(255, 255, 255, 120), 7 * s, Qt.SolidLine, Qt.RoundCap))
    p.drawLine(QPointF(cx - r * 0.45, cy - r * 0.30),
               QPointF(cx - r * 0.30, cy - r * 0.45))
    p.end()
    return pm


def main():
    app = None
    try:
        from PySide6.QtWidgets import QApplication
        app = QApplication([]) if not QApplication.instance() else QApplication.instance()
    except Exception:
        pass

    pm = draw_icon(256)
    png_path = OUT_DIR / 'icon.png'
    pm.save(str(png_path), 'PNG')

    # 用 PIL 生成多尺寸 ico
    from PIL import Image
    img = Image.open(png_path)
    img.save(str(OUT_DIR / 'icon.ico'),
             sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)])
    print('saved:', png_path, OUT_DIR / 'icon.ico')


if __name__ == '__main__':
    main()
