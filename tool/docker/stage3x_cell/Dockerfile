# Image of the MAP stage 3 EXPLORATION cell (exploration-grade isolation, see orch/map_s3x_cell.py): the local M image (rtl tool, iverilog, sudo) without the architecture products,
# with the allowlist program as the only sudo rule. build.sh flattens the result. Local build only.
ARG BASE=lora-rtl:v5.5-probea-20261110
FROM ${BASE}
USER root
RUN rm -rf /opt/resources /opt/skills /opt/pilot_tools /var/rtl /tmp/ip_work /state /workspace /code /app /srv /home/ubuntu /etc/sudoers.d/rtl \
 && find /root /var/tmp /tmp -mindepth 1 -delete 2>/dev/null; ls /opt; true
COPY rtl.s3 /opt/rtl/rtl.s3
COPY sudoers.rtl /etc/sudoers.d/rtl
COPY rtl.user /usr/local/bin/rtl
RUN chown -R root:root /usr/local /venv && chmod -R go-w /usr/local /venv \
 && chown root:root /opt/rtl/rtl.s3 /etc/sudoers.d/rtl /usr/local/bin/rtl && chmod 700 /opt/rtl/rtl.s3 && chmod 440 /etc/sudoers.d/rtl && chmod 755 /usr/local/bin/rtl && ls -ld /opt/rtl/* /usr/local/bin
COPY align_values.py /opt/s3/align_values.py
COPY align_values.sh /usr/local/bin/align_values
COPY align_values.s3 /opt/s3/align_values.s3
RUN chown root:root /opt/s3 /opt/s3/align_values.py /opt/s3/align_values.s3 /usr/local/bin/align_values && chmod 755 /opt/s3 /usr/local/bin/align_values && chmod 644 /opt/s3/align_values.py && chmod 700 /opt/s3/align_values.s3
USER agent
