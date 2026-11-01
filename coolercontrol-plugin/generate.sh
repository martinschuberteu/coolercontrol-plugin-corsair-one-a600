#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Regenerate the gRPC Python code in corsair-a600/gen/ from proto/ (needs python-grpcio-tools).
set -euo pipefail
cd "$(dirname "$0")"
rm -rf corsair-a600/gen
mkdir -p corsair-a600/gen
python3 -I -m grpc_tools.protoc -I proto \
    --python_out=corsair-a600/gen --grpc_python_out=corsair-a600/gen \
    $(cd proto && find coolercontrol -name '*.proto' | sort)
echo "Generated $(find corsair-a600/gen -name '*.py' | wc -l) files"
