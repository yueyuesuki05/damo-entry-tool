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

        # 核心改动 1：把 KWPS.Application 放在最前面，适配新版 WPS
        for prog_id in ["KWPS.Application", "KET.Application", "ET.Application", "WPS.Application"]:
            try:
                # 核心改动 2：只使用 GetActiveObject，只连接你眼睛看得见的已打开的 WPS
                self.app = win32com.client.GetActiveObject(prog_id)

                # 核心改动 3：验证这个 WPS 进程里确实打开了表格，防止连到隐藏的空进程
                if self.app.Workbooks.Count > 0:
                    print("WPS 连接成功：", prog_id)
                    return True
                else:
                    self.app = None  # 如果没有打开任何表格，就放弃这个进程
            except Exception:
                pass

        # 核心改动 4：彻底删除了 Dispatch，绝对不让程序在后台偷偷启动隐藏的幽灵进程！
        print("未找到已打开的 WPS 表格，请确保 WPS 已经打开了文件。")
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
        # 记录左列宽度
        left_width = None
        if col > 2:
            try:
                left_width = sh.Columns(col - 1).ColumnWidth
            except Exception:
                pass

        # 1. 执行插入
        try:
            sh.Columns(col).Insert(Shift=-4161)
        except Exception as e:
            print("插入列失败:", e)
            return False

        # 2. 设置列宽和边框（放弃耗时的 Copy 复制格式，直接秒设）
        if left_width is not None:
            try:
                sh.Columns(col).ColumnWidth = left_width
            except Exception:
                pass

        xlCenter = -4108
        xlContinuous = 1
        xlLineStyleNone = -4142

        try:
            # 居中
            rng_center = sh.Range(sh.Cells(2, col), sh.Cells(37, col))
            rng_center.HorizontalAlignment = xlCenter
            rng_center.VerticalAlignment = xlCenter
            # 边框（2-33行有线框）
            rng_border = sh.Range(sh.Cells(2, col), sh.Cells(33, col))
            for edge in [7, 8, 9, 10, 11, 12]:
                rng_border.Borders(edge).LineStyle = xlContinuous
            # 34-37行无线框
            rng_noborder = sh.Range(sh.Cells(34, col), sh.Cells(37, col))
            for edge in [7, 8, 9, 10, 11, 12]:
                rng_noborder.Borders(edge).LineStyle = xlLineStyleNone
            # 补回33行下边框
            sh.Cells(33, col).Borders(9).LineStyle = xlContinuous
        except Exception:
            pass

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