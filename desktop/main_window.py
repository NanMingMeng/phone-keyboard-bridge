from __future__ import annotations

import datetime
import io
import logging
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import qrcode
from PyQt6.QtCore import QSize, Qt, QTimer, QUrl
from PyQt6.QtGui import QAction, QDesktopServices, QIcon, QIntValidator, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QDialog,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from phone_keyboard.clipboard import copy_files_to_clipboard, copy_image_to_clipboard, copy_text
from phone_keyboard.cli import build_url, find_lan_ip
from phone_keyboard.config import (
    VERSION,
    Settings,
    ensure_data_dir,
    load_or_create_token,
    package_dir,
)

from .device_dialog import DeviceApprovalDialog
from .diagnostics import run_checks
from .icons import svg_icon, svg_pixmap
from .server_controller import ServerController
from .settings_store import load_config, save_config, set_startup
from .theme import build_qss, colors_for, is_dark_mode
from .updater import UpdateCheckWorker, UpdateDownloadWorker, UpdateInfo, launch_update_installer
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
        self.last_lan_ip = ""
        self.start_error: str | None = None
        self.last_log_size = -1
        self._really_quit = False
        self._pending_dialog_open = False
        self._shown_pending: set[str] = set()
        self._records_signature: tuple[str, ...] | None = None
        self.tray: QSystemTrayIcon | None = None
        self._update_check_worker: UpdateCheckWorker | None = None
        self._update_download_worker: UpdateDownloadWorker | None = None

        self._build_ui()
        self._apply_theme()
        self._start_server()
        self._setup_tray()
        try:
            if self.config.get("startup", True):
                set_startup(True)
        except Exception:
            logging.getLogger("pkb.ui").exception("Failed to ensure startup entry")

        self.log_timer = QTimer(self)
        self.log_timer.timeout.connect(self._refresh_logs)
        self.log_timer.start(1200)

        self.device_timer = QTimer(self)
        self.device_timer.timeout.connect(self._refresh_devices)
        self.device_timer.start(1000)

        self.network_timer = QTimer(self)
        self.network_timer.timeout.connect(self._refresh_network_info)
        self.network_timer.start(3000)

        self.pending_timer = QTimer(self)
        self.pending_timer.timeout.connect(self._check_pending_requests)
        self.pending_timer.start(1000)

        self.record_timer = QTimer(self)
        self.record_timer.timeout.connect(self._refresh_records)
        self.record_timer.start(2000)

        self.theme_timer = QTimer(self)
        self.theme_timer.timeout.connect(self._check_theme)
        self.theme_timer.start(2000)

        QTimer.singleShot(3000, self._auto_check_update)

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
        self.stack.addWidget(self._build_records_page())
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
            ("history", "记录"),
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
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setObjectName("pageScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 8, 0)
        layout.setSpacing(16)
        scroll.setWidget(content)
        page_layout.addWidget(scroll)

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

        check_row = QHBoxLayout()
        check_row.setSpacing(10)
        self.self_check_btn = QPushButton("检查连接")
        self.self_check_btn.setObjectName("secondary")
        self.self_check_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.self_check_btn.setIcon(svg_icon("check", "#6B7280", 16))
        self.self_check_btn.clicked.connect(self._run_self_check)
        self.open_firewall_btn = QPushButton("打开防火墙设置")
        self.open_firewall_btn.setObjectName("secondary")
        self.open_firewall_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.open_firewall_btn.clicked.connect(self._open_firewall_settings)
        self.open_firewall_btn.setVisible(False)
        check_row.addWidget(self.self_check_btn)
        check_row.addWidget(self.open_firewall_btn)
        check_row.addStretch(1)
        status_layout.addLayout(check_row)

        self.self_check_result = QLabel("")
        self.self_check_result.setObjectName("muted")
        self.self_check_result.setWordWrap(True)
        self.self_check_result.setVisible(False)
        status_layout.addWidget(self.self_check_result)
        layout.addWidget(self.status_card)

        self.devices_card = Card()
        devices_layout = QVBoxLayout(self.devices_card)
        devices_layout.setContentsMargins(22, 18, 22, 18)
        devices_layout.setSpacing(10)

        devices_header = QHBoxLayout()
        devices_header.setSpacing(10)
        devices_title = QLabel("连接设备")
        devices_title.setObjectName("h2")
        self.devices_count = QLabel("0 台在线")
        self.devices_count.setObjectName("pill")
        copy_diag_btn = QPushButton("复制诊断信息")
        copy_diag_btn.setObjectName("secondary")
        copy_diag_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        copy_diag_btn.setIcon(svg_icon("copy", "#6B7280", 16))
        copy_diag_btn.clicked.connect(self._copy_diagnostics)
        devices_header.addWidget(devices_title)
        devices_header.addWidget(self.devices_count)
        devices_header.addStretch(1)
        devices_header.addWidget(copy_diag_btn)
        devices_layout.addLayout(devices_header)

        self.devices_empty = QLabel("暂无设备连接。手机扫码打开页面后，这里会显示设备信息。")
        self.devices_empty.setObjectName("muted")
        self.devices_empty.setWordWrap(True)
        devices_layout.addWidget(self.devices_empty)

        self.device_rows = QWidget()
        self.device_rows_layout = QVBoxLayout(self.device_rows)
        self.device_rows_layout.setContentsMargins(0, 0, 0, 0)
        self.device_rows_layout.setSpacing(0)
        devices_layout.addWidget(self.device_rows)
        self.device_rows.setVisible(False)
        layout.addWidget(self.devices_card)

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

    def _build_records_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)

        layout.addWidget(PageHeader("记录", "查看最近发送的文字和图片。最多保留 50 条。"))

        toolbar = QHBoxLayout()
        toolbar.setSpacing(10)
        refresh_btn = QPushButton("刷新")
        refresh_btn.setObjectName("secondary")
        refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        refresh_btn.setIcon(svg_icon("refresh", "#6B7280", 16))
        refresh_btn.clicked.connect(lambda: self._refresh_records(force=True))
        clear_btn = QPushButton("清空全部记录")
        clear_btn.setObjectName("danger")
        clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        clear_btn.setIcon(svg_icon("trash", "#DC2626", 16))
        clear_btn.clicked.connect(self._clear_records)
        self.records_summary = QLabel("0 条记录")
        self.records_summary.setObjectName("muted")
        toolbar.addWidget(refresh_btn)
        toolbar.addWidget(clear_btn)
        toolbar.addWidget(self.records_summary)
        toolbar.addStretch(1)
        layout.addLayout(toolbar)

        self.records_empty = QLabel("还没有发送记录。手机发送文字或图片后会出现在这里。")
        self.records_empty.setObjectName("muted")
        self.records_empty.setWordWrap(True)
        layout.addWidget(self.records_empty)

        scroll = QScrollArea()
        scroll.setObjectName("pageScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.records_content = QWidget()
        self.records_layout = QVBoxLayout(self.records_content)
        self.records_layout.setContentsMargins(0, 0, 8, 0)
        self.records_layout.setSpacing(10)
        scroll.setWidget(self.records_content)
        self.records_scroll = scroll
        layout.addWidget(scroll, 1)
        return page

    def _build_settings_page(self) -> QWidget:
        page = QWidget()
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setObjectName("pageScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 8, 0)
        layout.setSpacing(16)
        scroll.setWidget(content)
        page_layout.addWidget(scroll)

        layout.addWidget(PageHeader("设置", "修改端口、数据目录和启动行为。保存后会自动重启服务。"))

        service_card = Card()
        service_layout = QFormLayout(service_card)
        service_layout.setContentsMargins(22, 20, 22, 20)
        service_layout.setHorizontalSpacing(18)
        service_layout.setVerticalSpacing(14)
        service_layout.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)

        self.port_edit = QLineEdit(str(self.config["port"]))
        self.port_edit.setValidator(QIntValidator(1024, 65535, self))
        self.port_edit.setFixedWidth(160)
        self.port_edit.setPlaceholderText("1024–65535")
        service_layout.addRow("监听端口", self.port_edit)

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

        devices_card = Card()
        devices_layout = QVBoxLayout(devices_card)
        devices_layout.setContentsMargins(22, 20, 22, 20)
        devices_layout.setSpacing(10)
        devices_title = QLabel("已授权设备")
        devices_title.setObjectName("h2")
        devices_layout.addWidget(devices_title)
        devices_hint = QLabel("这里可以给长期使用的手机改名，或者撤销授权。")
        devices_hint.setObjectName("muted")
        devices_hint.setWordWrap(True)
        devices_layout.addWidget(devices_hint)
        self.approved_empty = QLabel("还没有已授权设备。手机首次连接并允许后会出现在这里。")
        self.approved_empty.setObjectName("muted")
        self.approved_empty.setWordWrap(True)
        devices_layout.addWidget(self.approved_empty)
        self.approved_rows_layout = QVBoxLayout()
        self.approved_rows_layout.setContentsMargins(0, 0, 0, 0)
        self.approved_rows_layout.setSpacing(0)
        devices_layout.addLayout(self.approved_rows_layout)
        layout.addWidget(devices_card)

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

        update_card = Card()
        update_layout = QVBoxLayout(update_card)
        update_layout.setContentsMargins(22, 20, 22, 20)
        update_layout.setSpacing(10)
        update_title = QLabel("软件更新")
        update_title.setObjectName("h2")
        update_layout.addWidget(update_title)
        self.update_status = QLabel(f"当前版本 v{VERSION}")
        self.update_status.setObjectName("muted")
        self.update_status.setWordWrap(True)
        update_layout.addWidget(self.update_status)
        update_row = QHBoxLayout()
        update_row.setSpacing(10)
        self.update_switch = ToggleSwitch()
        self.update_switch.setChecked(bool(self.config.get("auto_update_check", True)))
        auto_update_label = QLabel("启动时自动检查更新")
        auto_update_label.setObjectName("body")
        self.check_update_btn = QPushButton("立即检查更新")
        self.check_update_btn.setObjectName("secondary")
        self.check_update_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.check_update_btn.clicked.connect(lambda: self._check_for_updates(silent=False))
        update_row.addWidget(auto_update_label)
        update_row.addWidget(self.update_switch)
        update_row.addStretch(1)
        update_row.addWidget(self.check_update_btn)
        update_layout.addLayout(update_row)
        layout.addWidget(update_card)

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
        if index == 1:
            self._refresh_records(force=True)
        elif index == 2:
            self._refresh_approved_devices()
        elif index == 3:
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
        if hasattr(self, "update_switch"):
            self.update_switch.set_dark(self.dark)
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
            self._refresh_tray_menu()
            self.settings_status.setText("服务已停止。")
        else:
            self._start_server()
            self._refresh_tray_menu()

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
        self.last_lan_ip = find_lan_ip()
        self.ip_value.setText(self.last_lan_ip)
        self.port_value.setText(str(self.config["port"]))
        self.data_value.setText(str(self.config["data_dir"]))
        self._refresh_qr()
        self._refresh_tray_menu()

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

    def _refresh_network_info(self) -> None:
        current_ip = find_lan_ip()
        if current_ip != self.last_lan_ip:
            self.last_lan_ip = current_ip
            self.ip_value.setText(current_ip)
            self._refresh_qr()

    def _open_phone_page(self) -> None:
        if self.phone_url:
            QDesktopServices.openUrl(QUrl(self.phone_url))

    @staticmethod
    def _format_ago(seconds: float) -> str:
        if seconds < 5:
            return "刚刚"
        if seconds < 60:
            return f"{int(seconds)} 秒前"
        if seconds < 3600:
            return f"{int(seconds // 60)} 分钟前"
        if seconds < 86400:
            return f"{int(seconds // 3600)} 小时前"
        return f"{int(seconds // 86400)} 天前"

    def _refresh_devices(self) -> None:
        connections = self.controller.connections()
        online = sum(1 for item in connections if item["online"])
        pending = sum(1 for item in connections if item["status"] == "pending")
        count_text = f"{online} 台在线"
        if pending:
            count_text += f" · {pending} 台待确认"
        self.devices_count.setText(count_text)
        has_devices = bool(connections)
        self.device_rows.setVisible(has_devices)
        self.devices_empty.setVisible(not has_devices)

        while self.device_rows_layout.count():
            child = self.device_rows_layout.takeAt(0)
            widget = child.widget()
            if widget is not None:
                widget.deleteLater()
        if not has_devices:
            self._refresh_tray_menu()
            return

        colors = colors_for(self.dark)
        for item in connections:
            row = QFrame()
            row.setObjectName("deviceRow")
            row_layout = QVBoxLayout(row)
            row_layout.setContentsMargins(0, 10, 0, 10)
            row_layout.setSpacing(2)

            online = bool(item["online"])
            status = str(item["status"])
            if status == "approved":
                state_text = "在线" if online else "离线"
                state_color = colors["success"] if online else colors["muted"]
            elif status == "pending":
                state_text = "等待确认"
                state_color = colors["primary"]
            else:
                state_text = "已拒绝"
                state_color = colors["danger"]
            display_name = str(item["alias"] or item["device"])
            device_label = QLabel(
                f'<span style="font-weight:600;">{display_name}</span>'
                f'&nbsp;&nbsp;<span style="color:{state_color}; font-weight:600;">'
                f'● {state_text}</span>'
            )
            device_label.setTextFormat(Qt.TextFormat.RichText)
            device_label.setObjectName("body")
            action = str(item["last_action"] or "已连接")
            detail_label = QLabel(
                f'{item["device"]} · {item["ip"]} · {item["request_count"]} 次操作 · '
                f'{self._format_ago(float(item["last_seen_ago"]))} · {action}'
            )
            detail_label.setObjectName("muted")
            detail_label.setWordWrap(True)
            row_layout.addWidget(device_label)
            row_layout.addWidget(detail_label)
            self.device_rows_layout.addWidget(row)
        self._refresh_tray_menu()

    def _copy_diagnostics(self) -> None:
        connections = self.controller.connections()
        lines = [
            f"PKB v{VERSION}",
            f"服务状态：{'运行中' if self.controller.is_running else '已停止'}",
            f"本机地址：{find_lan_ip()}",
            f"监听端口：{self.config['port']}",
            f"在线设备：{sum(1 for item in connections if item['online'])} 台",
        ]
        for item in connections:
            state = "在线" if item["online"] else "离线"
            lines.append(
                f"- {item['device']} | {item['ip']} | {state} | "
                f"{self._format_ago(float(item['last_seen_ago']))} | {item['last_action'] or '无操作'}"
            )
        QApplication.clipboard().setText("\n".join(lines))
        self.status_hint.setText("诊断信息已复制，可以直接粘贴给其他人排查。")

    @staticmethod
    def _clear_layout(layout: QVBoxLayout) -> None:
        while layout.count():
            child = layout.takeAt(0)
            widget = child.widget()
            if widget is not None:
                widget.deleteLater()

    def _refresh_approved_devices(self) -> None:
        if not hasattr(self, "approved_rows_layout"):
            return
        self._clear_layout(self.approved_rows_layout)
        devices = self.controller.approved_devices()
        self.approved_empty.setVisible(not devices)
        for item in devices:
            row = QFrame()
            row.setObjectName("deviceRow")
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 8, 0, 8)
            row_layout.setSpacing(10)
            text_col = QVBoxLayout()
            text_col.setSpacing(2)
            alias = str(item["alias"] or item["device"])
            alias_label = QLabel(alias)
            alias_label.setObjectName("body")
            last_seen = float(item.get("last_seen_ago", 0.0))
            detail = (
                f"{item['device']} · {item['ip'] or '尚无 IP'} · "
                f"{'从未连接' if last_seen <= 0 else self._format_ago(last_seen)}"
            )
            detail_label = QLabel(detail)
            detail_label.setObjectName("muted")
            text_col.addWidget(alias_label)
            text_col.addWidget(detail_label)
            rename_btn = QPushButton("改名")
            rename_btn.setObjectName("secondary")
            rename_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            rename_btn.clicked.connect(
                lambda _checked=False, device_id=str(item["device_id"]), old=alias: self._rename_approved_device(device_id, old)
            )
            revoke_btn = QPushButton("撤销授权")
            revoke_btn.setObjectName("danger")
            revoke_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            revoke_btn.clicked.connect(
                lambda _checked=False, device_id=str(item["device_id"]), name=alias: self._revoke_approved_device(device_id, name)
            )
            row_layout.addLayout(text_col, 1)
            row_layout.addWidget(rename_btn)
            row_layout.addWidget(revoke_btn)
            self.approved_rows_layout.addWidget(row)

    def _rename_approved_device(self, device_id: str, old_alias: str) -> None:
        alias, ok = QInputDialog.getText(self, "修改设备名称", "设备名称：", text=old_alias)
        if ok and alias.strip():
            self.controller.rename_device(device_id, alias.strip())
            self._refresh_approved_devices()
            self._refresh_devices()

    def _revoke_approved_device(self, device_id: str, alias: str) -> None:
        result = QMessageBox.question(
            self,
            "撤销设备授权",
            f"撤销“{alias}”的授权后，这台设备下次连接需要重新申请。继续吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if result != QMessageBox.StandardButton.Yes:
            return
        self.controller.revoke_device(device_id)
        self._refresh_approved_devices()
        self._refresh_devices()

    def _check_pending_requests(self) -> None:
        if not self.controller.is_running or self._pending_dialog_open:
            return
        pending = self.controller.pending_requests()
        if not pending:
            return
        for request in pending:
            device_id = str(request["device_id"])
            if device_id in self._shown_pending:
                continue
            self._shown_pending.add(device_id)
            self._pending_dialog_open = True
            try:
                dialog = DeviceApprovalDialog(request, self)
                accepted = dialog.exec() == QDialog.DialogCode.Accepted
                if accepted:
                    self.controller.approve_device(device_id, dialog.alias)
                    if self.tray is not None:
                        self.tray.showMessage("PKB", f"已允许 {dialog.alias} 连接", QSystemTrayIcon.MessageIcon.Information, 2500)
                else:
                    self.controller.deny_device(device_id)
            finally:
                self._pending_dialog_open = False
                self._shown_pending.discard(device_id)
                self._refresh_devices()
                self._refresh_approved_devices()
            break

    def _refresh_records(self, force: bool = False) -> None:
        if not hasattr(self, "records_layout"):
            return
        if not force and self.stack.currentIndex() != 1:
            return
        records = self.controller.records()
        signature = tuple(str(item.get("id", "")) for item in records)
        if not force and signature == self._records_signature:
            return
        self._records_signature = signature
        self._clear_layout(self.records_layout)
        self.records_summary.setText(f"{len(records)} 条记录")
        self.records_empty.setVisible(not records)
        self.records_scroll.setVisible(bool(records))
        for item in records:
            row = QFrame()
            row.setObjectName("recordRow")
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(14, 12, 14, 12)
            row_layout.setSpacing(12)

            if item.get("type") in ("image", "file"):
                thumb = QLabel()
                thumb.setFixedSize(92, 64)
                thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
                file_path = Path(str(item.get("image_path") or item.get("file_path") or ""))
                if item.get("type") == "image" and file_path.exists():
                    pixmap = QPixmap(str(file_path)).scaled(
                        92,
                        64,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                    thumb.setPixmap(pixmap)
                else:
                    thumb.setText("文件" if file_path.exists() else "文件已删除")
                    thumb.setObjectName("muted")
                row_layout.addWidget(thumb)
                title_text = "图片" if item.get("type") == "image" else "文件"
                preview_text = file_path.name if file_path.name else str(item.get("action", ""))
            else:
                title_text = "文字"
                text = str(item.get("text", "")).replace("\n", " ")
                preview_text = text[:120] + ("…" if len(text) > 120 else "")
                preview_label = QLabel(preview_text)
                preview_label.setObjectName("body")
                preview_label.setWordWrap(True)
                row_layout.addWidget(preview_label, 1)

            if item.get("type") in ("image", "file"):
                info_col = QVBoxLayout()
                info_col.setSpacing(2)
                title_label = QLabel(title_text)
                title_label.setObjectName("body")
                preview_label = QLabel(preview_text)
                preview_label.setObjectName("muted")
                info_col.addWidget(title_label)
                info_col.addWidget(preview_label)
                row_layout.addLayout(info_col, 1)

            meta_col = QVBoxLayout()
            meta_col.setSpacing(2)
            created = str(item.get("created_at", ""))
            try:
                created_text = datetime.datetime.fromisoformat(created).strftime("%m-%d %H:%M")
            except ValueError:
                created_text = created
            result_text = "成功" if item.get("success") else "失败"
            if item.get("error"):
                result_text += f"：{item.get('error')}"
            meta_label = QLabel(f"{created_text} · {result_text}")
            meta_label.setObjectName("muted")
            meta_label.setWordWrap(True)
            meta_col.addWidget(meta_label)
            row_layout.addLayout(meta_col, 0)

            copy_btn = QPushButton("复制")
            copy_btn.setObjectName("secondary")
            copy_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            copy_btn.clicked.connect(lambda _checked=False, record_id=str(item.get("id", "")): self._copy_record(record_id))
            delete_btn = QPushButton("删除")
            delete_btn.setObjectName("danger")
            delete_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            delete_btn.clicked.connect(lambda _checked=False, record_id=str(item.get("id", "")): self._delete_record(record_id))
            row_layout.addWidget(copy_btn)
            row_layout.addWidget(delete_btn)
            self.records_layout.addWidget(row)
        self.records_layout.addStretch(1)

    def _copy_record(self, record_id: str) -> None:
        for item in self.controller.records():
            if str(item.get("id")) != record_id:
                continue
            try:
                if item.get("type") == "image":
                    copy_image_to_clipboard(Path(str(item.get("image_path", ""))))
                    self.records_summary.setText("图片已复制到剪贴板")
                elif item.get("type") == "file":
                    copy_files_to_clipboard([Path(str(item.get("file_path", "")))])
                    self.records_summary.setText("文件已复制到剪贴板")
                else:
                    copy_text(str(item.get("text", "")))
                    self.records_summary.setText("文字已复制到剪贴板")
            except Exception as error:
                QMessageBox.warning(self, "复制失败", str(error))
            return

    def _delete_record(self, record_id: str) -> None:
        result = QMessageBox.question(
            self,
            "删除记录",
            "删除这条记录后，对应图片文件也会一起删除。继续吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if result != QMessageBox.StandardButton.Yes:
            return
        self.controller.delete_record(record_id)
        self._records_signature = None
        self._refresh_records(force=True)

    def _clear_records(self) -> None:
        result = QMessageBox.question(
            self,
            "清空全部记录",
            "确定要清空全部发送记录吗？对应图片文件也会一起删除。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if result != QMessageBox.StandardButton.Yes:
            return
        result = QMessageBox.question(
            self,
            "再次确认",
            "这是不可恢复操作。再次确认清空全部记录和图片文件？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if result != QMessageBox.StandardButton.Yes:
            return
        self.controller.clear_records()
        self._records_signature = None
        self._refresh_records(force=True)

    def _run_self_check(self) -> None:
        self.self_check_btn.setEnabled(False)
        self.self_check_result.setText("正在检查……")
        self.self_check_result.setVisible(True)
        QApplication.processEvents()
        try:
            results = run_checks(
                int(self.config["port"]),
                self.token,
                self.controller.is_running,
            )
            lines = []
            for result in results:
                state = "通过" if result.ok else "需要处理"
                line = f"{state} · {result.name}：{result.detail}"
                if not result.ok and result.hint:
                    line += f"\n  建议：{result.hint}"
                lines.append(line)
            self.self_check_result.setText("\n".join(lines))
            self.open_firewall_btn.setVisible(any(not item.ok for item in results))
        except Exception as error:
            self.self_check_result.setText(f"自检失败：{error}")
        finally:
            self.self_check_btn.setEnabled(True)

    def _open_firewall_settings(self) -> None:
        subprocess.Popen(
            ["control.exe", "/name", "Microsoft.WindowsDefenderFirewall"],
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )

    def _setup_tray(self) -> None:
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        icon_path = resource_path("assets/icon.png")
        self.tray = QSystemTrayIcon(QIcon(str(icon_path)), self)
        menu = QMenu()
        show_action = QAction("显示主窗口", self)
        show_action.triggered.connect(self._show_window)
        copy_action = QAction("复制手机地址", self)
        copy_action.triggered.connect(self._copy_phone_url)
        self.tray_toggle_action = QAction("停止服务", self)
        self.tray_toggle_action.triggered.connect(self._toggle_server)
        quit_action = QAction("退出 PKB", self)
        quit_action.triggered.connect(self._quit_app)
        menu.addAction(show_action)
        menu.addAction(copy_action)
        menu.addSeparator()
        menu.addAction(self.tray_toggle_action)
        menu.addSeparator()
        menu.addAction(quit_action)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._tray_activated)
        self.tray.show()
        self._refresh_tray_menu()

    def _tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self._show_window()

    def _refresh_tray_menu(self) -> None:
        if self.tray is None or not hasattr(self, "tray_toggle_action"):
            return
        self.tray_toggle_action.setText("停止服务" if self.controller.is_running else "启动服务")
        self.tray.setToolTip(f"PKB · {self.controller.online_count} 台在线")

    def _show_window(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _quit_app(self) -> None:
        self._really_quit = True
        if self.tray is not None:
            self.tray.hide()
        self.close()
        QApplication.quit()

    def _auto_check_update(self) -> None:
        if not self.config.get("auto_update_check", True):
            return
        try:
            last_check = float(self.config.get("last_update_check", 0.0))
        except (TypeError, ValueError):
            last_check = 0.0
        if time.time() - last_check < 86400:
            return
        self._check_for_updates(silent=True)

    def _check_for_updates(self, silent: bool = False) -> None:
        if self._update_check_worker is not None and self._update_check_worker.isRunning():
            return
        self.check_update_btn.setEnabled(False)
        if not silent:
            self.update_status.setText("正在检查 GitHub 上的最新版本…")
        worker = UpdateCheckWorker(VERSION, self)
        self._update_check_worker = worker
        worker.result_ready.connect(lambda info, error: self._handle_update_check_result(info, error, silent))
        worker.start()

    def _handle_update_check_result(self, info: object, error: object, silent: bool) -> None:
        self._update_check_worker = None
        self.check_update_btn.setEnabled(True)
        self.config["last_update_check"] = time.time()
        try:
            save_config(self.config)
        except Exception:
            pass
        if error is not None:
            message = f"检查更新失败：{error}"
            self.update_status.setText(message)
            if not silent:
                QMessageBox.warning(self, "检查更新", message)
            return
        if info is None:
            self.update_status.setText(f"当前已是最新版本 v{VERSION}")
            if not silent:
                QMessageBox.information(self, "检查更新", "当前已经是最新版本。")
            return
        update = info
        if not isinstance(update, UpdateInfo):
            return
        self.update_status.setText(f"发现新版本 v{update.version}，当前版本 v{VERSION}")
        notes = update.notes.strip()
        if len(notes) > 500:
            notes = notes[:500] + "…"
        detail = f"发现新版本 v{update.version}。\n\n{notes}\n\n是否下载并安装？"
        result = QMessageBox.question(
            self,
            "发现新版本",
            detail,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if result == QMessageBox.StandardButton.Yes:
            self._start_update_download(update)

    def _start_update_download(self, update: UpdateInfo) -> None:
        if self._update_download_worker is not None and self._update_download_worker.isRunning():
            return
        self.check_update_btn.setEnabled(False)
        self.update_status.setText(f"正在下载 v{update.version}…")
        worker = UpdateDownloadWorker(update, Path(tempfile.gettempdir()) / "PKB-update", self)
        self._update_download_worker = worker
        worker.progress_changed.connect(self._update_download_progress)
        worker.result_ready.connect(lambda path, error: self._handle_update_download_result(update, path, error))
        worker.start()

    def _update_download_progress(self, downloaded: int, total: int) -> None:
        if total > 0:
            percent = min(100, int(downloaded * 100 / total))
            self.update_status.setText(f"正在下载更新：{percent}%")
        else:
            self.update_status.setText(f"正在下载更新：{downloaded // (1024 * 1024)} MB")

    def _handle_update_download_result(self, update: UpdateInfo, path: object, error: object) -> None:
        self._update_download_worker = None
        if error is not None:
            self.check_update_btn.setEnabled(True)
            self.update_status.setText(f"更新下载失败：{error}")
            QMessageBox.warning(self, "更新失败", f"下载新版本失败：{error}")
            return
        if not isinstance(path, Path):
            self.check_update_btn.setEnabled(True)
            return
        if not getattr(sys, "frozen", False):
            self.check_update_btn.setEnabled(True)
            self.update_status.setText("更新已下载，但源码运行模式不能自动替换")
            QMessageBox.information(self, "自动更新", "当前是源码运行模式，请使用打包后的 PKB.exe 进行自动更新。")
            return
        result = QMessageBox.question(
            self,
            "更新已下载",
            f"v{update.version} 已下载并校验通过。现在退出并安装更新吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if result != QMessageBox.StandardButton.Yes:
            self.check_update_btn.setEnabled(True)
            self.update_status.setText("更新已下载，稍后可在设置页重新检查")
            return
        try:
            launch_update_installer(Path(sys.executable), path)
            self.update_status.setText("正在安装更新，PKB 将自动重启…")
            QTimer.singleShot(500, self._quit_app)
        except Exception as error:
            self.check_update_btn.setEnabled(True)
            self.update_status.setText(f"启动更新程序失败：{error}")
            QMessageBox.warning(self, "更新失败", str(error))

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
        self.controller.clear_devices()
        self._shown_pending.clear()
        try:
            (data_dir / "token.txt").unlink()
        except FileNotFoundError:
            pass
        self.controller.stop()
        self._start_server()
        self._refresh_approved_devices()
        self.settings_status.setText("连接令牌和授权设备已重置，请让手机重新扫码。")

    def _save_settings(self) -> None:
        port_text = self.port_edit.text().strip()
        if not port_text or not port_text.isdigit() or not (1024 <= int(port_text) <= 65535):
            self.settings_status.setText("端口必须是 1024 到 65535 之间的数字。")
            return
        port = int(port_text)
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
        self.config["auto_update_check"] = bool(self.update_switch.isChecked())
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
        if self.tray is not None and not self._really_quit:
            event.ignore()
            self.hide()
            if not self.config.get("tray_hint_shown", False):
                self.tray.showMessage(
                    "PKB 仍在后台运行",
                    "关闭窗口不会停止服务。要完全退出，请右键托盘图标选择“退出 PKB”。",
                    QSystemTrayIcon.MessageIcon.Information,
                    4000,
                )
                self.config["tray_hint_shown"] = True
                try:
                    save_config(self.config)
                except Exception:
                    logging.getLogger("pkb.ui").exception("Failed to save tray hint state")
            return
        self.controller.stop()
        if self.tray is not None:
            self.tray.hide()
        event.accept()
