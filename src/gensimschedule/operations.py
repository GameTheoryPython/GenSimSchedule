import random
from .core import TimeNode, TimeSegment, day, to_metric, rate, UNCHANGED, validate_type


def add_nodes(project, wells, when, value=0, minimum=None, maximum=None, seed=None, node_type=UNCHANGED):
    day(when)
    to_metric(value, project.units)
    if node_type is not UNCHANGED: validate_type(node_type, optional=True)
    if seed is not None and not isinstance(seed, int): raise ValueError('随机种子必须为整数')
    if (minimum is None) != (maximum is None):
        raise ValueError('随机流量需要同时指定最小值和最大值')
    if minimum is not None and (rate(minimum) > rate(maximum)):
        raise ValueError('最小值大于最大值')
    rng = random.Random(seed)
    success = 0
    for well in wells:
        q = rng.uniform(minimum, maximum) if minimum is not None else value
        success += well.add_node(when, to_metric(q, project.units), 'skip', node_type,
                                 seed=seed if minimum is not None else None)
    return {'success': success, 'skipped': len(wells) - success, 'errors': []}


def set_segments(wells, **changes):
    TimeSegment('a', 'b', **changes).validate()
    for well in wells:
        well.set_segments(**changes)
