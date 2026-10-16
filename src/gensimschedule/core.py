from dataclasses import dataclass, field, asdict, replace
from datetime import date, datetime, time, timedelta
import math
import random
import re
from bisect import bisect_right
from uuid import uuid4

BARREL = 0.158987294928
UNCHANGED = object()


def validate_type(value, optional=False):
    if optional and value is None:
        return
    if value not in ('producer', 'injector'):
        raise ValueError('井类型必须为 producer 或 injector')


def day(value):
    """Parse a model-local date/time at second precision (no timezone conversion)."""
    if isinstance(value, datetime):
        result = value
    elif isinstance(value, date):
        result = datetime.combine(value, time())
    elif isinstance(value, str):
        match = re.fullmatch(r'(\d{4})[-/](\d{1,2})[-/](\d{1,2})(?:[ T](\d{1,2}):(\d{2})(?::(\d{2}))?)?', value.strip())
        if not match:
            raise ValueError('日期时间格式应为 YYYY-MM-DD HH:MM:SS')
        result = datetime(*(int(part or 0) for part in match.groups()))
    else:
        raise ValueError('日期时间格式应为 YYYY-MM-DD HH:MM:SS')
    if result.tzinfo is not None or result.microsecond:
        raise ValueError('日期时间仅支持无时区的整秒精度')
    return result


def format_time(value):
    value = day(value)
    return value.date().isoformat() if value.time() == time() else value.isoformat(sep=' ', timespec='seconds')


def range_end(value):
    result = day(value)
    # A project end entered as just a date includes that whole calendar day.
    if isinstance(value, date) and not isinstance(value, datetime):
        return result.replace(hour=23, minute=59, second=59)
    if isinstance(value, str):
        if re.fullmatch(r'\d{4}[-/]\d{1,2}[-/]\d{1,2}', value.strip()):
            return result.replace(hour=23, minute=59, second=59)
    return result


def rate(value):
    value = float(value)
    if not math.isfinite(value) or value < 0:
        raise ValueError('流量必须为有限非负数')
    return value


def unit(value):
    if value not in ('METRIC', 'FIELD'):
        raise ValueError('单位制必须为 METRIC 或 FIELD')
    return value


def to_metric(value, units='METRIC'):
    return rate(value) * (BARREL if unit(units) == 'FIELD' else 1)


def from_metric(value, units='METRIC'):
    return value / (BARREL if unit(units) == 'FIELD' else 1)


@dataclass
class TimeNode:
    date: str
    rate: float
    id: str = field(default_factory=lambda: uuid4().hex)
    type: str | None = None
    seed: int | None = None

    def __post_init__(self):
        self.date = format_time(self.date)
        self.rate = rate(self.rate)
        validate_type(self.type, optional=True)
        if self.seed is not None and not isinstance(self.seed, int):
            raise ValueError('随机种子必须为整数')
        if not self.id:
            raise ValueError('节点 ID 不能为空')


@dataclass
class TimeSegment:
    start_node_id: str
    end_node_id: str
    method: str = 'linear'
    b: float = 0.5
    noise: float = 0.0
    seed: int | None = None

    def validate(self):
        if self.method not in ('linear', 'arps'):
            raise ValueError('曲线方法必须为 linear 或 arps')
        if not math.isfinite(self.b) or not 0 <= self.b <= 1:
            raise ValueError('Arps b 必须在 0 到 1 之间')
        rate(self.noise)
        if self.seed is not None and not isinstance(self.seed, int):
            raise ValueError('随机种子必须为整数')


