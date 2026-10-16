# GenSimSchedule

根据时间节点生成油井/注水井生产动态，提供 CLI 和 PySide6 桌面界面，共享核心计算。内部流量始终采用 m³/day。

## 启动

使用项目已有 `.venv`，通过 uv 安装本项目入口并运行：

```powershell
uv sync
uv run gensimschedule-gui
uv run gensimschedule --help
uv run pytest -q
```

测试临时文件统一放在 `.test-artifacts/`：pytest 临时目录为 `pytest-tmp/`，缓存为 `pytest-cache/`。运行测试无需额外指定 `--basetemp`；如需单独指定，路径也应放在 `.test-artifacts/` 下。历史 `.test-tmp*`、旧 pytest 缓存及界面截图保留在 `.test-artifacts/history/`，后续界面检查截图也请写入 `.test-artifacts/`，避免散落在项目根目录。

CLI 使用标准库 argparse，GUI 使用已有 PySide6 和 Matplotlib，未增加 Typer/pyqtgraph 依赖。

## 完整 CLI 示例

```powershell
uv run gensimschedule project new demo.json --start 2025-01-01 --end 2025-12-31
uv run gensimschedule well import examples/wells.txt --project demo.json
uv run gensimschedule well type I1 --kind injector --project demo.json
uv run gensimschedule node import examples/nodes.csv --project demo.json
uv run gensimschedule curve set --method arps --b 0.5 --noise 0.05 --seed 42 --project demo.json
uv run gensimschedule curve generate --output daily.csv --project demo.json
uv run gensimschedule export eclipse demo.inc --mode split --split-date 2025-07-01 --injection-bhp 200 --injection-thp 10 --project demo.json
```

批量命令默认作用于全部井；`--wells P1 P2` 或 `--selection examples/wells.txt` 限定井。随机添加节点用 `node add 日期 --minimum 50 --maximum 100 --seed 42`；同日节点跳过。CSV 导入支持 `--conflict overwrite`。`curve set` 仅修改显式参数；噪声比例 `0.05` 表示 5%。复制配置使用 `well copy 源井 --wells 目标井 --yes`，默认井类型、节点类型切换及全部段参数一并复制，使各时刻生效类型与源井一致；保留目标井名，节点 ID 会重新生成。GUI 的 Copy configuration / 复制配置采用同样规则。

`node edit 井名 节点ID 日期 --rate 数值` 修改节点，`node delete 井名 节点ID` 删除；节点 ID 可在 `project show` 中查看。`well rename`、`well delete`、`well type` 管理井。`node export` 导出当前项目单位下的 CSV；项目 JSON 同时包含节点、段参数和导出设置，可作为完整配置备份。

导出采样支持 `--frequency daily/monthly/custom`，自定义天数用 `--interval N`，月末用 `--month-end`，关闭节点保留用 `--no-keep-nodes`。分割日及以后使用预测关键字，分割日前使用历史关键字；分割日在有效曲线范围内会自动加入采样以保证切换生效。

## 桌面操作

随机种子分为两类：节点 `seed` 记录“随机添加”时生成节点流量使用的种子；时间段 `seed` 用于曲线噪声，两者独立。项目 JSON 保存两种种子，复制节点配置也保留节点的生成种子。手动修改节点流量或通过 CSV 覆盖为不同流量时会清除对应 `seed`，以免继续标记为原随机结果；修改日期或类型且流量不变时保留。未指定种子为 null，旧版本未保存的生成种子无法从已有流量反推。恢复项目使用已保存节点流量，不会再次随机生成；单独复现一次批量生成还需相同上下限、井顺序等输入。

节点时间支持 **`YYYY-MM-DD HH:MM:SS`**，例如 `2025-01-01 08:30:00`；也接受 `YYYY/M/D H:MM[:SS]` 和 ISO 的 `T` 分隔符。只输入日期表示当天 `00:00:00`。同井同日可有多个不同时间节点，仅完全相同的时刻视为冲突。使用模型本地时间，精度到秒，不接受时区或小数秒。

