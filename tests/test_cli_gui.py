import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from gensimschedule.cli import parser, execute
from gensimschedule import storage
import pytest


def test_cli_workflow(tmp_path):
    p = tmp_path / 'demo.json'; output = tmp_path / 'demo.inc'
    def run(text): return execute(parser().parse_args(text))
    run(['project', 'new', str(p)])
    run(['well', 'add', 'P1', '--project', str(p)])
    for d, q in [('2025-01-01', '100'), ('2025-04-01', '20')]:
        run(['node', 'add', d, '--rate', q, '--project', str(p)])
    run(['curve', 'set', '--method', 'arps', '--seed', '1', '--project', str(p)])
    run(['export', 'eclipse', str(output), '--project', str(p)])
    assert 'WCONPROD' in output.read_text()
    assert storage.load(p).wells[0].segments[0].method == 'arps'


def test_batch_segment_scope():
    from PySide6.QtWidgets import QApplication, QTableWidgetSelectionRange
    from gensimschedule.gui import Window
    app = QApplication.instance() or QApplication([])
    window = Window(language='zh')
    reports = []
    window.report = reports.append
    try:
        for name in ('A', 'B', 'C'):
            window.project.add_well(name)
            for month in (1, 2, 3):
                window.project.well(name).add_node(f'2025-0{month}-01', 100 / month)
        window.refresh()
        window.list.item(0).setSelected(True); window.list.item(1).setSelected(True)
        window.node_sort.setCurrentIndex(1)
        assert window.segment_scope.currentText() == '表格选中行'
        with pytest.raises(ValueError, match='勾选'): window.batch_segments()
        window.fields[0].setChecked(True); window.method.setCurrentText('arps')
        with pytest.raises(ValueError, match='选择'): window.batch_segments()
        # Interleaved rows: A January, B February, and A's final node.
        for r in (0, 3, 4):
            window.table.setRangeSelected(QTableWidgetSelectionRange(r, 0, r, 6), True)
        window.seed.setText('invalid unchecked field')
        window.batch_segments()
        a, b, c = window.project.wells
        assert [s.method for s in a.segments] == ['arps', 'linear']
        assert [s.method for s in b.segments] == ['linear', 'arps']
        assert all(s.method == 'linear' for s in c.segments)
        assert reports[-1] == {'success': 2, 'skipped': 1, 'errors': []}
        window.segment_scope.setCurrentIndex(1)
        window.fields[0].setChecked(False); window.fields[2].setChecked(True)
        window.noise.setValue(.1); window.batch_segments()
        assert all(s.noise == .1 for w in (a, b) for s in w.segments)
        assert all(s.noise == 0 for s in c.segments)
        assert [s.method for s in a.segments] == ['arps', 'linear']
        assert reports[-1]['success'] == 4
        app.processEvents()
    finally:
        window.dirty = False; window.close()


def test_curve_tab_exports_selected_wells(tmp_path):
    import csv
    from PySide6.QtWidgets import QApplication
    from gensimschedule.gui import Window
    app = QApplication.instance() or QApplication([])
    window = Window(language='zh')
    try:
        for name in ('A', 'B'):
            window.project.add_well(name)
            well = window.project.well(name)
            well.add_node('2025-01-01', 100)
            well.add_node('2025-01-03', 50)
            well.set_segments(method='arps', noise=.05, seed=42)
        window.project.units = 'FIELD'
        window.refresh(); window.list.item(1).setSelected(True)
        nodes_path = tmp_path / 'nodes.csv'
        window.choose = lambda *args, **kwargs: str(nodes_path)
        window.export_selected_nodes()
        with nodes_path.open(newline='', encoding='utf-8') as f: rows = list(csv.DictReader(f))
        assert len(rows) == 2 and {r['well'] for r in rows} == {'B'}
        from gensimschedule.core import from_metric
        assert float(rows[0]['rate']) == pytest.approx(from_metric(100, 'FIELD'))
        config_path = tmp_path / 'config.json'
        window.choose = lambda *args, **kwargs: str(config_path)
        window.export_selected_config()
        restored = storage.load(config_path)
        assert [w.name for w in restored.wells] == ['B']
        assert restored.units == 'FIELD'
        assert restored.wells[0].segments[0].seed == 42
        assert restored.wells[0].segments[0].method == 'arps'
        daily_path = tmp_path / 'daily.csv'
        window.choose = lambda *args, **kwargs: str(daily_path)
        window.export_daily_curves()
        with daily_path.open(newline='', encoding='utf-8') as f: rows = list(csv.DictReader(f))
        assert len(rows) == 3 and {r['well'] for r in rows} == {'B'}
        window.list.clearSelection()
        with pytest.raises(ValueError, match='选择井'): window.export_selected_config()
        app.processEvents()
    finally:
        window.dirty = False; window.close()


