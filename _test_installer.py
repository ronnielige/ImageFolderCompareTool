# -*- coding: utf-8 -*-
"""安装程序冒烟测试: 界面元素 + 真实 payload 布局的校验与后台复制。"""
import sys
import time
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from PySide6.QtWidgets import QApplication
import installer as ins

app = QApplication(sys.argv)
win = ins.InstallerWindow()
win.show()

# 1) 界面元素
assert win.windowTitle() == '图片文件夹对比工具 - 安装向导', win.windowTitle()
assert win.b_install.text() == '立即安装'
src_text = open(ins.__file__, encoding='utf-8').read()
assert '#bannerTitle' in src_text and 'qlineargradient' in src_text
print('PASS 1: 界面元素与样式齐全')

# 2) 模拟真实 onedir payload 布局: payload/APP.exe + payload/_internal/
tmp = Path(tempfile.mkdtemp())
fake_src = tmp / 'payload'
(fake_src / '_internal').mkdir(parents=True)
(fake_src / f'{ins.APP_NAME}.exe').write_bytes(b'MZ')
(fake_src / '_internal' / 'lib.dat').write_bytes(b'x' * 1000)
(fake_src / '_internal' / 'icon.ico').write_bytes(b'ICO')
ins.payload_dir = lambda: fake_src   # 让 find_app_icon / install 检查指向模拟目录

# 校验逻辑应通过 (不再报"安装包数据缺失")
assert (fake_src / f'{ins.APP_NAME}.exe').exists(), 'payload 校验应通过'
icon = ins.find_app_icon()
assert icon is not None and icon.name == 'icon.ico', f'图标查找: {icon}'
print('PASS 2: payload 校验通过, 图标定位到 _internal/icon.ico')

# 3) 后台复制: 保持 payload 顶层结构, 安装到 dst/APP_NAME/
dst = tmp / 'install_here'
w = ins.CopyWorker(fake_src, dst)
result = {}
w.progress.connect(lambda d, t, n: result.setdefault('prog', (d, t)))
w.finished_ok.connect(lambda t: result.__setitem__('done', t))
w.failed.connect(lambda m: result.__setitem__('fail', m))
w.start()
t0 = time.time()
while 'done' not in result and 'fail' not in result and time.time() - t0 < 10:
    app.processEvents(); time.sleep(0.01)

assert 'fail' not in result, result
target = dst / ins.APP_NAME
assert (target / f'{ins.APP_NAME}.exe').exists()
assert (target / '_internal' / 'lib.dat').stat().st_size == 1000
print('PASS 3: 后台复制完成, 目标结构正确:', target)
print('ALL OK')
