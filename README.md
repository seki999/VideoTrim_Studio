# VideoTrim Studio

完全本地运行的 Windows 10/11 x64 视频剪切、合并、压缩工具。Python 3.11+、PySide6、外部 FFmpeg / FFprobe；不调用云服务、AI 模型或换脸功能。

## 安装与启动（Windows PowerShell）

先安装 Python 3.11 x64。推荐 FFmpeg **8.x** 的完整 Windows 构建，需包含 libx264 和 libx265。将解压后的 bin 目录添加到 PATH，重新打开 PowerShell。

```powershell
cd C:\Users\seki9\Documents\VideoTrim_Studio
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
ffmpeg -version
ffprobe -version
python main.py
```

若激活脚本受执行策略限制，可直接运行 `.\.venv\Scripts\python.exe -m pip install -r requirements.txt` 与 `.\.venv\Scripts\python.exe main.py`。不需要修改系统执行策略。

检测顺序：环境变量 `VIDEOTRIM_FFMPEG_DIR` → 应用资源目录 `assets/ffmpeg` → EXE 同目录 → PATH。两项工具需来自同一构建。例如：

```powershell
$env:VIDEOTRIM_FFMPEG_DIR = 'C:\Tools\ffmpeg-8\bin'
python main.py
```

下载入口：[FFmpeg 官方下载页](https://ffmpeg.org/download.html)。程序不自动下载组件。可将 `ffmpeg.exe`、`ffprobe.exe` 放在 `assets\ffmpeg`，不将这些二进制提交到源码仓库。

## 使用

1. 添加文件、添加文件夹或拖入 MP4 / MOV / MKV / AVI / WEBM。左侧显示分辨率、帧率、编码、时长、大小和音轨。拖动列表改变顺序。
2. 中央播放器播放、暂停、前后跳转 5 秒。逐帧按钮通过后台 FFprobe 读取相邻帧实际时间戳，再用 FFmpeg 解码静帧展示。拖动黄色时间轴手柄或输入“小时:分:秒”（例如 `01:23:45`，不输入毫秒，小时支持超过 24）；添加多个片段。片段列表可拖动排序、删除、更新时间。滚轮缩放，Shift + 滚轮平移。剪切范围使用整数秒。
3. 首次点击时间框会选中已有时间，直接输入例如开始 `00:00:10`、结束 `00:00:30`，也可用“当前位置设为开始 / 结束”按钮标记播放器位置；再点击“添加片段”。片段列表有内容时按片段顺序输出；没有片段时按源视频列表顺序输出。仅剪切一个视频时也要点击“添加片段”。压缩单视频直接导入后输出即可。
4. 选择无损、CRF、目标码率或目标大小，设置分辨率、帧率和输出 MP4，开始处理。默认保存到源视频所在文件夹，名称为 `源文件名_YYYYMMDD_HHMMSS.mp4`（电脑当地时间），重名时追加 `_2` 等。合并默认以实际输出顺序中的首个源文件为基准。手动修改输出位置后，切换预览不会改变该位置。
5. 勾选批量输出后，每个源文件作为完整单独任务进入队列，各自默认输出到自己的源目录，使用各自源文件名加同一批次时间戳，忽略片段列表；手动选择输出位置时，整批使用所选目录，仍以各自源文件名加时间戳命名。停止会取消当前任务及尚未开始的队列。

**极速无损限制：** 使用 concat demuxer 和 `-c copy`；剪切开始位置受关键帧影响，可能包含边界前后的帧，时长及拼接处可能出现偏差。需要精确时间时选重新编码模式。流复制不能缩放或改帧率。兼容检查比较编码、编码参数哈希、分辨率、像素格式、时间基、帧率与音轨参数；不兼容或 MP4 不支持的流自动转为 H.264（默认编码器）/ AAC。仅保留首个视频与首个音轨，字幕、附件及额外音轨不输出。

**精确模式：** trim / atrim → 重置时间戳 → 比例缩放与黑边（可关闭改为拉伸）→ 统一 fps / 48 kHz 双声道 → concat → 一次编码。无音轨输入补静音；短音轨补齐。按输出帧率量化时间，毫秒参数不意味着视频有毫秒级帧。合并“保持原始”使用首个片段的分辨率与帧率。编码输出统一为偶数尺寸。任意片段重排和压缩通常不产生媒体中间文件；双遍模式需要分析日志且执行两次编码。

**压缩：** libx264 / libx265；QSV、NVENC、AMF 在后台通过实际一帧编码测试后才列出，失败仍可选软件。硬件编码质量参数不等同于 x264 CRF。目标大小按总时长、128 kbps 音频及 3% 封装余量估算，不保证精确命中；双遍仅支持 libx264 的码率 / 大小模式。无法保证所有视频都能无画质损失地缩小；CRF 18 也不是数学无损。

## 稳定性与文件安全

- 所有外部程序使用参数数组，无 shell 拼接。路径使用 pathlib 和 UTF-8；concat 清单对单引号专门转义。
- ffprobe JSON 检测在后台线程执行。FFmpeg 队列使用 QThread，通过 `-progress pipe:1` 获取进度和剩余时间估算。
- 停止通过 psutil 终止进程树。输出先写同目标目录下的临时目录，通过 ffprobe 基础有效性验证后原子提交；任务成功、失败、取消均清理临时文件。
- 禁止覆盖源文件，即使确认也必须选其他输出路径。已存在的其他输出必须确认覆盖；失败保留原有文件。界面任务启动后使用独立快照，编辑列表不修改运行任务。
- 日志持久保存在 `%USERPROFILE%\.videotrim\logs`，包含参数和 FFmpeg 错误。可能包含本地文件路径。
- 大文件按流处理，不将媒体整体读入内存；多路复杂滤镜仍需足够内存与磁盘。输出所在磁盘应有足够空间。

## 自动化测试

```powershell
python -m pip install -r requirements-build.txt
python -m pytest -q
```

集成测试通过 lavfi 生成真实 H.264/AAC 视频，真实执行 FFmpeg，不用 mock 替代。覆盖快速剪切、非整数边界精确剪切、同流无损合并、异分辨率合并、静音/单声道/双声道、压缩、多片段重排、双遍目标大小、H.265、中文/日文/空格/单引号/特殊字符路径、运行中取消、源文件保护、失败清理。ffprobe 验证编码、分辨率、时长、音轨、起始时间及音视频流时长差。缺少 FFmpeg 时跳过集成测试，不算验证通过。GUI 使用 offscreen 做导入与片段操作测试。

## 构建 Windows EXE

```powershell
python -m pip install -r requirements-build.txt
.\build_exe.ps1 -SkipFFmpeg
# 或携带 FFmpeg（先准备下述许可证材料）
.\build_exe.ps1 -FFmpegDir 'C:\Tools\ffmpeg-8\bin'
```

输出：`dist\VideoTrimStudio\VideoTrimStudio.exe`。采用 **onedir**，必须分发整个 `VideoTrimStudio` 目录，不能只复制 EXE。Qt Multimedia 插件随 PySide6 打包；目标机器需 Windows 10/11 x64。`-SkipFFmpeg` 时目标机器自行安装并配置 PATH 或放入同目录。打包运行时仍完全离线。

携带 FFmpeg 时，指定目录必须包含两项 exe 和 `licenses` 子目录，其中放入许可证文本、精确对应源码（或符合许可证的源码提供材料）、构建配置及修改说明。脚本只检查目录存在，不能自动证明法律合规。不要将不明来源或 `--enable-nonfree` 的构建直接再分发。

## 第三方许可证

FFmpeg 默认 LGPL 2.1 或更高，但启用 GPL 部分后整个 FFmpeg 构建适用 GPL；常见含 libx264 / libx265 的构建启用 GPL，`--enable-version3` 还可能改变版本要求。请运行 `ffmpeg -L`、`ffmpeg -buildconf` 检查所使用的具体构建。外部 subprocess 调用不等于把 FFmpeg 库直接链接进 Python 程序，但**随软件分发 FFmpeg 二进制仍须满足该构建的许可证**，提供版权声明、完整许可证及对应源码/构建材料。涉及编码专利的商业分发需要另外评估。[FFmpeg 官方许可证说明](https://ffmpeg.org/legal.html)。

PySide6 / Qt for Python 提供 LGPLv3 / GPLv3 / 商业许可选择，Qt 各模块及第三方组件可能有其他许可。采用 LGPL 路径应保留版权与许可证文本、允许相应库替换及为调试库修改进行逆向工程，履行对应源码等义务。onedir 有助于保持动态库可替换，但不自动免除这些义务。Qt Multimedia 使用的后端组件也需要一并检查。PyInstaller 应用打包例外允许打包程序采用自身许可；psutil 为 BSD-3-Clause，pytest 为 MIT。发布前审核打包产物中的全部第三方声明。[Qt for Python 官方许可证](https://doc.qt.io/qtforpython-6/licenses.html)、[PyInstaller 许可](https://pyinstaller.org/en/stable/license.html)。本项目尚未选择自身开源许可证，源码交付不代表授予不受限制的再分发许可。

## 当前范围与限制

已实现 P0 处理功能，以及多片段时间轴、队列、硬件检测、主题与输出参数保存、目标大小双遍编码。界面中文默认，大字体和深浅主题。源码按 gui / core / models / tests / assets 分层。

仍需完善：缩略图时间轴、完整项目保存、可编辑持久任务队列、批量按各自片段方案输出、完整多语言界面、更多输出容器。逐帧静帧解码可能比实时播放慢，长 GOP 素材需要从前一关键帧解码；继续播放使用 Qt 的 seek，未建立全视频帧缓存。旋转元数据、HDR / 10-bit 色彩、损坏或非零起始时间的特殊素材、数百片段及超长视频需进一步验证；当前统一 yuv420p 不提供 HDR 保真。输出验证为媒体结构与正时长检查，并非逐帧解码审计。无损 concat 的兼容检查保守且无法保证所有源文件时间戳健康。

开发验证机器与结果见 `VALIDATION.md`。运行在 Python 3.11 的兼容性以实际验证结果为准；不要将其他版本的测试结果表述成已完成全部 Windows 11 用户验收。
