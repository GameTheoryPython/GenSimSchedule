from dataclasses import replace
from datetime import datetime
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'

import pytest
from gensimschedule.core import Project, to_metric
from gensimschedule.vol import render, sampled_rows
from gensimschedule import storage
from gensimschedule.cli import parser, execute


def example_project():
    p = Project(units='FIELD', start='1970-01-01', end='1970-03-01')
    p.export = replace(p.export, units='FIELD')
    for name, rates in [('P2', [544.012, 985.237, 1252.83]), ('P3', [378.309, 667.569, 857.871])]:
        p.add_well(name)
        for month, rate in enumerate(rates, 1):
            p.well(name).add_node(f'1970-0{month}-01', to_metric(rate, 'FIELD'))
    return p


def test_vol_sample_layout_and_selection():
    p = example_project()
    text = render(p)
    assert text.startswith('*FIELD\n*DAILY\n*IGNORE_MISSING\n*HRS_IN_DAYS\n*DAY *MONTH *YEAR *OIL *WATER *GAS *WINJ *GINJ *DAYS\n')
    assert '*NAME P2\n01 01 1970 544.012 0 0 0 0 24\n' in text
    assert '*NAME P3\n01 01 1970 378.309 0 0 0 0 24\n' in text
    assert '01 03 1970 1252.83 0 0 0 0 24' in text
    selected = render(p, [p.well('P3')])
    assert '*NAME P2' not in selected and '*NAME P3' in selected
    metric = render(p, settings=replace(p.export, units='METRIC'))
    assert metric.startswith('*METRIC\n')
    rows = sampled_rows(p)
    assert rows[0].oil == pytest.approx(544.012)
    assert rows[0].water == rows[0].gas == rows[0].winj == rows[0].ginj == 0


def test_vol_conversion_and_time_guard():
    p = example_project(); w = p.well('P2')
    w.edit_node(w.nodes[1].id, '1970-02-01', to_metric(150, 'FIELD'), node_type='injector')
    rows = sampled_rows(p, [w])
    assert rows[0].oil > 0 and rows[0].winj == 0
    assert rows[1].oil == 0 and rows[1].winj == pytest.approx(150)
    assert rows[1].days == 24
    w.edit_node(w.nodes[1].id, '1970-02-01 12:30:00', w.nodes[1].rate)
    p.export.keep_nodes = False
    # Conversion moments must not be lost even if node retention is disabled.
    with pytest.raises(ValueError, match='时分秒'): render(p, [w])


def test_gui_vol_table_matches_export_and_cli(tmp_path):
    from PySide6.QtWidgets import QApplication, QAbstractItemView
    from gensimschedule.gui import Window
    app = QApplication.instance() or QApplication([])
    window = Window()
    try:
        window.project = example_project(); window.refresh(); window.list.item(0).setSelected(True)
        window.preview_format.setCurrentIndex(window.preview_format.findData('vol'))
        window.preview()
        assert window.samples.columnCount() == 11
        assert [window.samples.horizontalHeaderItem(c).text() for c in range(11)] == [
            'NAME', 'DAY', 'MONTH', 'YEAR', 'OIL', 'WATER', 'GAS', 'WINJ', 'GINJ', 'DAYS', 'TIME']
        assert window.samples.rowCount() == 3
        expected = ['P2', '01', '01', '1970', '544.012', '0', '0', '0', '0', '24', '00:00:00']
        assert [window.samples.item(0, c).text() for c in range(11)] == expected
        assert window.samples.editTriggers() == QAbstractItemView.NoEditTriggers
        text = window.text.toPlainText()
        assert ' '.join(expected[1:10]) in text
        window.set_language('zh')
        assert [window.samples.item(0, c).text() for c in range(11)] == expected
        window.choose = lambda *args, **kwargs: str(tmp_path / 'selected')
        window.export_vol()
        target = tmp_path / 'selected.VOL'
        assert target.read_text() == window.text.toPlainText()
        assert '*NAME P3' not in target.read_text()
        path = tmp_path / 'project.json'; storage.save(window.project, path)
        output = tmp_path / 'cli.VOL'
        execute(parser().parse_args(['export', 'vol', str(output), '--project', str(path), '--wells', 'P2']))
        assert output.read_text() == target.read_text()
        app.processEvents()
    finally:
        window.dirty = False; window.close()
