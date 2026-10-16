"""Producer/injector changes are dated controls, not a rename of the entire well."""
import csv
from dataclasses import asdict, replace
from datetime import datetime
import os

os.environ['QT_QPA_PLATFORM'] = 'offscreen'

import pytest
from gensimschedule.core import Project, curve, sample
from gensimschedule import storage
from gensimschedule.eclipse import render
from gensimschedule.cli import execute, parser


def conversion_project():
    p = Project(start='2025-01-01', end='2025-12-31')
    p.add_well('W1')
    w = p.wells[0]
    w.add_node('2025-01-01', 100)
    w.add_node('2025-06-20', 20)
    w.add_node('2025-07-15', 150, node_type='injector')
    w.add_node('2025-09-30', 200)
    w.add_node('2025-10-15', 40, node_type='producer')
    w.add_node('2025-12-31', 30)
    return p, w


def test_conversion_curves_do_not_interpolate_between_phases():
    p, w = conversion_project()
    assert len(w.segments) == 3
    assert w.segment_index(w.nodes[1].id) is None
    assert w.segment_index(w.nodes[3].id) is None
    values = curve(w)
    assert values[datetime(2025, 7, 14)] == 20
    assert values[datetime(2025, 7, 15)] == 150
    assert values[datetime(2025, 10, 14)] == 200
    assert values[datetime(2025, 10, 15)] == 40
    assert w.type_at('2025-07-14') == 'producer'
    assert w.type_at('2025-07-15') == 'injector'
    assert w.type_at('2025-10-15') == 'producer'
    w.set_segments(method='arps', b=.7, noise=.05, seed=42)
    values = curve(w)
    assert values[datetime(2025, 7, 14)] == 20
    assert values[datetime(2025, 7, 15)] == 150
    assert curve(w) == values


@pytest.mark.parametrize('frequency', ['monthly', 'custom', 'daily'])
def test_conversion_dates_forced_and_exported_once(frequency):
    p, w = conversion_project()
    p.export = replace(p.export, frequency=frequency, interval=60, keep_nodes=False)
    samples = sample(p, w)
    assert datetime(2025, 7, 15) in samples and datetime(2025, 10, 15) in samples
    text = render(p)
    injection_block = text.split("15 'JUL' 2025 /\n/", 1)[1].split('DATES', 1)[0]
    assert "'W1' WATER OPEN RATE 150 /" in injection_block
    assert 'WCONPROD' not in injection_block
    production_block = text.split("15 'OCT' 2025 /\n/", 1)[1].split('DATES', 1)[0]
    assert "'W1' OPEN ORAT 40 /" in production_block
    assert 'WCONINJE' not in production_block
    assert text.count("15 'JUL' 2025") == 1


def test_conversion_history_prediction_are_independent():
    p, w = conversion_project()
    p.export = replace(p.export, mode='split', split_date='2025-08-01', keep_nodes=False,
                       injection_bhp=200, injection_thp=10)
    text = render(p)
    assert 'WCONHIST' in text and 'WCONINJH' in text
    assert 'WCONPROD' in text and 'WCONINJE' in text
    history_switch = text.split("15 'JUL' 2025 /\n/", 1)[1].split('DATES', 1)[0]
    assert "'W1' WATER OPEN 150 200 10 /" in history_switch
    p.export.injection_bhp = None
    with pytest.raises(ValueError, match='BHP'): render(p)


def test_conversion_json_csv_roundtrip(tmp_path):
    p, w = conversion_project()
    path = tmp_path / 'config.json'
    storage.save(p, path)
    assert asdict(storage.load(path)) == asdict(p)
    nodes = tmp_path / 'nodes.csv'
    storage.export_nodes(p, nodes)
    q = Project(start=p.start, end=p.end); q.add_well(w.name)
    assert storage.import_nodes(q, nodes)['success'] == 6
    assert [n.type for n in q.wells[0].nodes] == [n.type for n in w.nodes]
    assert curve(q.wells[0]) == curve(w)
    # Three-column updates preserve previously defined conversion events.
    nodes.write_text('well,date,rate\nW1,2025-07-15,170\n', encoding='utf-8')
    storage.import_nodes(q, nodes, 'overwrite')
    assert q.wells[0].nodes[2].type == 'injector'
    assert q.wells[0].nodes[2].rate == 170
    # An explicit blank type removes an event; unknown types give a line error.
    nodes.write_text('well,date,rate,type\nW1,2025-07-15,170,\nW1,2025-11-01,20,unknown\n', encoding='utf-8')
    report = storage.import_nodes(q, nodes, 'overwrite')
    assert report['success'] == 1 and len(report['errors']) == 1
    assert q.wells[0].type_at('2025-07-15') == 'producer'


