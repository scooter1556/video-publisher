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
import base64
import cv2
import json
import os
import paho.mqtt.client as mqtt
import ssl
from datetime import datetime, timezone

parser = argparse.ArgumentParser(description='Video Publisher')

parser.add_argument('--input',required=False, default='/dev/video0', help='Specify the video input')
parser.add_argument('--loop', default=False, action='store_true', help='Loop input video')
parser.add_argument('--header', required=False, default='videopub', help='Specify the MQTT topic header')
parser.add_argument('--id', required=True, help='Unique stream identifier for MQTT topic')
parser.add_argument('--width', required=False, help='Specify desired input image width', type=int)
parser.add_argument('--height', required=False, help='Specify desired input image height', type=int)
parser.add_argument('--threads', required=False, help='Limit CPU usage for camera processing', default=10, type=int)
parser.add_argument('--mqtt_address', required=False, default='localhost',  help='MQTT broker address. default: localhost')
parser.add_argument('--mqtt_port', required=False, default=1883, help='MQTT port. default: 1883')
parser.add_argument('--mqtt_username', required=False, default='',  help='MQTT username.')
parser.add_argument('--mqtt_password', required=False, default='',  help='MQTT password.')
parser.add_argument('--mqtt_tls', default=False, action='store_true', help='use TLS communication for MQTT')
parser.add_argument('--perf_stats', default=False, action='store_true', help='Print performance statistics')
parser.add_argument('--debug', default=False, action='store_true', help='Print debug information')
args = vars(parser.parse_args())

address = "{}:{}".format(args.get('grpc_address'),args.get('grpc_port'))

model_name = args.get('model_name')
model_version = args.get('model_version')
instance_id = args.get('id')
header = args.get('header')
category = args.get('category')
threshold = args.get('threshold')
grpc_address = args.get('grpc_address')
grpc_port = args.get('grpc_port')
mqtt_address = args.get('mqtt_address')
mqtt_port = args.get('mqtt_port')
mqtt_username = args.get('mqtt_username')
mqtt_password = args.get('mqtt_password')

mqtt_topic = ''.join([header, "/", instance_id])
command_topic = ''.join([header, "/", "cmd", "/", "sensor", "/", "cam", "/", instance_id])
image_topic = ''.join([header, "/", "image", "/", "sensor", "/", "cam", "/", instance_id])

# Camera frame & timestamp
curr_frame = None
curr_timestamp = None

#
# Create MQTT client
#

def on_connect(mqttc, obj, flags, rc):
    print("MQTT connected...")

def on_message(mqttc, obj, msg):
    topic = msg.topic
    payload = msg.payload.decode("utf-8")

    if payload == 'getimage':
        if curr_frame is None:
            return

        jpeg = base64.b64encode(curr_frame).decode('utf-8')
        image_payload = {'timestamp':curr_timestamp.isoformat(timespec='milliseconds').replace("+00:00", "Z"), 'id':instance_id, 'image':jpeg}
        mqttc.publish(image_topic, json.dumps(image_payload))

mqttc = mqtt.Client()
mqttc.on_connect = on_connect
mqttc.on_message = on_message
mqttc.username_pw_set(mqtt_username,mqtt_password)

if args.get('mqtt_tls'):
    mqttc.tls_set(cert_reqs=ssl.CERT_NONE)
    mqttc.tls_insecure_set(True)

mqttc.connect(mqtt_address, int(mqtt_port), 60)
mqttc.subscribe(command_topic, 0)

# Limit OpenCV thread pool
cv2.setNumThreads(args['threads'])

vcap = cv2.VideoCapture()
status = vcap.open(args['input'])

# Test for camera stream
if not status:
    print('Failed to open video stream... quitting!')
    quit()

print('Start video capture...')

mqttc.loop_start()

while(1):
    status, img = vcap.read()

    if not status:
        # Loop video is applicable
        if not args.get('loop'):
            print('No more frames available... Quitting!')
            quit()

        vcap.set(cv2.CAP_PROP_POS_FRAMES, 0)
        status, img = vcap.read()

        if not status:
            quit()

    # Scale if requested
    if args.get('width') and args.get('height'):
        img = cv2.resize(img, (args.get('width'), args.get('height')))

    # Encode frame to JPEG
    ret, curr_frame = cv2.imencode(".jpg", img)
    height, width, channels = img.shape
    jpg = base64.b64encode(curr_frame).decode('utf-8')

    curr_timestamp = datetime.now(timezone.utc)
    timestamp_str = curr_timestamp.isoformat(timespec='milliseconds').replace("+00:00", "Z")

    mqtt_payload = {"timestamp":timestamp_str,"id":instance_id,"height":height,"width":width,"frame":jpg}
    mqttc.publish(mqtt_topic, json.dumps(mqtt_payload))
