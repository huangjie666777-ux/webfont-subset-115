# Web 字体裁剪后端

基于 FastAPI + fontTools 的站点字体子集化服务：上传静态 TrueType 字体，按文本生成
WOFF2 子集、同字体族 @font-face CSS 与 ZIP 包。

## 运行

```bash
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
# 或: .venv/bin/python -m app
```

## API

- `POST /fonts` — `multipart/form-data` 字段 `file` 上传单个静态 TTF。返回内容哈希
  字体 ID（SHA-256，天然不可覆盖；重复上传返回 `already_present`）与 Unicode 覆盖。
  拒绝 `.ttc/.otc` 集合、含 `fvar` 的可变字体、CFF/OTF 轮廓及损坏文件。
- `GET /fonts/{id}` — 查询字体元数据与覆盖。
- `POST /builds` — JSON `{"texts": [...], "font_ids": ["id1", "id2"]}`，ID 顺序即回退
  优先级。码点按首次出现去重，仅忽略 TAB/CR/LF（U+0009/000A/000D），不做归一化；
  每个码点分给第一个有非 `.notdef` 映射的字体；缺字返回 422 与 `missing` 码点列表，拒绝构建。
- `GET /builds/{job_id}` / `GET /builds/{job_id}/download` — 查询状态、下载 ZIP。

ZIP 内容（均为相对路径）：`fonts.css`、`manifest.json`、`fonts/fontN-<id12>.woff2`。
CSS 中所有 @font-face 共享同一 `font-family: "SubsetWeb"`，`unicode-range` 只含实际
分配给该文件的码点，升序合并连续区间；CSS 用相对路径 `url("fonts/...")` 引用。

## 子集策略

- fontTools Subsetter 真正重写 glyf 轮廓并输出 WOFF2（非改扩展名、非仅删 cmap）。
- `layout-features=*`：保留全部 GSUB 特性并对保留字形做替换闭包（如 fi/fl 连字），
  GPOS 自动裁剪到剩余字形相关的定位；复合字形组件随父字形保留。
- 保留 hmtx 度量；`name_IDs=*` 保留版权、许可、设计者等全部 name 记录。
- 未被任何码点命中的字体不出现在产物中。

## 并发与失败

每个构建使用唯一 job ID 与独立暂存目录，成功后原子 rename 发布；失败（含缺字之外
的内部错误）清理暂存目录，不开放下载，构建之间互不覆盖。

## 限制（可用环境变量覆盖）

| 变量 | 默认 |
| --- | --- |
| `MAX_FONT_BYTES` | 15 MiB |
| `MAX_TEXTS` | 500 条 |
| `MAX_TEXT_CHARS` | 单条 200,000 字符 |
| `MAX_TOTAL_TEXT_CHARS` | 合计 2,000,000 字符 |
| `MAX_BUILD_FONTS` | 16 个有序字体 ID |
| `FONT_SUBSET_DATA` | `./data`（fonts/、jobs/、tmp/） |

另：仅接受含 glyf 表的单字体静态 TTF；无宿主路径输入（字体以 ID 引用，上传文件名仅作元数据）。

## 测试

```bash
.venv/bin/python -m pytest -q
```

覆盖：码点去重/忽略控制字符/不归一化、首字体回退、缺字拒绝、区间合并、字体校验
（损坏/集合/可变）、GSUB 闭包与复合字形保留、HTTP 全流程、并发构建、大小限制、
失败清理与原件不变。
