"""CLI uses argparse to keep the existing dependency set unchanged."""
import argparse
import csv
import json
from pathlib import Path
from .core import Project, ExportSettings, curve, from_metric, to_metric
from . import storage
from .operations import add_nodes, set_segments
from .eclipse import render
from .vol import render as render_vol


def parser():
    root = argparse.ArgumentParser(description='油藏生产动态与 ECLIPSE SCHEDULE 生成器')
    domains = root.add_subparsers(dest='domain', required=True)
    specs = {
        'project': {'new': ['path'], 'show': []},
        'well': {'add': ['name'], 'import': ['path'], 'list': [], 'delete': ['name'],
                 'rename': ['name', 'new_name'], 'type': ['name'], 'copy': ['name']},
        'node': {'add': ['date'], 'import': ['path'], 'export': ['path'],
                 'delete': ['name', 'id'], 'edit': ['name', 'id', 'date']},
        'curve': {'set': [], 'generate': []},
        'export': {'eclipse': ['path'], 'vol': ['path']},
    }
    for domain, commands in specs.items():
        sub = domains.add_parser(domain).add_subparsers(dest='command', required=True)
        for command, positional in commands.items():
            p = sub.add_parser(command)
            for name in positional:
                p.add_argument(name)
            p.add_argument('--project', required=not (domain == 'project' and command == 'new'))
            p.add_argument('--wells', nargs='+', help='不指定则选择全部井')
            p.add_argument('--selection', help='TXT 井名选择文件')
            if command in ('new', 'import') or domain == 'export':
                p.add_argument('--units', choices=['METRIC', 'FIELD'])
            if domain == 'project' and command == 'new':
                p.add_argument('--start', default='2025-01-01')
                p.add_argument('--end', default='2025-12-31')
            if domain == 'well' and command in ('add', 'import', 'type'):
                p.add_argument('--kind', choices=['producer', 'injector'], default='producer')
            if domain == 'well' and command == 'copy':
                p.add_argument('--yes', action='store_true', help='确认覆盖目标井配置')
            if domain == 'node' and command in ('add', 'edit'):
                p.add_argument('--rate', type=float, default=0)
                p.add_argument('--type', choices=['producer', 'injector', 'inherit'],
                               help='从节点日期起切换类型；inherit 表示继承前次设置')
            if domain == 'node' and command == 'add':
                p.add_argument('--minimum', type=float)
                p.add_argument('--maximum', type=float)
                p.add_argument('--seed', type=int)
            if domain == 'node' and command == 'import':
                p.add_argument('--conflict', choices=['skip', 'overwrite'], default='skip')
            if domain == 'curve' and command == 'set':
                p.add_argument('--method', choices=['linear', 'arps'])
                p.add_argument('--b', type=float)
                p.add_argument('--noise', type=float)
                p.add_argument('--seed', type=int)
            if domain == 'curve' and command == 'generate':
                p.add_argument('--output', required=True)
            if domain == 'export':
                p.add_argument('--frequency', choices=['daily', 'monthly', 'custom'])
                p.add_argument('--interval', type=int)
                p.add_argument('--month-end', action='store_true', default=None)
                p.add_argument('--no-keep-nodes', action='store_true')
                p.add_argument('--mode', choices=['history', 'prediction', 'split'])
                p.add_argument('--split-date')
                p.add_argument('--injection-bhp', type=float)
                p.add_argument('--injection-thp', type=float)
    return root


def execute(args):
    if args.domain == 'project' and args.command == 'new':
        if Path(args.path).exists():
            raise ValueError('项目已存在，拒绝覆盖')
        project = Project(name=Path(args.path).stem, units=args.units or 'METRIC',
                          start=args.start, end=args.end)
        project.export.units = project.units
        storage.save(project, args.path)
        return args.path
    project = storage.load(args.project)
    selection = args.wells or (storage.names(args.selection) if args.selection else None)
    wells = project.wells if selection is None else [project.well(n) for n in dict.fromkeys(selection)]
    result = '完成'
    changed = True
    d, c = args.domain, args.command
    if d == 'project':
        return json.dumps(storage.project_data(project), ensure_ascii=False, indent=2)
    if d == 'well':
        if c == 'add': result = project.add_well(args.name, args.kind)
        elif c == 'import': result = storage.import_wells(project, args.path, args.kind)
        elif c == 'list': return '\n'.join(f'{w.name}\t{w.kind}\t{len(w.nodes)}' for w in wells)
        elif c == 'delete': project.wells.remove(project.well(args.name))
        elif c == 'type':
            project.well(args.name).kind = args.kind
            project.well(args.name).sync_segments()
        elif c == 'rename':
            if any(w.name == args.new_name for w in project.wells): raise ValueError('井名已存在')
            project.well(args.name).name = args.new_name
        elif c == 'copy':
            if not args.yes: raise ValueError('复制将覆盖配置，请用 --yes 确认')
            source = project.well(args.name)
            for w in wells:
                if w is not source: w.copy_from(source)
    elif d == 'node':
        from .core import UNCHANGED
        node_type = UNCHANGED if getattr(args, 'type', None) is None else (None if args.type == 'inherit' else args.type)
        if c == 'add': result = add_nodes(project, wells, args.date, args.rate, args.minimum, args.maximum, args.seed, node_type)
        elif c == 'import': result = storage.import_nodes(project, args.path, args.conflict, args.units)
        elif c == 'export': storage.export_nodes(project, args.path); changed = False
        elif c == 'delete': project.well(args.name).delete_node(args.id)
        elif c == 'edit': project.well(args.name).edit_node(args.id, args.date, to_metric(args.rate, project.units), node_type)
    elif d == 'curve':
        if c == 'set':
            set_segments(wells, **{k: getattr(args, k) for k in ('method', 'b', 'noise', 'seed') if getattr(args, k) is not None})
        else:
            with open(args.output, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f); writer.writerow(['well', 'date', 'rate', 'type'])
                for w in wells:
                    writer.writerows((w.name, d.isoformat(), from_metric(q, project.units), w.type_at(d)) for d, q in curve(w).items())
            changed = False
    elif d == 'export':
        for k in ('frequency', 'interval', 'month_end', 'mode', 'split_date', 'units', 'injection_bhp', 'injection_thp'):
            if getattr(args, k) is not None: setattr(project.export, k, getattr(args, k))
        if args.no_keep_nodes: project.export.keep_nodes = False
        Path(args.path).write_text((render_vol if c == 'vol' else render)(project, wells), encoding='utf-8')
    if changed: storage.save(project, args.project)
    return result


def main():
    p = parser()
    try:
        result = execute(p.parse_args())
        print(json.dumps(result, ensure_ascii=False) if isinstance(result, dict) else result)
    except (ValueError, OSError, StopIteration, KeyError, TypeError) as e:
        p.exit(2, f'错误: {e or "找不到井或节点"}\n')


if __name__ == '__main__':
    main()
