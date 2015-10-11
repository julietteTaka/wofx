#!/bin/bash

echo "Starting mongodb"
(/opt/mongodb/bin/mongod --dbpath /opt/mongo-data > /opt/logs/mongo.log 2>&1) &

echo "Starting Analyzer"
(python ${SHUTTLEOFX_DEV}/shuttleofx_analyser/views.py > /opt/logs/analyser.log 2>&1) &
echo "Starting Render"
(python ${SHUTTLEOFX_DEV}/shuttleofx_render/views.py > /opt/logs/render.log 2>&1) &
echo "Starting Catalog"
(python ${SHUTTLEOFX_DEV}/shuttleofx_catalog/views.py > /opt/logs/catalog.log 2>&1) &
echo "Starting Client"
(python ${SHUTTLEOFX_DEV}/shuttleofx_client/views.py > /opt/logs/client.log 2>&1) &
echo "END"

wait
