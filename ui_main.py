# @Version  : 1.0
# @Author   : 小野
# @File     : ui_main.py 主界面 + 交互逻辑
# @Time     : 2026/9/30 13:19

import os
import re
from collections import defaultdict
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QComboBox, QMessageBox, QListWidget,
    QListWidgetItem, QDialog, QInputDialog, QSlider, QFileDialog,
    QCheckBox, QLayout, QPlainTextEdit, QSpinBox, QCompleter
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


class QueryDateDialog(QDialog):
    def __init__(self, conn, parent=None):
        super().__init__(parent)
        self.setWindowTitle("查询某天记录")
        self.resize(700, 760)
        self.conn = conn
        self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)

        layout = QVBoxLayout(self)

        # --- 工作簿选择 ---
        row_wb = QHBoxLayout()
        row_wb.addWidget(QLabel("工作簿："))
        self.cbo_wb = QComboBox()
        self.cbo_wb.setMinimumWidth(320)
        self.cbo_wb.currentIndexChanged.connect(self._on_wb_changed)
        row_wb.addWidget(self.cbo_wb, 1)

        btn_refresh_wb = QPushButton("刷新工作簿")
        btn_refresh_wb.clicked.connect(self._load_workbooks)
        row_wb.addWidget(btn_refresh_wb)
        layout.addLayout(row_wb)

        # --- 日期 + 查询按钮 ---
        row = QHBoxLayout()
        row.addWidget(QLabel("日期（几号）："))
        self.txt_day = QLineEdit()
        self.txt_day.setFixedWidth(80)
        self.txt_day.returnPressed.connect(self.do_query)
        row.addWidget(self.txt_day)

        btn_query = QPushButton("查询")
        btn_query.clicked.connect(self.do_query)
        row.addWidget(btn_query)

        btn_all = QPushButton("全选")
        btn_all.clicked.connect(lambda: self._set_all(True))
        row.addWidget(btn_all)

        btn_none = QPushButton("全不选")
        btn_none.clicked.connect(lambda: self._set_all(False))
        row.addWidget(btn_none)

        row.addStretch(1)
        layout.addLayout(row)

        # --- 直接输入人员 ---
        row_manual = QHBoxLayout()
        row_manual.addWidget(QLabel("或直接输入人员："))
        self.txt_persons_manual = QLineEdit()
        self.txt_persons_manual.setPlaceholderText(
            "留空则用下方勾选；填写则只看这里的人名（逗号/顿号/分号分隔，如：张三,李四）"
        )
        self.txt_persons_manual.returnPressed.connect(self.do_query)
        self.txt_persons_manual.textChanged.connect(self._on_manual_changed)
        row_manual.addWidget(self.txt_persons_manual, 1)

        btn_clear_manual = QPushButton("清空")
        btn_clear_manual.clicked.connect(self.txt_persons_manual.clear)
        row_manual.addWidget(btn_clear_manual)
        layout.addLayout(row_manual)

        layout.addWidget(QLabel("要查询的 sheet（可多选，输入框非空时忽略这里的勾选）："))
        self.list_sheets = QListWidget()
        self.list_sheets.setSelectionMode(QListWidget.MultiSelection)
        self.list_sheets.setMaximumHeight(150)
        layout.addWidget(self.list_sheets)

        self.txt_result = QPlainTextEdit()
        self.txt_result.setReadOnly(True)
        layout.addWidget(self.txt_result, 1)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        btn_close = QPushButton("关闭")
        btn_close.clicked.connect(self.close)
        btn_row.addWidget(btn_close)
        layout.addLayout(btn_row)

        self._load_workbooks()
        self.txt_day.setFocus()

    # ---------- 工作簿 / sheet 列表 ----------
    def _load_workbooks(self):
        self.cbo_wb.blockSignals(True)
        self.cbo_wb.clear()
        self.cbo_wb.blockSignals(False)

        if self.conn.app is None:
            try:
                self.conn.connect()
            except Exception:
                pass
        if self.conn.app is None:
            self._load_sheets()
            return

        try:
            active_name = ""
            try:
                awb = self.conn.app.ActiveWorkbook
                if awb is not None:
                    active_name = awb.Name
            except Exception:
                pass

            idx_active = -1
            i = 0
            for wb in self.conn.app.Workbooks:
                try:
                    nm = wb.Name
                except Exception:
                    continue
                self.cbo_wb.addItem(nm)
                if nm == active_name:
                    idx_active = i
                i += 1

            if idx_active >= 0:
                self.cbo_wb.setCurrentIndex(idx_active)
        except Exception as e:
            print("加载工作簿列表失败:", e)

        self._load_sheets()

    def _on_wb_changed(self, _index):
        self._load_sheets()

    def _get_selected_wb(self):
        name = self.cbo_wb.currentText().strip()
        if not name or self.conn.app is None:
            return None
        try:
            return self.conn.app.Workbooks(name)
        except Exception:
            return None

    def _load_sheets(self):
        self.list_sheets.clear()
        wb = self._get_selected_wb()
        if wb is None:
            return
        try:
            for sh in wb.Sheets:
                try:
                    n = sh.Name
                except Exception:
                    continue
                if n == "合计":
                    continue
                item = QListWidgetItem(n)
                item.setSelected(True)
                self.list_sheets.addItem(item)
        except Exception as e:
            print("加载 sheet 列表失败:", e)

    def _set_all(self, flag):
        for i in range(self.list_sheets.count()):
            self.list_sheets.item(i).setSelected(flag)

    # ---------- 输入框联动 ----------
    def _on_manual_changed(self, text):
        has_manual = bool(text.strip())
        self.list_sheets.setEnabled(not has_manual)
        if has_manual:
            self.list_sheets.setStyleSheet("color: gray;")
        else:
            self.list_sheets.setStyleSheet("")

    def _parse_manual_persons(self, raw):
        for sep in ["，", "、", ";", "；", "\n", "\r", "\t", "|"]:
            raw = raw.replace(sep, ",")
        parts = []
        for p in raw.split(","):
            p = p.strip()
            if p:
                parts.append(p)
        return parts

    # ---------- 查询 ----------
    def do_query(self):
        day_str = self.txt_day.text().strip()
        try:
            day = int(day_str)
            if day < 1 or day > 31:
                raise ValueError
        except ValueError:
            self.txt_result.setPlainText("请输入 1-31 的日期。")
            return

        wb = self._get_selected_wb()
        if wb is None:
            self.txt_result.setPlainText("请选择一个工作簿。")
            return

        raw_manual = self.txt_persons_manual.text().strip()
        if raw_manual:
            selected = self._parse_manual_persons(raw_manual)
        else:
            selected = [i.text() for i in self.list_sheets.selectedItems()]

        if not selected:
            self.txt_result.setPlainText("请至少指定一个人（输入框或勾选列表）。")
            return

        # 去重但保持输入顺序
        seen = set()
        ordered = []
        for n in selected:
            if n not in seen:
                seen.add(n)
                ordered.append(n)
        selected = ordered

        row = day + 2

        try:
            wb_name = wb.Name
        except Exception:
            wb_name = "?"

        lines = [f"工作簿：{wb_name}", f"日期：{day} 号（第 {row} 行）", "=" * 40]

        missing_sheets = []
        try:
            all_names = set()
            for sh in wb.Sheets:
                try:
                    all_names.add(sh.Name)
                except Exception:
                    continue
            for n in selected:
                if n not in all_names:
                    missing_sheets.append(n)
        except Exception:
            pass

        total_overall = 0
        any_data = False

        try:
            try:
                self.conn.app.ScreenUpdating = False
            except Exception:
                pass

            for sheet_name in selected:
                try:
                    sh = wb.Sheets(sheet_name)
                except Exception:
                    continue

                try:
                    last_col = self.conn.scan_last_model_col(sh)
                except Exception:
                    continue
                if last_col < 2:
                    continue

                try:
                    rng_h = sh.Range(sh.Cells(2, 2), sh.Cells(2, last_col))
                    rng_v = sh.Range(sh.Cells(row, 2), sh.Cells(row, last_col))
                    headers = rng_h.Value
                    values = rng_v.Value
                    if not isinstance(headers, tuple):
                        headers = (headers,)
                    if not isinstance(values, tuple):
                        values = (values,)
                    if headers and isinstance(headers[0], tuple):
                        headers = headers[0]
                    if values and isinstance(values[0], tuple):
                        values = values[0]
                except Exception as e:
                    print(f"读 {sheet_name} 失败: {e}")
                    continue

                items = []
                sheet_total = 0
                for h, v in zip(headers, values):
                    if h is None:
                        continue
                    hs = str(h).strip()
                    if not hs:
                        continue
                    try:
                        v_num = float(v) if v is not None else 0
                    except (ValueError, TypeError):
                        v_num = 0
                    if v_num == 0:
                        continue
                    items.append((hs, v_num))
                    sheet_total += v_num

                if items:
                    any_data = True
                    lines.append("")
                    lines.append(f"【{sheet_name}】")
                    for name, val in items:
                        val_str = str(int(val)) if val == int(val) else f"{val:g}"
                        lines.append(f"    {name}：{val_str}")
                    if len(items) > 1:
                        ts = str(int(sheet_total)) if sheet_total == int(sheet_total) \
                            else f"{sheet_total:g}"
                        lines.append(f"    小计：{ts}")
                    total_overall += sheet_total
        finally:
            try:
                self.conn.app.ScreenUpdating = True
            except Exception:
                pass

        if missing_sheets:
            lines.append("")
            lines.append("未找到以下 sheet：")
            for n in missing_sheets:
                lines.append(f"    · {n}")

        if not any_data:
            lines.append("")
            lines.append(f"{day} 号没有任何记录。")
        else:
            lines.append("")
            lines.append("=" * 40)
            ts = str(int(total_overall)) if total_overall == int(total_overall) \
                else f"{total_overall:g}"
            lines.append(f"总计：{ts}")

        self.txt_result.setPlainText("\n".join(lines))

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.close()
            return
        super().keyPressEvent(event)


