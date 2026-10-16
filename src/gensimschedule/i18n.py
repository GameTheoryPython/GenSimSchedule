"""Small UI catalog; machine-readable project and CSV values stay untranslated."""

EN = {
    '节点流量随机种子（可空）': 'Node rate seed (optional)',
    '噪声种子': 'Noise seed', '噪声种子（可空）': 'Noise seed (optional)',
    '随机添加节点': 'Add random nodes', '应用': 'Apply',
    '为 {count} 口选中井添加节点；流量单位：{units}': 'Add nodes to {count} selected wells; rate units: {units}',
    '节点时间（必填）': 'Node time (required)', '最小流量（必填）': 'Minimum rate (required)',
    '最大流量（必填）': 'Maximum rate (required)',
    '请填写节点时间、最小流量和最大流量': 'Enter the node time, minimum rate and maximum rate',
    '未打开工区': 'No workspace open',
    '未打开工区；请选择新建或打开': 'No workspace open; choose New or Open',
    '关闭当前工区': 'Close workspace',
    '未命名': 'Untitled',
    '预览格式': 'Preview format', '保存 VOL': 'Save VOL',
    'OIL/WINJ 为当前单位制的日流量；DAYS 为每日开井小时数（24）；TIME 仅用于表格显示':
        'OIL/WINJ: daily rates in current units; DAYS: uptime hours per day (24); TIME: table display only',
    'VOL 示例格式不支持时分秒；请使用午夜采样或导出 INC，不能丢弃节点时间':
        'This VOL layout does not support time of day. Use midnight samples or export INC; node times cannot be discarded.',
    'VOL 日期重复': 'Duplicate VOL date',
    '日期时间': 'Date / time', '节点时间': 'Node time',
    '支持日期或日期时间；省略时间时为 00:00:00': 'Enter a date or date/time; omitted time means 00:00:00',
    'YYYY-MM-DD HH:MM:SS；从此时开始预测': 'YYYY-MM-DD HH:MM:SS; prediction starts at this instant',
    '日期时间格式应为 YYYY-MM-DD HH:MM:SS': 'Expected date/time format: YYYY-MM-DD HH:MM:SS',
    '日期时间仅支持无时区的整秒精度': 'Use model-local date/time at whole-second precision without a timezone',
    '日期起点': 'Date from', '日期终点': 'Date to', '流量下限': 'Rate min', '流量上限': 'Rate max',
    '留空自动': 'Blank = auto', '应用坐标': 'Apply axes', '自动范围': 'Auto range',
    '坐标起点必须小于终点': 'Axis start must be less than axis end', '坐标必须为有限数值': 'Axis limits must be finite numbers',
    '初始视图': 'Home', '后退': 'Back', '前进': 'Forward', '平移': 'Pan', '框选缩放': 'Zoom',
    '恢复初始视图': 'Reset original view', '返回上一视图': 'Back to previous view',
    '前往下一视图': 'Forward to next view',
    '拖动平移；使用工具栏缩放按钮框选区域': 'Left button pans, Right button zooms\nx/y fixes axis, CTRL fixes aspect',
    '拖动框选区域缩放': 'Zoom to rectangle\nx/y fixes axis',
    '项目': 'Project', '新建': 'New', '打开': 'Open', '保存': 'Save', '另存为': 'Save As',
    '语言': 'Language', '搜索井名': 'Search wells', '创建井': 'Add well',
    'TXT 批量创建': 'Import wells (TXT)', 'TXT 选择井': 'Select wells (TXT)', '全选': 'Select all',
    '重命名': 'Rename', '删除选中井': 'Delete selected wells',
    '默认类型：生产井': 'Default type: producer', '默认类型：注水井': 'Default type: injector',
    '复制配置到选中井': 'Copy configuration', '单位': 'Units', '开始': 'Start', '结束': 'End',
    '应用项目设置': 'Apply project settings', '动态编辑': 'Schedule Editor', '采样与导出': 'Sampling and Export',
    '导入节点 CSV': 'Import nodes (CSV)', '导出节点 CSV': 'Export nodes (CSV)',
    '导入曲线配置 JSON': 'Import configuration (JSON)', '导出曲线配置 JSON': 'Export configuration (JSON)',
    '导出每日曲线 CSV': 'Export daily curves (CSV)', '第一优先级': 'Sort first by',
    '第二优先级': 'Then by', '井名': 'Well', '日期': 'Date', '升序': 'Ascending', '降序': 'Descending',
    '流量': 'Rate', '至下一节点方法': 'Next method', 'Arps b': 'Arps b',
    '噪声比例': 'Noise fraction', '种子': 'Seed', '从此日起类型': 'Type from this date', '生效类型': 'Effective type',
    '节点日期': 'Node date', '继承之前类型': 'Inherit', '生产井': 'Producer', '注水井': 'Injector',
    '添加到选中井': 'Add to selected wells', '随机添加': 'Add random', '删除节点': 'Delete nodes',
    '种子（可空）': 'Seed (optional)', '表格选中行': 'Selected table rows',
    '所选井全部时间段': 'All segments of selected wells', '应用范围': 'Apply to',
    '方法': 'Method', '噪声': 'Noise', '批量应用勾选字段': 'Apply checked fields',
    '月初': 'Month start', '月末': 'Month end', '保留节点': 'Keep nodes',
    'YYYY-MM-DD；该日开始预测': 'YYYY-MM-DD; prediction starts on this date',
    '采样': 'Sampling', '每 N 天': 'Every N days', '月采样位置': 'Monthly position', '模式': 'Mode',
    '分割日期': 'Split date', '历史注水 BHP（bar / psia）': 'History injection BHP (bar / psia)',
    '历史注水 THP（bar / psia）': 'History injection THP (bar / psia)',
    '预览': 'Preview', '保存 INC': 'Save INC', '复制文本': 'Copy text',
    '从本节点日期起生效；继承表示沿用前一次设置或井的默认类型':
        'Effective from this node date; inherit uses the previous setting or the well default',
    '{selected} 口井选中；{total} 口井；预览最多 50 口井':
        '{selected} selected; {total} wells; preview limited to 50 wells',
    '操作失败': 'Operation failed', '请选择井或节点': 'Select a well or node', '请先选择井': 'Select wells first',
    '选择文件': 'Choose file', '未保存': 'Unsaved changes', '保存当前项目？': 'Save the current project?',
    '井名已存在': 'The well name already exists', '未匹配井': 'Unmatched wells',
    '重命名请选择一口井': 'Select one well to rename', '新井名': 'New well name', '删除井': 'Delete wells',
    '删除 {count} 口井及其配置？': 'Delete {count} wells and their configuration?',
    '复制配置': 'Copy configuration', '源井': 'Source well', '覆盖配置': 'Overwrite configuration',
    '覆盖所选目标井的默认类型、全部节点和段参数？': 'Overwrite the default type, all nodes and segment parameters of the selected target wells?',
    '随机流量': 'Random rates', '最小值': 'Minimum', '最大值': 'Maximum',
    '请勾选需要应用的字段': 'Check the fields to apply',
    '请先在节点表中选择需要应用的行': 'Select the target rows in the node table first',
    '操作报告': 'Operation report', '成功 {success}；跳过 {skipped}；问题 {errors}':
        'Succeeded: {success}; skipped: {skipped}; issues: {errors}',
    '冲突策略': 'Conflict policy', '同日节点': 'Nodes on the same date', '配置导入': 'Import configuration',
    '导入全部井配置，同名井将覆盖，其他项目设置保留？':
        'Import all well configurations? Matching wells will be overwritten; other project settings are kept.',
    '保存失败': 'Save failed', '是': 'Yes', '否': 'No', '取消': 'Cancel', '放弃': 'Discard', '确定': 'OK',
    '每月': 'Monthly', '每日': 'Daily', '自定义': 'Custom', '预测': 'Prediction', '历史': 'History',
    '历史与预测': 'History / prediction', '跳过': 'Skip', '覆盖': 'Overwrite',
    '油量': 'Oil', '注水量': 'Water injection',
    # Errors from shared core remain Chinese for CLI; translate them at the UI boundary.
    '流量必须为有限非负数': 'Rate must be a finite non-negative number',
    '井类型必须为 producer 或 injector': 'Well type must be producer or injector',
    '节点 ID 不能为空': 'Node ID cannot be empty',
    '曲线方法必须为 linear 或 arps': 'Curve method must be linear or arps',
    'Arps b 必须在 0 到 1 之间': 'Arps b must be between 0 and 1',
    '随机种子必须为整数': 'Seed must be an integer',
    '井名不能为空或包含空格、引号、斜线、通配符': 'Well name cannot be empty or contain whitespace, quotes, slashes or wildcards',
    '节点日期重复': 'Duplicate node date', '节点 ID 重复': 'Duplicate node ID',
    '单位制必须为 METRIC 或 FIELD': 'Units must be METRIC or FIELD',
    '无效采样设置': 'Invalid sampling settings', '无效导出模式': 'Invalid export mode',
    '项目开始日期晚于结束日期': 'Project start date is after the end date', '井名重复': 'Duplicate well name',
    '节点超出项目日期范围': 'Node is outside the project date range',
    '历史注水 WCONINJH 需要显式 BHP 和 THP（目标单位制压力）':
        'History injection (WCONINJH) requires explicit BHP and THP in target pressure units',
    '随机流量需要同时指定最小值和最大值': 'Random rates require both minimum and maximum',
    '最小值大于最大值': 'Minimum exceeds maximum', '不支持的项目版本': 'Unsupported project version',
    '不支持 kind 字段，请使用 type': 'The kind field is not supported; use type',
    '缺少 type 字段': 'Missing type field', '冲突策略必须为 skip 或 overwrite': 'Conflict policy must be skip or overwrite',
    'CSV 必须含 well,date,rate 列': 'CSV must contain well,date,rate columns', '未知井': 'Unknown well', '已存在': 'already exists',
}


def translate(text, language):
    if language == 'zh':
        return text
    if text in EN:
        return EN[text]
    # Preserve contextual data such as well names and line numbers in shared errors.
    import re
    text = re.sub(r'第 (\d+) 行', r'Line \1', text)
    for source in sorted(EN, key=len, reverse=True):
        if source in text:
            text = text.replace(source, EN[source])
    return text
