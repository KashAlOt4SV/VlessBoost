"""Cached Qt screens, bounded workers and native Windows window lifecycle."""
from __future__ import annotations

from collections import deque
from copy import deepcopy
import logging
import math
import queue
import sys
import threading
import time
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal, QObject, QVariantAnimation, QEasingCurve, QRectF, QPointF
from PySide6.QtGui import QColor, QPainter, QPen, QPainterPath, QLinearGradient, QRadialGradient, QFont, QIcon, QPixmap
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QFrame, QLabel, QPushButton, QVBoxLayout,
    QHBoxLayout, QGridLayout, QStackedWidget, QScrollArea, QLineEdit,
    QPlainTextEdit, QFileDialog, QDialog, QDialogButtonBox, QTableWidget,
    QTableWidgetItem, QHeaderView, QAbstractItemView, QComboBox, QSystemTrayIcon, QMenu,
    QAbstractButton,
)

from app import __version__
from app.amneziawg import AmneziaWGManager, find_binary
from app.awg_profile import parse_awg_profile
from app.connection_check import check_https_proxy
from app.list_updater import update_all_remote
from app.paths import LOG_PATH
from app.log_utils import redact
from app.presets import CATALOG
from app.settings import load_settings, save_settings
from app.ui.veil_theme import STYLE, BG, BLUE, GREEN, MUTED

log = logging.getLogger(__name__)


def label(text, kind=None):
    item = QLabel(text)
    if kind:
        item.setProperty("kind", kind)
    if kind == "muted":
        item.setWordWrap(True)
    return item


def button(text, callback, primary=False):
    item = GlowButton(text)
    item.setProperty("primary", primary)
    item.setCursor(Qt.CursorShape.PointingHandCursor)
    item.clicked.connect(callback)
    return item


class GlowButton(QPushButton):
    """A 120 ms border highlight painted in place, without stylesheet churn."""
    def __init__(self, text):
        super().__init__(text)
        self.glow = 0.
        self.motion = QVariantAnimation(self)
        self.motion.setDuration(120)
        self.motion.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.motion.valueChanged.connect(self._frame)

    def _frame(self, value):
        self.glow = float(value)
        self.update()

    def _hover(self, value):
        self.motion.stop()
        settings = getattr(self.window(), "settings", None)
        if settings and settings.reduce_motion:
            self._frame(value)
            return
        self.motion.setStartValue(self.glow)
        self.motion.setEndValue(value)
        self.motion.start()

    def enterEvent(self, event):
        if self.isEnabled():
            self._hover(1.)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hover(0.)
        super().leaveEvent(event)

    def hideEvent(self, event):
        self.motion.stop()
        self.glow = 0.
        super().hideEvent(event)

    def paintEvent(self, event):
        super().paintEvent(event)
        if self.glow > .01 and self.isEnabled():
            p = QPainter(self)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(QColor(150, 202, 255, round(150*self.glow)), 1))
            p.drawRoundedRect(QRectF(.5, .5, self.width()-1, self.height()-1), 7, 7)


def box(parent=None, margins=20, gap=12, horizontal=False):
    layout = QHBoxLayout(parent) if horizontal else QVBoxLayout(parent)
    layout.setContentsMargins(margins, margins, margins, margins)
    layout.setSpacing(gap)
    return layout


def card():
    item = QFrame()
    item.setObjectName("card")
    return item


