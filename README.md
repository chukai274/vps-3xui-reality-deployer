# VPS 3x-ui Reality Deployer

涓€娆?Windows 鏈湴 PyQt6 宸ュ叿锛岀敤浜庡湪**宸叉巿鏉?*鐨?VPS 涓婅嚜鍔ㄩ儴缃?3x-ui锛岄厤缃?`VLESS + TCP + REALITY + xtls-rprx-vision`锛屽紑鍚?`BBR / UFW`锛屽苟鐢熸垚 Clash Verge / Shadowrocket 璁㈤槄閾炬帴涓?Markdown 璁板綍銆?

> 浠呬緵瀛︿範鍙傝€冦€備粎闄愪綘鏈汉鎷ユ湁鎴栬鏄庣‘鎺堟潈绠＄悊鐨?VPS銆傝閬靛畧鎵€鍦ㄥ湴娉曞緥娉曡銆佷簯鏈嶅姟鍟嗘潯娆句笌缃戠粶浣跨敤瑙勮寖锛屼笉寰楃敤浜庤繚娉曡繚瑙勭敤閫斻€?

## 涓昏鍔熻兘

- 鍚庡彴绾跨▼閮ㄧ讲锛岀晫闈笉浼氬崱姝?
- SSH 涓€閿繛鎺ュ崟鍙?VPS
- 鑷姩瀹夎鎴栬鐩栭儴缃?3x-ui
- 鑷姩鐢熸垚鑺傜偣銆佽闃呭拰閮ㄧ讲璁板綍
- 鍚敤 `BBR + fq`
- 閰嶇疆 `UFW`
- 鍙€夊啓鍏?SSH 瀵嗙爜銆佷慨鏀?root 瀵嗙爜銆侀檺鍒堕潰鏉挎潵婧?IP

## 鐣岄潰棰勮

![閮ㄧ讲鐣岄潰](assets/ui_review_2026-05-24.png)

## 蹇€熶笂鎵?

1. 鍦?`VPS IP` 濉洰鏍囨満鍏綉 IPv4銆?
2. `SSH 鐢ㄦ埛` 榛樿鏄?`root`锛岃緭鍏ュ疄渚嬪瘑鐮併€?
3. 绔彛涓€鑸繚鎸侀粯璁わ細`32105 / 2096 / 443`銆?
4. 鍕鹃€夋巿鏉冪‘璁ゃ€?
5. 鐐瑰嚮 `寮€濮嬮儴缃瞏锛岀瓑寰呮棩蹇楀畬鎴愩€?
6. 閮ㄧ讲缁撴潫鍚庡鍒堕潰鏉垮湴鍧€鍜岃闃呴摼鎺ワ紝璁板綍鏂囦欢浼氳嚜鍔ㄧ敓鎴愩€?

### 瀛楁璇存槑

| 瀛楁 | 璇存槑 |
| --- | --- |
| `VPS IP` | 鐩爣 VPS 鐨勫叕缃?IPv4 |
| `SSH 鐢ㄦ埛` | 榛樿 `root` |
| `SSH 瀵嗙爜` | 瀹炰緥鎺у埗鍙扮粰鍑虹殑瀵嗙爜 |
| `闈㈡澘绔彛` | 3x-ui 绠＄悊闈㈡澘 HTTPS 绔彛 |
| `璁㈤槄绔彛` | Clash / Shadowrocket 璁㈤槄绔彛 |
| `鑺傜偣绔彛` | VLESS Reality 鍏ョ珯绔彛锛岄粯璁?`443` |

## 杈撳嚭鍐呭

- 3x-ui 闈㈡澘鍦板潃銆佽处鍙峰拰瀵嗙爜
- Clash Verge 璁㈤槄閾炬帴
- Shadowrocket 璁㈤槄閾炬帴
- Markdown 閮ㄧ讲璁板綍锛歚deployment_records/vps-<ip>-deployment.md`

## 鎶€鏈鏄?

- 鍗忚锛歚VLESS + TCP + REALITY + xtls-rprx-vision`
- 鑺傜偣鍙傛暟锛歚UUID`銆乣Reality key`銆乣ShortId`銆乣SubId` 姣忔閲嶆柊鐢熸垚
- 璇佷功锛欼P 璇佷功
- 绯荤粺浼樺寲锛歚BBR + fq`
- 闃茬伀澧欙細UFW 鏀捐 `22 / 80 / 443 / 2096 / 32105`

## 鏁欑▼

1. 濉啓 VPS 鐨?IP 鍜?SSH 瀵嗙爜銆?
2. 纭绔彛閰嶇疆鏃犺锛岄€氬父鐩存帴淇濇寔榛樿鍊笺€?
3. 鍕鹃€夆€滄垜纭姝?VPS...鈥濈殑鎺堟潈椤广€?
4. 鐐瑰嚮 `寮€濮嬮儴缃瞏銆?
5. 绛夊緟瀹炴椂鎺у埗鍙拌緭鍑哄畬鎴愰儴缃层€侀獙璇佸拰璁板綍鍐欏叆銆?
6. 澶嶅埗缁撴灉鍖洪噷鐨勯潰鏉裤€丆lash Verge 鍜?Shadowrocket 閾炬帴銆?

## 閫夊瀷鍙傝€?

濡傛灉浣犲湪鎵惧悎閫傜殑 VPS锛屽彲浠ュ弬鑰冭繖涓帹骞垮叆鍙ｏ細

[NovixLink 鎺ㄨ崘鍏ュ彛](https://novixlink.com/aff.php?aff=84)

璇存槑锛氳繖鏄甫鎺ㄥ箍鍙傛暟鐨勯摼鎺ワ紝鐢ㄤ簬鏀寔椤圭洰缁存姢銆?

鏍规嵁瀹樼綉褰撳墠淇℃伅锛孨ovixLink 涓绘墦缇庡浗 ISP 浣忓畢 IP VPS銆丅GP 鍥介檯绾胯矾 VPS 鍜?IDC 鏈烘埧 VPS锛岄〉闈㈠己璋?`Tier-1` 缃戠粶銆佸師鐢熶綇瀹?IP銆乣NVMe` 瀛樺偍銆乣KVM` 铏氭嫙鍖栧拰澶氭。浣嶅椁愩€傛洿閫傚悎闇€瑕佹捣澶栫綉缁滆繛閫氭€с€佺ǔ瀹氬叕缃戠幆澧冩垨缇庡浗浣忓畢 IP 鍦烘櫙鐨勭敤鎴枫€傚叿浣撳椁愪笌浠锋牸浠ュ畼缃戝疄鏃堕〉闈负鍑嗐€?

## 鏋勫缓

```bash
pip install -r requirements.txt
pyinstaller VPS_Reality_Deployer.spec
```

## Release

鍙戝竷鐗堟湰浼氶檮甯?Windows 鍗曟枃浠剁▼搴?`VPS_Reality_Deployer.exe`銆?

## 浣滆€?

CraigChu
