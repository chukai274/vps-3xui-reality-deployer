from __future__ import annotations

import base64
import os
import re
import shlex
import socket
import sys
import textwrap
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

import paramiko
from PyQt6.QtCore import QThread, Qt, pyqtSignal
from PyQt6.QtGui import QFont, QIntValidator, QTextCursor
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QProgressBar,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


APP_TITLE = "VPS 3x-ui Reality 自动部署工具"
AUTHOR = "CraigChu"
DISCLAIMER = (
    "仅供学习参考；本工具仅用于本人拥有或被授权管理的 VPS 环境部署、网络技术学习和合规运维。"
    "请遵守所在地法律法规、云服务商条款和网络使用规范，不得用于违法违规用途。"
)

ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
IP_RE = re.compile(
    r"^(25[0-5]|2[0-4]\d|1?\d?\d)(\.(25[0-5]|2[0-4]\d|1?\d?\d)){3}$"
)


@dataclass
class DeployConfig:
    ip: str
    ssh_user: str
    ssh_password: str
    panel_port: int
    sub_port: int
    inbound_port: int
    write_ssh_password: bool
    change_root_password: bool
    new_root_password: str
    restrict_panel: bool
    panel_allowed_ip: str


@dataclass
class DeployResult:
    ip: str
    ssh_user: str
    ssh_password_for_report: str
    panel_url: str
    panel_username: str
    panel_password: str
    web_base_path: str
    clash_url: str
    shadowrocket_url: str
    uuid: str
    public_key: str
    private_key: str
    short_id: str
    sub_id: str
    panel_port: int
    sub_port: int
    inbound_port: int
    cert_summary: str
    acme_summary: str
    ufw_summary: str
    bbr_summary: str
    report_path: str


def strip_ansi(text: str) -> str:
    return ANSI_RE.sub("", text).replace("\r", "\n")


def now_stamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def safe_filename_ip(ip: str) -> str:
    return re.sub(r"[^0-9A-Za-z_.-]+", "_", ip)


def extract_value(text: str, key: str) -> str:
    pattern = re.compile(rf"^{re.escape(key)}=(.*)$", re.MULTILINE)
    match = pattern.search(text)
    return match.group(1).strip() if match else ""


def parse_install_output(output: str) -> dict[str, str]:
    clean = strip_ansi(output)
    result: dict[str, str] = {}
    patterns = {
        "panel_username": r"Username:\s*([^\s]+)",
        "panel_password": r"Password:\s*([^\s]+)",
        "web_base_path": r"WebBasePath:\s*([^\s]+)",
        "panel_url": r"Access URL:\s*(https?://[^\s]+)",
    }
    for name, pattern in patterns.items():
        matches = re.findall(pattern, clean)
        if matches:
            result[name] = matches[-1].strip()
    return result


def b64_text(value: str) -> str:
    return base64.b64encode(value.encode("utf-8")).decode("ascii")


class RemoteError(RuntimeError):
    pass


