from flask import Flask, render_template, jsonify, request
import paho.mqtt.client as mqtt
import json
import sqlite3
from datetime import datetime
from threading import Thread
import pyrebase

firebaseConfig = {
    "apiKey": "AIzaSyACuevUCbfT-Kxzo6xWe3I-BCNCIO8r2Kw",
    "authDomain": "trang-64053.firebaseapp.com",
    "databaseURL": "https://trang-64053-default-rtdb.firebaseio.com",
    "projectId": "trang-64053",
    "storageBucket": "trang-64053.firebasestorage.app",
    "messagingSenderId": "104965919201",
    "appId": "1:104965919201:web:8655bd9609c63d2ebb42a0"
}
firebase = pyrebase.initialize_app(firebaseConfig)
db_firebase = firebase.database()

MQTT_BROKER = "nekotrang.duckdns.org"
MQTT_PORT = 1883
MQTT_SENSOR_TOPIC = "nhom28/data"
MQTT_RELAY_TOPIC = "nhom28/relay"

app = Flask(__name__)

latest_data = {"temperature": 0, "humidity": 0, "relay": 0}
auto_mode = False
temperature_threshold = 30
humidity_threshold = 70

last_firebase_data = None

def init_db():
    conn = sqlite3.connect('sensor_data.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS sensor_data
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  temperature REAL,
                  humidity REAL,
                  relay INTEGER,
                  timestamp DATETIME)''')
    c.execute("CREATE INDEX IF NOT EXISTS idx_timestamp ON sensor_data(timestamp)")
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

def push_to_firebase(temperature, humidity, relay):
    global last_firebase_data
    temp_margin = 0.5
    humi_margin = 2.0
    if last_firebase_data is not None:
        if (abs(temperature - last_firebase_data["temperature"]) < temp_margin and
            abs(humidity - last_firebase_data["humidity"]) < humi_margin and
            relay == last_firebase_data["relay"]):
            print("Dữ liệu không thay đổi nên không cần gửi lên Firebase")
            return

    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    data_firebase = {
        "temperature": temperature,
        "humidity": humidity,
        "relay": relay,
        "timestamp": timestamp
    }
    db_firebase.child("sensor_data").push(data_firebase)
    last_firebase_data = {"temperature": temperature, "humidity": humidity, "relay": relay}
    print("Dữ liệu được gửi lên Firebase:", data_firebase)

def get_latest_records():
    conn = sqlite3.connect('sensor_data.db')
    c = conn.cursor()
    c.execute("""
        SELECT * FROM (
            SELECT * FROM sensor_data 
            ORDER BY timestamp DESC 
            LIMIT 100
        ) ORDER BY timestamp ASC
    """)
    records = c.fetchall()
    conn.close()
    return records

def get_history_data(start, end):
    conn = sqlite3.connect('sensor_data.db')
    c = conn.cursor()
    c.execute("""
        SELECT * FROM sensor_data 
        WHERE timestamp BETWEEN ? AND ?
        ORDER BY timestamp ASC
    """, (start, end))
    records = c.fetchall()
    conn.close()
    return records

def on_connect(client, userdata, flags, rc):
    print(f"Connected to MQTT Broker with code {rc}")
    client.subscribe(MQTT_SENSOR_TOPIC)
    client.subscribe(MQTT_RELAY_TOPIC)

def on_message(client, userdata, msg):
    global latest_data, auto_mode, temperature_threshold, humidity_threshold
    try:
        data = json.loads(msg.payload.decode())
        if msg.topic == MQTT_SENSOR_TOPIC:
            new_relay = latest_data["relay"]
            if auto_mode:
                new_relay = 1 if (data["temperature"] >= temperature_threshold or
                                  data["humidity"] >= humidity_threshold) else 0
                if new_relay != latest_data["relay"]:
                    client.publish(MQTT_RELAY_TOPIC, json.dumps({"relay": new_relay}))
            latest_data.update({
                "temperature": data["temperature"],
                "humidity": data["humidity"],
                "relay": new_relay
            })
            save_to_db(data["temperature"], data["humidity"], latest_data["relay"])
            push_to_firebase(data["temperature"], data["humidity"], latest_data["relay"])
        elif msg.topic == MQTT_RELAY_TOPIC:
            latest_data["relay"] = data.get("relay", 0)
    except Exception as e:
        print(f"Error processing message: {str(e)}")

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/get_all_data')
def get_all_data():
    records = get_latest_records()
    return jsonify({
        "latest_data": latest_data,
        "records": [{
            "time": record[4][11:16],
            "temperature": record[1],
            "humidity": record[2],
            "relay": record[3]
        } for record in records],
        "auto_mode": auto_mode,
        "thresholds": {
            "temperature": temperature_threshold,
            "humidity": humidity_threshold
        }
    })

@app.route('/control', methods=['POST'])
def handle_control():
    global auto_mode, temperature_threshold, humidity_threshold
    data = request.json
    action = data.get('action')
    if action == 'set_relay':
        state = data.get('state')
        if state in [0, 1]:
            auto_mode = False
            latest_data["relay"] = state
            mqtt_client.publish(MQTT_RELAY_TOPIC, json.dumps({"relay": state}))
            return jsonify(success=True, auto_mode=auto_mode)
    elif action == 'toggle_auto':
        auto_mode = not auto_mode
        return jsonify(success=True, auto_mode=auto_mode)
    elif action == 'set_thresholds':
        temperature_threshold = float(data.get('temperature', temperature_threshold))
        humidity_threshold = float(data.get('humidity', humidity_threshold))
        return jsonify(success=True)
    return jsonify(success=False)

@app.route('/get_history_data')
def handle_history():
    try:
        start = datetime.strptime(request.args.get('start'), "%Y-%m-%dT%H:%M").strftime("%Y-%m-%d %H:%M:%S")
        end = datetime.strptime(request.args.get('end'), "%Y-%m-%dT%H:%M").strftime("%Y-%m-%d %H:%M:%S")
        records = get_history_data(start, end)
        return jsonify([{
            "time": record[4][11:16],
            "temperature": record[1],
            "humidity": record[2],
            "relay": record[3]
        } for record in records])
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    init_db()
    mqtt_client = mqtt.Client()
    mqtt_client.on_connect = on_connect
    mqtt_client.on_message = on_message
    mqtt_client.connect(MQTT_BROKER, MQTT_PORT)
    Thread(target=mqtt_client.loop_forever).start()
    app.run(host='0.0.0.0', port=5000, debug=True, use_reloader=False)
