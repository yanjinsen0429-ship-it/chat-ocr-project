from __future__ import annotations

import json
import logging
import os
import re
import sys
import traceback
from dataclasses import dataclass
from pathlib import Path
from statistics import median
from typing import Any

BASE_DIR = Path(__file__).resolve().parent
SCREENSHOTS_DIR = BASE_DIR / "screenshots"
OUTPUT_DIR = BASE_DIR / "output"
DEBUG_DIR = OUTPUT_DIR / "debug"
TEMPLATES_DIR = BASE_DIR / "templates"
CONFIG_PATH = BASE_DIR / "config.json"

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}


@dataclass
class OCRItem:
    text: str
    confidence: float
    bbox: list[float]
    bbox_space: str

    @property
    def x1(self) -> float:
        return self.bbox[0]

    @property
    def y1(self) -> float:
        return self.bbox[1]

    @property
    def x2(self) -> float:
        return self.bbox[2]

    @property
    def y2(self) -> float:
        return self.bbox[3]

    @property
    def width(self) -> float:
        return max(0.0, self.x2 - self.x1)

    @property
    def height(self) -> float:
        return max(0.0, self.y2 - self.y1)

    @property
    def center_x(self) -> float:
        return (self.x1 + self.x2) / 2

    @property
    def center_y(self) -> float:
        return (self.y1 + self.y2) / 2


def load_config() -> dict[str, Any]:
    defaults = {
        "ocr_engine": "paddleocr",
        "scale": 2,
        "crop_top_ratio": 0.12,
        "crop_bottom_ratio": 0.04,
        "confidence_threshold": 0.5,
        "enable_dedup": True,
        "default_sender": "UNKNOWN",
    }
    if not CONFIG_PATH.exists():
        CONFIG_PATH.write_text(json.dumps(defaults, ensure_ascii=False, indent=2), encoding="utf-8")
        return defaults

    try:
        with CONFIG_PATH.open("r", encoding="utf-8") as f:
            loaded = json.load(f)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"config.json 不是合法 JSON：{exc}") from exc

    defaults.update(loaded)
    return defaults


def ensure_directories() -> None:
    SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    DEBUG_DIR.mkdir(parents=True, exist_ok=True)
    TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)


def setup_logging() -> tuple[logging.Logger, logging.Logger]:
    process_logger = logging.getLogger("process")
    error_logger = logging.getLogger("errors")
    process_logger.handlers.clear()
    error_logger.handlers.clear()
    process_logger.setLevel(logging.INFO)
    error_logger.setLevel(logging.ERROR)

    process_handler = logging.FileHandler(OUTPUT_DIR / "process.log", mode="w", encoding="utf-8")
    error_handler = logging.FileHandler(OUTPUT_DIR / "errors.log", mode="w", encoding="utf-8")
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    process_handler.setFormatter(formatter)
    error_handler.setFormatter(formatter)
    process_logger.addHandler(process_handler)
    error_logger.addHandler(error_handler)
    return process_logger, error_logger


def natural_key(path: Path) -> list[Any]:
    parts = re.split(r"(\d+)", path.name.lower())
    return [int(part) if part.isdigit() else part for part in parts]


def get_screenshot_files() -> list[Path]:
    files = [p for p in SCREENSHOTS_DIR.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS]
    try:
        from natsort import natsorted

        return list(natsorted(files, key=lambda p: p.name))
    except Exception:
        return sorted(files, key=natural_key)


