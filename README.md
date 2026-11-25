# ImageFolderCompareTool

A tool to compare a set of image folders.  These Image Folders contains image with same name.

# Ui of application
<img width="1920" height="1040" alt="image" src="https://github.com/user-attachments/assets/c4aa8bff-513b-4981-8b83-442440a99928" />
<img width="1920" height="1080" alt="image" src="https://github.com/user-attachments/assets/ca0f62f3-cdc7-45a4-86f5-d7c38d60583a" />

---

# 图片对比工具 (Image Compare Tool)

多目录图片同步对比工具，面向**超分辨率数据集 / 算法结果对比**场景：把 HR、LR、各 SR 算法输出文件夹加进来，同一张图 N 分屏并排显示，缩放平移全同步，逐像素看清差异。

基于 Python + PySide6（Qt6），单文件主程序，Windows 绿色免安装。

## 功能特性

- **多文件夹 N 分屏**：最多 6 个文件夹同时对比，分屏数量随勾选自动调整（4 屏自动铺满窗口）
- **同步缩放平移**：滚轮以鼠标为中心缩放、拖动平移，所有分屏显示同一图像区域；跨屏橙色准星指示鼠标对应位置（鼠标所在屏不画）
- **左右单屏对比**（S 键）：仅 2 个文件夹时，可拖动分割线，左 A 右 B 滑动对比
- **LR 自动对齐**：低分辨率图按参考尺寸自动放大对齐（默认 4 倍），高倍率下逐屏对位
- **大文件友好**：16K 级大图后台线程解码，界面不卡死；分屏右上角显示「加载中 X.Xs」实时计时，状态栏显示进度
- **文件夹扫描异步化**：网络盘扫描不阻塞界面，选图用扫描缓存匹配，响应更快
- **路径粘贴**：添加文件夹对话框的 Look In 输入框可直接粘贴 UNC 长路径回车跳转（回车不会关闭对话框）
- **文件夹拖动重排序**、记住勾选状态与上次目录（QSettings 持久化）
- **沉浸全屏**（F11）：零边距、图片顶满屏幕边缘，分屏间细分隔线；进出全屏保留缩放与观察位置
- **双击切换**：适配窗口 ↔ 100% 显示，切到 100% 时以双击位置为中心，全部分屏同步
- 附带**图形安装器**（PySide6 自研）：选择目录安装、创建桌面/开始菜单快捷方式、生成卸载脚本

## 快捷键

| 按键 | 功能 |
|---|---|
| ← / → | 上一张 / 下一张 |
| 空格 | 下一张 |
| F | 适配窗口 |
| 1 | 100% 缩放（以图片为中心） |
| 双击图片 | 适配窗口 ↔ 100% 切换（以双击位置为中心） |
| S | 切换左右单屏对比模式（仅 2 个文件夹时） |
| F11 | 全屏对比模式 |
| Ctrl+B | 隐藏/显示左侧文件列表 |
| F5 | 重新扫描文件夹 |
| Esc | 退出全屏 |

## 运行

```bash
pip install PySide6
python image_compare.py
```

- 支持 png / jpg / jpeg / bmp / webp / tif / tiff
- 图片按**文件名主干**匹配（不区分扩展名），各文件夹取共有图片的交集
- 配置保存在注册表 `HKEY_CURRENT_USER\Software\ArcVideo\ImageCompare`

## 打包

```bash
# 主程序 (onedir, 启动快)
python -m PyInstaller --noconfirm --onedir --windowed --icon icon.ico \
    --add-data "icon.png;." --add-data "icon.ico;." \
    --name 图片对比工具 image_compare.py

# 图形安装器 (onefile, 内嵌主程序目录作为 payload)
python -m PyInstaller --noconfirm --onefile --windowed --icon icon.ico \
    --name 图片文件夹对比工具 --add-data "dist/图片对比工具;payload" installer.py
```

也可以直接用仓库里的 spec 文件：`python -m PyInstaller 图片对比工具.spec`。

## 目录结构

```
image_compare.py            主程序
installer.py                图形安装程序
gen_icon.py                 图标生成脚本
icon.ico / icon.png         应用图标
图片对比工具.spec            主程序打包配置
图片文件夹对比工具.spec      安装器打包配置
```

## 实现要点

- 所有分屏共享一套参考坐标系（`widget = center - (ref - center) × zoom`），缩放/平移天然同步；LR 等低分辨率图只按比例缩放矩形宽高，不参与 pan/zoom 计算，保证任意倍率下严格对齐
- 图片解码使用 `QThreadPool` + `QRunnable` 后台执行（`QImageReader.setAllocationLimit(0)` 解除 Qt6 默认 256MB 分配上限），带代数校验丢弃过期结果，快速连续切图不闪错图
- 文件夹扫描与目录自动发现同样走后台线程，通过信号回主线程合并结果

## License

MIT
