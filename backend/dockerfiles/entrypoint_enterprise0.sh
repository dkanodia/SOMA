#!/bin/bash
set -e
ssh-keygen -A
/usr/sbin/sshd -D &
nginx -g 'daemon off;' &
exec python3 /soma_agent.py
