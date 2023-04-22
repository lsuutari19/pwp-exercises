import json
import sys
import pika
import requests
import ssl
context = ssl.create_default_context()
context.check_hostname = False
context.verify_mode = ssl.CERT_NONE

API_SERVER = "API SERVER"
API_KEY = "api key"
BROKER_ADDR = 'rabbitmq addr'
host = "rabbitmq addr"
port = 5672
virtual_host = "{group}-vhost"
sensor = ""

headers = {
    "Pwp-Api-Key": API_KEY
}

class StopListening(Exception):
    pass


def notification_handler(ch, method, properties, body):
    print("notification_handling...")
    try:
        data = json.loads(body)
        href = data["@controls"]["pwpex:get-certificate"]["href"]
        print(data)
        certificate_file_name = "certificate.json"
        response = requests.get(href, headers=headers, verify=False)
        certificate_data = response.json()
        print(certificate_data)
        with open(certificate_file_name, "w") as f:
            json.dump(certificate_data, f)
        print(f"Certificate saved to {certificate_file_name}")
        sys.exit(0)
    except Exception as e:
        print(f"Error processing notification: {e}")


def listen_notifications():
    global channel

    username = 'webdevmaniac'
    password = 'password'
    vhost = 'webdevmaniac-vhost'
    credentials = pika.PlainCredentials(username, password)

    connection = pika.BlockingConnection(pika.ConnectionParameters(
        host,
        port,
        vhost,
        credentials,
        ssl_options=pika.SSLOptions(context)
    ))
    
    channel = connection.channel()
    channel.exchange_declare(
        exchange="notifications",
        exchange_type="fanout"
    )
    result = channel.queue_declare(queue="", exclusive=True)
    channel.queue_bind(
        exchange="notifications",
        queue=result.method.queue
    )
    channel.basic_consume(
        queue=result.method.queue,
        on_message_callback=notification_handler,
        auto_ack=True
    )
    channel.start_consuming()


if __name__ == "__main__":
    response = requests.post('https://86.50.230.115/api/groups/webdevmaniac/certificates/', headers=headers, verify=False)
    if response.status_code == 202:
        print("POSTED")
        listen_notifications()
    else:
        print(f'Request failed with status code {response.status_code}')
        sys.exit(1)

