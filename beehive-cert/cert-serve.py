#!/usr/bin/env python
import web
import os.path
import subprocess
import threading
import re
import sys
import logging
import pprint
import time
from os import listdir
from os.path import isdir, join
from mysql import Mysql

formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - line=%(lineno)d - %(message)s')

handler = logging.StreamHandler(stream=sys.stdout)
handler.setFormatter(formatter)

logger = logging.getLogger(__name__)
logger.addHandler(handler)
logger.setLevel(logging.DEBUG)


def ensure_dirs(path):
    try:
        os.makedirs(path)
    except:
        pass


httpserver_port = 80

resource_lock = threading.RLock()

script_path = '/usr/lib/waggle/beehive-server/beehive-cert/SSL/'
ssl_dir = '/usr/lib/waggle/SSL/'
ssl_nodes_dir = os.path.join(ssl_dir, 'nodes')

ensure_dirs(ssl_nodes_dir)

authorized_keys_file = os.path.join(ssl_nodes_dir, 'authorized_keys')

db = None


def read_file(path):
    with open(path, 'r') as file:
        return file.read().strip()


urls = (
    '/certca', 'certca',
    '/node/?', 'newnode',
    '/', 'index'
)

app = web.application(urls, globals())

class index:
    def GET(self):
        return 'This is the Waggle certificate server.'

class certca:
    def GET(self):
        try:
            return read_file(os.path.join(ssl_dir, 'waggleca/cacert.pem'))
        except FileNotFoundError:
            return 'error: cacert file not found !?'


def validate_query_string(s):
    return s.startswith('?')


def validate_node_id_string(s):
    return re.match('[0-9A-F]{16}$', s) is not None


class newnode:

    def GET(self):
        query = web.ctx.query

        if not validate_query_string(query):
            logger.info('GET newnode - Invalid query string "{}"'.format(query))
            return 'error: Invalid query string "{}".\n'.format(query)

        nodeid = query.lstrip('?').upper()

        if not validate_node_id_string(nodeid):
            logger.error('GET newnode - Invalid node ID string "{}".'.format(nodeid))
            return 'error: Invalid node ID string "{}".\n'.format(nodeid)

        logger.info('GET newnode - Preparing to register "{}".'.format(nodeid))

        node_dir = os.path.join(ssl_nodes_dir, 'node_' + nodeid)

        ##### Got node_id #####
        if not os.path.isdir(node_dir):
            with resource_lock:
                logger.info('Call create_client_cert.sh')

                subprocess.call([
                    os.path.join(script_path, 'create_client_cert.sh'),
                    'node',
                    os.path.join('nodes/', 'node_' + nodeid),  # BUG create_client_cert.sh already prefixes path...
                ])

                logger.info('OK')

                time.sleep(1)

                logger.info('Append')
                append_command = 'cat {} >> {}'.format(os.path.join(node_dir, 'key_rsa.pub'), authorized_keys_file)
                print "command: ", append_command
                # manual recreaetion of authorized_keys file:
                # cat node_*/key_rsa.pub > authorized_keys
                subprocess.call(append_command, shell=True)

                logger.info('chmod')
                chmod_cmd = "chmod 600 {0}".format(authorized_keys_file)
                print "command: ", chmod_cmd
                subprocess.call(chmod_cmd, shell=True)
                # manual recreation of authorized_keys file:
                # cat node_*/key_rsa.pub > authorized_keys

        privkey = read_file(os.path.join(node_dir, 'key.pem'))
        cert = read_file(os.path.join(node_dir, 'cert.pem'))
        key_rsa_pub_file_content = read_file(os.path.join(node_dir, 'key_rsa.pub'))

        db = Mysql( host="beehive-mysql",
                        user="waggle",
                        passwd="waggle",
                        db="waggle")

        mysql_row_node = db.get_node(nodeid)

        if not mysql_row_node:
            port=db.createNewNode(nodeid)
            if not port:
                print "Error: Node creation failed"
                return "Error: Node creation failed"
            mysql_row_node = db.get_node(nodeid)

        port = int(db.find_port(nodeid))

        if not port:
            logger.error("Error: port number not found !?")
            return "Error: port number not found !?"

        return privkey + "\n" + cert + "\nPORT="+str(port) + "\n" + key_rsa_pub_file_content + "\n"


