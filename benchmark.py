#
# Copyright (c) 2022 Scott Ware
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

import argparse
import json
import os
import paho.mqtt.client as mqtt
import ssl
from datetime import date, datetime, timezone
from dateutil.parser import isoparse
from threading import Thread
from time import sleep

parser = argparse.ArgumentParser(description='Video publisher benchmark utility')

parser.add_argument('--input',required=False, default='videopub/stream/#', help='Specify the video input')
parser.add_argument('--mqtt_address', required=False, default='localhost',  help='MQTT broker address. default: localhost')
parser.add_argument('--mqtt_port', required=False, default=1883, help='MQTT port. default: 1883')
parser.add_argument('--mqtt_username', required=False, default='',  help='MQTT username.')
parser.add_argument('--mqtt_password', required=False, default='',  help='MQTT password.')
parser.add_argument('--mqtt_tls', default=False, action='store_true', help='use TLS communication for MQTT')
parser.add_argument('--perf_stats', default=False, action='store_true', help='Print detailed performance statistics')
args = vars(parser.parse_args())

topic = args.get('input')
mqtt_address = args.get('mqtt_address')
mqtt_port = args.get('mqtt_port')
mqtt_username = args.get('mqtt_username')
mqtt_password = args.get('mqtt_password')
perf_stats = args.get('perf_stats')

# Message counter
count = 0
total_latency = 0

#
# Create MQTT client
#

def on_connect(mqttc, obj, flags, rc):
    print("MQTT connected...")

def on_message(mqttc, obj, msg):
    global count
    global total_latency

    topic = msg.topic
    payload = msg.payload.decode("utf-8")
    
    count += 1

    try:
        json_payload = json.loads(payload)
    except JSONDecodeError:
        return

    if "timestamp" in json_payload:
        timestamp_str = json_payload['timestamp']
        timestamp = isoparse(timestamp_str)
        timestamp_now = datetime.now(timezone.utc)
        
        delta = timestamp_now - timestamp
        total_latency += delta.total_seconds()

        if perf_stats:
            print("Latency:", delta.total_seconds())

mqttc = mqtt.Client()
mqttc.on_connect = on_connect
mqttc.on_message = on_message
mqttc.username_pw_set(mqtt_username,mqtt_password)

if args.get('mqtt_tls'):
    mqttc.tls_set(cert_reqs=ssl.CERT_NONE)
    mqttc.tls_insecure_set(True)

mqttc.connect(mqtt_address, int(mqtt_port), 60)
mqttc.subscribe(topic, 0)

print('Start benchmarking...')

mqttc.loop_start()

while True:
    count = 0
    total_latency = 0

    sleep(1)

    average_latency = 0

    if count > 0:
        average_latency = total_latency / count

    print('Message Per Second:', count, " ", 'Average Latency:', round(average_latency, 3))
