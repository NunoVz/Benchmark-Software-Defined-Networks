FROM ubuntu:22.04
ENV DEBIAN_FRONTEND=noninteractive PIP_DISABLE_PIP_VERSION_CHECK=1
# Make venv the default PATH for everything that follows
ENV VENV=/opt/venv
ENV PATH="$VENV/bin:${PATH}"

# Base OS + tooling
RUN set -eux; \
    printf 'Acquire::ForceIPv4 "true";\nAcquire::Retries "5";\n' > /etc/apt/apt.conf.d/99force-ipv4; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
        ca-certificates software-properties-common gnupg \
        iproute2 iputils-ping net-tools tcpdump ethtool \
        openvswitch-switch openvswitch-common \
        python3 python3-venv python3-dev python3-pip build-essential \
        sudo curl git vim; \
    ln -sf /usr/bin/python3 /usr/bin/python; \
    rm -rf /var/lib/apt/lists/*

# Python venv (can see system site-packages => imports mininet installed via apt)
RUN set -eux; \
    python3 -m venv --system-site-packages "$VENV"; \
    "$VENV/bin/pip" install --no-cache-dir --upgrade pip

# Mininet via apt (fallback to source if apt fails)
RUN set -eux; \
    apt-get update || true; \
    if ! apt-get install -y --no-install-recommends mininet; then \
        echo "Apt mininet not available; installing from source..."; \
        rm -rf /var/lib/apt/lists/*; \
        git clone --depth=1 https://github.com/mininet/mininet.git /opt/mininet; \
        ln -s /opt/mininet/bin/mn /usr/local/bin/mn; \
        ln -s /opt/mininet/util/m /usr/local/bin/m || true; \
        ln -s /opt/mininet/util/mnexec /usr/local/bin/mnexec || true; \
    else \
        rm -rf /var/lib/apt/lists/*; \
    fi

# (Optional but recommended) Install Python deps from your repo's requirements.txt
# Keep this before copying the rest so Docker caches it when reqs don't change.
WORKDIR /opt/Mininet
COPY requirements.txt /tmp/requirements.txt
RUN /opt/venv/bin/pip install --no-cache-dir -r /tmp/requirements.txt


# Helper scripts
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh 
ENTRYPOINT ["/entrypoint.sh"]
