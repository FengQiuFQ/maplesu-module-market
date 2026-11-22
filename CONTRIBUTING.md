# 投稿与维护模块

模块作者可以通过 Fork + PR 管理条目，也可使用“模块投稿与更新”Issue 提供材料。保持原 ID、作者与发布来源，后续更新由登记的维护者共同完成。

## 准备材料

- 原始模块 ZIP、稳定 ID、版本、兼容模式、发布日期与更新说明。
- 对应版本源码、原作者、实际许可证和第三方内容的来源；转载另附明确的分发依据。
- 负责更新的 GitHub 账号；接手已有模块时附原作者或现任维护者的交接依据。
- 实际验证的 MapleSU 版本、设备与限制，不把静态识别通过写成运行兼容。

## 导入与校验

在仓库根目录执行，下列文件名和 ID 换成自己的实际值：

```shell
python -m pip install -r requirements.txt
python tools/market.py add-local --package example-module.zip --release-date 2026-11-11
```

原生模块使用真实的描述 ID 与根目录库名：

```shell
python tools/market.py add-local --package example-module.zip --native-id a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6 --native-member libmodule_example.so --release-date 2026-11-11
```

更新已存在的模块时添加 `--select-latest`。同 ID、同版本的不同字节会被拒绝；使用新的版本号并保留旧包。原生市场元信息位于 `payload/module.prop`；脚本模块使用根目录 `module.prop`。

在 `maintainers.json` 的 `entries` 下登记条目。`maintainers` 使用 GitHub 用户名，`origin` 填真实原作，`license` 填实际许可，`evidence` 列出仓库内按版本保存的来源说明文件。由维护者核对后将 `status` 从 `pending` 设为 `ready`。现有导入不替作者推定许可。

```shell
python tools/market.py verify --allow-unsigned
python tools/check_maintainers.py
python -m unittest discover -s tools -p "test_*.py" -v
```

## 提交 PR

一并提交安装包、目录、版本记录、来源与维护登记。目录变化使旧签名失效，PR 阶段只检查结构和完整性；最终验签与发布在维护者重新签名后执行。不要为了通过 PR 伪造签名或更换信任公钥。

新增条目未完成来源核对时可以保留为待审阅，正式分发须通过 `python tools/check_maintainers.py --release`。维护登记不是账号访问控制，合并与签名仍由仓库维护者审核；投稿者不需要市场私钥。

只读取、校验投稿包，不执行投稿脚本、模块或库作为 CI 检查。版权和下架问题见 [COPYRIGHT.md](COPYRIGHT.md)，发布命令见 [PUBLISH.md](PUBLISH.md)。
