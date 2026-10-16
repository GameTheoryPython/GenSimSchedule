"""Sampled single-phase rates in the user's OFM/Schedule VOL layout."""
from dataclasses import dataclass
from datetime import datetime, time
from .core import sample, from_metric


@dataclass(frozen=True)
class SampleRow:
    name: str
    when: datetime
    oil: float = 0
    water: float = 0
    gas: float = 0
    winj: float = 0
    ginj: float = 0
    days: float = 24

    def fields(self):
        return (f'{self.when.day:02d}', f'{self.when.month:02d}', str(self.when.year),
                *(f'{q:.10g}' for q in (self.oil, self.water, self.gas, self.winj, self.ginj, self.days)))


def sampled_rows(project, wells=None, settings=None, sampled=None):
    settings = settings or project.export
    wells = project.wells if wells is None else wells
    rows = []
    for well in wells:
        values = sampled[well.name] if sampled is not None else sample(project, well, settings)
        for when, value in sorted(values.items()):
            q = from_metric(value, settings.units)
            rows.append(SampleRow(well.name, when, oil=q if well.type_at(when) == 'producer' else 0,
                                  winj=q if well.type_at(when) == 'injector' else 0))
    return rows


def render_rows(rows, units):
    if units not in ('METRIC', 'FIELD'): raise ValueError('单位制必须为 METRIC 或 FIELD')
    if any(row.when.time() != time() for row in rows):
        raise ValueError('VOL 示例格式不支持时分秒；请使用午夜采样或导出 INC，不能丢弃节点时间')
    groups = {}
    for row in rows:
        groups.setdefault(row.name, []).append(row)
    lines = [f'*{units}', '*DAILY', '*IGNORE_MISSING', '*HRS_IN_DAYS',
             '*DAY *MONTH *YEAR *OIL *WATER *GAS *WINJ *GINJ *DAYS']
    for name, values in groups.items():
        if len({row.when for row in values}) != len(values):
            raise ValueError(f'{name}: VOL 日期重复')
        lines.extend(['', f'*NAME {name}'])
        lines.extend(' '.join(row.fields()) for row in sorted(values, key=lambda row: row.when))
    return '\n'.join(lines) + '\n'


def render(project, wells=None, settings=None):
    settings = settings or project.export
    return render_rows(sampled_rows(project, wells, settings), settings.units)
