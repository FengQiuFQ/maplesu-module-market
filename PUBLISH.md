# 独立仓库发布

此文档描述发布步骤；执行工具准备目录不会创建远端仓库或上传。初次发布继续使用已冻结的 `market.json` 和 `market.json.sig`，不重新生成时间戳或签名。

## 文件集合

独立仓库根目录保留：

- `market.json`、`market.json.sig`、`upstream-overrides.json`
- `README.md`、`SCHEMA.md`、`PUBLISH.md`、`requirements.txt`、`.gitignore`
- `.github/workflows/{ci,pages,sign}.yml`
- `tools/*.py` 与 `trust/{public-key.pem,public-key.spki.b64}`
- `modules/`、`packages/`、`sources/`、`changelogs/`、`upstream/` 的内容

排除 `.private/`、其他 PEM/私钥容器、Git blob 下载缓存、`__pycache__/`、虚拟环境、下载临时文件、`dist/` 和 `_site/`。原始模块 ZIP、源码 ZIP 的字节保持完整，不展开运行。

## 本地准备和复核

在 MapleSU 工作区执行，输出目录应为此前不存在的新目录：

```powershell
py -3 maplesu-module-market/tools/prepare_repository.py --out evidence/module-market-20261101/repository-ready --report evidence/module-market-20261101/repository-ready-files.json
py -3 maplesu-module-market/tools/check_publish_tree.py --root evidence/module-market-20261101/repository-ready --all
py -3 evidence/module-market-20261101/repository-ready/tools/market.py verify --public-key evidence/module-market-20261101/repository-ready/trust/public-key.pem
```

文件清单和字节统计写入 `repository-ready-files.json`。准备工具会验证正式签名，并在复制前检查所有选中文件；其输出包含工作流、维护工具和公钥。Pages 的静态树与该完整维护仓库分开生成。

## 建库、推送与启用 Pages

在已登录正确 GitHub 账号的 PowerShell 中执行以下命令。若远端仓库已经存在，先核对其内容和远端地址，再在现有仓库更新，跳过建库步骤。

```powershell
$marketRepository = 'D:/Maple_Workflow/MapleSU/evidence/module-market-20261101/repository-ready'
gh auth status
git -C $marketRepository init -b main
git -C $marketRepository add .
py -3 "$marketRepository/tools/check_publish_tree.py"
git -C $marketRepository diff --cached --stat
git -C $marketRepository commit -m 'Publish independently signed MapleSU module market'
gh repo create FengQiuFQ/maplesu-module-market --public --source $marketRepository --remote origin
git -C $marketRepository push -u origin main
gh api --method POST repos/FengQiuFQ/maplesu-module-market/pages -f build_type=workflow
gh workflow run pages.yml --repo FengQiuFQ/maplesu-module-market --ref main
gh run list --repo FengQiuFQ/maplesu-module-market --limit 10
```

若 Pages 站点已存在，则用以下命令把发布来源设为 GitHub Actions，替代上面的 POST：

```powershell
gh api --method PUT repos/FengQiuFQ/maplesu-module-market/pages -f build_type=workflow
```

初次推送触发的 Pages 任务可能早于站点配置；完成配置后显式运行 `pages.yml`，以该次任务的部署结果为准。任务只在签名与所有静态文件验证通过后上传 Pages artifact。工作流 Actions 以完整 commit SHA 固定。

部署完成后分别验证主备 URL。先核对清单和签名的实际响应字节，再验证清单引用的包；不要把 GitHub 任务成功视作多地区网络可达的证明。

```powershell
py -3 "$marketRepository/tools/market.py" probe --base-url https://fengqiufq.github.io/maplesu-module-market/ --report evidence/module-market-20261101/network-primary.json
py -3 "$marketRepository/tools/market.py" probe --base-url https://raw.githubusercontent.com/FengQiuFQ/maplesu-module-market/main/ --report evidence/module-market-20261101/network-backup.json
```

## 后续更新与可选工作流签名

常规更新可以本地导入、验证、签名后一起提交。推送 `main` 后，CI 和 Pages 都使用固定公钥验签；Pages 构建过程不读取私钥。

可选的 `Sign catalog` 工作流需要维护者事先配置仓库 Secret `MARKET_SIGNING_PRIVATE_KEY`，内容为与固定公钥配对的 PKCS#8 PEM。密钥仅在 runner 临时目录创建，权限为 `0600`，使用后清理，不进入 checkout 或 artifact。该工作流权限仅为 `contents: read`，不自动写回仓库。

手动运行签名任务后，下载名称为 `signed-catalog-<commit SHA>` 的 artifact。核对其中 `market.json` 与当前准备发布的清单原始字节一致，再接收对应 `market.json.sig`，使用 `trust/public-key.pem` 验证，提交并推送。清单发生任何字节变化，都需要重新签名。