def test_gui_smoke():
    from PySide6.QtWidgets import QApplication
    from gensimschedule.gui import Window
    app = QApplication.instance() or QApplication([])
    window = Window(language='zh')
    from PySide6.QtWidgets import QToolBar
    assert [action.text() for action in window.findChild(QToolBar).actions() if action.text()] == ['新建', '打开', '保存', '另存为', '关闭当前工区']
    assert [window.tabs.tabText(i) for i in range(window.tabs.count())] == ['动态编辑', '采样与导出']
    window.project.add_well('P1')
    window.project.wells[0].add_node('2025-01-01', 100)
    window.project.wells[0].add_node('2025-04-01', 20)
    window.refresh(); window.list.item(0).setSelected(True)
    window.preview(); app.processEvents()
    assert window.table.rowCount() == 2
    assert 'WCONPROD' in window.text.toPlainText()
    window.dirty = False; window.close()


def test_saved_project_title_tracks_file(tmp_path):
    from PySide6.QtWidgets import QApplication
    from gensimschedule.gui import Window
    app = QApplication.instance() or QApplication([])
    window = Window()
    try:
        assert window.windowTitle() == 'GenSimSchedule — Untitled'
        first = tmp_path / 'demo.json'
        window.choose = lambda *args, **kwargs: str(first)
        assert window.save()
        assert window.windowTitle() == 'GenSimSchedule — demo.json'
        assert storage.load(first).name == 'demo'
        window.changed()
        assert window.windowTitle() == 'GenSimSchedule — demo.json *'
        assert window.save()
        second = tmp_path / 'renamed.json'
        window.choose = lambda *args, **kwargs: str(second)
        assert window.save(True)
        assert window.windowTitle() == 'GenSimSchedule — renamed.json'
        assert storage.load(second).name == 'renamed'
        window.set_language('zh')
        assert window.windowTitle() == 'GenSimSchedule — renamed.json'
        window.choose = lambda *args, **kwargs: ''
        assert not window.save(True)
        assert window.windowTitle() == 'GenSimSchedule — renamed.json'
        # Older projects may contain an Untitled metadata name; opening shows the file.
        project = storage.load(first); project.name = 'Untitled'; storage.save(project, first)
        window.choose = lambda *args, **kwargs: str(first)
        window.open()
        assert window.windowTitle() == 'GenSimSchedule — demo.json'
        app.processEvents()
    finally:
        window.dirty = False; window.close()


def test_save_dialog_adds_json_suffix(tmp_path, monkeypatch):
    from PySide6.QtWidgets import QApplication, QFileDialog, QDialog
    from gensimschedule.gui import Window
    app = QApplication.instance() or QApplication([])
    window = Window()
    try:
        def accept(dialog):
            assert dialog.defaultSuffix() == 'json'
            dialog.selectFile(str(tmp_path / 'my_project'))
            return QDialog.Accepted
        monkeypatch.setattr(QFileDialog, 'exec', accept)
        assert window.save()
        assert (tmp_path / 'my_project.json').exists()
        from pathlib import Path
        assert Path(window.path) == tmp_path / 'my_project.json'
        assert window.project.name == 'my_project'
        assert window.windowTitle().endswith('my_project.json')
        app.processEvents()
    finally:
        window.dirty = False; window.close()


