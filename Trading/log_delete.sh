#!/bin/bash
cd /var/log
sudo yum clean all
sudo rm -rf /var/cache/yum
sudo find ~/.cache/ -type f -atime +2 -delete
sudo find /var/log -name "*.log" -ctime +2 -exec rm -f {} \;
sudo find ./mail* -ctime +2 -exec rm -f {} \;
sudo find ./cron* -ctime +2 -exec rm -f {} \;
sudo find ./message* -ctime +2 -exec rm -f {} \;
sudo find ./secure* -ctime +2 -exec rm -f {} \;
sudo find ./spooler* -ctime +2 -exec rm -f {} \;
sudo journalctl --vacuum-size=200M
sudo rm -rf /home/ec2-user/.cache/*
sudo rm -rf /root/.cache/*
