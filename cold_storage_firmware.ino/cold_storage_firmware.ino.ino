//库的引入
#include <DHT.h>      //DHT22驱动库
#include <OneWire.h>        //DS18B20 通信协议库：一根线双向传数据
#include <DallasTemperature.h>    //DS18B20 温度解析库：把原始电信号转成摄氏度

//引脚定义
#define DHTPIN D4     //DHT22 数据线接 D4
#define DHTTYPE DHT22     //声明传感器型号是 DHT22
#define ONE_WIRE_BUS D2     //DS18B20 数据线接 D2
#define BUZZER_PIN D5       //蜂鸣器接D5，高电平响，低电平停

//报警阈值
#define ALARM_TEMP 30.0      //冷库温度超过30℃就报警

//创建传感器对象
//相当于 C 语言里声明结构体变量，并初始化硬件接口
DHT dht(DHTPIN, DHTTYPE);         //创建 DHT22 对象，绑定 D4 引脚
OneWire oneWire(ONE_WIRE_BUS);    //创建单总线对象，绑定 D2 引脚
DallasTemperature ds18b20(&oneWire);      //把单总线对象交给 DS18B20 驱动管理

//全局变量
bool alarm_active = false;        //报警状态标志位，true=正在报警，false=正常
//用bool类型而不是int，省内存，语义更清晰

//初始化函数
void setup(){
  Serial.begin(115200);       //启动串口，波特率115200

  dht.begin();          //初始化 DHT22
  ds18b20.begin();      //初始化 DS18B20
  //这两个begin() 内部会做：复位传感器、检测是否在线、标准初始值

  pinMode(BUZZER_PIN,OUTPUT);     //把蜂鸣器引脚设为输出模式
  digitalWrite(BUZZER_PIN,LOW);   //初始状态：不响（低电平）
  //有源蜂鸣器高电平触发，通电就响

  Serial.println("{\"status\":\"cold_storage_guardian_ready\"}");
  //打印就绪信号，Python 端读到这行就知道硬件初始化完成
}

//主循环
void loop(){
  //读取冷库环境温湿度 (DHT22，放在冷酷门口或仓库外)
  float env_temp = dht.readTemperature();     //读取环境温度
  float env_humi = dht.readHumidity();        //读取环境湿度
  //这两个函数内部实际做了：发命令 -> 等待传感器应答 -> 读 40bit 数据 -> 校验 -> 解析

  //读取冷库核心温度(DS18B20, 放进冷库里面)
  ds18b20.requestTemperatures();        //向所有 DS18B20 发送“开始测量”命令
  //这是一个广播命令，总线上挂几个传感器就同时测几个
  float cold_temp = ds18b20.getTempCByIndex(0);       //读第 0 个传感器的温度值
  //如果接了俩个探头，index 1 就是第二个

  //报警判断
  if(cold_temp > ALARM_TEMP){
    digitalWrite(BUZZER_PIN, HIGH);
    alarm_active = true;
  }else{
    digitalWrite(BUZZER_PIN,LOW);
    alarm_active = false;
  }
  //digitalWrite 本质是写 ESP826 的 GPIO 寄存器，拉高或拉低电平

  //串口输出 JSON
  //把三个传感器数据 + 报警状态打包成一个 JSON 字符串
  //Python 端 hardware_sensor.py 读串口后，直接json.loods就能解析
  Serial.print("{\"env_temp\":");
  Serial.print(env_temp, 1);                // 保留 1 位小数
  Serial.print(",\"env_humi\":");
  Serial.print(env_humi, 1);
  Serial.print(",\"cold_temp\":");
  Serial.print(cold_temp, 1);
  Serial.print(",\"alarm\":");
  Serial.print(alarm_active ? "true" : "false"); // 三元运算符：1→"true", 0→"false"
  Serial.println("}");

  delay(5000);      //每5秒采集1次
  }
