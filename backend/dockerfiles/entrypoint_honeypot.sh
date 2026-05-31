#!/bin/bash
set -e
ssh-keygen -A
/usr/sbin/sshd -D &
nginx -g 'daemon off;' &
python3 /honeypot_server.py &
exec python3 /soma_agent.py
