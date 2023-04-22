import math
import os
import sys
import random
import time
import json
import pika
import requests
from datetime import datetime

API_SERVER = "http://localhost:5000"
LINK_RELATIONS = "/sensorhub/link-relations/"
BROKER_ADDR = 'localhost'

channel = None

def calculate_stats(data):
    # sleep a random amount of time to simulate longer processign time.
    time.sleep(random.randint(5, 60))
    return {
        "mean": math.fsum(data) / len(data)
    }
    
def send_notification(href, sensor):
    channel.basic_publish(
        exchange="notifications",
        routing_key="",
        body=json.dumps({
            "task": "statistics",
            "sensor": sensor,
            "@namespaces": {
                "senhub": {"name": API_SERVER + LINK_RELATIONS}
            },
            "@controls": {
                "senhub:stats": {
                    "href": href,
                    "title": "View stats"
                }
            }
        })
    )

def log_error(message):
    channel.basic_publish(
        exchange="logs",
        routing_key="",
        body=json.dumps({
            "timestamp": datetime.now().isoformat(),
            "content": message
        })
    )
    
def handle_task(channel, method, properties, body):
    print("Handling task")
    try:
        # try to parse data and return address from the message body
        task = json.loads(body)
        data = task["data"]
        sensor = task["sensor"]
        href = API_SERVER + task["@controls"]["edit"]["href"]
    except (KeyError, json.JSONDecodeError) as e:
        log_error(f"Task parse error: {e}")
    else:
        # calculate stats
        stats = calculate_stats(task["data"])
        stats["generated"] = datetime.now().isoformat()
    
        # send the results back to the API
        with requests.Session() as session:
            resp = session.put(
                href,
                json=stats
            )
    
        if resp.status_code != 204:
            # log error 
            log_error(f"Unable to send result")
        else:
            send_notification(href, sensor)
    finally:
        # acknowledge the task regardless of outcome
        print("Task handled")
        channel.basic_ack(delivery_tag=method.delivery_tag)

def main():
    global channel
    connection = pika.BlockingConnection(pika.ConnectionParameters(BROKER_ADDR))
    channel = connection.channel()
    channel.exchange_declare(
        exchange="notifications",
        exchange_type="fanout"
    )
    channel.exchange_declare(
        exchange="logs",
        exchange_type="fanout"
    )
    channel.queue_declare(queue="stats")
    channel.basic_consume(queue="stats", on_message_callback=handle_task)
    print("Service started")
    channel.start_consuming()
    
if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        try:
            sys.exit(0)
        except SystemExit:
            os._exit(0)
