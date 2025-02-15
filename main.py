from flask import Flask, render_template, jsonify, request
import paho.mqtt.client as mqtt
import json
import sqlite3
from datetime import datetime

MQTT_BROKER = "192.168.0.103"
MQTT_PORT = 1883
MQTT_SENSOR_TOPIC = "sensor/data"
MQTT_RELAY_TOPIC = "relay/control"

app = Flask(__name__)

latest_data = {"temperature": 0, "humidity": 0, "relay": 0}
auto_mode = False
temperature_threshold = 30
humidity_threshold = 70

def init_db():
    conn = sqlite3.connect('sensor_data.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS sensor_data
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  temperature REAL,
                  humidity REAL,
                  relay INTEGER,
                  timestamp DATETIME)''')
    conn.commit()
    conn.close()

def save_to_db(temperature, humidity, relay):
    conn = sqlite3.connect('sensor_data.db')
    c = conn.cursor()
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    c.execute("INSERT INTO sensor_data (temperature, humidity, relay, timestamp) VALUES (?, ?, ?, ?)",
              (temperature, humidity, relay, timestamp))
    conn.commit()
    conn.close()

def get_latest_records():
    conn = sqlite3.connect('sensor_data.db')
    c = conn.cursor()
    c.execute("SELECT * FROM sensor_data ORDER BY timestamp DESC LIMIT 10")
    records = c.fetchall()
    conn.close()
    return records

def on_connect(client, userdata, flags, rc):
    print(f"Đã kết nối MQTT, Mã kết nối: {rc}")
    client.subscribe(MQTT_SENSOR_TOPIC)
    client.subscribe(MQTT_RELAY_TOPIC)

# Hàm xử lý khi nhận được MQTT
def on_message(client, userdata, message):
    global latest_data, auto_mode, temperature_threshold, humidity_threshold
    payload = message.payload.decode()
    print(f"Nhận MQTT từ {message.topic}: {payload}")
    try:
        data = json.loads(payload)
        if message.topic == MQTT_SENSOR_TOPIC:
            latest_data["temperature"] = data["temperature"]
            latest_data["humidity"] = data["humidity"]
            latest_data["relay"] = data.get("relay", latest_data["relay"])

            if auto_mode:
                if latest_data["temperature"] >= temperature_threshold or latest_data["humidity"] >= humidity_threshold:
                    mqtt_client.publish(MQTT_RELAY_TOPIC, json.dumps({"relay": 1}))
                    latest_data["relay"] = 1
                else:
                    mqtt_client.publish(MQTT_RELAY_TOPIC, json.dumps({"relay": 0}))
                    latest_data["relay"] = 0

            save_to_db(data["temperature"], data["humidity"], latest_data["relay"])
        elif message.topic == MQTT_RELAY_TOPIC:
            latest_data["relay"] = data["relay"]
    except json.JSONDecodeError as e:
        print(f"Lỗi JSON: {e}")

@app.route('/')
def index():
    records = get_latest_records()
    return render_template('index.html', latest_data=latest_data, records=records, auto_mode=auto_mode,
                           temperature_threshold=temperature_threshold, humidity_threshold=humidity_threshold)

@app.route('/get_all_data')
def get_all_data():
    latest_records = get_latest_records()
    return jsonify({
        "latest_data": latest_data,
        "records": latest_records,
        "auto_mode": auto_mode,
        "temperature_threshold": temperature_threshold,
        "humidity_threshold": humidity_threshold
    })

@app.route('/set_relay')
def set_relay():
    state = request.args.get('state')
    if state not in ['0', '1']:
        return jsonify({"status": "error", "message": "Invalid state"})

    relay_state = int(state)
    latest_data["relay"] = relay_state
    mqtt_client.publish(MQTT_RELAY_TOPIC, json.dumps({"relay": relay_state}))

    return jsonify({"status": "success", "relay": relay_state})

@app.route('/toggle_auto_mode')
def toggle_auto_mode():
    global auto_mode
    auto_mode = not auto_mode
    return jsonify({"status": "success", "auto_mode": auto_mode})

@app.route('/set_thresholds')
def set_thresholds():
    global temperature_threshold, humidity_threshold
    temperature_threshold = float(request.args.get('temperature_threshold', temperature_threshold))
    humidity_threshold = float(request.args.get('humidity_threshold', humidity_threshold))
    return jsonify({"status": "success", "temperature_threshold": temperature_threshold, "humidity_threshold": humidity_threshold})

mqtt_client = mqtt.Client()
mqtt_client.on_connect = on_connect
mqtt_client.on_message = on_message
mqtt_client.connect(MQTT_BROKER, MQTT_PORT, 60)

def start_mqtt():
    mqtt_client.loop_forever()

init_db()

if __name__ == '__main__':
    from threading import Thread

    mqtt_thread = Thread(target=start_mqtt)
    mqtt_thread.start()
    app.run(host='0.0.0.0', port=5000)