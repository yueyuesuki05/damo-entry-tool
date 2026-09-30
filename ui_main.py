# @Version  : 1.0
# @Author   : 小野
# @File     : ui_main.py
# @Time     : 2026/9/30 13:19

import os
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QComboBox, QMessageBox, QListWidget,
    QListWidgetItem, QDialog, QInputDialog, QSlider, QFileDialog,
    QCheckBox, QLayout, QPlainTextEdit
)
from PySide6.QtCore import Qt, QSettings, QTimer, QEvent, Signal, QElapsedTimer, QRect, QSize, QPoint

from wps_connector import WPSConnector
from entry_logic import EntryManager
from price_loader import PriceTable


class FlowLayout(QLayout):
    def __init__(self, parent=None, margin=0, h_spacing=6, v_spacing=6):
        super().__init__(parent)
        self._items = []
        self._h_spacing = h_spacing
        self._v_spacing = v_spacing
        self.setContentsMargins(margin, margin, margin, margin)

    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, index):
        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    def takeAt(self, index):
        if 0 <= index < len(self._items):
            return self._items.pop(index)
        return None

    def expandingDirections(self):
        return Qt.Orientations(Qt.Orientation(0))

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._do_layout(QRect(0, 0, width, 0), test_only=True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._do_layout(rect, test_only=False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        m = self.contentsMargins()
        size += QSize(m.left() + m.right(), m.top() + m.bottom())
        return size

    def _do_layout(self, rect, test_only):
        m = self.contentsMargins()
        effective = rect.adjusted(m.left(), m.top(), -m.right(), -m.bottom())
        x = effective.x()
        y = effective.y()
        line_height = 0

        for item in self._items:
            widget = item.widget()
            if widget is None:
                continue
            space_x = self._h_spacing
            space_y = self._v_spacing
            hint = widget.sizeHint()
            next_x = x + hint.width() + space_x
            if next_x - space_x > effective.right() and line_height > 0:
                x = effective.x()
                y = y + line_height + space_y
                next_x = x + hint.width() + space_x
                line_height = 0
            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), hint))
            x = next_x
            line_height = max(line_height, hint.height())

        return y + line_height - rect.y() + m.bottom()


class SingleStepComboBox(QComboBox):
    wheelSignal = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._debounce = QElapsedTimer()
        self._debounce.start()

    def wheelEvent(self, event):
        if self._debounce.elapsed() < 200:
            event.accept()
            return
        self._debounce.restart()
        delta = event.angleDelta().y()
        if delta > 0:
            self.wheelSignal.emit(-1)
        elif delta < 0:
            self.wheelSignal.emit(1)
        event.accept()


