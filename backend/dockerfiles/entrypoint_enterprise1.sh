#!/bin/bash
set -e
ssh-keygen -A
/usr/sbin/sshd -D &
redis-server --protected-mode no --daemonize yes
exec python3 /soma_agent.py
