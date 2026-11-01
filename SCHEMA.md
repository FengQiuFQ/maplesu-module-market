# MapleSU 静态模块市场格式（v1）

目录入口为 `market.json`，保留 `module_list` 及模块原有的 `chn_name`、`eng_name`、`ver`、`desc`、`author`、`id32`、`update_date`、下载提示与 `ban` 字段。完整原始记录另保存在 `upstream`，原始响应按摘要留在 `upstream/`。

新增字段：

```json
{
  "schema_version": 1,
  "catalog_id": "maplesu",
  "generated_at": "ISO-8601 UTC",
  "official_mirrors": {
    "primary": {"base_url": "https://fengqiufq.github.io/maplesu-module-market/", "published": false},
    "backup": {"base_url": "https://raw.githubusercontent.com/FengQiuFQ/maplesu-module-market/main/", "published": false}
  },
  "signature": {"algorithm": "SHA256withECDSA", "encoding": "base64-der", "curve": "P-256", "path": "market.json.sig", "required": true},
  "module_list": [{
    "chn_name": "保留上游名称",
    "ver": "保留上游版本",
    "id32": "保留原始标识（并非总是32位十六进制）",
    "type": "SKROOT_PRO",
    "compatibility": {
      "modes": ["MapleSU_Ultra"],
      "normal_supported": false,
      "device_validation": "pending"
    },
    "download_url": "packages/ID/VERSION/module.zip",
    "sha256": "下载ZIP的64位小写SHA256",
    "size": 123,
    "package": {"path": "packages/ID/VERSION/module.zip", "sha256": "同上", "size": 123},
    "source_url": "sources/SOURCE-ID/index.json",
    "source_index": {"path": "sources/SOURCE-ID/index.json", "sha256": "来源索引原始字节的SHA256", "size": 123},
    "changelog_url": "changelogs/ID/VERSION.md",
    "module_index": {"path": "modules/ID/module.json", "sha256": "版本索引原始字节的SHA256", "size": 123},
    "mirrors": {
      "primary": "packages/ID/VERSION/module.zip",
      "backup": "packages/ID/VERSION/module.zip"
    },
    "upstream": {"download_url": "原URL", "source_url": "原URL", "其他字段": "原值"}
  }]
}
```

`download_url`、`source_url`、`changelog_url`、`package.path`、`module_index.path`、`mirrors` 都是相对于所加载清单 URL 的路径。主备部署应包含完全相同的静态树，App 分别以可信主备根地址解析；当前正式地址已配置，`published=false` 表示仍待发布验收。

`compatibility` 来自市场格式/来源归类，`device_validation=pending` 表示未宣称已逐个在真机安装。`SKROOT_PRO` 模块在 MapleSU_Normal 中不开放安装。

签名使用 P-256 与 SHA-256，覆盖 **market.json 原始 UTF-8 字节**。`market.json.sig` 是 ASCII Base64 编码的 **DER ECDSA 签名**，末尾换行；不是固定 64 字节的 `r || s`。客户端通过 `Signature.getInstance("SHA256withECDSA")` 验证。公钥为独立固定的 X.509/SPKI DER Base64，禁止从同一清单自动接受新公钥。签名通过后，再验证模块 ZIP 的 `size`、`sha256` 和版本索引摘要。仓库仅包含公钥，私钥保存在仓库树外。

每个 `modules/ID/module.json` 包含 `schema_version`、`id32`、`name`、`latest_version`、`compatibility` 与 `releases`。每个 release 保存原版本、日期、作者、包路径与摘要、源码索引、更新记录和原始来源记录；相同 ID 的旧版本保留独立包路径。`market.json` 的 `module_list` 每个 ID 只出现一个当前版本。

原上游响应由 `upstream_snapshot` 固定；用户提供的额外包使用 `additional_snapshots` 固定原始元信息、包摘要、文件名日期与 native ID 依据。所有来源 ID 的并集须与当前模块 ID 集合一致，防止导入时静默丢项。用户本地包的源码索引使用 `kind=user-supplied-package`、`source_available=false`、`archive=null`；该索引记录来源，不声称附带对应源码。
