import argparse
from glob import glob
import hashlib
import datetime
import os
import gzip
import multiprocessing
import subprocess
import time
import publishing
import pprint


def read_file(filename):
    with open(filename, 'rb') as file:
        return file.read()


def read_compressed_file(filename):
    return gzip.decompress(read_file(filename))


def ensure_dir(filename):
    os.makedirs(os.path.dirname(filename), exist_ok=True)


def hash_dependencies(filenames):
    hash = hashlib.sha1()

    for filename in sorted(filenames):
        with open(filename, 'rb') as file:
            hash.update(file.read())

    return hash.digest()


# rename checkpoint -> digest
def get_checkpoint(target):
    try:
        with open(target + '.checkpoint', 'rb') as file:
            return file.read()
    except FileNotFoundError:
        return bytes()


def set_checkpoint(target, hash):
    ensure_dir(target)

    with open(target + '.checkpoint', 'wb') as file:
        file.write(hash)


# NOTE Safer to just do simple listdir rather than walk?
def find_data_files(top, rel=''):
    for entry in os.scandir(top):
        if entry.is_dir():
            yield from find_data_files(entry, os.path.join(rel, entry.name))
        if entry.is_file() and entry.name.endswith('.csv.gz'):
            yield os.path.join(rel, entry.name)


# NOTE Simpler to just enumerate nodes and then check dates?
def find_data_files_for_project(data_dir, project_metadata):
    # node_dirs = set(os.listdir(data_dir)) & {node['node_id'] for node in project_metadata}
    #
    # for node in node_dirs:
    #     for date in ...
    nodes_by_id = {node['node_id']: node for node in project_metadata}

    def isvalid(file):
        node_id, date = file.rstrip('.csv.gz').split('/')
        date = datetime.datetime.strptime(date, '%Y-%m-%d')
        return (node_id in nodes_by_id and
                any(date in interval for interval in nodes_by_id[node_id]['commissioned']))

    return filter(isvalid, find_data_files(data_dir))


def update_filtered_files(data_dir, build_dir, project_dir):
    project_metadata = publishing.load_project_metadata(project_dir)
    sensor_metadata = publishing.load_sensor_metadata(os.path.join(project_dir, 'sensors.csv'))

    tasks = []

    for file in find_data_files_for_project(data_dir, project_metadata):
        target = os.path.join(build_dir, file)
        dependencies = [os.path.join(data_dir, file)]
        configs = [
            os.path.join(project_dir, 'sensors.csv'), # maybe allow to depend on flag?
        ]
        tasks.append((target, dependencies, configs))

    with multiprocessing.Pool() as pool:
        pool.starmap(update_filtered_file_if_needed, tasks)


def update_filtered_file_if_needed(target, dependencies, configs):
    hash = hash_dependencies(dependencies)
    # hash = hash_dependencies(dependencies + configs)

    if get_checkpoint(target) == hash:
        return

    print('make', target)
    start = time.time()
    update_filtered_file(target, dependencies)
    print('done', target, time.time() - start)
    set_checkpoint(target, hash)


def update_filtered_file(target, dependencies):
    ensure_dir(target)

    with open(target, 'wb') as outfile:
        for source in dependencies:
            lines = read_compressed_file(source).splitlines()

            # drop header from staged data
            if lines[0].startswith(b'timestamp'):
                lines = lines[1:]

            lines.sort()
            data = b'\n'.join(lines)
            outfile.write(gzip.compress(data))


def update_date_files(data_dir, build_dir, project_dir):
    project_metadata = publishing.load_project_metadata(project_dir)

    configs = []

    date_dependencies = {}

    for file in find_data_files_for_project(data_dir, project_metadata):
        target = os.path.join(build_dir, os.path.basename(file))

        if target not in date_dependencies:
            date_dependencies[target] = []

        date_dependencies[target].append(os.path.join(data_dir, file))

    tasks = []

    for target, dependencies in sorted(date_dependencies.items(), reverse=True):
        tasks.append((target, dependencies, configs))

    # NOTE May want to adapt based on available memory, not just processors.
    with multiprocessing.Pool() as pool:
        pool.starmap(update_date_file_if_needed, tasks)


def update_date_file_if_needed(target, dependencies, configs):
    hash = hash_dependencies(dependencies)
    # hash = hash_dependencies(dependencies + configs)

    if get_checkpoint(target) == hash:
        return

    print('make', target)
    start = time.time()
    update_date_file(target, dependencies)
    print('done', target, time.time() - start)
    set_checkpoint(target, hash)


# NOTE Should be able to implement a streaming merge as follows:
#
# 1. read all n compressed in memory streams
# 2. heapify first lines
# 3. repeat:
#      1. pop heap min line from heap
#      2. write min line to compressed out stream
#      3. get next line from min line's in stream
#
# should run in O(#lines * log(#files))
#
def update_date_file(target, dependencies):
    rows = []

    for source in dependencies:
        rows.extend(read_compressed_file(source).splitlines())

    rows.sort()

    # ensure blank line at end
    rows.append(b'')
    data = gzip.compress(b'\n'.join(rows))

    ensure_dir(target)

    with open(target, 'wb') as file:
        file.write(data)


# NOTE faster to cat rather than check if needed
def update_combined_file(data_dir, build_dir):
    target = os.path.join(build_dir, 'data.csv.gz')
    dependencies = [os.path.join(data_dir, file) for file in sorted(find_data_files(data_dir))]

    print('make', target)
    start = time.time()

    with open(target, 'wb') as file:
        # restore header to final result
        header = b'timestamp,node_id,subsystem,sensor,parameter,value_raw,value_hrf\n'
        file.write(gzip.compress(header))

        for dep in dependencies:
            file.write(read_file(dep))

    print('done', target, time.time() - start)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('data_dir')
    parser.add_argument('build_dir')
    # parser.add_argument('project_dir')
    args = parser.parse_args()

    data_dir = os.path.abspath(args.data_dir)
    build_dir = os.path.abspath(args.build_dir)
    # project_dir = os.path.abspath(args.project_dir)
    filtered_dir = os.path.join(build_dir, 'filtered')
    dates_dir = os.path.join(build_dir, 'dates')

    project_dir = '/Users/Sean/beehive-server/publishing-tools/projects/AoT_Chicago.complete'

    update_filtered_files(data_dir, filtered_dir, project_dir)
    update_date_files(filtered_dir, dates_dir, project_dir)
    update_combined_file(dates_dir, build_dir)
