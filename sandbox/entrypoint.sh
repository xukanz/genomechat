#!/bin/bash
set -e

# Create jobs directory with proper permissions
mkdir -p /sandbox/jobs
chown -R runner:runner /sandbox
chmod 755 /sandbox
chmod 755 /sandbox/jobs

# Switch to runner user and run the server
exec gosu runner "$@"