class RemoteDeployer:
    def __init__(self, config: DeployConfig, log: Callable[[str], None]):
        self.config = config
        self.log = log
        self.client: paramiko.SSHClient | None = None

    def deploy(self) -> DeployResult:
        self.connect()
        try:
            baseline = self.exec_script(
                self.baseline_script(),
                "读取系统、端口和旧配置状态",
                timeout=60,
            )

            install_output = self.exec_script(
                self.install_script(),
                "覆盖安装 3x-ui 并申请 IP 证书",
                timeout=1800,
            )
            install_info = parse_install_output(install_output)
            missing = [
                name
                for name in ("panel_username", "panel_password", "web_base_path")
                if not install_info.get(name)
            ]
            if missing:
                raise RemoteError(
                    "无法从 3x-ui 安装输出中解析面板信息: " + ", ".join(missing)
                )

            config_output = self.exec_script(
                self.configure_script(),
                "配置 VLESS Reality、订阅、BBR 和 UFW",
                timeout=600,
            )

            verify_output = self.exec_script(
                self.verify_script(),
                "验证服务、证书、订阅和自动续期",
                timeout=180,
            )

            self.check_public_ports()

            result = self.build_result(
                baseline=baseline,
                install_info=install_info,
                config_output=config_output,
                verify_output=verify_output,
            )
            report_path = self.write_report(result)
            result.report_path = str(report_path)
            return result
        finally:
            self.close()

    def connect(self) -> None:
        self.log(f"[{now_stamp()}] 正在连接 {self.config.ssh_user}@{self.config.ip} ...\n")
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            client.connect(
                hostname=self.config.ip,
                port=22,
                username=self.config.ssh_user,
                password=self.config.ssh_password,
                timeout=15,
                banner_timeout=15,
                auth_timeout=15,
                look_for_keys=False,
                allow_agent=False,
            )
        except Exception as exc:
            raise RemoteError(f"SSH 连接失败: {exc}") from exc
        self.client = client
        self.log(f"[{now_stamp()}] SSH 连接成功。\n")

    def close(self) -> None:
        if self.client is not None:
            self.client.close()
            self.client = None

    def exec_script(self, script: str, title: str, timeout: int) -> str:
        if self.client is None:
            raise RemoteError("SSH 未连接。")
        self.log(f"\n========== {title} ==========\n")
        transport = self.client.get_transport()
        if transport is None:
            raise RemoteError("SSH transport 不可用。")

        channel = transport.open_session()
        channel.set_combine_stderr(True)
        channel.exec_command("bash -s")
        channel.sendall(script)
        channel.shutdown_write()

        start = time.time()
        output_parts: list[str] = []
        while True:
            if channel.recv_ready():
                chunk = channel.recv(8192).decode("utf-8", errors="replace")
                output_parts.append(chunk)
                self.log(strip_ansi(chunk))

            if channel.exit_status_ready():
                while channel.recv_ready():
                    chunk = channel.recv(8192).decode("utf-8", errors="replace")
                    output_parts.append(chunk)
                    self.log(strip_ansi(chunk))
                status = channel.recv_exit_status()
                break

            if time.time() - start > timeout:
                channel.close()
                raise RemoteError(f"{title} 超时，已中止。")
            time.sleep(0.1)

        output = "".join(output_parts)
        if status != 0:
            raise RemoteError(f"{title} 失败，远程退出码 {status}。")
        self.log(f"\n[{now_stamp()}] {title} 完成。\n")
        return output

    def baseline_script(self) -> str:
        return textwrap.dedent(
            """
            set -e
            echo "-- hostnamectl --"
            hostnamectl || true
            echo
            echo "-- listening before --"
            ss -tulpen || true
            echo
            echo "-- ufw before --"
            ufw status verbose 2>/dev/null || true
            echo
            echo "-- existing x-ui --"
            systemctl status x-ui --no-pager 2>/dev/null || true
            ls -la /usr/local/x-ui /etc/x-ui 2>/dev/null || true
            """
        )

    def install_script(self) -> str:
        answers = f"y\n{self.config.panel_port}\n2\n\n80\n"
        answers_b64 = b64_text(answers)
        return textwrap.dedent(
            f"""
            set -e
            export DEBIAN_FRONTEND=noninteractive
            export NEEDRESTART_MODE=l
            TS="$(date +%Y%m%d_%H%M%S)"
            if [ -d /etc/x-ui ]; then
                cp -a /etc/x-ui "/root/x-ui-backup-${{TS}}"
                echo "旧 /etc/x-ui 已备份到 /root/x-ui-backup-${{TS}}"
            fi
            systemctl stop x-ui 2>/dev/null || true
            rm -rf /usr/local/x-ui /etc/x-ui
            apt-get update
            apt-get install -y curl ca-certificates socat ufw sqlite3 openssl jq
            curl -fsSL https://raw.githubusercontent.com/MHSanaei/3x-ui/master/install.sh -o /tmp/3x-ui-install.sh
            printf '%s' '{answers_b64}' | base64 -d | bash /tmp/3x-ui-install.sh
            [ -s /root/cert/ip/fullchain.pem ] || {{ echo "证书文件缺失: /root/cert/ip/fullchain.pem"; exit 12; }}
            [ -s /root/cert/ip/privkey.pem ] || {{ echo "证书私钥缺失: /root/cert/ip/privkey.pem"; exit 13; }}
            """
        )

    def configure_script(self) -> str:
        change_password = "1" if self.config.change_root_password else "0"
        new_password_b64 = b64_text(self.config.new_root_password)
        restrict_panel = "1" if self.config.restrict_panel else "0"
        allowed_ip = self.config.panel_allowed_ip.strip()
        return textwrap.dedent(
            f"""
            set -e
            PANEL_PORT={self.config.panel_port}
            SUB_PORT={self.config.sub_port}
            INBOUND_PORT={self.config.inbound_port}
            CHANGE_ROOT_PASSWORD={change_password}
            NEW_ROOT_PASSWORD_B64='{new_password_b64}'
            RESTRICT_PANEL={restrict_panel}
            PANEL_ALLOWED_IP={shlex.quote(allowed_ip)}
            DB=/etc/x-ui/x-ui.db

            KEYS=$(/usr/local/x-ui/bin/xray-linux-amd64 x25519)
            PRIVATE_KEY=$(printf '%s\\n' "$KEYS" | awk -F': ' '/PrivateKey/ {{print $2}}')
            PUBLIC_KEY=$(printf '%s\\n' "$KEYS" | awk -F': ' '/Password \\(PublicKey\\)|PublicKey/ {{print $2}}' | tail -n 1)
            UUID=$(/usr/local/x-ui/bin/xray-linux-amd64 uuid)
            SHORT_ID=$(openssl rand -hex 8)
            SUBID=$(openssl rand -hex 12)

            [ -n "$PRIVATE_KEY" ] || {{ echo "生成 Reality PrivateKey 失败"; exit 20; }}
            [ -n "$PUBLIC_KEY" ] || {{ echo "生成 Reality PublicKey 失败"; exit 21; }}
            [ -n "$UUID" ] || {{ echo "生成 UUID 失败"; exit 22; }}

            INBOUND_SETTINGS=$(jq -cn --arg uuid "$UUID" --arg subid "$SUBID" '{{clients:[{{email:"",enable:true,expiryTime:0,flow:"xtls-rprx-vision",id:$uuid,limitIp:0,reset:0,subId:$subid,tgId:"",totalGB:0}}],decryption:"none",fallbacks:[]}}')
            STREAM_SETTINGS=$(jq -cn --arg privateKey "$PRIVATE_KEY" --arg publicKey "$PUBLIC_KEY" --arg shortId "$SHORT_ID" '{{network:"tcp",security:"reality",externalProxy:[],realitySettings:{{show:false,xver:0,dest:"www.cloudflare.com:443",serverNames:["www.cloudflare.com"],privateKey:$privateKey,minClient:"",maxClient:"",maxTimediff:0,shortIds:[$shortId],settings:{{publicKey:$publicKey,fingerprint:"chrome",serverName:"www.cloudflare.com",spiderX:"/"}}}},tcpSettings:{{acceptProxyProtocol:false,header:{{type:"none"}}}}}}')
            SNIFFING=$(jq -cn '{{enabled:true,destOverride:["http","tls","quic","fakedns"],metadataOnly:false,routeOnly:false}}')
            IN_ESC=$(printf '%s' "$INBOUND_SETTINGS" | sed "s/'/''/g")
            ST_ESC=$(printf '%s' "$STREAM_SETTINGS" | sed "s/'/''/g")
            SN_ESC=$(printf '%s' "$SNIFFING" | sed "s/'/''/g")

            sqlite3 "$DB" <<SQL
            BEGIN;
            DELETE FROM client_traffics WHERE inbound_id IN (SELECT id FROM inbounds WHERE tag='inbound-443' OR port=$INBOUND_PORT);
            DELETE FROM inbounds WHERE tag='inbound-443' OR port=$INBOUND_PORT;
            INSERT INTO inbounds (user_id, up, down, total, all_time, remark, enable, expiry_time, traffic_reset, last_traffic_reset_time, listen, port, protocol, settings, stream_settings, tag, sniffing)
            VALUES (1, 0, 0, 0, 0, '🇺🇸 美国', 1, 0, 'never', 0, '', $INBOUND_PORT, 'vless', '$IN_ESC', '$ST_ESC', 'inbound-443', '$SN_ESC');
            INSERT OR REPLACE INTO client_traffics (inbound_id, enable, email, up, down, all_time, expiry_time, total, reset, last_online)
            VALUES ((SELECT id FROM inbounds WHERE tag='inbound-443'), 1, '', 0, 0, 0, 0, 536870912000, 0, 0);
            DELETE FROM settings WHERE key IN ('subEnable','subPort','subPath','subCertFile','subKeyFile','subEncrypt','subShowInfo','subUpdates','subClashEnable','subClashPath','remarkModel');
            INSERT OR REPLACE INTO settings (key, value) VALUES ('subEnable','true');
            INSERT OR REPLACE INTO settings (key, value) VALUES ('subPort','$SUB_PORT');
            INSERT OR REPLACE INTO settings (key, value) VALUES ('subPath','/sub/');
            INSERT OR REPLACE INTO settings (key, value) VALUES ('subCertFile','/root/cert/ip/fullchain.pem');
            INSERT OR REPLACE INTO settings (key, value) VALUES ('subKeyFile','/root/cert/ip/privkey.pem');
            INSERT OR REPLACE INTO settings (key, value) VALUES ('subEncrypt','true');
            INSERT OR REPLACE INTO settings (key, value) VALUES ('subShowInfo','false');
            INSERT OR REPLACE INTO settings (key, value) VALUES ('subUpdates','12');
            INSERT OR REPLACE INTO settings (key, value) VALUES ('subClashEnable','true');
            INSERT OR REPLACE INTO settings (key, value) VALUES ('subClashPath','/clash/');
            INSERT OR REPLACE INTO settings (key, value) VALUES ('remarkModel','-ieo');
            COMMIT;
SQL

            printf '%s\\n' 'net.core.default_qdisc=fq' 'net.ipv4.tcp_congestion_control=bbr' > /etc/sysctl.d/99-bbr.conf
            echo tcp_bbr > /etc/modules-load.d/bbr.conf
            modprobe tcp_bbr || true
            sysctl --system >/dev/null || true

            ufw --force reset
            ufw default deny incoming
            ufw default allow outgoing
            ufw allow 22/tcp
            ufw allow 80/tcp
            ufw allow "$INBOUND_PORT"/tcp
            ufw allow "$SUB_PORT"/tcp
            if [ "$RESTRICT_PANEL" = "1" ] && [ -n "$PANEL_ALLOWED_IP" ]; then
                ufw allow from "$PANEL_ALLOWED_IP" to any port "$PANEL_PORT" proto tcp
                echo "面板端口仅允许 $PANEL_ALLOWED_IP 访问"
            else
                ufw allow "$PANEL_PORT"/tcp
            fi
            ufw --force enable

            systemctl restart x-ui
            sleep 2

            if [ "$CHANGE_ROOT_PASSWORD" = "1" ]; then
                NEW_PASS=$(printf '%s' "$NEW_ROOT_PASSWORD_B64" | base64 -d)
                printf 'root:%s\\n' "$NEW_PASS" | chpasswd
                echo "root 密码已按界面输入更新"
            fi

            echo "DEPLOYED_PARAMS_BEGIN"
            echo "UUID=$UUID"
            echo "PRIVATE_KEY=$PRIVATE_KEY"
            echo "PUBLIC_KEY=$PUBLIC_KEY"
            echo "SHORT_ID=$SHORT_ID"
            echo "SUBID=$SUBID"
            echo "DEPLOYED_PARAMS_END"
            """
        )

    def verify_script(self) -> str:
        return textwrap.dedent(
            f"""
            set -e
            SERVER_IP={shlex.quote(self.config.ip)}
            PANEL_PORT={self.config.panel_port}
            SUB_PORT={self.config.sub_port}
            INBOUND_PORT={self.config.inbound_port}
            SUBID=$(sqlite3 -noheader /etc/x-ui/x-ui.db "select json_extract(settings,'$.clients[0].subId') from inbounds where tag='inbound-443';")

            echo "-- x-ui status --"
            systemctl status x-ui --no-pager | sed -n '1,90p'
            systemctl is-active --quiet x-ui

            echo
            echo "-- listening --"
            ss -tulpen | sed -n '1,180p'
            ss -tulpen | grep -q ":$INBOUND_PORT "
            ss -tulpen | grep -q ":$SUB_PORT "
            ss -tulpen | grep -q ":$PANEL_PORT "

            echo
            echo "-- ufw --"
            ufw status verbose

            echo
            echo "-- bbr --"
            sysctl net.ipv4.tcp_congestion_control net.core.default_qdisc
            lsmod | grep bbr

            echo
            echo "-- clash subscription --"
            curl -k -fsS --max-time 12 "https://$SERVER_IP:$SUB_PORT/clash/$SUBID" | sed -n '1,80p'

            echo
            echo "-- shadowrocket subscription --"
            curl -k -fsS --max-time 12 "https://$SERVER_IP:$SUB_PORT/sub/$SUBID" | sed -n '1,12p'

            echo
            echo "-- x-ui settings --"
            /usr/local/x-ui/x-ui setting -show true || true
            /usr/local/x-ui/x-ui setting -getCert true || true

            echo
            echo "-- acme --"
            crontab -l 2>/dev/null || true
            /root/.acme.sh/acme.sh --list 2>/dev/null || true

            echo
            echo "-- cert --"
            openssl x509 -in /root/cert/ip/fullchain.pem -noout -subject -issuer -dates -ext subjectAltName

            echo
            echo "-- apt/reboot --"
            [ -f /var/run/reboot-required ] && cat /var/run/reboot-required || echo no-reboot-required
            apt list --upgradable 2>/dev/null | tail -n +2 | wc -l
            """
        )

    def check_public_ports(self) -> None:
        self.log("\n========== 本机公网端口连通性检查 ==========\n")
        for port in (22, self.config.inbound_port, self.config.sub_port, self.config.panel_port):
            ok = False
            err = ""
            try:
                with socket.create_connection((self.config.ip, port), timeout=6):
                    ok = True
            except OSError as exc:
                err = str(exc)
            status = "可达" if ok else f"不可达: {err}"
            self.log(f"{port}/tcp: {status}\n")
        self.log("80/tcp 平时可能没有常驻监听；证书续期时 acme.sh 会临时占用。\n")

    def build_result(
        self,
        baseline: str,
        install_info: dict[str, str],
        config_output: str,
        verify_output: str,
    ) -> DeployResult:
        clean_config = strip_ansi(config_output)
        clean_verify = strip_ansi(verify_output)

        uuid = extract_value(clean_config, "UUID")
        public_key = extract_value(clean_config, "PUBLIC_KEY")
        private_key = extract_value(clean_config, "PRIVATE_KEY")
        short_id = extract_value(clean_config, "SHORT_ID")
        sub_id = extract_value(clean_config, "SUBID")
        if not all((uuid, public_key, private_key, short_id, sub_id)):
            raise RemoteError("部署参数解析失败，无法生成订阅链接。")

        web_base_path = install_info["web_base_path"].strip("/")
        panel_url = install_info.get("panel_url") or (
            f"https://{self.config.ip}:{self.config.panel_port}/{web_base_path}/"
        )
        if not panel_url.endswith("/"):
            panel_url += "/"

        cert_summary = self.extract_section(clean_verify, "-- cert --", "-- apt/reboot --")
        acme_summary = self.extract_section(clean_verify, "-- acme --", "-- cert --")
        ufw_summary = self.extract_section(clean_verify, "-- ufw --", "-- bbr --")
        bbr_summary = self.extract_section(clean_verify, "-- bbr --", "-- clash subscription --")

        ssh_password = self.config.ssh_password
        if self.config.change_root_password:
            ssh_password = self.config.new_root_password
        if not self.config.write_ssh_password:
            ssh_password = "未写入本地记录"

        return DeployResult(
            ip=self.config.ip,
            ssh_user=self.config.ssh_user,
            ssh_password_for_report=ssh_password,
            panel_url=panel_url,
            panel_username=install_info["panel_username"],
            panel_password=install_info["panel_password"],
            web_base_path=web_base_path,
            clash_url=f"https://{self.config.ip}:{self.config.sub_port}/clash/{sub_id}",
            shadowrocket_url=f"https://{self.config.ip}:{self.config.sub_port}/sub/{sub_id}",
            uuid=uuid,
            public_key=public_key,
            private_key=private_key,
            short_id=short_id,
            sub_id=sub_id,
            panel_port=self.config.panel_port,
            sub_port=self.config.sub_port,
            inbound_port=self.config.inbound_port,
            cert_summary=cert_summary.strip(),
            acme_summary=acme_summary.strip(),
            ufw_summary=ufw_summary.strip(),
            bbr_summary=bbr_summary.strip(),
            report_path="",
        )

    @staticmethod
    def extract_section(text: str, start_marker: str, end_marker: str) -> str:
        start = text.find(start_marker)
        if start == -1:
            return ""
        start += len(start_marker)
        end = text.find(end_marker, start)
        if end == -1:
            end = len(text)
        return text[start:end]

    def write_report(self, result: DeployResult) -> Path:
        records_dir = Path.cwd() / "deployment_records"
        records_dir.mkdir(exist_ok=True)
        path = records_dir / f"vps-{safe_filename_ip(result.ip)}-deployment.md"
        password_note = (
            result.ssh_password_for_report
            if result.ssh_password_for_report != "未写入本地记录"
            else "未写入本地记录（界面未勾选保存 SSH 密码）"
        )
        content = f"""# VPS 部署记录：{result.ip}

> {DISCLAIMER}
> 作者：{AUTHOR}

## 一、机器基础信息

```text
服务器 IP: {result.ip}
SSH 用户: {result.ssh_user}
SSH 密码: {password_note}
部署工具作者: {AUTHOR}
记录生成时间: {now_stamp()}
```

## 二、3x-ui 面板信息

```text
面板地址: {result.panel_url}
面板端口: {result.panel_port}
用户名: {result.panel_username}
密码: {result.panel_password}
WebBasePath: /{result.web_base_path}/
```

## 三、订阅链接

```text
Clash Verge:
{result.clash_url}

Shadowrocket:
{result.shadowrocket_url}
```

## 四、主节点参数

```text
协议: VLESS
地址: {result.ip}
端口: {result.inbound_port}
传输: tcp
安全: reality
Flow: xtls-rprx-vision
UUID: {result.uuid}
SNI: www.cloudflare.com
伪装目标: www.cloudflare.com:443
Fingerprint: chrome
PublicKey: {result.public_key}
ShortId: {result.short_id}
Reality PrivateKey（服务器端恢复用）: {result.private_key}
```

协议功能说明：

1. `VLESS` 负责客户端身份与节点参数。
2. `TCP` 是当前传输层，默认使用节点端口 `{result.inbound_port}`。
3. `REALITY` 负责握手与服务端安全配置；节点入站不需要绑定域名证书，适合只有 VPS IP 的部署场景。
4. `xtls-rprx-vision` 是客户端 Flow，用于优化 XTLS 数据流。
5. 当前方案固定使用 `443/tcp`，客户端兼容性较好，Clash Verge 与 Shadowrocket 都能通过订阅导入。
6. 每次部署都会重新生成 UUID、Reality key、ShortId 和 SubId，不复用旧机器参数。
7. 面板和订阅服务继续使用 IP 证书 HTTPS，便于管理、导入和后续续期检查。

## 五、端口与防火墙

```text
22/tcp     SSH
80/tcp     证书申请/续期验证
{result.inbound_port}/tcp    Xray VLESS Reality 主入站
{result.sub_port}/tcp   3x-ui 订阅服务 HTTPS
{result.panel_port}/tcp  3x-ui 管理面板 HTTPS
```

```text
{result.ufw_summary}
```

## 六、BBR 状态

```text
{result.bbr_summary}
```

## 七、证书与续期

```text
{result.acme_summary}

{result.cert_summary}
```

## 八、部署流程摘要

1. SSH 登录目标 VPS。
2. 备份旧 `/etc/x-ui` 到 `/root/x-ui-backup-<timestamp>`，然后覆盖安装 3x-ui。
3. 申请 Let's Encrypt IP 证书并配置面板/订阅 HTTPS。
4. 创建 `VLESS + TCP + REALITY + xtls-rprx-vision` 入站。
5. 开启 Clash 和普通订阅。
6. 开启 `bbr + fq`。
7. 配置 UFW 放行 `22/80/{result.inbound_port}/{result.sub_port}/{result.panel_port}`。
8. 验证 x-ui、Xray、订阅、证书、BBR 和防火墙状态。

## 九、后续安全建议

1. 更换 SSH root 密码，或改用 SSH key 登录。
2. 登录 3x-ui 后更换面板密码，并开启二次验证。
3. 如果不需要公网访问面板，限制 `{result.panel_port}/tcp` 只允许固定 IP。
4. 不要公开发送本文件；其中包含面板密码和节点密钥。
5. 证书续期依赖 `80/tcp` 在续期时可用，云服务商安全组也应允许 `80/tcp` 入站。
"""
        path.write_text(content, encoding="utf-8")
        self.log(f"\n部署记录已保存: {path}\n")
        return path


