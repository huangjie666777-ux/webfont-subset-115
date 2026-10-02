# Web Font Subsetter

FastAPI 后端：上传静态 TrueType 字体，按文本需求裁剪为 WOFF2 子集并打包下载。

## 运行

    .venv/bin/uvicorn app.main:app --port 8140

## API

- POST /fonts（multipart 上传 .ttf）→ {font_id, coverage, ...}。仅接受含 glyf
  表的单字体 TTF；拒绝 TTC 集合、可变字体（fvar）、损坏文件。ID 为随机 UUID，
  不可覆盖，不接收宿主路径，原件以字节形式落盘、不做修改。
- GET /fonts/{font_id} → 字体元信息及 Unicode 覆盖。
- POST /builds，body {"texts": [...], "font_ids": [...], "family": "Name"}：
  - 码点按出现顺序去重，仅忽略 TAB/CR/LF，不做 Unicode 归一化；
  - 每个码点分配给首个 cmap 中有非 .notdef 映射的字体；
  - 缺字返回 422 并列出缺失码点，不做方框替代；
  - 为每个被使用的字体生成 WOFF2 子集：保留全部 GSUB 特性及其替换闭包、
    复合字形、GPOS 按保留字形裁剪、字形度量（hmtx/hhea）与 name 表
    （版权/许可）全部保留；未使用的字体不输出。
  - 成功后才注册 build ID；失败清理临时目录；并发构建使用唯一 ID + 原子改名，
    互不覆盖。
- GET /builds/{build_id}/download → ZIP：fonts.css（同一 font-family 的多条
  @font-face，unicode-range 升序合并连续区间，相对路径引用）、
  fonts/*.woff2、manifest.json（源字体 ID、码点分配、原始/输出字节数）。

## 限制

- 上传上限 FONT_SUBSET_MAX_UPLOAD_BYTES（默认 20MB）；
  文本总量 FONT_SUBSET_MAX_TEXT_CHARS（默认 200k 字符）、
  条目数 FONT_SUBSET_MAX_TEXTS（默认 10000）。
- 仅支持 glyf 版 TTF；不支持 CFF/CFF2 轮廓的 OTF、TTC 集合、可变字体。
- 输出仅 WOFF2；family 名限字母数字、空格、连字符（≤64 字符）。
- 数据存放于 FONT_SUBSET_DATA_DIR（默认 ./data）；无鉴权，请勿直接暴露公网。

## 测试

    .venv/bin/python -m pytest tests/ -q
