### Commands

- setup and install all dependencies;
``` bash
$ /usr/bin/nginx-agent setup --upstreams "" --connect_url "" --connect_token "" --reconfigure
```

- connect and run app;
``` bash
$ /usr/bin/nginx-agent run --debug --connect_url "" --connect_token ""
```
- letsecrypt manual-auth-hook;
``` bash
$ /usr/bin/nginx-agent acme_auth
```
- letsecrypt deploy-hook;
``` bash
$ /usr/bin/nginx-agent acme_deploy
```


- run install script, this will install all dependencies;
```text
    $ ./install.sh
```

- configure nginx and setup new upstream server;
```text
 $ ./nginx-agent.py install --upstream mydomain.com --reconfigure
```

- create systemctl service config file, also replace with your data --connect_url and --connect_token;
```text
# nano /etc/systemd/system/nginx-agent.service
[Unit]
Description=NginxAgent
Wants=network-online.target
After=network-online.target

[Service]
Type=simple
Restart=always
User=root
Group=root
WorkingDirectory=/srv/nginx-agent/
ExecStart=/usr/bin/python3.8 nginx-agent.py run --debug --connect_url "wss://cpanel.mydomain.com/websocket/vps/agents/" --connect_token "SUPERSECRET_TOKEN"

[Install]
WantedBy=multi-user.target
```
- make this service boot on startup;
  
```text
  $ systemctl enable nginx-agent
```

- run nginx-agent service;
  
```text
  $ systemctl start nginx-agent
```

