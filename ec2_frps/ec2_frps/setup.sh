#!/bin/sh

# Friendly name
echo "frps" > /etc/hostname
sysctl kernel.hostname=${REG}-frps

# Enable and start service
mkdir /etc/frp/
wget https://github.com/fatedier/frp/releases/download/v0.35.1/frp_0.35.1_linux_amd64.tar.gz
tar xvf frp_0.35.1_linux_amd64.tar.gz -C /lib/systemd/system/ frp_0.35.1_linux_amd64/systemd/frps.service --strip-components=2
tar xvf frp_0.35.1_linux_amd64.tar.gz -C /usr/bin/ frp_0.35.1_linux_amd64/frps --strip-components=1

cat<<EOF >/etc/frp/frps.ini
[common]
dashboard_port = 7500
dashboard_user = admin
dashboard_pwd = PASSWORD
bind_port = 7000
EOF

chmod +x /usr/bin/frps
systemctl enable frps.service
systemctl start frps.service
rm frp_0.35.1_linux_amd64.tar.gz

# Install htop
yum install -y htop

# Forwarding network
echo "net.ipv4.ip_forward=1" >> /etc/sysctl.conf
sysctl -p
