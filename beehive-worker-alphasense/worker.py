#!/usr/bin/env python3
import json
import pika
import os
import struct

RABBITMQ_HOST = os.environ.get('RABBITMQ_HOST', 'rabbitmq')
RABBITMQ_PORT = int(os.environ.get('RABBITMQ_PORT', '5672'))
RABBITMQ_USERNAME = os.environ.get('RABBITMQ_USERNAME', 'worker_alphasense')
RABBITMQ_PASSWORD = os.environ.get('RABBITMQ_PASSWORD', 'worker')
BEEHIVE_DEPLOYMENT = os.environ.get('BEEHIVE_DEPLOYMENT', '/')


def decode_alphasense(data):
    bincounts = struct.unpack_from('<16H', data, offset=0)
    pmvalues = struct.unpack_from('<3f', data, offset=50)

    values = {
        'bins': ','.join(map(str, bincounts)),
        'pm1': pmvalues[0],
        'pm2.5': pmvalues[1],
        'pm10': pmvalues[2],
    }

    return values


def callback(ch, method, properties, body):
    if properties.type == 'histogram':
        values = decode_alphasense(body)

        props = pika.BasicProperties(
            app_id=properties.app_id,
            timestamp=properties.timestamp,
            reply_to=properties.reply_to,
            type='histogram',
            content_type='text/json',
        )

        ch.basic_publish(properties=props,
                         exchange='plugins-out',
                         routing_key=method.routing_key,
                         body=json.dumps(values))

    ch.basic_ack(delivery_tag=method.delivery_tag)


connection = pika.BlockingConnection(pika.ConnectionParameters(
    host=RABBITMQ_HOST,
    port=RABBITMQ_PORT,
    virtual_host=BEEHIVE_DEPLOYMENT,
    credentials=pika.PlainCredentials(
        username=RABBITMQ_USERNAME,
        password=RABBITMQ_PASSWORD,
    ),
    connection_attempts=10,
    retry_delay=3.0))

channel = connection.channel()

plugin = 'alphasense:1'
channel.queue_declare(queue=plugin, durable=True)
channel.queue_bind(queue=plugin, exchange='plugins-in', routing_key=plugin)
channel.basic_consume(callback, queue=plugin, no_ack=False)
channel.start_consuming()
