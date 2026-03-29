# Scout Unit Management System: Detailed User Flows & Logic

## 1. Unauthenticated & Authentication Flow

### 1.1 Public Access

- **Landing Page:** Access to Home, FAQ, Agenda (public view), and Section descriptions.
- **Registration:** Users can create an account via:
  - Local Email/Password.
  - Social Login (Google/Facebook).
  - _Logic:_ If a local email matches a social login email, the system must prompt to link them.
- **Verification:** Users must confirm their email via a sent link before full access is granted.

### 1.2 Onboarding (First Login)

- **Profile Setup:** Users are redirected to a mandatory profile completion page.
- **Account Types:** Users must select one: **Parent**, **Animateur**, or **Animé**.
- **Fields:** Name, Address, Phone, GDPR/Media Consent (Boolean).

---

## 2. Roles, Sections, and The "Secret Key"

### 2.1 The Secret Key System

- **Generation:** Every "Animé" (child) profile generates a 6-character unique key (first 6 characters of a UUID).
- **Linking:** A Parent can link an existing child to their profile by entering this secret key.
- **Ownership:** Multiple parents can link to the same child.

### 2.2 Role-Specific Constraints

- **Animé:** Can log in (if age 12+) to see messages and agenda. They can update their Totem, Email, and Phone, but **cannot** change their Address (must match the Parent).
- **Animateur:** Adult leaders assigned to sections.
- **Staff d'Unité:** A special, non-editable section. Members (e.g., Trésorier, Animateur Responsable) have elevated permissions to manage the whole unit.
- **Archive:** A dummy section for members who have left.

---

## 3. Communication & Messaging System

### 3.1 Message Creation

- **Fields:** Title, Body (Rich Text), School Year Selector (Previous, Current, Next), Attachments.
- **Draft Status:** Users can save messages as "Draft" or "Send."
- **Attachments:** Maximum 10MB per file. Files are stored on the server. The outgoing email contains a unique UUID link to the file rather than the file itself.

### 3.2 Recipient Logic & Dispatch

- **Targeting:** Users select a Section or Role. The system filters members based on their status during the selected School Year.
- **Exclusion List:** Before sending, the UI must display a list of all recipients (First Name, Last Name, Role, Email). The sender can manually uncheck individuals to exclude them.
- **Execution:** Dispatch is handled via a **Celery** task.
- **Logs:** A persistent log is maintained.
  - _Staff:_ Can see all logs.
  - _Animateurs:_ Can see only logs for messages sent to their section.

---

## 4. The Agenda & Event Lifecycle

### 4.1 UI Rules

- **Future Events:** Displayed normally.
- **Recent Past Events:** Events that occurred within the last 30 days are displayed in **gray** (scale/muted).
- **Automatic Cleanup:** Events older than 30 days are automatically deleted from the database/view via a daily Celery task.
- **Integration:** Messages sent with a defined "Date" field automatically create a corresponding entry in the section’s Agenda.

---

## 5. Financial Management (Offline Tracking)

### 5.1 Household Calculation

- **Anchor:** The **Child’s Address** defines the "Household Unit."
- **Billing Rule:** - The eldest child in a household pays the full fee (100%).
  - Younger siblings in the same household receive a **Sibling Discount**.
  - **Animateurs/Staff** pay a flat individual rate (exempt from sibling discounts).
- **Penalties:** If a balance is unpaid after a specific "Late Date," a percentage penalty is automatically added to the total.

### 5.2 Management Tools

- **Payment Entry:** Trésorier manually records payments (Amount, Date).
- **Reminders:** Bulk tool to send emails to all adults in a household with unpaid balances. Templates must support variables like `{prénom}` and `{solde}`.

---

## 6. System Lifecycle & Maintenance

### 6.1 The "Passage" (May 1st)

On May 1st, an automated Celery task processes all "Animé" members:

1. Check `Prochaine section`. If empty, calculate based on age/branch.
2. If child exceeds current Branch age:
   - Move to next Branch.
   - If multiple sections exist in that branch, assign to the **alphabetically first** section.
3. If child exceeds the oldest Branch (Pionniers):
   - Change Role to **Animateur**.
   - Remove from parent household for billing.

### 6.2 Data Retention

- **Archive Delete:** Users in the "Archive" section for 5 consecutive years are permanently deleted.
- **Notification:** An automated email is sent to the user/parent 1 month before deletion occurs.

---

## 7. Navigation & Admin Views

### 7.1 User Menu

- Top-right dropdown (Authenticated):
  - **Profil:** Edit personal data.
  - **Documents Importants:** Links managed via Django Admin.
  - **Déconnexion:** Logout.

### 7.2 Admin User List

- View all users with filters: Name, Role, Birth Year, Section.
- **School Year Toggle:** Admins can view the section assignments for "Current," "Past," or "Next" years to see historical or projected data.