class DeployWorker(QThread):
    log_message = pyqtSignal(str)
    deploy_success = pyqtSignal(dict)
    deploy_failed = pyqtSignal(str)

    def __init__(self, config: DeployConfig):
        super().__init__()
        self.config = config

    def run(self) -> None:
        deployer = RemoteDeployer(self.config, self.log_message.emit)
        try:
            result = deployer.deploy()
        except Exception as exc:
            self.deploy_failed.emit(str(exc))
            return
        self.deploy_success.emit(result.__dict__)


class CopyLine(QWidget):
    def __init__(self, label: str, parent: QWidget | None = None):
        super().__init__(parent)
        title = QLabel(label)
        title.setObjectName("resultLabel")
        title.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.edit = QLineEdit()
        self.edit.setReadOnly(True)
        self.edit.setMinimumHeight(36)
        self.button = QPushButton("复制")
        self.button.setFixedWidth(70)
        self.button.setMinimumHeight(36)
        self.button.clicked.connect(self.copy_text)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        row.addWidget(self.edit, 1)
        row.addWidget(self.button, 0)
        layout.addWidget(title, 0)
        layout.addLayout(row, 0)

    def set_text(self, text: str) -> None:
        self.edit.setText(text)

    def copy_text(self) -> None:
        QApplication.clipboard().setText(self.edit.text())


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.worker: DeployWorker | None = None
        self.setWindowTitle(APP_TITLE)
        self.resize(1360, 940)
        self.setMinimumSize(1180, 780)
        self.apply_style()
        self.setup_ui()

    def setup_ui(self) -> None:
        root = QWidget()
        self.setCentralWidget(root)
        main = QVBoxLayout(root)
        main.setContentsMargins(22, 18, 22, 18)
        main.setSpacing(10)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        title = QLabel(APP_TITLE)
        title.setObjectName("titleLabel")
        author = QLabel(f"作者：{AUTHOR}")
        author.setObjectName("authorLabel")
        author.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        header.addWidget(title, 1)
        header.addWidget(author, 0)
        subtitle = QLabel(DISCLAIMER)
        subtitle.setWordWrap(True)
        subtitle.setObjectName("subtitleLabel")
        main.addLayout(header)
        main.addWidget(subtitle)

        top_grid = QGridLayout()
        top_grid.setSpacing(12)
        top_grid.addWidget(self.build_connection_box(), 0, 0)
        top_grid.addWidget(self.build_options_box(), 0, 1)
        top_grid.addWidget(self.build_protocol_info_box(), 0, 2)
        top_grid.setColumnStretch(0, 1)
        top_grid.setColumnStretch(1, 1)
        top_grid.setColumnStretch(2, 1)
        main.addLayout(top_grid)

        self.auth_check = QCheckBox("我确认此 VPS 由我本人拥有或已获授权管理，并承诺仅用于合规学习和运维用途。")
        self.auth_check.stateChanged.connect(self.update_start_enabled)

        actions = QHBoxLayout()
        actions.setContentsMargins(0, 2, 0, 2)
        actions.setSpacing(12)
        self.start_button = QPushButton("开始部署")
        self.start_button.setObjectName("primaryButton")
        self.start_button.clicked.connect(self.start_deploy)
        self.start_button.setEnabled(False)
        self.progress = QProgressBar()
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        self.progress.setMaximumWidth(220)
        self.progress.hide()
        actions.addWidget(self.auth_check, 1)
        actions.addWidget(self.start_button, 0)
        actions.addWidget(self.progress, 0)
        main.addLayout(actions)

        console_box = QGroupBox("实时控制台")
        console_layout = QVBoxLayout(console_box)
        console_layout.setContentsMargins(16, 18, 16, 16)
        self.console = QTextEdit()
        self.console.setReadOnly(True)
        self.console.setFont(QFont("Consolas", 10))
        self.console.setMinimumHeight(340)
        console_layout.addWidget(self.console)

        result_box = QGroupBox("部署结果")
        result_layout = QVBoxLayout(result_box)
        result_layout.setContentsMargins(16, 18, 16, 16)
        result_layout.setSpacing(10)
        result_box.setMinimumWidth(460)
        result_box.setMaximumWidth(580)
        self.panel_line = CopyLine("面板")
        self.clash_line = CopyLine("Clash Verge")
        self.shadow_line = CopyLine("Shadowrocket")
        self.report_line = CopyLine("记录文件")
        result_layout.addWidget(self.panel_line)
        result_layout.addWidget(self.clash_line)
        result_layout.addWidget(self.shadow_line)
        result_layout.addWidget(self.report_line)
        result_layout.addStretch(1)

        lower_splitter = QSplitter(Qt.Orientation.Horizontal)
        lower_splitter.setChildrenCollapsible(False)
        lower_splitter.addWidget(console_box)
        lower_splitter.addWidget(result_box)
        lower_splitter.setStretchFactor(0, 3)
        lower_splitter.setStretchFactor(1, 1)
        lower_splitter.setSizes([760, 500])
        main.addWidget(lower_splitter, 1)

    def build_protocol_info_box(self) -> QGroupBox:
        box = QGroupBox("当前协议功能说明")
        layout = QVBoxLayout(box)
        layout.setContentsMargins(16, 18, 16, 14)
        text = QLabel(
            "默认部署协议为 VLESS + TCP + REALITY + xtls-rprx-vision。"
            "优势：节点入站不依赖域名证书，适合只有 VPS IP 的机器；"
            "固定走 443/tcp，客户端兼容性好；每次部署都会重新生成 UUID、Reality key、ShortId 和 SubId；"
            "同时保留 3x-ui 面板、HTTPS 订阅、BBR、UFW 和证书续期检查，方便 Clash Verge 与 Shadowrocket 直接导入。"
        )
        text.setWordWrap(True)
        text.setObjectName("protocolText")
        layout.addWidget(text)
        return box

    def build_connection_box(self) -> QGroupBox:
        box = QGroupBox("连接与端口")
        layout = QFormLayout(box)
        layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        layout.setHorizontalSpacing(12)
        layout.setVerticalSpacing(10)

        self.ip_edit = QLineEdit()
        self.ip_edit.setPlaceholderText("192.220.xxx.xxx")
        self.user_edit = QLineEdit("root")
        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_edit.setPlaceholderText("root 密码")
        self.panel_port = self.port_edit(32105)
        self.sub_port = self.port_edit(2096)
        self.inbound_port = self.port_edit(443)
        for field in (
            self.ip_edit,
            self.user_edit,
            self.password_edit,
            self.panel_port,
            self.sub_port,
            self.inbound_port,
        ):
            field.setMinimumHeight(34)

        self.ip_edit.textChanged.connect(self.update_start_enabled)
        self.password_edit.textChanged.connect(self.update_start_enabled)
        self.panel_port.textChanged.connect(self.update_start_enabled)
        self.sub_port.textChanged.connect(self.update_start_enabled)
        self.inbound_port.textChanged.connect(self.update_start_enabled)

        layout.addRow("VPS IP", self.ip_edit)
        layout.addRow("SSH 用户", self.user_edit)
        layout.addRow("SSH 密码", self.password_edit)
        layout.addRow("面板端口", self.panel_port)
        layout.addRow("订阅端口", self.sub_port)
        layout.addRow("节点端口", self.inbound_port)
        return box

    def build_options_box(self) -> QGroupBox:
        box = QGroupBox("安全与记录选项")
        layout = QFormLayout(box)
        layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        layout.setHorizontalSpacing(12)
        layout.setVerticalSpacing(10)

        self.write_ssh_password = QCheckBox("把 SSH 密码写入 Markdown 记录")
        self.change_root_password = QCheckBox("部署后更换 root 密码")
        self.new_root_password = QLineEdit()
        self.new_root_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.new_root_password.setEnabled(False)
        self.new_root_password.setPlaceholderText("新 root 密码")
        self.restrict_panel = QCheckBox("限制面板端口只允许指定 IP 访问")
        self.panel_allowed_ip = QLineEdit()
        self.panel_allowed_ip.setEnabled(False)
        self.panel_allowed_ip.setPlaceholderText("你的固定公网 IP")
        for field in (self.new_root_password, self.panel_allowed_ip):
            field.setMinimumHeight(34)
        for check in (self.write_ssh_password, self.change_root_password, self.restrict_panel):
            check.setMinimumHeight(28)

        self.change_root_password.stateChanged.connect(
            lambda state: self.new_root_password.setEnabled(state == Qt.CheckState.Checked.value)
        )
        self.restrict_panel.stateChanged.connect(
            lambda state: self.panel_allowed_ip.setEnabled(state == Qt.CheckState.Checked.value)
        )
        self.change_root_password.stateChanged.connect(self.update_start_enabled)
        self.new_root_password.textChanged.connect(self.update_start_enabled)
        self.restrict_panel.stateChanged.connect(self.update_start_enabled)
        self.panel_allowed_ip.textChanged.connect(self.update_start_enabled)

        layout.addRow(self.write_ssh_password)
        layout.addRow(self.change_root_password)
        layout.addRow("新密码", self.new_root_password)
        layout.addRow(self.restrict_panel)
        layout.addRow("允许 IP", self.panel_allowed_ip)
        note = QLabel("默认不强制加固；如限制面板端口，请确保填写的是你当前可用的固定公网 IP。")
        note.setWordWrap(True)
        note.setObjectName("hintLabel")
        layout.addRow(note)
        return box

    @staticmethod
    def port_edit(default: int) -> QLineEdit:
        edit = QLineEdit(str(default))
        edit.setValidator(QIntValidator(1, 65535, edit))
        edit.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        return edit

    @staticmethod
    def read_port(edit: QLineEdit) -> int:
        text = edit.text().strip()
        if not text:
            return 0
        return int(text)

    def update_start_enabled(self) -> None:
        ok = bool(self.ip_edit.text().strip()) and bool(self.password_edit.text())
        ok = ok and self.auth_check.isChecked()
        if self.change_root_password.isChecked() and not self.new_root_password.text():
            ok = False
        if self.restrict_panel.isChecked() and not self.panel_allowed_ip.text().strip():
            ok = False
        self.start_button.setEnabled(ok and self.worker is None)

    def validate_config(self) -> DeployConfig | None:
        ip = self.ip_edit.text().strip()
        if not IP_RE.match(ip):
            QMessageBox.warning(self, "输入错误", "请输入有效的 IPv4 地址。")
            return None
        allowed_ip = self.panel_allowed_ip.text().strip()
        if self.restrict_panel.isChecked() and not IP_RE.match(allowed_ip):
            QMessageBox.warning(self, "输入错误", "限制面板访问时，请填写有效的 IPv4 地址。")
            return None
        ports = [
            self.read_port(self.panel_port),
            self.read_port(self.sub_port),
            self.read_port(self.inbound_port),
        ]
        if any(port < 1 or port > 65535 for port in ports):
            QMessageBox.warning(self, "输入错误", "端口必须是 1 到 65535 之间的数字。")
            return None
        if len(set(ports)) != len(ports):
            QMessageBox.warning(self, "输入错误", "面板端口、订阅端口、节点端口不能重复。")
            return None
        return DeployConfig(
            ip=ip,
            ssh_user=self.user_edit.text().strip() or "root",
            ssh_password=self.password_edit.text(),
            panel_port=self.read_port(self.panel_port),
            sub_port=self.read_port(self.sub_port),
            inbound_port=self.read_port(self.inbound_port),
            write_ssh_password=self.write_ssh_password.isChecked(),
            change_root_password=self.change_root_password.isChecked(),
            new_root_password=self.new_root_password.text(),
            restrict_panel=self.restrict_panel.isChecked(),
            panel_allowed_ip=allowed_ip,
        )

    def start_deploy(self) -> None:
        config = self.validate_config()
        if config is None:
            return
        self.console.clear()
        self.panel_line.set_text("")
        self.clash_line.set_text("")
        self.shadow_line.set_text("")
        self.report_line.set_text("")
        self.start_button.setEnabled(False)
        self.progress.show()
        self.progress.setRange(0, 0)

        self.worker = DeployWorker(config)
        self.worker.log_message.connect(self.append_log)
        self.worker.deploy_success.connect(self.on_success)
        self.worker.deploy_failed.connect(self.on_failed)
        self.worker.finished.connect(self.on_worker_finished)
        self.worker.start()

    def append_log(self, text: str) -> None:
        self.console.moveCursor(QTextCursor.MoveOperation.End)
        self.console.insertPlainText(text)
        self.console.moveCursor(QTextCursor.MoveOperation.End)

    def on_success(self, data: dict) -> None:
        self.panel_line.set_text(data["panel_url"])
        self.clash_line.set_text(data["clash_url"])
        self.shadow_line.set_text(data["shadowrocket_url"])
        self.report_line.set_text(data["report_path"])
        QMessageBox.information(self, "部署完成", "部署完成，订阅链接和记录文件已生成。")

    def on_failed(self, message: str) -> None:
        self.append_log(f"\n部署失败: {message}\n")
        QMessageBox.critical(self, "部署失败", message)

    def on_worker_finished(self) -> None:
        self.worker = None
        self.progress.hide()
        self.progress.setRange(0, 1)
        self.update_start_enabled()

    def apply_style(self) -> None:
        self.setStyleSheet(
            """
            QWidget {
                font-family: "Microsoft YaHei UI", "Segoe UI", sans-serif;
                font-size: 13px;
                color: #172033;
                background: #f5f7fb;
            }
            #titleLabel {
                font-size: 24px;
                font-weight: 700;
                color: #101828;
                padding-bottom: 2px;
            }
            #authorLabel {
                color: #475467;
                font-weight: 600;
                padding-right: 2px;
            }
            #subtitleLabel {
                color: #475467;
                background: #fff7ed;
                border: 1px solid #fed7aa;
                border-radius: 8px;
                padding: 10px 12px;
            }
            #protocolText {
                color: #344054;
                line-height: 150%;
            }
            #hintLabel {
                color: #667085;
            }
            #resultLabel {
                color: #344054;
                font-weight: 600;
                padding-left: 2px;
            }
            QGroupBox {
                background: #ffffff;
                border: 1px solid #d9e2ec;
                border-radius: 8px;
                margin-top: 12px;
                padding: 12px;
                font-weight: 600;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 12px;
                padding: 0 6px;
                color: #344054;
            }
            QLineEdit, QTextEdit {
                background: #ffffff;
                border: 1px solid #cbd5e1;
                border-radius: 6px;
                min-height: 30px;
                padding: 4px 10px;
                selection-background-color: #2563eb;
                selection-color: #ffffff;
            }
            QTextEdit {
                background: #0f172a;
                color: #d1e7ff;
                border-color: #1e293b;
                padding: 8px;
            }
            QLabel {
                background: transparent;
            }
            QCheckBox {
                background: transparent;
                spacing: 8px;
            }
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
            }
            QPushButton {
                background: #ffffff;
                border: 1px solid #cbd5e1;
                border-radius: 6px;
                min-height: 30px;
                padding: 4px 14px;
            }
            QPushButton:hover {
                background: #eef4ff;
            }
            QPushButton:disabled {
                color: #98a2b3;
                background: #f2f4f7;
            }
            #primaryButton {
                background: #2563eb;
                color: #ffffff;
                border-color: #2563eb;
                font-weight: 700;
                min-width: 120px;
            }
            #primaryButton:hover {
                background: #1d4ed8;
            }
            QProgressBar {
                border: 1px solid #cbd5e1;
                border-radius: 6px;
                background: #ffffff;
                min-height: 18px;
            }
            QProgressBar::chunk {
                background: #2563eb;
                border-radius: 5px;
            }
            """
        )


def self_test() -> int:
    print(f"PyQt6 ok: {QApplication is not None}")
    print(f"paramiko ok: {paramiko.__version__}")
    print("self-test ok")
    return 0


def main() -> int:
    if "--self-test" in sys.argv:
        return self_test()
    os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
