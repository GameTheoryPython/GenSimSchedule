from dataclasses import asdict, replace
from datetime import datetime
import math
import json
import pytest
from gensimschedule.core import Project, Well, TimeNode, curve, sample, to_metric, from_metric
from gensimschedule import storage
from gensimschedule.eclipse import render
from gensimschedule.operations import add_nodes, set_segments


def fixture():
    p = Project(start='2025-01-01', end='2025-04-30')
    p.add_well('P1'); w = p.wells[0]
    w.add_node('2025-01-01', 100); w.add_node('2025-04-01', 20)
    return p, w


def test_split_merge_and_stable_ids():
    p, w = fixture(); w.set_segments(method='arps', b=.7, noise=.05, seed=42)
    old_ids = [n.id for n in w.nodes]
    w.add_node('2025-02-01', 50)
    assert len(w.segments) == 2
    assert all(s.method == 'arps' and s.b == .7 for s in w.segments)
    w.segments[1].b = .2
    w.delete_node(w.nodes[1].id)
    assert w.segments[0].b == .7
    assert [n.id for n in w.nodes] == old_ids
    w.edit_node(old_ids[0], '2025-01-01', 120)
    assert w.segments[0].b == .7


@pytest.mark.parametrize('b', [0, .5, 1])
def test_arps_endpoints_noise(b):
    p, w = fixture(); w.set_segments(method='arps', b=b)
    values = curve(w); mid = values[datetime(2025, 2, 15)]
    assert 20 < mid < 100
    assert list(values.values())[0] == 100 and list(values.values())[-1] == 20
    assert all(x >= y for x, y in zip(values.values(), list(values.values())[1:]))
    w.set_segments(noise=2, seed=9)
    assert curve(w) == curve(w)
    assert min(curve(w).values()) >= 0
    assert curve(w)[datetime(2025, 1, 1)] == 100
    assert curve(w)[datetime(2025, 4, 1)] == 20


def test_fallback_and_single():
    w = Well('P'); assert curve(w) == {}
    w.add_node('2025-01-01', 0); assert len(curve(w)) == 1
    w.add_node('2025-01-11', 100); w.set_segments(method='arps')
    assert curve(w)[datetime(2025, 1, 6)] == 50


def test_sampling():
    p, w = fixture(); w.add_node('2025-02-15', 60)
    assert datetime(2025, 2, 15) in sample(p, w)
    s = replace(p.export, keep_nodes=False)
    assert list(sample(p, w, s)) == [datetime(2025, i, 1) for i in range(1, 5)]
    s = replace(s, month_end=True)
    assert list(sample(p, w, s)) == [datetime(2025, 1, 31), datetime(2025, 2, 28), datetime(2025, 3, 31)]
    s = replace(s, frequency='custom', interval=10)
    assert list(sample(p, w, s))[1] == datetime(2025, 1, 11)
    s = replace(s, frequency='daily'); assert len(sample(p, w, s)) == 91


def test_roundtrip_copy_units(tmp_path):
    p, w = fixture(); w.set_segments(method='arps', seed=1)
    path = tmp_path / 'p.json'; storage.save(p, path)
    assert asdict(storage.load(path)) == asdict(p)
    target = Well('P2'); target.copy_from(w)
    assert {n.id for n in target.nodes}.isdisjoint(n.id for n in w.nodes)
    assert curve(target) == curve(w)
    assert from_metric(to_metric(123, 'FIELD'), 'FIELD') == pytest.approx(123)


def test_json_well_type_only(tmp_path):
    p, w = fixture()
    p.add_well('I1', 'injector')
    path = tmp_path / 'types.json'
    storage.save(p, path)
    data = json.loads(path.read_text(encoding='utf-8'))
    assert [item['type'] for item in data['wells']] == ['producer', 'injector']
    assert all('kind' not in item for item in data['wells'])
    assert asdict(storage.load(path)) == asdict(p)
    for item in data['wells']:
        item['kind'] = item.pop('type')
    path.write_text(json.dumps(data), encoding='utf-8')
    with pytest.raises(ValueError, match='不支持 kind'): storage.load(path)
    data = {'version': 1, **storage.project_data(p)}
    del data['wells'][0]['type']
    path.write_text(json.dumps(data), encoding='utf-8')
    with pytest.raises(ValueError, match='缺少 type'): storage.load(path)
    data = {'version': 1, **storage.project_data(p)}
    data['wells'][0]['kind'] = 'producer'
    path.write_text(json.dumps(data), encoding='utf-8')
    with pytest.raises(ValueError, match='不支持 kind'): storage.load(path)


def test_batch_import_100(tmp_path):
    p = Project(); path = tmp_path / 'wells.txt'
    path.write_text('\n'.join(f'P{i}' for i in range(100)), encoding='utf-8')
    assert storage.import_wells(p, path)['success'] == 100
    assert storage.import_wells(p, path)['skipped'] == 100
    add_nodes(p, p.wells, '2025-01-01', minimum=10, maximum=20, seed=1)
    add_nodes(p, p.wells, '2025-02-01', 5)
    assert all(len(w.segments) == 1 for w in p.wells)
    set_segments(p.wells, noise=.05)
    assert all(w.segments[0].noise == .05 for w in p.wells)
    path = tmp_path / 'n.csv'
    path.write_text('well,date,rate\nP0,2025-01-01,7\nP1,2025-03-05,8\nUNKNOWN,2025-01-01,1\nP2,bad,-1\n', encoding='utf-8')
    report = storage.import_nodes(p, path, 'overwrite')
    assert report['success'] == 2 and len(report['errors']) == 2
    assert p.well('P0').nodes[0].rate == 7


def test_csv_excel_date_format(tmp_path):
    p = Project(start='2000-01-01', end='2000-12-31')
    p.add_well('P1')
    path = tmp_path / 'dates.csv'
    path.write_text('well,date,rate\nP1,2000/1/1,100\nP1, 2000-2-1 ,80\nP1,2000/2/30,50\n', encoding='utf-8')
    report = storage.import_nodes(p, path)
    assert report['success'] == 2
    assert len(report['errors']) == 1 and '第 4 行' in report['errors'][0]
    assert [n.date for n in p.wells[0].nodes] == ['2000-01-01', '2000-02-01']
    assert len(p.wells[0].segments) == 1


def test_export_fields_and_split():
    p, w = fixture(); p.add_well('I1', 'injector'); p.well('I1').copy_from(w)
    p.well('I1').kind = 'injector'
    p.export = replace(p.export, mode='split', split_date='2025-02-15', injection_bhp=200, injection_thp=10)
    text = render(p)
    assert "'P1' OPEN ORAT 100 /" in text
    assert "'I1' WATER OPEN 100 200 10 /" in text
    assert 'WCONHIST' in text and 'WCONINJH' in text
    assert 'WCONPROD' in text and 'WCONINJE' in text
    assert "15 'FEB' 2025" in text
    p.export.injection_bhp = None
    with pytest.raises(ValueError, match='BHP'): render(p)


def test_validation_atomic():
    p, w = fixture(); before = asdict(w)
    with pytest.raises(ValueError): w.edit_node(w.nodes[0].id, w.nodes[1].date, 2)
    assert asdict(w) == before
    with pytest.raises(ValueError): add_nodes(p, [w], '2025-03-01', minimum=20, maximum=10)
    assert asdict(w) == before
    with pytest.raises(ValueError): w.set_segments(b=2)
    assert asdict(w) == before
    with pytest.raises(ValueError): TimeNode('2025-01-01', float('nan'))
    p.start = '2025-02-01'
    with pytest.raises(ValueError, match='范围'): render(p)
