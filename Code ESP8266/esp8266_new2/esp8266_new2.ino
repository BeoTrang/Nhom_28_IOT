#include <ESP8266WiFi.h>
#include <PubSubClient.h>
#include <DHT.h>
#include <ArduinoJson.h>

const char* ssid = "RiNo House";
const char* password = "12345678@";
const char* mqtt_server = "nekotrang.duckdns.org";
const int mqtt_port = 1883;

#define DHTPIN D4
#define DHTTYPE DHT22
DHT dht(DHTPIN, DHTTYPE);
#define RELAY_PIN D3

WiFiClient espClient;
PubSubClient client(espClient);

const char* topicData = "nhom28/data";
const char* topicRelay = "nhom28/relay";

unsigned long lastPublishTime = 0;
const long publishInterval = 5000;

float lastTemperature = NAN;
float lastHumidity = NAN;
int lastRelayState = -1;

void setup() {
  Serial.begin(115200);
  dht.begin();

  pinMode(RELAY_PIN, OUTPUT);
  digitalWrite(RELAY_PIN, LOW);

  setup_wifi();

  client.setServer(mqtt_server, mqtt_port);
  client.setCallback(callback);
}

void loop() {
  if (!client.connected()) {
    reconnect();
  }
  client.loop();

  unsigned long currentMillis = millis();
  if (currentMillis - lastPublishTime >= publishInterval) {
    lastPublishTime = currentMillis;

    float temperature = dht.readTemperature();
    float humidity = dht.readHumidity();
    int relayState = digitalRead(RELAY_PIN);

    if ((!isnan(temperature) && temperature != lastTemperature) || 
        (!isnan(humidity) && humidity != lastHumidity) || 
        (relayState != lastRelayState)) {

      lastTemperature = temperature;
      lastHumidity = humidity;
      lastRelayState = relayState;

      StaticJsonDocument<200> doc;
      doc["temperature"] = temperature;
      doc["humidity"] = humidity;
      doc["relay"] = relayState;

      char buffer[512];
      serializeJson(doc, buffer);

      client.publish(topicData, buffer);
      Serial.println("Đã gửi dữ liệu: " + String(buffer));
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

  Serial.println("Nhận MQTT từ " + String(topic) + ": " + message);

  StaticJsonDocument<200> doc;
  DeserializationError error = deserializeJson(doc, message);

  if (error) {
    Serial.println("Lỗi phân tích JSON");
    return;
  }

  if (String(topic) == topicRelay && doc.containsKey("relay")) {
    int relayState = doc["relay"];
    digitalWrite(RELAY_PIN, relayState ? HIGH : LOW);
    Serial.println("Relay: " + String(relayState));
  }
}

void reconnect() {
  while (!client.connected()) {
    if (client.connect("ESP8266Client")) {
      client.subscribe(topicRelay);
      Serial.println("Đã subscribe: " + String(topicRelay));
    } else {
      delay(5000);
    }
  }
}
