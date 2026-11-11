# MapleSU 模块市场

独立维护的静态模块目录。客户端从 MapleSU 的主备地址读取签名清单、模块包和更新记录；运行时不请求原上游服务。

当前收录 44 个模块。置顶顺序为 TEESimulator-RS_MapleSU 6.0.16、MapleSU Zygisk 5.1.2、LSPosed v2.1.1 (7790)、HMA-OSS Zygisk oss-173；其后按上传顺序排列本次用户提供的 17 个模块，其余模块保持原顺序。模块 ZIP 保留完整原始字节；源码归档与来源索引分开保存。兼容类别为 MapleSU_Ultra，具体安装条件见各条目说明。

正式地址：

- 主：`https://fengqiufq.github.io/maplesu-module-market/market.json`
- 备：`https://raw.githubusercontent.com/FengQiuFQ/maplesu-module-market/main/market.json`

## 目录

| 路径 | 用途 |
| --- | --- |
| `market.json` / `market.json.sig` | 当前模块清单与独立 ECDSA 签名 |
| `modules/<id>/module.json` | 自有模块元信息、兼容类别、当前版本与历史版本索引 |
| `packages/<id>/<version>/module.zip` | 按模块 ID、版本保存的原始包 |
| `changelogs/<id>/<version>.md` | 对应版本的更新记录与原始说明 |
| `sources/<source-id>/index.json` | 固定 commit 的源码归档或明确的来源说明 |
| `upstream/` | 原始清单快照、固定 Git commit/tree 与本地包元信息快照 |
| `trust/` | 可公开提交的 P-256 公钥 |

格式细节见 [SCHEMA.md](SCHEMA.md)。保留各模块原名称、作者与来源，不给未声明许可的来源统一追加许可证。原上游固定 tree 无顶层 LICENSE/COPYING/NOTICE；源码内已有第三方声明保留于各原始归档。

## 离线验证

```powershell
py -3 -m pip install -r requirements.txt
py -3 tools/market.py verify --public-key trust/public-key.pem
py -3 -m unittest discover -s tools -p 'test_*.py' -v
```

验证顺序：固定公钥验证清单原始字节 → 校验每个包的大小和 SHA256 → 检查 ZIP 结构与 CRC → 校验版本索引和源码归档 → 核对完整来源集合。导入及验证均不执行包内脚本或二进制。

## 更新来源

```powershell
py -3 tools/market.py import --report import-report.json
py -3 tools/market.py verify --allow-unsigned
```

`import` 更新远端来源，同时保留已登记的用户本地模块、旧版本包与版本索引。源码固定到本次导入的 commit。上游与本地模块 ID 冲突、同 ID 同版本出现不同字节时立即停止，由维护者明确选择当前版本；不按下载时间覆盖。

添加本地包时，先静态检查真实 native ID、`payload/module.prop` 和来源日期，再运行：

```powershell
py -3 tools/market.py add-local --package PATH_TO_ZIP --native-id NATIVE_ID --native-member libmodule_NAME.so --release-date YYYY-MM-DD
```

普通脚本模块省略 `--native-id` 和 `--native-member`，从根目录 `module.prop` 读取真实 ID，记录为 `KERNEL_SU`；原生模块记录为 `SKROOT_PRO`。展示版本保持原值，仅静态路径将空格等字符替换为下划线。

本地包来源索引明确标注是否附带对应源码；包内的 `webroot/source.zip` 会单独保存并校验。日期由维护者指定。`pinned_module_ids` 控制置顶顺序，后续导入继续保留。新增或更新清单会移除旧签名。

## 签名与发布

已生成公钥为 `trust/public-key.pem`，客户端固定值为 `trust/public-key.spki.b64`。私钥由维护者保存在市场目录和 Git 仓库之外；私钥内容不进入任何发布树。

```powershell
py -3 tools/market.py sign --private-key OUTSIDE_REPOSITORY/release-private.pem
py -3 tools/market.py verify --public-key trust/public-key.pem
py -3 tools/market.py publish --private-key OUTSIDE_REPOSITORY/release-private.pem --public-key trust/public-key.pem --primary-base https://fengqiufq.github.io/maplesu-module-market/ --backup-base https://raw.githubusercontent.com/FengQiuFQ/maplesu-module-market/main/ --out NEW_STAGING_DIRECTORY
```

`publish` 创建一个新的静态 staging 目录，签名并验证，不上传。部署者再把同一静态树发布到主备服务。`upstream/github/.../blobs` 是重复下载缓存，已从 Git 与发布树排除。

已有签名的版本使用以下命令导出 Pages 静态树，完整保留清单和签名字节，无需私钥：

```powershell
py -3 tools/market.py export --public-key trust/public-key.pem --out NEW_STATIC_DIRECTORY
```

仓库提供三个工作流：`Verify market` 在推送和 PR 时执行发布文件检查、测试及完整验签；`Publish Pages` 在 `main` 推送后验证并发布静态树；`Sign catalog` 由维护者手动运行，从仓库 Secret 中读取私钥，只产出清单与签名 artifact，不自动提交。默认维护方式仍可在本地签名，不要求给 GitHub 配置私钥。

完整独立仓库包含工具、公钥、工作流和静态内容；Pages 产物只包含运行所需静态文件。使用 `tools/prepare_repository.py` 生成经过检查的独立仓库发布目录。建库、Pages 配置及精确命令见 [PUBLISH.md](PUBLISH.md)。

发布后可从当前电脑执行三次真实下载探测：

```powershell
py -3 tools/market.py probe --base-url https://fengqiufq.github.io/maplesu-module-market/ --report network-primary.json
```

此结果只代表当前电脑网络。国内多运营商访问需另行记录地区、运营商、时间与实际响应；当前未宣称已完成该验收。
