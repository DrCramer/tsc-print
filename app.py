import os
import logging
import re
import threading
import uuid

from flask import Flask, jsonify, request, send_from_directory


app = Flask(__name__)

PRINTER_DEVICE = os.environ.get("PRINTER_DEVICE", "/dev/usb/lp0")
logger = app.logger
logger.setLevel(logging.INFO)

# This protects the physical printer only inside one process. If Gunicorn workers
# are increased above 1, replace this with an inter-process lock or print queue.
PRINT_LOCK = threading.Lock()


def normalize_tspl(tspl: str) -> bytes:
    """Normalize TSPL line endings and terminate every job with CRLF."""
    normalized = tspl.replace("\r\n", "\n").replace("\r", "\n")
    normalized = normalized.rstrip("\n") + "\n"
    return normalized.replace("\n", "\r\n").encode("utf-8")


@app.get("/")
def index():
    return send_from_directory(app.root_path, "index.html")


@app.post("/print")
def print_label():
    if not request.is_json:
        return jsonify({"ok": False, "error": "Request must be JSON"}), 400

    data = request.get_json(silent=True) or {}
    tspl = data.get("tspl")

    if not isinstance(tspl, str) or not tspl.strip():
        return jsonify({"ok": False, "error": "Field 'tspl' must be a non-empty string"}), 400

    job_id = uuid.uuid4().hex[:8]
    payload = normalize_tspl(tspl)
    label_count = len(re.findall(r"(?im)^\s*PRINT\s+1\s*$", tspl))
    logger.info(
        "[PRINT %s] PRINT JOB START labels=%s bytes=%d device=%s",
        job_id,
        label_count if label_count else "unknown",
        len(payload),
        PRINTER_DEVICE,
    )

    try:
        logger.info("[PRINT %s] Waiting for printer lock", job_id)
        with PRINT_LOCK:
            logger.info("[PRINT %s] Lock acquired", job_id)
            logger.info("[PRINT %s] Opening %s", job_id, PRINTER_DEVICE)
            fd = os.open(PRINTER_DEVICE, os.O_WRONLY)
            with os.fdopen(fd, "wb") as printer:
                logger.info("[PRINT %s] Writing %d bytes", job_id, len(payload))
                printer.write(payload)
                printer.flush()
                logger.info("[PRINT %s] Write complete", job_id)
            logger.info("[PRINT %s] Device closed", job_id)
    except FileNotFoundError:
        logger.exception("[PRINT %s] PRINT JOB ERROR", job_id)
        return jsonify({
            "ok": False,
            "error": f"Printer device not found: {PRINTER_DEVICE}",
        }), 503
    except PermissionError:
        logger.exception("[PRINT %s] PRINT JOB ERROR", job_id)
        return jsonify({
            "ok": False,
            "error": f"No permission to write to printer device: {PRINTER_DEVICE}",
        }), 503
    except OSError as exc:
        logger.exception("[PRINT %s] PRINT JOB ERROR", job_id)
        return jsonify({
            "ok": False,
            "error": f"Printer write failed: {exc}",
        }), 503

    logger.info("[PRINT %s] PRINT JOB COMPLETE", job_id)
    return jsonify({"ok": True, "job_id": job_id, "bytes": len(payload), "message": "TSPL sent to printer"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=9090)
