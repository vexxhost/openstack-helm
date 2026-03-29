#!/bin/bash

{{/*
Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

   http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
*/}}

set -ex
export HOME=/tmp

{{- if and .Values.ceph_client.enable_external_ceph_backend .Values.ceph_client.external_ceph.rbd_user }}
# Handle external Ceph keyring
if [ -n "${EXTERNAL_RBD_USER}" ] && [ -f /tmp/external-ceph-client-keyring ]; then
  cat <<EOF > /etc/ceph/ceph.client.${EXTERNAL_RBD_USER}.keyring
[client.${EXTERNAL_RBD_USER}]
    key = $(cat /tmp/external-ceph-client-keyring)
EOF
fi
{{- end }}

# Handle internal Ceph keyring (only if mounted)
if [ -n "${RBD_USER}" ] && [ -f /tmp/client-keyring ]; then
  cat <<EOF > /etc/ceph/ceph.client.${RBD_USER}.keyring
[client.${RBD_USER}]
    key = $(cat /tmp/client-keyring)
EOF
fi

exit 0
