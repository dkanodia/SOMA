#!/bin/bash
set -e
ssh-keygen -A
/usr/sbin/sshd -D &
vsftpd /etc/vsftpd.conf &
exec python3 /soma_agent.py