class MultiDialog(QDialog):
    def __init__(self, sheet_names, settings, entry_manager,
                 default_day="", parent=None):
        super().__init__(parent)
        self.setWindowTitle("多人合作")
        self.resize(340, 580)
        self.settings = settings
        self.manager = entry_manager
        self.parent_window = parent

        self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)
        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("选择合作人员（可多选）："))
        self.list_widget = QListWidget()
        self.list_widget.setSelectionMode(QListWidget.MultiSelection)
        for name in sheet_names:
            self.list_widget.addItem(QListWidgetItem(name))
        layout.addWidget(self.list_widget)

        self._restore_last_selection()

        layout.addWidget(QLabel("日期（几号）："))
        self.txt_day = QLineEdit()
        if default_day:
            self.txt_day.setText(default_day)
        else:
            self.txt_day.setText(self.settings.value("multi_last_day", "", type=str))
        layout.addWidget(self.txt_day)

        layout.addWidget(QLabel("型号："))
        self.txt_model = QLineEdit()
        last_model = self.settings.value("multi_last_model", "", type=str)
        if last_model:
            self.txt_model.setPlaceholderText(f"上次填过：{last_model}（空着不算填）")
        layout.addWidget(self.txt_model)

        layout.addWidget(QLabel("总数："))
        self.txt_total = QLineEdit()
        self.txt_total.returnPressed.connect(self.do_multi_entry)
        layout.addWidget(self.txt_total)

        self.lbl_status = QLabel("")
        self.lbl_status.setWordWrap(True)
        layout.addWidget(self.lbl_status)

        row_op = QHBoxLayout()
        row_op.addWidget(QLabel("透明度："))
        self.slider_opacity = QSlider(Qt.Horizontal)
        self.slider_opacity.setMinimum(30)
        self.slider_opacity.setMaximum(100)
        try:
            opacity = int(self.settings.value("opacity", 100, type=int))
        except Exception:
            opacity = 100
        if opacity < 30:
            opacity = 30
        if opacity > 100:
            opacity = 100
        self.slider_opacity.setValue(opacity)
        self.slider_opacity.valueChanged.connect(self.on_opacity_changed)
        row_op.addWidget(self.slider_opacity)
        self.lbl_opacity = QLabel(f"{opacity}%")
        self.lbl_opacity.setFixedWidth(45)
        row_op.addWidget(self.lbl_opacity)
        layout.addLayout(row_op)

        btn_row = QHBoxLayout()
        btn_entry = QPushButton("录入")
        btn_entry.clicked.connect(self.do_multi_entry)
        btn_row.addWidget(btn_entry)

        btn_clear = QPushButton("清除选择")
        btn_clear.clicked.connect(self.clear_selection)
        btn_row.addWidget(btn_clear)

        btn_close = QPushButton("关闭")
        btn_close.clicked.connect(self.close)
        btn_row.addWidget(btn_close)
        layout.addLayout(btn_row)

        self.setWindowOpacity(opacity / 100.0)
        self.list_widget.installEventFilter(self)
        self.txt_day.installEventFilter(self)
        self.txt_model.installEventFilter(self)
        self.txt_total.installEventFilter(self)

    def on_opacity_changed(self, value):
        self.setWindowOpacity(value / 100.0)
        self.lbl_opacity.setText(f"{value}%")
        self.settings.setValue("opacity", value)
        if self.parent_window is not None:
            try:
                self.parent_window.setWindowOpacity(value / 100.0)
                self.parent_window.slider_opacity.blockSignals(True)
                self.parent_window.slider_opacity.setValue(value)
                self.parent_window.slider_opacity.blockSignals(False)
                self.parent_window.lbl_opacity.setText(f"{value}%")
            except Exception:
                pass

    def eventFilter(self, obj, event):
        if event.type() == QEvent.KeyPress:
            key = event.key()
            if obj is self.list_widget:
                if key == Qt.Key_Down:
                    cur = self.list_widget.currentRow()
                    if cur >= self.list_widget.count() - 1:
                        self.txt_day.setFocus()
                        return True
            elif obj is self.txt_day:
                if key == Qt.Key_Up:
                    self.list_widget.setFocus()
                    return True
                if key == Qt.Key_Down:
                    self.txt_model.setFocus()
                    return True
            elif obj is self.txt_model:
                if key == Qt.Key_Up:
                    self.txt_day.setFocus()
                    return True
                if key == Qt.Key_Down:
                    self.txt_total.setFocus()
                    return True
            elif obj is self.txt_total:
                if key == Qt.Key_Up:
                    self.txt_model.setFocus()
                    return True
        return super().eventFilter(obj, event)

    def _restore_last_selection(self):
        raw = self.settings.value("multi_last_persons", "", type=str)
        if not raw:
            return
        last_persons = [x for x in raw.split(",") if x.strip()]
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            if item.text() in last_persons:
                item.setSelected(True)

    def _save_last_selection(self, selected):
        self.settings.setValue("multi_last_persons", ",".join(selected))

    def clear_selection(self):
        self.list_widget.clearSelection()
        self.list_widget.setCurrentRow(-1)

    def do_multi_entry(self):
        selected = [i.text() for i in self.list_widget.selectedItems()]
        day = self.txt_day.text().strip()
        model = self.txt_model.text().strip()
        total = self.txt_total.text().strip()

        missing = []
        if not selected:
            missing.append("合作人员")
        if not day:
            missing.append("日期")
        if not model:
            missing.append("型号")
        if not total:
            missing.append("总数")

        if missing:
            self.lbl_status.setText("未填写完整：" + "、".join(missing))
            return

        ok, msg = self.manager.multi_entry(selected, day, model, total)
        self.lbl_status.setText(msg)
        if ok:
            self.settings.setValue("multi_last_day", day)
            self.settings.setValue("multi_last_model", model)
            self._save_last_selection(selected)
            self.txt_model.setPlaceholderText(f"上次填过：{model}（空着不算填）")
            self.txt_model.clear()
            self.txt_total.clear()
            self.txt_model.setFocus()
            QTimer.singleShot(50, self._refocus)
        else:
            self.lbl_status.setText(msg)

    def _refocus(self):
        try:
            self.activateWindow()
            self.raise_()
            self.txt_model.setFocus()
        except Exception:
            pass

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            return
        super().keyPressEvent(event)


class MultiBatchDialog(QDialog):
    """批量录入：选择多个人员，型号固定，数量逐个输入"""
    def __init__(self, sheet_names, settings, parent=None):
        super().__init__(parent)
        self.setWindowTitle("批量录入 - 选择人员")
        self.resize(320, 540)
        self.settings = settings

        self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)
        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("选择人员（按 sheet 顺序，可多选）："))
        self.list_widget = QListWidget()
        self.list_widget.setSelectionMode(QListWidget.MultiSelection)
        for name in sheet_names:
            self.list_widget.addItem(QListWidgetItem(name))
        layout.addWidget(self.list_widget)

        raw = self.settings.value("batch_last_persons", "", type=str)
        if raw:
            last = [x for x in raw.split(",") if x.strip()]
            for i in range(self.list_widget.count()):
                item = self.list_widget.item(i)
                if item.text() in last:
                    item.setSelected(True)

        self.lbl_info = QLabel("已选 0 人")
        layout.addWidget(self.lbl_info)
        self.list_widget.itemSelectionChanged.connect(self._update_count)
        self._update_count()

        btn_row = QHBoxLayout()
        btn_ok = QPushButton("开始批量录入")
        btn_ok.clicked.connect(self.accept)
        btn_row.addWidget(btn_ok)

        btn_clear = QPushButton("清除选择")
        btn_clear.clicked.connect(self.clear_selection)
        btn_row.addWidget(btn_clear)

        btn_cancel = QPushButton("取消")
        btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(btn_cancel)
        layout.addLayout(btn_row)

    def _update_count(self):
        n = len(self.list_widget.selectedItems())
        self.lbl_info.setText(f"已选 {n} 人")

    def clear_selection(self):
        self.list_widget.clearSelection()
        self.list_widget.setCurrentRow(-1)
        self._update_count()

    def get_selected(self):
        return [i.text() for i in self.list_widget.selectedItems()]

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.reject()
            return
        super().keyPressEvent(event)


