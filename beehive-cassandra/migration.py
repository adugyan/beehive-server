#!/usr/bin/env python3

# docker run -ti --net beehive -e CQLSH_HOST=beehive-cassandra --rm -v /storage/temp/:/storage/temp/:rw python:3 /bin/bash
# pip install --upgrade pip
# pip install cassandra-driver


# This script migrates waggle tables in cassandra to another cassandra instance. Since all tables use the same 
# partiton key (node_id, date), we can use the same migration function for each table. Only the insert queries differ. 

# note 1: the field date is of type date in table data_messages_v2, but in older tables it is of type ascii.

# note 2: The query "SELECT DISTINCT node_id,date ... FROM <table>" fails sometimes. Use cqlsh to run this command manually and hit space to go trough all pages.
#          It seem that will put the result into a cache and then the python library can do the same query successfully. 
#          (There is probably a better way to get this to work without this ugly work-around, but I did not bother digging into this further.) 


from cassandra.cluster import Cluster, BatchStatement
import json
import sys
import os
import time

def migrate_waggle_table(source_host, target_host, table_name, insert_query):
    
    
    #schema

    #node_id ascii,
    #date ascii,
    #plugin_name ascii,
    #plugin_version ascii,
    #plugin_instance ascii,
    #timestamp timestamp,
    #parameter ascii,
    #data ascii,
    #ingest_id int,
    #PRIMARY KEY ((node_id, date), plugin_name, plugin_version, plugin_instance, timestamp, parameter)


    cluster = Cluster([source_host])
    session = cluster.connect('waggle')
    

    cluster2 = Cluster([target_host])
    target_session = cluster2.connect('waggle')

    # get 
    

    query = 'SELECT * FROM {} WHERE node_id=%s AND date=%s;'.format(table_name)
    count_query = 'SELECT COUNT(*) FROM {} WHERE node_id=%s AND date=%s;'.format(table_name)

    delete_query='DELETE FROM {} WHERE node_id=%s AND date=%s;'.format(table_name)

    prepared_insert_query = target_session.prepare(insert_query)


    status = {"year_skip":0, "already_complete":0, "completed":0, "format_skip":0}

    node_days_query = 'SELECT DISTINCT node_id,date FROM {}'.format(table_name)
    print(node_days_query)
    node_days = session.execute(node_days_query)

    loop_count = 0
    for row in node_days:
        node_id = row.node_id
        row_date = row.date

        loop_count += 1

        #if loop_count < 37700:
        #    status["already_complete"]+=1
        #    continue

        if loop_count % 100 == 0:
            print("loop_count: {}".format(loop_count))
            print(json.dumps(status))

        if not ( len(node_id) == 12 or len(node_id) == 16) :
            print("skipping wrong node_id format {}".format(node_id))
            status["format_skip"] += 1
            continue

        row_date_year = 0

        if table_name == "data_messages_v2":
            row_date_year = row_date.date().year
        else:
            
            row_date_array = row_date.split("-")

            if len(row_date_array) != 3:
                print("skipping wrong date format {}".format(row_date))
                status["format_skip"] += 1
                continue

            row_date_year = int(row_date_array[0])
        

        #if row_date_year >= 2020:
        #    print("skipping data from this year")
        #    status["year_skip"] += 1
        #    continue


        #print(node_id)
        #print(row_date)
        

        

        source_count_rows=session.execute(count_query, [node_id,row_date ])
        source_count = source_count_rows[0].count
        #print(source_count)

        if source_count == 0:
            print("empty source")
            continue

        target_count_rows=target_session.execute(count_query, [node_id,row_date ])
        target_count = target_count_rows[0].count

        if source_count == target_count:
            status["already_complete"]+=1
            
            continue

        while target_count > 0:
            print("detected partial migration: {} {}".format(node_id, row_date))
            print("source_count: {}".format(source_count))
            print("target_count: {}".format(target_count))
            
            target_session.execute(delete_query, [node_id,row_date ])
            time.sleep( 2 )
            target_count_rows=target_session.execute(count_query, [node_id,row_date ])
            target_count = target_count_rows[0].count

            time.sleep( 3 )
            
 
        source_rows=session.execute(query, [node_id,row_date ])


        batch_insert = BatchStatement()


        insert_count = 0
        for row in source_rows:
            insert_array = list(row)
            #print(insert_array)
            batch_insert.add(prepared_insert_query , insert_array)
            #target_session.execute( prepared_insert_query , insert_array )
            insert_count += 1

            if insert_count >= 10000:
                target_session.execute( batch_insert )
                print("in {}".format(insert_count))
                batch_insert = BatchStatement()
                insert_count = 0
        
        #print("prepared {} rows for batch insert".format(insert_count))
        target_session.execute( batch_insert )

        print("in {}".format(insert_count))
        status["completed"]+=1
        
        
    
    print("loop_count: {}".format(loop_count))
    print(json.dumps(status))
    print(" ----------- finished")


    



tables={'sensor_data_raw':{} , 'data_messages_v2': {}, 'sensor_data':{} }

tables['sensor_data_raw']['insert_query']=\
    """
    INSERT INTO sensor_data_raw (node_id, date, plugin_name, plugin_version, plugin_instance, timestamp, parameter, data, ingest_id)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """

tables['data_messages_v2']['insert_query']=\
    """
    INSERT INTO data_messages_v2 (node_id, date, plugin_id, plugin_version, timestamp, data, plugin_instance)
    VALUES (?, ?, ?, ?, ?, ?, ?)
    """


tables['sensor_data']['insert_query']=\
    """
    INSERT INTO sensor_data (node_id, date, plugin_id, plugin_version, plugin_instance, timestamp, sensor, data, sensor_meta)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """



#migrate_waggle_table('beehive-cassandra' , 'beehive-data.cels.anl.gov', 'sensor_data_raw', tables['sensor_data_raw']['insert_query'])

#migrate_waggle_table('beehive-cassandra' , 'beehive-data.cels.anl.gov', 'data_messages_v2', tables['data_messages_v2']['insert_query'])

migrate_waggle_table('beehive-cassandra' , 'beehive-data.cels.anl.gov', 'sensor_data', tables['sensor_data']['insert_query'])
