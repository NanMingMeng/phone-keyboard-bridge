from __future__ import annotations

import argparse
import logging
import os
import socket
import subprocess
import sys
from pathlib import Path

from .config import (
    APP_NAME,
    VERSION,
    Settings,
    default_data_dir,
    ensure_data_dir,
    load_or_create_token,
    package_dir,
)
from .server import run_server


def find_lan_ip() -> str:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        return sock.getsockname()[0]
    except OSError:
        try:
            return socket.gethostbyname(socket.gethostname())
        except OSError:
            return "127.0.0.1"
    finally:
        sock.close()


def build_url(host: str, port: int, token: str) -> str:
    return f"http://{host}:{port}/?t={token}"


def generate_qr(url: str, data_dir: Path) -> Path:
    try:
        import qrcode
    except ImportError as error:
        raise RuntimeError(
            "qrcode is not installed. Run: python -m pip install -r requirements.txt"
        ) from error
    path = data_dir / "phone-keyboard-qr.png"
    qrcode.make(url).save(path)
    return path


def open_path(path: Path) -> None:
    if os.name == "nt":
        os.startfile(str(path))  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="phone-keyboard",
        description="Type on your phone, paste into the active window on your Windows PC.",
    )
    parser.add_argument("--host", default="0.0.0.0", help="Bind address (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=3002, help="HTTP port (default: 3002)")
    parser.add_argument("--data-dir", type=Path, default=None, help="Where token, images and logs are stored")
    parser.add_argument("--qr", action="store_true", help="Generate a QR code for the phone URL")
    parser.add_argument("--open-qr", action="store_true", help="Generate and open the QR code")
    parser.add_argument("--version", action="version", version=f"%(prog)s {VERSION}")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    data_dir = ensure_data_dir(args.data_dir or default_data_dir())
    token = load_or_create_token(data_dir)
    template_file = package_dir() / "templates" / "index.html"
    if not template_file.exists():
        print(f"Template not found: {template_file}", file=sys.stderr)
        return 1
    template = template_file.read_text(encoding="utf-8")

    settings = Settings(
        host=args.host,
        port=args.port,
        data_dir=data_dir,
        token=token,
        image_dir=data_dir / "images",
        log_file=data_dir / "logs" / "phone-keyboard.log",
        template_file=template_file,
    )
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[
            logging.FileHandler(settings.log_file, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )

    lan_ip = find_lan_ip()
    local_url = build_url("127.0.0.1", settings.port, token)
    phone_url = build_url(lan_ip, settings.port, token)

    print(f"{APP_NAME} v{VERSION}")
    print(f"Local:  {local_url}")
    print(f"Phone:  {phone_url}")
    print(f"Data:   {data_dir}")
    print("Keep this window open while using the phone.")
    print("Press Ctrl+C to stop.")
    print()

    if args.qr or args.open_qr:
        try:
            qr_path = generate_qr(phone_url, data_dir)
            print(f"QR:     {qr_path}")
            if args.open_qr:
                open_path(qr_path)
        except Exception as error:
            print(f"QR generation failed: {error}", file=sys.stderr)

    try:
        run_server(settings, template)
    except KeyboardInterrupt:
        print("\nStopped.")
        return 0
    except OSError as error:
        print(f"Could not start the server: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
