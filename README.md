# 🧊 冷库哨兵 · Cold Storage Guardian

低成本冷链温度监控与报警系统，基于 ESP8266 + DS18B20 + Coze + 企业微信。

## 系统架构

```
DS18B20/DHT22 ──→ ESP8266 ──→ 串口JSON ──→ hardware_sensor.py ──→ sensor_data.csv
                                                       │
                                              api_server.py (FastAPI)
                                                  ┌────┴────┐
                                          前端仪表盘      Coze 工作流
                                                              │
                                                        企业微信报警通知
```

**数据流说明：**

1. **传感器层** — DS18B20（冷库内部温度）和 DHT22（环境温湿度）连接到 ESP8266，固件每 5 秒采集一次数据并通过串口输出 JSON。
2. **采集层** — `hardware_sensor.py` 读取串口 JSON，解析后追加写入 `sensor_data.csv`。
3. **API 层** — `api_server.py` 基于 FastAPI 提供 REST 接口，读取 CSV 数据和 `alert_config.json` 报警配置。
4. **联动层** — Coze 工作流轮询 `GET /api/alert_message`，当温度超限时触发企业微信 Webhook 报警通知。
5. **控制层** — Coze 工作流或前端可通过 `POST /api/alert_config` 远程修改报警阈值和开关。

## 硬件清单

| 组件 | 规格 | 数量 | 用途 |
|------|------|:----:|------|
| ESP8266 NodeMCU | CP2102 USB-to-Serial | 1 | 主控，采集传感器数据并输出 JSON |
| DS18B20 不锈钢防水探头 | 9-12mm 直径，1m 线 | 2 | 冷库内部核心温度测量 |
| DHT22 / AM2302 | 温度 ±0.5°C，湿度 ±2% | 1 | 冷库门口环境温湿度 |
| 有源蜂鸣器 | 3.3V 低电平触发 | 1 | 本地声光报警 |
| 4.7kΩ 上拉电阻 | 1/4W 金属膜 | 1 | DS18B20 单总线数据线拉高 |
| 三防漆 | PCB 喷涂型 | 1 瓶 | 电路板防潮防腐 |
| 防水接线盒 | IP65 以上 | 1 | 保护电路板和传感器接头 |

## 接线表

| ESP8266 引脚 | 连接目标 | 说明 |
|:---:|------|------|
| D2 (GPIO2) | DS18B20 DATA（黄线） | 单总线数据线，需接 4.7kΩ 上拉电阻到 3.3V |
| D4 (GPIO4) | DHT22 DATA | 单总线数字信号 |
| D5 (GPIO5) | 蜂鸣器 + | 高电平响，低电平停 |
| 3.3V | DS18B20 VCC（红线） + DHT22 VCC + 蜂鸣器 VCC + 上拉电阻 | 统一供电 |
| GND | DS18B20 GND（黑线） + DHT22 GND + 蜂鸣器 GND | 共地 |

> **注意：** DS18B20 防水探头通常引出三根线 — 红线(VCC)、黑线(GND)、黄线(DATA)。DATA 与 VCC 之间必须并联 4.7kΩ 上拉电阻，否则通信不稳定。

## 项目文件

```
cold-storage-guardian/
├── cold_storage_firmware.ino/
│   └── cold_storage_firmware.ino.ino   # ESP8266 固件（Arduino 工程）
├── hardware_sensor.py                   # 串口读取 + CSV 写入
├── api_server.py                        # FastAPI 后端服务
├── alert_config.json                    # 报警阈值配置文件
├── sensor_data.csv                      # 传感器时序数据（自动生成）
└── README.md
```

## 快速开始

### 1. 接线

按照上方接线表连接 ESP8266 与各传感器。注意：
- DS18B20 的 DATA 线务必接 4.7kΩ 上拉电阻到 3.3V。
- 冷库内部湿度大，电路板喷涂三防漆后装入防水接线盒。
- 传感器引线穿过接线盒预留的防水接头后拧紧。

