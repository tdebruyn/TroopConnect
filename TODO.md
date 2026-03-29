# TroopConnect TODO

Feature implementation roadmap derived from [UserFlows.md](UserFlows.md). Each task includes required tests (Python unit/integration + Playwright E2E).

---

## 1. Implement onboarding flow (first-login profile completion)
**Spec:** UserFlows 1.2

After signup/email verification, redirect to mandatory profile completion page. User selects account type (Parent, Animateur, Animé), fills name/address/phone, accepts GDPR/media consent. Middleware enforces completion before accessing other pages.

**Tests:**
- [x] Python: middleware blocks unprofiled users from protected views
- [x] Python: onboarding form validates required fields (first_name, last_name, primary_role)
- [x] Python: successful submission sets Person.status = "a" and redirects to homepage
- [x] Playwright: new signup redirects to onboarding page (not homepage)
- [x] Playwright: onboarding page shows account type radio buttons, name, address, phone, consent
- [x] Playwright: submitting valid form redirects to homepage
- [x] Playwright: navigating to profile without completing onboarding redirects back to onboarding

---

## 2. Fix social login: link accounts & fix Facebook button
**Spec:** UserFlows 1.1

When social login email matches an existing local account, prompt to link. Fix Facebook login (currently dead `#!` href). Improve social signup template.

**Tests:**
- [x] Python: social login with existing email triggers link prompt (not duplicate account)
- [x] Python: Facebook provider configuration is valid
- [x] Playwright: Google login button navigates to OAuth flow
- [x] Playwright: Facebook login button navigates to OAuth flow (not dead link)

---

## 3. Build Agenda/Event system (model, views, Celery cleanup)
**Spec:** UserFlows 4

Create Event model. Future events display normally, past events (≤30 days) in gray. Auto-delete events older than 30 days via Celery.

**Tests:**
- [x] Python: Event model creation with required fields
- [x] Python: events older than 30 days are deleted by cleanup task
- [x] Python: events within 30 days are not deleted but marked as past
- [x] Playwright: agenda page shows future events
- [x] Playwright: past events (≤30 days) appear in muted/gray style

---

## 4. Enhance messaging: drafts, attachments, rich text, Celery dispatch
**Spec:** UserFlows 3

Fix permissions: animateurs can only send to their section, only staff d'unité (secondary role ar/ad) can send to all. Add draft status. Rich text editor for body. File attachments (max 10MB, UUID link in email). School year selector. Move dispatch to Celery task. Staff sees all logs.

**Tests:**
- [x] Python: animateur cannot access compose-all (404)
- [x] Python: staff d'unité can access compose-all
- [x] Python: animateur can view their sent history
- [x] Python: animateur history hides "send to all" button
- [ ] Python: message can be saved as draft (not sent)
- [ ] Python: attachment upload rejects files >10MB
- [ ] Python: dispatch creates Celery task instead of synchronous send
- [ ] Python: staff user can see all message logs
- [ ] Playwright: compose page shows "Save draft" and "Send" buttons
- [ ] Playwright: file upload field appears on compose page
- [ ] Playwright: staff sees all sent messages in history

---

## 5. Build financial management (household billing, payments, reminders)
**Spec:** UserFlows 5

Household = child's address. Eldest pays full fee, siblings get discount, animateurs flat rate. Late penalty. Trésorier payment entry. Bulk reminder emails with `{prénom}` and `{solde}`.

**Tests:**
- [x] Python: household grouping by child address
- [x] Python: eldest child charged full fee, younger siblings discounted
- [x] Python: animateurs/staff pay flat rate (no sibling discount)
- [x] Python: late payment penalty applied after deadline
- [x] Python: bulk reminder sends to all adults with unpaid balance
- [x] Playwright: Trésorier can access payment entry form
- [x] Playwright: Cotisations nav link leads to billing page (not dead link)

---

## 6. Implement automated Passage (May 1st section transition)
**Spec:** UserFlows 6.1

Celery task on May 1st processes all Animé members. Auto-assign next section based on age/branch. Exceeding oldest branch → role changes to Animateur, removed from household billing.

**Tests:**
- [x] Python: child aging out of branch moves to next branch
- [x] Python: child stays in branch when within age range
- [x] Python: child exceeding oldest branch changes role to Animateur
- [x] Python: aged-out child is removed from parent household
- [x] Python: child with manual next_section override respects the override
- [x] Python: manual override is cleared after use
- [x] Python: alphabetically first section chosen when multiple exist
- [x] Python: archived children are skipped
- [x] Python: children without birthday are skipped
- [x] Python: no next school year returns early

---

## 7. Implement data retention (auto-delete archived users after 5 years)
**Spec:** UserFlows 6.2

Celery task deletes users archived for 5+ consecutive years. Notification email sent 1 month before deletion.

**Tests:**
- [x] Python: users archived >5 years are deleted by task
- [x] Python: users archived <5 years are not deleted
- [x] Python: notification email sent 1 month before deletion date
- [x] Python: no email sent if user archived <4 years 11 months
- [x] Python: active users not deleted
- [x] Python: archived users without date not deleted
- [x] Python: notification falls back to own account if no parent

---

## 8. Build Documents Importants feature
**Spec:** UserFlows 7.1

Model for important documents/links managed via Django Admin. Authenticated users browse them. Wire up dead "Mes documents" navbar link.

**Tests:**
- [x] Python: Document model CRUD via admin
- [x] Python: only authenticated users can list documents
- [x] Playwright: "Mes documents" link navigates to document list
- [x] Playwright: document list shows title and link

---

## 9. Fix navigation menu (dead links, stub sections dropdown)
**Spec:** UserFlows 7.1, navigation

Sections dropdown → dynamic section links. Cotisations → billing page. Mes documents → documents page.

**Tests:**
- [x] Python: sections context processor provides all sections to base template
- [x] Playwright: Sections dropdown shows actual section names (not "First Item")
- [x] Playwright: Cotisations link navigates to billing page
- [x] Playwright: Mes documents link navigates to documents page

---

## 10. Align secret key with spec (6-char vs full UUID)
**Spec:** UserFlows 2.1

Spec says 6-character key (first 6 of UUID). Implementation uses full UUID. Decide and align.

**Tests:**
- [x] Python: secret key is 6 characters (if changing to match spec)
- [x] Python: linking child by 6-char key resolves to correct Person
- [x] Python: 6-char prefix collision handling
- [x] Playwright: child list displays 6-char key (if changed)

---

## 11. Add Animé self-service profile editing (restricted fields)
**Spec:** UserFlows 2.2

Animés (age 12+) can log in, see messages/agenda, update Totem/Email/Phone, but not Address.

**Tests:**
- [x] Python: Animé role user can update totem, email, phone
- [x] Python: Animé role user cannot update address
- [ ] Playwright: Animé profile page shows editable totem/email/phone fields
- [ ] Playwright: Animé profile page shows address as read-only

---

## 12. Enhance admin user list (filters, school year toggle)
**Spec:** UserFlows 7.2

Filters: Name, Role, Birth Year, Section. School Year toggle for Current/Past/Next year assignments.

**Tests:**
- [x] Python: filter by name returns matching persons
- [x] Python: filter by role returns persons with that role
- [x] Python: school year toggle returns correct enrollments for selected year
- [ ] Playwright: filter form applies and updates member list
- [ ] Playwright: year toggle switches displayed section assignments