表格编辑、批量添加、CSV/JSON、CLI、图表和坐标范围均保留完整时间；插值按实际秒数比例计算，短于一天的时间段也能生成曲线。转注及历史/预测分割均按精确时刻生效。项目结束只填日期时包含整天；若填写日期时间则以该时刻为界。每日/每 N 天采样以项目开始时刻为锚点，月采样取相应月初/月末且使用项目开始时分秒；保留节点时额外包含原始时刻，类型切换时刻始终保留。预览/每日曲线 CSV 采用每日网格加节点，对不足一天的段补充最多 24 个间隔以展示曲线形状；它不是小时采样设置。

ECLIPSE 非零时刻写入 DATES 第四字段，例如 `1 'JAN' 2025 '08:30:00' /`，午夜省略时间字段。同一天不同时间分别输出，不合并。[OPM DATES 字段说明](https://opm.github.io/opm-flow-editor-support/keywords/DATES.html)支持该时间字段；实际目标模拟器的兼容性仍需模型验证。固定种子噪声按段端点及计算时刻确定，同一时刻不受采样频率影响；端点不加噪声。

界面默认使用英文。顶部工具栏的 **Language / 语言** 下拉框可即时切换 **English / 中文**，菜单、页签、按钮、表头、选项、对话框、提示及曲线图例同步切换。英文页签名称为 **Schedule Editor** 和 **Sampling and Export**。切换语言保留当前项目、未保存输入、所选井、节点表选择及预览结果；语言仅影响界面，CSV/JSON 字段、内部类型值及 ECLIPSE 关键字不翻译。每次启动默认英文。

动态图支持鼠标滚轮缩放（以鼠标位置为中心），以及图上方工具栏的平移、框选缩放、初始视图、前进和后退。输入“日期起点 / 日期终点”和“流量下限 / 流量上限”后点击“应用坐标”；日期可用 `YYYY-MM-DD` 或 `YYYY/M/D`，流量按当前显示单位输入，留空的边界按数据自动计算。起点须小于终点。点击“自动范围”清除自定义边界并显示全部曲线。已应用的边界在节点重绘和语言切换时保留，单位切换保持相同物理范围；切换井后若部分自动边界产生无效范围则恢复自动范围。坐标范围仅用于本次界面显示，不修改项目日期、节点、采样或导出数据；新建或打开项目时恢复自动范围。

“动态编辑”页提供节点 CSV 导入/导出、曲线配置 JSON 导入/导出，以及每日曲线 CSV 导出。该页导出仅包含左侧选中的井；CSV 流量按当前显示单位输出。节点 CSV 保存 `well,date,rate,type`（type 为空表示继承），导入时井须已存在，可选择跳过或覆盖同日节点。曲线配置 JSON 保存节点、方法、Arps 参数、噪声和种子，并记录单位与项目设置；导入时确认覆盖同名井配置，项目设置保留。每日曲线 CSV 是生成后的派生数据，重新作为节点导入会产生每日节点，不等同于恢复原始曲线配置；需要完整往返时使用 JSON。顶部项目工具栏提供新建、打开、保存、另存为和“关闭当前工区 / Close workspace”。关闭工区时可保存、放弃或取消；关闭后清空井、节点、曲线与导出预览，进入“未打开工区 / No workspace open”状态：禁用井管理、编辑、保存和导出，仅保留新建、打开及语言切换。软件窗口和当前语言保留。New 创建可编辑的未命名工区；Open 成功后恢复编辑。取消打开或取消保存不会退出当前状态。

左侧创建、导入、搜索和多选井；TXT 可匹配选中井。节点表展示所有选中井的节点，包含只读井名列；节点排序支持第一、第二优先级选择“井名”或“日期”，各优先级独立设置升序或降序；两个字段始终不同，切换一个字段时另一个自动调整。默认井名优先、日期其次，均为升序。例如可设置井名降序、同井内日期升序。单选或多选井时均可直接修改每行的日期、流量、段方法、b、噪声和种子，也可选择多行跨井删除节点。每口井的最后一个节点以及跨类型转换前的节点没有后续插值段。“批量应用勾选字段”默认范围为“表格选中行”，只修改选中行至下一节点的时间段，末节点跳过；未选行或未勾选字段时提示。也可显式选择“所选井全部时间段”。未勾选字段、节点日期和流量均保持原值。“随机添加 / Add random”使用单个窗口集中填写节点时间、最小/最大流量、可选随机种子及从此日起类型，点击 Apply / 应用后统一校验。时间和流量上下限为必填，时间须在项目范围内，流量须为有限非负数、最小值不得大于最大值，种子须为空或整数。无效输入在原窗口提示并保留已填内容，校验通过前不修改数据；取消不产生变化。曲线最多显示所选前 50 口井，节点表和导出仍处理全部所选井。

“采样与导出”页显示采样表和可复制文本；`monthly` 时启用“月初 / 月末”选择，默认月初；`custom` 时启用“每 N 天”；`daily` 时两者均禁用。切换采样方式时保留输入值，但不适用的设置不参与采样。保存 INC 前自动重新生成。项目设置控制日期范围与显示单位；单位切换保持节点物理量不变。关闭、新建或打开前提示保存修改。完整配置 JSON 可导入已有项目，同名井覆盖前会确认。

## 导出兼容性与行为

### VOL 采样预览与导出

“采样与导出”页的表格按示例展示 `NAME, DAY, MONTH, YEAR, OIL, WATER, GAS, WINJ, GINJ, DAYS`，额外的 `TIME` 列保留节点时分秒以免界面隐藏时间。表格是派生数据，只读，所有列仍可拖动调整宽度。选择“预览格式”为 VOL 可查看原始文本；“保存 VOL”导出左侧选中井，并自动补充 `.VOL` 后缀。原来的 INC 预览及导出继续保留。

文件头为当前单位制的 `*METRIC` 或 `*FIELD`，随后为 `*DAILY`、`*IGNORE_MISSING`、`*HRS_IN_DAYS` 和示例列头，按井输出 `*NAME 井名` 数据块。生产阶段流量写入 OIL，注水阶段写入 WINJ；未建模的 WATER、GAS、GINJ 填 0。DAYS 固定为 24，表示本工具采用每日 24 小时可用的假设，不是采样间隔。流量仍为每日单位，月采样也不乘以当月天数；[Equinor VOL 示例](https://equinor.github.io/subscript/scripts/ofmvol2csv.html)同样使用 DAILY/HRS_IN_DAYS 及 DAYS=24 的布局。

该示例 VOL 布局只有日/月/年，没有时分秒字段。若采样结果含非午夜时刻，VOL 预览/导出会明确报错，不截断或合并时刻；表格仍显示完整时间。可使用午夜采样；若必须保留非午夜节点或转注时刻，请导出支持时间字段的 INC。尚未运行实际 VOL 消费软件进行兼容验证。

CLI 同样支持：`uv run gensimschedule export vol output.VOL --project demo.json`，采样与单位参数同 `export eclipse`。

### 按日期转注 / 转回生产

井的 `type` 是默认类型，节点新增可选 `type`：`producer` / `injector`，为空（JSON 为 `null`）表示继承前一次节点设置，没有前次设置时使用井默认类型。设置从本节点日期起生效，支持多次转换。修改默认类型不清除显式节点设置。

在“动态编辑”表格的“从此日起类型”下拉框设置转换日节点，旁边“生效类型”显示实际类型。添加节点时也可选择类型。“默认类型：生产井 / 注水井”只修改井默认值，不代替按日期转换。油量和注水量分别以实线 / 虚线显示，转换处断开，不将不同物理量连成曲线。

不同类型的相邻节点不创建插值段：前一节点流量保持到转换日前一天；转换日立即采用新类型及其节点流量。如果需要停产期，先添加原类型的零流量节点。最终节点之后仍不延伸曲线。末节点及跨类型相邻节点的“至下一节点方法”留空，批量应用段参数时跳过。

节点 CSV 支持可选 `type` 列，例如 [conversion_nodes.csv](examples/conversion_nodes.csv)：

```csv
well,date,rate,type
W1,2025-01-01,100,producer
W1,2025-06-30,20,
W1,2025-07-15,150,injector
W1,2025-12-31,200,
```

导入前创建 W1；项目日期范围须涵盖这些节点。三列 CSV 覆盖已有节点时保留原类型设置；包含 `type` 列时空值表示清除该节点显式设置、恢复继承。节点 CSV 导出保存显式类型设置；每日曲线 CSV 导出为每一日写入生效类型。JSON 保存节点类型及段 ID 引用。

CLI 创建转换节点：`node add 2025-07-15 --rate 150 --type injector --wells W1 --project demo.json`。`node edit` 同样支持 `--type producer/injector/inherit`；省略该选项时保留已有类型设置。

采样始终包含类型转换日期，即使关闭“保留节点”。历史/预测分割日期和井类型转换日期分别处理：历史生产 / 注水使用 WCONHIST / WCONINJH，预测生产 / 注水使用 WCONPROD / WCONINJE；每日期每井仅写入当前类型的控制。历史注水仍需显式 BHP、THP。采用新控制关键字切换类型的行为参考 [OPM Well 的生产/注入控制更新实现](https://github.com/OPM/opm-common/blob/master/opm/input/eclipse/Schedule/Well/Well.cpp)，不额外在同日重发旧类型控制以免切回。尚无实际模拟器运行验证，具体商业 ECLIPSE 版本及转注后的完井/压力约束需由目标模型验证。

字段顺序依据 OPM opm-common 的 ECLIPSE100 关键字定义核对：

- [WCONPROD](https://github.com/OPM/opm-common/blob/master/opm/input/eclipse/share/keywords/000_Eclipse100/W/WCONPROD)：井名、状态、ORAT、油量。
- [WCONHIST](https://github.com/OPM/opm-common/blob/master/opm/input/eclipse/share/keywords/000_Eclipse100/W/WCONHIST)：井名、状态、ORAT、油量；水气量使用该格式允许的缺省零值。仅用于设计规定的单相合成历史，不表达真实多相历史。
- [WCONINJE](https://github.com/OPM/opm-common/blob/master/opm/input/eclipse/share/keywords/000_Eclipse100/W/WCONINJE)：井名、WATER、状态、RATE、水量；其余字段采用解析器默认。
- [WCONINJH](https://github.com/OPM/opm-common/blob/master/opm/input/eclipse/share/keywords/000_Eclipse100/W/WCONINJH)：井名、WATER、状态、水量、BHP、THP。压力字段没有声明默认值，因此必须显式提供。METRIC 压力为 bar，FIELD 为 psia。

这是可包含于已有 SCHEDULE 的片段，依赖模型已定义井和完井，目标模型单位须与导出单位一致。没有实际 ECLIPSE/OPM 模拟器运行验证；不承诺所有商业版本兼容，投入具体模型前需按目标版本验证压力约束和历史控制行为。

零流量输出 SHUT；正流量输出 OPEN。没有节点的井不输出；单节点只在该节点日期有一个值，不延伸。节点超出项目范围禁止导出。不满足正流量递减条件的 Arps 段使用线性。固定种子噪声先生成每日值再采样，端点不加噪声。TXT 支持 UTF-8/BOM 和 GB18030；CSV 为 UTF-8/BOM，必需列为 `well,date,rate`，可选 `type` 列支持按日期转换井类型。错误报告包含行号，未知井跳过，合法行在全部解析后应用。

## 结构

`core.py`：模型、段同步、曲线、单位、采样；`operations.py`：共享批量操作；`storage.py`：JSON/TXT/CSV；`eclipse.py`：SCHEDULE 渲染；`cli.py` / `gui.py`：入口。测试覆盖段继承、Arps、噪声、单位、采样、100 井批量、持久化、字段输出、CLI 流程和 GUI 离屏启动。