### 2. 烧录固件

1. 安装 [Arduino IDE](https://www.arduino.cc/en/software)（2.x 版本）。
2. 在 Arduino IDE 的「首选项 → 附加开发板管理器网址」中添加 ESP8266 包地址：
   ```
   https://arduino.esp8266.com/stable/package_esp8266com_index.json
   ```
3. 打开「工具 → 开发板 → 开发板管理器」，搜索安装 **ESP8266**。
4. 安装依赖库（「项目 → 加载库 → 管理库」）：
   - **DHT sensor library** by Adafruit
   - **DallasTemperature** by Miles Burton
   - **OneWire** by Jim Studt
5. 用 USB 数据线连接 ESP8266 到电脑，选择对应的 COM 口和开发板型号（NodeMCU 1.0）。
6. 打开 `cold_storage_firmware.ino/cold_storage_firmware.ino.ino`，点击上传。

> 固件中的报警阈值 `ALARM_TEMP` 默认为 30.0°C，可根据实际需求修改。

### 3. 启动硬件采集

```bash
pip install pyserial
python hardware_sensor.py
```

首次运行会自动创建 `sensor_data.csv`。终端将打印实时数据：

```
[2026-05-15 14:30:01] 环境温度:24.5°C | 环境湿度:62.8% | 冷库温度:18.2°C | 报警:false
```

> 若串口号不是 `COM11`，编辑 `hardware_sensor.py` 第 12 行修改 `SERIAL_PORT`。

### 4. 启动后端

```bash
pip install fastapi uvicorn pydantic
python api_server.py
```

服务启动在 `http://0.0.0.0:8000`。验证接口：

```bash
# 获取最新数据
curl http://localhost:8000/api/latest

# 获取报警消息（Coze 用）
curl http://localhost:8000/api/alert_message
```

### 5. 配置 Coze 工作流

在 Coze 中创建工作流，核心节点：

1. **HTTP 请求节点** — 调用 `GET http://<你的服务器IP>:8000/api/alert_message`，解析返回的 `alarm` 和 `message` 字段。
2. **条件判断节点** — 当 `alarm == true` 时进入报警分支。
3. **企业微信机器人节点** — 将 `message` 通过 Webhook 发送到企业微信群。

企业微信 Webhook 地址填入 `alert_config.json` 的 `wechat_webhook` 字段。

> 建议 Coze 工作流的轮询间隔设为 60 秒，避免频繁请求。

### 6. 测试报警

1. 将 DS18B20 探头握在手心或放入温水，使温度超过 `max_temp` 阈值。
2. 确认本地蜂鸣器响起。
3. 调用 `GET /api/alert_message`，确认返回 `alarm: true`。
4. 检查企业微信群是否收到报警消息。

## API 文档

| 方法 | 路径 | 认证 | 说明 |
|:----:|------|:----:|------|
| GET | `/api/latest` | 无 | 获取最新一条传感器数据和报警状态 |
| GET | `/api/alert_message` | 无 | 获取报警状态和中文提示消息（供 Coze 调用） |
| GET | `/api/alert_config` | Bearer Token | 读取当前报警配置 |
| POST | `/api/alert_config` | Bearer Token | 修改报警阈值和开关（限频 10次/分钟/IP） |

### POST /api/alert_config 请求体

```json
{
  "max_temp": 25.0,
  "alarm_enabled": true
}
```

两个字段均可选，未传字段保持原值。

## 配置文件

`alert_config.json` 字段说明：

| 字段 | 类型 | 说明 |
|------|:----:|------|
| `max_temp` | float | 报警温度阈值 (°C)，如 20.0 |
| `alarm_enabled` | bool | 报警总开关 |
| `token` | string | API 认证 Bearer Token |
| `wechat_webhook` | string | 企业微信机器人 Webhook 地址 |

## 开源协议

MIT License
