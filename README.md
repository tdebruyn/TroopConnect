TODO

1. http://127.0.0.1:8000/users/adminlist
   => update section
2. Création d'une nouvelle année
3. Assignation de la section année+1
4. Effacer année - 5
5. Créer un évènement
6. Pièces jointes et liens
7. Cotisations
8. Ajouter les liens importants

Starting REDIS
redis-server /opt/homebrew/etc/redis.conf
celery -A siteunite worker -l INFO
celery -A siteunite beat -l INFO --scheduler django_celery_beat.schedulers:DatabaseScheduler

mail sender:
https://www.mailersend.com

Nom de domaine:
tomctl.be

Registrar: regery.com
Hosting: contabo.com

Terraform

Docker
