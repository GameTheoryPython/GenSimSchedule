from collections import defaultdict
from .core import sample, from_metric, day

MONTHS = ('JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN', 'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC')


def render(project, wells=None, settings=None, sampled=None):
    settings = settings or project.export
    settings.validate()
    blocks = defaultdict(lambda: defaultdict(list))
    for well in project.wells if wells is None else wells:
        values = sampled[well.name] if sampled is not None else sample(project, well, settings)
        for d, value in values.items():
            history = settings.mode == 'history' or (settings.mode == 'split' and d < day(settings.split_date))
            q = f'{from_metric(value, settings.units):.10g}'
            status = 'OPEN' if value > 0 else 'SHUT'
            prefix = f"  '{well.name}'"
            if well.type_at(d) == 'producer':
                keyword = 'WCONHIST' if history else 'WCONPROD'
                record = f"{prefix} {status} ORAT {q} /"
            elif history:
                keyword = 'WCONINJH'
                if settings.injection_bhp is None or settings.injection_thp is None:
                    raise ValueError('历史注水 WCONINJH 需要显式 BHP 和 THP（目标单位制压力）')
                record = f'{prefix} WATER {status} {q} {settings.injection_bhp:.10g} {settings.injection_thp:.10g} /'
            else:
                keyword = 'WCONINJE'
                record = f'{prefix} WATER {status} RATE {q} /'
            blocks[d][keyword].append(record)
    lines = ['-- Generated SCHEDULE include; existing WELSPECS/COMPDAT required.',
             f'-- Rates in {settings.units}; model unit system must match.',
             '-- ECLIPSE100 field layout checked against OPM keyword definitions.']
    for d, groups in sorted(blocks.items()):
        clock = f" '{d:%H:%M:%S}'" if d.hour or d.minute or d.second else ''
        lines.extend(['', 'DATES', f"  {d.day} '{MONTHS[d.month-1]}' {d.year}{clock} /", '/'])
        for keyword, records in sorted(groups.items()):
            lines.extend([keyword, *records, '/'])
    return '\n'.join(lines) + '\n'
