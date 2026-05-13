# Wolfx Open API 使用须知

- 感谢您使用 Wolfx Open API！建议您在使用前阅读本页面底部的《隐私政策》和《服务条款》。如有任何疑问，欢迎通过 contact@mtf.edu.kg 与我们联系。

## WebSocket API 使用须知

### WebSocket 简介

- WebSocket API 将在服务端收到EEW后自动向所有客户端推送相关信息
- 心跳包机制：服务端将在每分钟和建立连接后发送一个heartbeat心跳包以保持连接，客户端可选回复ping包（推荐）

### WebSocket 调用地址

- 接收所有 JSON API 推送:`wss://ws-api.wolfx.jp/all_eew`
- 四川地震局 地震预警 JSON API:`wss://ws-api.wolfx.jp/sc_eew`
- JMA 緊急地震速報 JSON API:`wss://ws-api.wolfx.jp/jma_eew`
- 福建地震局 地震预警 JSON API:`wss://ws-api.wolfx.jp/fj_eew`
- 中国地震台网 地震预警 JSON API:`wss://ws-api.wolfx.jp/cenc_eew`
- 中国地震台网 地震信息 JSON API:`wss://ws-api.wolfx.jp/cenc_eqlist`
- JMA 地震情報 JSON API:`wss://ws-api.wolfx.jp/jma_eqlist`
- JSON字段解析详见： [https://api.wolfx.jp](https://api.wolfx.jp/)

### WebSocket 手动查询指令

- Ping:`ping`
- 四川地震局 地震预警 JSON:`query_sceew`
- JMA 緊急地震速報 JSON:`query_jmaeew`
- 福建地震局 地震预警 JSON:`query_fjeew`
- 中国地震台网 地震预警 JSON:`query_cenceew`
- 中国地震台网 地震信息 JSON:`query_cenceqlist`
- JMA 地震情報 JSON:`query_jmaeqlist`

### WebSocket JSON 资料说明

- 共有JSON字段解析:

| type | 资料类型/提供源(对应值详见API主页)(字符串型) |
| --- | --- |

- WebSocket 心跳包JSON字段解析:

| type | heartbeat(字符串型) |
| --- | --- |
| ver | 服务端版本号(数值型) |
| id | 客户端连接UUID(字符串型) |
| timestamp | 心跳包发送毫秒级时间戳(字符串型) |

- WebSocket Pong包JSON字段解析:

| type | pong(字符串型) |
| --- | --- |
| timestamp | Pong包发送毫秒级时间戳(字符串型) |

## JMA 緊急地震速報 JSON API

- 描述: 实时获取日本気象庁发布的緊急地震速報
- HTTP GET API地址:`https://api.wolfx.jp/jma_eew.json`
- WebSocket API地址:`wss://ws-api.wolfx.jp/jma_eew`

- JSON字段解析(数据类型):

| type | jma\_eew(字符串型) |
| --- | --- |
| Title | EEW发报报头(字符串型) |
| CodeType | EEW发报说明(字符串型) |
| Issue.Source | EEW发报机构位置(字符串型) |
| Issue.Status | EEW发报状态(字符串型) |
| EventID | EEW发报ID(字符串型) |
| Serial | EEW发报数(数值型) |
| AnnouncedTime | EEW发报时间(UTC+9)(字符串型) |
| OriginTime | 发震时间(UTC+9)(字符串型) |
| Hypocenter | 震源地(字符串型) |
| Latitude | 震源地纬度(数值型) |
| Longitude | 震源地经度(数值型) |
| Magunitude | 震级(数值型) |
| Depth | 震源深度(数值型) |
| MaxIntensity | 最大震度(弱/強)(字符串型) |
| Accuracy.Epicenter | 震中精度说明(字符串型) |
| Accuracy.Depth | 深度精度说明(字符串型) |
| Accuracy.Magnitude | 震级精度说明(字符串型) |
| MaxIntChange.String | 最大震度变更说明(字符串型) |
| MaxIntChange.Reason | 最大震度变更原因(字符串型) |
| WarnArea.Chiiki | 警报区域(字符串型) |
| WarnArea.Shindo1 | 区域最大震度(弱/強)(字符串型) |
| WarnArea.Shindo2 | 区域最小震度(弱/強)(字符串型) |
| WarnArea.Time | 区域警报时间(字符串型) |
| WarnArea.Type | 区域发报类型，分为 "予報" 和 "警報"(字符串型) |
| WarnArea.Arrive | 区域地震波是否已到达(布尔型) |
| isSea | 是否为海域地震(布尔型) |
| isTraining | 是否为训练报(布尔型) |
| isAssumption | 是否为推定震源(PLUM法)(布尔型) |
| isWarn | 是否为警报(布尔型) |
| isFinal | 是否为最终报(布尔型) |
| isCancel | 是否为取消报(布尔型) |
| OriginalText | JMA气象厅原电文(字符串型) |

## 中国地震台网 地震预警 JSON API

- 描述: 实时获取中国地震台网发布的地震预警
- HTTP GET API地址:`https://api.wolfx.jp/cenc_eew.json`
- WebSocket API地址:`wss://ws-api.wolfx.jp/cenc_eew`

- JSON字段解析(数据类型):

| type | cenc\_eew(字符串型) |
| --- | --- |
| ID | EEW发报ID(字符串型) |
| EventID | EEW发报事件ID(字符串型) |
| ReportTime | EEW发报时间(UTC+8)(字符串型) |
| ReportNum | EEW发报数(数值型) |
| OriginTime | 发震时间(UTC+8)(字符串型) |
| HypoCenter | 震源地(字符串型) |
| Latitude | 震源地纬度(数值型) |
| Longitude | 震源地经度(数值型) |
| Magnitude | 震级(数值型) |
| Depth | 震源深度(可能为null)(数值型) |
| MaxIntensity | 最大烈度(数值型) |

## 中国地震台网 地震信息 JSON API

- 描述: 获取中国地震台网发布的最新地震信息, 共50条
- HTTP GET API地址:`https://api.wolfx.jp/cenc_eqlist.json`
- WebSocket API地址:`wss://ws-api.wolfx.jp/cenc_eqlist`

- JSON字段解析(数据类型):

| type | cenc\_eqlist(字符串型) |
| --- | --- |
| No(1~50) | 地震信息条目数，发布时间顺序(字符串型) |
| type | 信息类型，分为"automatic"和"reviewed"(字符串型) |
| time | 发震时间(UTC+8)(字符串型) |
| location | 震源地(对原数据进行了处理以保证国内地区格式一致性)(字符串型) |
| placeName | 震源地(未对原数据进行修改以保证数据的原始性)(字符串型) |
| magnitude | 震级(字符串型) |
| depth | 震源深度(字符串型) |
| latitude | 震源地纬度(字符串型) |
| longitude | 震源地经度(字符串型) |
| intensity | 最大烈度(字符串型) |
| md5 | 地震信息更新校验码(字符串型) |

## CWA 地震预警 JSON API (仅服务大陆地区)

- 描述: 实时获取CWA发布的地震预警
- HTTP GET API地址:`https://api.wolfx.jp/cwa_eew.json`

- JSON字段解析(数据类型):

| ID | EEW发报ID(数值型) |
| --- | --- |
| ReportTime | EEW发报时间(UTC+8)(字符串型) |
| ReportNum | EEW发报数(数值型) |
| OriginTime | 发震时间(UTC+8)(字符串型) |
| HypoCenter | 震源地(字符串型) |
| Latitude | 震源地纬度(数值型) |
| Longitude | 震源地经度(数值型) |
| Magunitude | 震级(数值型) |
| Depth | 震源深度(数值型) |
| MaxIntensity | 最大震度(弱/強)(字符串型) |

## JMA 地震情報 JSON API

- 描述: 获取日本気象庁发布的最新地震情報, 共50条
- HTTP GET API地址:`https://api.wolfx.jp/jma_eqlist.json`
- WebSocket API地址:`wss://ws-api.wolfx.jp/jma_eqlist`

- JSON字段解析(数据类型):

| type | jma\_eqlist(字符串型) |
| --- | --- |
| Title | 发报报头(字符串型) |
| No(1~50) | 地震情报条目数，发布时间顺序(字符串型) |
| time | 发震时间(UTC+9)(字符串型) |
| location | 震源地(字符串型) |
| magnitude | 震级(字符串型) |
| shindo | 最大震度(-/+)(字符串型) |
| depth | 震源深度(字符串型) |
| latitude | 震源地纬度(字符串型) |
| longitude | 震源地经度(字符串型) |
| info | 津波情报(仅第一条提供)(字符串型) |
| md5 | 地震情报更新校验码(字符串型) |

## 中国气象实况排行 JSON API

- 描述: 提供每小时国家级气象观测站气温、降水、风速实况排行
- HTTP GET API地址:`https://api.wolfx.jp/weather_rank.json`

- JSON字段解析(数据类型):

| YYYYMMDDHH00 | 分别提供最近8小时内的全国气象实况排行(UTC+8)(字符串型) |
| --- | --- |
| tempRank | 气温排行(从高到低10条)(字符串型) |
| rainRank | 降水排行(从高到低10条)(字符串型) |
| windSRank | 风速排行(从高到低10条)(字符串型) |
| md5 | 排行数据更新校验码(字符串型) |

## IP位址资讯查询 JSON API

- 描述: 获取请求方或指定IP位址的相关资讯
- HTTP GET API地址:`https://api.wolfx.jp/geoip.php` `https://api.wolfx.jp/geoip.php?ip=<IP位址>`

- JSON字段解析(数据类型):

| ip | 请求IP(字符串型) |
| --- | --- |
| country\_code | 所在国家或地区缩写(字符串型) |
| country\_name | 所在国家或地区(字符串型) |
| country\_name\_zh | 所在国家或地区(中文)(字符串型) |
| province\_code | 所在省或州代码(字符串型) |
| province\_name | 所在省或州(字符串型) |
| province\_name\_zh | 所在省或州(中文)(字符串型) |
| city | 所在城市(字符串型) |
| city\_zh | 所在城市(中文)(字符串型) |
| latitude | 所在纬度(可能无法获取)(数值型) |
| longitude | 所在经度(可能无法获取)(数值型) |
