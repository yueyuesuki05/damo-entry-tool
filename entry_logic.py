# @Version  : 1.0
# @Author   : 小野
# @File     : entry_logic.py
# @Time     : 2026/9/30 13:18

from model_sort import (
    normalize_model, model_sort_key, find_insert_position,
    to_chinese_suffix
)


class EntryManager:
    def __init__(self, connector, price_table=None):
        self.conn = connector
        self.price_table = price_table
        self.undo_stack = []

    def _is_ganmo(self, wb_name):
        return "干磨" in wb_name

    def _is_special(self, name):
        return str(name).strip() in ("时间", "样品")

    def _eval_quantity(self, expr):
        expr = str(expr).replace(" ", "")
        allowed = set("0123456789.+-*/()")
        if not all(ch in allowed for ch in expr):
            return None
        try:
            return eval(expr, {"__builtins__": {}}, {})
        except Exception:
            return None

    def _record_undo(self, wb_name, sheet_name, row, col, old_value, inserted):
        self.undo_stack.append({
            "wb_name": wb_name,
            "sheet_name": sheet_name,
            "row": row,
            "col": col,
            "old_value": old_value,
            "inserted": inserted,
        })

    def _col_letter(self, col):
        result = ""
        while col > 0:
            col, rem = divmod(col - 1, 26)
            result = chr(65 + rem) + result
        return result

    def _safe_save(self, wb):
        """安全保存：关掉弹窗，静默保存，失败不崩"""
        try:
            try:
                self.conn.app.DisplayAlerts = False
            except Exception:
                pass
            try:
                wb.Save()
            except Exception as e:
                print("保存失败:", e)
            try:
                self.conn.app.DisplayAlerts = True
            except Exception:
                pass
        except Exception:
            pass

    # ---------- 单价 ----------
    def _fill_price_for_col(self, sh, col, model_name):
        if self.price_table is None or not self.price_table.loaded:
            return False, ""
        if self._is_special(model_name):
            return True, ""

        price = self.price_table.get_price(model_name)
        if price is None:
            return False, f"{model_name} 未找到单价"

        try:
            old = sh.Cells(35, col).Value
        except Exception:
            old = None

        if old is not None:
            try:
                if abs(float(old) - price) < 0.0001:
                    return True, ""
            except (ValueError, TypeError):
                pass

        try:
            sh.Cells(35, col).Value = price
            return True, ""
        except Exception as e:
            print("写单价失败:", e)
            return False, ""

    def scan_and_fill_prices(self, wb_name):
        if self.price_table is None or not self.price_table.loaded:
            return []
        if "干磨" not in wb_name:
            return []

        wb = self.conn.get_active_workbook()
        if wb is None:
            return []

        missing = []
        try:
            for sh in wb.Sheets:
                try:
                    sh_name = sh.Name
                except Exception:
                    continue
                if sh_name == "合计":
                    continue

                try:
                    last_col = self.conn.scan_last_model_col(sh)
                except Exception:
                    continue
                if last_col < 2:
                    continue

                for c in range(2, last_col + 1):
                    try:
                        header = sh.Cells(2, c).Value
                    except Exception:
                        continue
                    if header is None:
                        continue
                    name = str(header).strip()

                    try:
                        f = float(name)
                        if f == int(f):
                            name = str(int(f))
                    except (ValueError, TypeError):
                        pass

                    if name == "" or self._is_special(name):
                        continue

                    ok, msg = self._fill_price_for_col(sh, c, name)
                    if not ok and msg:
                        missing.append(f"{sh_name}/{name}")
        except Exception as e:
            print("扫描单价失败:", e)

        if missing is not None:
            self._safe_save(wb)

        return missing

    def find_missing_prices(self, wb_name):
        if self.price_table is None or not self.price_table.loaded:
            return [], "单价表未加载"
        if "干磨" not in wb_name:
            return [], f"当前工作簿不是干磨表：{wb_name}"

        wb = self.conn.get_active_workbook()
        if wb is None:
            return [], "未检测到活动工作簿"

        missing_set = set()

        try:
            self.conn.app.ScreenUpdating = False
        except Exception:
            pass
        try:
            self.conn.app.Calculation = -4135
        except Exception:
            pass
        try:
            self.conn.app.EnableEvents = False
        except Exception:
            pass

        try:
            for sh in wb.Sheets:
                try:
                    sh_name = sh.Name
                except Exception:
                    continue
                if sh_name == "合计":
                    continue

                try:
                    last_col = self.conn.scan_last_model_col(sh)
                except Exception:
                    continue
                if last_col < 2:
                    continue

                try:
                    rng = sh.Range(sh.Cells(2, 2), sh.Cells(2, last_col))
                    headers = rng.Value
                    if not isinstance(headers, tuple):
                        headers = (headers,)
                    if headers and isinstance(headers[0], tuple):
                        headers = headers[0]
                except Exception:
                    continue

                for h in headers:
                    if h is None:
                        continue
                    name = str(h).strip()
                    if name == "" or self._is_special(name):
                        continue
                    try:
                        f = float(name)
                        if f == int(f):
                            name = str(int(f))
                    except (ValueError, TypeError):
                        pass

                    price = self.price_table.get_price(name)
                    if price is None:
                        missing_set.add(name)
        except Exception as e:
            return [], f"扫描失败：{e}"
        finally:
            try:
                self.conn.app.ScreenUpdating = True
            except Exception:
                pass
            try:
                self.conn.app.Calculation = -4105
            except Exception:
                pass
            try:
                self.conn.app.EnableEvents = True
            except Exception:
                pass

        return sorted(missing_set), ""

    # ---------- 录入 ----------
    def entry(self, sheet_name, day, model, expr):
        if self.price_table is not None:
            try:
                self.price_table.reload_if_changed()
            except Exception:
                pass

        wb = self.conn.get_active_workbook()
        if wb is None:
            return False, "未检测到活动工作簿，请先在 WPS 中打开文件。"

        try:
            wb_name = wb.Name
        except Exception:
            return False, "工作簿已失效，请重新打开文件。"

        sh = self.conn.get_sheet(sheet_name)
        if sh is None:
            return False, f"找不到 sheet：{sheet_name}"

        try:
            sh.Activate()
        except Exception:
            pass

        try:
            day_int = int(day)
            if day_int < 1 or day_int > 31:
                raise ValueError
        except Exception:
            return False, "日期必须是 1-31 的整数。"

        row = day_int + 2

        qty = self._eval_quantity(expr)
        if qty is None:
            return False, f"数量表达式不合法：{expr}"

        model_norm = normalize_model(model)

        col = self.conn.find_model_column(sh, model_norm)
        inserted = False

        if col == 0:
            display_name = to_chinese_suffix(model_norm)
            is_time = (display_name == "时间")
            is_sample = (display_name == "样品")

            last_col = self.conn.scan_last_model_col(sh)
            existing = []
            try:
                rng = sh.Range(sh.Cells(2, 2), sh.Cells(2, last_col))
                vals = rng.Value
                if isinstance(vals, tuple):
                    row_vals = vals[0]
                else:
                    row_vals = (vals,)
                for v in row_vals:
                    if v is not None:
                        existing.append(str(v))
            except Exception:
                pass

            time_col = None
            if existing and existing[-1] == "时间":
                time_col = last_col
            insert_end = (time_col - 1) if time_col else last_col
            pos = find_insert_position(existing[:insert_end - 1], display_name)
            insert_col = 2 + pos
            if time_col and insert_col > time_col - 1:
                insert_col = time_col

            ok = self.conn.insert_column(sh, insert_col)
            if not ok:
                return False, (
                    "WPS 拒绝插入新列。请在该 sheet 中按 Ctrl+End，"
                    "看是否跳到了很远的单元格；如果是，删除该整行/整列，"
                    "保存并重新打开 WPS，然后再录入。"
                )
            self.conn.set_header_text_format(sh, insert_col)
            sh.Cells(2, insert_col).Value = display_name

            col_letter = self._col_letter(insert_col)

            self.conn.write_formula(sh, 34, insert_col,
                                    f"=SUM({col_letter}3:{col_letter}33)")

            if self._is_ganmo(wb_name) and not is_time and not is_sample:
                self.conn.write_formula(sh, 36, insert_col,
                                        f"={col_letter}34*{col_letter}35")

            col = insert_col
            inserted = True
            model_norm = display_name

        old_value = self.conn.read_cell(sh, row, col)
        if old_value is None:
            old_value = 0
        try:
            old_num = float(old_value)
        except (ValueError, TypeError):
            old_num = 0

        if old_num != 0:
            self.conn.write_cell(sh, row, col, old_num + qty)
        else:
            self.conn.write_cell(sh, row, col, qty)

        price_msg = ""
        if self._is_ganmo(wb_name):
            ok_price, price_msg = self._fill_price_for_col(sh, col, model_norm)
            if not ok_price and not price_msg:
                price_msg = ""

        self._update_total(sh, wb_name)
        self._record_undo(wb_name, sheet_name, row, col, old_value, inserted)

        self._safe_save(wb)

        try:
            sh.Cells(row, col).Select()
        except Exception:
            pass

        result = f"已录入 {model_norm} = {qty}（{day}日）"
        if price_msg:
            result += f"    [{price_msg}]"
        return True, result

    def _update_total(self, sh, wb_name):
        last_col = self.conn.scan_last_model_col(sh)
        if last_col < 2:
            return

        headers = ()
        try:
            rng = sh.Range(sh.Cells(2, 2), sh.Cells(2, last_col))
            hh = rng.Value
            if not isinstance(hh, tuple):
                hh = (hh,)
            if hh and isinstance(hh[0], tuple):
                hh = hh[0]
            headers = hh
        except Exception:
            headers = ()

        if self._is_ganmo(wb_name):
            skip = ("时间", "样品")
        else:
            skip = ("时间",)

        effective_last = None
        for i in range(len(headers) - 1, -1, -1):
            h = headers[i]
            if h is None:
                continue
            hs = str(h).strip()
            if hs == "":
                continue
            if hs in skip:
                continue
            effective_last = 2 + i
            break

        if self._is_ganmo(wb_name):
            total_row = 37
            sum_row = 36
        else:
            total_row = 35
            sum_row = 34

        try:
            start_letter = self._col_letter(1)
            end_letter = self._col_letter(last_col + 2)
            sh.Range(f"{start_letter}{total_row}:{end_letter}{total_row}").ClearContents()
        except Exception as e:
            print("清空总计失败:", e)

        if effective_last is None:
            return

        if effective_last == 2:
            label_col = effective_last
            formula_col = effective_last + 1
        else:
            label_col = effective_last - 1
            formula_col = effective_last

        try:
            sh.Cells(total_row, label_col).Value = "总计："
            start = self._col_letter(2)
            end = self._col_letter(effective_last)
            self.conn.write_formula(sh, total_row, formula_col,
                                    f"=SUM({start}{sum_row}:{end}{sum_row})")
        except Exception as e:
            print("写总计失败:", e)

    def undo(self):
        if not self.undo_stack:
            return False, "没有可撤回的操作。"
        item = self.undo_stack.pop()
        wb = self.conn.get_active_workbook()
        if wb is None:
            return False, "未检测到活动工作簿。"
        sh = wb.Sheets(item["sheet_name"])
        if item["inserted"]:
            sh.Columns(item["col"]).Delete()
        else:
            sh.Cells(item["row"], item["col"]).Value = item["old_value"]
        self._update_total(sh, wb.Name)
        self._safe_save(wb)
        return True, "已撤回上一步操作。"

    def multi_entry(self, sheet_names, day, model, total):
        if not sheet_names:
            return False, "没有选择人员。"
        n = len(sheet_names)
        try:
            total_num = float(total)
        except ValueError:
            return False, "总数不合法。"
        if total_num % n != 0:
            return False, f"总数 {total_num} 不能被 {n} 整除。"
        each = total_num / n
        results = []
        for name in sheet_names:
            ok, msg = self.entry(name, day, model, str(each))
            results.append(f"{name}: {'成功' if ok else '失败：' + msg}")
        return True, "\n".join(results)

    def add_person(self, name):
        wb = self.conn.get_active_workbook()
        if wb is None:
            return False, "未检测到活动工作簿。"
        for sh in wb.Sheets:
            if sh.Name == name:
                return False, f"已存在同名 sheet：{name}"

        count = wb.Sheets.Count
        new_sh = wb.Sheets.Add(After=wb.Sheets(count))
        new_sh.Name = name

        xlCenter = -4108
        xlContinuous = 1
        xlEdgeLeft = 7
        xlEdgeTop = 8
        xlEdgeBottom = 9
        xlEdgeRight = 10
        xlInsideHorizontal = 12
        xlInsideVertical = 11

        a1 = new_sh.Cells(1, 1)
        a1.Value = name
        a1.Font.Name = "宋体"
        a1.Font.Bold = True
        a1.Font.Size = 16
        a1.HorizontalAlignment = xlCenter
        a1.VerticalAlignment = xlCenter

        try:
            new_sh.Rows(1).AutoFit()
        except Exception:
            pass
        try:
            if new_sh.Rows(1).RowHeight < 25:
                new_sh.Rows(1).RowHeight = 25
        except Exception:
            pass

        a2 = new_sh.Cells(2, 1)
        a2.Value = "日期"
        a2.HorizontalAlignment = xlCenter

        for i in range(1, 32):
            new_sh.Cells(i + 2, 1).Value = i

        rng_days = new_sh.Range(new_sh.Cells(3, 1), new_sh.Cells(33, 1))
        rng_days.HorizontalAlignment = xlCenter

        rng_border = new_sh.Range(new_sh.Cells(2, 1), new_sh.Cells(33, 1))
        try:
            for edge in [xlEdgeLeft, xlEdgeTop, xlEdgeBottom, xlEdgeRight,
                         xlInsideHorizontal, xlInsideVertical]:
                rng_border.Borders(edge).LineStyle = xlContinuous
        except Exception as e:
            print("设置边框失败:", e)

        self._safe_save(wb)
        return True, f"已新增人员：{name}"

    # ---------- 清理空列 ----------
    def clean_empty_columns_all(self):
        wb = self.conn.get_active_workbook()
        if wb is None:
            return [], "未检测到活动工作簿。"

        result = []

        try:
            self.conn.app.ScreenUpdating = False
        except Exception:
            pass
        try:
            self.conn.app.Calculation = -4135
        except Exception:
            pass
        try:
            self.conn.app.EnableEvents = False
        except Exception:
            pass
        try:
            self.conn.app.DisplayAlerts = False
        except Exception:
            pass

        try:
            sheet_names = []
            for sh in wb.Sheets:
                try:
                    n = sh.Name
                except Exception:
                    continue
                if n == "合计":
                    continue
                sheet_names.append(n)

            for sheet_name in sheet_names:
                sh = self.conn.get_sheet(sheet_name)
                if sh is None:
                    continue

                try:
                    last_col = self.conn.scan_last_model_col(sh)
                except Exception:
                    continue
                if last_col < 2:
                    continue

                try:
                    rng_h = sh.Range(sh.Cells(2, 2), sh.Cells(2, last_col))
                    rng_v = sh.Range(sh.Cells(34, 2), sh.Cells(34, last_col))
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
                    print(f"读 {sheet_name} 失败:", e)
                    continue

                for i, (h, v) in enumerate(zip(headers, values)):
                    if h is None:
                        continue
                    name = str(h).strip()
                    if name == "":
                        continue

                    is_zero = False
                    if v is None:
                        is_zero = True
                    else:
                        try:
                            if abs(float(v)) < 0.0001:
                                is_zero = True
                        except (ValueError, TypeError):
                            continue

                    if is_zero:
                        result.append({
                            "sheet": sheet_name,
                            "col": 2 + i,
                            "name": name,
                        })
        except Exception as e:
            return [], f"扫描失败：{e}"
        finally:
            try:
                self.conn.app.ScreenUpdating = True
            except Exception:
                pass
            try:
                self.conn.app.Calculation = -4105
            except Exception:
                pass
            try:
                self.conn.app.EnableEvents = True
            except Exception:
                pass
            try:
                self.conn.app.DisplayAlerts = True
            except Exception:
                pass

        return result, ""

    def do_delete_columns_batch(self, items):
        wb = self.conn.get_active_workbook()
        if wb is None:
            return False, "未检测到活动工作簿。"

        grouped = {}
        for it in items:
            grouped.setdefault(it["sheet"], []).append(it["col"])

        deleted_total = 0
        try:
            for sheet_name, cols in grouped.items():
                sh = self.conn.get_sheet(sheet_name)
                if sh is None:
                    continue
                for c in sorted(cols, reverse=True):
                    try:
                        sh.Columns(c).Delete()
                        deleted_total += 1
                    except Exception as e:
                        print(f"删除 {sheet_name} 第 {c} 列失败:", e)

                self._update_total(sh, wb.Name)
        except Exception as e:
            return False, f"删除过程中出错：{e}"

        self._safe_save(wb)
        return True, f"已删除 {deleted_total} 列（涉及 {len(grouped)} 个 sheet）。"

    def clean_empty_columns(self, sheet_name):
        wb = self.conn.get_active_workbook()
        if wb is None:
            return [], "未检测到活动工作簿。"

        sh = self.conn.get_sheet(sheet_name)
        if sh is None:
            return [], f"找不到 sheet：{sheet_name}"

        try:
            sh.Calculate()
        except Exception:
            pass

        try:
            last_col = self.conn.scan_last_model_col(sh)
        except Exception:
            return [], "读取列范围失败"

        if last_col < 2:
            return [], ""

        to_delete = []
        for c in range(2, last_col + 1):
            try:
                header = sh.Cells(2, c).Value
            except Exception:
                continue
            if header is None:
                continue
            name = str(header).strip()
            if name == "":
                continue

            try:
                val = sh.Cells(34, c).Value
            except Exception:
                continue

            is_zero = False
            if val is None:
                is_zero = True
            else:
                try:
                    if abs(float(val)) < 0.0001:
                        is_zero = True
                except (ValueError, TypeError):
                    continue

            if is_zero:
                to_delete.append({"col": c, "name": name})

        return to_delete, ""

    def do_delete_columns(self, sheet_name, columns):
        wb = self.conn.get_active_workbook()
        if wb is None:
            return False, "未检测到活动工作簿。"

        sh = self.conn.get_sheet(sheet_name)
        if sh is None:
            return False, f"找不到 sheet：{sheet_name}"

        wb_name = wb.Name
        cols = sorted([c["col"] for c in columns], reverse=True)

        try:
            for c in cols:
                sh.Columns(c).Delete()
        except Exception as e:
            return False, f"删除列失败：{e}"

        self._update_total(sh, wb_name)
        self._safe_save(wb)
        return True, f"已删除 {len(cols)} 列。"

    # ---------- 修帽子合计统计 ----------
    def _read_total_value(self, sh, wb_name):
        if "干磨" in wb_name:
            total_row = 37
        else:
            total_row = 35
        try:
            last_col = self.conn.scan_last_model_col(sh)
        except Exception:
            return 0
        for c in range(last_col + 2, 1, -1):
            try:
                v = sh.Cells(total_row, c).Value
            except Exception:
                continue
            if v is not None and "总计" in str(v):
                try:
                    vv = sh.Cells(total_row, c + 1).Value
                    return float(vv) if vv is not None else 0
                except Exception:
                    return 0
        return 0

    def _get_per_page_cols(self, sh, default=16):
        try:
            count = sh.VPageBreaks.Count
            if count > 0:
                loc = sh.VPageBreaks(1).Location.Column
                if loc > 1:
                    return loc - 1
        except Exception:
            pass
        return default

    def _build_segments(self, models, time_item, total_val, per_page=16):
        slots_per_seg = per_page - 1

        remaining = list(models)
        segments = []
        total_placed = False
        time_placed = (time_item is None)

        while remaining or not total_placed:
            seg = []
            while remaining and len(seg) < slots_per_seg:
                seg.append(remaining.pop(0))

            if not remaining:
                if not total_placed and len(seg) < slots_per_seg:
                    seg.append(("合计", total_val))
                    total_placed = True
                if not time_placed and len(seg) < slots_per_seg:
                    seg.append(time_item)
                    time_placed = True

            segments.append(seg)

            if not remaining and total_placed and time_placed:
                break

        if not total_placed or not time_placed:
            seg = []
            if not total_placed:
                seg.append(("合计", total_val))
                total_placed = True
            if not time_placed and len(seg) < slots_per_seg:
                seg.append(time_item)
                time_placed = True
            segments.append(seg)

        segments = [s for s in segments if s]
        return segments

    def make_summary(self, summary_sheet_name="合计"):
        wb = self.conn.get_active_workbook()
        if wb is None:
            return False, "未检测到活动工作簿。"

        wb_name = wb.Name
        if "修帽子" not in wb_name:
            return False, f"当前工作簿不是修帽子表：{wb_name}"

        try:
            summary_sh = wb.Sheets(summary_sheet_name)
        except Exception:
            return False, f"找不到 sheet：{summary_sheet_name}"

        try:
            self.conn.app.ScreenUpdating = False
        except Exception:
            pass
        try:
            self.conn.app.Calculation = -4135
        except Exception:
            pass
        try:
            self.conn.app.EnableEvents = False
        except Exception:
            pass
        try:
            self.conn.app.DisplayAlerts = False
        except Exception:
            pass

        try:
            per_page = self._get_per_page_cols(summary_sh, 16)

            names = []
            sheet_map = {}
            for sh in wb.Sheets:
                try:
                    sname = sh.Name
                except Exception:
                    continue
                sheet_map[sname] = sh
                if sname == summary_sheet_name or sname == "合计":
                    continue
                names.append(sname)

            if not names:
                return False, "没有找到任何人名（除合计外没有其他 sheet）。"

            people_data = []
            for name in names:
                src_sh = sheet_map.get(name)
                if src_sh is None:
                    continue

                try:
                    last_col = self.conn.scan_last_model_col(src_sh)
                except Exception:
                    last_col = 1

                models = []
                time_item = None

                if last_col >= 2:
                    try:
                        rng_h = src_sh.Range(src_sh.Cells(2, 2),
                                             src_sh.Cells(2, last_col))
                        rng_v = src_sh.Range(src_sh.Cells(34, 2),
                                             src_sh.Cells(34, last_col))
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

                        for h, v in zip(headers, values):
                            if h is None:
                                continue
                            h_str = str(h).strip()
                            if not h_str:
                                continue
                            try:
                                v_num = float(v) if v is not None else 0
                            except (ValueError, TypeError):
                                v_num = 0

                            if h_str == "时间":
                                time_item = ("时间", v_num)
                            else:
                                models.append((h_str, v_num))
                    except Exception as e:
                        print(f"读 {name} 失败:", e)

                total_val = self._read_total_value(src_sh, wb_name)
                people_data.append((name, models, time_item, total_val))

            try:
                used = summary_sh.UsedRange
                last_row = used.Row + used.Rows.Count - 1
                last_col = used.Column + used.Columns.Count - 1
                if last_row < 300:
                    last_row = 300
                if last_col < 100:
                    last_col = 100
                rng = summary_sh.Range(summary_sh.Cells(2, 1),
                                       summary_sh.Cells(last_row, last_col))
                rng.ClearContents()
                rng.Borders.LineStyle = -4142
            except Exception as e:
                print("清空失败:", e)

            cur_row = 2
            for name, models, time_item, total_val in people_data:
                segments = self._build_segments(models, time_item, total_val, per_page)

                try:
                    summary_sh.Cells(cur_row, 1).Value = name
                except Exception:
                    pass

                for seg_i, seg in enumerate(segments):
                    r_model = cur_row + 2 * seg_i
                    r_num = r_model + 1

                    if not seg:
                        continue

                    names_col = [x[0] for x in seg]
                    vals_col = [x[1] for x in seg]
                    n_cols = len(seg)

                    try:
                        summary_sh.Range(
                            summary_sh.Cells(r_model, 2),
                            summary_sh.Cells(r_model, n_cols + 1)
                        ).Value = tuple(names_col)
                    except Exception as e:
                        print(f"写 {name} 型号失败:", e)

                    try:
                        summary_sh.Range(
                            summary_sh.Cells(r_num, 2),
                            summary_sh.Cells(r_num, n_cols + 1)
                        ).Value = tuple(vals_col)
                    except Exception as e:
                        print(f"写 {name} 数量失败:", e)

                    try:
                        rng_border = summary_sh.Range(
                            summary_sh.Cells(r_model, 2),
                            summary_sh.Cells(r_num, n_cols + 1)
                        )
                        for edge in [7, 8, 9, 10, 11, 12]:
                            rng_border.Borders(edge).LineStyle = 1
                        rng_border.HorizontalAlignment = -4108
                        rng_border.VerticalAlignment = -4108
                    except Exception as e:
                        print(f"加边框 {name} 失败:", e)

                    try:
                        rng_a = summary_sh.Range(
                            summary_sh.Cells(r_model, 1),
                            summary_sh.Cells(r_num, 1)
                        )
                        rng_a.HorizontalAlignment = -4108
                        rng_a.VerticalAlignment = -4108
                    except Exception:
                        pass

                n_rows = 2 * len(segments)
                cur_row = cur_row + n_rows + 1

            self._safe_save(wb)
            return True, f"合计已生成，共填写 {len(people_data)} 人"

        finally:
            try:
                self.conn.app.ScreenUpdating = True
            except Exception:
                pass
            try:
                self.conn.app.Calculation = -4105
            except Exception:
                pass
            try:
                self.conn.app.EnableEvents = True
            except Exception:
                pass
            try:
                self.conn.app.DisplayAlerts = True
            except Exception:
                pass

    # ---------- 检查并修正公式 ----------
    def verify_and_fix_sheet(self, sh, wb_name):
        fixes = []
        try:
            last_col = self.conn.scan_last_model_col(sh)
        except Exception:
            return fixes
        if last_col < 2:
            return fixes

        is_ganmo = self._is_ganmo(wb_name)

        try:
            rng_h = sh.Range(sh.Cells(2, 2), sh.Cells(2, last_col))
            headers = rng_h.Value
            if not isinstance(headers, tuple):
                headers = (headers,)
            if headers and isinstance(headers[0], tuple):
                headers = headers[0]
        except Exception:
            return fixes

        try:
            rng_34 = sh.Range(sh.Cells(34, 2), sh.Cells(34, last_col))
            f34 = rng_34.Formula
            if not isinstance(f34, tuple):
                f34 = (f34,)
            if f34 and isinstance(f34[0], tuple):
                f34 = f34[0]
        except Exception:
            f34 = ()

        if is_ganmo:
            try:
                rng_36 = sh.Range(sh.Cells(36, 2), sh.Cells(36, last_col))
                f36 = rng_36.Formula
                if not isinstance(f36, tuple):
                    f36 = (f36,)
                if f36 and isinstance(f36[0], tuple):
                    f36 = f36[0]
            except Exception:
                f36 = ()
        else:
            f36 = ()

        fix_34 = {}
        fix_36 = {}

        for i, h in enumerate(headers):
            col = 2 + i
            col_letter = self._col_letter(col)
            hs = str(h).strip() if h is not None else ""

            if hs == "":
                continue

            exp34 = f"=SUM({col_letter}3:{col_letter}33)"
            got34 = f34[i] if i < len(f34) else None
            got34_s = str(got34).strip() if got34 is not None else ""
            if got34_s.upper() != exp34.upper():
                fix_34[col] = exp34

            if is_ganmo:
                if hs in ("时间", "样品"):
                    got36 = f36[i] if i < len(f36) else None
                    got36_s = str(got36).strip() if got36 is not None else ""
                    if got36_s != "":
                        fix_36[col] = ""
                else:
                    exp36 = f"={col_letter}34*{col_letter}35"
                    got36 = f36[i] if i < len(f36) else None
                    got36_s = str(got36).strip() if got36 is not None else ""
                    if got36_s.upper() != exp36.upper():
                        fix_36[col] = exp36

        for col, formula in fix_34.items():
            try:
                self.conn.write_formula(sh, 34, col, formula)
                fixes.append(f"{sh.Name}!{self._col_letter(col)}34")
            except Exception:
                pass

        for col, formula in fix_36.items():
            try:
                if formula == "":
                    sh.Cells(36, col).ClearContents()
                    fixes.append(f"{sh.Name}!{self._col_letter(col)}36清空")
                else:
                    self.conn.write_formula(sh, 36, col, formula)
                    fixes.append(f"{sh.Name}!{self._col_letter(col)}36")
            except Exception:
                pass

        if is_ganmo:
            skip = ("时间", "样品")
        else:
            skip = ("时间",)

        effective_last = None
        for i in range(len(headers) - 1, -1, -1):
            h = headers[i]
            if h is None:
                continue
            hs = str(h).strip()
            if hs == "" or hs in skip:
                continue
            effective_last = 2 + i
            break

        if effective_last is None:
            return fixes

        if is_ganmo:
            total_row = 37
            sum_row = 36
        else:
            total_row = 35
            sum_row = 34

        if effective_last == 2:
            label_col = effective_last
            formula_col = effective_last + 1
        else:
            label_col = effective_last - 1
            formula_col = effective_last

        exp_total = f"=SUM(B{sum_row}:{self._col_letter(effective_last)}{sum_row})"

        label_ok = False
        formula_ok = False
        try:
            lv = sh.Cells(total_row, label_col).Value
            if lv is not None and "总计" in str(lv):
                label_ok = True
        except Exception:
            pass

        try:
            ft = sh.Cells(total_row, formula_col).Formula
            if ft is not None:
                ft_s = str(ft).strip()
                if ft_s.upper() == exp_total.upper():
                    formula_ok = True
        except Exception:
            pass

        if not (label_ok and formula_ok):
            try:
                start_letter = self._col_letter(1)
                end_letter = self._col_letter(last_col + 2)
                sh.Range(f"{start_letter}{total_row}:{end_letter}{total_row}").ClearContents()
            except Exception:
                pass
            try:
                sh.Cells(total_row, label_col).Value = "总计："
                self.conn.write_formula(sh, total_row, formula_col, exp_total)
                fixes.append(f"{sh.Name}!总计行")
            except Exception:
                pass

        return fixes

    def verify_current_workbook(self):
        wb = self.conn.get_active_workbook()
        if wb is None:
            return []

        wb_name = wb.Name
        all_fixes = []

        try:
            self.conn.app.ScreenUpdating = False
        except Exception:
            pass
        try:
            self.conn.app.Calculation = -4135
        except Exception:
            pass
        try:
            self.conn.app.EnableEvents = False
        except Exception:
            pass

        try:
            for sh in wb.Sheets:
                try:
                    sname = sh.Name
                except Exception:
                    continue
                if sname == "合计":
                    continue
                try:
                    fixes = self.verify_and_fix_sheet(sh, wb_name)
                    all_fixes.extend(fixes)
                except Exception as e:
                    print(f"检查 {sname} 失败:", e)

            if all_fixes:
                self._safe_save(wb)
        finally:
            try:
                self.conn.app.ScreenUpdating = True
            except Exception:
                pass
            try:
                self.conn.app.Calculation = -4105
            except Exception:
                pass
            try:
                self.conn.app.EnableEvents = True
            except Exception:
                pass

        return all_fixes