def preprocess_image(image_path: Path, config: dict[str, Any]) -> tuple[Path, dict[str, Any]]:
    try:
        import cv2
        import numpy as np
    except ImportError as exc:
        raise RuntimeError("缺少 opencv-python 或 numpy，请先运行 pip install -r requirements.txt") from exc

    image = cv2.imdecode(np.fromfile(str(image_path), dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise RuntimeError("图片无法读取，可能格式损坏或路径包含异常字符")

    original_height, original_width = image.shape[:2]
    crop_top = int(original_height * float(config["crop_top_ratio"]))
    crop_bottom = int(original_height * float(config["crop_bottom_ratio"]))
    bottom = max(crop_top + 1, original_height - crop_bottom)
    cropped = image[crop_top:bottom, :]

    scale = max(1.0, float(config["scale"]))
    resized = cv2.resize(cropped, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)
    denoised = cv2.fastNlMeansDenoising(gray, h=7, templateWindowSize=7, searchWindowSize=21)
    blurred = cv2.GaussianBlur(denoised, (0, 0), sigmaX=1.0)
    sharpened = cv2.addWeighted(denoised, 1.45, blurred, -0.45, 0)

    output_path = DEBUG_DIR / f"{image_path.stem}_processed.png"
    success, encoded = cv2.imencode(".png", sharpened)
    if not success:
        raise RuntimeError("预处理图片编码失败")
    encoded.tofile(str(output_path))

    transform = {
        "scale": scale,
        "crop_top": crop_top,
        "crop_bottom": crop_bottom,
        "original_width": original_width,
        "original_height": original_height,
        "processed_path": output_path,
    }
    return output_path, transform


def init_ocr_engine(config: dict[str, Any]) -> Any:
    engine = str(config.get("ocr_engine", "paddleocr")).lower()
    if engine == "rapidocr":
        raise RuntimeError("rapidocr 已预留配置入口，但当前项目先实现 paddleocr。请把 ocr_engine 改为 paddleocr。")
    if engine != "paddleocr":
        raise RuntimeError(f"不支持的 OCR 引擎：{engine}")

    configure_paddle_runtime()

    try:
        from paddleocr import PaddleOCR
    except ImportError as exc:
        raise RuntimeError(
            "没有安装 PaddleOCR。请先运行 pip install -r requirements.txt；"
            "如果 paddlepaddle 安装失败，请看 README 的 Windows 处理方式。"
        ) from exc

    try:
        return PaddleOCR(
            device="cpu",
            enable_mkldnn=False,
            cpu_threads=1,
            text_detection_model_name="PP-OCRv5_mobile_det",
            text_recognition_model_name="PP-OCRv5_mobile_rec",
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
        )
    except Exception as exc:
        raise RuntimeError(f"PaddleOCR 初始化失败：{exc}") from exc


def configure_paddle_runtime() -> None:
    """Keep PaddleOCR on the stable Windows CPU execution path."""
    os.environ.setdefault("FLAGS_use_mkldnn", "0")
    os.environ.setdefault("FLAGS_enable_pir_api", "0")
    os.environ.setdefault("PADDLE_PDX_ENABLE_MKLDNN_BYDEFAULT", "False")
    os.environ.setdefault("PADDLE_PDX_CPU_NUM_THREADS", "1")
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    os.environ.setdefault("MKL_NUM_THREADS", "1")


def run_ocr(ocr_engine: Any, image_path: Path) -> Any:
    image = str(image_path)
    if hasattr(ocr_engine, "predict"):
        return list(ocr_engine.predict(image))
    if hasattr(ocr_engine, "ocr"):
        return ocr_engine.ocr(image)
    raise RuntimeError("PaddleOCR 对象没有可用的 ocr 或 predict 方法")


def normalize_ocr_result(raw_result: Any, transform: dict[str, Any], confidence_threshold: float) -> list[OCRItem]:
    candidates: list[OCRItem] = []

    def first_present(node: dict[str, Any], *keys: str) -> Any:
        for key in keys:
            if key in node and node[key] is not None:
                return node[key]
        return None

    def as_sequence(value: Any) -> Any:
        if hasattr(value, "tolist"):
            return value.tolist()
        return value

    def is_bbox(value: Any) -> bool:
        value = as_sequence(value)
        return (
            isinstance(value, (list, tuple))
            and len(value) >= 4
            and all(isinstance(point, (list, tuple)) and len(point) >= 2 for point in value[:4])
        )

    def collect(node: Any, active_bbox: Any = None) -> None:
        node = as_sequence(node)
        if isinstance(node, dict):
            texts = as_sequence(first_present(node, "rec_texts", "texts"))
            scores = as_sequence(first_present(node, "rec_scores", "scores"))
            boxes = as_sequence(first_present(node, "rec_boxes", "dt_polys", "boxes"))
            if isinstance(texts, list) and isinstance(boxes, list):
                for idx, text in enumerate(texts):
                    score = float(scores[idx]) if isinstance(scores, list) and idx < len(scores) else 1.0
                    add_item(text, score, boxes[idx])
                return
            for value in node.values():
                collect(value, active_bbox)
            return

        if isinstance(node, (list, tuple)):
            if len(node) >= 2 and is_bbox(node[0]):
                bbox = node[0]
                second = node[1]
                if isinstance(second, (list, tuple)) and second and isinstance(second[0], str):
                    text = second[0]
                    score = float(second[1]) if len(second) > 1 and isinstance(second[1], (int, float)) else 1.0
                    add_item(text, score, bbox)
                    return
                collect(second, bbox)
                for extra in node[2:]:
                    collect(extra, bbox)
                return
            if active_bbox is not None and node and isinstance(node[0], str):
                score = float(node[1]) if len(node) > 1 and isinstance(node[1], (int, float)) else 1.0
                add_item(node[0], score, active_bbox)
                return
            for value in node:
                collect(value, active_bbox)

    def add_item(text: Any, score: float, bbox_like: Any) -> None:
        text = str(text).strip()
        if not text or score < confidence_threshold:
            return
        bbox = bbox_to_original_rect(bbox_like, transform)
        candidates.append(OCRItem(text=text, confidence=score, bbox=bbox, bbox_space="original_image"))

    collect(raw_result)
    return sorted(candidates, key=lambda item: (item.y1, item.x1))


def bbox_to_original_rect(bbox_like: Any, transform: dict[str, Any]) -> list[float]:
    import numpy as np

    scale = float(transform["scale"])
    crop_top = float(transform["crop_top"])

    points: list[tuple[float, float]] = []
    if isinstance(bbox_like, np.ndarray):
        bbox_like = bbox_like.tolist()

    if isinstance(bbox_like, (list, tuple)) and len(bbox_like) == 4 and all(
        isinstance(v, (int, float, np.integer, np.floating)) for v in bbox_like
    ):
        x1, y1, x2, y2 = [float(v) for v in bbox_like]
        points = [(x1, y1), (x2, y1), (x2, y2), (x1, y2)]
    elif isinstance(bbox_like, (list, tuple)):
        for point in bbox_like[:4]:
            if isinstance(point, np.ndarray):
                point = point.tolist()
            if isinstance(point, (list, tuple)) and len(point) >= 2:
                points.append((float(point[0]), float(point[1])))

    if not points:
        return [0, 0, 0, 0]

    xs = [p[0] / scale for p in points]
    ys = [(p[1] / scale) + crop_top for p in points]
    return [round(min(xs), 1), round(min(ys), 1), round(max(xs), 1), round(max(ys), 1)]


def is_time_node(text: str) -> bool:
    value = normalize_text(text)
    patterns = [
        r"^\d{1,2}/\d{1,2}\s+\d{1,2}:\d{2}$",
        r"^(昨天|今天|前天)\s*\d{1,2}:\d{2}$",
        r"^星期[一二三四五六日天]\s*\d{1,2}:\d{2}$",
        r"^周[一二三四五六日天]\s*\d{1,2}:\d{2}$",
        r"^\d{4}[/-]\d{1,2}[/-]\d{1,2}\s+\d{1,2}:\d{2}$",
    ]
    return any(re.match(pattern, value) for pattern in patterns)


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip())


def should_filter_text(item: OCRItem, image_width: int, image_height: int) -> bool:
    text = normalize_text(item.text)
    compact = re.sub(r"\s+", "", text).lower()

    if is_time_node(text):
        return False

    if item.y1 < image_height * 0.1:
        if re.fullmatch(r"\d{1,2}:\d{2}", compact):
            return True
        if compact in {"4g", "5g", "wifi", "wi-fi", "返回", "群聊的聊天记录", "...", "…"}:
            return True
        if re.search(r"(电量|中国移动|中国联通|中国电信|群聊的聊天记录)", compact):
            return True

    if item.y2 > image_height * 0.965 and len(compact) <= 8:
        return True

    if compact in {"<", "〈", "‹", "返回", "...", "…", "···"}:
        return True

    if item.width < image_width * 0.025 and len(compact) <= 2:
        return True

    return False


def analyze_layout(items: list[OCRItem], image_name: str, image_size: tuple[int, int], config: dict[str, Any]) -> list[dict[str, Any]]:
    image_width, image_height = image_size
    sorted_items = sorted(items, key=lambda item: (item.y1, item.x1))
    heights = [item.height for item in sorted_items if item.height > 0]
    median_height = median(heights) if heights else 18
    current_sender = str(config.get("default_sender", "UNKNOWN"))
    records: list[dict[str, Any]] = []
    message_lines: list[OCRItem] = []
    message_side = "left"
    filtered_items: list[OCRItem] = []

    def flush_message() -> None:
        nonlocal message_lines, message_side
        if not message_lines:
            return
        text = "\n".join(line.text.strip() for line in message_lines if line.text.strip())
        if text:
            records.append(
                {
                    "type": "message",
                    "sender": current_sender,
                    "side": message_side,
                    "text": text,
                    "source_image": image_name,
                    "bbox": union_bbox([line.bbox for line in message_lines]),
                    "bbox_space": "original_image",
                }
            )
        message_lines = []
        message_side = "left"

    for item in sorted_items:
        if not should_filter_text(item, image_width, image_height):
            filtered_items.append(item)

    for index, item in enumerate(filtered_items):
        text = normalize_text(item.text)
        if not text:
            continue

        if is_time_node(text):
            flush_message()
            records.append({"type": "time", "time": text, "source_image": image_name})
            continue

        next_item = filtered_items[index + 1] if index + 1 < len(filtered_items) else None
        if looks_like_sender(item, next_item, image_width, median_height):
            flush_message()
            current_sender = text
            continue

        side = "right" if item.center_x > image_width * 0.57 else "left"
        if message_lines:
            prev = message_lines[-1]
            y_gap = item.y1 - prev.y2
            side_changed = side != message_side
            separated = y_gap > max(median_height * 1.15, 24)
            if side_changed or separated:
                flush_message()

        if not message_lines:
            message_side = side
        message_lines.append(item)

    flush_message()
    return records


def looks_like_sender(item: OCRItem, next_item: OCRItem | None, image_width: int, median_height: float) -> bool:
    text = normalize_text(item.text)
    if not next_item or is_time_node(text):
        return False
    if len(text) > 24 or "\n" in text:
        return False
    if item.center_x > image_width * 0.55:
        return False
    vertical_gap = next_item.y1 - item.y2
    if vertical_gap < 0 or vertical_gap > max(median_height * 1.8, 34):
        return False
    if next_item.center_x < image_width * 0.18:
        return False
    if re.fullmatch(r"[\W_]+", text):
        return False
    return item.height <= median_height * 1.35


def union_bbox(boxes: list[list[float]]) -> list[float]:
    if not boxes:
        return [0, 0, 0, 0]
    return [
        round(min(box[0] for box in boxes), 1),
        round(min(box[1] for box in boxes), 1),
        round(max(box[2] for box in boxes), 1),
        round(max(box[3] for box in boxes), 1),
    ]


def deduplicate_records(records: list[dict[str, Any]], enable_dedup: bool) -> list[dict[str, Any]]:
    if not enable_dedup:
        return records

    seen: set[tuple[str, str, str]] = set()
    result: list[dict[str, Any]] = []
    last_time = ""
    for record in records:
        if record.get("type") == "time":
            last_time = str(record.get("time", ""))
            result.append(record)
            continue

        if record.get("type") == "message":
            key = (str(record.get("sender", "")), str(record.get("text", "")), last_time)
            if key in seen:
                continue
            seen.add(key)
        result.append(record)
    return result


def write_data_json(records: list[dict[str, Any]]) -> Path:
    path = OUTPUT_DIR / "data.json"
    path.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def write_chat_txt(records: list[dict[str, Any]]) -> Path:
    path = OUTPUT_DIR / "chat.txt"
    lines: list[str] = []
    last_image = None
    for record in records:
        source_image = record.get("source_image", "")
        if source_image != last_image:
            if lines:
                lines.append("")
            lines.append(f"===== {source_image} =====")
            lines.append("")
            last_image = source_image

        if record.get("type") == "time":
            lines.append(f"[{record.get('time', '')}]")
            lines.append("")
        elif record.get("type") == "message":
            lines.append(f"{record.get('sender', '')}：")
            lines.append(str(record.get("text", "")))
            lines.append("")

    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return path


def get_template_env() -> Any:
    from jinja2 import Environment, FileSystemLoader, select_autoescape

    return Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=select_autoescape(enabled_extensions=("html", "xml"), default_for_string=True),
    )


