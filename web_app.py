from __future__ import annotations

import secrets
import socket
import threading
import webbrowser
from datetime import datetime
from pathlib import Path
from typing import Any

from flask import Flask, render_template, request, send_from_directory
from werkzeug.utils import secure_filename

from main import IMAGE_EXTENSIONS, OUTPUT_DIR, ensure_directories, load_config, process_image_files

UPLOADS_DIR = OUTPUT_DIR / "uploads"
HOST = "127.0.0.1"
PORT = 5000
LOCAL_URL = f"http://{HOST}:{PORT}"

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 100 * 1024 * 1024


def is_port_in_use(host: str = HOST, port: int = PORT) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(1)
        return sock.connect_ex((host, port)) == 0


def open_browser() -> None:
    webbrowser.open(LOCAL_URL)


def make_batch_dir() -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    suffix = secrets.token_hex(3)
    batch_dir = UPLOADS_DIR / f"{stamp}_{suffix}"
    batch_dir.mkdir(parents=True, exist_ok=True)
    return batch_dir


def allowed_file(filename: str) -> bool:
    return Path(filename).suffix.lower() in IMAGE_EXTENSIONS


def save_uploads(files: list[Any]) -> tuple[list[Path], list[dict[str, Any]], Path | None]:
    saved_paths: list[Path] = []
    rejected: list[dict[str, Any]] = []
    batch_dir: Path | None = None

    for index, file in enumerate(files, start=1):
        original_name = file.filename or ""
        if not original_name:
            continue
        if not allowed_file(original_name):
            rejected.append(
                {
                    "name": original_name,
                    "success": False,
                    "error": "文件格式不支持。请上传 PNG/JPG/JPEG/WEBP/HEIC/HEIF 图片。",
                    "text_summary": "",
                }
            )
            continue

        if batch_dir is None:
            batch_dir = make_batch_dir()

        safe_name = secure_filename(original_name)
        if not safe_name:
            safe_name = f"upload_{index}{Path(original_name).suffix.lower()}"
        save_path = batch_dir / f"{index:03d}_{safe_name}"
        file.save(save_path)
        saved_paths.append(save_path)

    return saved_paths, rejected, batch_dir


@app.route("/", methods=["GET"])
def index() -> str:
    return render_template("upload.html", result=None, rejected=[], output_links=None)


@app.route("/upload", methods=["POST"])
def upload() -> str:
    ensure_directories()
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

    files = request.files.getlist("images")
    saved_paths, rejected, batch_dir = save_uploads(files)
    result = None
    error = ""

    if saved_paths:
        try:
            result = process_image_files(saved_paths, config=load_config())
            if rejected:
                result["image_results"] = rejected + result["image_results"]
                result["total_images"] += len(rejected)
                result["failure_count"] += len(rejected)
        except Exception as exc:
            error = str(exc)
    elif not rejected:
        error = "没有选择可处理的图片。"

    output_links = {
        "chat_html": "/output/chat.html",
        "review_html": "/output/review.html",
        "data_json": "/output/data.json",
        "chat_txt": "/output/chat.txt",
    }
    return render_template(
        "upload.html",
        result=result,
        rejected=rejected if result is None else [],
        error=error,
        batch_dir=batch_dir,
        output_links=output_links,
    )


@app.route("/output/<path:filename>", methods=["GET"])
def output_file(filename: str):
    return send_from_directory(OUTPUT_DIR, filename)


if __name__ == "__main__":
    ensure_directories()
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    if is_port_in_use():
        print("检测到 5000 端口已被占用。")
        print("请关闭已有 OCR 服务后重试。")
        raise SystemExit(1)

    threading.Timer(1.5, open_browser).start()
    print(f"网页 OCR 服务启动中：{LOCAL_URL}")
    app.run(host=HOST, port=PORT, debug=False)
