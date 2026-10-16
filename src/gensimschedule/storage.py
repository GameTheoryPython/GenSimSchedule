import csv
import json
from dataclasses import asdict
from pathlib import Path
from .core import Project, Well, TimeNode, TimeSegment, ExportSettings, to_metric, from_metric, UNCHANGED


def project_data(project):
    data = asdict(project)
    for well in data['wells']:
        well['type'] = well.pop('kind')
    return data


def save(project, path):
    project.validate()
    target = Path(path)
    temporary = target.with_suffix(target.suffix + '.tmp')
    temporary.write_text(json.dumps({'version': 1, **project_data(project)}, ensure_ascii=False,
                                    indent=2), encoding='utf-8')
    temporary.replace(target)


def load(path):
    data = json.loads(Path(path).read_text(encoding='utf-8-sig'))
    if data.pop('version', 1) != 1:
        raise ValueError('不支持的项目版本')
    data['export'] = ExportSettings(**data.get('export', {}))
    wells = []
    for item in data.pop('wells', []):
        if 'kind' in item:
            raise ValueError(f'{item.get("name", "")}: 不支持 kind 字段，请使用 type')
        if 'type' not in item:
            raise ValueError(f'{item.get("name", "")}: 缺少 type 字段')
        item['kind'] = item.pop('type')
        item['nodes'] = [TimeNode(**n) for n in item.get('nodes', [])]
        item['segments'] = [TimeSegment(**s) for s in item.get('segments', [])]
        w = Well(**item)
        w.sync_segments()
        wells.append(w)
    project = Project(wells=wells, **data)
    project.validate()
    return project


def names(path):
    raw = Path(path).read_bytes()
    try:
        text = raw.decode('utf-8-sig')
    except UnicodeDecodeError:
        text = raw.decode('gb18030')
    return [s.strip() for s in text.splitlines() if s.strip()]


def import_wells(project, path, kind='producer'):
    items = names(path)
    for name in items:
        Well(name, kind).validate()
    count = sum(project.add_well(n, kind) for n in items)
    return {'success': count, 'skipped': len(items) - count, 'errors': []}


def import_nodes(project, path, conflict='skip', units=None):
    if conflict not in ('skip', 'overwrite'):
        raise ValueError('冲突策略必须为 skip 或 overwrite')
    report = {'success': 0, 'skipped': 0, 'errors': []}
    pending = []
    with open(path, encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        if not {'well', 'date', 'rate'} <= set(reader.fieldnames or []):
            raise ValueError('CSV 必须含 well,date,rate 列')
        for line, row in enumerate(reader, 2):
            try:
                w = project.well(row['well'])
                has_type = 'type' in (reader.fieldnames or [])
                node_type = (row.get('type') or '').strip() or None
                n = TimeNode(row['date'], to_metric(row['rate'], units or project.units), type=node_type)
                pending.append((w, n, has_type))
            except StopIteration:
                report['skipped'] += 1
                report['errors'].append(f'第 {line} 行: 未知井 {row["well"]}')
            except (ValueError, TypeError) as e:
                report['errors'].append(f'第 {line} 行: {e}')
    for w, n, has_type in pending:
        key = 'success' if w.add_node(n.date, n.rate, conflict, n.type if has_type else UNCHANGED) else 'skipped'
        report[key] += 1
    return report


def export_nodes(project, path):
    with open(path, 'w', encoding='utf-8', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['well', 'date', 'rate', 'type'])
        for w in project.wells:
            for n in w.nodes:
                writer.writerow([w.name, n.date, from_metric(n.rate, project.units), n.type or ''])
