# 1.搬工具
from collections import defaultdict  # 用于 IP 频率限制的数据结构（自动为每个 IP 创建独立的计时列表）
from typing import Optional  # 类型注解：声明可选字段

from fastapi import Depends, FastAPI, HTTPException, Request  # FastAPI 框架 + 认证依赖注入 + 请求对象
from fastapi.middleware.cors import CORSMiddleware  # 解决跨域问题，让前端能请求我们
from pydantic import BaseModel, Field  # Pydantic：为 POST 接口做请求体校验，防止注入攻击

import csv  # 用 csv.reader 安全解析 CSV（替代手写 split 避免逗号逃逸问题）
import json  # JSON 库：负责把 Python 字典和 JSON 字符串互相转换
import os  # 检查文件是否存在
import time  # 频率限制的时间戳计算

# ==================== 配置文件路径和默认配置 ====================
ALERT_CONFIG_FILE = "alert_config.json"  # 报警配置就存在这个文件里
# 为什么用 .json 文件而不是 CSV？因为 JSON 更适合存"键值对"这种配置信息
DEFAULT_CONFIG = {
    "max_temp": 30.0,  # 温度超过此值触发报警
    "alarm_enabled": True,  # 报警总开关（修复：统一使用 alarm_enabled 字段名）
    "token": "",  # 【安全加固】默认空 token，生产环境须在 alert_config.json 中设置强随机令牌
    "wechat_webhook": "",  # 【安全加固】企业微信 Webhook 地址存配置文件，不硬编码在代码中
    "allowed_origins": ["*"],  # 【安全加固】CORS 允许的源，生产环境请改为具体域名如 ["https://dashboard.example.com"]
}
# 单独定义一个 DEFAULT_CONFIG，是为了当配置文件被误删或损坏时，系统会自动用这套默认值重建，不会崩溃（默认值兜底）


def load_config():
    """【安全加固】集中式配置加载器 —— 统一从磁盘读取配置，避免分散的 try-except。
    返回值：配置字典。若文件不存在或损坏，返回 DEFAULT_CONFIG 的副本作为兜底。"""
    try:
        with open(ALERT_CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return dict(DEFAULT_CONFIG)  # dict() 创建副本，避免调用方意外修改 DEFAULT_CONFIG


# ==================== 频率限制器（IP 级别） ====================
rate_records = defaultdict(list)  # key: IP 地址, value: 该 IP 最近一分钟的请求时间戳列表


def check_rate_limit(request: Request):
    """【安全加固】IP 频率限制依赖 —— 同一 IP 每分钟最多 10 次请求。
    用于 POST /api/alert_config 接口，防止暴力破解 token 和配置篡改洪水攻击。
    超限时抛出 HTTP 429 状态码。"""
    ip = request.client.host  # 获取请求来源 IP
    now = time.time()  # 当前 Unix 时间戳（秒）
    # 清理超过 60 秒的旧记录
    rate_records[ip] = [t for t in rate_records[ip] if now - t < 60]
    if len(rate_records[ip]) >= 10:  # 60 秒内已有 10 次请求
        raise HTTPException(status_code=429, detail="请求过于频繁，请稍后再试")
    rate_records[ip].append(now)  # 记录本次请求时间戳


# ==================== API Token 认证（仅 Bearer 头） ====================
def verify_token(request: Request):
    """【安全加固】Bearer Token 认证依赖。
    仅接受 Authorization: Bearer <token> 头部（不再支持 URL 查询参数，避免 token 泄露到日志）。
    若配置文件未设置 token（空字符串），直接拒绝所有请求，防止空 token 绕过认证。
    认证失败时抛出 HTTP 401 状态码。"""
    config = load_config()
    expected = config.get("token", "")

    # 【安全加固】空 token 直接拒绝，防止 Authorization: Bearer  绕过认证
    if not expected:
        raise HTTPException(status_code=500, detail="服务器未配置认证令牌，请联系管理员")

    # 仅接受 Bearer 头部
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer ") and auth[7:] == expected:
        return True

    # 认证失败（使用通用错误消息，不泄露内部细节）
    raise HTTPException(status_code=401, detail="认证失败")


# ==================== Pydantic 请求体模型 ====================
class AlertConfigUpdate(BaseModel):
    """【安全加固】POST 请求体校验模型 —— 替代裸 dict 参数，限制字段类型和取值范围。
    两个字段均为可选：只传需要修改的字段即可，未传字段保持原值不变。"""

    max_temp: Optional[float] = Field(default=None, ge=0.0, le=100.0)  # 温度范围 0°C ~ 100°C，拒绝非法值
    alarm_enabled: Optional[bool] = Field(default=None)  # 报警开关，只接受 true/false


# ==================== 应用和中间件 ====================
# 2.创建一个"应用"
app = FastAPI(title="智能环境哨兵 API", version="2.0")

# 3.允许跨域访问（从配置文件读取 allowed_origins，生产环境请改为具体域名）
origins = load_config().get("allowed_origins", ["*"])
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,  # 【安全加固】从配置文件读取，不再硬编码 *
    allow_methods=["*"],
    allow_headers=["*"],
)

