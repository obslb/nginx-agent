# this is nginx with automatical monitoring if conf.d has been changed and auto master restart
# Pull base image
FROM python:3.10.4-buster as build-system
COPY install-nginx-debian.sh /
RUN bash /install-nginx-debian.sh

EXPOSE 80
# Expose 443, in case of LTS / HTTPS
EXPOSE 443


# Set environment varibles
# If this is set to a non-empty string,
# Python won’t try to write .pyc files on the import of source modules.
# This is equivalent to specifying the -B option.
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
ENV PIP_NO_CACHE_DIR 0

RUN set -ex &&  pip3 install --no-cache-dir --upgrade pip pycryptodomex watchdog websockets tldextract redis jinja2 dnspython && mkdir -p /app

WORKDIR /app
# -- Adding Pipfiles
ONBUILD COPY Pipfile Pipfile
ONBUILD COPY Pipfile.lock Pipfile.lock
ONBUILD RUN set -ex && pipenv install --deploy --system -v


### create the runtime image ###
FROM build-system as runtime

# Install Supervisord and LetsEncrypt
RUN apt-get update && apt-get install -y supervisor letsencrypt \
&& rm -rf /var/lib/apt/lists/*
# Custom Supervisord config
COPY supervisord-debian.conf /etc/supervisor/conf.d/supervisord.conf

# Copy start.sh script that will check for a /app/prestart.sh script and run it before starting the app
COPY start.sh /start.sh
RUN chmod +x /start.sh

# Copy the entrypoint that will generate Nginx additional configs
COPY  docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh


WORKDIR /app
COPY ./src /app
RUN chmod +x /app/nginx-agent.py


ENTRYPOINT ["/docker-entrypoint.sh"]

# Run the start script, it will check for an /app/prestart.sh script (e.g. for migrations)
# And then will start Supervisor, which in turn will start Nginx and uWSGI
CMD ["/start.sh"]