import sys
import os
import csv
import math
import re
from itertools import groupby
from dataclasses import replace
from pathlib import Path
from PySide6 import QtWidgets as Q, QtCore
from PySide6.QtGui import QFont, QFontDatabase
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT
from matplotlib import dates as mdates
from matplotlib.figure import Figure
from matplotlib.font_manager import FontProperties
from .core import Project, TimeSegment, curve, sample, from_metric, to_metric, day, rate, range_end
from . import storage
from .operations import add_nodes
from .eclipse import render
from .vol import sampled_rows, render_rows
from .i18n import EN, translate


class PlotToolbar(NavigationToolbar2QT):
    toolitems = tuple(item for item in NavigationToolbar2QT.toolitems
                      if item[3] in ('home', 'back', 'forward', 'pan', 'zoom'))


class RandomNodeDialog(Q.QDialog):
    def __init__(self, owner, well_count):
        super().__init__(owner)
        self.owner = owner
        self.setWindowTitle(owner.t('随机添加节点'))
        self.setMinimumWidth(500)
        layout = Q.QVBoxLayout(self)
        layout.addWidget(Q.QLabel(owner.t('为 {count} 口选中井添加节点；流量单位：{units}', count=well_count,
                                         units='m³/day' if owner.project.units == 'METRIC' else 'STB/day')))
        form = Q.QFormLayout(); layout.addLayout(form)
        self.when = Q.QLineEdit(owner.node_date.text())
        self.when.setPlaceholderText('YYYY-MM-DD HH:MM:SS')
        self.minimum = Q.QLineEdit('0'); self.maximum = Q.QLineEdit('100')
        self.seed = Q.QLineEdit(); self.seed.setPlaceholderText(owner.t('节点流量随机种子（可空）'))
        self.node_type = Q.QComboBox()
        for label, value in [('继承之前类型', None), ('生产井', 'producer'), ('注水井', 'injector')]:
            self.node_type.addItem(owner.t(label), value)
        self.node_type.setCurrentIndex(self.node_type.findData(owner.node_type.currentData()))
        for label, widget in [('节点时间（必填）', self.when), ('最小流量（必填）', self.minimum),
                              ('最大流量（必填）', self.maximum), ('节点流量随机种子（可空）', self.seed),
                              ('从此日起类型', self.node_type)]:
            form.addRow(owner.t(label), widget)
        self.error = Q.QLabel(); self.error.setWordWrap(True); self.error.setStyleSheet('color: #c62828;')
        layout.addWidget(self.error)
        self.buttons = Q.QDialogButtonBox(Q.QDialogButtonBox.Apply | Q.QDialogButtonBox.Cancel)
        self.buttons.button(Q.QDialogButtonBox.Apply).setText(owner.t('应用'))
        self.buttons.button(Q.QDialogButtonBox.Cancel).setText(owner.t('取消'))
        self.buttons.button(Q.QDialogButtonBox.Apply).clicked.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        self.payload = None

    def parameters(self):
        if any(not widget.text().strip() for widget in (self.when, self.minimum, self.maximum)):
            raise ValueError('请填写节点时间、最小流量和最大流量')
        when = day(self.when.text())
        if not day(self.owner.project.start) <= when <= range_end(self.owner.project.end):
            raise ValueError('节点超出项目日期范围')
        try:
            minimum, maximum = rate(self.minimum.text()), rate(self.maximum.text())
        except ValueError:
            raise ValueError('流量必须为有限非负数') from None
        if minimum > maximum: raise ValueError('最小值大于最大值')
        try:
            seed = int(self.seed.text().strip()) if self.seed.text().strip() else None
        except ValueError:
            raise ValueError('随机种子必须为整数') from None
        return dict(when=self.when.text().strip(), minimum=minimum, maximum=maximum,
                    seed=seed, node_type=self.node_type.currentData())

    def accept(self):
        try:
            self.payload = self.parameters()
        except (ValueError, TypeError) as error:
            self.error.setText(self.owner.t(str(error)))
            return
        self.error.clear()
        super().accept()


