from __future__ import annotations

import io
import logging
import sys
from pathlib import Path

import qrcode
from PyQt6.QtCore import QSize, Qt, QTimer, QUrl
from PyQt6.QtGui import QDesktopServices, QIcon, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from phone_keyboard.cli import build_url, find_lan_ip
from phone_keyboard.config import (
    VERSION,
    Settings,
    ensure_data_dir,
    load_or_create_token,
    package_dir,
)

from .icons import svg_icon, svg_pixmap
from .server_controller import ServerController
from .settings_store import load_config, save_config, set_startup
from .theme import build_qss, colors_for, is_dark_mode
from .widgets import Card, NavButton, PageHeader, StatusDot, ToggleSwitch


def resource_path(relative: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return base / relative


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("PKB")
        self.resize(1080, 700)
        self.setMinimumSize(980, 640)
        icon_path = resource_path("assets/icon.png")
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))

        self.config = load_config()
        self.dark = is_dark_mode()
        self.controller = ServerController()
        self.token = ""
        self.template = ""
        self.settings: Settings | None = None
        self.phone_url = ""
        self.start_error: str | None = None
        self.last_log_size = -1

        self._build_ui()
        self._apply_theme()
        self._start_server()

        self.log_timer = QTimer(self)
        self.log_timer.timeout.connect(self._refresh_logs)
        self.log_timer.start(1200)

        self.theme_timer = QTimer(self)
        self.theme_timer.timeout.connect(self._check_theme)
        self.theme_timer.start(2000)

    def _build_ui(self) -> None:
        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        root_layout.addWidget(self._build_sidebar())

        content = QFrame()
        content.setObjectName("content")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(28, 24, 28, 24)
        content_layout.setSpacing(18)

        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_connection_page())
        self.stack.addWidget(self._build_settings_page())
        self.stack.addWidget(self._build_logs_page())
        self.stack.addWidget(self._build_about_page())
        content_layout.addWidget(self.stack, 1)
        root_layout.addWidget(content, 1)

        self.nav_buttons[0].setChecked(True)

    def _build_sidebar(self) -> QFrame:
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(220)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(18, 20, 14, 18)
        layout.setSpacing(6)

        logo_row = QHBoxLayout()
        logo_row.setSpacing(10)
        logo = QLabel()
        icon_path = resource_path("assets/icon.png")
        if icon_path.exists():
            pixmap = QPixmap(str(icon_path)).scaled(
                38, 38,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            logo.setPixmap(pixmap)
        else:
            logo.setPixmap(svg_pixmap("link", "#2F6BFF", 38))
        logo.setFixedSize(38, 38)
        logo_row.addWidget(logo)

        brand_col = QVBoxLayout()
        brand_col.setSpacing(0)
        brand = QLabel("PKB")
        brand.setObjectName("brand")
        brand_sub = QLabel("手机键盘桥")
        brand_sub.setObjectName("brandSub")
        brand_col.addWidget(brand)
        brand_col.addWidget(brand_sub)
        logo_row.addLayout(brand_col, 1)
        layout.addLayout(logo_row)
        layout.addSpacing(18)

        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)
        self.nav_buttons: list[NavButton] = []
        nav_items = [
            ("link", "连接"),
            ("settings", "设置"),
            ("logs", "日志"),
            ("about", "关于"),
        ]
        for index, (icon_name, text) in enumerate(nav_items):
            button = NavButton(icon_name, text)
            self.nav_group.addButton(button, index)
            self.nav_buttons.append(button)
            layout.addWidget(button)

        self.nav_group.idClicked.connect(self._select_page)
        layout.addStretch(1)

        version = QLabel(f"v{VERSION}")
        version.setObjectName("muted")
        layout.addWidget(version)
        return sidebar

    def _build_connection_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)

        layout.addWidget(PageHeader("连接", "手机和电脑在同一个局域网即可使用。"))

        self.status_card = Card()
        status_layout = QVBoxLayout(self.status_card)
        status_layout.setContentsMargins(22, 20, 22, 20)
        status_layout.setSpacing(10)

        top_row = QHBoxLayout()
        top_row.setSpacing(10)
        self.status_dot = StatusDot()
        self.status_title = QLabel("服务启动中…")
        self.status_title.setObjectName("statusTitle")
        self.status_port = QLabel(f"端口 {self.config['port']}")
        self.status_port.setObjectName("pill")
        self.toggle_btn = QPushButton("停止服务")
        self.toggle_btn.setObjectName("primary")
        self.toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.toggle_btn.setFixedWidth(112)
        self.toggle_btn.clicked.connect(self._toggle_server)

        top_row.addWidget(self.status_dot)
        top_row.addWidget(self.status_title)
        top_row.addWidget(self.status_port)
        top_row.addStretch(1)
        top_row.addWidget(self.toggle_btn)
        status_layout.addLayout(top_row)

        self.status_hint = QLabel("正在启动本机服务…")
        self.status_hint.setObjectName("statusHint")
        self.status_hint.setWordWrap(True)
        status_layout.addWidget(self.status_hint)
        layout.addWidget(self.status_card)

        self.qr_card = Card()
        qr_layout = QHBoxLayout(self.qr_card)
        qr_layout.setContentsMargins(22, 20, 22, 20)
        qr_layout.setSpacing(24)

        self.qr_label = QLabel()
        self.qr_label.setFixedSize(200, 200)
        self.qr_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.qr_label.setStyleSheet("background: #FFFFFF; border-radius: 16px;")
        qr_layout.addWidget(self.qr_label, 0, Qt.AlignmentFlag.AlignTop)

        qr_right = QVBoxLayout()
        qr_right.setSpacing(10)
        qr_title = QLabel("手机扫码连接")
        qr_title.setObjectName("h2")
        qr_right.addWidget(qr_title)

        self.url_label = QLabel("正在生成手机地址…")
        self.url_label.setObjectName("muted")
        self.url_label.setWordWrap(True)
        self.url_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        qr_right.addWidget(self.url_label)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        copy_btn = QPushButton("复制地址")
        copy_btn.setObjectName("secondary")
        copy_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        copy_btn.setIcon(svg_icon("copy", "#6B7280", 16))
        copy_btn.clicked.connect(self._copy_phone_url)
        open_btn = QPushButton("打开手机页面")
        open_btn.setObjectName("secondary")
        open_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        open_btn.setIcon(svg_icon("open", "#6B7280", 16))
        open_btn.clicked.connect(self._open_phone_page)
        btn_row.addWidget(copy_btn)
        btn_row.addWidget(open_btn)
        btn_row.addStretch(1)
        qr_right.addLayout(btn_row)

        hint = QLabel("先在电脑上点一下目标输入框，再在手机上打字或选图。")
        hint.setObjectName("muted")
        hint.setWordWrap(True)
        qr_right.addWidget(hint)
        qr_right.addStretch(1)
        qr_layout.addLayout(qr_right, 1)
        layout.addWidget(self.qr_card)

        self.info_card = Card()
        info_layout = QGridLayout(self.info_card)
        info_layout.setContentsMargins(22, 18, 22, 18)
        info_layout.setHorizontalSpacing(16)
        info_layout.setVerticalSpacing(10)

        self.ip_value = self._info_value()
        self.port_value = self._info_value()
        self.data_value = self._info_value()
        info_layout.addWidget(self._muted_label("本机地址"), 0, 0)
        info_layout.addWidget(self.ip_value, 0, 1)
        info_layout.addWidget(self._muted_label("端口"), 1, 0)
        info_layout.addWidget(self.port_value, 1, 1)
        info_layout.addWidget(self._muted_label("数据目录"), 2, 0)
        info_layout.addWidget(self.data_value, 2, 1)
        info_layout.setColumnStretch(1, 1)
        layout.addWidget(self.info_card)
        layout.addStretch(1)
        return page

    def _build_settings_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)

        layout.addWidget(PageHeader("设置", "修改端口、数据目录和启动行为。保存后会自动重启服务。"))

        service_card = Card()
        service_layout = QFormLayout(service_card)
        service_layout.setContentsMargins(22, 20, 22, 20)
        service_layout.setHorizontalSpacing(18)
        service_layout.setVerticalSpacing(14)
        service_layout.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)

        self.port_spin = QSpinBox()
        self.port_spin.setRange(1024, 65535)
        self.port_spin.setValue(int(self.config["port"]))
        self.port_spin.setFixedWidth(160)
        service_layout.addRow("监听端口", self.port_spin)

        dir_row = QWidget()
        dir_layout = QHBoxLayout(dir_row)
        dir_layout.setContentsMargins(0, 0, 0, 0)
        dir_layout.setSpacing(8)
        self.data_dir_edit = QLineEdit(str(self.config["data_dir"]))
        browse_btn = QPushButton("浏览…")
        browse_btn.setObjectName("secondary")
        browse_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        browse_btn.clicked.connect(self._browse_data_dir)
        dir_layout.addWidget(self.data_dir_edit, 1)
        dir_layout.addWidget(browse_btn)
        service_layout.addRow("数据目录", dir_row)
        layout.addWidget(service_card)

        security_card = Card()
        security_layout = QVBoxLayout(security_card)
        security_layout.setContentsMargins(22, 20, 22, 20)
        security_layout.setSpacing(12)
        security_title = QLabel("连接安全")
        security_title.setObjectName("h2")
        security_layout.addWidget(security_title)

        token_row = QHBoxLayout()
        token_row.setSpacing(10)
        token_label = QLabel("连接令牌")
        self.token_state = QLabel("已生成")
        self.token_state.setObjectName("pill")
        reset_btn = QPushButton("重置连接令牌")
        reset_btn.setObjectName("danger")
        reset_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        reset_btn.setIcon(svg_icon("trash", "#DC2626", 16))
        reset_btn.clicked.connect(self._reset_token)
        token_row.addWidget(token_label)
        token_row.addWidget(self.token_state)
        token_row.addStretch(1)
        token_row.addWidget(reset_btn)
        security_layout.addLayout(token_row)

        token_hint = QLabel("重置后旧二维码会立即失效，手机需要重新扫码。")
        token_hint.setObjectName("muted")
        token_hint.setWordWrap(True)
        security_layout.addWidget(token_hint)
        layout.addWidget(security_card)

        startup_card = Card()
        startup_layout = QVBoxLayout(startup_card)
        startup_layout.setContentsMargins(22, 20, 22, 20)
        startup_layout.setSpacing(10)
        startup_title = QLabel("启动设置")
        startup_title.setObjectName("h2")
        startup_row = QHBoxLayout()
        startup_row.setSpacing(10)
        startup_label = QLabel("开机自启")
        startup_label.setObjectName("body")
        self.startup_switch = ToggleSwitch()
        self.startup_switch.setChecked(bool(self.config.get("startup", False)))
        startup_row.addWidget(startup_label)
        startup_row.addStretch(1)
        startup_row.addWidget(self.startup_switch)
        startup_hint = QLabel("只会在 Windows 启动文件夹里创建一个 PKB.cmd，不会修改注册表。")
        startup_hint.setObjectName("muted")
        startup_hint.setWordWrap(True)
        startup_layout.addWidget(startup_title)
        startup_layout.addLayout(startup_row)
        startup_layout.addWidget(startup_hint)
        layout.addWidget(startup_card)

        save_row = QHBoxLayout()
        self.save_btn = QPushButton("保存并重启服务")
        self.save_btn.setObjectName("primary")
        self.save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.save_btn.clicked.connect(self._save_settings)
        self.settings_status = QLabel("")
        self.settings_status.setObjectName("muted")
        save_row.addWidget(self.save_btn)
        save_row.addWidget(self.settings_status, 1)
        layout.addLayout(save_row)
        layout.addStretch(1)
        return page

    def _build_logs_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)

        layout.addWidget(PageHeader("日志", "查看本机服务的运行记录，方便排查连接问题。"))

        toolbar = QHBoxLayout()
        toolbar.setSpacing(10)
        refresh_btn = QPushButton("刷新")
        refresh_btn.setObjectName("secondary")
        refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        refresh_btn.setIcon(svg_icon("refresh", "#6B7280", 16))
        refresh_btn.clicked.connect(lambda: self._refresh_logs(force=True))
        clear_btn = QPushButton("清空显示")
        clear_btn.setObjectName("secondary")
        clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        clear_btn.setIcon(svg_icon("trash", "#6B7280", 16))
        clear_btn.clicked.connect(self.log_view_clear)
        open_btn = QPushButton("打开日志文件")
        open_btn.setObjectName("secondary")
        open_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        open_btn.setIcon(svg_icon("open", "#6B7280", 16))
        open_btn.clicked.connect(self._open_log_file)
        toolbar.addWidget(refresh_btn)
        toolbar.addWidget(clear_btn)
        toolbar.addWidget(open_btn)
        toolbar.addStretch(1)
        layout.addLayout(toolbar)

        self.log_view = QPlainTextEdit()
        self.log_view.setObjectName("logView")
        self.log_view.setReadOnly(True)
        self.log_view.setMinimumHeight(380)
        layout.addWidget(self.log_view, 1)
        return page

    def _build_about_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)

        layout.addWidget(PageHeader("关于", "PKB 是一个把手机当电脑键盘用的局域网工具。"))

        about_card = Card()
        about_layout = QVBoxLayout(about_card)
        about_layout.setContentsMargins(30, 26, 30, 26)
        about_layout.setSpacing(10)

        icon_label = QLabel()
        icon_path = resource_path("assets/icon.png")
        if icon_path.exists():
            icon_label.setPixmap(
                QPixmap(str(icon_path)).scaled(
                    72, 72,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
        about_layout.addWidget(icon_label)

        title = QLabel("PKB")
        title.setObjectName("h1")
        about_layout.addWidget(title)

        subtitle = QLabel("手机键盘桥 / Phone Keyboard Bridge")
        subtitle.setObjectName("muted")
        about_layout.addWidget(subtitle)

        desc = QLabel(
            "手机浏览器打开局域网页面，输入文字或选择图片，电脑当前窗口自动收到粘贴内容。"
            "不需要手机 App，不需要云服务，数据只走你自己的局域网。"
        )
        desc.setWordWrap(True)
        about_layout.addWidget(desc)

        self.version_label = QLabel(f"版本 {VERSION}")
        self.version_label.setObjectName("muted")
        about_layout.addWidget(self.version_label)

        self.github_link = QLabel()
        self.github_link.setOpenExternalLinks(True)
        self.github_link.setTextFormat(Qt.TextFormat.RichText)
        about_layout.addWidget(self.github_link)

        license_label = QLabel("开源许可证：MIT")
        license_label.setObjectName("muted")
        about_layout.addWidget(license_label)
        about_layout.addStretch(1)

        layout.addWidget(about_card)
        layout.addStretch(1)
        return page

    def _muted_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("muted")
        return label

    def _info_value(self) -> QLabel:
        label = QLabel("—")
        label.setObjectName("body")
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        label.setWordWrap(True)
        return label

    def _select_page(self, index: int) -> None:
        self.stack.setCurrentIndex(index)
        self._refresh_nav_icons()
        if index == 2:
            self._refresh_logs(force=True)

    def _refresh_nav_icons(self) -> None:
        colors = colors_for(self.dark)
        for button in self.nav_buttons:
            color = colors["primary"] if button.isChecked() else colors["muted"]
            button.set_icon_color(color)

    def _apply_theme(self) -> None:
        self.dark = is_dark_mode()
        colors = colors_for(self.dark)
        self.setStyleSheet(build_qss(self.dark))
        for card in self.findChildren(Card):
            card.set_dark(self.dark)
        self._refresh_nav_icons()
        if hasattr(self, "startup_switch"):
            self.startup_switch.set_dark(self.dark)
        if hasattr(self, "status_dot"):
            self.status_dot.set_color(colors["success"] if self.controller.is_running else colors["muted"])
        if hasattr(self, "github_link"):
            self.github_link.setText(
                f'<a style="color:{colors["primary"]}; text-decoration:none;" '
                'href="https://github.com/NanMingMeng/phone-keyboard-bridge">'
                "github.com/NanMingMeng/phone-keyboard-bridge</a>"
            )

    def _configure_logging(self, log_file: Path) -> None:
        root = logging.getLogger()
        for handler in root.handlers[:]:
            root.removeHandler(handler)
        log_file.parent.mkdir(parents=True, exist_ok=True)
        handler = logging.FileHandler(log_file, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        root.addHandler(handler)
        root.setLevel(logging.INFO)

    def _start_server(self) -> None:
        try:
            data_dir = ensure_data_dir(Path(self.config["data_dir"]))
            self.token = load_or_create_token(data_dir)
            template_file = package_dir() / "templates" / "index.html"
            self.template = template_file.read_text(encoding="utf-8")
            self.settings = Settings(
                host="0.0.0.0",
                port=int(self.config["port"]),
                data_dir=data_dir,
                token=self.token,
                image_dir=data_dir / "images",
                log_file=data_dir / "logs" / "phone-keyboard.log",
                template_file=template_file,
            )
            self._configure_logging(self.settings.log_file)
            ok, error = self.controller.start(self.settings, self.template)
            self.start_error = None if ok else error
            if ok:
                logging.getLogger("pkb.ui").info("Service started on port %s", self.config["port"])
            else:
                logging.getLogger("pkb.ui").error("Service start failed: %s", error)
        except Exception as error:
            self.start_error = str(error)
            logging.getLogger("pkb.ui").exception("Service start failed")
        self._update_connection_ui()
        self._refresh_logs(force=True)

    def _toggle_server(self) -> None:
        if self.controller.is_running:
            self.controller.stop()
            logging.getLogger("pkb.ui").info("Service stopped by user")
            self._update_connection_ui()
            self.settings_status.setText("服务已停止。")
        else:
            self._start_server()

    def _update_connection_ui(self) -> None:
        colors = colors_for(self.dark)
        running = self.controller.is_running
        if running:
            self.status_title.setText("服务运行中")
            self.status_dot.set_color(colors["success"])
            self.toggle_btn.setText("停止服务")
            self.status_hint.setText("手机和电脑在同一个局域网即可连接。")
        elif self.start_error:
            self.status_title.setText("启动失败")
            self.status_dot.set_color(colors["danger"])
            self.toggle_btn.setText("重试启动")
            self.status_hint.setText(f"启动失败：{self.start_error}")
        else:
            self.status_title.setText("服务已停止")
            self.status_dot.set_color(colors["muted"])
            self.toggle_btn.setText("启动服务")
            self.status_hint.setText("点击启动服务后，手机才能连接。")

        self.status_port.setText(f"端口 {self.config['port']}")
        self.ip_value.setText(find_lan_ip())
        self.port_value.setText(str(self.config["port"]))
        self.data_value.setText(str(self.config["data_dir"]))
        self._refresh_qr()

    def _refresh_qr(self) -> None:
        if not self.token:
            return
        url = build_url(find_lan_ip(), int(self.config["port"]), self.token)
        self.phone_url = url
        self.url_label.setText(url)
        try:
            image = qrcode.make(url)
            buffer = io.BytesIO()
            image.save(buffer, format="PNG")
            pixmap = QPixmap()
            pixmap.loadFromData(buffer.getvalue())
            self.qr_label.setPixmap(
                pixmap.scaled(
                    192, 192,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
        except Exception as error:
            self.url_label.setText(f"二维码生成失败：{error}")

    def _copy_phone_url(self) -> None:
        if self.phone_url:
            QApplication.clipboard().setText(self.phone_url)
            self.status_hint.setText("手机地址已复制到剪贴板。")

    def _open_phone_page(self) -> None:
        if self.phone_url:
            QDesktopServices.openUrl(QUrl(self.phone_url))

    def _browse_data_dir(self) -> None:
        directory = QFileDialog.getExistingDirectory(
            self, "选择数据目录", self.data_dir_edit.text()
        )
        if directory:
            self.data_dir_edit.setText(directory)

    def _reset_token(self) -> None:
        result = QMessageBox.question(
            self,
            "重置连接令牌",
            "重置后旧二维码会立即失效，手机需要重新扫码。继续吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if result != QMessageBox.StandardButton.Yes:
            return
        data_dir = Path(self.config["data_dir"])
        try:
            (data_dir / "token.txt").unlink()
        except FileNotFoundError:
            pass
        self.controller.stop()
        self._start_server()
        self.settings_status.setText("连接令牌已重置，请让手机重新扫码。")

    def _save_settings(self) -> None:
        port = int(self.port_spin.value())
        data_dir_text = self.data_dir_edit.text().strip()
        if not data_dir_text:
            self.settings_status.setText("数据目录不能为空。")
            return
        try:
            data_dir = ensure_data_dir(Path(data_dir_text))
        except Exception as error:
            self.settings_status.setText(f"数据目录无效：{error}")
            return

        self.config["port"] = port
        self.config["data_dir"] = str(data_dir)
        self.config["startup"] = bool(self.startup_switch.isChecked())
        try:
            save_config(self.config)
            set_startup(self.config["startup"])
        except Exception as error:
            self.settings_status.setText(f"保存设置失败：{error}")
            return

        self.settings_status.setText("正在重启服务…")
        self.controller.stop()
        self._start_server()
        if self.controller.is_running:
            self.settings_status.setText("已保存并重启服务。")
        else:
            self.settings_status.setText(f"已保存，但服务启动失败：{self.start_error}")

    def log_view_clear(self) -> None:
        self.log_view.clear()
        self.last_log_size = -1

    def _refresh_logs(self, force: bool = False) -> None:
        if self.settings is None:
            return
        log_file = self.settings.log_file
        if not log_file.exists():
            if force:
                self.log_view.setPlainText("暂无日志。")
            return
        try:
            size = log_file.stat().st_size
            if not force and size == self.last_log_size:
                return
            text = log_file.read_text(encoding="utf-8", errors="replace")
            self.last_log_size = size
            lines = text.splitlines()
            self.log_view.setPlainText("\n".join(lines[-400:]))
            scrollbar = self.log_view.verticalScrollBar()
            scrollbar.setValue(scrollbar.maximum())
        except OSError as error:
            if force:
                self.log_view.setPlainText(f"读取日志失败：{error}")

    def _open_log_file(self) -> None:
        if self.settings is None:
            return
        log_file = self.settings.log_file
        if log_file.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(log_file)))
        else:
            QMessageBox.information(self, "日志", "日志文件还没有生成。")

    def _check_theme(self) -> None:
        if is_dark_mode() != self.dark:
            self._apply_theme()

    def closeEvent(self, event) -> None:  # type: ignore[override]
        self.controller.stop()
        event.accept()