@dataclass
class Well:
    name: str
    kind: str = 'producer'
    nodes: list[TimeNode] = field(default_factory=list)
    segments: list[TimeSegment] = field(default_factory=list)

    def validate(self):
        if not re.fullmatch(r"[^\s'/*]+", self.name):
            raise ValueError('井名不能为空或包含空格、引号、斜线、通配符')
        if self.kind not in ('producer', 'injector'):
            raise ValueError('井类型必须为 producer 或 injector')
        if len({day(n.date) for n in self.nodes}) != len(self.nodes):
            raise ValueError(f'{self.name}: 节点日期重复')
        if len({n.id for n in self.nodes}) != len(self.nodes):
            raise ValueError(f'{self.name}: 节点 ID 重复')
        for n in self.nodes:
            day(n.date)
            rate(n.rate)
            validate_type(n.type, optional=True)
        for s in self.segments:
            s.validate()

    def sync_segments(self):
        self.validate()
        self.nodes.sort(key=lambda n: n.date)
        old = {(s.start_node_id, s.end_node_id): s for s in self.segments}
        lookup = {n.id: n for n in self.nodes}
        result = []
        for a, z in zip(self.nodes, self.nodes[1:]):
            if self.type_at(a.date) != self.type_at(z.date):
                continue
            source = old.get((a.id, z.id))
            if source is None:
                # Splits inherit a containing old segment; merges inherit the preceding one.
                source = next((s for s in self.segments
                               if s.start_node_id in lookup and s.end_node_id in lookup
                               and lookup[s.start_node_id].date <= a.date
                               and z.date <= lookup[s.end_node_id].date), None)
                if source is None:
                    source = next((s for s in self.segments if s.start_node_id == a.id
                                   and s.end_node_id not in lookup), None)
            result.append(replace(source, start_node_id=a.id, end_node_id=z.id)
                          if source else TimeSegment(a.id, z.id))
        self.segments = result

    def type_at(self, when):
        current = self.kind
        for node in sorted(self.nodes, key=lambda n: n.date):
            if day(node.date) > day(when): break
            if node.type is not None: current = node.type
        return current

    def conversion_dates(self):
        current = self.kind
        result = []
        for node in sorted(self.nodes, key=lambda n: n.date):
            if node.type is not None and node.type != current:
                result.append(day(node.date))
                current = node.type
        return result

    def segment_index(self, node_id):
        return next((i for i, s in enumerate(self.segments) if s.start_node_id == node_id), None)

    def add_node(self, when, value, conflict='error', node_type=UNCHANGED, seed=None):
        node = TimeNode(when, value, type=None if node_type is UNCHANGED else node_type,
                        seed=seed)
        existing = next((n for n in self.nodes if n.date == node.date), None)
        if existing:
            if conflict == 'skip':
                return False
            if conflict == 'overwrite':
                if existing.rate != node.rate: existing.seed = None
                existing.rate = node.rate
                if node_type is not UNCHANGED:
                    existing.type = node.type
                    self.sync_segments()
                return True
            raise ValueError(f'{self.name}: {node.date} 已存在')
        self.nodes.append(node)
        self.sync_segments()
        return True

    def edit_node(self, node_id, when, value, node_type=UNCHANGED):
        index = next(i for i, n in enumerate(self.nodes) if n.id == node_id)
        previous = self.nodes[index]
        node = TimeNode(when, value, node_id, previous.type if node_type is UNCHANGED else node_type,
                        previous.seed if rate(value) == previous.rate else None)
        if any(n.id != node_id and n.date == node.date for n in self.nodes):
            raise ValueError('节点日期重复')
        self.nodes[index] = node
        self.sync_segments()

    def delete_node(self, node_id):
        self.nodes = [n for n in self.nodes if n.id != node_id]
        self.sync_segments()

    def set_segments(self, **changes):
        updated = [replace(s, **changes) for s in self.segments]
        for s in updated:
            s.validate()
        self.segments = updated

    def copy_from(self, source):
        self.kind = source.kind
        mapping = {n.id: uuid4().hex for n in source.nodes}
        self.nodes = [replace(n, id=mapping[n.id]) for n in source.nodes]
        self.segments = [replace(s, start_node_id=mapping[s.start_node_id],
                                 end_node_id=mapping[s.end_node_id]) for s in source.segments]


@dataclass
class ExportSettings:
    frequency: str = 'monthly'
    interval: int = 1
    month_end: bool = False
    keep_nodes: bool = True
    mode: str = 'prediction'
    split_date: str | None = None
    units: str = 'METRIC'
    injection_bhp: float | None = None
    injection_thp: float | None = None

    def validate(self):
        unit(self.units)
        if self.frequency not in ('daily', 'monthly', 'custom') or self.interval < 1:
            raise ValueError('无效采样设置')
        if self.mode not in ('history', 'prediction', 'split'):
            raise ValueError('无效导出模式')
        if self.mode == 'split':
            day(self.split_date)
        for p in (self.injection_bhp, self.injection_thp):
            if p is not None:
                rate(p)


