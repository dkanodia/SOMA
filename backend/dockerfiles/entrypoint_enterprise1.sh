#!/bin/bash
set -e
ssh-keygen -A
/usr/sbin/sshd -D &
redis-server --protected-mode no --daemonize yes
sleep 1
/redis_seed.sh
exec python3 /soma_agent.py
