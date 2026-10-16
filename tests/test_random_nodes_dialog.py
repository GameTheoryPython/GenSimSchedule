import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'

from dataclasses import asdict
import pytest
from PySide6 import QtWidgets as Q
from gensimschedule.gui import Window, RandomNodeDialog


def test_random_dialog_validation_retains_inputs():
    app = Q.QApplication.instance() or Q.QApplication([])
    window = Window()
    try:
        before = asdict(window.project)
        dialog = RandomNodeDialog(window, 2)
        assert dialog.buttons.button(Q.QDialogButtonBox.Apply).text() == 'Apply'
        for field, value in [('when', ''), ('minimum', ''), ('maximum', ''),
                             ('minimum', 'nan'), ('minimum', '-1'), ('maximum', 'not a number'),
                             ('seed', '1.5'), ('when', '2025-02-30'), ('when', '2024-01-01')]:
            dialog.when.setText('2025-02-01 12:30:00')
            dialog.minimum.setText('10'); dialog.maximum.setText('20'); dialog.seed.clear()
            getattr(dialog, field).setText(value)
            dialog.accept()
            assert dialog.result() != Q.QDialog.Accepted
            assert dialog.error.text()
            assert getattr(dialog, field).text() == value
            assert asdict(window.project) == before
        dialog.when.setText('2025-02-01 12:30:00'); dialog.seed.clear()
        dialog.minimum.setText('30'); dialog.maximum.setText('20')
        dialog.accept()
        assert 'Minimum exceeds maximum' in dialog.error.text()
        dialog.minimum.setText('10'); dialog.seed.setText('42')
        dialog.accept()
        assert dialog.result() == Q.QDialog.Accepted
        assert dialog.payload == dict(when='2025-02-01 12:30:00', minimum=10, maximum=20, seed=42, node_type=None)
        window.set_language('zh')
        chinese = RandomNodeDialog(window, 2)
        chinese.minimum.clear(); chinese.accept()
        assert chinese.error.text() == '请填写节点时间、最小流量和最大流量'
        app.processEvents()
    finally:
        window.dirty = False; window.close()


def test_random_dialog_apply_and_cancel(monkeypatch, tmp_path):
    app = Q.QApplication.instance() or Q.QApplication([])
    window = Window(); reports = []; window.report = reports.append
    try:
        for name in ('A', 'B', 'UNSELECTED'): window.project.add_well(name)
        window.refresh(); window.list.item(0).setSelected(True); window.list.item(1).setSelected(True)
        def apply(dialog):
            dialog.when.setText('2025-02-01 12:30:00')
            dialog.minimum.setText('10'); dialog.maximum.setText('20'); dialog.seed.setText('42')
            dialog.node_type.setCurrentIndex(dialog.node_type.findData('injector'))
            dialog.accept()
            return dialog.result()
        monkeypatch.setattr(RandomNodeDialog, 'exec', apply)
        window.random_node()
        assert window.dirty
        assert reports[-1]['success'] == 2
        assert not window.project.well('UNSELECTED').nodes
        for name in ('A', 'B'):
            n = window.project.well(name).nodes[0]
            assert n.date == '2025-02-01 12:30:00' and 10 <= n.rate <= 20 and n.type == 'injector'
            assert n.seed == 42
        from gensimschedule import storage
        path = tmp_path / 'seeds.json'
        storage.save(window.project, path)
        restored = storage.load(path)
        assert [w.nodes[0].seed for w in restored.wells[:2]] == [42, 42]
        rates = [w.nodes[0].rate for w in window.project.wells[:2]]
        assert rates[0] != rates[1]
        before = asdict(window.project)
        window.random_node()
        assert asdict(window.project) == before
        assert reports[-1]['skipped'] == 2
        monkeypatch.setattr(RandomNodeDialog, 'exec', lambda dialog: Q.QDialog.Rejected)
        window.dirty = False; window.random_node()
        assert asdict(window.project) == before and not window.dirty
        app.processEvents()
    finally:
        window.dirty = False; window.close()


def test_node_seed_is_distinct_from_noise_seed(tmp_path):
    from gensimschedule.core import Project
    from gensimschedule.operations import add_nodes
    from gensimschedule import storage
    import json
    p = Project(); p.add_well('W1')
    add_nodes(p, p.wells, '2025-01-01', minimum=10, maximum=20, seed=42)
    add_nodes(p, p.wells, '2025-02-01', minimum=10, maximum=20, seed=43)
    w = p.wells[0]
    assert w.segments[0].seed is None
    w.set_segments(noise=.05, seed=99)
    path = tmp_path / 'seeds.json'; storage.save(p, path)
    data = json.loads(path.read_text())['wells'][0]
    assert [node['seed'] for node in data['nodes']] == [42, 43]
    assert data['segments'][0]['seed'] == 99
    assert asdict(storage.load(path)) == asdict(p)
    # Repeating an existing timestamp skips it and preserves its original provenance.
    add_nodes(p, p.wells, '2025-01-01', minimum=100, maximum=200, seed=7)
    assert w.nodes[0].seed == 42
    n = w.nodes[0]
    w.edit_node(n.id, n.date, n.rate)
    assert w.nodes[0].seed == 42
    w.edit_node(n.id, n.date, 500)
    assert w.nodes[0].seed is None
    assert w.segments[0].seed == 99
