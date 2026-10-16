import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'

from dataclasses import asdict
from PySide6 import QtWidgets as Q
from PySide6.QtCore import QTimer
from gensimschedule.gui import Window
from gensimschedule.eclipse import render


def test_default_english_and_switch_preserves_editing_state():
    app = Q.QApplication.instance() or Q.QApplication([])
    window = Window()
    try:
        assert window.language == 'en'
        assert window.tabs.tabText(0) == 'Schedule Editor'
        assert window.tabs.tabText(1) == 'Sampling and Export'
        assert window.search.placeholderText() == 'Search wells'
        assert window.frequency.currentText() == 'Monthly'
        assert window.mode.currentText() == 'Prediction'
        window.project.add_well('生产井')  # A user name must never be translated.
        well = window.project.wells[0]
        well.add_node('2025-01-01', 100)
        well.add_node('2025-07-15', 150, node_type='injector')
        well.add_node('2025-12-31', 200)
        window.refresh(); window.list.item(0).setSelected(True)
        window.preview()
        window.search.setText('生产井')
        window.node_date.setText('2025-08-01')
        window.start.setText('2024-01-01')  # Draft, unapplied project settings.
        window.bhp.setText('123.5')
        window.table.selectRow(1)
        window.node_sort_order.setCurrentIndex(1)
        window.table.selectRow(1)
        selected_rows = {i.row() for i in window.table.selectedIndexes()}
        before = asdict(window.project)
        dirty = window.dirty
        inc = window.text.toPlainText()
        output = render(window.project)
        window.language_select.setCurrentIndex(1)
        assert window.language == 'zh'
        assert window.tabs.tabText(0) == '动态编辑'
        assert window.table.horizontalHeaderItem(7).text() == '从此日起类型'
        assert window.frequency.currentText() == '每月'
        assert window.mode.currentText() == '预测'
        assert window.table.cellWidget(1, 7).currentData() == 'injector'
        assert window.table.item(1, 8).text() == '注水井'
        assert window.samples.item(0, 3).text() == '2025'
        assert window.list.item(0).text() == '生产井'
        assert window.table.item(0, 0).text() == '生产井'
        assert window.search.text() == '生产井'
        assert window.node_date.text() == '2025-08-01'
        assert window.start.text() == '2024-01-01'
        assert window.bhp.text() == '123.5'
        assert {i.row() for i in window.table.selectedIndexes()} == selected_rows
        assert asdict(window.project) == before and window.dirty == dirty
        assert window.text.toPlainText() == inc and render(window.project) == output
        window.language_select.setCurrentIndex(0)
        assert window.language == 'en'
        assert window.table.item(1, 8).text() == 'Injector'
        assert window.samples.item(0, 3).text() == '2025'
        assert window.table.horizontalHeaderItem(0).text() == 'Well'
        assert window.segment_scope.currentText() == 'Selected table rows'
        assert 'selected' in window.statusBar().currentMessage()
        assert asdict(window.project) == before and window.dirty == dirty
        # Language changes must not trigger frequency, mode, or type edits.
        window.frequency.setCurrentIndex(window.frequency.findData('custom'))
        assert window.interval.isEnabled() and not window.month_position.isEnabled()
        window.mode.setCurrentIndex(window.mode.findData('split'))
        assert window.split.isEnabled()
        window.split.setText('2025-08-01')
        assert window.settings().mode == 'split'
        assert window.settings().frequency == 'custom'
        window.table.cellWidget(1, 7).setCurrentIndex(0)
        assert well.type_at('2025-08-01') == 'producer'
        assert window.table.item(1, 8).text() == 'Producer'
        app.processEvents()
    finally:
        window.dirty = False; window.close()


def test_bilingual_dialogs_errors_and_reports():
    app = Q.QApplication.instance() or Q.QApplication([])
    window = Window()
    try:
        captured = []
        def dismiss():
            dialog = app.activeModalWidget()
            captured.append(dialog)
            assert dialog.windowTitle() == 'Operation failed'
            assert dialog.text() == 'Select wells first'
            assert dialog.button(Q.QMessageBox.Ok).text() == 'OK'
            dialog.accept()
        QTimer.singleShot(0, dismiss)
        window.guard(window.require)
        assert captured
        dialog = window.input_dialog('创建井', '井名')
        assert dialog.windowTitle() == 'Add well' and dialog.labelText() == 'Well'
        assert dialog.okButtonText() == 'OK' and dialog.cancelButtonText() == 'Cancel'
        window.set_language('zh')
        dialog = window.input_dialog('创建井', '井名')
        assert dialog.labelText() == '井名' and dialog.cancelButtonText() == '取消'
        window.set_language('en')
        assert window.t('第 2 行: 未知井 W1') == 'Line 2: Unknown well W1'
        assert window.t('W1: 节点超出项目日期范围') == 'W1: Node is outside the project date range'
        reports = []
        window.message = lambda icon, title, text, buttons=None: reports.append(text)
        window.report({'success': 2, 'skipped': 1, 'errors': ['第 3 行: 未知井 W2']})
        assert reports[-1] == 'Succeeded: 2; skipped: 1; issues: 1\nLine 3: Unknown well W2'
    finally:
        window.dirty = False; window.close()
