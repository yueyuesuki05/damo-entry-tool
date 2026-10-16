# @Version  : 1.0
# @Author   : 小野
# @File     : wps_connector.py WPS COM 接口封装
# @Time     : 2026/9/30 13:17
import win32com.client
import pythoncom


def _model_key(m):
    s = str(m).strip().replace(" ", "")
    if s == "":
        return ("empty", "")
    try:
        return ("num", round(float(s), 6))
    except ValueError:
        pass
    return ("str", s.upper())


class WPSConnector:
    def __init__(self):
        self.app = None
        self.wb = None

    def connect(self):
        if self.app is not None:
            try:
                _ = self.app.Name
                return True
            except Exception:
                self.app = None
                self.wb = None

        pythoncom.CoInitialize()
        for prog_id in ["KET.Application", "ET.Application", "WPS.Application"]:
            # 先尝试连接已有实例
            try:
                self.app = win32com.client.GetActiveObject(prog_id)
                print("连接成功（已运行实例）：", prog_id)
                return True
            except Exception:
                pass
            # 失败再尝试 Dispatch
            try:
                self.app = win32com.client.Dispatch(prog_id)
                print("连接成功（Dispatch）：", prog_id)
                return True
            except Exception:
                continue
        return False

    def get_active_workbook(self):
        if self.app is None:
            return None
        try:
            wb = self.app.ActiveWorkbook
            if wb is None:
                self.wb = None
                return None
            _ = wb.Name
            self.wb = wb
            return wb
        except Exception:
            self.wb = None
            return None

    def get_sheet_names(self, exclude=("合计",)):
        wb = self.get_active_workbook()
        if wb is None:
            return []
        names = []
        try:
            for sh in wb.Sheets:
                try:
                    nm = sh.Name
                except Exception:
                    continue
                if nm not in exclude:
                    names.append(nm)
        except Exception:
            return []
        return names

    def get_sheet(self, name):
        wb = self.get_active_workbook()
        if wb is None:
            return None
        try:
            return wb.Sheets(name)
        except Exception:
            return None

    def get_active_sheet(self):
        try:
            sh = self.app.ActiveSheet
            if sh is None:
                return None
            _ = sh.Name
            return sh
        except Exception:
            return None

    def activate_sheet(self, name):
        sh = self.get_sheet(name)
        if sh:
            try:
                sh.Activate()
                return True
            except Exception:
                return False
        return False

    def get_workbook_name(self):
        try:
            wb = self.get_active_workbook()
            if wb is None:
                return ""
            return wb.Name
        except Exception:
            return ""

    def get_active_sheet_name(self):
        try:
            sh = self.app.ActiveSheet
            if sh is None:
                return ""
            return sh.Name
        except Exception:
            return ""

    def _col_letter(self, col):
        result = ""
        while col > 0:
            col, rem = divmod(col - 1, 26)
            result = chr(65 + rem) + result
        return result

    def _used_range_cols(self, sh):
        try:
            ur = sh.UsedRange
            return ur.Column + ur.Columns.Count - 1
        except Exception:
            return 1

    def scan_last_model_col(self, sh):
        ur_last_col = self._used_range_cols(sh)
        max_col = min(ur_last_col, 200)
        if max_col < 1:
            return 1
        try:
            rng = sh.Range(sh.Cells(2, 1), sh.Cells(2, max_col))
            vals = rng.Value
            if isinstance(vals, tuple):
                row_vals = vals[0]
            else:
                row_vals = (vals,)
            last = 1
            for i, v in enumerate(row_vals):
                if v is not None and str(v).strip() != "":
                    last = i + 1
            return last
        except Exception:
            return 1

    def _clean_used_range(self, sh):
        try:
            ur = sh.UsedRange
            ur_last_col = ur.Column + ur.Columns.Count - 1
            ur_last_row = ur.Row + ur.Rows.Count - 1
        except Exception:
            return

        if ur_last_col > 100:
            try:
                sh.Range(sh.Cells(1, 101), sh.Cells(1, ur_last_col)).EntireColumn.Delete()
                print("已清理多余列 101 ~", ur_last_col)
            except Exception as e:
                print("清理多余列失败:", e)

        if ur_last_row > 50:
            try:
                sh.Range(sh.Cells(51, 1), sh.Cells(ur_last_row, 1)).EntireRow.Delete()
                print("已清理多余行 51 ~", ur_last_row)
            except Exception as e:
                print("清理多余行失败:", e)

    def insert_column(self, sh, col):
        try:
            sh.Activate()
        except Exception:
            pass

        left_width = None
        if col > 2:
            try:
                left_width = sh.Columns(col - 1).ColumnWidth
            except Exception:
                pass

        inserted_ok = False
        try:
            sh.Columns(col).Insert(Shift=-4161)
            inserted_ok = True
        except Exception as e:
            print("第一次插入失败:", e)

        if not inserted_ok:
            print("清理 UsedRange 后重试")
            self._clean_used_range(sh)
            try:
                sh.Columns(col).Insert(Shift=-4161)
                inserted_ok = True
            except Exception as e:
                print("清理后仍失败:", e)
                return False

        if col > 2:
            try:
                left_letter = self._col_letter(col - 1)
                new_letter = self._col_letter(col)
                sh.Range(f"{left_letter}1:{left_letter}37").Copy(
                    sh.Range(f"{new_letter}1:{new_letter}37")
                )
                sh.Range(f"{new_letter}3:{new_letter}37").ClearContents()
            except Exception as e:
                print("复制格式失败:", e)

        if left_width is not None:
            try:
                sh.Columns(col).ColumnWidth = left_width
            except Exception:
                pass

        xlCenter = -4108
        xlContinuous = 1
        xlLineStyleNone = -4142

        try:
            rng_center = sh.Range(sh.Cells(2, col), sh.Cells(37, col))
            rng_center.HorizontalAlignment = xlCenter
            rng_center.VerticalAlignment = xlCenter
        except Exception as e:
            print("设置居中失败:", e)

        try:
            rng_border = sh.Range(sh.Cells(2, col), sh.Cells(33, col))
            for edge in [7, 8, 9, 10, 11, 12]:
                rng_border.Borders(edge).LineStyle = xlContinuous
        except Exception as e:
            print("设置边框失败:", e)

        try:
            rng_noborder = sh.Range(sh.Cells(34, col), sh.Cells(37, col))
            for edge in [7, 8, 9, 10, 11, 12]:
                rng_noborder.Borders(edge).LineStyle = xlLineStyleNone
        except Exception as e:
            print("清除34~37行边框失败:", e)

        try:
            sh.Cells(33, col).Borders(9).LineStyle = xlContinuous
        except Exception as e:
            print("补回33行下边框失败:", e)

        self._clean_used_range(sh)
        return True

    def find_model_column(self, sh, model, normalizer=None):
        from model_sort import to_abbr, to_abbr_loose

        target_key = _model_key(model)
        target_abbr = to_abbr(model)
        target_abbr_loose = to_abbr_loose(model)

        last_col = self.scan_last_model_col(sh)
        if last_col < 2:
            return 0
        try:
            rng = sh.Range(sh.Cells(2, 2), sh.Cells(2, last_col))
            values = rng.Value
        except Exception as e:
            print("读取第2行失败:", e)
            return 0
        if values is None:
            return 0
        if isinstance(values, tuple):
            row_vals = values[0]
        else:
            row_vals = (values,)

        for i, v in enumerate(row_vals):
            if v is None:
                continue
            if _model_key(str(v)) == target_key:
                return i + 2

        for i, v in enumerate(row_vals):
            if v is None:
                continue
            if to_abbr(str(v)) == target_abbr:
                return i + 2

        for i, v in enumerate(row_vals):
            if v is None:
                continue
            if to_abbr_loose(str(v)) == target_abbr_loose:
                return i + 2

        return 0

    def write_cell(self, sh, row, col, value):
        sh.Cells(row, col).Value = value

    def read_cell(self, sh, row, col):
        return sh.Cells(row, col).Value

    def write_formula(self, sh, row, col, formula):
        try:
            sh.Cells(row, col).NumberFormat = "General"
        except Exception:
            pass
        sh.Cells(row, col).Formula = formula

    def set_header_text_format(self, sh, col):
        try:
            sh.Cells(2, col).NumberFormat = "@"
        except Exception:
            pass

    def save(self):
        if self.wb:
            try:
                self.wb.Save()
            except Exception:
                pass

    def screen_updating(self, flag):
        pass