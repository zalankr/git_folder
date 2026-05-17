#!/bin/bash
cd /var/log
sudo yum clean all
sudo rm -rf /var/cache/yum
sudo find ~/.cache/ -type f -atime +14 -delete
sudo find /var/log -name "*.log" -ctime +14 -exec rm -f {} \;
sudo find ./mail* -ctime +14 -exec rm -f {} \;
sudo find ./cron* -ctime +14 -exec rm -f {} \;
sudo find ./message* -ctime +14 -exec rm -f {} \;
sudo find ./secure* -ctime +14 -exec rm -f {} \;
sudo find ./spooler* -ctime +14 -exec rm -f {} \;
sudo journalctl --vacuum-time=14d
sudo rm -rf /home/ec2-user/.cache/*
sudo rm -rf /root/.cache/*