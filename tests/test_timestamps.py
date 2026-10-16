import csv
from dataclasses import asdict, replace
from datetime import datetime
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'

import pytest
from gensimschedule.core import TimeNode, Project, Well, day, curve, sample
from gensimschedule import storage
from gensimschedule.eclipse import render
from gensimschedule.cli import execute, parser


@pytest.mark.parametrize('text', ['2025-01-01 08:30:05', '2025/1/1 8:30:05', '2025-01-01T08:30:05'])
def test_datetime_input_formats(text):
    assert TimeNode(text, 10).date == '2025-01-01 08:30:05'
    assert TimeNode('2025-01-01 00:00:00', 10).date == '2025-01-01'
    assert TimeNode('2025/1/1 8:30', 10).date == '2025-01-01 08:30:00'


def test_same_day_nodes_unique_seconds_and_arps():
    w = Well('W1')
    w.add_node('2025-01-01 06:00', 100)
    w.add_node('2025-01-01 18:00', 25)
    assert len(w.segments) == 1
    values = curve(w, at=['2025-01-01 12:00'])
    assert values[datetime(2025, 1, 1, 12)] == 62.5
    w.set_segments(method='arps', b=0)
    assert curve(w, at=['2025-01-01 12:00'])[datetime(2025, 1, 1, 12)] == pytest.approx(50)
    assert len(curve(w)) > 2  # A short Arps segment must be visibly curved.
    with pytest.raises(ValueError): w.add_node('2025/1/1 6:00:00', 20)
    w.add_node('2025-01-01 18:00:01', 20)
    assert len(w.segments) == 2
    assert curve(w)[datetime(2025, 1, 1, 18, 0, 1)] == 20
    with pytest.raises(ValueError): TimeNode('2025-01-01 25:00:00', 10)
    with pytest.raises(ValueError): TimeNode('2025-01-01T06:00:00+04:00', 10)


def test_sampling_midnight_and_exact_split_with_noise():
    p = Project(start='2025-01-01', end='2025-01-03')
    p.add_well('W1'); w = p.wells[0]
    w.add_node('2025-01-01 06:00', 100); w.add_node('2025-01-03 18:00', 40)
    p.export = replace(p.export, frequency='daily', keep_nodes=False)
    samples = sample(p, w)
    assert list(samples) == [datetime(2025, 1, 2), datetime(2025, 1, 3)]
    assert list(samples.values()) == pytest.approx([82, 58])
    p.export.mode = 'split'; p.export.split_date = '2025-01-02 12:00:00'
    assert sample(p, w)[datetime(2025, 1, 2, 12)] == 70
    w.set_segments(noise=.1, seed=42)
    before = sample(p, w)
    p.export.keep_nodes = True
    after = sample(p, w)
    assert all(after[t] == q for t, q in before.items())
    assert after[datetime(2025, 1, 1, 6)] == 100
    assert after[datetime(2025, 1, 3, 18)] == 40
    p.end = '2025-01-03 17:59:59'
    with pytest.raises(ValueError, match='范围'): sample(p, w)


def test_intraday_conversion_and_eclipse_clock():
    p = Project(start='2025-01-01', end='2025-01-01')
    p.add_well('W1'); w = p.wells[0]
    w.add_node('2025-01-01', 100)
    w.add_node('2025-01-01 12:30:05', 150, node_type='injector')
    w.add_node('2025-01-01 18:00:00', 200)
    assert w.type_at('2025-01-01 12:30:04') == 'producer'
    assert w.type_at('2025-01-01 12:30:05') == 'injector'
    assert curve(w, at=['2025-01-01 12:30:04'])[datetime(2025, 1, 1, 12, 30, 4)] == 100
    p.export = replace(p.export, frequency='daily', keep_nodes=False)
    assert datetime(2025, 1, 1, 12, 30, 5) in sample(p, w)
    text = render(p)
    assert "1 'JAN' 2025 '12:30:05' /" in text
    switch = text.split("'12:30:05' /\n/", 1)[1].split('DATES', 1)[0]
    assert 'WCONINJE' in switch and 'WCONPROD' not in switch
    # History/prediction can switch at a separate time on the same day.
    p.export = replace(p.export, mode='split', split_date='2025-01-01 06:00:00', keep_nodes=True)
    text = render(p)
    assert 'WCONHIST' in text and 'WCONPROD' in text and 'WCONINJE' in text
    assert text.index("1 'JAN' 2025 /") < text.index("'06:00:00'") < text.index("'12:30:05'") < text.index("'18:00:00'")


def test_csv_json_and_cli_preserve_time(tmp_path):
    p = Project(); p.add_well('W1')
    csv_path = tmp_path / 'nodes.csv'
    csv_path.write_text('well,date,rate\nW1,2025/1/1 08:30:05,100\nW1,2025-01-01T20:30:05,50\n', encoding='utf-8')
    assert storage.import_nodes(p, csv_path)['success'] == 2
    storage.export_nodes(p, csv_path)
    with csv_path.open(encoding='utf-8') as f: rows = list(csv.DictReader(f))
    assert rows[0]['date'] == '2025-01-01 08:30:05'
    path = tmp_path / 'p.json'; storage.save(p, path)
    assert asdict(storage.load(path)) == asdict(p)
    execute(parser().parse_args(['node', 'add', '2025-01-01 22:00:05', '--rate', '40', '--project', str(path)]))
    assert storage.load(path).wells[0].nodes[-1].date == '2025-01-01 22:00:05'


def test_gui_intraday_nodes_and_axis_limits():
    from PySide6.QtWidgets import QApplication
    from gensimschedule.gui import Window
    app = QApplication.instance() or QApplication([])
    window = Window(); window.report = lambda report: None
    try:
        window.project.add_well('W1'); window.refresh(); window.list.item(0).setSelected(True)
        window.node_date.setText('2025-01-01 08:30:05'); window.node_rate.setValue(100); window.add_node()
        window.node_date.setText('2025-01-01 20:30:05'); window.node_rate.setValue(50); window.add_node()
        assert window.table.rowCount() == 2
        assert window.table.item(0, 1).text() == '2025-01-01 08:30:05'
        window.table.item(1, 1).setText('2025-01-01 21:30:05')
        assert window.project.wells[0].nodes[-1].date == '2025-01-01 21:30:05'
        window.plot_start.setText('2025-01-01 08:00:00'); window.plot_end.setText('2025-01-01 23:00:00')
        window.apply_plot_limits(); window.preview()
        assert "'08:30:05'" in window.text.toPlainText()
        window.set_language('zh')
        assert window.table.horizontalHeaderItem(1).text() == '日期时间'
        assert window.table.item(0, 1).text() == '2025-01-01 08:30:05'
        app.processEvents()
    finally:
        window.dirty = False; window.close()
