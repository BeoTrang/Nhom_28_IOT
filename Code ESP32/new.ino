#include <WiFi.h>
#include <PubSubClient.h>
#include <DHT.h>
#include <ArduinoJson.h>

// Cấu hình WiFi và MQTT
const char* ssid = "IoT";
const char* password = "234567Cn";
const char* mqtt_server = "192.168.0.103";
const int mqtt_port = 1883;

// Cấu hình DHT
#define DHTPIN 21
#define DHTTYPE DHT22
DHT dht(DHTPIN, DHTTYPE);

// Cấu hình chân relay
#define RELAY_PIN 23

WiFiClient espClient;
PubSubClient client(espClient);

// Các topic MQTT
const char* sensorTopic = "sensor/data";
const char* relayTopic = "relay/control";

// Biến kiểm tra thời gian gửi
unsigned long lastPublishTime = 0;
const long publishInterval = 5000;  // Khoảng thời gian giữa các lần gửi dữ liệu

void setup() {
  Serial.begin(115200);
  dht.begin();

  pinMode(RELAY_PIN, OUTPUT);
  digitalWrite(RELAY_PIN, LOW);

  // Kết nối WiFi
  setup_wifi();

  // Cấu hình MQTT
  client.setServer(mqtt_server, mqtt_port);
  client.setCallback(callback);
}

void loop() {
  if (!client.connected()) {
    reconnect();
  }
  client.loop();

  // Chỉ gửi dữ liệu sau mỗi publishInterval ms
  unsigned long currentMillis = millis();
  if (currentMillis - lastPublishTime >= publishInterval) {
    lastPublishTime = currentMillis;

    // Đọc dữ liệu từ cảm biến DHT22
    float temperature = dht.readTemperature();
    float humidity = dht.readHumidity();

    if (!isnan(temperature) && !isnan(humidity)) {
      // Tạo chuỗi JSON với dữ liệu từ cảm biến và trạng thái relay
      StaticJsonDocument<200> doc;
      doc["temperature"] = temperature;
      doc["humidity"] = humidity;
      doc["relay"] = (digitalRead(RELAY_PIN) == HIGH) ? 1 : 0;

      char buffer[512];
      serializeJson(doc, buffer);

      // Gửi dữ liệu JSON qua MQTT
      client.publish(sensorTopic, buffer);
      Serial.println(buffer);
    } else {
      Serial.println("Lỗi đọc DHT22!");
    }
  }
}

void setup_wifi() {
  Serial.println("Đang kết nối WiFi...");
  WiFi.begin(ssid, password);
  while (WiFi.status() != WL_CONNECTED) {
    delay(1000);
    Serial.print(".");
  }
  Serial.println("\nWiFi đã kết nối!");
}

void callback(char* topic, byte* payload, unsigned int length) {
  String message;
  for (int i = 0; i < length; i++) {
    message += (char)payload[i];
  }

  StaticJsonDocument<200> doc;
  DeserializationError error = deserializeJson(doc, message);

  if (error) {
    Serial.println("Lỗi phân tích JSON");
    return;
  }

  if (doc.containsKey("relay")) {
    int relayState = doc["relay"];
    if (relayState == 1) {
      digitalWrite(RELAY_PIN, HIGH);  // Bật relay
    } else if (relayState == 0) {
      digitalWrite(RELAY_PIN, LOW);   // Tắt relay
    }
  }
}

void reconnect() {
  while (!client.connected()) {
    if (client.connect("ESP32Client")) {
      client.subscribe(relayTopic);  // Subscribe vào topic relay
    } else {
      delay(5000);
    }
  }
}
