# chat_ocr_project

这是一个 Windows 本地运行的 QQ 群聊截图 OCR 项目。它会读取 `screenshots/` 中的聊天截图，尽量保留聊天顺序、时间节点、昵称、左右消息和气泡结构，并生成适合后续分析和人工校对的文件。

所有图片都只在本机处理，不上传网络，不依赖收费 API，也不会修改 `screenshots/` 里的原始截图。

## 目录结构

```text
chat_ocr_project/
├─ screenshots/              # 放 QQ 聊天截图
├─ output/                   # 所有输出文件
│  └─ debug/                 # 预处理后的调试图片
├─ templates/
│  ├─ chat_template.html
│  └─ review_template.html
├─ main.py
├─ config.json
├─ requirements.txt
└─ README.md
```

## 环境要求

- Windows 10 或 Windows 11
- Python 3.10 或 3.11 更稳妥
- 建议使用虚拟环境
- CPU 即可运行，速度会慢一些但更省心

## 安装 Python

1. 打开 https://www.python.org/downloads/windows/
2. 下载 Python 3.10 或 3.11 的 Windows installer
3. 安装时勾选 `Add python.exe to PATH`
4. 打开 PowerShell，检查版本：

```powershell
python --version
pip --version
```

## 创建虚拟环境

在本项目目录运行：

```powershell
cd C:\Users\Salt2\Downloads\小学搜题酱\chat_ocr_project
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

如果 PowerShell 不允许激活虚拟环境，可以先运行：

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

然后重新执行激活命令。

## 安装依赖

```powershell
python -m pip install --upgrade pip
pip install -r requirements.txt
```

`requirements.txt` 包含：

- `paddleocr`
- `paddlepaddle`
- `opencv-python`
- `pillow`
- `numpy`
- `jinja2`
- `natsort`

## Windows 安装 PaddlePaddle 的注意事项

如果 `pip install -r requirements.txt` 在 `paddlepaddle` 处失败，常见原因是 Python 版本或系统架构不匹配。

建议处理顺序：

1. 优先使用 64 位 Python 3.10 或 3.11。
2. 升级 pip：

```powershell
python -m pip install --upgrade pip setuptools wheel
```

3. 单独安装 CPU 版 PaddlePaddle：

```powershell
pip install paddlepaddle
```

4. 再安装其他依赖：

```powershell
pip install paddleocr opencv-python pillow numpy jinja2 natsort
```

如果仍然失败，请到 PaddlePaddle 官网查看与你的 Python 版本匹配的 Windows 安装命令。没有安装成功时，本项目会在终端和 `output/errors.log` 给出清晰提示。

## 放入截图

把 QQ 聊天截图放进：

```text
chat_ocr_project/screenshots/
```

支持格式：

- `.png`
- `.jpg`
- `.jpeg`
- `.webp`

文件会按自然顺序处理，例如 `1.png`、`2.png`、`10.png` 会按 1、2、10 的顺序读取。

## 运行

```powershell
cd C:\Users\Salt2\Downloads\小学搜题酱\chat_ocr_project
.\.venv\Scripts\Activate.ps1
python main.py
```

如果 `screenshots/` 不存在，程序会自动创建。  
如果 `screenshots/` 为空，程序会提示你放入截图后退出，不会报错。

## 输出文件

所有输出都固定在 `output/`：

- `output/data.json`：结构化聊天记录，包含 `type`、`time`、`sender`、`side`、`text`、`source_image`、`bbox`、`bbox_space`
- `output/chat.txt`：适合复制给 ChatGPT 继续分析的纯文本聊天记录
- `output/chat.html`：接近 QQ 聊天样式的静态 HTML，可直接双击打开
- `output/review.html`：人工校对页面，左侧看截图，右侧看识别记录编号
- `output/debug/*_processed.png`：OCR 前的预处理图片
- `output/process.log`：每张图的处理数量和输出路径
- `output/errors.log`：失败图片、错误原因和 traceback

## config.json 怎么调

默认配置：

```json
{
  "ocr_engine": "paddleocr",
  "scale": 2,
  "crop_top_ratio": 0.12,
  "crop_bottom_ratio": 0.04,
  "confidence_threshold": 0.5,
  "enable_dedup": true,
  "default_sender": "UNKNOWN"
}
```

字段说明：

- `ocr_engine`：默认 `paddleocr`。代码里预留了 `rapidocr` 名称，但当前先保证 PaddleOCR 可跑。
- `scale`：OCR 前放大倍数。文字太小可调到 `2.5` 或 `3`，但会更慢。
- `crop_top_ratio`：裁掉顶部状态栏和标题栏的比例。时间节点被裁掉时调小。
- `crop_bottom_ratio`：裁掉底部手势条的比例。底部消息被裁掉时调小。
- `confidence_threshold`：OCR 置信度过滤阈值。漏字多可调低，例如 `0.35`。
- `enable_dedup`：是否启用保守去重。只删除 `sender + text + time` 完全相同的消息。
- `default_sender`：识别不到昵称时使用的默认发送者。

## OCR 结果不准怎么办

可以按这个顺序检查：

1. 打开 `output/debug/` 看预处理图片是否清晰。
2. 如果顶部聊天时间被裁掉，调小 `crop_top_ratio`。
3. 如果底部消息被裁掉，调小 `crop_bottom_ratio`。
4. 如果文字太小，调大 `scale`。
5. 如果漏掉很多文字，调低 `confidence_threshold`。
6. 如果误识别太多，调高 `confidence_threshold`。
7. 尽量使用清晰、无压缩、无裁切的原图截图。

OCR 不可能 100% 准确，尤其是中文昵称、表情、压缩截图、小字号、深浅相近背景、重叠区域和长图拼接边缘。这个项目的目标是尽量保留结构，并提供 `review.html` 和 `data.json` 方便人工校对。

## 人工校对 data.json

运行后双击打开：

```text
output/review.html
```

左侧是原始截图，右侧是识别记录。每条记录都有编号，并显示：

- `type`
- `time`
- `sender`
- `side`
- `text`
- `source_image`
- `bbox`
- `bbox_space`

根据编号找到问题后，直接编辑 `output/data.json` 即可。网页本身是静态 HTML，不会直接保存修改。

## 常见报错

### 没有安装 PaddleOCR

终端会看到类似：

```text
OCR 初始化失败：没有安装 PaddleOCR...
```

处理：

```powershell
pip install -r requirements.txt
```

### paddlepaddle 安装失败

优先确认 Python 是 64 位 3.10 或 3.11，然后升级 pip：

```powershell
python -m pip install --upgrade pip setuptools wheel
pip install paddlepaddle
```

### opencv-python 缺失

```powershell
pip install opencv-python
```

### 识别过程中某张图失败

单张图片失败不会中断整个程序。失败详情在：

```text
output/errors.log
```

可以检查图片是否损坏、格式是否受支持，或文件名是否异常。

## 验收说明

- 项目目录结构已完整创建。
- `screenshots/` 为空时，程序会正常提示并退出。
- 没有安装 PaddleOCR 时，程序会输出清晰错误信息。
- 所有输出文件固定在 `output/`。
- 原始截图只读取，不修改。
- `chat.html` 和 `review.html` 都是静态文件，可以直接双击打开。
- README 包含 Windows 安装 PaddlePaddle 的常见问题处理方式。
