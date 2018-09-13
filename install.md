<!--
waggle_topic=/beehive/installation
-->

# Beehive Deployment Guide

## System Requirements

### Docker

We'll assume Docker CE (Community Edition) version 17.01 or later (_check minimal version_) is installed on the system.

Docker provides their own installation guides for various system configurations. [Here](https://docs.docker.com/install/linux/docker-ce/ubuntu/#install-from-a-package) is a link to the guide for Ubuntu. 

## Deployment Instructions

### Checkout Beehive Server Repo

First, we'll ensure we have the latest code:

```
git clone https://github.com/waggle-sensor/beehive-server
cd beehive-server
```

### Deploy Containers

Next, we'll specify a deployment directory and spin up all the containers. The deployment directory holds 1. Databases 2. Nodes Keys 3. Beehive Keys 4. RMQP data. If you remove this directory you loose all persistent stuff. The incoming data from the nodes also gets stored under this directory. :

```
export BEEHIVE_ROOT=/path/to/deploy/into
./do.sh deploy
```

### Perform Initial Setup of Containers

Now, we perform some one-time configuration of our containers:

```
./do.sh setup
```

You should be prompted for a RabbitMQ server admin password during this
process. Remember to choose this password wisely. You can always rerun
this step if you forget the password.

## Issues and Todo Items

### Registration keys should configurable

Right now, a default registration public key is used for node registration. I
think it makes sense to allow for a special dev key.