def bolt_icon():
    pix = QPixmap(64, 64)
    pix.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(QPen(QColor(BLUE), 3, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    path = QPainterPath(QPointF(35, 8))
    for x, y in [(15, 35), (29, 35), (25, 56), (49, 27), (34, 27), (35, 8)]:
        path.lineTo(x, y)
    painter.drawPath(path)
    painter.end()
    return QIcon(pix)


def nav_icon(kind):
    pix = QPixmap(20, 20)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(QPen(QColor("#9db7d1"), 1.2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    if kind == 0:
        path = QPainterPath(QPointF(1, 10))
        for x, y in [(5, 10), (7, 3), (11, 17), (14, 8), (16, 10), (19, 10)]:
            path.lineTo(x, y)
        p.drawPath(path)
    elif kind == 1:
        for start, end in [((10, 6), (10, 10)), ((4, 10), (16, 10)), ((4, 10), (4, 14)), ((16, 10), (16, 14))]:
            p.drawLine(QPointF(*start), QPointF(*end))
        for x, y in [(8, 2), (2, 14), (14, 14)]:
            p.drawRoundedRect(QRectF(x, y, 4, 4), 1, 1)
    elif kind == 2:
        for y, x in [(4, 6), (10, 14), (16, 9)]:
            p.drawLine(2, y, 18, y)
            p.setBrush(QColor("#0e141b"))
            p.drawEllipse(QPointF(x, y), 2.2, 2.2)
    else:
        p.drawLine(3, 5, 7, 9)
        p.drawLine(7, 9, 3, 13)
        p.drawLine(10, 14, 17, 14)
    p.end()
    return QIcon(pix)


class Toggle(QAbstractButton):
    """One small painted surface. No animated geometry, shadows or layout."""
    def __init__(self, checked=False, reduce_motion=False):
        super().__init__()
        self.setCheckable(True)
        self.setChecked(checked)
        self.setFixedSize(42, 26)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.reduce_motion = reduce_motion
        self.position = float(checked)
        self.animation = QVariantAnimation(self)
        self.animation.setDuration(140)
        self.animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.animation.valueChanged.connect(self._value)
        self.toggled.connect(self._toggle)

    def _value(self, value):
        self.position = value
        self.update()

    def _toggle(self, checked):
        self.animation.stop()
        if self.reduce_motion or not self.isVisible() or not self.underMouse():
            self._value(float(checked))
            return
        self.animation.setStartValue(self.position)
        self.animation.setEndValue(float(checked))
        self.animation.start()

    def hideEvent(self, event):
        self.animation.stop()
        self.position = float(self.isChecked())
        super().hideEvent(event)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        off, on = QColor("#293748"), QColor(BLUE)
        color = QColor(*[round(a + (b-a)*self.position) for a, b in zip(off.getRgb()[:3], on.getRgb()[:3])])
        p.setBrush(color)
        p.drawRoundedRect(QRectF(1, 4, 40, 20), 10, 10)
        p.setBrush(QColor("#0b1521") if self.isChecked() else QColor("#a6b2c2"))
        p.drawEllipse(QRectF(4 + 20*self.position, 7, 14, 14))
        if self.hasFocus():
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(QColor(BLUE), 1))
            p.drawRoundedRect(QRectF(.5, .5, 41, 25), 7, 7)


class Hero(QFrame):
    def __init__(self):
        super().__init__()
        self.setMinimumHeight(210)
        self.connected = False
        self.busy = False
        self.phase = 0.
        self.motion = True
        self.timer = QTimer(self)
        self.timer.setInterval(40)
        self.timer.timeout.connect(self._tick)

    def _tick(self):
        self.phase = (self.phase + .035) % (math.pi * 2)
        self.update()

    def set_state(self, connected, busy, motion):
        self.connected, self.busy, self.motion = connected, busy, motion
        self._sync()
        self.update()

    def _sync(self):
        if self.busy and self.motion and self.isVisible() and not self.window().isMinimized():
            self.timer.start()
        else:
            self.timer.stop()

    def showEvent(self, event):
        self._sync()
        super().showEvent(event)

    def hideEvent(self, event):
        self.timer.stop()
        super().hideEvent(event)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        gradient = QLinearGradient(0, 0, self.width(), self.height())
        gradient.setColorAt(0, QColor("#192c42"))
        gradient.setColorAt(.65, QColor("#121d2b"))
        gradient.setColorAt(1, QColor("#101923"))
        p.setBrush(gradient)
        p.setPen(QPen(QColor("#2b425b"), 1))
        p.drawRoundedRect(QRectF(.5, .5, self.width()-1, self.height()-1), 13, 13)
        center = QPointF(self.width()-112, 90)
        glow = QRadialGradient(center, 105)
        glow.setColorAt(0, QColor(90, 165, 255, 38))
        glow.setColorAt(1, QColor(90, 165, 255, 0))
        p.setBrush(glow)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(center, 103, 103)
        p.setBrush(Qt.BrushStyle.NoBrush)
        for radius in (42, 64, 86):
            p.setPen(QPen(QColor("#2c4561"), 1))
            p.drawEllipse(center, radius, radius)
        p.setPen(QPen(QColor(BLUE), 2))
        path = QPainterPath(center + QPointF(5, -24))
        for point in [(-16, 3), (-1, 3), (-6, 25), (18, -7), (4, -7), (5, -24)]:
            path.lineTo(center + QPointF(*point))
        p.drawPath(path)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(GREEN if self.connected else BLUE))
        angle = self.phase if self.busy else -.7
        p.drawEllipse(center + QPointF(64*math.cos(angle), 64*math.sin(angle)), 4, 4)


class LatencyChart(QWidget):
    def __init__(self):
        super().__init__()
        self.samples = deque(maxlen=30)
        self.setMinimumHeight(112)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        area = QRectF(0, 8, self.width(), self.height()-18)
        p.setPen(QPen(QColor("#22303f"), 1, Qt.PenStyle.DotLine))
        for fraction in (0, .5, 1):
            y = area.top() + area.height()*fraction
            p.drawLine(QPointF(area.left(), y), QPointF(area.right(), y))
        if not self.samples:
            p.setPen(QColor(MUTED))
            p.drawText(area, Qt.AlignmentFlag.AlignCenter, "График появится после подключения")
            return
        top = max(100, max((v or 0) for v in self.samples)*1.3)
        path = QPainterPath()
        has_point = False
        for i, value in enumerate(self.samples):
            if value is None:
                has_point = False
                continue
            point = QPointF(area.left()+area.width()*i/29, area.bottom()-area.height()*value/top)
            if has_point:
                path.lineTo(point)
            else:
                path.moveTo(point)
            has_point = True
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(BLUE))
            p.drawEllipse(point, 2.5, 2.5)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor(100, 174, 255, 25), 8))
        p.drawPath(path)
        p.setPen(QPen(QColor(BLUE), 1.8))
        p.drawPath(path)


