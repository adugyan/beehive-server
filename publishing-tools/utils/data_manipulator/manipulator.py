#! /usr/bin/python3

import os
import time
import argparse
from csv import DictReader, DictWriter


def grep(values, keywords):
    count = 0
    for keyword in keywords:
        for value in values:
            if keyword in value:
                count = count + 1
                break
    if len(keywords) == count:
        return True
    else:
        return False


def fill_lookup(add_fields, source_path, keys):
    lookup_table = {}
    with open(source_path, 'r') as source_file:
        csv_handler = DictReader(source_file)

        # Sanitize header field
        headers = csv_handler.fieldnames.copy()
        remove_fields = []
        for field in add_fields:
            if field not in headers:
                print('[WARNING] field %s not exist in %s' % (field, source_path))
                remove_fields.append(field)
        for field in remove_fields:
            add_fields.remove(field)

        for row in csv_handler:
            key = []
            for field in keys:
                key.append(row[field])
            key = tuple(key)
            if key not in lookup_table:
                lookup_table[key] = {}

            for field in add_fields:
                lookup_table[key][field] = row[field]
    return add_fields, lookup_table


def load_lookups(add_op, nodes_path, sensors_path):
    nodes_add_fields = []
    sensors_add_fields = []
    for field in add_op:
        sp = field.strip().split('.')
        if len(sp) != 2:
            print('[ ERROR ] Could not parse the operation: %s' % (field,))
            continue
        if 'node' in sp[0]:
            nodes_add_fields.append(sp[1])
        elif 'sensor' in sp[0]:
            sensors_add_fields.append(sp[1])
        else:
            print('[ ERROR ] Failed to recognize %s' % (sp[0],))

    if len(nodes_add_fields) > 0:
        nodes_add_fields, node_lookup_table = fill_lookup(nodes_add_fields, nodes_path, keys=['node_id'])

    if len(sensors_add_fields) > 0:
        sensors_add_fields, sensor_lookup_table = fill_lookup(sensors_add_fields, sensors_path, keys=['sensor', 'parameter'])        

    return nodes_add_fields, node_lookup_table, sensors_add_fields, sensor_lookup_table


def perform(input_path, output_path, grep_op, cut_op, add_op, nodes_path, sensors_path):
    if add_op != []:
        nodes_lookup_header, nodes_lookup, sensors_lookup_header, sensors_lookup = load_lookups(add_op, nodes_path, sensors_path)

    with open(output_path, 'w') as output:
        # csv_output = DictWriter(output)
        with open(input_path, 'r') as file:
            csv_handler = DictReader(file)

            # Add operation
            headers = csv_handler.fieldnames.copy()
            for node_add_op_header in nodes_lookup_header:
                if node_add_op_header not in headers:
                    headers.append(node_add_op_header)
            for sensors_add_op_header in sensors_lookup_header:
                if sensors_add_op_header not in headers:
                    headers.append(sensors_add_op_header)

            # Cut operation
            for cut_field in cut_op:
                if cut_field in headers:
                    headers.remove(cut_field)

            csv_output = DictWriter(output, headers)
            csv_output.writeheader()
            for row in csv_handler:
                # Grep operation
                if grep(list(row.values()), grep_op) is False:
                    continue

                # Get values from the input row
                output_row = {}
                for header in headers:
                    if header in row:
                        output_row[header] = row[header]

                # Add nodes app_op fields to the output row
                key = row['node_id']
                if len(nodes_lookup_header) > 0:
                    if key in nodes_lookup:
                        for node_add_op_header in nodes_lookup_header:
                            output_row[node_add_op_header] = nodes_lookup[key][node_add_op_header]

                # Add sensors app_op fields to the output row
                key = (row['sensor'], row['parameter'])
                if len(sensors_lookup_header) > 0:
                    if key in sensors_lookup:
                        for sensor_add_op_header in sensors_lookup_header:
                            output_row[sensor_add_op_header] = sensors_lookup[key][sensor_add_op_header]


                csv_output.writerow(output_row)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Manipulate csv dataset')
    parser.add_argument('-i', '--input', dest='input')
    parser.add_argument('-o', '--output', dest='output')
    parser.add_argument('-g', '--grep', dest='grep_op')
    parser.add_argument('-c', '--cut', dest='cut_op')
    parser.add_argument('-a', '--add', dest='add_op')
    
    args = parser.parse_args()
    if not os.path.exists(args.input):
        print('[ ERROR ] Input file path is invalid.')
        exit(1)
    input_path = args.input

    if args.output is None:
        print('[WARNING] Output file is not specified.')
        print('[ INFO  ] Output will be output.csv')
        output_path = './output.csv'
    else:
        output_path = args.output

    if args.grep_op is None and args.cut_op is None and args.add_op is None:
        print('[ ERROR ] No manipulation is provided')
        parser.print_help()
        exit(1)

    grep_op = []
    cut_op = []
    add_op = []
    nodes_path = None
    sensors_path = None
    if args.grep_op is not None:
        grep_op = args.grep_op.strip().split(' ')
    if args.cut_op is not None:
        cut_op = args.cut_op.strip().split(' ')
    if args.add_op is not None:
        add_op = args.add_op.strip().split(' ')

    if args.add_op != []:
        base_path = os.path.dirname(input_path)
        if base_path == '':
            base_path = './'
        if os.path.exists(os.path.join(base_path, 'nodes.csv')):
            nodes_path = os.path.join(base_path, 'nodes.csv')
        else:
            print('[WARNING] nodes.csv not exist under %s. Ignore \"nodes.*\" operations...' % (base_path,))

        if os.path.exists(os.path.join(base_path, 'sensors.csv')):
            sensors_path = os.path.join(base_path, 'sensors.csv')
        else:
            print('[WARNING] sensors.csv not exist under %s. Ignore \"sensors.*\" operations...' % (base_path,))

    start_t = time.time()
    perform(
        input_path,
        output_path,
        grep_op,
        cut_op,
        add_op,
        nodes_path=nodes_path,
        sensors_path=sensors_path
    )
    end_t = time.time()
    print('[ INFO  ] took %.2f seconds for the manipulation' % ((end_t - start_t),))