#!/bin/sh

PID=$(ps aux | grep "python GBot" | grep -v grep | awk '{print $2}')
kill -9 $PID