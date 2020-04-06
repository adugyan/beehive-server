#!/usr/bin/env python3
# ANL:waggle-license
#  This file is part of the Waggle Platform.  Please see the file
#  LICENSE.waggle.txt for the legal details of the copyright and software
#  license.  For more details on the Waggle project, visit:
#           http://www.wa8.gl
# ANL:waggle-license
import argparse
from cassandra.cluster import Cluster
import csv
import datetime
import pika
import sys
import waggle.protocol
import os
import logging

logging.basicConfig(level=logging.INFO)


cassandra_host = os.environ.get('CASSANDRA_HOST')


cluster = Cluster([cassandra_host])
session = cluster.connect('waggle')

session.execute('''
CREATE TABLE IF NOT EXISTS waggle.data_messages_v2 (
  node_id text,
  date date,
  plugin_id int,
  plugin_version text,
  plugin_instance int,
  timestamp timestamp,
  data blob,
  PRIMARY KEY ((node_id, date), plugin_id, plugin_version, timestamp, data)
)
''')

insert_query = session.prepare('''
INSERT INTO waggle.data_messages_v2
(date, node_id, plugin_id, plugin_version, plugin_instance, timestamp, data)
VALUES (?, ?, ?, ?, ?, ?, ?)
''')

# session.execute('''
# CREATE TABLE IF NOT EXISTS waggle.measurements_by_date (
#   date date,
#   timestamp timestamp,
#   node_id text,
#   subsystem text,
#   sensor text,
#   parameter text,
#   value text,
#   PRIMARY KEY ((node_id, date), timestamp, subsystem, sensor, parameter)
# )
# ''')
#
# measurements_by_date = session.prepare('''
# INSERT INTO measurements_by_date
# (date, timestamp, node_id, subsystem, sensor, parameter, value)
# VALUES (?, ?, ?, ?, ?, ?, ?)
# ''')
#
# session.execute('''
# CREATE TABLE IF NOT EXISTS waggle.measurements_by_type (
#   timestamp timestamp,
#   node_id text,
#   subsystem text,
#   sensor text,
#   parameter text,
#   value text,
#   PRIMARY KEY ((node_id, subsystem, sensor, parameter), timestamp)
# )
# ''')
#
# measurements_by_type = session.prepare('''
# INSERT INTO measurements_by_type
# (node_id, subsystem, sensor, parameter, timestamp, value)
# VALUES (?, ?, ?, ?, ?, ?)
# ''')


def stringify_value(value):
    if isinstance(value, bytes):
        return value.hex()
    if isinstance(value, list):
        return ','.join(map(str, value))
    return repr(str(value))


def unpack_messages(body):
    try:
        for message in waggle.protocol.unpack_waggle_packets(body):
            yield message
    except Exception:
        logging.exception('invalid message with body %s', body)


def unpack_messages_datagrams(body):
    for message in unpack_messages(body):
        try:
            for datagram in waggle.protocol.unpack_datagrams(message['body']):
                yield message, datagram
        except Exception:
            node_id = message['sender_id']
            logging.exception(
                'invalid message from node_id %s with body %s', node_id, body)


def unpack_messages_datagrams_sensorgrams(body):
    for message, datagram in unpack_messages_datagrams(body):
        try:
            for sensorgram in waggle.protocol.unpack_sensorgrams(datagram['body']):
                yield message, datagram, sensorgram
        except Exception:
            node_id = message['sender_id']
            plugin_id = datagram['plugin_id']
            plugin_version = get_plugin_version(datagram)
            logging.exception('invalid message from node_id %s plugin %s %s with body %s',
                              node_id, plugin_id, plugin_version, body)


csvout = csv.writer(sys.stdout)


def get_plugin_version(datagram):
    return '{plugin_major_version}.{plugin_minor_version}.{plugin_patch_version}'.format(**datagram)


def message_handler(ch, method, properties, body):
    for message, datagram, sensorgram in unpack_messages_datagrams_sensorgrams(body):
        ts = datetime.datetime.fromtimestamp(sensorgram['timestamp'])
        node_id = message['sender_id']

        plugin_id = datagram['plugin_id']
        plugin_version = get_plugin_version(datagram)
        plugin_instance = datagram['plugin_instance']

        session.execute(
            insert_query,
            (ts.date(), node_id, plugin_id, plugin_version, plugin_instance, ts, body))

        sub_id = message['sender_sub_id']
        sensor = str(sensorgram['sensor_id'])
        parameter = str(sensorgram['parameter_id'])
        value = stringify_value(sensorgram['value'])

        # session.execute(
        #     measurements_by_date,
        #     (ts.date(), ts, node_id, subsystem, sensor, parameter, value))

        # session.execute(
        #     measurements_by_type,
        #     (node_id, subsystem, sensor, parameter, ts, value))

        csvout.writerow([
            ts,
            node_id,
            sub_id,
            plugin_id,
            plugin_version,
            sensor,
            parameter,
            value,
        ])

        sys.stdout.flush()

    ch.basic_ack(delivery_tag=method.delivery_tag)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--url', default='amqp://localhost')
    parser.add_argument('node_id')
    args = parser.parse_args()

    queue = 'to-node-{}'.format(args.node_id)

    connection = pika.BlockingConnection(pika.URLParameters(args.url))
    channel = connection.channel()

    channel.queue_declare(queue=queue, durable=True)
    channel.basic_consume(queue, message_handler)
    channel.start_consuming()


if __name__ == '__main__':
    main()