def test_close_workspace_preserves_cancel_and_saves_before_clearing(tmp_path):
    from PySide6.QtWidgets import QApplication, QMessageBox
    from gensimschedule.gui import Window
    app = QApplication.instance() or QApplication([])
    window = Window()
    try:
        window.project.add_well('W1')
        window.project.wells[0].add_node('2025-01-01', 100)
        window.refresh(); window.list.item(0).setSelected(True); window.preview()
        window.message = lambda *args: QMessageBox.Cancel
        assert not window.close_workspace()
        assert len(window.project.wells) == 1 and window.list.count() == 1
        # Canceling Save As also cancels closing.
        window.message = lambda *args: QMessageBox.Save
        window.choose = lambda *args, **kwargs: ''
        assert not window.close_workspace()
        assert len(window.project.wells) == 1
        path = tmp_path / 'before_close.json'
        window.choose = lambda *args, **kwargs: str(path)
        assert window.close_workspace()
        assert storage.load(path).wells[0].name == 'W1'
        assert not window.workspace_open
        assert all(not panel.isEnabled() for panel in window.workspace_panels)
        assert all(not action.isEnabled() for action in window.workspace_actions)
        assert window.language_select.isEnabled()
        assert 'No workspace open' in window.windowTitle()
        assert window.path is None and not window.dirty
        assert not window.project.wells and window.list.count() == 0
        assert window.table.rowCount() == window.samples.rowCount() == 0
        assert not window.text.toPlainText()
        assert not window.figure.axes[0].lines
        assert window.language == 'en'
        # Closing a clean workspace is safe to repeat.
        assert window.close_workspace()
        with pytest.raises(ValueError, match='未打开工区'): window.save()
        window.set_language('zh')
        assert '未打开工区' in window.windowTitle()
        assert all(not panel.isEnabled() for panel in window.workspace_panels)
        # New creates an editable workspace rather than remaining closed.
        assert window.new()
        assert window.workspace_open and not window.dirty and window.path is None
        assert all(panel.isEnabled() for panel in window.workspace_panels)
        assert all(action.isEnabled() for action in window.workspace_actions)
        assert '未命名' in window.windowTitle()
        # Open from the closed state enables the editor and restores the file.
        window.close_workspace()
        window.choose = lambda *args, **kwargs: ''
        window.open()
        assert not window.workspace_open
        window.choose = lambda *args, **kwargs: str(path)
        window.open()
        assert window.workspace_open and window.project.wells[0].name == 'W1'
        assert all(panel.isEnabled() for panel in window.workspace_panels)
        app.processEvents()
    finally:
        window.dirty = False; window.close()


def test_sampling_controls_follow_frequency():
    from PySide6.QtWidgets import QApplication
    from gensimschedule.gui import Window
    app = QApplication.instance() or QApplication([])
    window = Window(language='zh')
    try:
        assert window.frequency.currentData() == 'monthly'
        assert window.month_position.isEnabled()
        assert window.month_position.currentText() == '月初'
        assert not window.interval.isEnabled()
        window.month_position.setCurrentText('月末')
        assert window.settings().month_end
        window.frequency.setCurrentIndex(window.frequency.findData('custom'))
        assert window.interval.isEnabled() and not window.month_position.isEnabled()
        window.interval.setValue(10)
        assert window.settings().interval == 10
        window.frequency.setCurrentIndex(window.frequency.findData('daily'))
        assert not window.interval.isEnabled() and not window.month_position.isEnabled()
        window.frequency.setCurrentIndex(window.frequency.findData('monthly'))
        assert window.month_position.currentText() == '月末'
        # Restoring project settings also restores the corresponding enabled state.
        window.project.export.frequency = 'custom'
        window.refresh()
        assert window.interval.isEnabled() and not window.month_position.isEnabled()
        app.processEvents()
    finally:
        window.dirty = False
        window.close()


def test_export_mode_controls():
    from PySide6.QtWidgets import QApplication
    from gensimschedule.gui import Window
    app = QApplication.instance() or QApplication([])
    window = Window(language='zh')
    try:
        assert window.mode.currentData() == 'prediction'
        assert not window.split.isEnabled()
        assert not window.bhp.isEnabled() and not window.thp.isEnabled()
        window.mode.setCurrentIndex(window.mode.findData('split'))
        assert window.split.isEnabled()
        assert window.bhp.isEnabled() and window.thp.isEnabled()
        window.split.setText('2025-07-01')
        assert window.settings().split_date == '2025-07-01'
        window.mode.setCurrentIndex(window.mode.findData('history'))
        assert not window.split.isEnabled()
        assert window.bhp.isEnabled() and window.thp.isEnabled()
        window.mode.setCurrentIndex(window.mode.findData('prediction'))
        assert not window.split.isEnabled()
        assert not window.bhp.isEnabled() and not window.thp.isEnabled()
        window.mode.setCurrentIndex(window.mode.findData('split'))
        assert window.split.text() == '2025-07-01'
        window.project.export.mode = 'history'
        window.refresh()
        assert not window.split.isEnabled() and window.bhp.isEnabled()
        app.processEvents()
    finally:
        window.dirty = False
        window.close()


