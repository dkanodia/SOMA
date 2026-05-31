#!/bin/bash
set -e
ssh-keygen -A
/usr/sbin/sshd -D &
exec python3 /soma_agent.py