class GlobalQueryDialog(QDialog):
    def __init__(self, conn, parent=None):
        super().__init__(parent)
        self.setWindowTitle("综合数据查询")
        self.resize(700, 650)
        self.conn = conn
        self.person_map = {}  # 保存人员与工作簿的映射关系
        self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)

        layout = QVBoxLayout(self)

        row1 = QHBoxLayout()
        row1.addWidget(QLabel("人员姓名："))
        self.cbo_person = QComboBox()
        self.cbo_person.setEditable(True)  # 允许手动输入
        self.cbo_person.setMinimumWidth(250)

        # 开启模糊查询（包含匹配）
        completer = self.cbo_person.completer()
        if completer:
            completer.setFilterMode(Qt.MatchContains)
            completer.setCompletionMode(QCompleter.PopupCompletion)
            completer.setCaseSensitivity(Qt.CaseInsensitive)

        # 绑定文本变化，实现联动
        self.cbo_person.currentTextChanged.connect(self._on_person_changed)
        row1.addWidget(self.cbo_person)

        row1.addWidget(QLabel("日期："))
        self.txt_day = QLineEdit()
        self.txt_day.setPlaceholderText("留空=查所有日期")
        row1.addWidget(self.txt_day)

        layout.addLayout(row1)

        layout.addWidget(QLabel("选择需要查询的工作簿（当前WPS已打开）："))
        self.list_wbs = QListWidget()
        self.list_wbs.setSelectionMode(QListWidget.MultiSelection)
        self.list_wbs.setMaximumHeight(120)
        layout.addWidget(self.list_wbs)

        self._load_workbooks_and_persons()

        btn_row = QHBoxLayout()
        btn_all = QPushButton("全选")
        btn_all.clicked.connect(lambda: self._set_all_wbs(True))
        btn_row.addWidget(btn_all)
        btn_none = QPushButton("全不选")
        btn_none.clicked.connect(lambda: self._set_all_wbs(False))
        btn_row.addWidget(btn_none)

        btn_query = QPushButton("开始查询")
        btn_query.clicked.connect(self.do_query)
        btn_query.setStyleSheet("background-color: #0078D7; color: white; font-weight: bold;")
        btn_row.addWidget(btn_query)

        layout.addLayout(btn_row)

        self.txt_result = QPlainTextEdit()
        self.txt_result.setReadOnly(True)
        layout.addWidget(self.txt_result, 1)

        btn_close = QPushButton("关闭")
        btn_close.clicked.connect(self.close)
        layout.addWidget(btn_close)

    def _on_person_changed(self, text):
        """人员变动时，联动过滤下方的工作簿列表"""
        person = re.sub(r'\(.*\)$', '', text).strip()

        if not person:
            self.list_wbs.clear()
            return

        # 如果提取到的名字存在于映射表中，只显示对应的工作簿
        if person in self.person_map:
            wbs = self.person_map[person]
            self.list_wbs.clear()
            for wb in sorted(set(wbs)):
                item = QListWidgetItem(wb)
                item.setSelected(True)
                self.list_wbs.addItem(item)
        # 如果输入不完整（如只输入了“李金”），不清空列表，避免闪烁

    def _read_range(self, rng):
        """统一处理 Excel Range.Value 返回值，确保始终返回二维元组"""
        vals = rng.Value
        if vals is None:
            return ()
        if not isinstance(vals, tuple):
            return ((vals,),)
        if not isinstance(vals[0], tuple):
            return (vals,)
        return vals

    def _load_workbooks_and_persons(self):
        self.list_wbs.clear()
        self.cbo_person.clear()
        self.person_map.clear()

        if self.conn.app is None:
            try:
                self.conn.connect()
            except Exception:
                pass
        if self.conn.app is None:
            return

        try:
            for wb in self.conn.app.Workbooks:
                wb_name = wb.Name
                for sh in wb.Sheets:
                    sh_name = sh.Name
                    if sh_name == "合计":
                        continue

                    # 1. 一般排单表：Sheet名就是人名
                    if re.match(r'^[\u4e00-\u9fa5]{2,4}$', sh_name):
                        self.person_map.setdefault(sh_name, []).append(wb_name)
                    # 2. 检查表头是否有“姓名”列
                    else:
                        used = sh.UsedRange
                        max_r = min(used.Row + used.Rows.Count - 1, 50)
                        max_c = min(used.Column + used.Columns.Count - 1, 20)
                        if max_r < 1 or max_c < 1:
                            continue

                        r_limit = min(5, max_r)
                        header_data = self._read_range(sh.Range(sh.Cells(1, 1), sh.Cells(r_limit, max_c)))

                        col_person = -1
                        for r_idx, row in enumerate(header_data):
                            for c_idx, v in enumerate(row):
                                if v and "姓名" in str(v):
                                    col_person = c_idx + 1
                                    break
                            if col_person > 0:
                                break

                        if col_person > 0:
                            # 批量读取该列的所有姓名数据
                            col_vals = self._read_range(sh.Range(sh.Cells(1, col_person), sh.Cells(max_r, col_person)))
                            for row_vals in col_vals:
                                v = row_vals[0] if row_vals else None
                                if v and str(v).strip() and str(v).strip() != "姓名":
                                    name = str(v).strip()
                                    if wb_name not in self.person_map.get(name, []):
                                        self.person_map.setdefault(name, []).append(wb_name)

            # 生成下拉框选项
            for name, wbs in sorted(self.person_map.items()):
                wb_str = ",".join(sorted(set(wbs)))
                self.cbo_person.addItem(f"{name}({wb_str})")

            # 如果加载到了人，默认选中第一个，触发一次联动
            if self.cbo_person.count() > 0:
                self.cbo_person.setCurrentIndex(0)

        except Exception as e:
            print("加载工作簿失败:", e)

    def _set_all_wbs(self, flag):
        for i in range(self.list_wbs.count()):
            self.list_wbs.item(i).setSelected(flag)

    def do_query(self):
        # 从下拉框提取真实人名（去掉括号部分）
        raw_person = self.cbo_person.currentText().strip()
        person = re.sub(r'\(.*\)$', '', raw_person).strip()

        date_str = self.txt_day.text().strip()

        if not person:
            QMessageBox.warning(self, "提示", "请输入或选择人员姓名")
            return

        selected_wbs = [i.text() for i in self.list_wbs.selectedItems()]
        if not selected_wbs:
            QMessageBox.warning(self, "提示", "请至少选择一个工作簿")
            return

        self.txt_result.clear()
        self.txt_result.appendPlainText(f"正在查询：{person} ... 请稍候\n")
        QApplication.processEvents()  # 刷新界面

        results = defaultdict(lambda: defaultdict(lambda: defaultdict(float)))

        try:
            self.conn.app.ScreenUpdating = False
            self.conn.app.Calculation = -4135  # 手动计算，提速
        except Exception:
            pass

        total_grand = 0
        model_grand = defaultdict(float)

        for wb_name in selected_wbs:
            try:
                wb = self.conn.app.Workbooks(wb_name)
            except Exception:
                continue

            for sh in wb.Sheets:
                try:
                    sh_name = sh.Name
                except Exception:
                    continue

                if sh_name == person:
                    self._parse_paidan_sheet(sh, wb_name, date_str, results)
                elif "退打磨" in wb_name:
                    self._parse_tuimoda_sheet(sh, wb_name, date_str, results)
                else:
                    self._parse_generic_sheet(sh, wb_name, person, date_str, results)

        try:
            self.conn.app.ScreenUpdating = True
            self.conn.app.Calculation = -4105
        except Exception:
            pass

        # 生成报告
        report_lines = []
        for wb_name, types_data in results.items():
            report_lines.append(f"【{wb_name}】")
            wb_total = 0

            for type_name, models_data in types_data.items():
                if not models_data:
                    continue
                report_lines.append(f"  -- {type_name} --")
                type_total = 0
                for model, qty in sorted(models_data.items()):
                    if qty > 0:
                        report_lines.append(f"      {model} : {int(qty) if qty.is_integer() else qty}")
                        type_total += qty
                        model_grand[model] += qty
                if type_total > 0:
                    report_lines.append(f"      小计：{int(type_total) if type_total.is_integer() else type_total}")
                    wb_total += type_total

            if wb_total > 0:
                report_lines.append(f"  >> {wb_name} 总计：{int(wb_total) if wb_total.is_integer() else wb_total}\n")
                total_grand += wb_total
            else:
                report_lines.append("  (无符合条件的数据)\n")

        if not results or total_grand == 0:
            self.txt_result.appendPlainText(f"未找到 {person} 的符合条件的记录。")
        else:
            report_lines.append("=" * 30)
            report_lines.append("【全部型号汇总】")
            for model, qty in sorted(model_grand.items()):
                report_lines.append(f"    {model} : {int(qty) if qty.is_integer() else qty}")
            report_lines.append("=" * 30)
            report_lines.append(f"总计数量：{int(total_grand) if total_grand.is_integer() else total_grand}")

            self.txt_result.setPlainText("\n".join(report_lines))

    def _parse_paidan_sheet(self, sh, wb_name, date_str, results):
        try:
            used = sh.UsedRange
            last_col = min(used.Column + used.Columns.Count - 1, 200)
            if last_col < 2: return

            if date_str:
                # 查特定天，一次性读该天所在行
                try:
                    day = int(date_str)
                except:
                    return
                r = day + 2
                if not (3 <= r <= 33): return

                rng_h = self._read_range(sh.Range(sh.Cells(2, 2), sh.Cells(2, last_col)))[0]
                rng_v = self._read_range(sh.Range(sh.Cells(34, 2), sh.Cells(34, last_col)))[0]
                rng_day = self._read_range(sh.Range(sh.Cells(r, 2), sh.Cells(r, last_col)))[0]

                for h, v, d in zip(rng_h, rng_v, rng_day):
                    if h is not None and d is not None and str(d).strip() != "":
                        q = float(v) if v is not None else 0
                        if q == 0:
                            try:
                                q = float(d)
                            except:
                                q = 1
                        if q > 0:
                            results[wb_name]["排单表(按天)"][str(h).strip()] += q
            else:
                # 查全周期，直接加总
                rng_h = self._read_range(sh.Range(sh.Cells(2, 2), sh.Cells(2, last_col)))[0]
                rng_v = self._read_range(sh.Range(sh.Cells(34, 2), sh.Cells(34, last_col)))[0]
                for h, v in zip(rng_h, rng_v):
                    if h is not None and v is not None:
                        try:
                            q = float(v)
                            if q > 0:
                                results[wb_name]["排单表(全周期)"][str(h).strip()] += q
                        except:
                            pass
        except Exception:
            pass

    def _parse_tuimoda_sheet(self, sh, wb_name, date_str, results):
        try:
            used = sh.UsedRange
            max_r = used.Row + used.Rows.Count - 1
            if max_r < 3: return

            # 一次性读取 A列(日期) 到 D列(数量)
            rng = self._read_range(sh.Range(sh.Cells(3, 1), sh.Cells(max_r, 4)))
            current_day = None
            for row in rng:
                if not row or len(row) < 4: continue
                a_val = row[0]
                if a_val is not None and str(a_val).strip() != "":
                    current_day = str(a_val).strip()

                if date_str and current_day != date_str:
                    continue

                model = row[2]
                qty = row[3]
                if model and qty:
                    try:
                        q = float(qty)
                        results[wb_name]["退打磨"][str(model).strip()] += q
                    except:
                        pass
        except Exception:
            pass

    def _parse_generic_sheet(self, sh, wb_name, person, date_str, results):
        try:
            used = sh.UsedRange
            max_r = used.Row + used.Rows.Count - 1
            max_c = used.Column + used.Columns.Count - 1
            if max_r < 2 or max_c < 2: return

            # 批量读取找表头
            r_limit = min(10, max_r)
            c_limit = min(30, max_c)
            header_data = self._read_range(sh.Range(sh.Cells(1, 1), sh.Cells(r_limit, c_limit)))

            col_person, col_model, col_qty, col_date, header_row = -1, -1, -1, -1, -1

            for r_idx, row in enumerate(header_data):
                for c_idx, v in enumerate(row):
                    if v is None: continue
                    s = str(v).strip()
                    if "姓名" in s or "人员" in s:
                        col_person = c_idx + 1;
                        header_row = r_idx + 1
                    elif "型号" in s or "产品" in s:
                        col_model = c_idx + 1;
                        header_row = r_idx + 1
                    elif "数量" in s or "产量" in s:
                        col_qty = c_idx + 1;
                        header_row = r_idx + 1
                    elif "日期" in s or "时间" in s:
                        col_date = c_idx + 1;
                        header_row = r_idx + 1

            if col_model > 0 and col_qty > 0 and header_row > 0 and col_person > 0:
                if header_row + 1 <= max_r:
                    # 一次性读取数据区域
                    rng = self._read_range(sh.Range(sh.Cells(header_row + 1, 1), sh.Cells(max_r, max_c)))
                    for row in rng:
                        if not row or len(row) < max(col_person, col_model, col_qty): continue

                        p_val = row[col_person - 1]
                        if p_val is None or str(p_val).strip() != person: continue

                        if date_str and col_date > 0:
                            d_val = row[col_date - 1]
                            if d_val is None or str(d_val).strip() != date_str: continue

                        model = row[col_model - 1]
                        qty = row[col_qty - 1]
                        if model and qty:
                            try:
                                q = float(qty)
                                results[wb_name][f"{sh.Name}"][str(model).strip()] += q
                            except:
                                pass
        except Exception:
            pass


