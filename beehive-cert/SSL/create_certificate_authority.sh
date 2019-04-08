#!/bin/bash
# ANL:waggle-license
#  This file is part of the Waggle Platform.  Please see the file
#  LICENSE.waggle.txt for the legal details of the copyright and software
#  license.  For more details on the Waggle project, visit:
#           http://www.wa8.gl
# ANL:waggle-license

SSL_DIR="/usr/lib/waggle/SSL"
CA_DIR="${SSL_DIR}/waggleca"

create_ca_dir() {
	mkdir -p $CA_DIR
	chmod 755 $CA_DIR
	cd $CA_DIR

	# Make appropriate folders
	mkdir -p certs private
	chmod 700 private

	if [ ! -f serial ]; then
		echo 01 > serial
	fi

	touch index.txt

	# this is needed for "node" certificates. We may change that later.
	echo "unique_subject = no" > index.txt.attr

	cp /usr/lib/waggle/beehive-server/beehive-cert/SSL/waggleca/openssl.cnf openssl.cnf
}

create_ca_key_if_needed() {
	cd $CA_DIR

	if [ -f "private/cakey.pem" ]; then
		echo "CA key already exists."
	else
		echo "Creating CA key."
		openssl genrsa -out $CA_DIR/private/cakey.pem 2048
		rm -f $CA_DIR/cacert.pem
		rm $CA_DIR/certs/*
	fi
}

create_ca_cert_if_needed() {
	cd $CA_DIR

	if [ -f "cacert.pem" ]; then
		echo "CA certificate already exists."
	else
		echo "Creating CA certificate."

		openssl req \
			-new \
			-x509 \
			-key private/cakey.pem \
			-days 3650 \
			-out cacert.pem \
			-outform PEM \
			-subj /CN=waggleca/ \
			-sha256
			# openssl req -new -x509 -key private/cakey.pem -days 3650 -out cacert.pem -outform PEM -subj /CN=waggleca/ -sha256
			# openssl x509 -in cacert.pem -out cacert.cer -outform DER
	fi
}

create_ca_dir
create_ca_key_if_needed
create_ca_cert_if_needed
