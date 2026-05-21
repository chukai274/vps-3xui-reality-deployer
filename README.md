# VPS 3x-ui Reality Deployer

一个 Windows 本地 PyQt6 工具，用于在**已授权**的 VPS 上自动部署 3x-ui、配置 `VLESS + TCP + REALITY + xtls-rprx-vision`、开启 `BBR`、配置 `UFW`，并生成 Clash Verge / Shadowrocket 订阅链接与 Markdown 部署记录。

> 仅供学习参考。仅用于你本人拥有或被明确授权管理的 VPS。请遵守所在地法律法规、云服务商条款和网络使用规范，不得用于违法违规用途。

## 功能

- PyQt6 图形界面，支持后台线程执行部署
- 通过 SSH 自动连接单台 VPS
- 安装或覆盖部署 3x-ui
- 自动生成并写入 `VLESS + TCP + REALITY + xtls-rprx-vision` 节点
- 启用 `BBR + fq`
- 配置 `UFW`
- 生成 Clash Verge 和 Shadowrocket 订阅链接
- 自动保存 Markdown 部署记录
- 支持 `--self-test` 自检

## 环境要求

- Windows 10 / 11
- Python 3.11+
- 可访问目标 VPS 的 SSH 账号和密码

## 安装

```bash
pip install -r requirements.txt
```

## 运行

```bash
python vps_auto_deployer.py
```

自检：

```bash
python vps_auto_deployer.py --self-test
```

## 打包

使用 PyInstaller：

```bash
pyinstaller VPS_Reality_Deployer.spec
```

## 输出文件

- `deployment_records/vps-<ip>-deployment.md`

## 项目结构

```text
.
├── assets/
├── deployment_records/
├── requirements.txt
├── VPS_Reality_Deployer.spec
├── vps_auto_deployer.py
└── README.md
```

## 作者

CraigChu
