ARG BUILD_FROM=ghcr.io/home-assistant/base:latest
FROM ${BUILD_FROM}

WORKDIR /app

# Install runtime dependencies (tzdata fuer korrekte lokale Tagesgrenzen via zoneinfo)
RUN apk add --no-cache \
    python3 \
    py3-pip \
    tzdata

# Install Python package dependencies
COPY requirements.txt /app/requirements.txt
RUN pip3 install --no-cache-dir --break-system-packages -r /app/requirements.txt

# Copy app source
COPY app /app/app
COPY run.sh /run.sh
RUN chmod +x /run.sh

EXPOSE 8099

CMD ["/run.sh"]