class CleanEmptyDialog(QDialog):
    """清理空列确认对话框：可滚动的文本框 + 底部固定按钮"""
    def __init__(self, preview_text, total, sheet_count, parent=None):
        super().__init__(parent)
        self.setWindowTitle("清理空列")
        self.resize(560, 640)

        self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)

        layout = QVBoxLayout(self)

        info = QLabel(
            f"共发现 {total} 个空列，分布在 {sheet_count} 个 sheet：\n"
            f"（删除后无法自动恢复，请确认）"
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        self.txt = QPlainTextEdit()
        self.txt.setReadOnly(True)
        self.txt.setPlainText(preview_text)
        layout.addWidget(self.txt, 1)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)

        btn_ok = QPushButton("确认删除")
        btn_ok.clicked.connect(self.accept)
        btn_row.addWidget(btn_ok)

        btn_cancel = QPushButton("取消")
        btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(btn_cancel)

        layout.addLayout(btn_row)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.reject()
            return
        super().keyPressEvent(event)


class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("打磨录入工具")
        self.resize(880, 380)

        self.settings = QSettings("config.ini", QSettings.IniFormat)

        try:
            on_top = int(self.settings.value("window_on_top", 1, type=int))
        except Exception:
            on_top = 1
        if on_top:
            self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)

        self.conn = WPSConnector()
        self.conn.connect()

        self.price_table = PriceTable()
        price_path = self.settings.value("price_file", "", type=str)
        if price_path:
            self.price_table.set_path(price_path)
            self.price_table.load()

        self.manager = EntryManager(self.conn, price_table=self.price_table)
        self._scanned_workbooks = set()
        self._verified_workbooks = set()
        self._missing_prices = []

        self._last_workbook = ""
        self._last_sheet = ""
        self._restoring = False

        # 批量录入状态
        self.batch_mode = False
        self.batch_persons = []
        self.batch_index = 0
        self.batch_model = ""
        self.batch_history = []

        self.build_ui()

        self.chk_top.setChecked(bool(on_top))

        try:
            opacity = int(self.settings.value("opacity", 100, type=int))
        except Exception:
            opacity = 100
        if opacity < 30:
            opacity = 30
        if opacity > 100:
            opacity = 100
        self.slider_opacity.setValue(opacity)
        self._apply_opacity(opacity)

        if self.price_table.loaded:
            self.log.setText(f"单价表已加载（{len(self.price_table.data)} 个型号）")
        else:
            self.log.setText("提示：点击'单价表'按钮选择单价表文件")

        self.refresh_sheets()

        self.timer = QTimer()
        self.timer.timeout.connect(self.monitor_wps)
        self.timer.start(500)

    def build_ui(self):
        layout = QVBoxLayout(self)

        self.lbl_status = QLabel("当前工作簿：-    当前人员：-")
        layout.addWidget(self.lbl_status)

        row1 = QHBoxLayout()
        row1.addWidget(QLabel("人员："))
        self.cbo_sheet = SingleStepComboBox()
        self.cbo_sheet.setEditable(True)
        self.cbo_sheet.setInsertPolicy(QComboBox.NoInsert)
        self.cbo_sheet.activated.connect(self.on_sheet_activated)
        self.cbo_sheet.wheelSignal.connect(self.on_wheel_navigate)
        row1.addWidget(self.cbo_sheet)
        btn_refresh = QPushButton("刷新")
        btn_refresh.clicked.connect(self.refresh_sheets)
        row1.addWidget(btn_refresh)
        layout.addLayout(row1)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel("日期（几号）："))
        self.txt_day = QLineEdit()
        self.txt_day.setText(self.settings.value("last_day", "", type=str))
        self.txt_day.returnPressed.connect(lambda: self.txt_model.setFocus())
        self.txt_day.installEventFilter(self)
        row2.addWidget(self.txt_day)
        layout.addLayout(row2)

        row3 = QHBoxLayout()
        row3.addWidget(QLabel("型号："))
        self.txt_model = QLineEdit()
        last_model = self.settings.value("last_model", "", type=str)
        if last_model:
            self.txt_model.setPlaceholderText(f"上次填过：{last_model}（空着不算填）")
        self.txt_model.returnPressed.connect(lambda: self.txt_qty.setFocus())
        self.txt_model.installEventFilter(self)
        row3.addWidget(self.txt_model)
        layout.addLayout(row3)

        row4 = QHBoxLayout()
        row4.addWidget(QLabel("数量表达式："))
        self.txt_qty = QLineEdit()
        self.txt_qty.returnPressed.connect(self.do_entry)
        self.txt_qty.installEventFilter(self)
        row4.addWidget(self.txt_qty)
        layout.addLayout(row4)

        btn_layout = FlowLayout(h_spacing=6, v_spacing=6)

        btn_entry = QPushButton("录入")
        btn_entry.clicked.connect(self.do_entry)
        btn_layout.addWidget(btn_entry)

        btn_undo = QPushButton("撤回")
        btn_undo.clicked.connect(self.do_undo)
        btn_layout.addWidget(btn_undo)

        btn_multi = QPushButton("多人合作")
        btn_multi.clicked.connect(self.do_multi)
        btn_layout.addWidget(btn_multi)

        self.btn_batch = QPushButton("批量录入")
        self.btn_batch.clicked.connect(self.do_batch_start)
        btn_layout.addWidget(self.btn_batch)

        btn_add = QPushButton("新增人员")
        btn_add.clicked.connect(self.do_add_person)
        btn_layout.addWidget(btn_add)

        btn_price = QPushButton("单价表")
        btn_price.clicked.connect(self.do_select_price_file)
        btn_layout.addWidget(btn_price)

        btn_reload = QPushButton("重载单价表")
        btn_reload.clicked.connect(self.do_reload_price_file)
        btn_layout.addWidget(btn_reload)

        btn_missing = QPushButton("检查缺失单价")
        btn_missing.clicked.connect(self.do_check_missing_prices)
        btn_layout.addWidget(btn_missing)

        btn_clean = QPushButton("清理空列")
        btn_clean.clicked.connect(self.do_clean_empty)
        btn_layout.addWidget(btn_clean)

        btn_verify = QPushButton("检查修正公式")
        btn_verify.clicked.connect(self.do_verify_formulas)
        btn_layout.addWidget(btn_verify)

        btn_summary = QPushButton("修帽子合计统计")
        btn_summary.clicked.connect(self.do_make_summary)
        btn_layout.addWidget(btn_summary)

        btn_container = QWidget()
        btn_container.setLayout(btn_layout)
        layout.addWidget(btn_container)

        row6 = QHBoxLayout()
        row6.addWidget(QLabel("窗口透明度："))
        self.slider_opacity = QSlider(Qt.Horizontal)
        self.slider_opacity.setMinimum(30)
        self.slider_opacity.setMaximum(100)
        self.slider_opacity.setValue(100)
        self.slider_opacity.setTickPosition(QSlider.TicksBelow)
        self.slider_opacity.setTickInterval(10)
        self.slider_opacity.valueChanged.connect(self.on_opacity_changed)
        row6.addWidget(self.slider_opacity)
        self.lbl_opacity = QLabel("100%")
        self.lbl_opacity.setFixedWidth(50)
        row6.addWidget(self.lbl_opacity)

        self.chk_top = QCheckBox("窗口置顶")
        self.chk_top.setChecked(True)
        self.chk_top.stateChanged.connect(self.on_top_changed)
        row6.addWidget(self.chk_top)

        layout.addLayout(row6)

        self.log = QLabel("")
        self.log.setWordWrap(True)
        layout.addWidget(self.log)

    def on_top_changed(self, state):
        if state:
            self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)
        else:
            self.setWindowFlags(self.windowFlags() & ~Qt.WindowStaysOnTopHint)
        self.show()
        self.settings.setValue("window_on_top", 1 if state else 0)

    # ---------- 批量录入 ----------
    def do_batch_start(self):
        if self.batch_mode:
            reply = QMessageBox.question(
                self, "退出批量录入",
                f"当前进度：{self.batch_index + 1}/{len(self.batch_persons)}\n"
                f"已录入的会保留，未录入的跳过。\n\n是否退出批量录入？",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                self._cancel_batch()
            return

        wb_name = self.conn.get_workbook_name()
        if "干磨" not in wb_name:
            QMessageBox.warning(self, "提示",
                                f"批量录入仅用于干磨表，当前工作簿：{wb_name}")
            return

        names = self.conn.get_sheet_names()
        if not names:
            QMessageBox.warning(self, "提示", "当前工作簿没有可用的 sheet。")
            return

        dlg = MultiBatchDialog(names, self.settings, self)
        if dlg.exec() != QDialog.Accepted:
            return

        selected = dlg.get_selected()
        if not selected:
            QMessageBox.warning(self, "提示", "至少选择一个人。")
            return

        self.settings.setValue("batch_last_persons", ",".join(selected))

        self.batch_persons = selected
        self.batch_index = 0
        self.batch_model = ""
        self.batch_history = []
        self.batch_mode = True

        self.btn_batch.setText("退出批量")

        first = self.batch_persons[0]
        try:
            self.conn.activate_sheet(first)
        except Exception as e:
            print("切换 sheet 失败:", e)
        self._last_sheet = first
        self.refresh_sheets()

        self.txt_qty.clear()
        self.txt_model.setFocus()
        self.txt_model.setPlaceholderText("请输入型号（回车后到数量框）")

        total = len(self.batch_persons)
        self.log.setText(
            f"批量录入已开始：{first}（1/{total}）\n"
            f"请先输入型号，再输入数量。\n"
            f"发现录错可按 Ctrl+Z 或点'撤回'回退上一步。\n"
            f"想退出批量：点'退出批量'按钮 或 按 ESC。"
        )

    def do_batch_entry(self):
        person = self.batch_persons[self.batch_index]
        total = len(self.batch_persons)

        if not self.batch_model:
            m = self.txt_model.text().strip()
            if not m:
                self.log.setText("请先输入型号")
                self.txt_model.setFocus()
                return
            self.batch_model = m
            self.txt_model.setText(m)

        qty = self.txt_qty.text().strip()
        if not qty:
            self.log.setText(f"请输入数量（{person}）")
            return

        day = self.txt_day.text().strip()
        if not day:
            self.log.setText("请先填写日期")
            self.txt_day.setFocus()
            return

        try:
            current = self.conn.get_active_sheet_name()
            if current != person:
                self.conn.activate_sheet(person)
                self._last_sheet = person
                self.refresh_sheets()
        except Exception:
            pass

        undo_before = len(self.manager.undo_stack)

        ok, msg = self.manager.entry(person, day, self.batch_model, qty)
        self.log.setText(msg)
        if not ok:
            QMessageBox.warning(self, "批量录入失败", f"{person}: {msg}")
            return

        if len(self.manager.undo_stack) > undo_before:
            rec = self.manager.undo_stack[-1]
            self.batch_history.append({
                "person": person,
                "model": self.batch_model,
                "qty": qty,
                "record": rec,
            })

        try:
            self.settings.setValue("last_day", day)
            self.settings.setValue("last_model", self.batch_model)
        except Exception:
            pass

        self.batch_index += 1
        self.txt_qty.clear()

        if self.batch_index >= total:
            done_model = self.batch_model
            done_count = total
            self.batch_mode = False
            self.batch_model = ""
            self.batch_persons = []
            self.batch_index = 0
            self.batch_history = []
            self.btn_batch.setText("批量录入")
            self.txt_model.setPlaceholderText("")
            self.txt_qty.setFocus()
            self.log.setText(f"批量录入完成：{done_model}，共 {done_count} 人")
            QMessageBox.information(
                self, "批量录入",
                f"全部完成！\n型号：{done_model}\n共 {done_count} 人"
            )
            return

        next_person = self.batch_persons[self.batch_index]
        try:
            self.conn.activate_sheet(next_person)
        except Exception as e:
            print("切换 sheet 失败:", e)
        self._last_sheet = next_person
        self.refresh_sheets()

        self.txt_qty.setFocus()
        idx = self.batch_index + 1
        self.log.setText(
            f"批量录入：{self.batch_model} - {next_person}（{idx}/{total}）\n"
            f"可按 Ctrl+Z 或点'撤回'回退上一步；按 ESC 退出批量"
        )

    def do_batch_undo(self):
        if not self.batch_history:
            QMessageBox.information(self, "批量回退",
                                    "没有可回退的操作（已经是第一步）")
            return

        item = self.batch_history.pop()
        person = item["person"]
        rec = item["record"]

        try:
            wb = self.conn.get_active_workbook()
            if wb is None:
                QMessageBox.warning(self, "批量回退", "未检测到工作簿")
                return
            sh = wb.Sheets(rec["sheet_name"])

            if rec["inserted"]:
                sh.Columns(rec["col"]).Delete()
            else:
                old = rec.get("old_value")
                is_empty = (old is None)
                if not is_empty:
                    try:
                        if abs(float(old)) < 1e-9:
                            is_empty = True
                    except (ValueError, TypeError):
                        is_empty = False

                if is_empty:
                    sh.Cells(rec["row"], rec["col"]).ClearContents()
                else:
                    sh.Cells(rec["row"], rec["col"]).Value = old

            try:
                self.manager._update_total(sh, wb.Name)
            except Exception:
                pass
            try:
                wb.Save()
            except Exception:
                pass

            if self.manager.undo_stack and self.manager.undo_stack[-1] is rec:
                self.manager.undo_stack.pop()
        except Exception as e:
            QMessageBox.warning(self, "批量回退", f"恢复失败：{e}")
            return

        self.batch_index = max(0, self.batch_index - 1)

        try:
            self.conn.activate_sheet(person)
            self._last_sheet = person
            self.refresh_sheets()
        except Exception as e:
            print("切换 sheet 失败:", e)

        self.txt_qty.clear()
        self.txt_qty.setFocus()

        total = len(self.batch_persons)
        idx = self.batch_index + 1
        self.log.setText(
            f"已回退到：{person}（{idx}/{total}）\n"
            f"型号：{self.batch_model}，请重新输入数量"
        )

    def _cancel_batch(self):
        self.batch_mode = False
        self.batch_persons = []
        self.batch_index = 0
        self.batch_model = ""
        self.batch_history = []
        self.btn_batch.setText("批量录入")
        self.txt_model.setPlaceholderText("")
        self.txt_qty.clear()
        self.log.setText("已退出批量录入（已录入的保留）")

    # ---------- 单价表 ----------
    def do_select_price_file(self):
        last = self.settings.value("price_file", "", type=str)
        init_dir = os.path.dirname(last) if last else ""
        path, _ = QFileDialog.getOpenFileName(
            self, "选择单价表文件", init_dir,
            "Excel 文件 (*.xlsx *.xls);;所有文件 (*.*)"
        )
        if not path:
            return
        self.settings.setValue("price_file", path)
        self.price_table.set_path(path)
        ok = self.price_table.load()
        if ok:
            self._scanned_workbooks.clear()
            self.log.setText(f"单价表已加载（{len(self.price_table.data)} 个型号）")
            wb_name = self.conn.get_workbook_name()
            if "干磨" in wb_name:
                self.try_scan_prices()
        else:
            self.log.setText(f"单价表加载失败：{self.price_table.error}")

    def do_reload_price_file(self):
        path = self.settings.value("price_file", "", type=str)
        if not path:
            QMessageBox.warning(self, "提示",
                                "还没设置单价表路径，请先点'单价表'按钮选择文件。")
            return
        self.price_table.set_path(path)
        ok = self.price_table.load()
        if ok:
            self._scanned_workbooks.clear()
            self.log.setText(f"单价表已重新加载（{len(self.price_table.data)} 个型号）")
            wb_name = self.conn.get_workbook_name()
            if "干磨" in wb_name:
                self.try_scan_prices()
        else:
            self.log.setText(f"单价表加载失败：{self.price_table.error}")

    def try_scan_prices(self):
        wb_name = self.conn.get_workbook_name()
        if "干磨" not in wb_name:
            return
        if wb_name in self._scanned_workbooks:
            return
        if not self.price_table.loaded:
            return
        self._scanned_workbooks.add(wb_name)
        missing = self.manager.scan_and_fill_prices(wb_name)
        self._missing_prices = missing
        if missing:
            preview = "、".join(missing[:5])
            if len(missing) > 5:
                preview += f" 等 {len(missing)} 个"
            self.log.setText(f"未找到单价：{preview}")
        else:
            self.log.setText("单价已全部检查并填充")

    def do_check_missing_prices(self):
        wb_name = self.conn.get_workbook_name()
        if "干磨" not in wb_name:
            QMessageBox.warning(self, "提示", f"当前工作簿不是干磨表：{wb_name}")
            return
        missing, err = self.manager.find_missing_prices(wb_name)
        if err:
            QMessageBox.warning(self, "检查缺失单价", err)
            return
        if not missing:
            QMessageBox.information(self, "检查缺失单价",
                                    "所有型号都能在单价表中找到单价。")
            self.log.setText("检查缺失单价：无缺失")
            return
        preview = "\n".join(missing[:80])
        if len(missing) > 80:
            preview += f"\n…… 共 {len(missing)} 个"
        msg = f"以下 {len(missing)} 个型号没有单价：\n\n{preview}"
        if len(msg) > 4000:
            msg = msg[:4000] + "\n\n……（内容过多，已截断）"
        QMessageBox.information(self, "检查缺失单价", msg)
        self.log.setText(f"缺失单价：共 {len(missing)} 个型号")

    # ---------- 公式检查 ----------
    def try_verify_formulas(self):
        wb_name = self.conn.get_workbook_name()
        if not wb_name:
            return
        if wb_name in self._verified_workbooks:
            return
        self._verified_workbooks.add(wb_name)
        fixes = self.manager.verify_current_workbook()
        if fixes:
            preview = "、".join(fixes[:5])
            if len(fixes) > 5:
                preview += f" 等 {len(fixes)} 处"
            self.log.setText(f"已修正公式：{preview}")
        else:
            self.log.setText("公式检查完成，无修正")

    def do_verify_formulas(self):
        wb_name = self.conn.get_workbook_name()
        if not wb_name:
            QMessageBox.warning(self, "提示", "未检测到活动工作簿。")
            return
        self._verified_workbooks.discard(wb_name)
        reply = QMessageBox.question(
            self,
            "检查修正公式",
            f"将检查并修正「{wb_name}」所有 sheet 的公式，是否继续？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes
        )
        if reply != QMessageBox.Yes:
            return
        fixes = self.manager.verify_current_workbook()
        if fixes:
            preview = "、".join(fixes[:10])
            if len(fixes) > 10:
                preview += f" 等 {len(fixes)} 处"
            QMessageBox.information(self, "检查修正公式",
                                    f"已修正 {len(fixes)} 处：\n{preview}")
            self.log.setText(f"已修正公式：{preview}")
        else:
            QMessageBox.information(self, "检查修正公式", "所有公式都符合规范，无需修正。")
            self.log.setText("公式检查完成，无修正")
        self.refresh_sheets()

    # ---------- 透明度 ----------
    def on_opacity_changed(self, value):
        self._apply_opacity(value)
        self.lbl_opacity.setText(f"{value}%")
        self.settings.setValue("opacity", value)

    def _apply_opacity(self, value):
        try:
            self.setWindowOpacity(value / 100.0)
        except Exception as e:
            print("设置透明度失败:", e)

    def _refocus(self):
        try:
            self.activateWindow()
            self.raise_()
            self.txt_model.setFocus()
        except Exception:
            pass

    def eventFilter(self, obj, event):
        if event.type() == QEvent.KeyPress:
            key = event.key()
            if (self.batch_mode
                    and key == Qt.Key_Z
                    and event.modifiers() == Qt.ControlModifier):
                self.do_undo()
                return True

            if self.batch_mode and key == Qt.Key_Escape:
                reply = QMessageBox.question(
                    self, "退出批量录入",
                    f"当前进度：{self.batch_index + 1}/{len(self.batch_persons)}\n"
                    f"已录入的会保留，未录入的跳过。\n\n是否退出批量录入？",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No
                )
                if reply == QMessageBox.Yes:
                    self._cancel_batch()
                return True

            if obj is self.txt_day:
                if key == Qt.Key_Down:
                    self.txt_model.setFocus()
                    return True
            elif obj is self.txt_model:
                if key == Qt.Key_Up:
                    self.txt_day.setFocus()
                    return True
                if key == Qt.Key_Down:
                    self.txt_qty.setFocus()
                    return True
            elif obj is self.txt_qty:
                if key == Qt.Key_Up:
                    self.txt_model.setFocus()
                    return True
        return super().eventFilter(obj, event)

    def monitor_wps(self):
        if self._restoring:
            return
        if self.batch_mode:
            return

        if self.conn.app is None:
            self.conn.connect()
            return

        try:
            wb = self.conn.get_active_workbook()
        except Exception:
            return

        if wb is None:
            if self._last_workbook != "":
                self._last_workbook = ""
                self._last_sheet = ""
                self.lbl_status.setText("当前工作簿：-    当前人员：-")
            return

        try:
            wb_name = wb.Name
            active = self.conn.get_active_sheet_name()
        except Exception:
            return

        if wb_name != self._last_workbook:
            self._last_workbook = wb_name
            last_sheet = self.settings.value(f"last_sheet_for_{wb_name}", "", type=str)
            self._last_sheet = active
            self.refresh_sheets()
            QTimer.singleShot(1500, self.try_scan_prices)
            if last_sheet:
                QTimer.singleShot(
                    500,
                    lambda w=wb_name, s=last_sheet: self._delayed_restore(w, s)
                )
            return

        if active != self._last_sheet:
            self._last_sheet = active
            try:
                self.settings.setValue(f"last_sheet_for_{wb_name}", active)
            except Exception:
                pass
            self.refresh_sheets()

    def _delayed_restore(self, wb_name, sheet_name):
        if self._restoring:
            return
        if self.batch_mode:
            return
        try:
            current_wb = self.conn.get_workbook_name()
        except Exception:
            return
        if current_wb != wb_name:
            return
        try:
            all_sheets = self.conn.get_sheet_names()
        except Exception:
            return
        if sheet_name not in all_sheets:
            return
        try:
            active = self.conn.get_active_sheet_name()
        except Exception:
            return
        first_sheet = all_sheets[0] if all_sheets else ""
        if active != first_sheet and active != sheet_name:
            return
        if active == sheet_name:
            return
        self._restoring = True
        try:
            self.conn.activate_sheet(sheet_name)
            self._last_sheet = sheet_name
            try:
                self.settings.setValue(f"last_sheet_for_{wb_name}", sheet_name)
            except Exception:
                pass
        except Exception as e:
            print("延时恢复 sheet 失败:", e)
        finally:
            self._restoring = False
        self.refresh_sheets()

    def refresh_sheets(self):
        if self.conn.app is None:
            self.conn.connect()
        wb = self.conn.get_active_workbook()
        if wb is None:
            self.conn.connect()
            wb = self.conn.get_active_workbook()
        if wb is None:
            self.lbl_status.setText("当前工作簿：-    当前人员：-")
            return
        names = self.conn.get_sheet_names()
        current_items = [self.cbo_sheet.itemText(i) for i in range(self.cbo_sheet.count())]
        if current_items != names:
            self.cbo_sheet.blockSignals(True)
            self.cbo_sheet.clear()
            self.cbo_sheet.addItems(names)
            self.cbo_sheet.blockSignals(False)
        wb_name = self.conn.get_workbook_name()
        active = self.conn.get_active_sheet_name()
        self.lbl_status.setText(f"当前工作簿：{wb_name}    当前人员：{active}")
        if active in names and self.cbo_sheet.currentText() != active:
            self.cbo_sheet.blockSignals(True)
            self.cbo_sheet.setCurrentText(active)
            self.cbo_sheet.blockSignals(False)

    def on_sheet_activated(self, index):
        text = self.cbo_sheet.currentText().strip()
        if not text:
            return
        all_sheets = [self.cbo_sheet.itemText(i) for i in range(self.cbo_sheet.count())]
        if text in all_sheets:
            self._switch_to_sheet(text)

    def on_wheel_navigate(self, direction):
        if direction == 0:
            return
        try:
            active = self.conn.get_active_sheet_name()
        except Exception:
            return
        names = [self.cbo_sheet.itemText(i) for i in range(self.cbo_sheet.count())]
        if not names:
            return
        if active not in names:
            self.refresh_sheets()
            names = [self.cbo_sheet.itemText(i) for i in range(self.cbo_sheet.count())]
            if active not in names:
                return
        cur_idx = names.index(active)
        new_idx = cur_idx + direction
        if new_idx < 0 or new_idx >= len(names):
            return
        self._switch_to_sheet(names[new_idx])

    def _switch_to_sheet(self, name):
        wb_name = self.conn.get_workbook_name()
        if wb_name:
            try:
                self.settings.setValue(f"last_sheet_for_{wb_name}", name)
            except Exception:
                pass
        try:
            self.conn.activate_sheet(name)
        except Exception as e:
            print("切换 sheet 失败:", e)
            return
        self._last_sheet = name
        self.refresh_sheets()
        self.txt_model.setFocus()

    def _get_current_sheet(self):
        active = self.conn.get_active_sheet_name()
        if active:
            return active
        text = self.cbo_sheet.currentText().strip()
        return text if text else None

    def do_entry(self):
        if self.batch_mode:
            self.do_batch_entry()
            return

        sheet = self._get_current_sheet()
        if not sheet:
            QMessageBox.warning(self, "提示", "未检测到 WPS 活动 sheet。")
            return
        current_model = self.txt_model.text().strip()

        ok, msg = self.manager.entry(
            sheet,
            self.txt_day.text(),
            current_model,
            self.txt_qty.text()
        )
        self.log.setText(msg)
        if ok:
            wb_name = self.conn.get_workbook_name()
            if wb_name and sheet:
                try:
                    self.settings.setValue(f"last_sheet_for_{wb_name}", sheet)
                except Exception:
                    pass
            self.settings.setValue("last_day", self.txt_day.text())
            if current_model:
                self.settings.setValue("last_model", current_model)
                self.txt_model.setPlaceholderText(f"上次填过：{current_model}（空着不算填）")
            self.txt_qty.clear()
            self.txt_model.clear()
            self.txt_model.setFocus()
            self.refresh_sheets()
            QTimer.singleShot(50, self._refocus)
        else:
            QMessageBox.warning(self, "录入失败", msg)

    def do_undo(self):
        if self.batch_mode and self.batch_history:
            self.do_batch_undo()
            return

        ok, msg = self.manager.undo()
        self.log.setText(msg)
        if not ok:
            QMessageBox.information(self, "撤回", msg)
        else:
            self.refresh_sheets()

    def do_multi(self):
        names = self.conn.get_sheet_names()
        current_day = self.txt_day.text().strip()
        dlg = MultiDialog(names, self.settings, self.manager,
                          default_day=current_day, parent=self)
        dlg.exec()
        self.refresh_sheets()

    def do_add_person(self):
        name, ok = QInputDialog.getText(self, "新增人员", "请输入人员姓名：")
        if ok and name.strip():
            ok, msg = self.manager.add_person(name.strip())
            self.log.setText(msg)
            if not ok:
                QMessageBox.warning(self, "新增人员", msg)
            else:
                self.refresh_sheets()

    def do_clean_empty(self):
        items, err = self.manager.clean_empty_columns_all()
        if err:
            QMessageBox.warning(self, "清理空列", err)
            return
        if not items:
            QMessageBox.information(self, "清理空列", "没有 34 行为 0 的型号列，无需清理。")
            return

        grouped = {}
        for it in items:
            grouped.setdefault(it["sheet"], []).append(it["name"])

        lines = []
        for sheet_name, names in grouped.items():
            lines.append(f"【{sheet_name}】共 {len(names)} 列")
            for n in names:
                lines.append(f"    · {n}")
            lines.append("")

        preview = "\n".join(lines)

        total = len(items)
        sheet_count = len(grouped)

        dlg = CleanEmptyDialog(preview, total, sheet_count, parent=self)
        if dlg.exec() != QDialog.Accepted:
            self.log.setText("已取消清理。")
            return

        ok, msg2 = self.manager.do_delete_columns_batch(items)
        self.log.setText(msg2)
        if not ok:
            QMessageBox.warning(self, "清理空列", msg2)
        else:
            QMessageBox.information(self, "清理空列", msg2)
            self.refresh_sheets()

    def do_make_summary(self):
        wb_name = self.conn.get_workbook_name()
        if "修帽子" not in wb_name:
            QMessageBox.warning(self, "提示", f"当前工作簿不是修帽子表：{wb_name}")
            return
        reply = QMessageBox.question(
            self, "修帽子合计统计",
            "将按 sheet 顺序生成合计，是否继续？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return
        ok, msg = self.manager.make_summary()
        self.log.setText(msg)
        if not ok:
            QMessageBox.warning(self, "修帽子合计统计", msg)
        else:
            try:
                self.conn.activate_sheet("合计")
            except Exception as e:
                print("切换到合计 sheet 失败:", e)
            QMessageBox.information(self, "修帽子合计统计", msg)
            self.refresh_sheets()


def run():
    import sys
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    run()