class LogBridge(logging.Handler):
    def __init__(self):
        super().__init__()
        self.pending = deque(maxlen=500)
        self.setFormatter(logging.Formatter("%(asctime)s  %(levelname)-7s  %(message)s", "%H:%M:%S"))

    def emit(self, record):
        # A busy router must not flood Qt's unbounded queued-signal event queue.
        self.pending.append((record.levelname, redact(self.format(record))[:2000]))


class VeilWindow(QMainWindow):
    def __init__(self, settings=None, manager=None):
        super().__init__()
        self.settings = settings if settings is not None else load_settings()
        self.manager = manager if manager is not None else AmneziaWGManager()
        self.results = queue.SimpleQueue()
        self.workers = set()
        self.busy = False
        self.connected = False
        self.exiting = False
        self._exit_requested = False
        self._quitting = False
        self.started = None
        self._telemetry_pending = False
        self._last_probe = 0.
        self._last_transfer = None
        self._session_id = 0
        self._last_log_filter = "Все события"
        self.records = deque(maxlen=1000)
        self.setWindowTitle("VEIL · Network Accelerator")
        self.resize(1220, 840)
        self.setMinimumSize(980, 710)
        self.setWindowIcon(bolt_icon())
        self.setStyleSheet(STYLE)
        self._build()
        self._tray()
        self.bridge = LogBridge()
        logging.getLogger().addHandler(self.bridge)
        self.poll = QTimer(self)
        self.poll.setInterval(50)
        self.poll.timeout.connect(self._drain)
        self.poll.start()
        self.tick = QTimer(self)
        self.tick.setInterval(2000)
        self.tick.timeout.connect(self._tick)
        self.tick.start()
        self._update_routes()
        self._profile_summary()
        QTimer.singleShot(0, self._initial_checks)

    def _build(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = box(central, 0, 0, horizontal=True)
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(205)
        side = box(sidebar, 18, 9)
        brand = box(gap=9, horizontal=True)
        mark = QLabel()
        mark.setPixmap(bolt_icon().pixmap(29, 29))
        brand.addWidget(mark)
        name = label("VEIL")
        name.setStyleSheet("font-size: 21px; font-weight: 600; letter-spacing: 3px")
        brand.addWidget(name)
        brand.addStretch()
        side.addLayout(brand)
        side.addWidget(label("NETWORK ACCELERATOR", "eyebrow"))
        side.addSpacing(30)
        self.nav = []
        for index, text in enumerate(("Главная", "Маршрутизация", "Настройки", "Журнал событий")):
            item = button(text, lambda checked=False, i=index: self._navigate(i))
            item.setIcon(nav_icon(index))
            item.setProperty("nav", True)
            item.setCheckable(True)
            side.addWidget(item)
            self.nav.append(item)
        self.nav[0].setChecked(True)
        side.addStretch()
        engine = QFrame()
        engine.setObjectName("engine")
        engine_box = box(engine, 13, 8)
        self.engine_status = label("●  ПРОВЕРКА ЯДРА", "eyebrow")
        self.engine_status.setStyleSheet("color: #6ee7bd; letter-spacing: 1px; font-size: 10px")
        engine_box.addWidget(self.engine_status)
        engine_box.addWidget(label("AmneziaWG 3.1", "section"))
        engine_box.addWidget(label("Выборочный маршрут", "muted"))
        side.addWidget(engine)
        side.addSpacing(8)
        side.addWidget(label("Windows  ·  " + __version__, "muted"))
        root.addWidget(sidebar)
        right = box(margins=0, gap=0)
        topbar = QFrame()
        topbar.setObjectName("topbar")
        top = box(topbar, 14, 8, horizontal=True)
        top.addWidget(label("РАЗДЕЛЬНЫЙ ТУННЕЛЬ", "eyebrow"))
        top.addStretch()
        self.top_status = label("●  Не подключено", "muted")
        top.addWidget(self.top_status)
        right.addWidget(topbar)
        self.stack = QStackedWidget()
        right.addWidget(self.stack, 1)
        for build_page in (self._home, self._routing, self._settings, self._logs):
            page = QWidget()
            body = box(page, 26, 14)
            build_page(body)
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setWidget(page)
            self.stack.addWidget(scroll)
        root.addLayout(right, 1)
        self.notice = label("")
        self.notice.setWordWrap(True)
        self.notice.setStyleSheet("color: #9bc8ff; padding: 7px 20px; background: #111e2b")
        self.notice.hide()
        right.addWidget(self.notice)

    def _heading(self, layout, title, description):
        row = box(margins=0, horizontal=True)
        texts = box(margins=0, gap=6)
        texts.addWidget(label(title, "title"))
        texts.addWidget(label(description, "muted"))
        row.addLayout(texts, 1)
        row.addWidget(label("AWG / 3.1", "badge"), 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(row)

    def _home(self, layout):
        self._heading(layout, "Обзор подключения", "Ваш трафик. Ваш маршрут. Полный контроль.")
        self.hero = Hero()
        content = box(self.hero, 24, 8)
        content.addWidget(label("ЗАЩИЩЁННЫЙ МАРШРУТ", "eyebrow"))
        self.connection_title = label("Готовы к подключению")
        self.connection_title.setStyleSheet("font-size: 26px; font-weight: 600")
        content.addWidget(self.connection_title)
        content.addWidget(label("Только выбранные приложения и сайты используют туннель.", "muted"))
        content.addStretch()
        bottom = box(margins=0, horizontal=True)
        server = box(margins=0, gap=5)
        self.server_label = label("Добавьте профиль AmneziaWG", "section")
        self.session_label = label("UDP  ·  Раздельная маршрутизация", "muted")
        server.addWidget(self.server_label)
        server.addWidget(self.session_label)
        bottom.addLayout(server, 1)
        self.connect_button = button("Подключить  →", self._connect, True)
        self.connect_button.setMinimumWidth(145)
        bottom.addWidget(self.connect_button, 0, Qt.AlignmentFlag.AlignBottom)
        content.addLayout(bottom)
        layout.addWidget(self.hero)
        metrics = box(margins=0, gap=12, horizontal=True)
        self.metric_values, self.metric_notes = [], []
        for title, note in (("ОТКЛИК ТУННЕЛЯ", "HTTPS через AWG"), ("ВХОДЯЩИЙ ТРАФИК", "Счётчики сетевого ядра"), ("СОСТОЯНИЕ ТУННЕЛЯ", "Ожидание подключения")):
            panel = card()
            inner = box(panel, 16, 7)
            inner.addWidget(label(title, "muted"))
            value = label("—", "metric")
            inner.addWidget(value)
            info = label(note, "muted")
            inner.addWidget(info)
            self.metric_values.append(value)
            self.metric_notes.append(info)
            metrics.addWidget(panel, 1)
        layout.addLayout(metrics)
        graph = card()
        body = box(graph, 18, 8)
        header = box(margins=0, horizontal=True)
        header.addWidget(label("Стабильность соединения", "section"))
        header.addStretch()
        period = label("30 последних проверок", "muted")
        period.setWordWrap(False)
        header.addWidget(period)
        body.addLayout(header)
        self.chart = LatencyChart()
        body.addWidget(self.chart)
        body.addWidget(label("Отклик HTTPS: соединение, TLS и ответ сервера · проверка раз в 10 секунд", "muted"))
        layout.addWidget(graph)
        routes = card()
        inner = box(routes, 18, 10)
        heading = box(margins=0, horizontal=True)
        heading.addWidget(label("Выбрано для маршрута", "section"))
        heading.addStretch()
        heading.addWidget(button("Управление  ↗", lambda: self._navigate(1)))
        inner.addLayout(heading)
        self.home_routes = label("")
        self.home_routes.setWordWrap(True)
        inner.addWidget(self.home_routes)
        layout.addWidget(routes)
        layout.addStretch()

    def _routing(self, layout):
        self._heading(layout, "Маршрутизация", "Выберите, какой трафик направлять через туннель.")
        intro = card()
        inner = box(intro, 18, 7)
        inner.addWidget(label("Раздельная маршрутизация", "section"))
        inner.addWidget(label("Выбранные процессы, домены и IP → AmneziaWG. Остальной трафик → напрямую.", "muted"))
        layout.addWidget(intro)
        tools = box(margins=0, horizontal=True)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Найти приложение или сервис…")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._filter_routes)
        tools.addWidget(self.search, 1)
        self.list_button = button("Обновить IP-листы", self._update_lists)
        tools.addWidget(self.list_button)
        tools.addWidget(button("+  Приложение", self._add_application, True))
        layout.addLayout(tools)
        self.table = QTableWidget(len(CATALOG), 3)
        self.table.setHorizontalHeaderLabels(["ПРИЛОЖЕНИЕ / СЕРВИС", "ПРАВИЛО", "ТУННЕЛЬ"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(2, 110)
        self.table.verticalHeader().hide()
        self.table.setShowGrid(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setMinimumHeight(355)
        self.toggles = []
        for row, preset in enumerate(CATALOG):
            self.table.setRowHeight(row, 54)
            self.table.setItem(row, 0, QTableWidgetItem(preset.name))
            description = ", ".join(preset.processes[:2]) or preset.description
            detail = QTableWidgetItem(description)
            detail.setForeground(QColor(MUTED))
            detail.setToolTip(preset.description)
            self.table.setItem(row, 1, detail)
            wrapper = QWidget()
            inner = box(wrapper, 0, horizontal=True)
            toggle = Toggle(self.settings.is_enabled(preset.id), self.settings.reduce_motion)
            toggle.setAccessibleName("Через туннель: " + preset.name)
            toggle.toggled.connect(lambda enabled, pid=preset.id: self._set_route(pid, enabled))
            inner.addWidget(toggle, 0, Qt.AlignmentFlag.AlignCenter)
            self.table.setCellWidget(row, 2, wrapper)
            self.toggles.append(toggle)
        layout.addWidget(self.table, 1)
        custom = card()
        inner = box(custom, 18, 10)
        inner.addWidget(label("Свои правила", "section"))
        self.custom_domains = QLineEdit(", ".join(self.settings.custom_domains))
        self.custom_domains.setPlaceholderText("Домены: example.com, example.org")
        self.custom_processes = QLineEdit(", ".join(self.settings.custom_processes))
        self.custom_processes.setPlaceholderText("Процессы: game.exe, browser.exe")
        inner.addWidget(self.custom_domains)
        inner.addWidget(self.custom_processes)
        inner.addWidget(button("Сохранить правила", self._save_custom), 0, Qt.AlignmentFlag.AlignRight)
        layout.addWidget(custom)
        layout.addWidget(label("Изменения маршрута применяются при следующем подключении. Локальная сеть остаётся напрямую.", "muted"))

    def _settings(self, layout):
        self._heading(layout, "Настройки", "Профиль подключения и поведение клиента.")
        profile = card()
        inner = box(profile, 20, 13)
        inner.addWidget(label("Профиль подключения", "section"))
        inner.addWidget(label("AmneziaWG 3.1 · .conf или vpn:// с вложенным AWG-профилем", "muted"))
        row = box(margins=0, horizontal=True)
        self.profile_display = QLineEdit()
        self.profile_display.setReadOnly(True)
        self.profile_display.setPlaceholderText("Профиль ещё не добавлен")
        row.addWidget(self.profile_display, 1)
        row.addWidget(button("Импорт .conf", self._import_file, True))
        row.addWidget(button("Вставить", self._import_text))
        inner.addLayout(row)
        self.profile_info = label("Ключи скрыты. Для нового транспорта нужен профиль AWG 3.1.", "muted")
        self.profile_info.setWordWrap(True)
        inner.addWidget(self.profile_info)
        layout.addWidget(profile)
        behavior = card()
        inner = box(behavior, 20, 8)
        inner.addWidget(label("Поведение приложения", "section"))
        self.preference_toggles = []
        for field, title, note in (
            ("minimize_to_tray", "Сворачивать в системный трей", "При закрытии окна сохранять активное соединение"),
            ("reduce_motion", "Уменьшить анимации", "Мгновенные переключатели и статичный индикатор подключения"),
            ("route_processes", "Маршрутизация по приложениям", "Направлять весь трафик выбранных процессов через AWG"),
            ("route_domains", "Маршрутизация по доменам", "Применять доменные правила выбранных сервисов"),
            ("route_ips", "Маршрутизация по IP-листам", "Использовать загруженные списки IP выбранных сервисов"),
        ):
            row = box(margins=0, gap=15, horizontal=True)
            texts = box(margins=0, gap=4)
            texts.addWidget(label(title))
            texts.addWidget(label(note, "muted"))
            row.addLayout(texts, 1)
            toggle = Toggle(getattr(self.settings, field), self.settings.reduce_motion)
            toggle.setAccessibleName(title)
            toggle.toggled.connect(lambda value, name=field: self._preference(name, value))
            self.preference_toggles.append(toggle)
            row.addWidget(toggle)
            inner.addSpacing(12)
            inner.addLayout(row)
        layout.addWidget(behavior)
        network = card()
        inner = box(network, 20, 10)
        inner.addWidget(label("Сеть", "section"))
        self.network_info = label("MTU 1280  ·  UDP  ·  DNS выбранного трафика через туннель", "muted")
        inner.addWidget(self.network_info)
        inner.addWidget(label("Рабочие сервисы Microsoft и локальные адреса остаются напрямую.", "muted"))
        layout.addWidget(network)
        layout.addWidget(label("Настройки сохраняются автоматически. Сетевые изменения — со следующего подключения.", "muted"))
        layout.addStretch()

    def _logs(self, layout):
        self._heading(layout, "Журнал событий", "Всё, что происходит с вашим подключением.")
        tools = box(margins=0, horizontal=True)
        self.log_filter = QComboBox()
        self.log_filter.addItems(["Все события", "Информация", "Предупреждения", "Ошибки"])
        self.log_filter.currentTextChanged.connect(self._render_logs)
        tools.addWidget(self.log_filter)
        tools.addStretch()
        tools.addWidget(button("Экспорт .log", self._export_logs, True))
        layout.addLayout(tools)
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(1000)
        self.log_view.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.log_view.setStyleSheet("font-family: Consolas; font-size: 12px; padding: 15px; background: #111821")
        layout.addWidget(self.log_view, 1)
        self.log_count = label("0 событий  ·  Время локальное  ·  Последние 1000 записей", "muted")
        layout.addWidget(self.log_count)

    def _navigate(self, index):
        self.stack.setCurrentIndex(index)
        for i, item in enumerate(self.nav):
            item.setChecked(i == index)

    def _work(self, work, done, failed=None):
        def run():
            try:
                result = work()
                self.results.put((done, result))
            except Exception as exc:
                log.error("%s", exc)
                self.results.put((failed or self._failure, str(exc)))
            finally:
                self.results.put((self.workers.discard, thread))
        thread = threading.Thread(target=run, name="veil-worker", daemon=True)
        self.workers.add(thread)
        thread.start()

    def _drain(self):
        for _ in range(40):
            try:
                self._record(*self.bridge.pending.popleft())
            except IndexError:
                break
        for _ in range(48):
            try:
                callback, result = self.results.get_nowait()
            except queue.Empty:
                break
            try:
                callback(result)
            except Exception:
                log.exception("UI callback failed")

    def _notify(self, text):
        self.notice.setText(text)
        self.notice.show()

    def _persist(self):
        try:
            save_settings(self.settings)
        except OSError as exc:
            self._notify("Не удалось сохранить настройки: " + str(exc))

    def _initial_checks(self):
        def check():
            try:
                find_binary()
                ready = True
            except FileNotFoundError:
                ready = False
            if sys.platform == "win32":
                self.manager.cleanup_stale()
            lines = []
            if LOG_PATH.exists():
                with LOG_PATH.open("rb") as stream:
                    stream.seek(max(0, LOG_PATH.stat().st_size - 64_000))
                    lines = stream.read().decode("utf-8", errors="replace").splitlines()[-150:]
            return ready, lines
        def done(result):
            ready, lines = result
            self.engine_status.setText("●  ЯДРО ГОТОВО" if ready else "○  НУЖЕН RUNTIME")
            for line in lines:
                self._record("ERROR" if "[ERROR]" in line else "INFO", line)
            log.info("VEIL ready; cached native Qt screens initialized")
        self._work(check, done)

    def _profile_summary(self):
        if not self.settings.awg_config:
            return
        try:
            profile = parse_awg_profile(self.settings.awg_config)
            self.profile_display.setText(profile.endpoint + "  ·  Ключ скрыт")
            self.server_label.setText(self.settings.profile_name + "  /  " + profile.host)
            self.profile_info.setText("Профиль AWG 3.1 проверен  ·  Header Protection  ·  Ключи скрыты")
            self.network_info.setText(f"MTU {profile.interface['mtu']}  ·  UDP  ·  DNS выбранного трафика через туннель")
        except ValueError as exc:
            self.profile_info.setText(str(exc))

    def _import_file(self):
        filename, _ = QFileDialog.getOpenFileName(self, "Импорт AmneziaWG 3.1", "", "AWG (*.conf);;Все файлы (*)")
        if not filename:
            return
        try:
            path = Path(filename)
            if path.stat().st_size > 2_000_000:
                raise ValueError("Профиль слишком большой")
            self._accept_profile(path.read_text(encoding="utf-8-sig"), path.stem)
        except (OSError, ValueError) as exc:
            self._notify(str(exc))

    def _import_text(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Импорт профиля AmneziaWG 3.1")
        dialog.resize(620, 420)
        inner = box(dialog, 22, 12)
        inner.addWidget(label("Вставьте .conf или vpn://", "section"))
        inner.addWidget(label("Профиль содержит приватный ключ. Он не попадёт в журнал.", "muted"))
        editor = QPlainTextEdit()
        editor.setPlaceholderText("[Interface]\nPrivateKey = …\nHeaderProtectionKey = …\n…\n[Peer]\n…")
        inner.addWidget(editor, 1)
        error = label("")
        error.setWordWrap(True)
        error.setStyleSheet("color: #ffadad")
        inner.addWidget(error)
        actions = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        actions.button(QDialogButtonBox.StandardButton.Save).setText("Сохранить профиль")
        actions.button(QDialogButtonBox.StandardButton.Cancel).setText("Отмена")
        def accept():
            try:
                self._accept_profile(editor.toPlainText(), "Мой сервер")
                editor.clear()
                dialog.accept()
            except ValueError as exc:
                error.setText(str(exc))
        actions.accepted.connect(accept)
        actions.rejected.connect(dialog.reject)
        inner.addWidget(actions)
        dialog.exec()
        editor.clear()

    def _accept_profile(self, text, name):
        profile = parse_awg_profile(text)
        self.settings.awg_config = profile.service_config()
        self.settings.profile_name = name
        self._persist()
        self._profile_summary()
        log.info("Imported AWG 3.1 profile; keys hidden")
        self._notify("Профиль сохранён. Можно подключаться." if not self.connected else "Профиль сохранён. Переподключитесь для его применения.")

    def _preference(self, field, value):
        setattr(self.settings, field, value)
        if field == "reduce_motion":
            for toggle in self.toggles + self.preference_toggles:
                toggle.reduce_motion = value
            self.hero.set_state(self.connected, self.busy, not value)
        self._persist()

    def _set_route(self, preset_id, value):
        self.settings.set_enabled(preset_id, value)
        self._persist()
        self._update_routes()
        if self.connected:
            self._notify("Правила сохранены. Переподключитесь, чтобы применить изменения.")

    def _update_routes(self):
        names = [p.name for p in CATALOG if self.settings.is_enabled(p.id)]
        self.home_routes.setText("   ·   ".join(names) if names else "Пока ничего не выбрано. Добавьте приложения или сервисы.")

    def _filter_routes(self, text):
        text = text.casefold()
        for row, preset in enumerate(CATALOG):
            self.table.setRowHidden(row, text not in (preset.name + " " + preset.description + " " + " ".join(preset.processes)).casefold())

    def _save_custom(self):
        import re
        domains = [v.strip().lower().lstrip(".") for v in self.custom_domains.text().split(",") if v.strip()]
        processes = [v.strip() for v in self.custom_processes.text().split(",") if v.strip()]
        if any(not re.fullmatch(r"[a-z0-9][a-z0-9.\-]*\.[a-z]{2,}", value) for value in domains):
            self._notify("Укажите домены без https://, путей и пробелов.")
            return
        if any(not value.lower().endswith(".exe") or "/" in value or "\\" in value for value in processes):
            self._notify("Укажите имена процессов с .exe, без пути к файлу.")
            return
        self.settings.custom_domains = list(dict.fromkeys(domains))
        self.settings.custom_processes = list(dict.fromkeys(processes))
        self.settings.set_enabled("custom", bool(domains or processes))
        for row, preset in enumerate(CATALOG):
            if preset.id == "custom":
                self.toggles[row].setChecked(bool(domains or processes))
        self._persist()
        self._update_routes()
        self._notify("Свои правила сохранены. Применение — при следующем подключении.")

    def _add_application(self):
        filename, _ = QFileDialog.getOpenFileName(self, "Выбрать приложение", "", "Приложение Windows (*.exe)")
        if filename:
            names = [v.strip() for v in self.custom_processes.text().split(",") if v.strip()]
            names.append(Path(filename).name)
            self.custom_processes.setText(", ".join(dict.fromkeys(names)))
            self._save_custom()

    def _update_lists(self):
        self._list_cancel = threading.Event()
        self.list_button.setEnabled(False)
        self.list_button.setText("Обновление…")
        def done(result):
            self.list_button.setEnabled(True)
            self.list_button.setText("Обновить IP-листы")
            failures = [name for name, value in result.items() if "error" in value]
            self._notify("Не удалось обновить: " + ", ".join(failures) if failures else "Списки обновлены. Применение — при следующем подключении.")
        def failed(error):
            done({"списки": {"error": error}})
        self._work(lambda: update_all_remote(cancel_event=self._list_cancel), done, failed)

    def _set_busy(self, value):
        self.busy = value
        self.connect_button.setEnabled(not value)
        self.hero.set_state(self.connected, value, not self.settings.reduce_motion)

    def _connect(self):
        if self.busy:
            return
        if self.connected:
            self._disconnect()
            return
        try:
            parse_awg_profile(self.settings.awg_config)
        except ValueError as exc:
            self._navigate(2)
            self._notify(str(exc))
            return
        self._set_busy(True)
        self.connection_title.setText("Устанавливаем соединение…")
        self.connect_button.setText("Подключение…")
        self.top_status.setText("◌  Подключение")
        snapshot = deepcopy(self.settings)
        self.manager.cancel_event.clear()
        self._work(lambda: self.manager.start(snapshot), self._connected)

    def _connected(self, result):
        self._session_id += 1
        self.connected = True
        self.started = time.monotonic()
        self._set_busy(False)
        self.connection_title.setText("Вы подключены")
        self.connect_button.setText("Отключить")
        self.top_status.setText("●  Туннель активен")
        self.top_status.setStyleSheet("color: #6ee7bd")
        self.metric_values[2].setText("Активен")
        self.metric_notes[2].setText("Подключение проверено")
        self.notice.hide()
        self.chart.samples.clear()
        self._last_probe = 0
        self._tick()
        if self._exit_requested:
            self._disconnect(exiting=True)

    def _disconnect(self, exiting=False):
        if self.busy:
            return
        self.exiting = exiting
        self._set_busy(True)
        self.connect_button.setText("Отключение…")
        self._work(self.manager.stop, self._disconnected)

    def _disconnected(self, result):
        self._session_id += 1
        self.connected = False
        self.started = None
        self._last_transfer = None
        self._set_busy(False)
        self.connection_title.setText("Готовы к подключению")
        self.connect_button.setText("Подключить  →")
        self.top_status.setText("●  Не подключено")
        self.top_status.setStyleSheet("")
        self.session_label.setText("UDP  ·  Раздельная маршрутизация")
        for item in self.metric_values:
            item.setText("—")
        self.metric_notes[1].setText("Счётчики сетевого ядра")
        self.metric_notes[2].setText("Ожидание подключения")
        if self.exiting:
            self._quit()

    def _failure(self, error):
        self.exiting = False
        self._set_busy(False)
        # A partial disconnect must remain retryable if service removal failed.
        self.connected = bool(self.manager.running or getattr(self.manager, "_owned", False))
        self.connection_title.setText("Не удалось отключиться" if self.connected else "Не удалось подключиться")
        self.connect_button.setText("Отключить" if self.connected else "Повторить  →")
        self.top_status.setText("●  Требуется внимание")
        self._notify(error)
        if self._exit_requested and not self.connected:
            self._quit()

    def _tick(self):
        if not self.connected or self.busy:
            return
        elapsed = int(time.monotonic() - self.started) if self.started else 0
        self.session_label.setText(f"AmneziaWG 3.1  ·  UDP  ·  {elapsed//3600:02}:{elapsed//60%60:02}:{elapsed%60:02}")
        if not self.manager.running:
            self._notify("Маршрутизатор завершился. Останавливаем туннель.")
            self._disconnect()
            return
        if not self.isVisible() or self.isMinimized() or self._telemetry_pending:
            return
        self._telemetry_pending = True
        session_id = self._session_id
        probe_port = self.manager.active_settings.socks_port
        probe = time.monotonic() - self._last_probe >= 10
        if probe:
            self._last_probe = time.monotonic()
        def read():
            stats = self.manager.telemetry()
            latency = None
            if probe:
                started = time.monotonic()
                try:
                    check_https_proxy(probe_port, "one.one.one.one", timeout=6)
                    latency = round((time.monotonic()-started)*1000)
                except (OSError, ValueError):
                    pass
            return stats, probe, latency
        def done(result):
            self._telemetry_pending = False
            if not self.connected or self.busy or session_id != self._session_id:
                return
            stats, probed, latency = result
            if not stats["alive"]:
                self._notify("Служба AWG остановилась. Отключаем маршрутизацию.")
                self._disconnect()
                return
            if probed:
                self.chart.samples.append(latency)
                self.chart.update()
                self.metric_values[0].setText(f"{latency} мс" if latency is not None else "—")
                self.metric_notes[0].setText("HTTPS через AWG" if latency is not None else "Проверка не прошла")
                self.metric_values[2].setText("Активен" if latency is not None else "Нет ответа")
                self.metric_notes[2].setText("Туннель отвечает" if latency is not None else "Служба работает, сервер не отвечает")
            if stats["rx"] is not None:
                now = time.monotonic()
                if self._last_transfer:
                    before, timestamp = self._last_transfer
                    rate = max(0, stats["rx"]-before)*8/(now-timestamp)/1_000_000
                    self.metric_values[1].setText(f"{rate:.1f} Мбит/с")
                self._last_transfer = stats["rx"], now
                self.metric_notes[1].setText(f"Получено {stats['rx']/1024/1024:.1f} МБ")
        def failed(error):
            self._telemetry_pending = False
            if self.connected:
                self.metric_values[2].setText("Проверка")
                self.metric_notes[2].setText("Нет данных от ядра")
        self._work(read, done, failed)

    def _record(self, level, text):
        text = redact(text)
        self.records.append((level, text))
        allowed = {"Информация": {"INFO", "DEBUG"}, "Предупреждения": {"WARNING"}, "Ошибки": {"ERROR", "CRITICAL"}}
        if self.log_filter.currentText() == "Все события" or level in allowed.get(self.log_filter.currentText(), set()):
            scrollbar = self.log_view.verticalScrollBar()
            bottom = scrollbar.value() >= scrollbar.maximum()-4
            position = scrollbar.value()
            self.log_view.appendPlainText(text)
            scrollbar.setValue(scrollbar.maximum() if bottom else position)
        self.log_count.setText(f"{len(self.records)} событий  ·  Время локальное  ·  Последние 1000 записей")

    def _render_logs(self, *_):
        allowed = {"Информация": {"INFO", "DEBUG"}, "Предупреждения": {"WARNING"}, "Ошибки": {"ERROR", "CRITICAL"}}
        selection = self.log_filter.currentText()
        self.log_view.setPlainText("\n".join(text for level, text in self.records
                                            if selection == "Все события" or level in allowed[selection]))

    def _export_logs(self):
        filename, _ = QFileDialog.getSaveFileName(self, "Экспорт журнала", "veil.log", "Журнал (*.log)")
        if filename:
            try:
                Path(filename).write_text("\n".join(text for _, text in self.records)+"\n", encoding="utf-8")
                self._notify("Журнал экспортирован: " + filename)
            except OSError as exc:
                self._notify(str(exc))

    def _tray(self):
        self.tray = QSystemTrayIcon(self.windowIcon(), self)
        self.tray.setToolTip("VEIL · Network Accelerator")
        menu = QMenu(self)
        menu.addAction("Открыть VEIL", self._restore)
        menu.addAction("Отключить", lambda: self._disconnect() if self.connected else None)
        menu.addSeparator()
        menu.addAction("Выход", self._request_quit)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(lambda reason: self._restore() if reason in
                                   (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick) else None)
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray.show()

    def _restore(self):
        # Native restore preserves maximized state; no alpha, topmost or delayed resizing.
        self.show()
        self.setWindowState(self.windowState() & ~Qt.WindowState.WindowMinimized)
        self.raise_()
        self.activateWindow()
        self.hero._sync()

    def changeEvent(self, event):
        super().changeEvent(event)
        if hasattr(self, "hero"):
            self.hero._sync()

    def closeEvent(self, event):
        if self._quitting:
            event.accept()
            return
        event.ignore()
        if self.settings.minimize_to_tray and self.tray.isVisible():
            self.hide()
            self.hero.timer.stop()
        else:
            self._request_quit()

    def _request_quit(self):
        if self.busy:
            self._exit_requested = True
            self.exiting = True
            self.manager.cancel_event.set()
            self._notify("Завершаем сетевые операции и выходим…")
            return
        self._disconnect(exiting=True)

    def _quit(self):
        self._quitting = True
        if hasattr(self, "_list_cancel"):
            self._list_cancel.set()
        self.tick.stop()
        self.poll.stop()
        self.hero.timer.stop()
        logging.getLogger().removeHandler(self.bridge)
        self.tray.hide()
        self.close()
        QApplication.instance().quit()


def run_app():
    app = QApplication(sys.argv)
    app.setApplicationName("VEIL")
    app.setOrganizationName("VEIL")
    app.setQuitOnLastWindowClosed(False)
    app.setFont(QFont("Segoe UI", 10))
    window = VeilWindow()
    window.show()
    app.exec()
