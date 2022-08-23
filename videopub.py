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
import pybase64
import queue
import simplejpeg
import ssl
import threading
import time
from datetime import datetime, timezone

parser = argparse.ArgumentParser(description='Video Publisher')

parser.add_argument('--input',required=False, default='/dev/video0', help='Specify the video input')
parser.add_argument('--loop', default=False, action='store_true', help='Loop input video')
parser.add_argument('--topic', required=False, default='videopub/stream', help='Specify the MQTT topic')
parser.add_argument('--id', required=True, help='Unique stream identifier for MQTT topic')
parser.add_argument('--width', required=False, help='Specify desired input image width', type=int)
parser.add_argument('--height', required=False, help='Specify desired input image height', type=int)
parser.add_argument('--frame_rate', required=False, default=0, help='Limit frame rate of input', type=int)
parser.add_argument('--threads', required=False, help='Limit CPU usage for camera processing', default=4, type=int)
parser.add_argument('--mqtt_address', required=False, default='localhost',  help='MQTT broker address. default: localhost')
parser.add_argument('--mqtt_port', required=False, default=1883, help='MQTT port. default: 1883')
parser.add_argument('--mqtt_username', required=False, default='',  help='MQTT username.')
parser.add_argument('--mqtt_password', required=False, default='',  help='MQTT password.')
parser.add_argument('--mqtt_tls', default=False, action='store_true', help='use TLS communication for MQTT')
parser.add_argument('--perf_stats', default=False, action='store_true', help='Print performance statistics')
parser.add_argument('--debug', default=False, action='store_true', help='Print debug information')
parser.add_argument('--hw', default=False, action='store_true', help='Use hardware acceleration if available')
args = vars(parser.parse_args())

instance_id = args.get('id')
topic = args.get('topic')
scale_width = args.get('width')
scale_height = args.get('height')
frame_rate = args.get('frame_rate')
mqtt_address = args.get('mqtt_address')
mqtt_port = args.get('mqtt_port')
mqtt_username = args.get('mqtt_username')
mqtt_password = args.get('mqtt_password')
num_threads = args.get('threads')
perf_stats = args.get('perf_stats')
debug = args.get('debug')
hwaccel = args.get('hw')

mqtt_topic = ''.join([topic, "/", instance_id])

def frame_worker():
    global curr_frame, curr_timestamp

    while True:
        data = q.get()

        timestamp = data[0]
        key_frame = data[1]
        frame = data[2]

        # Scale if requested
        if scale_width and scale_height:
            frame = cv2.resize(frame, (scale_width, scale_height))

        # Encode frame to JPEG
        height, width, channels = frame.shape

        if perf_stats:
            start_time = time.perf_counter()

        jpg = simplejpeg.encode_jpeg(
            frame,
            quality=85,
            colorspace='BGR',
            colorsubsampling='420',
            fastdct=True,
        )

        jpg = pybase64.b64encode(jpg).decode('utf-8')

        if perf_stats:
            end_time = time.perf_counter()
            duration = (end_time - start_time) * 1000
            print('Processing time: {:.2f} ms; speed {:.2f} fps'.format(round(duration, 2), round(1000 / duration, 2)))

        timestamp_str = timestamp.isoformat(timespec='milliseconds')

        mqtt_payload = {"dtype":"image/jpeg", "timestamp":timestamp_str,"src_id":instance_id,"height":height,"width":width,"data":jpg}
        mqttc.publish(mqtt_topic, json.dumps(mqtt_payload), qos=0, retain=False)

        q.task_done()

#
# Create MQTT client
#

def on_connect(mqttc, obj, flags, rc):
    print("MQTT connected...")

mqttc = mqtt.Client()
mqttc.on_connect = on_connect
mqttc.username_pw_set(mqtt_username,mqtt_password)

if args.get('mqtt_tls'):
    mqttc.tls_set(cert_reqs=ssl.CERT_NONE)
    mqttc.tls_insecure_set(True)

mqttc.connect(mqtt_address, int(mqtt_port), 60)

# Limit OpenCV thread pool
cv2.setNumThreads(num_threads)

# Initialise worker queue
q = queue.Queue(maxsize=0)

vcap = cv2.VideoCapture()
status = vcap.open(args['input'], cv2.CAP_ANY, (cv2.CAP_PROP_HW_ACCELERATION, cv2.VIDEO_ACCELERATION_ANY if hwaccel else cv2.VIDEO_ACCELERATION_NONE))

print("Using video backend:", vcap.getBackendName())

# Test for camera stream
if not status:
    print('Failed to open video stream... quitting!')
    quit()

#Starting worker threads
for i in range(num_threads):
    worker = threading.Thread(target=frame_worker, daemon=True)
    worker.start()

# Calculate frame rate timeout
if frame_rate > 0:
    frame_rate = 1 / frame_rate

print('Start video capture...')

mqttc.loop_start()

while(1):
    start_time = time.perf_counter()
    status, frame = vcap.read()

    if not status:
        # Loop video is applicable
        if not args.get('loop'):
            print('No more frames available... Quitting!')
            quit()

        vcap.set(cv2.CAP_PROP_POS_FRAMES, 0)
        status, frame = vcap.read()

        if not status:
            quit()

    timestamp = datetime.now(timezone.utc)

    q.put( (timestamp, vcap.get(cv2.CAP_PROP_LRF_HAS_KEY_FRAME), frame) )

    end_time = time.perf_counter()
    duration = (end_time - start_time)
    timeout = max(0, (frame_rate - duration))
    time.sleep(timeout)

