# 实际验证记录

日期：2026-10-08（日本时间）。

## 环境

- Windows 11 Pro x64，10.0.26200。
- Python 3.11.13（单独安装并创建 `.venv311`），另以 Python 3.13.14 做过首轮验证。
- PySide6 6.11.2、psutil 7.2.2、pytest 9.1.1、PyInstaller 6.22.3。
- FFmpeg / FFprobe 8.1.2 essentials build（独立下载到 `.validation`，未修改系统 PATH），首轮另使用系统 9.0.1。

## 已完成

Python 3.11.13 + FFmpeg 8.1.2：**24 passed in 10.36s**。包括真实 FFmpeg 集成测试、GUI 异步输出、静帧前后逐帧解码、源文件硬链接保护和时:分:秒输入（含超过 24 小时及拒绝毫秒输入）。QTest 真实键盘编辑测试验证可删除、重输和确认时间。另验证默认输出使用源目录、源文件名加时间戳、重名追加编号，以及切换预览保留用户自定义路径。

测试命令：

```powershell
$env:VIDEOTRIM_FFMPEG_DIR = Join-Path $PWD '.validation\ffmpeg8\ffmpeg-8.1.2-essentials_build\bin'
.\.venv311\Scripts\python.exe -m pytest -q
```

音视频同步检查除流起始时间 / 时长差外，还构造音轨延迟 0.5 秒的真实媒体，解码输出 PCM：验证开头保持静音且后续音频存在，防止统一时间戳错误地提前音轨。

GUI 在 offscreen 下验证导入、片段创建、删除后重新导入和异步输出；另实际启动桌面窗口并检查截图中的布局、字号、中文显示及控件。逐帧通过 FFprobe 时间戳检查 0.400 秒的前一帧为 0.360 秒，后一帧为 0.440 秒，并真实解码 PNG。

PyInstaller 使用 Python 3.11 构建 onedir EXE。构建时已修复 PATH 中 Poppler 的同名 ICU DLL 被误收入包的问题：脚本隔离搜索路径，使用选定 PySide6 及系统 DLL。

构建命令：

```powershell
.\build_exe.ps1 -SkipFFmpeg -PythonPath .\.venv311\Scripts\python.exe
```

本次产物不内置外部 FFmpeg / FFprobe；可使用系统 PATH 或 `VIDEOTRIM_FFMPEG_DIR`，无需安装 Python。必须保留 EXE 同级 `_internal` 目录。

最终 EXE 已用 `tests/exe_smoke.py` 隐藏启动、确认本进程的 `VideoTrim Studio` 主窗口，再向其发送正常关闭事件；**退出码 0**。此检查验证打包后的启动与关闭，不代表已在 EXE 中重复全部媒体测试。

```powershell
.\.venv311\Scripts\python.exe tests\exe_smoke.py dist\VideoTrimStudio\VideoTrimStudio.exe
```

## 验证边界

不等同于所有硬件的 Windows 10/11 用户验收。硬件编码在本机启动时实际试编码；其他 GPU / 驱动需当地验证。未对数百 GB 视频、数百片段、HDR 色彩保真、异常时间戳、所有 VFR / 长 GOP 和损坏素材进行全面压力测试。P2 缩略图时间轴及更多输出容器尚未实现。
