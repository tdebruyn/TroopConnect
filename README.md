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

## E2E Test Users (local)

The following users are seeded for Playwright end-to-end tests. Password for all: `Test1234!`

| Role | Email |
|------|-------|
| Parent | parent1@test.be |
| Parent | parent2@test.be |
| Animateur | anim1@test.be |
| Staff (Admin) | staff1@test.be |