# 4.定义我们的数据文件（就是虚拟传感器写的那个 CSV）
CSV_FILE = "sensor_data.csv"


# ==================== API 路由 ====================

# 5.API 接口 0：获取最新一条温湿度数据（无需认证，公开只读）
@app.get("/api/latest")
def get_latest():
    """
    返回 sensor_data.csv 里最后一行温湿度数据。
    公开接口，无需 token —— 方便前端仪表盘直接轮询。
    """
    # 如果文件不存在，报错（通用消息，不泄露路径）
    if not os.path.exists(CSV_FILE):
        return {"error": "暂无数据"}

    # 使用 csv.reader 安全解析 CSV（修复：替代手写 split，正确处理字段内的逗号）
    with open(CSV_FILE, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        rows = list(reader)

    # 如果只有表头或者空文件，说明没数据
    if len(rows) < 2:
        return {"error": "暂无数据"}

    # 取最后一行（最新数据）
    parts = rows[-1]  # csv.reader 返回列表，无需手动 split
    # parts[0] 是时间，parts[1] 是温度，parts[2] 是湿度

    # 从配置文件读取报警阈值
    alert_config = load_config()

    # 计算报警状态
    alarm_active = False  # 初始状态：不报警
    # 【修复】兼容旧配置字段名 alarm_enable 和新字段名 alarm_enabled
    alarm_switch = alert_config.get("alarm_enabled", alert_config.get("alarm_enable", True))
    if alarm_switch:  # 如果报警开关是开启的
        try:
            current_temp = float(parts[1])  # 当前温度
            # 【安全加固】温度值范围校验：拒绝异常值
            if -50.0 <= current_temp <= 120.0:
                if current_temp > alert_config.get("max_temp", 30.0):
                    alarm_active = True  # 超过阈值 → 报警
        except (ValueError, IndexError):
            pass  # 数据格式异常时跳过报警判断，不崩溃

    return {
        "timestamp": parts[0],
        "temp": float(parts[1]) if len(parts) > 1 else 0.0,
        "humi": float(parts[2]) if len(parts) > 2 else 0.0,
        "alarm": alarm_active,  # 前端和 Coze 都读取这个
    }


# API 接口 1：获取报警配置（需要 token 认证）
@app.get("/api/alert_config")
def get_alert_config(_: bool = Depends(verify_token)):
    """读取当前报警阈值配置，返回给前端。
    【安全加固】需要 Authorization: Bearer <token> 认证。"""
    try:
        config = load_config()
        # 【安全加固】返回配置前脱敏：不暴露 token 的完整值，只返回是否已配置
        safe_config = dict(config)
        if safe_config.get("token"):
            safe_config["token"] = "***"
        if safe_config.get("wechat_webhook"):
            safe_config["wechat_webhook"] = "***"  # 掩码处理，防止 webhook 地址泄露
        return safe_config
    except Exception:
        return {"error": "读取配置失败"}


# API 接口 2：修改报警配置（需要 token 认证 + 频率限制）
@app.post("/api/alert_config")
def set_alert_config(
    data: AlertConfigUpdate,  # 【安全加固】Pydantic 模型替代裸 dict，自动校验类型和范围
    request: Request,
    _token: bool = Depends(verify_token),  # 【安全加固】Token 认证依赖
    _rate: None = Depends(check_rate_limit),  # 【安全加固】频率限制依赖（每分钟 10 次）
):
    """修改报警阈值配置。
    前端或 Coze 工作流可以用 POST 请求把新配置发过来。
    请求体示例：{"max_temp": 35.0, "alarm_enabled": true}

    【安全加固】：
      - 需要 Bearer Token 认证
      - 同一 IP 每分钟最多 10 次请求
      - 字段类型和取值由 Pydantic 自动校验
    """
    try:
        # 1. 先读出当前现有配置
        config = load_config()

        # 2. 根据用户传入的参数，覆盖对应的旧字段
        #    用户不传的字段保持原样不变
        if data.max_temp is not None:  # 如果用户传了 max_temp 字段
            config["max_temp"] = float(data.max_temp)  # Pydantic 已校验范围 0~100
        if data.alarm_enabled is not None:  # 如果用户传了 alarm_enabled 字段
            config["alarm_enabled"] = bool(data.alarm_enabled)  # Pydantic 已校验为布尔类型

        # 3. 把更新后的配置写回 JSON 文件
        with open(ALERT_CONFIG_FILE, "w", encoding="utf-8") as f:  # 【修复】文件模式 "W" → "w"
            json.dump(config, f, indent=2, ensure_ascii=False)
            # ensure_ascii=False 让中文注释可以正常写入，不会被转成 \u 编码

        # 4. 返回成功标志和脱敏后的新配置
        safe_config = dict(config)
        if safe_config.get("token"):
            safe_config["token"] = "***"
        if safe_config.get("wechat_webhook"):
            safe_config["wechat_webhook"] = "***"  # POST 接口返回也做脱敏
        return {"status": "ok", "config": safe_config}

    except Exception:
        return {"error": "更新配置失败"}  # 【修复】通用错误消息，不暴露内部异常细节


# 这个接口供外部系统（如Coze工作流）获取冷库报警状态和语音播报消息
@app.get("/api/alert_message")
def get_alert_message():
    """返回冷库报警状态和提示消息，供外部语音播报系统调用。"""
    if not os.path.exists(CSV_FILE):
        return {"status": "error", "message": "暂无数据"}

    with open(CSV_FILE, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        rows = list(reader)

    if len(rows) < 2:
        return {"status": "error", "message": "暂无数据"}

    parts = rows[-1]

    try:
        current_temp = float(parts[1])
    except (ValueError, IndexError):
        return {"status": "error", "message": "数据格式异常"}

    alert_config = load_config()
    alarm_switch = alert_config.get("alarm_enabled", alert_config.get("alarm_enable", True))
    max_temp = alert_config.get("max_temp", 30.0)

    alarm_active = False
    if alarm_switch and current_temp > max_temp:
        alarm_active = True

    if alarm_active:
        message = f"⚠️ 冷库温度异常！当前温度：{current_temp}°C，请立即检查！"
    else:
        message = "✅ 冷库温度正常。"

    return {
        "status": "ok",
        "alarm": alarm_active,
        "message": message,
    }


# ==================== 启动入口 ====================
# 6.这个 if 判断：只有直接运行 api_server.py 时才启动服务器
#    如果被别人 import，就不启动
if __name__ == "__main__":
    import uvicorn

    # host="0.0.0.0" 让局域网设备可访问; port=8000 端口号
    #
    # 【安全加固】生产环境务必通过 Nginx/Caddy 反向代理添加 HTTPS，否则 token 明文传输。
    # 若必须由 uvicorn 直接提供 HTTPS，取消下面注释并签发证书：
    # uvicorn.run(app, host="0.0.0.0", port=8000,
    #             ssl_keyfile="/path/to/privkey.pem",
    #             ssl_certfile="/path/to/fullchain.pem")
    #
    # 开发 / 内网环境：
    uvicorn.run(app, host="0.0.0.0", port=8000)


# ==================== 配置文件初始化 ====================
if not os.path.exists(ALERT_CONFIG_FILE):  # 如果配置文件不存在
    with open(ALERT_CONFIG_FILE, "w", encoding="utf-8") as f:  # 【修复】文件模式 "W" → "w"
        json.dump(DEFAULT_CONFIG, f, indent=2)