class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("打磨录入工具")
        self.resize(880, 380)

        self.settings = QSettings("config.ini", QSettings.IniFormat)

        # ---- 状态变量先置空 ----
        self.conn = None
        self.price_table = None
        self.manager = None
        self._scanned_workbooks = set()
        self._verified_workbooks = set()
        self._missing_prices = []
        self._last_workbook = ""
        self._last_sheet = ""
        self._restoring = False
        self.batch_mode = False
        self.batch_persons = []
        self.batch_index = 0
        self.batch_model = ""
        self.batch_history = []

        try:
            on_top = int(self.settings.value("window_on_top", 1, type=int))
        except Exception:
            on_top = 1
        if on_top:
            self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)

        # ---- 先建 UI ----
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

        self.log.setText("正在初始化...")

        self.timer = QTimer()
        self.timer.timeout.connect(self.monitor_wps)

        self._batch_jump_timer = QTimer(self)
        self._batch_jump_timer.setSingleShot(True)
        self._batch_jump_timer.timeout.connect(self._batch_do_jump)

        QTimer.singleShot(0, self._deferred_init)

    def _deferred_init(self):
        self.conn = WPSConnector()
        self.conn.connect()

        self.price_table = PriceTable()
        price_path = self.settings.value("price_file", "", type=str)
        if price_path:
            self.price_table.set_path(price_path)
            self.price_table.load()

        self.manager = EntryManager(self.conn, price_table=self.price_table)

        if self.price_table.loaded:
            self.log.setText(f"单价表已加载（{len(self.price_table.data)} 个型号）")
        else:
            self.log.setText("提示：点击'单价表'按钮选择单价表文件")

        self.refresh_sheets()
        self.timer.start(500)

        self._batch_jump_timer = QTimer(self)
        self._batch_jump_timer.setSingleShot(True)
        self._batch_jump_timer.timeout.connect(self._batch_do_jump)

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

        btn_redo = QPushButton("回退")  # <--- 新增
        btn_redo.clicked.connect(self.do_redo)  # <--- 新增
        btn_layout.addWidget(btn_redo)  # <--- 新增

        btn_multi = QPushButton("多人合作")
        btn_multi.clicked.connect(self.do_multi)
        btn_layout.addWidget(btn_multi)

        self.btn_batch = QPushButton("批量录入")
        self.btn_batch.clicked.connect(self.do_batch_start)
        btn_layout.addWidget(self.btn_batch)

        btn_add = QPushButton("新增人员")
        btn_add.clicked.connect(self.do_add_person)
        btn_layout.addWidget(btn_add)

        btn_clean_sheets = QPushButton("清理离职表")
        btn_clean_sheets.clicked.connect(self.do_clean_empty_sheets)
        btn_layout.addWidget(btn_clean_sheets)

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

        # --- 检查排版按钮 ---
        btn_margin = QPushButton("检查排版(边距/横打)")
        btn_margin.clicked.connect(self.do_check_margins)
        btn_layout.addWidget(btn_margin)

        btn_summary = QPushButton("修帽子合计统计")
        btn_summary.clicked.connect(self.do_make_summary)
        btn_layout.addWidget(btn_summary)

        btn_query = QPushButton("查询某天记录")
        btn_query.clicked.connect(self.do_query_date)
        btn_layout.addWidget(btn_query)

        btn_global_query = QPushButton("🔍 跨表综合查询")
        btn_global_query.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold;")
        btn_global_query.clicked.connect(self.do_global_query)
        btn_layout.addWidget(btn_global_query)

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

        row7 = QHBoxLayout()
        row7.addWidget(QLabel("批量跳转延迟(毫秒)："))
        self.spin_jump = QSpinBox()
        self.spin_jump.setRange(0, 10000)
        self.spin_jump.setSingleStep(100)
        try:
            _d = int(self.settings.value("batch_jump_delay_ms", 500, type=int))
        except Exception:
            _d = 500
        if _d < 0:
            _d = 0
        if _d > 10000:
            _d = 10000
        self.spin_jump.setValue(_d)
        self.spin_jump.valueChanged.connect(self.on_jump_delay_changed)
        row7.addWidget(self.spin_jump)
        row7.addStretch(1)
        layout.addLayout(row7)

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

    def on_jump_delay_changed(self, value):
        self.settings.setValue("batch_jump_delay", int(value))

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
        self._batch_jump_timer.stop()

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
        try:
            delay = int(self.spin_jump.value())
        except Exception:
            delay = 500
        self.log.setText(
            f"批量录入已开始：{first}（1/{total}）\n"
            f"请先输入型号，再输入数量。\n"
            f"录入完成后会在当前 sheet 停留 {delay} 毫秒供核对，然后自动跳转下一位。\n"
            f"发现录错可按 Ctrl+Z 或点'撤回'回退上一步。\n"
            f"想退出批量：点'退出批量'按钮 或 按 ESC。"
        )

    def do_batch_entry(self):
        if not self.batch_mode:
            return
        self._batch_jump_timer.stop()

        person = self.batch_persons[self.batch_index]
        total = len(self.batch_persons)

        m = self.txt_model.text().strip()
        if m:
            self.batch_model = m

        if not self.batch_model:
            self.log.setText("请先输入型号")
            self.txt_model.setFocus()
            return

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

        self.txt_qty.clear()

        idx = self.batch_index + 1
        if idx >= total:
            tip = "已是最后一位，稍后自动结束"
        else:
            nxt = self.batch_persons[self.batch_index + 1]
            tip = f"稍后自动跳转到 {nxt}"
        try:
            delay = int(self.spin_jump.value())
        except Exception:
            delay = 500
        self.log.setText(
            f"已录入 {person}（{idx}/{total}）：{self.batch_model} = {qty}\n"
            f"{tip}（延迟 {delay} 毫秒）\n"
            f"若要在当前 sheet 继续录入，可直接改型号/数量再回车；Ctrl+Z 撤回；ESC 退出"
        )

        self._batch_jump_timer.start(max(0, delay))
        self.txt_qty.setFocus()

    def _batch_do_jump(self):
        if not self.batch_mode:
            return

        total = len(self.batch_persons)
        expected = self.batch_persons[self.batch_index] if self.batch_index < total else ""

        try:
            current = self.conn.get_active_sheet_name()
        except Exception:
            current = ""
        if current and expected and current != expected:
            return

        self.batch_index += 1

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

        self.txt_qty.clear()
        self.txt_qty.setFocus()

        idx = self.batch_index + 1
        self.log.setText(
            f"批量录入：{self.batch_model} - {next_person}（{idx}/{total}）\n"
            f"请输入数量；Ctrl+Z 撤回上一步；ESC 退出批量"
        )

    def do_batch_undo(self):
        if not self.batch_history:
            QMessageBox.information(self, "批量回退",
                                    "没有可回退的操作（已经是第一步）")
            return

        self._batch_jump_timer.stop()
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

        try:
            self.batch_index = self.batch_persons.index(person)
        except ValueError:
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
        self._batch_jump_timer.stop()
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

        missing_info, err = self.manager.find_missing_prices(wb_name)
        if err:
            QMessageBox.warning(self, "检查缺失单价", err)
            return
        if not missing_info:
            QMessageBox.information(self, "检查缺失单价",
                                    "所有型号都能在单价表中找到单价。")
            self.log.setText("检查缺失单价：无缺失")
            return

        # 拼接详细报告文本
        lines = []
        for model, occurrences in missing_info.items():
            if occurrences:
                parts = []
                for person, days in occurrences.items():
                    if days:
                        days_str = ",".join(map(str, days))
                        parts.append(f"{person}({days_str}号)")
                    else:
                        parts.append(f"{person}(仅表头)")
                lines.append(f"· {model}  →  {'；'.join(parts)}")
            else:
                lines.append(f"· {model}  →  未找到是谁填的")

        msg = f"以下 {len(missing_info)} 个型号没有单价：\n\n" + "\n".join(lines)

        # 如果文本太长，截断防止弹窗卡死
        if len(msg) > 4000:
            msg = msg[:4000] + "\n\n……（内容过多，已截断，请补齐单价后重新检查）"

        QMessageBox.information(self, "检查缺失单价", msg)
        self.log.setText(f"缺失单价：共 {len(missing_info)} 个型号")

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
            # --- 新增：强制保存 ---
            try:
                wb = self.conn.get_active_workbook()
                if wb:
                    wb.Save()
            except Exception as e:
                QMessageBox.warning(self, "保存失败", f"公式修正成功，但保存文件时出错：{e}\n请手动按 Ctrl+S 保存。")

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

    def do_check_margins(self):
        # 先只检查
        ok, non_compliant, err = self.manager.check_and_fix_margins(fix=False)
        if not ok:
            QMessageBox.warning(self, "检查排版", err)
            return

        if not non_compliant:
            QMessageBox.information(self, "检查排版",
                                    "当前工作簿所有 sheet 的排版均符合要求：\n"
                                    "· 左边距 2cm，其余边距 1cm\n"
                                    "· 横向打印")
            self.log.setText("检查排版：全部符合要求")
            return

        preview = "、".join(non_compliant[:10])
        if len(non_compliant) > 10:
            preview += f" 等 {len(non_compliant)} 个"

        reply = QMessageBox.question(
            self, "检查排版",
            f"发现以下 {len(non_compliant)} 个 sheet 的排版不符合要求：\n{preview}\n\n"
            f"是否统一修改为（左边距 2cm，右/上/下边距 1cm）且【横向打印】？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes
        )
        if reply != QMessageBox.Yes:
            return

        # 执行修正
        ok, _, err2 = self.manager.check_and_fix_margins(fix=True)
        if ok:
            # 强制保存兜底
            try:
                wb = self.conn.get_active_workbook()
                if wb:
                    wb.Save()
            except Exception:
                pass
            QMessageBox.information(self, "检查排版", err2)
            self.log.setText(err2)
        else:
            QMessageBox.warning(self, "修正失败", err2)

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
        if self.conn is None:
            return
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
        QTimer.singleShot(50, self._refocus)
        QTimer.singleShot(200, self._refocus)

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
        # 批量模式特殊处理
        if self.batch_mode and self.batch_history:
            self.do_batch_undo()
            return

        # --- 撤回前预览 ---
        if not self.manager.undo_stack:
            QMessageBox.information(self, "撤回", "没有可撤回的操作。")
            return

        # 获取栈顶元素用于预览
        item = self.manager.undo_stack[-1]
        sheet_name = item["sheet_name"]
        row = item["row"]
        col = item["col"]

        # 将列号转为字母（如 2 -> B）
        def _col_letter(c):
            res = ""
            while c > 0:
                c, rem = divmod(c - 1, 26)
                res = chr(65 + rem) + res
            return res

        col_letter = _col_letter(col)

        if item["inserted"]:
            action_desc = f"【新插入列】：{sheet_name} 表的 {col_letter} 列"
        else:
            old_val = item["old_value"] if item["old_value"] is not None else "空"
            new_val = item.get("new_value") if item.get("new_value") is not None else "空"
            action_desc = f"【数据修改】：{sheet_name} 表的 {col_letter}{row} 单元格，将“{new_val}”恢复为“{old_val}”"

        reply = QMessageBox.question(
            self, "撤回确认",
            f"即将撤回以下操作，是否继续？\n\n{action_desc}",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes
        )
        if reply != QMessageBox.Yes:
            return

        ok, msg = self.manager.undo()
        self.log.setText(msg)
        if not ok:
            QMessageBox.warning(self, "撤回失败", msg)
        else:
            self.refresh_sheets()

    def do_redo(self):
        if self.batch_mode:
            QMessageBox.warning(self, "提示", "批量录入模式下暂不支持重做。")
            return

        if not self.manager.redo_stack:
            QMessageBox.information(self, "重做", "没有可重做的操作。")
            return

        # 获取栈顶元素用于预览
        item = self.manager.redo_stack[-1]
        sheet_name = item["sheet_name"]
        row = item["row"]
        col = item["col"]

        def _col_letter(c):
            res = ""
            while c > 0:
                c, rem = divmod(c - 1, 26)
                res = chr(65 + rem) + res
            return res

        col_letter = _col_letter(col)

        if item["inserted"]:
            action_desc = f"【重新插入列】：{sheet_name} 表的 {col_letter} 列"
        else:
            new_val = item.get("new_value") if item.get("new_value") is not None else "空"
            action_desc = f"【重新写入】：{sheet_name} 表的 {col_letter}{row} 单元格，将改回“{new_val}”"

        reply = QMessageBox.question(
            self, "回退确认",
            f"即将回退以下操作，是否继续？\n\n{action_desc}",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes
        )

        if reply != QMessageBox.Yes:
            return

        ok, msg = self.manager.redo()
        self.log.setText(msg)
        if not ok:
            QMessageBox.warning(self, "重做失败", msg)
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

    def do_clean_empty_sheets(self):
        """扫描并删除 3-33 行完全没有数据的 sheet（离职/空表）"""
        empty, err = self.manager.find_empty_sheets()
        if err:
            QMessageBox.warning(self, "清理离职表", err)
            return
        if not empty:
            QMessageBox.information(self, "清理离职表",
                                    "所有 sheet 都有数据，无需清理。")
            self.log.setText("清理离职表：无空表")
            return

        preview = "\n".join(f"· {n}" for n in empty[:30])
        if len(empty) > 30:
            preview += f"\n…… 共 {len(empty)} 个"

        msg = (
            f"以下 {len(empty)} 个 sheet 从 3 行到 33 行完全没有数据：\n\n"
            f"{preview}\n\n"
            f"是否删除这些 sheet？删除后无法自动恢复。"
        )

        reply = QMessageBox.question(
            self, "清理离职表", msg,
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            self.log.setText("已取消清理。")
            return

        ok, msg2 = self.manager.delete_sheets(empty)

        if ok:
            # --- 新增：强制保存 ---
            try:
                wb = self.conn.get_active_workbook()
                if wb:
                    wb.Save()
            except Exception as e:
                QMessageBox.warning(self, "保存失败", f"清理成功，但保存文件时出错：{e}\n请手动按 Ctrl+S 保存。")

        self.log.setText(msg2)
        if ok:
            QMessageBox.information(self, "清理离职表", msg2)
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

        if ok:
            # --- 新增：强制保存 ---
            try:
                wb = self.conn.get_active_workbook()
                if wb:
                    wb.Save()
            except Exception as e:
                QMessageBox.warning(self, "保存失败", f"清理成功，但保存文件时出错：{e}\n请手动按 Ctrl+S 保存。")

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

    def do_query_date(self):
        dlg = QueryDateDialog(self.conn, self)
        dlg.exec()

    def do_global_query(self):
        dlg = GlobalQueryDialog(self.conn, self)
        dlg.exec()

    def closeEvent(self, event):
        try:
            self.timer.stop()
        except Exception:
            pass
        try:
            self._batch_jump_timer.stop()
        except Exception:
            pass
        try:
            self.conn.wb = None
        except Exception:
            pass
        event.accept()
        try:
            QApplication.instance().quit()
        except Exception:
            pass


def run():
    import sys
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    run()