#!/bin/bash

REPO_DIR="$HOME/Omega"  
PROTO_DIR="$REPO_DIR/Tool"  


echo "Pulling latest changes from Git..."
cd "$REPO_DIR" || { echo "Error: Repo directory not found!"; exit 1; }
git pull origin main || { echo "Error: Git pull failed!"; exit 1; }

echo "Removing old generated gRPC files..."
find "$PROTO_DIR" -name "*_pb2.py" -o -name "*_pb2_grpc.py" -type f -delete || { echo "Error: Failed to delete old gRPC files!"; exit 1; }

echo "Regenerating gRPC files..."
cd "$PROTO_DIR" || { echo "Error: Proto directory not found!"; exit 1; }
for proto_file in *.proto; do
    echo "Processing: $proto_file"
    python3 -m grpc_tools.protoc -I. --python_out=. --grpc_python_out=. "$proto_file" || { echo "Error: Failed to compile $proto_file"; exit 1; }
done

echo "✅ All proto files successfully regenerated!"
