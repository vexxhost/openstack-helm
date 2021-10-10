#!/bin/bash

#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

set -xe

#NOTE: Get the over-rides to use
: ${OSH_EXTRA_HELM_ARGS_HORIZON:="$(./tools/deployment/common/get-values-overrides.sh horizon)"}

#NOTE: Lint and package chart
make horizon

#NOTE: Deploy command
: ${OSH_EXTRA_HELM_ARGS:=""}
helm upgrade --install horizon ./horizon \
    --namespace=openstack \
    --set network.node_port.enabled=true \
    --set network.node_port.port=31000 \
    ${OSH_EXTRA_HELM_ARGS} \
    ${OSH_EXTRA_HELM_ARGS_HORIZON}

#NOTE: Wait for deploy
./tools/deployment/common/wait-for-pods.sh openstack

# Delete the test pod if it still exists
kubectl delete pods -l application=horizon,release_group=horizon,component=test --namespace=openstack --ignore-not-found
helm test horizon
