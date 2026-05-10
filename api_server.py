#1.搬工具
from fastapi import FastAPI     #FastAPI 框架，帮我们快速搭建网站后端
from fastapi.middleware.cors import CORSMiddleware      #解决跨域问题，让前端能请求我们

import csv      #提取 CSV 文件用
import os       #检查文件是否存在
#报警配置管理
import json     #JSON库:负责把 Python 字典和 JSON 字符串互相转换

#配置文件路径和默认配置
ALERT_CONFIG_FILE = "alert_config.json"        #报警配置就存在这个文件夹里
#为什么用 .json 文件而不是 CSV？ 因为 JSON 更适合存 “键值对” 这种配置信息
DEFAULT_CONFIG = {
    "max_temp":30.0,        #温度超过此值触发报警
    "alarm_enable":True     #报警总开关
}
#单独定义一个DEFAULT_CONFIG，是为了当配置文件被误删或者损坏时，系统会自动用这套默认值重建，不会奔溃(默认值兜底)


#2.创建一个 "应用"
app = FastAPI(title="智能环境哨兵 API", version="1.0")

#3.允许任何人来访问
#   以后前端页面和API不在同一个地址时，这个配置就不会报错
app.add_middleware(
    CORSMiddleware,
    # "*" 表示允许所有来源
    allow_origins = ["*"],
    allow_methods = ["*"],
    allow_headers = ["*"],
)

#4.定义我们的数据文件(就是虚拟传感器写的那个CSV)
CSV_FILE = "sensor_data.csv"


#5.写第一个API接口：获取最新一条数据
@app.get("/api/latest")
def get_latest():
    """
    返回 sensor_data.csv 里最后一行温湿度数据
    """
    
    #如果文件不存在，报错
    if not os.path.exists(CSV_FILE):
        return{"error": "还没有数据，请先运行传感器"}

    #打开CSV文件，读所有行
    with open(CSV_FILE, "r", encoding="utf-8") as f:
        lines = f.readlines()

    #如果只有表头或者空文件，说明没数据
    if len(lines) < 2:
        return {"error": "CSV 中暂无数据"}

    #取最后一行(最新数据)
    last_line = lines[-1].strip()       #.strip() 去掉换行符
    parts = last_line.split(",")        #用逗号切开：时间，温度，湿度
    #parts[0]是时间，parts[1]是温度，parts[2]是湿度
    
    #先从配置文件里读取报警阈值
    try:
        with open(ALERT_CONFIG_FILE, "r", encoding="utf-8") as f:
            alert_config = json.load(f)
    except:
        alert_config =  DEFAULT_CONFIG      #万一配置文件读不出来，用默认值兜底

    #计算报警状态
    alarm_active = False       #初始状态：不报警
    if alert_config.get("alarm_enabled", True):         #如果报警开关是开启的
        current_temp = float(parts[1])      #当前温度
        if current_temp > alert_config.get("max_temp",30.0):
            alarm_active = True         #超过阈值 -> 报警

    return{
        "timestamp":parts[0],
        "temp":float(parts[1]),
        "humi":float(parts[2]),
        "alarm":alarm_active        #前端和 Coze 都读取这个
    }

#6.这个if判断：只有直接运行api_server.py时才启动服务器
#   如果被别人import, 就不启动
if __name__ == "__main__":
    import uvicorn
    #uvicorn.run 启动服务器
    #app 是我们要运行的应用
    #host = "0.0.0.0" 让同一个wifi下的其他设备也能访问
    #port = 8000 端口号
    uvicorn.run(app, host="0.0.0.0",port=8000)


#配置文件初始化
if not os.path.exists(ALERT_CONFIG_FILE):       #如果配置文件不存在
    with open(ALERT_CONFIG_FILE,"W",encoding="utf-8") as f:
        json.dump(DEFAULT_CONFIG, f, indent=2)

#API接口1：获取报警配置
@app.get("/api/alert_config")       #GET方法：浏览器直接打开这个网址就能看到这个内容
def get_alert_config():
    """读取当前报警阈值配置，返回给前端"""
    try:        #try 块：尝试执行，如果出错不会让整个程序奔溃
        with open(ALERT_CONFIG_FILE,"r",encoding="utf-8") as f:
            config = json.load(f)       #读取文件内容，并解析成 Python 字典
        return config       #FastAPI 自动把整个字典转成 JSON 返回给浏览器
    except Exception as e:      #如果读取失败（文件被误删）
        return {"error":f"读取配置文件失败：{str(e)}"}
        #给一个错误提示，而不是让服务端直接崩掉

#API接口2：修改报警配置
@app.post("/api/alert_config")      #POST 方法：浏览器不能直接访问，需要代码或工具调用
def set_alert_config(data:dict):
    """
    修改报警阈值配置
    前端或 Coze 工作流可以用 POST 请求把新配置发过来
    请求体示例：{"max_temp":35.0, "alarm_enabled":true}
    """
    try:
        #1. 先读出当前现有配置
        with open(ALERT_CONFIG_FILE, "r", encoding="utf-8") as f:
            config = json.load(f)

        #2. 根据用户传入的参数，覆盖对应的旧字段
        #   用户不传的字段保持原样不变
        if "max_temp" in data:      #如果用户传了 alarm_enabled 这个字段
            config["max_temp"] = float(data["max_temp"])
            # 用 bool() 保证 alarm_enabled 始终保持布尔类型
        if "alarm_enabled" in data:     #如果用户传了 alarm_enabled 这个字段
            config["alarm_enabled"] = bool(data["alarm_enabled"])
            #用 bool() 保证 alarm_enabled 始终保持布尔类型

        #3. 把更新后的配置写回 JSON 文件
        with open(ALERT_CONFIG_FILE,"w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
            #ensure_ascii = False 让中文注释可以正常写入，不会被转成 \u 编码
        
        return {"status": "ok", "config":config}        #返回成功标志和新配置
    
    except Exception as e:
        return{"error":f"更新配置文件失败：{str(e)}"}


        