import json
import os
import sys
from dataclasses import dataclass
from collections import Counter
from urllib.request import Request, urlopen
from time import sleep

from PySide6.QtCore import (
    QEasingCurve,
    QObject,
    QPoint,
    QRunnable,
    QThreadPool,
    QTimer,
    Qt,
    Signal,
    QPropertyAnimation,
)
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QFrame,
    QGraphicsDropShadowEffect,
    QGraphicsOpacityEffect,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSizePolicy,
    QSpacerItem,
    QVBoxLayout,
    QWidget,
)

def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

APP_TITLE = "WinTrade MM2"
JSON_FILE = "supreme_values_mm2.json"
WINDOW_W = 900
WINDOW_H = 620
CARD_W = 112
CARD_H = 124
MAX_UNIQUE_ITEMS_PER_SIDE = 4
PURPLE = "#9B5CFF"
PURPLE_HOVER = "#B785FF"
BG = "#0D0A17"
BG_ALT = "#120D20"
PANEL = "#171129"
PANEL_2 = "#1D1633"
TEXT = "#F6F2FF"
MUTED = "#B7A9D6"
BORDER = "#332552"
GREEN = "#32D583"
RED = "#F97066"
YELLOW = "#F6C344"
INITIAL_BATCH = 28
LOAD_MORE_BATCH = 20
BROWSER_COLUMNS = 2


@dataclass
class Weapon:
    name: str
    thumbnail: str
    value: float
    demand: int
    stability: str


class ClickableFrame(QFrame):
    clicked = Signal()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class ImageLoadSignals(QObject):
    finished = Signal(str, QPixmap)


class ImageLoaderTask(QRunnable):
    def __init__(self, url):
        super().__init__()
        self.url = url
        self.signals = ImageLoadSignals()

    def run(self):
        pixmap = QPixmap()
        try:
            req = Request(self.url, headers={"User-Agent": "Mozilla/5.0"})
            with urlopen(req, timeout=8) as response:
                data = response.read()
            pixmap.loadFromData(data)
        except Exception:
            pass
        self.signals.finished.emit(self.url, pixmap)


class WeaponImageCache(QObject):
    image_loaded = Signal(str, QPixmap)

    def __init__(self):
        super().__init__()
        self.cache = {}
        self.pending = set()
        self.thread_pool = QThreadPool.globalInstance()
        self._placeholder_pixmap = self._build_placeholder()

    def placeholder(self):
        return self._placeholder_pixmap

    def _build_placeholder(self):
        pixmap = QPixmap(120, 120)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(QColor(PANEL_2))
        painter.setPen(QColor(BORDER))
        painter.drawRoundedRect(1, 1, 118, 118, 18, 18)
        painter.setPen(QColor(MUTED))
        painter.drawText(pixmap.rect(), Qt.AlignCenter, "Loading")
        painter.end()
        return pixmap

    def get(self, url):
        return self.cache.get(url)

    def request(self, url):
        if not url:
            return
        if url in self.cache or url in self.pending:
            return
        self.pending.add(url)
        task = ImageLoaderTask(url)
        task.signals.finished.connect(self._handle_loaded)
        self.thread_pool.start(task)

    def _handle_loaded(self, url, pixmap):
        self.pending.discard(url)
        if pixmap.isNull():
            pixmap = self._placeholder_pixmap
        self.cache[url] = pixmap
        self.image_loaded.emit(url, pixmap)


class TitleBar(QFrame):
    def __init__(self, window):
        super().__init__()
        self.window = window
        self.drag_pos = None
        self.setObjectName("titleBar")
        self.setFixedHeight(42)
        self._build_ui()

    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 6, 8, 6)
        layout.setSpacing(8)

        logo = QLabel()
        pixmap = QPixmap(resource_path("logo.png"))
        logo.setPixmap(pixmap.scaled(32, 32, Qt.KeepAspectRatio, Qt.SmoothTransformation))

        title = QLabel(APP_TITLE)
        title.setObjectName("titleBarText")

        minimize_btn = QPushButton("−")
        minimize_btn.setObjectName("titleButton")
        minimize_btn.setFixedSize(30, 26)
        minimize_btn.clicked.connect(self.window.showMinimized)

        close_btn = QPushButton("×")
        close_btn.setObjectName("titleCloseButton")
        close_btn.setFixedSize(30, 26)
        close_btn.clicked.connect(self.window.close)

        layout.addWidget(logo)
        layout.addWidget(title)
        layout.addStretch(1)
        layout.addWidget(minimize_btn)
        layout.addWidget(close_btn)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.drag_pos = event.globalPosition().toPoint() - self.window.frameGeometry().topLeft()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.drag_pos is not None and event.buttons() & Qt.LeftButton:
            self.window.move(event.globalPosition().toPoint() - self.drag_pos)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self.drag_pos = None
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        event.accept()


