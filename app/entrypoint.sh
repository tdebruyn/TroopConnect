#!/bin/sh

# Wait for postgres
echo "Waiting for postgres..."
sleep 5

# Collect static files
echo "Collecting static files..."
python manage.py collectstatic --noinput

# Apply database migrations
echo "Applying database migrations..."
python manage.py migrate

# Start server
echo "Starting server..."
gunicorn troopconnect.wsgi:application --bind 0.0.0.0:9000 --workers 4 --timeout 120
