import json
import os
import sys
from dataclasses import dataclass
from collections import Counter
from urllib.request import Request, urlopen

from PySide6.QtCore import (
    QEasingCurve,
    QObject,
    QRunnable,
    QThreadPool,
    QTimer,
    Qt,
    Signal,
    QPropertyAnimation,
)
from PySide6.QtGui import QColor, QPainter, QPixmap
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

APP_TITLE = "WinTrade MM2"
JSON_FILE = "supreme_values_mm2.json"
CARD_W = 170
CARD_H = 215
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
INITIAL_BATCH = 36
LOAD_MORE_BATCH = 24


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
        shadow.setBlurRadius(28)
        shadow.setOffset(0, 8)
        shadow.setColor(QColor(0, 0, 0, 100))
        self.setGraphicsEffect(shadow)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setFixedHeight(104)
        self.set_card_pixmap(self.image_cache.placeholder())

        self.name_label = QLabel(self.weapon.name)
        self.name_label.setWordWrap(True)
        self.name_label.setAlignment(Qt.AlignTop | Qt.AlignHCenter)
        self.name_label.setObjectName("weaponName")

        self.value_label = QLabel("Value: {}".format(format_value(self.weapon.value)))
        self.value_label.setObjectName("weaponMeta")
        self.value_label.setAlignment(Qt.AlignCenter)

        self.stability_label = QLabel(self.weapon.stability)
        self.stability_label.setObjectName("weaponMetaSoft")
        self.stability_label.setAlignment(Qt.AlignCenter)

        layout.addWidget(self.image_label)
        layout.addWidget(self.name_label)
        layout.addStretch(1)
        layout.addWidget(self.value_label)
        layout.addWidget(self.stability_label)

    def set_card_pixmap(self, pixmap):
        self.image_label.setPixmap(
            pixmap.scaled(92, 92, Qt.KeepAspectRatio, Qt.SmoothTransformation)
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
        self.setMinimumHeight(88)
        self.setMaximumHeight(88)
        self._build_ui()
        self.image_cache.image_loaded.connect(self.on_image_loaded)
        self.load_image_async()

    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        self.thumb = QLabel()
        self.thumb.setFixedSize(52, 52)
        self.thumb.setAlignment(Qt.AlignCenter)
        self.set_card_pixmap(self.image_cache.placeholder(), 48)

        info_layout = QVBoxLayout()
        info_layout.setSpacing(2)

        title_row = QHBoxLayout()
        title_row.setSpacing(6)

        name = QLabel(self.weapon.name)
        name.setObjectName("selectedName")
        name.setWordWrap(True)

        badge = QLabel("x{}".format(self.count))
        badge.setObjectName("countBadge")
        badge.setVisible(self.count > 1)

        title_row.addWidget(name, 1)
        title_row.addWidget(badge, 0, Qt.AlignTop)

        value = QLabel("{} each".format(format_value(self.weapon.value)))
        value.setObjectName("selectedMeta")

        total = QLabel("Total: {}".format(format_value(self.weapon.value * self.count)))
        total.setObjectName("selectedMeta")

        info_layout.addLayout(title_row)
        info_layout.addWidget(value)
        info_layout.addWidget(total)

        remove_btn = QPushButton("−")
        remove_btn.setObjectName("removeButton")
        remove_btn.setCursor(Qt.PointingHandCursor)
        remove_btn.setFixedSize(32, 32)
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
            self.set_card_pixmap(cached, 48)
            return
        self.image_cache.request(self.weapon.thumbnail)

    def on_image_loaded(self, url, pixmap):
        if url == self.weapon.thumbnail:
            self.set_card_pixmap(pixmap, 48)


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
        outer.setContentsMargins(16, 16, 16, 16)
        outer.setSpacing(12)

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
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setFrameShape(QFrame.NoFrame)

        self.content = QWidget()
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(10)
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
            key=lambda w: (w.value, w.name.lower()),
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
        self.resize(1560, 920)
        self.setMinimumSize(1280, 760)

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
        weapons.sort(key=lambda w: (w.value, w.name.lower()), reverse=True)
        return weapons

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)

        root = QHBoxLayout(central)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(18)

        left_side = QFrame()
        left_layout = QVBoxLayout(left_side)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(16)

        left_layout.addWidget(self.build_header())
        left_layout.addWidget(self.build_calculator_section(), 1)

        right_side = self.build_weapon_browser()
        right_side.setFixedWidth(560)

        root.addWidget(left_side, 1)
        root.addWidget(right_side, 0)

    def build_header(self):
        frame = QFrame()
        frame.setObjectName("headerFrame")
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(22, 18, 22, 18)

        title_col = QVBoxLayout()
        title_col.setSpacing(4)

        title = QLabel(APP_TITLE)
        title.setObjectName("appTitle")
        subtitle = QLabel("Fast MM2 trade calculator")
        subtitle.setObjectName("appSubtitle")

        title_col.addWidget(title)
        title_col.addWidget(subtitle)

        self.side_indicator = QLabel("Adding to: Your Side")
        self.side_indicator.setObjectName("sideIndicator")

        layout.addLayout(title_col)
        layout.addStretch(1)
        layout.addWidget(self.side_indicator)
        return frame

    def build_calculator_section(self):
        frame = QFrame()
        frame.setObjectName("calculatorFrame")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(14)

        selector_row = QFrame()
        selector_row.setObjectName("selectorFrame")
        selector_layout = QHBoxLayout(selector_row)
        selector_layout.setContentsMargins(12, 12, 12, 12)

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
        panels_row.setSpacing(14)

        self.your_panel = SidePanel("Your Side", accent_border=True)
        self.other_panel = SidePanel("Other Side")
        self.your_panel.remove_requested.connect(self.remove_from_your_side)
        self.other_panel.remove_requested.connect(self.remove_from_other_side)

        panels_row.addWidget(self.your_panel, 1)
        panels_row.addWidget(self.other_panel, 1)

        result_frame = QFrame()
        result_frame.setObjectName("resultFrame")
        result_layout = QHBoxLayout(result_frame)
        result_layout.setContentsMargins(16, 16, 16, 16)
        result_layout.setSpacing(14)

        self.result_status = QLabel("Fair")
        self.result_status.setObjectName("resultStatusNeutral")

        details_col = QVBoxLayout()
        details_col.setSpacing(6)
        self.result_totals = QLabel("Your Total: 0   •   Other Total: 0")
        self.result_totals.setObjectName("resultText")
        self.result_delta = QLabel("Difference: 0")
        self.result_delta.setObjectName("resultText")
        self.result_percent = QLabel("Difference: 0.00%")
        self.result_percent.setObjectName("resultText")
        details_col.addWidget(self.result_totals)
        details_col.addWidget(self.result_delta)
        details_col.addWidget(self.result_percent)

        buttons_col = QHBoxLayout()
        clear_your_btn = QPushButton("Clear Your Side")
        clear_other_btn = QPushButton("Clear Other Side")
        clear_all_btn = QPushButton("Clear All")
        clear_your_btn.clicked.connect(self.clear_your_side)
        clear_other_btn.clicked.connect(self.clear_other_side)
        clear_all_btn.clicked.connect(self.clear_all)
        buttons_col.addWidget(clear_your_btn)
        buttons_col.addWidget(clear_other_btn)
        buttons_col.addWidget(clear_all_btn)

        result_layout.addWidget(self.result_status)
        result_layout.addLayout(details_col, 1)
        result_layout.addLayout(buttons_col)

        layout.addWidget(selector_row)
        layout.addLayout(panels_row, 1)
        layout.addWidget(result_frame)
        return frame

    def build_weapon_browser(self):
        frame = QFrame()
        frame.setObjectName("browserFrame")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(14)

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
        self.browser_grid.setSpacing(16)
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
                if search_text in weapon.name.lower() or search_text in weapon.stability.lower()
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
            empty.setMinimumHeight(200)
            empty.setAlignment(Qt.AlignCenter)
            self.browser_grid.addWidget(empty, 0, 0)
            self.weapon_count_label.setText("0 weapons")
            return

        target = INITIAL_BATCH if self.rendered_count == 0 else self.rendered_count + LOAD_MORE_BATCH
        target = min(target, len(self.filtered_weapons))
        columns = 3

        for index in range(self.rendered_count, target):
            weapon = self.filtered_weapons[index]
            row = index // columns
            col = index % columns
            card = WeaponListCard(weapon, self.image_cache, self.add_weapon_to_selected_side)
            self.browser_grid.addWidget(card, row, col)

        self.rendered_count = target
        self.weapon_count_label.setText("{} weapons".format(len(self.filtered_weapons)))

        if self.browser_spacer is not None:
            self.browser_grid.removeItem(self.browser_spacer)

        self.browser_spacer = QSpacerItem(20, 20, QSizePolicy.Minimum, QSizePolicy.Expanding)
        self.browser_grid.addItem(
            self.browser_spacer,
            (max(self.rendered_count - 1, 0) // columns) + 1,
            0,
            1,
            columns,
        )

    def on_browser_scrolled(self, value):
        bar = self.browser_scroll.verticalScrollBar()
        if value >= bar.maximum() - 250 and self.rendered_count < len(self.filtered_weapons):
            self.refresh_weapon_grid(reset=False)

    def add_weapon_to_selected_side(self, weapon):
        if self.selected_side == "your":
            self.your_counter[weapon.name] += 1
        else:
            self.other_counter[weapon.name] += 1
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

    def compute_total(self, counter):
        total = 0
        for name, count in counter.items():
            weapon = self.weapon_lookup.get(name)
            if weapon:
                total += weapon.value * count
        return total

    def refresh_trade_view(self):
        your_total = self.compute_total(self.your_counter)
        other_total = self.compute_total(self.other_counter)
        diff = other_total - your_total

        self.your_panel.set_total(your_total)
        self.other_panel.set_total(other_total)
        self.your_panel.populate(self.weapons, self.your_counter, self.image_cache)
        self.other_panel.populate(self.weapons, self.other_counter, self.image_cache)

        self.result_totals.setText(
            "Your Total: {}   •   Other Total: {}".format(
                format_value(your_total), format_value(other_total)
            )
        )

        if diff > 0:
            self.result_status.setText("You Win")
            self.result_status.setObjectName("resultStatusWin")
            self.result_delta.setText("You gain: {}".format(format_value(diff)))
        elif diff < 0:
            self.result_status.setText("You Lose")
            self.result_status.setObjectName("resultStatusLose")
            self.result_delta.setText("You lose: {}".format(format_value(abs(diff))))
        else:
            self.result_status.setText("Fair")
            self.result_status.setObjectName("resultStatusNeutral")
            self.result_delta.setText("Difference: 0")

        base = max(your_total, 1) if (your_total or other_total) else 1
        percent = (diff / base) * 100.0 if (your_total or other_total) else 0.0
        sign = "+" if percent > 0 else ""
        self.result_percent.setText("Difference: {}{:.2f}%".format(sign, percent))
        self.repolish(self.result_status)

    def _apply_styles(self):
        self.setStyleSheet(f"""
            QMainWindow, QWidget {{
                background: {BG};
                color: {TEXT};
                font-family: Segoe UI, Arial, sans-serif;
                font-size: 14px;
            }}

            QLabel {{
                background: transparent;
                border: none;
            }}

            QFrame#headerFrame,
            QFrame#calculatorFrame,
            QFrame#browserFrame,
            QFrame#resultFrame,
            QFrame#selectorFrame {{
                background: {PANEL};
                border: 1px solid {BORDER};
                border-radius: 22px;
            }}

            QFrame#sidePanel,
            QFrame#sidePanelAccent {{
                background: {PANEL_2};
                border-radius: 22px;
                border: 1px solid {BORDER};
            }}

            QFrame#sidePanelAccent {{
                border: 2px solid {PURPLE};
            }}

            QLabel#appTitle {{
                font-size: 30px;
                font-weight: 800;
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

            QLabel#sideIndicator {{
                color: {PURPLE_HOVER};
                background: transparent;
                font-weight: 700;
                border: none;
                padding: 2px;
            }}

            QLabel#panelTitle,
            QLabel#browserTitle,
            QLabel#selectedName,
            QLabel#weaponName {{
                color: {TEXT};
                font-weight: 800;
                background: transparent;
                border: none;
            }}

            QLabel#panelTotal,
            QLabel#weaponMeta {{
                color: {PURPLE_HOVER};
                font-weight: 700;
                background: transparent;
                border: none;
            }}

            QLabel#countBadge {{
                background: {PURPLE};
                color: white;
                font-weight: 800;
                border-radius: 10px;
                padding: 3px 8px;
            }}

            QLabel#resultStatusWin,
            QLabel#resultStatusLose,
            QLabel#resultStatusNeutral {{
                font-size: 28px;
                font-weight: 900;
                background: transparent;
                border: none;
                padding: 0;
            }}

            QLabel#resultStatusWin {{ color: {GREEN}; }}
            QLabel#resultStatusLose {{ color: {RED}; }}
            QLabel#resultStatusNeutral {{ color: {YELLOW}; }}

            QRadioButton {{
                color: {TEXT};
                font-weight: 700;
                background: transparent;
                border: none;
            }}

            QRadioButton::indicator {{
                width: 18px;
                height: 18px;
                border-radius: 9px;
                border: 2px solid {PURPLE};
                background: {BG_ALT};
            }}

            QRadioButton::indicator:checked {{
                background: {PURPLE};
            }}

            QLineEdit {{
                background: {BG_ALT};
                border: 1px solid {BORDER};
                border-radius: 16px;
                padding: 12px;
                color: {TEXT};
            }}

            QLineEdit:focus {{
                border: 1px solid {PURPLE};
            }}

            QFrame#weaponListCard {{
                background: {PANEL_2};
                border: 1px solid {BORDER};
                border-radius: 22px;
            }}

            QFrame#weaponListCard:hover {{
                border: 1px solid {PURPLE};
                background: #241c3d;
            }}

            QFrame#selectedWeaponCard {{
                background: #120C22;
                border: 1px solid {BORDER};
                border-radius: 18px;
            }}

            QPushButton {{
                background: {PURPLE};
                color: white;
                border: none;
                border-radius: 14px;
                padding: 10px 14px;
                font-weight: 700;
            }}

            QPushButton:hover {{
                background: {PURPLE_HOVER};
            }}

            QPushButton#removeButton {{
                background: rgba(155, 92, 255, 0.18);
                color: {TEXT};
                border: none;
                font-size: 18px;
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
                width: 12px;
                border-radius: 6px;
                margin: 2px;
            }}

            QScrollBar::handle:vertical {{
                background: {PURPLE};
                min-height: 26px;
                border-radius: 6px;
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


def format_value(value):
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    if isinstance(value, (int, float)):
        return "{:,}".format(value)
    return str(value)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName(APP_TITLE)
    window = WinTradeWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