class WeaponListCard(ClickableFrame):
    def __init__(self, weapon, image_cache, on_click):
        super().__init__()
        self.weapon = weapon
        self.image_cache = image_cache
        self.on_click = on_click
        self.setObjectName("weaponListCard")
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(CARD_W, CARD_H)
        self._build_ui()
        self.clicked.connect(self.handle_click)
        self.image_cache.image_loaded.connect(self.on_image_loaded)
        self.load_image_async()

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(16)
        shadow.setOffset(0, 4)
        shadow.setColor(QColor(0, 0, 0, 80))
        self.setGraphicsEffect(shadow)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)

        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setFixedHeight(60)
        self.set_card_pixmap(self.image_cache.placeholder())

        self.name_label = QLabel(self.weapon.name)
        self.name_label.setWordWrap(True)
        self.name_label.setAlignment(Qt.AlignTop | Qt.AlignHCenter)
        self.name_label.setObjectName("weaponName")

        self.value_label = QLabel("V {}".format(format_value(self.weapon.value)))
        self.value_label.setObjectName("weaponMeta")
        self.value_label.setAlignment(Qt.AlignCenter)

        self.demand_label = QLabel("D {}".format(self.weapon.demand))
        self.demand_label.setObjectName("weaponMetaSoft")
        self.demand_label.setAlignment(Qt.AlignCenter)

        layout.addWidget(self.image_label)
        layout.addWidget(self.name_label)
        layout.addStretch(1)
        layout.addWidget(self.value_label)
        layout.addWidget(self.demand_label)

    def set_card_pixmap(self, pixmap):
        self.image_label.setPixmap(
            pixmap.scaled(50, 50, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        )

    def load_image_async(self):
        cached = self.image_cache.get(self.weapon.thumbnail)
        if cached is not None:
            self.set_card_pixmap(cached)
            return
        self.image_cache.request(self.weapon.thumbnail)

    def on_image_loaded(self, url, pixmap):
        if url == self.weapon.thumbnail:
            self.set_card_pixmap(pixmap)

    def handle_click(self):
        self.on_click(self.weapon)


class SelectedWeaponCard(QFrame):
    removed = Signal(str)

    def __init__(self, weapon, count, image_cache):
        super().__init__()
        self.weapon = weapon
        self.count = count
        self.image_cache = image_cache
        self.setObjectName("selectedWeaponCard")
        self.setFixedHeight(58)
        self._build_ui()
        self.image_cache.image_loaded.connect(self.on_image_loaded)
        self.load_image_async()

    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(7, 7, 7, 7)
        layout.setSpacing(7)

        self.thumb = QLabel()
        self.thumb.setFixedSize(34, 34)
        self.thumb.setAlignment(Qt.AlignCenter)
        self.set_card_pixmap(self.image_cache.placeholder(), 30)

        info_layout = QVBoxLayout()
        info_layout.setSpacing(0)

        title_row = QHBoxLayout()
        title_row.setSpacing(4)

        name = QLabel(self.weapon.name)
        name.setObjectName("selectedName")
        name.setWordWrap(True)

        badge = QLabel("x{}".format(self.count))
        badge.setObjectName("countBadge")
        badge.setVisible(self.count > 1)

        title_row.addWidget(name, 1)
        title_row.addWidget(badge, 0, Qt.AlignTop)

        meta = QLabel("{} each • D{} • Total {}".format(
            format_value(self.weapon.value), self.weapon.demand, format_value(self.weapon.value * self.count)
        ))
        meta.setObjectName("selectedMeta")

        info_layout.addLayout(title_row)
        info_layout.addWidget(meta)

        remove_btn = QPushButton("−")
        remove_btn.setObjectName("removeButton")
        remove_btn.setCursor(Qt.PointingHandCursor)
        remove_btn.setFixedSize(22, 22)
        remove_btn.clicked.connect(lambda: self.removed.emit(self.weapon.name))

        layout.addWidget(self.thumb)
        layout.addLayout(info_layout, 1)
        layout.addWidget(remove_btn, 0, Qt.AlignCenter)

    def set_card_pixmap(self, pixmap, size):
        self.thumb.setPixmap(
            pixmap.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        )

    def load_image_async(self):
        cached = self.image_cache.get(self.weapon.thumbnail)
        if cached is not None:
            self.set_card_pixmap(cached, 30)
            return
        self.image_cache.request(self.weapon.thumbnail)

    def on_image_loaded(self, url, pixmap):
        if url == self.weapon.thumbnail:
            self.set_card_pixmap(pixmap, 30)


class SidePanel(QFrame):
    remove_requested = Signal(str)

    def __init__(self, title, accent_border=False):
        super().__init__()
        self.title = title
        self.accent_border = accent_border
        self.setObjectName("sidePanelAccent" if accent_border else "sidePanel")
        self._build_ui()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(9, 9, 9, 9)
        outer.setSpacing(6)

        self.title_label = QLabel(self.title)
        self.title_label.setObjectName("panelTitle")

        self.total_label = QLabel("Total: 0")
        self.total_label.setObjectName("panelTotal")

        title_wrap = QHBoxLayout()
        title_wrap.addWidget(self.title_label)
        title_wrap.addStretch(1)
        title_wrap.addWidget(self.total_label)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setFrameShape(QFrame.NoFrame)

        self.content = QWidget()
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(5)
        self.content_layout.addStretch(1)
        self.scroll.setWidget(self.content)

        outer.addLayout(title_wrap)
        outer.addWidget(self.scroll, 1)

    def set_total(self, value):
        self.total_label.setText("Total: {}".format(format_value(value)))

    def clear_cards(self):
        while self.content_layout.count():
            item = self.content_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self.content_layout.addStretch(1)

    def populate(self, weapons, counter, image_cache):
        self.clear_cards()
        if not counter:
            empty = QLabel("No weapons added yet")
            empty.setObjectName("emptyState")
            empty.setAlignment(Qt.AlignCenter)
            self.content_layout.insertWidget(0, empty)
            return

        sorted_weapons = sorted(
            [w for w in weapons if counter.get(w.name, 0) > 0],
            key=lambda w: (w.value, w.demand, w.name.lower()),
            reverse=True,
        )

        for weapon in sorted_weapons:
            card = SelectedWeaponCard(weapon, counter[weapon.name], image_cache)
            card.removed.connect(self.remove_requested.emit)
            self.content_layout.insertWidget(self.content_layout.count() - 1, card)


class WinTradeWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setFixedSize(WINDOW_W, WINDOW_H)

        self.image_cache = WeaponImageCache()
        self.weapons = self.load_weapons()
        self.weapon_lookup = {weapon.name: weapon for weapon in self.weapons}
        self.filtered_weapons = list(self.weapons)
        self.rendered_count = 0
        self.browser_spacer = None
        self.search_timer = QTimer(self)
        self.search_timer.setSingleShot(True)
        self.search_timer.setInterval(160)
        self.search_timer.timeout.connect(self.apply_search)

        self.your_counter = Counter()
        self.other_counter = Counter()
        self.selected_side = "your"

        self._build_ui()
        self._apply_styles()
        QTimer.singleShot(0, self.refresh_weapon_grid)
        self.refresh_trade_view()

    def load_weapons(self):
        if not os.path.exists(JSON_FILE):
            QMessageBox.critical(
                None,
                APP_TITLE,
                "Could not find '{}' in the same folder as this script.".format(JSON_FILE),
            )
            raise FileNotFoundError(JSON_FILE)

        with open(JSON_FILE, "r", encoding="utf-8") as file:
            raw_items = json.load(file)

        weapons = []
        for item in raw_items:
            weapons.append(
                Weapon(
                    name=str(item.get("itemName", "Unknown")),
                    thumbnail=str(item.get("thumbnail", "")),
                    value=float(item.get("value", 0) or 0),
                    demand=int(item.get("demand", 0) or 0),
                    stability=str(item.get("stability", "Unknown")),
                )
            )
        weapons.sort(key=lambda w: (w.value, w.demand, w.name.lower()), reverse=True)
        return weapons

    def _build_ui(self):
        outer = QWidget()
        self.setCentralWidget(outer)
        outer_layout = QVBoxLayout(outer)
        outer_layout.setContentsMargins(12, 12, 12, 12)
        outer_layout.setSpacing(0)

        shell = QFrame()
        shell.setObjectName("windowShell")
        shell_layout = QVBoxLayout(shell)
        shell_layout.setContentsMargins(0, 0, 0, 0)
        shell_layout.setSpacing(0)

        self.title_bar = TitleBar(self)
        shell_layout.addWidget(self.title_bar)

        content = QWidget()
        content_layout = QHBoxLayout(content)
        content_layout.setContentsMargins(10, 10, 10, 10)
        content_layout.setSpacing(10)

        left_side = QFrame()
        left_side.setObjectName("mainColumn")
        left_layout = QVBoxLayout(left_side)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(8)

        left_layout.addWidget(self.build_header())
        left_layout.addWidget(self.build_calculator_section(), 1)

        right_side = self.build_weapon_browser()
        right_side.setFixedWidth(272)

        content_layout.addWidget(left_side, 1)
        content_layout.addWidget(right_side, 0)

        shell_layout.addWidget(content, 1)
        outer_layout.addWidget(shell)

    def build_header(self):
        frame = QFrame()
        frame.setObjectName("headerFrame")
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(10)

        logo = QLabel()
        pixmap = QPixmap(resource_path("logo.png"))
        logo.setPixmap(pixmap.scaled(32, 32, Qt.KeepAspectRatio, Qt.SmoothTransformation))

        title_col = QVBoxLayout()
        title_col.setSpacing(2)

        title = QLabel(APP_TITLE)
        title.setObjectName("appTitle")
        subtitle = QLabel("Compact MM2 value checker")
        subtitle.setObjectName("appSubtitle")

        title_col.addWidget(title)
        title_col.addWidget(subtitle)

        self.side_indicator = QLabel("Adding to: Your Side")
        self.side_indicator.setObjectName("sideIndicator")
        self.side_indicator.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        layout.addWidget(logo)
        layout.addLayout(title_col, 1)
        layout.addWidget(self.side_indicator, 0, Qt.AlignRight | Qt.AlignVCenter)
        return frame

    def build_calculator_section(self):
        frame = QFrame()
        frame.setObjectName("calculatorFrame")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        selector_row = QFrame()
        selector_row.setObjectName("selectorFrame")
        selector_layout = QHBoxLayout(selector_row)
        selector_layout.setContentsMargins(8, 6, 8, 6)

        selector_label = QLabel("Selected side")
        selector_label.setObjectName("selectorLabel")

        self.your_radio = QRadioButton("Your Side")
        self.other_radio = QRadioButton("Other Side")
        self.your_radio.setChecked(True)
        self.your_radio.toggled.connect(self.on_side_changed)
        self.other_radio.toggled.connect(self.on_side_changed)

        group = QButtonGroup(self)
        group.addButton(self.your_radio)
        group.addButton(self.other_radio)

        selector_layout.addWidget(selector_label)
        selector_layout.addStretch(1)
        selector_layout.addWidget(self.your_radio)
        selector_layout.addWidget(self.other_radio)

        panels_row = QHBoxLayout()
        panels_row.setSpacing(8)

        self.your_panel = SidePanel("Your Side", accent_border=True)
        self.other_panel = SidePanel("Other Side")
        self.your_panel.setMaximumHeight(220)
        self.other_panel.setMaximumHeight(220)
        self.your_panel.remove_requested.connect(self.remove_from_your_side)
        self.other_panel.remove_requested.connect(self.remove_from_other_side)

        panels_row.addWidget(self.your_panel, 1)
        panels_row.addWidget(self.other_panel, 1)

        result_frame = QFrame()
        result_frame.setObjectName("resultFrame")
        result_layout = QVBoxLayout(result_frame)
        result_layout.setContentsMargins(10, 10, 10, 10)
        result_layout.setSpacing(8)

        top_row = QHBoxLayout()
        top_row.setSpacing(8)

        self.result_status = QLabel("Fair")
        self.result_status.setObjectName("resultStatusNeutral")

        stats_col = QVBoxLayout()
        stats_col.setSpacing(3)
        self.result_totals = QLabel("Your Total: 0   •   Other Total: 0")
        self.result_totals.setObjectName("resultText")
        self.result_delta = QLabel("Difference: 0")
        self.result_delta.setObjectName("resultText")
        self.result_percent = QLabel("Raw difference: 0.00%")
        self.result_percent.setObjectName("resultText")
        stats_col.addWidget(self.result_totals)
        stats_col.addWidget(self.result_delta)
        stats_col.addWidget(self.result_percent)

        top_row.addWidget(self.result_status, 0, Qt.AlignTop)
        top_row.addLayout(stats_col, 1)

        self.result_reason = QLabel("Smart explanation: add items to compare")
        self.result_reason.setObjectName("smartExplanation")
        self.result_reason.setWordWrap(True)
        self.result_reason.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.result_reason.setMinimumHeight(74)

        buttons_col = QHBoxLayout()
        buttons_col.setSpacing(6)
        clear_your_btn = QPushButton("Clear Your Side")
        clear_other_btn = QPushButton("Clear Other Side")
        clear_all_btn = QPushButton("Clear All")
        clear_your_btn.clicked.connect(self.clear_your_side)
        clear_other_btn.clicked.connect(self.clear_other_side)
        clear_all_btn.clicked.connect(self.clear_all)
        buttons_col.addWidget(clear_your_btn)
        buttons_col.addWidget(clear_other_btn)
        buttons_col.addWidget(clear_all_btn)

        result_layout.addLayout(top_row)
        result_layout.addWidget(self.result_reason)
        result_layout.addLayout(buttons_col)

        layout.addWidget(selector_row)
        layout.addLayout(panels_row, 1)
        layout.addWidget(result_frame)
        return frame

    def build_weapon_browser(self):
        frame = QFrame()
        frame.setObjectName("browserFrame")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        title = QLabel("Weapons")
        title.setObjectName("browserTitle")

        self.search = QLineEdit()
        self.search.setPlaceholderText("Search weapons...")
        self.search.textChanged.connect(self.on_search_changed)

        self.weapon_count_label = QLabel("")
        self.weapon_count_label.setObjectName("weaponCount")

        self.browser_scroll = QScrollArea()
        self.browser_scroll.setWidgetResizable(True)
        self.browser_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.browser_scroll.setFrameShape(QFrame.NoFrame)

        self.browser_content = QWidget()
        self.browser_grid = QGridLayout(self.browser_content)
        self.browser_grid.setContentsMargins(0, 0, 0, 0)
        self.browser_grid.setSpacing(8)
        self.browser_grid.setAlignment(Qt.AlignTop)
        self.browser_scroll.setWidget(self.browser_content)
        self.browser_scroll.verticalScrollBar().valueChanged.connect(self.on_browser_scrolled)

        layout.addWidget(title)
        layout.addWidget(self.search)
        layout.addWidget(self.weapon_count_label)
        layout.addWidget(self.browser_scroll, 1)
        return frame

    def on_side_changed(self):
        self.selected_side = "your" if self.your_radio.isChecked() else "other"
        self.side_indicator.setText(
            "Adding to: Your Side" if self.selected_side == "your" else "Adding to: Other Side"
        )
        self.your_panel.setObjectName("sidePanelAccent" if self.selected_side == "your" else "sidePanel")
        self.other_panel.setObjectName("sidePanelAccent" if self.selected_side == "other" else "sidePanel")
        self.repolish(self.your_panel)
        self.repolish(self.other_panel)

    def repolish(self, widget):
        widget.style().unpolish(widget)
        widget.style().polish(widget)
        widget.update()

    def on_search_changed(self, _text):
        self.search_timer.start()

    def apply_search(self):
        search_text = self.search.text().strip().lower()
        if not search_text:
            self.filtered_weapons = list(self.weapons)
        else:
            self.filtered_weapons = [
                weapon for weapon in self.weapons
                if search_text in weapon.name.lower()
            ]
        self.refresh_weapon_grid(reset=True)

    def clear_browser_grid(self):
        self.browser_spacer = None
        while self.browser_grid.count():
            item = self.browser_grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def refresh_weapon_grid(self, reset=True):
        if reset:
            self.rendered_count = 0
            self.clear_browser_grid()

        if not self.filtered_weapons:
            empty = QLabel("No weapons found")
            empty.setObjectName("emptyState")
            empty.setMinimumHeight(220)
            empty.setAlignment(Qt.AlignCenter)
            self.browser_grid.addWidget(empty, 0, 0, 1, BROWSER_COLUMNS)
            self.weapon_count_label.setText("0 weapons")
            return

        target = INITIAL_BATCH if self.rendered_count == 0 else self.rendered_count + LOAD_MORE_BATCH
        target = min(target, len(self.filtered_weapons))

        for index in range(self.rendered_count, target):
            weapon = self.filtered_weapons[index]
            row = index // BROWSER_COLUMNS
            col = index % BROWSER_COLUMNS
            card = WeaponListCard(weapon, self.image_cache, self.add_weapon_to_selected_side)
            self.browser_grid.addWidget(card, row, col)

        self.rendered_count = target
        self.weapon_count_label.setText("{} weapons".format(len(self.filtered_weapons)))

        if self.browser_spacer is not None:
            self.browser_grid.removeItem(self.browser_spacer)

        self.browser_spacer = QSpacerItem(20, 20, QSizePolicy.Minimum, QSizePolicy.Expanding)
        self.browser_grid.addItem(
            self.browser_spacer,
            (max(self.rendered_count - 1, 0) // BROWSER_COLUMNS) + 1,
            0,
            1,
            BROWSER_COLUMNS,
        )

    def on_browser_scrolled(self, value):
        bar = self.browser_scroll.verticalScrollBar()
        if value >= bar.maximum() - 220 and self.rendered_count < len(self.filtered_weapons):
            self.refresh_weapon_grid(reset=False)

    def add_weapon_to_selected_side(self, weapon):
        counter = self.your_counter if self.selected_side == "your" else self.other_counter

        if weapon.name not in counter and len(counter) >= MAX_UNIQUE_ITEMS_PER_SIDE:
            QMessageBox.information(
                self,
                APP_TITLE,
                "MM2 only allows 4 different items per side. You can still stack an item you already added.",
            )
            return

        counter[weapon.name] += 1
        self.refresh_trade_view()
        self.pulse_result_box()

    def pulse_result_box(self):
        effect = QGraphicsOpacityEffect(self.result_status)
        self.result_status.setGraphicsEffect(effect)
        animation = QPropertyAnimation(effect, b"opacity", self)
        animation.setDuration(180)
        animation.setStartValue(0.5)
        animation.setEndValue(1.0)
        animation.setEasingCurve(QEasingCurve.OutCubic)
        animation.start()
        self._pulse_animation = animation

    def remove_from_your_side(self, name):
        if self.your_counter.get(name, 0) > 0:
            self.your_counter[name] -= 1
            if self.your_counter[name] <= 0:
                del self.your_counter[name]
        self.refresh_trade_view()

    def remove_from_other_side(self, name):
        if self.other_counter.get(name, 0) > 0:
            self.other_counter[name] -= 1
            if self.other_counter[name] <= 0:
                del self.other_counter[name]
        self.refresh_trade_view()

    def clear_your_side(self):
        self.your_counter.clear()
        self.refresh_trade_view()

    def clear_other_side(self):
        self.other_counter.clear()
        self.refresh_trade_view()

    def clear_all(self):
        self.your_counter.clear()
        self.other_counter.clear()
        self.refresh_trade_view()

    def compute_trade_stats(self, counter):
        total_value = 0.0
        total_demand = 0.0
        total_stability = 0.0
        item_count = 0

        for name, count in counter.items():
            weapon = self.weapon_lookup.get(name)
            if not weapon:
                continue
            total_value += weapon.value * count
            total_demand += weapon.demand * count
            total_stability += stability_score(weapon.stability) * count
            item_count += count

        avg_demand = (total_demand / item_count) if item_count else 0.0
        avg_stability = (total_stability / item_count) if item_count else 0.0
        weighted_score = total_value * (1 + (avg_demand * 0.015) + (avg_stability * 0.03))
        return {
            "value": total_value,
            "avg_demand": avg_demand,
            "avg_stability": avg_stability,
            "item_count": item_count,
            "weighted_score": weighted_score,
        }

    def determine_trade_result(self, your_stats, other_stats):
        your_value = your_stats["value"]
        other_value = other_stats["value"]
        raw_diff = other_value - your_value

        your_score = your_stats["weighted_score"]
        other_score = other_stats["weighted_score"]
        score_diff = other_score - your_score

        if not (your_value or other_value):
            return {
                "status": "Fair",
                "object_name": "resultStatusNeutral",
                "delta_text": "Difference: 0",
                "reason": "Smart explanation: add items to compare so the app can judge value, demand, and stability.",
                "score_diff": 0.0,
            }

        baseline = max(your_score, other_score, 1.0)
        score_percent = (score_diff / baseline) * 100.0

        raw_bias = abs(raw_diff) / max(max(your_value, other_value, 1.0), 1.0)
        demand_bias = other_stats["avg_demand"] - your_stats["avg_demand"]
        stability_bias = other_stats["avg_stability"] - your_stats["avg_stability"]

        if score_percent >= 4.5:
            status = "You Win"
            object_name = "resultStatusWin"
            delta_text = "You gain: {}".format(format_value(raw_diff if raw_diff > 0 else 0))
        elif score_percent <= -4.5:
            status = "You Lose"
            object_name = "resultStatusLose"
            delta_text = "You lose: {}".format(format_value(abs(raw_diff) if raw_diff < 0 else 0))
        else:
            status = "Fair"
            object_name = "resultStatusNeutral"
            delta_text = "Difference: {}".format(format_value(abs(raw_diff)))

        reasons = []
        if raw_bias > 0.02:
            if raw_diff > 0:
                reasons.append("The raw value is higher on the other side, so this trade pays you more.")
            elif raw_diff < 0:
                reasons.append("The raw value is higher on your side, so you are paying more here.")
        if abs(demand_bias) >= 0.35:
            if demand_bias > 0:
                reasons.append("The other side has stronger demand, which makes those items easier to move.")
            else:
                reasons.append("Your side has stronger demand, so their offer may look good but be weaker in trading speed.")
        if abs(stability_bias) >= 0.35:
            if stability_bias > 0:
                reasons.append("The other side is more stable, so it carries less drop risk.")
            else:
                reasons.append("Your side is more stable, which means you would be giving up safer items.")
        if not reasons:
            reasons.append("Both sides are very close in value, demand, and stability, so this looks balanced.")

        return {
            "status": status,
            "object_name": object_name,
            "delta_text": delta_text,
            "reason": "Smart explanation: " + " ".join(reasons),
            "score_diff": score_diff,
        }

    def refresh_trade_view(self):
        your_stats = self.compute_trade_stats(self.your_counter)
        other_stats = self.compute_trade_stats(self.other_counter)
        your_total = your_stats["value"]
        other_total = other_stats["value"]
        diff = other_total - your_total
        result = self.determine_trade_result(your_stats, other_stats)

        self.your_panel.title_label.setText("Your Side ({}/4)".format(len(self.your_counter)))
        self.other_panel.title_label.setText("Other Side ({}/4)".format(len(self.other_counter)))
        self.your_panel.set_total(your_total)
        self.other_panel.set_total(other_total)
        self.your_panel.populate(self.weapons, self.your_counter, self.image_cache)
        self.other_panel.populate(self.weapons, self.other_counter, self.image_cache)

        self.result_totals.setText(
            "Your Total: {}   •   Other Total: {}".format(
                format_value(your_total), format_value(other_total)
            )
        )

        self.result_status.setText(result["status"])
        self.result_status.setObjectName(result["object_name"])
        self.result_delta.setText(result["delta_text"])

        base = max(your_total, other_total, 1) if (your_total or other_total) else 1
        percent = (diff / base) * 100.0 if (your_total or other_total) else 0.0
        sign = "+" if percent > 0 else ""
        self.result_percent.setText("Raw difference: {}{:.2f}%".format(sign, percent))

        smart_base = max(your_stats["weighted_score"], other_stats["weighted_score"], 1.0)
        smart_percent = (result["score_diff"] / smart_base) * 100.0 if smart_base else 0.0
        smart_sign = "+" if smart_percent > 0 else ""
        explanation = "{}\nSmart edge: {}{:.2f}%".format(result["reason"], smart_sign, smart_percent)
        self.result_reason.setText(explanation)
        self.repolish(self.result_status)

    def _apply_styles(self):
        self.setStyleSheet(f"""
            QMainWindow, QWidget {{
                background: transparent;
                color: {TEXT};
                font-family: Segoe UI, Arial, sans-serif;
                font-size: 11px;
            }}

            QLabel {{
                background: transparent;
                border: none;
            }}

            QFrame#windowShell {{
                background: {BG};
                border: 1px solid #261c40;
                border-radius: 16px;
            }}

            QFrame#titleBar {{
                background: #120d20;
                border-bottom: 1px solid {BORDER};
                border-top-left-radius: 16px;
                border-top-right-radius: 16px;
            }}

            QLabel#titleBarText {{
                color: {TEXT};
                font-size: 12px;
                font-weight: 700;
            }}

            QFrame#headerFrame,
            QFrame#calculatorFrame,
            QFrame#browserFrame,
            QFrame#resultFrame,
            QFrame#selectorFrame {{
                background: {PANEL};
                border: 1px solid {BORDER};
                border-radius: 10px;
            }}

            QFrame#sidePanel,
            QFrame#sidePanelAccent {{
                background: {PANEL_2};
                border-radius: 10px;
                border: 1px solid {BORDER};
            }}

            QFrame#sidePanelAccent {{
                border: 2px solid {PURPLE};
            }}

            QLabel#appTitle {{
                font-size: 24px;
                font-weight: 900;
                color: {TEXT};
                background: transparent;
            }}

            QLabel#appSubtitle,
            QLabel#selectorLabel,
            QLabel#weaponCount,
            QLabel#weaponMetaSoft,
            QLabel#selectedMeta,
            QLabel#emptyState,
            QLabel#resultText {{
                color: {MUTED};
                background: transparent;
                border: none;
            }}

            QLabel#appSubtitle {{
                font-size: 11px;
            }}

            QLabel#sideIndicator {{
                color: {PURPLE_HOVER};
                background: transparent;
                font-weight: 800;
                font-size: 12px;
                border: none;
                padding: 2px;
            }}

            QLabel#panelTitle,
            QLabel#browserTitle,
            QLabel#selectedName,
            QLabel#weaponName {{
                color: {TEXT};
                font-weight: 700;
                background: transparent;
                border: none;
            }}

            QLabel#browserTitle {{
                font-size: 13px;
            }}

            QLabel#weaponName {{
                font-size: 10px;
            }}

            QLabel#panelTotal,
            QLabel#weaponMeta {{
                color: {PURPLE_HOVER};
                font-weight: 800;
                background: transparent;
                border: none;
            }}

            QLabel#countBadge {{
                background: {PURPLE};
                color: white;
                font-weight: 800;
                border-radius: 8px;
                padding: 1px 5px;
            }}

            QLabel#resultStatusWin,
            QLabel#resultStatusLose,
            QLabel#resultStatusNeutral {{
                font-size: 22px;
                font-weight: 900;
                background: transparent;
                border: none;
                padding: 0;
                min-width: 96px;
            }}

            QLabel#resultStatusWin {{ color: {GREEN}; }}
            QLabel#resultStatusLose {{ color: {RED}; }}
            QLabel#resultStatusNeutral {{ color: {YELLOW}; }}

            QLabel#smartExplanation {{
                color: {TEXT};
                background: #120C22;
                border: 1px solid {BORDER};
                border-radius: 10px;
                padding: 10px;
                font-size: 13px;
                font-weight: 600;
                line-height: 1.3;
            }}

            QRadioButton {{
                color: {TEXT};
                font-weight: 700;
                background: transparent;
                border: none;
            }}

            QRadioButton::indicator {{
                width: 14px;
                height: 14px;
                border-radius: 7px;
                border: 2px solid {PURPLE};
                background: {BG_ALT};
            }}

            QRadioButton::indicator:checked {{
                background: {PURPLE};
            }}

            QLineEdit {{
                background: {BG_ALT};
                border: 1px solid {BORDER};
                border-radius: 10px;
                padding: 8px;
                color: {TEXT};
            }}

            QLineEdit:focus {{
                border: 1px solid {PURPLE};
            }}

            QFrame#weaponListCard {{
                background: {PANEL_2};
                border: 1px solid {BORDER};
                border-radius: 10px;
            }}

            QFrame#weaponListCard:hover {{
                border: 1px solid {PURPLE};
                background: #241c3d;
            }}

            QFrame#selectedWeaponCard {{
                background: #120C22;
                border: 1px solid {BORDER};
                border-radius: 12px;
            }}

            QPushButton {{
                background: {PURPLE};
                color: white;
                border: none;
                border-radius: 10px;
                padding: 6px 8px;
                font-weight: 700;
            }}

            QPushButton:hover {{
                background: {PURPLE_HOVER};
            }}

            QPushButton#titleButton,
            QPushButton#titleCloseButton {{
                background: transparent;
                color: {TEXT};
                border-radius: 8px;
                font-size: 14px;
                font-weight: 800;
                padding: 0;
            }}

            QPushButton#titleButton:hover {{
                background: rgba(255,255,255,0.08);
            }}

            QPushButton#titleCloseButton:hover {{
                background: rgba(249,112,102,0.22);
                color: {RED};
            }}

            QPushButton#removeButton {{
                background: rgba(155, 92, 255, 0.18);
                color: {TEXT};
                border: none;
                font-size: 13px;
                padding: 0;
            }}

            QPushButton#removeButton:hover {{
                background: rgba(155, 92, 255, 0.30);
            }}

            QScrollArea {{
                border: none;
                background: transparent;
            }}

            QScrollBar:vertical {{
                background: {BG_ALT};
                width: 8px;
                border-radius: 4px;
                margin: 2px;
            }}

            QScrollBar::handle:vertical {{
                background: {PURPLE};
                min-height: 18px;
                border-radius: 4px;
            }}

            QScrollBar::handle:vertical:hover {{
                background: {PURPLE_HOVER};
            }}

            QScrollBar::sub-line:vertical,
            QScrollBar::add-line:vertical,
            QScrollBar::up-arrow:vertical,
            QScrollBar::down-arrow:vertical,
            QScrollBar::sub-page:vertical,
            QScrollBar::add-page:vertical {{
                background: none;
                height: 0px;
            }}
        """)

def stability_score(stability):
    normalized = str(stability).strip().lower()
    mapping = {
        "very stable": 2.0,
        "stable": 1.2,
        "decent": 0.5,
        "average": 0.0,
        "unknown": 0.0,
        "changing": -0.4,
        "unstable": -1.0,
        "very unstable": -1.8,
        "dropping": -1.6,
        "rising": 0.8,
        "overpaid": -0.2,
    }
    return mapping.get(normalized, 0.0)


def format_value(value):
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    if isinstance(value, (int, float)):
        if isinstance(value, float) and not float(value).is_integer():
            return "{:,.1f}".format(value)
        return "{:,.0f}".format(value)
    return str(value)

def main():
    app = QApplication(sys.argv)
    app.setApplicationName(APP_TITLE)
    window = WinTradeWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