def render_chat_html(records: list[dict[str, Any]]) -> Path:
    path = OUTPUT_DIR / "chat.html"
    template = get_template_env().get_template("chat_template.html")
    path.write_text(template.render(records=records), encoding="utf-8")
    return path


def render_review_html(records: list[dict[str, Any]], screenshot_files: list[Path]) -> Path:
    path = OUTPUT_DIR / "review.html"
    template = get_template_env().get_template("review_template.html")
    images = [{"name": p.name, "path": f"../screenshots/{p.name}"} for p in screenshot_files]
    path.write_text(template.render(records=records, images=images), encoding="utf-8")
    return path


def get_image_size(image_path: Path) -> tuple[int, int]:
    from PIL import Image

    with Image.open(image_path) as img:
        return img.size


def main() -> int:
    ensure_directories()
    config = load_config()
    process_logger, error_logger = setup_logging()
    screenshot_files = get_screenshot_files()

    if not screenshot_files:
        message = f"screenshots 文件夹为空：{SCREENSHOTS_DIR}\n请把 QQ 聊天截图放进去后重新运行 python main.py。"
        print(message)
        process_logger.info(message)
        return 0

    try:
        ocr_engine = init_ocr_engine(config)
    except Exception as exc:
        print(f"OCR 初始化失败：{exc}")
        error_logger.error("OCR 初始化失败：%s\n%s", exc, traceback.format_exc())
        return 2

    all_records: list[dict[str, Any]] = []
    total_raw = 0
    total_filtered = 0
    success_count = 0

    for image_path in screenshot_files:
        try:
            process_logger.info("开始处理 %s", image_path.name)
            processed_path, transform = preprocess_image(image_path, config)
            raw_result = run_ocr(ocr_engine, processed_path)
            normalized = normalize_ocr_result(
                raw_result,
                transform,
                float(config.get("confidence_threshold", 0.5)),
            )
            image_size = get_image_size(image_path)
            kept = [item for item in normalized if not should_filter_text(item, image_size[0], image_size[1])]
            records = analyze_layout(normalized, image_path.name, image_size, config)
            all_records.extend(records)
            total_raw += len(normalized)
            total_filtered += max(0, len(normalized) - len(kept))
            success_count += 1
            process_logger.info(
                "完成 %s: raw=%s filtered=%s records=%s processed=%s",
                image_path.name,
                len(normalized),
                len(normalized) - len(kept),
                len(records),
                processed_path,
            )
        except Exception as exc:
            error_logger.error("处理失败 %s: %s\n%s", image_path.name, exc, traceback.format_exc())
            process_logger.info("失败 %s: %s", image_path.name, exc)

    before_dedup = len(all_records)
    all_records = deduplicate_records(all_records, bool(config.get("enable_dedup", True)))
    removed = before_dedup - len(all_records)

    output_paths = [
        write_data_json(all_records),
        write_chat_txt(all_records),
        render_chat_html(all_records),
        render_review_html(all_records, screenshot_files),
    ]
    for output_path in output_paths:
        process_logger.info("输出文件：%s", output_path)

    print("处理完成")
    print(f"截图总数：{len(screenshot_files)}，成功：{success_count}，失败：{len(screenshot_files) - success_count}")
    print(f"OCR 文本框：{total_raw}，过滤：{total_filtered}，去重：{removed}，最终记录：{len(all_records)}")
    print(f"输出目录：{OUTPUT_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