@dataclass
class Project:
    name: str = 'Untitled'
    units: str = 'METRIC'
    start: str = '2025-01-01'
    end: str = '2025-12-31'
    wells: list[Well] = field(default_factory=list)
    export: ExportSettings = field(default_factory=ExportSettings)

    def validate(self):
        unit(self.units)
        if day(self.start) > range_end(self.end):
            raise ValueError('项目开始日期晚于结束日期')
        if len({w.name for w in self.wells}) != len(self.wells):
            raise ValueError('井名重复')
        for w in self.wells:
            w.validate()
        self.export.validate()

    def well(self, name):
        return next(w for w in self.wells if w.name == name)

    def add_well(self, name, kind='producer'):
        w = Well(name, kind)
        w.validate()
        if any(x.name == name for x in self.wells):
            return False
        self.wells.append(w)
        return True


def curve(well, at=None):
    """Evaluate exact instants; default preview grid is daily plus all nodes.

    Sub-day segments also get up to 24 preview steps to show their shape.
    """
    well.sync_segments()
    if not well.nodes:
        return {}
    instants = [day(n.date) for n in well.nodes]
    if at is None:
        dates = set(instants)
        cursor = instants[0].replace(hour=0, minute=0, second=0)
        while cursor <= instants[-1]:
            if cursor >= instants[0]: dates.add(cursor)
            cursor += timedelta(days=1)
        for start, end in zip(instants, instants[1:]):
            seconds = int((end-start).total_seconds())
            if seconds < 86400:
                steps = min(24, seconds)
                dates.update(start + timedelta(seconds=seconds*i//steps) for i in range(1, steps))
    else:
        dates = {day(value) for value in at}
    result = {}
    segments = {s.start_node_id: s for s in well.segments}
    random_seed = random.Random().getrandbits(128)
    for when in sorted(dates):
        if when < instants[0] or when > instants[-1]: continue
        index = bisect_right(instants, when) - 1
        a = well.nodes[index]
        if when == instants[index]:
            result[when] = a.rate
            continue
        z = well.nodes[index+1]
        if a.id not in segments:
            # Different phases cannot be interpolated. Hold the previous rate until conversion.
            result[when] = a.rate
            continue
        s = segments[a.id]
        fraction = (when-instants[index]).total_seconds() / (instants[index+1]-instants[index]).total_seconds()
        value = a.rate + (z.rate-a.rate)*fraction
        if s.method == 'arps' and 0 < z.rate <= a.rate:
            log_ratio = math.log(a.rate) - math.log(z.rate)
            if s.b < 1e-8:
                value = a.rate * math.exp(-log_ratio*fraction)
            else:
                x = s.b*log_ratio
                if x < 700:
                    value = a.rate * math.exp(-math.log1p(math.expm1(x)*fraction)/s.b)
                else:
                    value = math.exp(math.log(a.rate) - (x+math.log(fraction))/s.b)
        if s.noise:
            # A time-keyed seed keeps an instant's noise independent of sampling frequency.
            seed = s.seed if s.seed is not None else random_seed
            rng = random.Random(f'{seed}:{a.date}:{z.date}:{when.isoformat()}')
            value = max(0, value*(1+rng.gauss(0, s.noise)))
        result[when] = value
    return result


def sample(project, well, settings=None):
    settings = settings or project.export
    project.validate()
    settings.validate()
    start, end = day(project.start), range_end(project.end)
    if any(not start <= day(n.date) <= end for n in well.nodes):
        raise ValueError(f'{well.name}: 节点超出项目日期范围')
    if not well.nodes:
        return {}
    dates = set()
    d = start
    while d <= end:
        if settings.frequency != 'monthly' or (d.day == 1 if not settings.month_end
                                               else (d + timedelta(days=1)).month != d.month):
            dates.add(d)
        d += timedelta(days=settings.interval if settings.frequency == 'custom' else 1)
    if settings.keep_nodes:
        dates.update(day(n.date) for n in well.nodes)
    dates.update(well.conversion_dates())
    if settings.mode == 'split':
        dates.add(day(settings.split_date))
    return curve(well, at=(d for d in dates if start <= d <= end))