def test_multiwell_node_sort_edit_delete():
    from PySide6.QtWidgets import QApplication, QTableWidgetSelectionRange
    from PySide6.QtCore import Qt
    from gensimschedule.gui import Window
    app = QApplication.instance() or QApplication([])
    window = Window(language='zh')
    try:
        for name in ('B', 'A', 'EMPTY', 'UNSELECTED'):
            window.project.add_well(name)
        a, b = window.project.well('A'), window.project.well('B')
        for when, q in [('2025-02-01', 20), ('2025-04-01', 10)]:
            a.add_node(when, q)
        for when, q in [('2025-01-01', 100), ('2025-04-01', 50), ('2025-05-01', 30)]:
            b.add_node(when, q)
        window.project.well('UNSELECTED').add_node('2025-01-01', 999)
        window.refresh()
        for i in range(3): window.list.item(i).setSelected(True)
        def displayed():
            return [(window.table.item(r, 0).text(), window.table.item(r, 1).text())
                    for r in range(window.table.rowCount())]
        assert displayed() == [('A', '2025-02-01'), ('A', '2025-04-01'),
                               ('B', '2025-01-01'), ('B', '2025-04-01'), ('B', '2025-05-01')]
        original = displayed()
        for primary in (0, 1):
            for descending_first in (0, 1):
                for descending_second in (0, 1):
                    window.node_sort.setCurrentIndex(primary)
                    window.node_sort_order.setCurrentIndex(descending_first)
                    window.node_sort_secondary_order.setCurrentIndex(descending_second)
                    expected = sorted(original, key=lambda x: x[1-primary], reverse=bool(descending_second))
                    expected.sort(key=lambda x: x[primary], reverse=bool(descending_first))
                    assert displayed() == expected
                    assert window.node_sort_secondary.currentIndex() == 1-primary
        # Changing the secondary priority also keeps the primary field distinct.
        window.node_sort_secondary.setCurrentIndex(1)
        assert window.node_sort.currentIndex() == 0
        window.node_sort_order.setCurrentIndex(0)
        window.node_sort_secondary_order.setCurrentIndex(0)
        window.node_sort.setCurrentIndex(1)
        assert displayed() == [('B', '2025-01-01'), ('A', '2025-02-01'),
                               ('A', '2025-04-01'), ('B', '2025-04-01'), ('B', '2025-05-01')]
        assert not window.table.item(0, 0).flags() & Qt.ItemIsEditable
        assert not window.table.item(2, 3).flags() & Qt.ItemIsEditable
        # Interleaved rows must edit their owning well and its actual outgoing segment.
        assert window.table.cellWidget(2, 3) is None
        method = window.table.cellWidget(3, 3)
        assert window.table.item(3, 3).text() == ''
        assert [method.itemText(i) for i in range(method.count())] == ['linear', 'arps']
        method.setCurrentText('arps')
        assert b.segments[1].method == 'arps' and a.segments[0].method == 'linear'
        assert window.table.cellWidget(3, 3).currentText() == 'arps'
        assert window.table.item(3, 3).text() == ''
        window.table.item(1, 2).setText('25')
        assert a.nodes[0].rate == 25 and b.nodes[0].rate == 100
        node_id = a.nodes[0].id
        window.table.item(1, 1).setText('2025-06-01')
        assert displayed()[-1] == ('A', '2025-06-01')
        assert a.nodes[-1].id == node_id
        # Delete rows from different wells after dates have been re-sorted.
        window.table.clearSelection()
        for r in (0, 1):
            window.table.setRangeSelected(QTableWidgetSelectionRange(r, 0, r, 6), True)
        window.delete_nodes()
        assert [n.date for n in a.nodes] == ['2025-06-01']
        assert [n.date for n in b.nodes] == ['2025-04-01', '2025-05-01']
        assert window.table.rowCount() == 3
        assert len(window.project.well('UNSELECTED').nodes) == 1
        app.processEvents()
    finally:
        window.dirty = False
        window.close()