if __name__ == "__main__":
    node_database = {}

    # get all public keys from disk
    for d in listdir(ssl_nodes_dir):
        if isdir(join(ssl_nodes_dir, d)) and d[0:5] == 'node_':
            rsa_pub_filename =  os.path.join(ssl_nodes_dir, d, 'key_rsa.pub')
            try:
                with open(rsa_pub_filename, 'r') as rsa_pub_file:
                    data=rsa_pub_file.read()
                    node_id = d[5:].upper()
                    node_database[node_id] = {}
                    node_database[node_id]['pub']=data
            except Exception as e:
                logger.error("Error reading file %s: %s" % (rsa_pub_filename, str(e)))

    print str(node_database)



    db = Mysql( host="beehive-mysql",
                user="waggle",
                passwd="waggle",
                db="waggle")

    # get port: for node_id SELECT reverse_ssh_port FROM nodes WHERE node_id='0000001e06200335';
    # get all ports:


    for row in db.query_all("SELECT * FROM nodes"):
        print row

    # get nodes and ports from database
    for row in db.query_all("SELECT node_id,reverse_ssh_port FROM nodes"):
        print row

        node_id = row[0].upper()

        if not node_id in node_database:
            logger.warning("Node %s is in database, but no public key was found")
            node_database[node_id] = {}

        try:
            port = int(row[1])
        except:
            port = None

        if port:
            node_database[node_id]['reverse_ssh_port']=port
        else:
            logger.warning("node %s has no port assigned" % (node_id))

    # explicit check for consistency
    for node_id in node_database:
        #logger.debug("node_id: %s" % (node_id))
        if not 'reverse_ssh_port' in node_database[node_id]:
            logger.warning("Node %s has public key, but no port number is assigned in database." % (node_id))

    pp = pprint.PrettyPrinter(indent=4)
    pp.pprint(node_database)

    auth_options = 'no-X11-forwarding,no-agent-forwarding,no-pty'
    registration_script =\
      '/usr/lib/waggle/beehive-server/beehive-sshd/register.sh'
    registration_key_filename =\
      '/usr/lib/waggle/ssh_keys/id_rsa_waggle_aot_registration.pub'
    with open(registration_key_filename) as registration_key_file:
      registration_key = registration_key_file.readline().strip()
    new_authorized_keys_content =['command="%s",%s %s\n\n' \
      % (registration_script, auth_options, registration_key)]

    for node_id in node_database.keys():
        line=None
        if 'pub' in node_database[node_id]:
            if 'reverse_ssh_port' in node_database[node_id]:
                port = node_database[node_id]['reverse_ssh_port']
                permitopen = 'permitopen="localhost:%d"' % (port)
                line="%s,%s %s" % (permitopen, auth_options, node_database[node_id]['pub'])
            else:
                # add public keys without port number, but comment the line
                permitopen = 'permitopen="localhost:?"'
                line="#%s,%s %s" % (permitopen, auth_options, node_database[node_id]['pub'])
        else:
            logger.warning("Node %s has no public key" % (node_id))

        if line:
            logger.debug(line)
            new_authorized_keys_content.append(line)

    # create new authorized_keys file on every start, just to be sure.
    with open(authorized_keys_file, 'w') as file:
        for line in new_authorized_keys_content:
            file.write("%s\n" % line)

    subprocess.call(['chmod', '600', authorized_keys_file])


    web.httpserver.runsimple(app.wsgifunc(), ("0.0.0.0", httpserver_port))
    app.run()