def test_edit_conversion_and_copy(tmp_path):
    p, w = conversion_project()
    node = w.nodes[2]
    w.edit_node(node.id, '2025-07-20', 160)
    assert w.nodes[2].type == 'injector'
    assert w.type_at('2025-07-19') == 'producer'
    assert w.type_at('2025-07-20') == 'injector'
    p.add_well('COPY'); target = p.wells[1]; target.copy_from(w)
    assert [n.type for n in target.nodes] == [n.type for n in w.nodes]
    assert curve(target) == curve(w)
    assert {n.id for n in target.nodes}.isdisjoint(n.id for n in w.nodes)
    w.delete_node(node.id)
    assert w.type_at('2025-08-01') == 'producer'
    assert len(w.segments) == 4


@pytest.mark.parametrize('source_type,target_type', [('injector', 'producer'), ('producer', 'injector')])
def test_copy_default_type_and_effective_type(source_type, target_type):
    p = Project(); p.add_well('SOURCE', source_type); p.add_well('TARGET', target_type)
    source, target = p.wells
    source.add_node('2025-01-01', 100)
    source.add_node('2025-02-01', 80)
    source.add_node('2025-03-01 12:30:00', 150, node_type=target_type)
    source.add_node('2025-04-01', 200)
    source.set_segments(method='arps', b=.8, noise=.05, seed=42)
    target.add_node('2025-01-01', 999)
    target.copy_from(source)
    assert target.name == 'TARGET' and target.kind == source_type
    for when in ('2025-01-01', '2025-02-15', '2025-03-01 12:29:59', '2025-03-01 12:30:00', '2025-04-01'):
        assert target.type_at(when) == source.type_at(when)
    assert curve(target) == curve(source)
    assert {n.id for n in target.nodes}.isdisjoint(n.id for n in source.nodes)
    assert all(s.b == .8 and s.seed == 42 for s in target.segments)


def test_conversion_cli(tmp_path):
    path = tmp_path / 'project.json'
    p, w = conversion_project(); storage.save(p, path)
    execute(parser().parse_args(['node', 'edit', 'W1', w.nodes[2].id, '2025-07-15',
                                '--rate', '150', '--type', 'inherit', '--project', str(path)]))
    assert storage.load(path).wells[0].type_at('2025-07-15') == 'producer'
    execute(parser().parse_args(['node', 'add', '2025-08-01', '--rate', '180',
                                '--type', 'injector', '--project', str(path)]))
    assert storage.load(path).wells[0].type_at('2025-08-01') == 'injector'


def test_conversion_gui_after_sorting():
    from PySide6.QtWidgets import QApplication, QTableWidgetSelectionRange
    from gensimschedule.gui import Window
    app = QApplication.instance() or QApplication([])
    window = Window(language='zh'); window.report = lambda report: None
    try:
        window.project, w = conversion_project()
        window.refresh(); window.list.item(0).setSelected(True)
        assert window.table.cellWidget(1, 3) is None
        assert window.table.cellWidget(2, 7).currentData() == 'injector'
        assert window.table.item(3, 8).text() == '注水井'
        # Segment indexes no longer equal node indexes after a conversion.
        window.table.cellWidget(2, 3).setCurrentText('arps')
        assert w.segments[1].method == 'arps'
        window.table.item(2, 4).setText('0.8')
        assert w.segments[1].b == .8
        window.node_sort_order.setCurrentIndex(1)
        window.node_sort_secondary_order.setCurrentIndex(1)
        row = window.node_rows.index((w.name, w.nodes[2].id))
        window.table.clearSelection()
        window.table.setRangeSelected(QTableWidgetSelectionRange(row, 0, row, 8), True)
        window.fields[2].setChecked(True); window.noise.setValue(.1); window.batch_segments()
        assert w.segments[1].noise == .1 and w.segments[0].noise == 0
        # Changing the event to inherit merges the phases and rebuilds controls.
        row = window.node_rows.index((w.name, w.nodes[2].id))
        window.table.cellWidget(row, 7).setCurrentIndex(0)
        assert w.type_at('2025-07-15') == 'producer'
        assert len(w.segments) == 5
        # Plot lines never connect production points to injection points.
        window.edit_node_type(w.name, w.nodes[2].id, 'injector')
        assert len(window.figure.axes[0].lines) == 3
        window.preview()
        assert window.samples.columnCount() == 11
        assert 'WCONINJE' in window.text.toPlainText()
        app.processEvents()
    finally:
        window.dirty = False; window.close()
