# cold_storage_guardian/ hardware_sensor.py
# 功能：从 ESP8266 串口读取冷库传感器数据，解析 JSON 并实时写入 CSV 文件。
# 配合冷库哨兵固件 cold_storage_firmware.ino 使用。

import serial
import json
import time
from datetime import datetime
import os

# -------------------- 配置 --------------------
SERIAL_PORT = "COM11"          # ESP8266 串口号，根据你实际端口修改
BAUD_RATE = 115200             # 与固件保持一致
CSV_FILE = "sensor_data.csv"   # 自动保存到当前目录

# -------------------- 初始化 --------------------
# 1. 打开串口
ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=10)

# 2. 如果 CSV 不存在，先写入表头（只写一次）
if not os.path.exists(CSV_FILE):
    with open(CSV_FILE, "w", encoding="utf-8") as f:
        f.write("timestamp,env_temp,env_humi,cold_temp,alarm\n")

print("冷库哨兵数据采集已启动，等待 ESP8266 数据...")

# -------------------- 主循环 --------------------
while True:
    try:
        # 3. 从串口读取一行
        line = ser.readline().decode("utf-8", errors="ignore").strip()

        # 4. 只处理 JSON 格式的行（以 { 开头）
        if line and line.startswith("{"):
            data = json.loads(line)
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # 5. 提取字段
            env_temp = data.get("env_temp", 0.0)
            env_humi = data.get("env_humi", 0.0)
            cold_temp = data.get("cold_temp", 0.0)
            alarm = data.get("alarm", "false")

            # 6. 写入 CSV 文件
            with open(CSV_FILE, "a", encoding="utf-8") as f:
                f.write(f"{now},{env_temp},{env_humi},{cold_temp},{alarm}\n")

            # 7. 打印到终端
            print(f"[{now}] 环境温度:{env_temp}°C | 环境湿度:{env_humi}% | 冷库温度:{cold_temp}°C | 报警:{alarm}")

    except json.JSONDecodeError:
        print(f"忽略无效数据: {line}")
    except Exception as e:
        print(f"错误: {e}")
        time.sleep(1)