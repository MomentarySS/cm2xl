"""
模板配置向导 - 帮用户配置新模板的列映射和关键参数
输出: %APPDATA%\\CMMFiller\\template_config.json
"""
import os
import json
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import openpyxl
from openpyxl.utils import get_column_letter, column_index_from_string
from pathlib import Path
from utils.settings import save_settings_json_atomic
from utils.paths import paths

def _get_appdata_dir():
    """统一配置目录：{data}/config/cmm_filler（与 gui.py/filler.py 一致，ARCH 3.9）"""
    path = paths.config_dir / 'cmm_filler'
    try:
        path.mkdir(parents=True, exist_ok=True)
        return str(path)
    except OSError:
        return str(Path(__file__).resolve().parent)

CONFIG_PATH = os.path.join(_get_appdata_dir(), 'template_config.json')


class TemplateWizard:
    COLUMN_LABELS = {
        'serial': '序号',
        'spec': '规格',
        'upper_tol': '上公差',
        'lower_tol': '下公差',
        'upper_limit': '上限公式',
        'lower_limit': '下限公式',
        'instrument': '测量仪器',
    }

    FIELD_LOCATION_LABELS = {
        'part_name': '零件名/品名',
        'date': '日期',
    }

    def __init__(self, parent=None):
        """parent=None 时独立窗口运行（CLI --wizard）；
        传入主 GUI root 时作为模态对话框运行（同进程，避免多 Tk 实例冲突）。"""
        if parent is None:
            self.root = tk.Tk()
        else:
            self.root = tk.Toplevel(parent)
            self.root.transient(parent)
        self.root.title('模板配置向导')
        self.root.geometry('1000x780')

        self.template_path = None
        self.wb = None
        self.ws = None
        self.config = {}
        self.column_vars = {}
        self.sample_vars = {}
        self.field_location_vars = {}
        self.header_labels = []

        self._build_ui()
        self._load_existing_config()

    def _build_ui(self):
        container = ttk.Frame(self.root)
        container.pack(fill='both', expand=True)

        canvas = tk.Canvas(container, highlightthickness=0)
        scrollbar = ttk.Scrollbar(container, orient='vertical', command=canvas.yview)
        self.scrollable_frame = ttk.Frame(canvas)

        self.scrollable_frame.bind(
            '<Configure>',
            lambda e: canvas.configure(scrollregion=canvas.bbox('all'))
        )
        canvas.create_window((0, 0), window=self.scrollable_frame, anchor='nw')
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')
        canvas.bind('<MouseWheel>', lambda e: canvas.yview_scroll(int(-1 * (e.delta / 120)), 'units'))
        canvas.bind('<Button-4>', lambda e: canvas.yview_scroll(-1, 'units'))
        canvas.bind('<Button-5>', lambda e: canvas.yview_scroll(1, 'units'))

        ttk.Label(self.scrollable_frame, text='模板配置向导', font=('Microsoft YaHei', 14, 'bold')).pack(pady=10)
        ttk.Label(self.scrollable_frame, text='选择模板文件，然后点击"加载模板"查看表头，对照表头选择各列对应什么',
                  font=('Microsoft YaHei', 9)).pack()

        # 文件选择
        file_frame = ttk.Frame(self.scrollable_frame)
        file_frame.pack(fill='x', padx=20, pady=5)
        ttk.Label(file_frame, text='模板文件:').pack(side='left')
        self.file_var = tk.StringVar(value='')
        self.file_entry = ttk.Entry(file_frame, textvariable=self.file_var, width=60)
        self.file_entry.pack(side='left', padx=5)
        ttk.Button(file_frame, text='浏览', command=self._browse).pack(side='left')
        ttk.Button(file_frame, text='加载模板', command=self._load_template).pack(side='left', padx=5)

        # 表头预览
        preview_frame = ttk.LabelFrame(self.scrollable_frame, text='模板表头预览 (Row 4)')
        preview_frame.pack(fill='x', padx=20, pady=5)
        self.preview_text = tk.Text(preview_frame, height=2, state='disabled')
        self.preview_text.pack(fill='x', padx=5, pady=5)

        # 列映射配置
        config_frame = ttk.LabelFrame(self.scrollable_frame, text='列映射配置')
        config_frame.pack(fill='x', padx=20, pady=5)

        self.mapping_frame = ttk.Frame(config_frame)
        self.mapping_frame.pack(fill='x', padx=5, pady=5)

        # 样品列配置
        sample_frame = ttk.LabelFrame(self.scrollable_frame, text='样品列配置 (1#-5#)')
        sample_frame.pack(fill='x', padx=20, pady=5)
        self.sample_labelframe = sample_frame  # 标题随主样品数更新

        self.sample_frame = ttk.Frame(sample_frame)
        self.sample_frame.pack(fill='x', padx=5, pady=5)

        # 字段位置配置
        field_frame = ttk.LabelFrame(self.scrollable_frame, text='字段写入位置（如：品名写 D5，日期写 A2）')
        field_frame.pack(fill='x', padx=20, pady=5)

        self.field_frame = ttk.Frame(field_frame)
        self.field_frame.pack(fill='x', padx=5, pady=5)

        ttk.Label(self.field_frame, text='字段').grid(row=0, column=0, padx=5, pady=2)
        ttk.Label(self.field_frame, text='写入位置').grid(row=0, column=1, padx=5, pady=2)
        ttk.Label(self.field_frame, text='说明').grid(row=0, column=2, padx=5, pady=2)

        for i, (key, label) in enumerate(self.FIELD_LOCATION_LABELS.items()):
            ttk.Label(self.field_frame, text=label).grid(row=i+1, column=0, sticky='w', padx=5, pady=2)

            var = self.field_location_vars.get(key)
            if var is None:
                var = tk.StringVar()
                self.field_location_vars[key] = var
            ttk.Entry(self.field_frame, textvariable=var, width=10).grid(row=i+1, column=1, padx=5, pady=2)

            if key == 'part_name':
                hint = '例如 D5、A5，写入零件名/品名'
            elif key == 'date':
                hint = '例如 L2、A2，写入日期'
            else:
                hint = ''
            ttk.Label(self.field_frame, text=hint, foreground='gray').grid(row=i+1, column=2, sticky='w', padx=5, pady=2)

        # 其他设置
        other_frame = ttk.LabelFrame(self.scrollable_frame, text='其他设置')
        other_frame.pack(fill='x', padx=20, pady=5)

        ttk.Label(other_frame, text='数据起始行:').grid(row=0, column=0, sticky='w', padx=5, pady=5)
        self.data_start_var = tk.StringVar(value='6')
        ttk.Entry(other_frame, textvariable=self.data_start_var, width=10).grid(row=0, column=1, sticky='w', pady=5)

        ttk.Label(other_frame, text='送检产品序号行:').grid(row=0, column=2, sticky='w', padx=5, pady=5)
        self.sample_row_var = tk.StringVar(value='5')
        ttk.Entry(other_frame, textvariable=self.sample_row_var, width=10).grid(row=0, column=3, sticky='w', pady=5)

        ttk.Label(other_frame, text='Sheet名称:').grid(row=0, column=4, sticky='w', padx=5, pady=5)
        self.sheet_var = tk.StringVar(value='FAI')
        ttk.Entry(other_frame, textvariable=self.sheet_var, width=10).grid(row=0, column=5, sticky='w', pady=5)

        ttk.Label(other_frame, text='主样品数:').grid(row=1, column=0, sticky='w', padx=5, pady=5)
        self.main_count_var = tk.StringVar(value='5')
        main_combo = ttk.Combobox(
            other_frame, textvariable=self.main_count_var,
            values=[str(i) for i in range(1, 11)], state='readonly', width=8,
        )
        main_combo.grid(row=1, column=1, sticky='w', pady=5)
        main_combo.bind('<<ComboboxSelected>>', lambda e: self._build_column_mapping())
        ttk.Label(other_frame, text='主表样品位（超出部分自动溢出到 Sheet B，容量相同）',
                  foreground='gray').grid(row=1, column=2, columnspan=3, sticky='w', padx=5)

        # 保存按钮
        btn_frame = ttk.Frame(self.scrollable_frame)
        btn_frame.pack(pady=10)
        ttk.Button(btn_frame, text='保存配置', command=self._save_config).pack(side='left', padx=5)
        ttk.Button(btn_frame, text='取消', command=self.root.destroy).pack(side='left', padx=5)

        # 初始构建列映射（可能没有加载模板，控件为空但已创建）
        self._build_column_mapping()

    def _get_main_count(self):
        """读取主样品数设置（容错，默认 5）"""
        try:
            n = int(self.main_count_var.get())
        except (ValueError, AttributeError, tk.TclError):
            n = 5
        return max(1, min(n, 10))

    def _load_existing_config(self):
        """加载已有配置并回填到 GUI 控件"""
        if not os.path.exists(CONFIG_PATH):
            return
        try:
            with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
                self.config = json.load(f)
        except Exception:
            return

        # 回填文件路径和 Sheet 名称
        if 'template_path' in self.config:
            self.file_var.set(self.config['template_path'])
        if 'sheet_name' in self.config:
            self.sheet_var.set(self.config['sheet_name'])
        if 'data_start_row' in self.config:
            self.data_start_var.set(str(self.config['data_start_row']))
        if 'sample_row' in self.config:
            self.sample_row_var.set(str(self.config['sample_row']))
        if 'main_sample_count' in self.config:
            self.main_count_var.set(str(self.config['main_sample_count']))

        # 回填列映射
        if 'columns' in self.config:
            for key, val in self.config['columns'].items():
                if key in self.column_vars and val:
                    self.column_vars[key].set(val)

        # 回填样品列映射
        if 'sample_cols' in self.config:
            for label, val in self.config['sample_cols'].items():
                if label in self.sample_vars and val:
                    self.sample_vars[label].set(val)

        # 回填字段位置
        if 'field_locations' in self.config:
            for key, val in self.config['field_locations'].items():
                if key in self.field_location_vars and val:
                    self.field_location_vars[key].set(val)

        # 主样品数若与默认不同，样品区行数需重建（重建时会从 config 回填各列）
        if str(self._get_main_count()) != '5':
            self._build_column_mapping()

    def _browse(self):
        path = filedialog.askopenfilename(
            title='选择 Excel 模板',
            filetypes=[('Excel 文件', '*.xlsx *.xls'), ('所有文件', '*.*')]
        )
        if path:
            self.file_var.set(path)
            self.file_entry.update_idletasks()
            # 强制确保 Entry 显示（frozen 环境下 StringVar 有时不同步）
            self.file_entry.delete(0, 'end')
            self.file_entry.insert(0, path)

    def _load_template(self):
        path = self.file_var.get().strip()
        if not os.path.isfile(path):
            messagebox.showerror('错误', '请选择有效的模板文件')
            return

        try:
            self.wb = openpyxl.load_workbook(path)
            sheet_name = self.sheet_var.get().strip()

            # 自动检测：如果指定 sheet 不存在，尝试首字母匹配或取第一个
            if sheet_name not in self.wb.sheetnames:
                for sn in self.wb.sheetnames:
                    if sn.lower().startswith(sheet_name.lower()):
                        sheet_name = sn
                        self.sheet_var.set(sheet_name)
                        break
                else:
                    sheet_name = self.wb.sheetnames[0]
                    self.sheet_var.set(sheet_name)
                    messagebox.showinfo('提示', f'Sheet "{self.sheet_var.get()}" 不存在，已自动切换到 "{sheet_name}"')

            self.ws = self.wb[sheet_name]

            # 读取 Row 4 的表头
            self.header_labels = []
            for col in range(1, 13):
                v = self.ws.cell(row=4, column=col).value
                self.header_labels.append(str(v) if v is not None else '')

            # 显示预览
            self.preview_text.config(state='normal')
            self.preview_text.delete('1.0', 'end')
            preview = '  |  '.join(f'{get_column_letter(i+1)}={lbl}' for i, lbl in enumerate(self.header_labels))
            self.preview_text.insert('1.0', preview)
            self.preview_text.config(state='disabled')

            # 重建列映射选择
            self._build_column_mapping()

            messagebox.showinfo('成功', f'模板加载成功，共 {len([l for l in self.header_labels if l])} 个有效列')
        except Exception as e:
            messagebox.showerror('错误', f'加载模板失败: {str(e)}')

    def _build_column_mapping(self):
        # 清空列映射和样品列控件（字段位置不依赖表头，但需重建以保持顺序）
        for widget in self.mapping_frame.winfo_children():
            widget.destroy()
        for widget in self.sample_frame.winfo_children():
            widget.destroy()
        for widget in self.field_frame.winfo_children():
            widget.destroy()

        self.column_vars = {}
        self.sample_vars = {}
        # field_location_vars 不重置 — 保留已有值

        # 列映射下拉框
        ttk.Label(self.mapping_frame, text='字段').grid(row=0, column=0, padx=5, pady=2)
        ttk.Label(self.mapping_frame, text='对应列').grid(row=0, column=1, padx=5, pady=2)
        ttk.Label(self.mapping_frame, text='预览').grid(row=0, column=2, padx=5, pady=2)

        for i, (key, label) in enumerate(self.COLUMN_LABELS.items()):
            ttk.Label(self.mapping_frame, text=label).grid(row=i+1, column=0, sticky='w', padx=5, pady=2)

            var = tk.StringVar()
            self.column_vars[key] = var

            options = [''] + [f'{get_column_letter(c)}' for c in range(1, 27)]
            combo = ttk.Combobox(self.mapping_frame, textvariable=var, values=options, state='readonly', width=5)
            combo.grid(row=i+1, column=1, padx=5, pady=2)

            matched = False
            if self.ws and self.header_labels:
                for idx, hdr in enumerate(self.header_labels):
                    if label in hdr or hdr in label:
                        var.set(get_column_letter(idx+1))
                        matched = True
                        break

            if not matched and 'columns' in self.config and key in self.config['columns']:
                var.set(self.config['columns'][key])

            preview_var = tk.StringVar()
            def update_preview(*args, key=key, var=var):
                col = var.get()
                preview_var.set('')
                if col and self.header_labels:
                    for idx, hdr in enumerate(self.header_labels):
                        if get_column_letter(idx+1) == col:
                            preview_var.set(hdr)
                            break
            var.trace('w', update_preview)
            ttk.Label(self.mapping_frame, textvariable=preview_var).grid(row=i+1, column=2, padx=5, pady=2)

        # 样品列配置（行数跟随主样品数，支持 1#-10#；下拉 A-Z）
        main_count = self._get_main_count()
        self.sample_labelframe.configure(text=f'样品列配置 (1#-{main_count}#)')
        ttk.Label(self.sample_frame, text='样品').grid(row=0, column=0, padx=5, pady=2)
        ttk.Label(self.sample_frame, text='对应列').grid(row=0, column=1, padx=5, pady=2)
        ttk.Label(self.sample_frame, text='预览').grid(row=0, column=2, padx=5, pady=2)

        for i in range(1, main_count + 1):
            label = f'{i}#'
            ttk.Label(self.sample_frame, text=label).grid(row=i, column=0, sticky='w', padx=5, pady=2)

            var = tk.StringVar()
            self.sample_vars[label] = var

            options = [''] + [f'{get_column_letter(c)}' for c in range(1, 27)]
            combo = ttk.Combobox(self.sample_frame, textvariable=var, values=options, state='readonly', width=5)
            combo.grid(row=i, column=1, padx=5, pady=2)

            matched = False
            if self.ws:
                sample_row = int(self.sample_row_var.get())
                for row in range(sample_row, min(sample_row+10, 35)):
                    for col in range(1, 27):
                        v = self.ws.cell(row=row, column=col).value
                        if v and str(v).strip() in [str(i).zfill(3), str(i)]:
                            var.set(get_column_letter(col))
                            matched = True
                            break
                    if matched:
                        break

            if not matched and 'sample_cols' in self.config and label in self.config['sample_cols']:
                var.set(self.config['sample_cols'][label])

            preview_var = tk.StringVar()
            def make_sample_preview(var, preview_var):
                def callback(*args):
                    col = var.get()
                    preview_var.set('')
                    if col and self.ws:
                        sample_row = int(self.sample_row_var.get())
                        for row in range(sample_row, min(sample_row+10, 35)):
                            for c in range(1, 27):
                                if get_column_letter(c) == col:
                                    v = self.ws.cell(row=row, column=c).value
                                    if v:
                                        preview_var.set(str(v))
                                        return
                return callback
            var.trace('w', make_sample_preview(var, preview_var))
            ttk.Label(self.sample_frame, textvariable=preview_var).grid(row=i, column=2, padx=5, pady=2)

    def _save_config(self):
        config = {
            'template_path': self.file_var.get().strip(),
            'sheet_name': self.sheet_var.get().strip(),
            'data_start_row': int(self.data_start_var.get().strip()),
            'sample_row': int(self.sample_row_var.get().strip()),
            'main_sample_count': self._get_main_count(),
            'columns': {},
            'sample_cols': {},
            'field_locations': {},
        }

        # 列映射
        for key, var in self.column_vars.items():
            col = var.get().strip()
            if col:
                config['columns'][key] = col  # 已经是字母形式，如 'H'

        # 样品列映射
        for label, var in self.sample_vars.items():
            col = var.get().strip()
            if col:
                config['sample_cols'][label] = col  # 已经是字母形式

        # 字段位置
        for key, var in self.field_location_vars.items():
            loc = var.get().strip()
            if loc:
                config['field_locations'][key] = loc.upper()

        if not config['columns']:
            messagebox.showwarning('提示', '请至少配置一列映射')
            return

        # 保存到文件（原子写，避免中断留下半截配置文件）
        save_settings_json_atomic(Path(CONFIG_PATH), config)

        messagebox.showinfo('成功', f'配置已保存到:\n{CONFIG_PATH}')
        self.root.destroy()

    def run(self):
        if isinstance(self.root, tk.Toplevel):
            # 模态模式：阻塞主窗口直到向导关闭
            self.root.grab_set()
            self.root.wait_window()
        else:
            self.root.mainloop()


if __name__ == '__main__':
    TemplateWizard().run()