class Window(Q.QMainWindow):
    def __init__(self, language='en'):
        super().__init__()
        self.language = language
        self.qt_translator = QtCore.QTranslator(self)
        self.qt_translator.load('qtbase_zh_CN', QtCore.QLibraryInfo.path(QtCore.QLibraryInfo.TranslationsPath))
        if language == 'zh': Q.QApplication.instance().installTranslator(self.qt_translator)
        self.plot_font = None
        if sys.platform == 'win32':
            font_path = Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Fonts' / 'msyh.ttc'
            if font_path.exists():
                self.plot_font = FontProperties(fname=str(font_path), size=8)
                font_id = QFontDatabase.addApplicationFont(str(font_path))
                families = QFontDatabase.applicationFontFamilies(font_id)
                if families:
                    Q.QApplication.instance().setFont(QFont(families[0], 9))
        self.project = Project()
        self.workspace_open = True
        self.path = None
        self.dirty = False
        self.loading = False
        self.resize(1400, 900)
        self.update_window_title()
        toolbar = self.addToolBar('项目')
        self.workspace_actions = []
        for label, fn in [('新建', self.new), ('打开', self.open), ('保存', self.save),
                          ('另存为', lambda: self.save(True)), ('关闭当前工区', self.close_workspace)]:
            action = toolbar.addAction(label, lambda checked=False, f=fn: self.guard(f))
            if label in ('保存', '另存为', '关闭当前工区'): self.workspace_actions.append(action)
        toolbar.addSeparator()
        toolbar.addWidget(Q.QLabel('语言'))
        self.language_select = Q.QComboBox()
        self.language_select.addItem('English', 'en'); self.language_select.addItem('中文', 'zh')
        self.language_select.setCurrentIndex(self.language_select.findData(language))
        toolbar.addWidget(self.language_select)
        host = Q.QSplitter(); self.setCentralWidget(host)
        left = Q.QWidget(); ll = Q.QVBoxLayout(left)
        self.search = Q.QLineEdit(); self.search.setPlaceholderText('搜索井名'); ll.addWidget(self.search)
        self.list = Q.QListWidget(); self.list.setSelectionMode(Q.QAbstractItemView.ExtendedSelection); ll.addWidget(self.list)
        for label, fn in [('创建井', self.add_well), ('TXT 批量创建', self.import_wells),
                          ('TXT 选择井', self.select_txt), ('全选', self.list.selectAll),
                          ('重命名', self.rename), ('删除选中井', self.delete_wells),
                          ('默认类型：生产井', lambda: self.kind('producer')), ('默认类型：注水井', lambda: self.kind('injector')),
                          ('复制配置到选中井', self.copy_config)]:
            b = Q.QPushButton(label); b.clicked.connect(lambda checked=False, f=fn: self.guard(f)); ll.addWidget(b)
        host.addWidget(left)
        right = Q.QWidget(); rl = Q.QVBoxLayout(right); host.addWidget(right); host.setSizes([230, 1170])
        self.workspace_panels = (left, right)
        meta = Q.QHBoxLayout(); rl.addLayout(meta)
        self.units = Q.QComboBox(); self.units.addItems(['METRIC', 'FIELD'])
        self.start = Q.QLineEdit(self.project.start); self.end = Q.QLineEdit(self.project.end)
        for label, widget in [('单位', self.units), ('开始', self.start), ('结束', self.end)]:
            meta.addWidget(Q.QLabel(label)); meta.addWidget(widget)
        apply = Q.QPushButton('应用项目设置'); apply.clicked.connect(lambda: self.guard(self.apply_meta)); meta.addWidget(apply)
        self.tabs = Q.QTabWidget(); rl.addWidget(self.tabs)
        edit = Q.QWidget(); el = Q.QVBoxLayout(edit); self.tabs.addTab(edit, '动态编辑')
        transfer = Q.QHBoxLayout(); el.addLayout(transfer)
        for label, fn in [('导入节点 CSV', self.import_csv), ('导出节点 CSV', self.export_selected_nodes),
                          ('导入曲线配置 JSON', self.import_config), ('导出曲线配置 JSON', self.export_selected_config),
                          ('导出每日曲线 CSV', self.export_daily_curves)]:
            button = Q.QPushButton(label)
            button.clicked.connect(lambda checked=False, f=fn: self.guard(f))
            transfer.addWidget(button)
        self.editor_splitter = Q.QSplitter(QtCore.Qt.Vertical)
        self.editor_splitter.setChildrenCollapsible(False)
        self.editor_splitter.setHandleWidth(8)
        self.editor_splitter.setStyleSheet('QSplitter::handle:vertical { background: palette(midlight); border-top: 1px solid palette(mid); border-bottom: 1px solid palette(mid); }')
        el.addWidget(self.editor_splitter, 1)
        plot_panel = Q.QWidget(); plot_layout = Q.QVBoxLayout(plot_panel)
        plot_layout.setContentsMargins(0, 0, 0, 0); plot_panel.setMinimumHeight(160)
        node_panel = Q.QWidget(); node_layout = Q.QVBoxLayout(node_panel)
        node_layout.setContentsMargins(0, 0, 0, 0); node_panel.setMinimumHeight(180)
        self.editor_splitter.addWidget(plot_panel); self.editor_splitter.addWidget(node_panel)
        self.editor_splitter.setStretchFactor(0, 3); self.editor_splitter.setStretchFactor(1, 2)
        self.editor_splitter.setSizes([450, 300])
        self.editor_splitter.handle(1).setCursor(QtCore.Qt.SizeVerCursor)
        self.figure = Figure(figsize=(8, 3), layout='constrained'); self.canvas = FigureCanvasQTAgg(self.figure)
        self.plot_toolbar = PlotToolbar(self.canvas, self, coordinates=False)
        plot_layout.addWidget(self.plot_toolbar)
        self.plot_limits = (None, None, None, None)
        bounds = Q.QHBoxLayout(); plot_layout.addLayout(bounds)
        self.plot_start = Q.QLineEdit(); self.plot_end = Q.QLineEdit()
        self.plot_min = Q.QLineEdit(); self.plot_max = Q.QLineEdit()
        for label, widget in [('日期起点', self.plot_start), ('日期终点', self.plot_end),
                              ('流量下限', self.plot_min), ('流量上限', self.plot_max)]:
            bounds.addWidget(Q.QLabel(label)); bounds.addWidget(widget)
            widget.setPlaceholderText('留空自动')
        for label, fn in [('应用坐标', self.apply_plot_limits), ('自动范围', self.reset_plot_limits)]:
            button = Q.QPushButton(label); bounds.addWidget(button)
            button.clicked.connect(lambda checked=False, f=fn: self.guard(f))
        plot_layout.addWidget(self.canvas, 1)
        self.canvas.mpl_connect('scroll_event', self.scroll_plot)
        sorting = Q.QHBoxLayout(); node_layout.addLayout(sorting)
        sorting.addWidget(Q.QLabel('第一优先级'))
        self.node_sort = Q.QComboBox(); self.node_sort.addItems(['井名', '日期'])
        self.node_sort_order = Q.QComboBox(); self.node_sort_order.addItems(['升序', '降序'])
        sorting.addWidget(self.node_sort); sorting.addWidget(self.node_sort_order)
        sorting.addWidget(Q.QLabel('第二优先级'))
        self.node_sort_secondary = Q.QComboBox(); self.node_sort_secondary.addItems(['井名', '日期'])
        self.node_sort_secondary.setCurrentIndex(1)
        self.node_sort_secondary_order = Q.QComboBox(); self.node_sort_secondary_order.addItems(['升序', '降序'])
        sorting.addWidget(self.node_sort_secondary); sorting.addWidget(self.node_sort_secondary_order)
        sorting.addStretch()
        self.node_rows = []
        self.table = Q.QTableWidget(0, 9); self.table.setHorizontalHeaderLabels(['井名', '日期时间', '流量', '至下一节点方法', 'Arps b', '噪声比例', '噪声种子', '从此日起类型', '生效类型'])
        self.table.horizontalHeader().setSectionResizeMode(Q.QHeaderView.Interactive)
        self.table.horizontalHeader().setMinimumSectionSize(40)
        for column, width in enumerate((110, 175, 100, 145, 90, 110, 90, 155, 120)):
            self.table.setColumnWidth(column, width)
        node_layout.addWidget(self.table, 1)
        row = Q.QHBoxLayout(); node_layout.addLayout(row)
        self.node_date = Q.QLineEdit('2025-01-01 00:00:00')
        self.node_date.setPlaceholderText('YYYY-MM-DD HH:MM:SS')
        self.node_date.setToolTip('支持日期或日期时间；省略时间时为 00:00:00')
        self.node_rate = Q.QDoubleSpinBox(); self.node_rate.setRange(0, 1e12); self.node_rate.setValue(100)
        row.addWidget(Q.QLabel('节点时间')); row.addWidget(self.node_date); row.addWidget(Q.QLabel('流量')); row.addWidget(self.node_rate)
        self.node_type = Q.QComboBox()
        self.node_type.addItem('继承之前类型', None)
        self.node_type.addItem('生产井', 'producer'); self.node_type.addItem('注水井', 'injector')
        row.addWidget(self.node_type)
        for label, fn in [('添加到选中井', self.add_node), ('随机添加', self.random_node), ('删除节点', self.delete_nodes)]:
            b = Q.QPushButton(label); b.clicked.connect(lambda checked=False, f=fn: self.guard(f)); row.addWidget(b)
        row = Q.QHBoxLayout(); node_layout.addLayout(row)
        self.method = Q.QComboBox(); self.method.addItems(['linear', 'arps'])
        self.b = Q.QDoubleSpinBox(); self.b.setRange(0, 1); self.b.setSingleStep(.1); self.b.setValue(.5)
        self.noise = Q.QDoubleSpinBox(); self.noise.setRange(0, 10); self.noise.setSingleStep(.01); self.noise.setValue(.05)
        self.seed = Q.QLineEdit(); self.seed.setPlaceholderText('噪声种子（可空）')
        self.segment_scope = Q.QComboBox()
        self.segment_scope.addItems(['表格选中行', '所选井全部时间段'])
        row.addWidget(Q.QLabel('应用范围')); row.addWidget(self.segment_scope)
        self.fields = []
        for label, widget in [('方法', self.method), ('b', self.b), ('噪声', self.noise), ('噪声种子', self.seed)]:
            check = Q.QCheckBox(label); row.addWidget(check); row.addWidget(widget); self.fields.append(check)
        b = Q.QPushButton('批量应用勾选字段'); b.clicked.connect(lambda: self.guard(self.batch_segments)); row.addWidget(b)
        export = Q.QWidget(); xl = Q.QVBoxLayout(export); self.tabs.addTab(export, '采样与导出')
        form = Q.QFormLayout(); xl.addLayout(form)
        self.frequency = Q.QComboBox()
        for label, code in [('每月', 'monthly'), ('每日', 'daily'), ('自定义', 'custom')]:
            self.frequency.addItem(label, code)
        self.interval = Q.QSpinBox(); self.interval.setRange(1, 36500)
        self.month_position = Q.QComboBox(); self.month_position.addItems(['月初', '月末'])
        self.keep = Q.QCheckBox('保留节点'); self.keep.setChecked(True)
        self.mode = Q.QComboBox()
        for label, code in [('预测', 'prediction'), ('历史', 'history'), ('历史与预测', 'split')]:
            self.mode.addItem(label, code)
        self.split = Q.QLineEdit(); self.split.setPlaceholderText('YYYY-MM-DD HH:MM:SS；从此时开始预测')
        self.bhp = Q.QLineEdit(); self.thp = Q.QLineEdit()
        for label, widget in [('采样', self.frequency), ('每 N 天', self.interval), ('月采样位置', self.month_position),
                              ('保留节点', self.keep), ('模式', self.mode), ('分割日期', self.split),
                              ('历史注水 BHP（bar / psia）', self.bhp), ('历史注水 THP（bar / psia）', self.thp)]:
            form.addRow(label, widget)
        row = Q.QHBoxLayout(); xl.addLayout(row)
        row.addWidget(Q.QLabel('预览格式'))
        self.preview_format = Q.QComboBox()
        self.preview_format.addItem('ECLIPSE INC', 'inc'); self.preview_format.addItem('VOL', 'vol')
        row.addWidget(self.preview_format)
        for label, fn in [('预览', self.preview), ('保存 INC', self.export_inc), ('保存 VOL', self.export_vol),
                          ('复制文本', lambda: Q.QApplication.clipboard().setText(self.text.toPlainText()))]:
            b = Q.QPushButton(label); b.clicked.connect(lambda checked=False, f=fn: self.guard(f)); row.addWidget(b)
        self.text = Q.QPlainTextEdit(); self.text.setReadOnly(True); xl.addWidget(self.text)
        self.samples = Q.QTableWidget(0, 11)
        self.samples.setHorizontalHeaderLabels(['NAME', 'DAY', 'MONTH', 'YEAR', 'OIL', 'WATER', 'GAS', 'WINJ', 'GINJ', 'DAYS', 'TIME'])
        self.samples.setEditTriggers(Q.QAbstractItemView.NoEditTriggers)
        xl.addWidget(self.samples)
        self.samples.horizontalHeader().setSectionResizeMode(Q.QHeaderView.Interactive)
        self.samples.horizontalHeader().setMinimumSectionSize(40)
        for column, width in enumerate((120, 65, 75, 75, 110, 110, 110, 110, 110, 75, 100)):
            self.samples.setColumnWidth(column, width)
        self.samples.setToolTip('OIL/WINJ 为当前单位制的日流量；DAYS 为每日开井小时数（24）；TIME 仅用于表格显示')
        self.search.textChanged.connect(self.filter)
        self.list.itemSelectionChanged.connect(lambda: self.guard(self.refresh_editor))
        self.table.cellChanged.connect(lambda r, c: self.guard(lambda: self.edit_cell(r, c)))
        self.node_sort.currentIndexChanged.connect(lambda: self.guard(lambda: self.update_node_sort(self.node_sort)))
        self.node_sort_secondary.currentIndexChanged.connect(lambda: self.guard(lambda: self.update_node_sort(self.node_sort_secondary)))
        for control in (self.node_sort_order, self.node_sort_secondary_order):
            control.currentIndexChanged.connect(lambda: self.guard(self.refresh_editor))
        self.units.currentTextChanged.connect(lambda: self.guard(self.change_units))
        for widget in (self.start, self.end, self.split, self.bhp, self.thp):
            widget.textEdited.connect(self.mark_dirty)
        for widget in (self.frequency, self.mode):
            widget.currentTextChanged.connect(self.mark_dirty)
        self.frequency.currentTextChanged.connect(self.update_sampling_controls)
        self.mode.currentTextChanged.connect(self.update_mode_controls)
        self.month_position.currentIndexChanged.connect(self.mark_dirty)
        self.interval.valueChanged.connect(self.mark_dirty)
        for widget in (self.keep,):
            widget.toggled.connect(self.mark_dirty)
        self.language_select.currentIndexChanged.connect(lambda: self.set_language(self.language_select.currentData()))
        self.preview_format.currentIndexChanged.connect(self.clear_export_preview)
        self.refresh()
        self.retranslate()

    def t(self, text, **values):
        return translate(text, self.language).format(**values) if values else translate(text, self.language)

    def clear_export_preview(self):
        self.text.clear(); self.samples.setRowCount(0)

    def update_window_title(self):
        name = (Path(self.path).name if self.path else self.t('未命名')) if self.workspace_open else self.t('未打开工区')
        self.setWindowTitle(f'GenSimSchedule — {name}' + (' *' if self.dirty else ''))

    def update_workspace_state(self):
        for panel in self.workspace_panels: panel.setEnabled(self.workspace_open)
        for action in self.workspace_actions: action.setEnabled(self.workspace_open)
        self.update_window_title()

    def set_language(self, language):
        if language not in ('en', 'zh'): raise ValueError('Unsupported language')
        # Commit any active table editor before relabeling, without resetting table selection.
        self.language_select.setFocus()
        self.language = language
        Q.QApplication.instance().removeTranslator(self.qt_translator)
        if language == 'zh': Q.QApplication.instance().installTranslator(self.qt_translator)
        blocker = QtCore.QSignalBlocker(self.language_select)
        self.language_select.setCurrentIndex(self.language_select.findData(language))
        del blocker
        self.retranslate()

    def retranslate(self):
        """Relabel UI only; never recreate the project, controls or user-entered text."""
        reverse = {value: key for key, value in EN.items()}
        def source(obj, name, text):
            key = obj.property(name)
            if key is None:
                key = text if text in EN else reverse.get(text, text)
                obj.setProperty(name, key)
            return self.t(key)
        for obj in self.findChildren(Q.QLabel) + self.findChildren(Q.QAbstractButton):
            obj.setText(source(obj, 'sourceText', obj.text()))
        for bar in self.findChildren(Q.QToolBar):
            bar.setWindowTitle(source(bar, 'sourceTitle', bar.windowTitle()))
            for action in bar.actions():
                if action.text(): action.setText(source(action, 'sourceText', action.text()))
                if action.toolTip(): action.setToolTip(source(action, 'sourceTooltip', action.toolTip()))
        for edit in self.findChildren(Q.QLineEdit):
            if edit.placeholderText():
                edit.setPlaceholderText(source(edit, 'sourcePlaceholder', edit.placeholderText()))
            if edit.toolTip(): edit.setToolTip(source(edit, 'sourceTooltip', edit.toolTip()))
        role = QtCore.Qt.UserRole + 1
        for combo in self.findChildren(Q.QComboBox):
            if isinstance(combo.window(), Q.QDialog): continue
            if combo is self.language_select: continue
            blocker = QtCore.QSignalBlocker(combo)
            for i in range(combo.count()):
                key = combo.itemData(i, role)
                if key is None:
                    text = combo.itemText(i)
                    key = text if text in EN else reverse.get(text, text)
                    combo.setItemData(i, key, role)
                combo.setItemText(i, self.t(key))
            if combo.toolTip(): combo.setToolTip(source(combo, 'sourceTooltip', combo.toolTip()))
            del blocker
        self.tabs.setTabText(0, self.t('动态编辑')); self.tabs.setTabText(1, self.t('采样与导出'))
        for table in (self.table, self.samples):
            if table.toolTip(): table.setToolTip(source(table, 'sourceTooltip', table.toolTip()))
            for col in range(table.columnCount()):
                header = table.horizontalHeaderItem(col)
                key = header.data(role)
                if key is None:
                    key = header.text() if header.text() in EN else reverse.get(header.text(), header.text())
                    header.setData(role, key)
                header.setText(self.t(key))
            blocker = QtCore.QSignalBlocker(table)
            col = 8
            for row in range(table.rowCount() if table is self.table else 0):
                item = table.item(row, col)
                if item:
                    text = item.text()
                    item.setText(self.t(reverse.get(text, text)))
            del blocker
        self.statusBar().showMessage(self.t('{selected} 口井选中；{total} 口井；预览最多 50 口井',
                                           selected=len(self.selected()), total=len(self.project.wells))
                                    if self.workspace_open else self.t('未打开工区；请选择新建或打开'))
        for ax in self.figure.axes:
            for line in ax.lines:
                label = getattr(line, '_schedule_label', None)
                if label: line.set_label(f'{label[0]} ({self.t(label[1])})')
            if ax.get_legend() is not None and ax.get_legend_handles_labels()[0]:
                ax.legend(fontsize=8, prop=self.plot_font)
        self.canvas.draw_idle()
        self.update_workspace_state()

    def message(self, icon, title, text, buttons=None):
        box = Q.QMessageBox(icon, self.t(title), self.t(text), parent=self)
        box.setTextFormat(QtCore.Qt.PlainText)
        box.setStandardButtons(buttons or (Q.QMessageBox.Yes | Q.QMessageBox.No
                               if icon == Q.QMessageBox.Question else Q.QMessageBox.Ok))
        for button, label in [(Q.QMessageBox.Yes, '是'), (Q.QMessageBox.No, '否'),
                              (Q.QMessageBox.Save, '保存'), (Q.QMessageBox.Discard, '放弃'),
                              (Q.QMessageBox.Cancel, '取消'), (Q.QMessageBox.Ok, '确定')]:
            widget = box.button(button)
            if widget: widget.setText(self.t(label))
        return box.exec()

    def input_dialog(self, title, label):
        dialog = Q.QInputDialog(self)
        dialog.setWindowTitle(self.t(title)); dialog.setLabelText(self.t(label))
        dialog.setOkButtonText(self.t('确定')); dialog.setCancelButtonText(self.t('取消'))
        return dialog

    def input_text(self, title, label, text=''):
        dialog = self.input_dialog(title, label); dialog.setTextValue(text)
        return (dialog.textValue(), True) if dialog.exec() else ('', False)

    def input_number(self, title, label, value, minimum, maximum, decimals):
        dialog = self.input_dialog(title, label)
        dialog.setInputMode(Q.QInputDialog.DoubleInput)
        dialog.setDoubleRange(minimum, maximum); dialog.setDoubleDecimals(decimals); dialog.setDoubleValue(value)
        return (dialog.doubleValue(), True) if dialog.exec() else (value, False)

    def input_item(self, title, label, items):
        dialog = self.input_dialog(title, label)
        dialog.setComboBoxItems(items); dialog.setComboBoxEditable(False)
        return (dialog.textValue(), True) if dialog.exec() else ('', False)

    def update_sampling_controls(self, *args):
        frequency = self.frequency.currentData()
        self.interval.setEnabled(frequency == 'custom')
        self.month_position.setEnabled(frequency == 'monthly')

    def resolved_plot_limits(self, limits):
        x0, x1, y0, y1 = limits
        auto_x, auto_y = self.auto_plot_limits
        factor = from_metric(1, self.project.units)
        x = (mdates.date2num(x0) if x0 is not None else auto_x[0],
             mdates.date2num(x1) if x1 is not None else auto_x[1])
        y = (y0 * factor if y0 is not None else auto_y[0],
             y1 * factor if y1 is not None else auto_y[1])
        if x[0] >= x[1] or y[0] >= y[1]:
            raise ValueError('坐标起点必须小于终点')
        return x, y

    def apply_plot_limits(self):
        x = [day(widget.text()) if widget.text().strip() else None
             for widget in (self.plot_start, self.plot_end)]
        y = [float(widget.text()) if widget.text().strip() else None
             for widget in (self.plot_min, self.plot_max)]
        if any(value is not None and not math.isfinite(value) for value in y):
            raise ValueError('坐标必须为有限数值')
        factor = from_metric(1, self.project.units)
        limits = (*x, *(value / factor if value is not None else None for value in y))
        xlim, ylim = self.resolved_plot_limits(limits)
        self.plot_limits = limits
        ax = self.figure.axes[0]; ax.set_xlim(xlim); ax.set_ylim(ylim)
        self.plot_toolbar.push_current(); self.canvas.draw_idle()

    def reset_plot_limits(self):
        self.plot_limits = (None, None, None, None)
        for widget in (self.plot_start, self.plot_end, self.plot_min, self.plot_max): widget.clear()
        ax = self.figure.axes[0]
        ax.set_xlim(self.auto_plot_limits[0]); ax.set_ylim(self.auto_plot_limits[1])
        self.plot_toolbar.push_current(); self.canvas.draw_idle()

    def scroll_plot(self, event):
        if event.inaxes is None or event.xdata is None or event.ydata is None: return
        ax = event.inaxes
        scale = .8 if event.button == 'up' else 1.25
        self.plot_toolbar.push_current()
        for getter, setter, center in [(ax.get_xlim, ax.set_xlim, event.xdata),
                                        (ax.get_ylim, ax.set_ylim, event.ydata)]:
            low, high = getter()
            setter(center + (low-center)*scale, center + (high-center)*scale)
        self.plot_toolbar.push_current(); self.canvas.draw_idle()

    def update_node_sort(self, changed):
        other = self.node_sort_secondary if changed is self.node_sort else self.node_sort
        other.blockSignals(True)
        other.setCurrentIndex(1 - changed.currentIndex())
        other.blockSignals(False)
        self.refresh_editor()

    def update_mode_controls(self, *args):
        mode = self.mode.currentData()
        self.split.setEnabled(mode == 'split')
        self.bhp.setEnabled(mode in ('history', 'split'))
        self.thp.setEnabled(mode in ('history', 'split'))

    def mark_dirty(self, *args):
        if not self.loading and self.workspace_open:
            self.dirty = True
            self.text.clear(); self.samples.setRowCount(0)
            self.update_window_title()

    def guard(self, fn):
        try:
            return fn()
        except (ValueError, OSError, KeyError, TypeError, StopIteration, IndexError) as e:
            self.message(Q.QMessageBox.Warning, '操作失败', str(e) or '请选择井或节点')

    def selected(self):
        return [self.project.well(i.text()) for i in self.list.selectedItems()]

    def require(self):
        if not self.workspace_open: raise ValueError('未打开工区；请选择新建或打开')
        wells = self.selected()
        if not wells: raise ValueError('请先选择井')
        return wells

    def changed(self):
        self.dirty = True
        self.update_window_title()
        self.text.clear(); self.samples.setRowCount(0)
        self.refresh_editor()

    def refresh(self):
        selected = {w.name for w in self.selected()} if self.list.count() else set()
        self.list.blockSignals(True); self.list.clear()
        for w in self.project.wells:
            self.list.addItem(w.name)
            self.list.item(self.list.count()-1).setSelected(w.name in selected)
        self.list.blockSignals(False)
        self.loading = True
        self.units.setCurrentText(self.project.units); self.start.setText(self.project.start); self.end.setText(self.project.end)
        s = self.project.export
        self.frequency.setCurrentIndex(self.frequency.findData(s.frequency)); self.interval.setValue(s.interval)
        self.month_position.setCurrentIndex(1 if s.month_end else 0); self.keep.setChecked(s.keep_nodes); self.mode.setCurrentIndex(self.mode.findData(s.mode))
        self.split.setText(s.split_date or '')
        self.bhp.setText('' if s.injection_bhp is None else str(s.injection_bhp)); self.thp.setText('' if s.injection_thp is None else str(s.injection_thp))
        self.loading = False
        self.update_sampling_controls()
        self.update_mode_controls()
        self.filter(); self.refresh_editor()

    def filter(self):
        for i in range(self.list.count()):
            self.list.item(i).setHidden(self.search.text().lower() not in self.list.item(i).text().lower())

    def refresh_editor(self):
        wells = self.selected(); self.loading = True
        self.table.setRowCount(0)
        rows = []
        for w in wells:
            w.sync_segments()
            outgoing = {s.start_node_id: s for s in w.segments}
            rows.extend((w, n, outgoing.get(n.id)) for n in w.nodes)
        def sort_value(entry, field):
            return entry[0].name if field == 0 else entry[1].date
        # Stable sorting from secondary to primary supports independent directions.
        rows.sort(key=lambda entry: sort_value(entry, self.node_sort_secondary.currentIndex()),
                  reverse=self.node_sort_secondary_order.currentIndex() == 1)
        rows.sort(key=lambda entry: sort_value(entry, self.node_sort.currentIndex()),
                  reverse=self.node_sort_order.currentIndex() == 1)
        self.node_rows = [(w.name, n.id) for w, n, s in rows]
        self.table.setRowCount(len(rows))
        for row, (w, n, s) in enumerate(rows):
            values = [w.name, n.date, f'{from_metric(n.rate, self.project.units):.12g}',
                      '', str(s.b) if s else '', str(s.noise) if s else '',
                      str(s.seed) if s and s.seed is not None else '', '',
                      '生产井' if w.type_at(n.date) == 'producer' else '注水井']
            for col, value in enumerate(values):
                item = Q.QTableWidgetItem(value)
                if col in (0, 3, 7, 8) or (3 <= col <= 6 and s is None):
                    item.setFlags(item.flags() & ~QtCore.Qt.ItemIsEditable)
                self.table.setItem(row, col, item)
            if s is not None:
                method = Q.QComboBox()
                method.addItems(['linear', 'arps'])
                method.setCurrentText(s.method)
                method.currentTextChanged.connect(
                    lambda value, well_name=w.name, node_id=n.id:
                    self.guard(lambda: self.edit_segment_method(well_name, node_id, value)))
                self.table.setCellWidget(row, 3, method)
            type_select = Q.QComboBox()
            type_select.addItem('继承之前类型', None)
            type_select.addItem('生产井', 'producer'); type_select.addItem('注水井', 'injector')
            type_select.setCurrentIndex(type_select.findData(n.type))
            type_select.setToolTip('从本节点日期起生效；继承表示沿用前一次设置或井的默认类型')
            type_select.currentIndexChanged.connect(
                lambda index, control=type_select, well_name=w.name, node_id=n.id:
                self.guard(lambda: self.edit_node_type(well_name, node_id, control.currentData())))
            self.table.setCellWidget(row, 7, type_select)
        self.loading = False
        self.figure.clear(); ax = self.figure.add_subplot()
        for well_index, w in enumerate(wells[:50]):
            values = curve(w)
            labeled = set()
            well_color = f'C{well_index}'
            for kind, group in groupby(values.items(), key=lambda entry: w.type_at(entry[0])):
                points = list(group)
                phase = '油量' if kind == 'producer' else '注水量'
                line, = ax.plot([d for d, q in points], [from_metric(q, self.project.units) for d, q in points],
                               color=well_color,
                               linestyle='-' if kind == 'producer' else '--',
                               label=f'{w.name} ({self.t(phase)})' if kind not in labeled else '_nolegend_')
                if kind not in labeled: line._schedule_label = (w.name, phase)
                labeled.add(kind)
                dates = {d for d, q in points}
                nodes = [n for n in w.nodes if day(n.date) in dates]
                ax.scatter([day(n.date) for n in nodes],
                           [from_metric(n.rate, self.project.units) for n in nodes], s=18, color=line.get_color())
        ax.set_ylabel('m³/day' if self.project.units == 'METRIC' else 'STB/day'); ax.grid(alpha=.2)
        if ax.get_legend_handles_labels()[0]: ax.legend(fontsize=8, prop=self.plot_font)
        self.figure.autofmt_xdate(); self.canvas.draw_idle()
        self.auto_plot_limits = (ax.get_xlim(), ax.get_ylim())
        try:
            xlim, ylim = self.resolved_plot_limits(self.plot_limits)
        except ValueError:
            # A partially automatic bound can become invalid when selecting different wells.
            self.reset_plot_limits()
        else:
            ax.set_xlim(xlim); ax.set_ylim(ylim)
        self.plot_toolbar.update(); self.plot_toolbar.push_current()
        self.retranslate()

    def edit_cell(self, row, col):
        if self.loading: return
        if col in (0, 3, 7, 8): return
        well_name, node_id = self.node_rows[row]
        w = self.project.well(well_name)
        index = next(i for i, node in enumerate(w.nodes) if node.id == node_id)
        n = w.nodes[index]
        try:
            if col < 3:
                w.edit_node(n.id, self.table.item(row, 1).text(), to_metric(self.table.item(row, 2).text(), self.project.units))
            else:
                segment_index = w.segment_index(node_id)
                if segment_index is None: return
                s = replace(w.segments[segment_index],
                            b=float(self.table.item(row, 4).text()), noise=float(self.table.item(row, 5).text()),
                            seed=int(self.table.item(row, 6).text()) if self.table.item(row, 6).text() else None)
                s.validate(); w.segments[segment_index] = s
        except Exception:
            self.refresh_editor(); raise
        self.changed()

    def edit_segment_method(self, well_name, node_id, method):
        if self.loading: return
        well = self.project.well(well_name)
        index = well.segment_index(node_id)
        if index is None: return
        segment = replace(well.segments[index], method=method)
        segment.validate()
        well.segments[index] = segment
        self.changed()

    def edit_node_type(self, well_name, node_id, node_type):
        if self.loading: return
        well = self.project.well(well_name)
        node = next(n for n in well.nodes if n.id == node_id)
        well.edit_node(node.id, node.date, node.rate, node_type)
        self.changed()

    def choose(self, save=False, pattern='JSON (*.json)'):
        dialog = Q.QFileDialog(self, self.t('选择文件'))
        dialog.setOption(Q.QFileDialog.DontUseNativeDialog, True)
        dialog.setNameFilter(pattern)
        if save:
            extension = re.search(r'\*\.([A-Za-z0-9]+)', pattern)
            if extension: dialog.setDefaultSuffix(extension.group(1))
        dialog.setAcceptMode(Q.QFileDialog.AcceptSave if save else Q.QFileDialog.AcceptOpen)
        dialog.setFileMode(Q.QFileDialog.AnyFile if save else Q.QFileDialog.ExistingFile)
        dialog.setLabelText(Q.QFileDialog.Accept, self.t('保存' if save else '打开'))
        dialog.setLabelText(Q.QFileDialog.Reject, self.t('取消'))
        return dialog.selectedFiles()[0] if dialog.exec() else ''

    def confirm_unsaved(self):
        if not self.workspace_open or not self.dirty: return True
        answer = self.message(Q.QMessageBox.Question, '未保存', '保存当前项目？', Q.QMessageBox.Save | Q.QMessageBox.Discard | Q.QMessageBox.Cancel)
        if answer == Q.QMessageBox.Cancel: return False
        return bool(self.save()) if answer == Q.QMessageBox.Save else True

    def new(self):
        if not self.confirm_unsaved(): return False
        self.reset_workspace(active=True)
        return True

    def close_workspace(self):
        if not self.confirm_unsaved(): return False
        self.reset_workspace(active=False)
        return True

    def reset_workspace(self, active):
        self.reset_plot_limits()
        blocker = QtCore.QSignalBlocker(self.list)
        self.list.clear()
        del blocker
        self.workspace_open = active
        self.project = Project(); self.path = None; self.dirty = False
        self.search.clear(); self.clear_export_preview()
        self.refresh(); self.update_workspace_state()

    def open(self):
        if not self.confirm_unsaved(): return
        path = self.choose()
        if path:
            project = storage.load(path); self.reset_plot_limits(); self.list.clear(); self.project = project; self.path = path; self.dirty = False
            self.workspace_open = True
            self.text.clear(); self.refresh(); self.update_window_title()

    def save(self, as_new=False):
        if not self.workspace_open: raise ValueError('未打开工区；请选择新建或打开')
        path = self.choose(True) if as_new or not self.path else self.path
        if not path: return False
        self.apply_meta(); self.settings()
        candidate = replace(self.project, name=Path(path).stem)
        storage.save(candidate, path)
        self.project.name = candidate.name
        self.path = path; self.dirty = False; self.update_window_title(); return True

    def apply_meta(self):
        candidate = replace(self.project, start=self.start.text(), end=self.end.text())
        candidate.validate(); self.project.start = candidate.start; self.project.end = candidate.end; self.changed()

    def change_units(self):
        if self.loading: return
        previous = self.project.units
        self.project.units = self.units.currentText()
        factor = from_metric(1, self.project.units) / from_metric(1, previous)
        for widget in (self.plot_min, self.plot_max):
            if widget.text().strip(): widget.setText(f'{float(widget.text()) * factor:.12g}')
        self.node_rate.setValue(from_metric(to_metric(self.node_rate.value(), previous), self.project.units))
        # Pressure inputs are in target units; convert their representation too.
        for widget in (self.bhp, self.thp):
            if widget.text(): widget.setText(str(float(widget.text()) * (14.503773773 if self.project.units == 'FIELD' else 1/14.503773773)))
        self.changed()

    def add_well(self):
        name, ok = self.input_text('创建井', '井名')
        if ok:
            if not self.project.add_well(name): raise ValueError('井名已存在')
            self.refresh(); self.changed()

    def import_wells(self):
        path = self.choose(pattern='TXT (*.txt)')
        if path: report = storage.import_wells(self.project, path); self.refresh(); self.changed(); self.report(report)

    def select_txt(self):
        path = self.choose(pattern='TXT (*.txt)')
        if path:
            names = set(storage.names(path)); self.list.blockSignals(True)
            for i in range(self.list.count()): self.list.item(i).setSelected(self.list.item(i).text() in names)
            self.list.blockSignals(False); self.refresh_editor()
            unknown = names - {w.name for w in self.project.wells}
            if unknown: self.message(Q.QMessageBox.Information, '未匹配井', '\n'.join(sorted(unknown)))

    def rename(self):
        wells = self.require()
        if len(wells) != 1: raise ValueError('重命名请选择一口井')
        name, ok = self.input_text('重命名', '新井名', text=wells[0].name)
        if ok:
            candidate = replace(wells[0], name=name); candidate.validate()
            if any(w is not wells[0] and w.name == name for w in self.project.wells): raise ValueError('井名已存在')
            wells[0].name = name; self.refresh(); self.changed()

    def delete_wells(self):
        wells = self.require()
        if self.message(Q.QMessageBox.Question, '删除井', self.t('删除 {count} 口井及其配置？', count=len(wells))) == Q.QMessageBox.Yes:
            self.project.wells = [w for w in self.project.wells if w not in wells]; self.refresh(); self.changed()

    def kind(self, kind):
        for w in self.require():
            w.kind = kind
            w.sync_segments()
        self.changed()

    def copy_config(self):
        wells = self.require(); name, ok = self.input_item('复制配置', '源井', [w.name for w in self.project.wells])
        if ok and self.message(Q.QMessageBox.Question, '覆盖配置', '覆盖所选目标井的默认类型、全部节点和段参数？') == Q.QMessageBox.Yes:
            source = self.project.well(name)
            for w in wells:
                if w is not source: w.copy_from(source)
            self.changed()

    def add_node(self):
        self.report(add_nodes(self.project, self.require(), self.node_date.text(), self.node_rate.value(), node_type=self.node_type.currentData())); self.changed()

    def random_node(self):
        wells = self.require()
        dialog = RandomNodeDialog(self, len(wells))
        if dialog.exec() == Q.QDialog.Accepted:
            report = add_nodes(self.project, wells, **dialog.payload)
            if report['success']: self.changed()
            self.report(report)

    def delete_nodes(self):
        targets = [self.node_rows[r] for r in sorted({i.row() for i in self.table.selectedIndexes()})]
        for well_name, node_id in targets:
            self.project.well(well_name).delete_node(node_id)
        self.changed()

    def batch_segments(self):
        changes = {}
        for key, widget, checkbox in zip(('method', 'b', 'noise', 'seed'),
                                        (self.method, self.b, self.noise, self.seed), self.fields):
            if not checkbox.isChecked(): continue
            if key == 'method': value = widget.currentText()
            elif key == 'seed': value = int(widget.text()) if widget.text() else None
            else: value = widget.value()
            changes[key] = value
        if not changes: raise ValueError('请勾选需要应用的字段')
        targets = []
        skipped = 0
        if self.segment_scope.currentIndex() == 0:
            rows = sorted({i.row() for i in self.table.selectedIndexes()})
            if not rows: raise ValueError('请先在节点表中选择需要应用的行')
            for row in rows:
                well_name, node_id = self.node_rows[row]
                well = self.project.well(well_name)
                index = well.segment_index(node_id)
                if index is None: skipped += 1
                else: targets.append((well, index))
        else:
            targets = [(well, i) for well in self.require() for i in range(len(well.segments))]
        # Validate the full update before changing any selected segment.
        updates = [(well, index, replace(well.segments[index], **changes)) for well, index in targets]
        for well, index, segment in updates: segment.validate()
        for well, index, segment in updates: well.segments[index] = segment
        if updates: self.changed()
        self.report({'success': len(updates), 'skipped': skipped, 'errors': []})

    def report(self, report):
        self.message(Q.QMessageBox.Information, '操作报告',
                     self.t('成功 {success}；跳过 {skipped}；问题 {errors}', success=report['success'],
                            skipped=report['skipped'], errors=len(report['errors'])) + '\n' +
                     '\n'.join(self.t(error) for error in report['errors'][:30]))

    def import_csv(self):
        path = self.choose(pattern='CSV (*.csv)')
        if path:
            options = [self.t('跳过'), self.t('覆盖')]
            conflict, ok = self.input_item('冲突策略', '同日节点', options)
            if ok:
                self.report(storage.import_nodes(self.project, path, ('skip', 'overwrite')[options.index(conflict)])); self.changed()

    def export_selected_nodes(self):
        wells = self.require()
        path = self.choose(True, 'CSV (*.csv)')
        if path:
            storage.export_nodes(replace(self.project, wells=wells), path)

    def export_selected_config(self):
        wells = self.require()
        path = self.choose(True)
        if path:
            storage.save(replace(self.project, wells=wells), path)

    def export_daily_curves(self):
        wells = self.require()
        path = self.choose(True, 'CSV (*.csv)')
        if path:
            with open(path, 'w', encoding='utf-8', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(['well', 'date', 'rate', 'type'])
                for well in wells:
                    writer.writerows((well.name, d.isoformat(), from_metric(q, self.project.units), well.type_at(d))
                                     for d, q in curve(well).items())

    def import_config(self):
        path = self.choose()
        if not path: return
        source = storage.load(path)
        if self.message(Q.QMessageBox.Question, '配置导入', '导入全部井配置，同名井将覆盖，其他项目设置保留？') != Q.QMessageBox.Yes: return
        for w in source.wells:
            if not any(x.name == w.name for x in self.project.wells): self.project.add_well(w.name, w.kind)
            target = self.project.well(w.name)
            target.kind = w.kind
            target.copy_from(w)
        self.refresh(); self.changed()

    def settings(self):
        s = replace(self.project.export, frequency=self.frequency.currentData(), interval=self.interval.value(),
                    month_end=self.month_position.currentIndex() == 1, keep_nodes=self.keep.isChecked(), mode=self.mode.currentData(),
                    split_date=self.split.text() or None, units=self.project.units,
                    injection_bhp=float(self.bhp.text()) if self.bhp.text() else None,
                    injection_thp=float(self.thp.text()) if self.thp.text() else None)
        s.validate()
        if s != self.project.export: self.project.export = s; self.dirty = True
        return s

    def preview(self):
        self.apply_meta(); s = self.settings(); wells = self.require()
        sampled = {w.name: sample(self.project, w, s) for w in wells}
        data = sampled_rows(self.project, wells, s, sampled=sampled)
        rows = [(row.name, *row.fields(), row.when.strftime('%H:%M:%S')) for row in data]
        self.samples.setRowCount(len(rows))
        for r, values in enumerate(rows):
            for c, value in enumerate(values): self.samples.setItem(r, c, Q.QTableWidgetItem(value))
        self.retranslate()
        text = render_rows(data, s.units) if self.preview_format.currentData() == 'vol' else render(self.project, wells, s, sampled=sampled)
        self.text.setPlainText(text)

    def export_inc(self):
        self.preview_format.setCurrentIndex(self.preview_format.findData('inc'))
        self.preview(); path = self.choose(True, 'ECLIPSE (*.inc *.INC)')
        if path: Path(path).write_text(self.text.toPlainText(), encoding='utf-8')

    def export_vol(self):
        self.preview_format.setCurrentIndex(self.preview_format.findData('vol'))
        self.preview(); path = self.choose(True, 'VOL (*.VOL *.vol)')
        if path:
            target = Path(path)
            if target.suffix.lower() != '.vol': target = target.with_suffix('.VOL')
            target.write_text(self.text.toPlainText(), encoding='utf-8')

    def closeEvent(self, event):
        try: accepted = self.confirm_unsaved()
        except (ValueError, OSError) as e: self.message(Q.QMessageBox.Warning, '保存失败', str(e)); accepted = False
        event.accept() if accepted else event.ignore()
        if accepted: Q.QApplication.instance().removeTranslator(self.qt_translator)


def main():
    app = Q.QApplication(sys.argv); window = Window(); window.show(); sys.exit(app.exec())


if __name__ == '__main__':
    main()
