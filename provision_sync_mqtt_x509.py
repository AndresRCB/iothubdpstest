#!python3

import json
import os
import random
import ssl
import sys
import time

import paho.mqtt.client as mqtt

PROVISIONING_HOST = os.environ.get('PROVISIONING_HOST')
PROVISIONING_IDSCOPE = os.environ.get('PROVISIONING_IDSCOPE')
PROVISIONING_PORT = 8883

class DpsMqttClient:
    def __init__(self,
                provisioning_host,
                provisioning_port,
                provisioning_id_scope,
                device_id,
                request_id,
                api_version='2021-06-01') -> None:
        self.provisioning_host = provisioning_host
        self.provisioning_id_scope = provisioning_id_scope
        self.provisioning_port = provisioning_port
        self.device_id = device_id
        self.request_id = request_id
        self.api_version = api_version
        self.username = f'{self.provisioning_id_scope}/registrations/{self.device_id}/api-version={self.api_version}'
        self.receive_topic = '$dps/registrations/res/#'
        self.registration_topic = f'$dps/registrations/PUT/iotdps-register/?$rid={self.request_id}'
        self.assigned_hub = ''
        self.operation_id = ''

        self.mqttc = mqtt.Client(self.device_id, clean_session=True)
        self.mqttc.username_pw_set(self.username)
        self.mqttc.tls_set(certfile=f'certificates/private/{self.device_id}.store.pem',
                        cert_reqs=ssl.CERT_REQUIRED)

    def build_operation_status_topic(self):
        return f'$dps/registrations/GET/iotdps-get-operationstatus/?$rid={self.request_id}&operationId={self.operation_id}'

    def on_log(self, mqttc, obj, level, string):
        print(string)

    def connect(self):
        print(f'Connecting to {self.provisioning_host} on port: {self.provisioning_port}')
        self.mqttc.connect(self.provisioning_host, self.provisioning_port)

    def register(self):
        payload = json.dumps({'registrationId': self.device_id})
        print(f'Publishing: {payload} to topic {self.registration_topic}')
        infot = self.mqttc.publish(self.registration_topic, payload)
        infot.wait_for_publish()

    def poll_operation_status(self):
        operation_status_topic = self.build_operation_status_topic()
        payload = json.dumps({'registrationId': self.device_id})
        print(f'Publishing: {payload} to topic {operation_status_topic}')
        infot = self.mqttc.publish(operation_status_topic, payload)
        infot.wait_for_publish()

    def disconnect(self):
        self.mqttc.disconnect()

    def on_message(self, mqttc, obj, msg):
        # Expect responses on either of these two topics:
        # register request: $dps/registrations/res/202/?$rid={request_id}&retry-after=x
        # operation check:  $dps/registrations/res/200/?$rid={request_id}
        json_payload = json.loads(msg.payload)
        pretty_payload = json.dumps(json_payload, indent=2)
        print(f'Received message on topic {msg.topic} with QoS {str(msg.qos)}. Message payload:\n{pretty_payload}')
        
        if self.operation_id == '':
            # First message: Register operation
            self.operation_id = json_payload['operationId']
        else:
            # Not first message: operation status check
            registration_status = json_payload['status']
            if registration_status != 'assigned':
                print(f'Waiting for device to be assigned. Current status: {registration_status}')
            else:
                self.assigned_hub = json_payload['registrationState']['assignedHub']

    def provision(self):
        self.mqttc.on_log = self.on_log
        self.mqttc.on_message = self.on_message
        self.mqttc.subscribe(self.receive_topic)
        self.mqttc.loop_start()

        self.register()

        for attempt in range(4):
            wait_seconds = pow(2, attempt)
            print(f'Waiting {wait_seconds} seconds for operation ID')
            time.sleep(wait_seconds)
            if self.operation_id != '':
                print(f'Operation ID: {self.operation_id}')
                break

        if self.operation_id == '':
            return 'Operation ID never received; register call failed'

        for attempt in range(4):
            self.poll_operation_status()
            wait_seconds = pow(2, attempt)
            print(f'Waiting {wait_seconds} seconds for operation to complete')
            time.sleep(wait_seconds)
            if self.assigned_hub != '':
                print(f'Assigned endpoint: {self.assigned_hub}')
                break

        if self.assigned_hub == '':
            return "Registration timed out"
        
        return ''

def main():
    if len(sys.argv) < 2:
        print("You must specify the Device ID")
        raise SystemExit(2)

    device_id = sys.argv[1]
    random.seed()
    request_id = random.randrange(1, sys.maxsize)

    client = DpsMqttClient(PROVISIONING_HOST,
                        PROVISIONING_PORT,
                        PROVISIONING_IDSCOPE,
                        device_id,
                        request_id)
    client.connect()
    message = client.provision()
    client.disconnect()

    if message != '':
        print(message)
        raise SystemExit(2)


if __name__ == "__main__":
    main()
