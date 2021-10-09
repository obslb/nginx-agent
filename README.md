### Commands

- upgrade your system, and remove all webservers;

``` bash
$ apt update -y && apt dist-upgrade -y && apt autoremove --purge -y apache2 nginx && apt install -y git
```

- Install and setup agent;

```bash
$ chmod +x ./install.sh && ./install.sh '["NGINX UPSTREAMS"]' '["WSS:URLS"]' 'TOKEN'
```