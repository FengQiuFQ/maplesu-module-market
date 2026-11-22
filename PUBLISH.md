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

PR 可以使用 `verify --allow-unsigned` 检查待签名的目录。正式发布始终使用固定公钥验证目录签名，不把 PR 的结构检查当作发行验签结果。

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

已有条目逐项登记维护人、原作来源、实际许可与证据。待确认条目可供结构审阅，但会阻止发行检查通过。作者与资源许可按上传内容单独核对，工具许可证不覆盖市场包。

清单发生字节变化后重新签名。原始版本包保持不可变，新内容使用新版本；维护和投稿规则见 [CONTRIBUTING.md](CONTRIBUTING.md)。

## 签名

`trust/public-key.pem` 与 `trust/public-key.spki.b64` 是固定验签公钥。私钥由维护者单独保存，PR 和 Pages 构建只持有公钥。

可选的 `Sign catalog` 工作流使用仓库 Secret `MARKET_SIGNING_PRIVATE_KEY`。签名材料仅在 runner 临时目录使用，工作流输出 `signed-catalog-<commit SHA>` artifact，不自动写回仓库。维护者核对 artifact 中的清单与审阅版本字节一致、使用固定公钥验签后，再一同提交清单和签名。

## Pages 与主备源

启用 GitHub Pages 的 GitHub Actions 发布方式。合并到 `main` 后，CI 和 Pages 先执行来源、维护登记、签名和包检查，再生成并上传静态目录；全部发布检查通过后才部署。

| 入口 | 地址 |
| --- | --- |
| 主索引 | `https://fengqiufq.github.io/maplesu-module-market/market.json` |
| 备用索引 | `https://raw.githubusercontent.com/FengQiuFQ/maplesu-module-market/main/market.json` |

部署后使用 `market.py probe --base-url` 分别核对主备站点，验证清单、签名与其引用的包和源码摘要。最后在 MapleSU 验证列表、详情、下载与安装前检查；站点上传成功与应用端验收分别记录。

版权与移除请求通过 [COPYRIGHT.md](COPYRIGHT.md) 和专用 Issue 处理。
