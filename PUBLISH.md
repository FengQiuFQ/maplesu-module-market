# 发布与维护

本仓库维护模块目录、原始模块包、对应源码与来源记录。投稿通过 Fork/PR 或 Issue 提交；目录签名和发布由仓库维护者管理。工具导出只准备本地文件，部署完成后再核对主备下载端点。

## 本地检查

以下命令在本仓库根目录执行：

```shell
python -m pip install -r requirements.txt
python tools/market.py verify --public-key trust/public-key.pem
python tools/check_maintainers.py
python -m unittest discover -s tools -p "test_*.py" -v
```

目录更新后使用 `verify --allow-unsigned` 运行待签名检查，发布使用固定公钥验证目录签名。

## 准备独立审阅目录

输出目录应为此前不存在的新目录：

```shell
python tools/prepare_repository.py --out ../module-market-review --report ../module-market-review-files.json
python tools/check_publish_tree.py --root ../module-market-review --all
python ../module-market-review/tools/market.py verify --public-key ../module-market-review/trust/public-key.pem
```

完整维护目录包含 README、SCHEMA、PUBLISH、贡献和版权说明、工具、Issue/PR 模板、维护登记、来源、公钥、原始包和对应源码。下载缓存、私钥容器、虚拟环境、临时文件与 `_site/` 不进入导出目录。

准备工具在报告中写入逐文件摘要、维护状态与 `release_ready`。原始包不展开执行；目录和签名原始字节保持不变。

## 发行前检查

```shell
python tools/check_maintainers.py --release
python tools/market.py verify --public-key trust/public-key.pem
```

`maintainers.json` 按模块 ID 登记维护账号、原作来源、实际许可和版本来源文件。`check_maintainers.py` 检查登记结构，`--release` 汇总各条目的维护登记完成状态。模块内容沿用各自许可证，工具代码使用仓库许可证。

清单发生字节变化后重新签名。原始版本包保持不可变，新内容使用新版本；维护和投稿规则见 [CONTRIBUTING.md](CONTRIBUTING.md)。

## 签名

`trust/public-key.pem` 与 `trust/public-key.spki.b64` 是固定验签公钥。私钥由维护者单独保存，PR 和 Pages 构建只持有公钥。

可选的 `Sign catalog` 工作流使用仓库 Secret `MARKET_SIGNING_PRIVATE_KEY`。签名材料仅在 runner 临时目录使用，工作流输出 `signed-catalog-<commit SHA>` artifact，不自动写回仓库。维护者核对 artifact 中的清单与审阅版本字节一致、使用固定公钥验签后，再一同提交清单和签名。

## Pages 与主备源

GitHub Pages 使用 GitHub Actions 发布。合并到 `main` 后，Pages 工作流运行公开树检查、单元测试和固定公钥验签，校验原始包及来源索引，再通过 `market.py export` 生成静态目录并部署。维护登记由 `check_maintainers.py` 独立维护。

| 入口 | 地址 |
| --- | --- |
| 主索引 | `https://fengqiufq.github.io/maplesu-module-market/market.json` |
| 备用索引 | `https://raw.githubusercontent.com/FengQiuFQ/maplesu-module-market/main/market.json` |

部署后使用 `market.py probe --base-url` 分别记录主备清单的下载状态与摘要。目录验签和本地包完整性由 `market.py verify --public-key trust/public-key.pem` 执行；匿名下载按清单中的包和源码摘要复核。MapleSU 端检查列表、详情、下载与安装前识别。

版权与移除请求通过 [COPYRIGHT.md](COPYRIGHT.md) 和专用 Issue 处理。

## MapleSU_Ultra 原生模块更新

新模块使用 `MAPLESU` 类型，已发布的 `SKROOT_PRO` 条目继续兼容。模块 ABI、ID 和原包保持稳定；更新使用新版本，`--select-latest` 选择当前版本并保留历史索引。

```shell
python tools/market.py add-local --package ../module-release/hello.zip --native-id e46a18d2c9074f63b85a9210d7ce304f --native-member libmodule_hello.so --release-date 2026-11-22
```

原生发布元信息放在 `payload/module.prop`。模块库内描述定义 ID，SDK 自带的独立标签常量由导入器略过。对应源码放在 `webroot/source.zip` 时，工具生成源码索引并记录字节摘要。完整调用、编译与打包见 [MapleSU_Ultra 开发指南](https://github.com/FengQiuFQ/MapleSU/blob/main/docs/ULTRA_MODULES.md)。
