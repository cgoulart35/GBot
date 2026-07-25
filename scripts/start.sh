#!/bin/sh
# Boot launcher for the deploy watcher. Invoked from /etc/rc.local:
#   su - cgoulart -c "sh /home/cgoulart/Code/GBot/scripts/start.sh"
cd /home/cgoulart/Code/GBot || exit 1
mkdir -p Logs
nohup sh scripts/deploy-watcher.sh >> Logs/deploy-watcher.log 2>&1 &
