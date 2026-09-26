# Getting started, from zero

This guide is for someone who has **never run a server before**. It takes you
from "I have a domain name and a credit card" to "my unit's site is online",
one step at a time, explaining the words as they come.

If you have done this before, the short version is in [INSTALL.md](INSTALL.md)
and you should read that instead.

> **TroopConnect is early-stage software.** It has no support contract, and a
> release can change things under you. Read the warning at the top of the
> [README](README.md) before you point a real troop at it. The short version:
> you will be the person who looks after this, so make sure you are comfortable
> copying commands into a terminal and reading what comes back.

## What you are about to do

| | |
| --- | --- |
| **Time** | about an hour, most of it waiting for things to install |
| **Cost** | roughly €5–10 a month for the server, €10–15 a year for the domain name |
| **Skills** | copying and pasting commands into a terminal |
| **Result** | a website at your own address, with its own database and its own email, that nobody else shares |

Nothing here is irreversible. If you get stuck halfway, you can start over. The
one thing to be careful with is deleting "volumes", which is where your data
lives — this guide says so when it comes up.

## The words you will meet

Skim this now and come back when a word shows up later.

| Word | What it means |
| --- | --- |
| **Server** or **VPS** | A computer in a data centre that you rent, which is on all the time. "VPS" means *virtual private server* — a slice of a bigger machine. You never see it; you connect to it over the internet. |
| **Terminal** | The black window where you type commands. On Windows it is **PowerShell**; on Mac it is **Terminal**; on Linux it is also called **Terminal**. |
| **SSH** | How you connect to your server from your own computer. It gives you a command line *on the server*, so what you type happens there, not on your laptop. |
| **IP address** | The server's number, like `203.0.113.45`. Four numbers with dots. Your provider shows it to you after you create the server. |
| **Domain name** | The address people type, like `scoutsdelimal.be`. You rent it yearly from a *registrar*, separately from the server. |
| **DNS** | The system that translates a domain name into an IP address. You set it up by adding a **record** — a little line saying "`scoutsdelimal.be` is at `203.0.113.45`". |
| **Docker** | The program that runs TroopConnect. It downloads ready-made pieces and starts them for you, so you never install Python, a database or a web server by hand. |
| **Container** | One of those pieces while it is running. TroopConnect runs six of them: the website, the database, a worker that sends mail and runs the nightly jobs, a scheduler that wakes it up, a queue the two of them talk through, and the piece that handles HTTPS for you. |
| **Image** | The frozen package a container is started from. TroopConnect publishes its images, so your server downloads them; it never builds anything. |
| **Volume** | A drawer Docker keeps on the server's disk that survives restarts. **Your data lives in volumes.** Deleting a volume deletes the data in it. |
| **`.env` file** | A plain text file with your settings in it — your domain, your mail password. This is the only file you edit. |
| **Certificate / HTTPS** | The padlock in the browser's address bar. TroopConnect gets it automatically, for free, from Let's Encrypt. |

## Step 1 — Rent a server

You are looking for the cheapest tier that is not a toy. Any of these will do:

| What | Value |
| --- | --- |
| Memory | **2 GB** (1 GB works, but is tight) |
| Processor | 1 or 2 cores |
| Disk | 20 GB or more |
| Operating system | **Ubuntu 24.04 LTS** (or 22.04) |
| Location | **in Europe**, ideally your own country |

Some providers you could use, all with European data centres:

| Provider | Notes |
| --- | --- |
| **Hetzner** | Cheapest of these, servers in Germany, Finland and (recently) Singapore. The control panel is plain but functional. |
| **Scaleway** | French, servers in Paris and Amsterdam. Good in French and English. |
| **OVHcloud** | French, many European locations. |
| **Infomaniak** | Swiss, advertises itself on data protection; slightly more expensive. |
| **Contabo** | Cheap, servers in Germany; the control panel is less polished. |
| **DigitalOcean** | Not European (US company, European regions available), but by far the friendliest control panel for a beginner. |

**Choose a European provider if you can.** You are going to store children's
names, addresses and medical notes. Keeping that inside the EU keeps the legal
side of it simple, and it is faster for your families besides.

You do not need to be loyal — moving to another provider later means copying
your data across, which is possible but a chore.

### Creating it

Every provider's control panel does the same four things, with different
words. Look for:

1. **"Create" / "Deploy" / "New server"** — a button, usually top right.
2. **A location picker** — choose the city nearest you.
3. **An image or OS picker** — choose **Ubuntu**, version **24.04 LTS**.
   *Do not* pick one with a control panel (Plesk, cPanel) — you do not need it
   and it costs more.
4. **A type / plan picker** — the smallest plan with 2 GB of memory. Ignore
   everything it offers to add on: no backups service, no extra IP addresses,
   no "managed database". You do not need them.

You will also be asked how you want to log in. You have two options:

- **Password** — the provider shows or emails you a `root` password. Simpler,
  and fine to start with.
- **SSH key** — more secure, and what an experienced operator would choose.
  If you pick this and have never made a key, pick the password instead.

At the end, press the button and wait a minute or two. **Write down two
things**, because everything else depends on them:

- the **IP address** (four numbers with dots),
- the **password** (if you chose one).

> If the provider offers a "firewall" or "security group", make sure incoming
> ports **80** (http) and **443** (https) are allowed — Caddy, the piece
> handling HTTPS, needs them to get your certificate. Port **22** (ssh) must
> stay open too or you will lock yourself out. If you never touch the firewall
> settings, they are usually open by default, which is what you want here.

## Step 2 — Get a domain name

A domain name costs about €10–15 a year. It is **separate from the server**: if
your domain expires, your site disappears even though the server is still
running.

Any registrar works — pick one you can pay and get support in a language you
read. Some are also server providers (OVHcloud, Infomaniak, Scaleway all sell
both, and it is convenient to have one bill).

A `.be` domain needs a Belgian registrant; most European troops use their
country's suffix, or a `.org`.

## Step 3 — Point the domain at your server

This is the step people find most mysterious, and it is only this:

> **You add one line, anywhere your domain's DNS is managed, that says
> "`scoutsdelimal.be` → `203.0.113.45`".**

That line is called an **A record**. From the moment it is saved, anyone typing
your domain reaches your server. (An "AAAA record" is the same thing for the
newer IPv6 numbering; ignore it unless your provider gave you an IPv6 address
too.)

### Where is my DNS managed?

Two arrangements are common, and you need to find out which one you have:

1. **At your registrar** (the usual case). You bought the domain, and the
   registrar's own control panel has the DNS settings. Look in the domain's
   page for a tab or menu called **DNS**, **DNS zone**, **DNS records**,
   **Manage DNS** or **Zone editor**.
2. **At your server provider.** Some hosts manage DNS for you, or let you
   transfer it. If you see **Nameservers** (or *NS*) listed as something like
   `ns1.provider.net`, then whoever owns those nameservers is where your DNS
   lives — often the provider's panel, sometimes a free service like
   Cloudflare.

If you are not sure, ask your registrar's support one question: *"Where do I
edit the A record for my domain?"* They answer this all day.

### Adding the record

In that DNS page, add a record with:

| Field | What to put |
| --- | --- |
| **Type** | `A` |
| **Name** / **Host** | `@` (the `@` means "the domain itself"). Some panels want it left blank or want the full domain spelled out. |
| **Value** / **Points to** / **Address** | your server's IP address |
| **TTL** | leave the default |

Then add a second one, the same but with **Name** = `www`, if you want
`www.scoutsdelimal.be` to work too. (TroopConnect itself does not require it.)

Save, and wait. It is usually 5–30 minutes before the rest of the internet
notices, though it can occasionally take a few hours. You can watch it happen:

```bash
ping scoutsdelimal.be
```

Once it shows your server's IP address instead of an error, you are done with
DNS.

> **Do this before starting TroopConnect.** Caddy asks Let's Encrypt for a
> certificate *for your domain name*, and Let's Encrypt has to check that the
> name really leads to your server. If DNS is not in place yet, that check
> fails and you have to try again later.

## Step 4 — Connect to your server

Open the terminal on your own computer:

- **Windows** — press the Windows key, type `powershell`, press Enter.
- **Mac** — press Cmd+Space, type `terminal`, press Enter.
- **Linux** — you already know where it is.

Type this, replacing the IP address with yours, and press Enter:

```bash
ssh root@203.0.113.45
```

The first time, it asks whether you trust this computer's fingerprint:

```
The authenticity of host '203.0.113.45' can't be established.
ED25519 key fingerprint is SHA256:xxxxxxxxxxxxxxxxxxxxxxxxxxxx.
Are you sure you want to continue connecting (yes/no/[fingerprint])?
```

Type `yes` and press Enter. That question appears once per server; it is your
computer saying "I have not met this machine before".

Then it asks for the password. **Nothing appears while you type it** — no dots,
no stars. That is normal, and it confuses everybody the first time. Type it and
press Enter.

You are connected when the line in front of the cursor changes to something
like:

```
root@ubuntu-2gb-nbg1:~#
```

Everything you type now happens **on the server**, not on your laptop. To leave
again, type `exit`.

> **If it says `Permission denied`** — the password is wrong, or you are using
> the wrong username. Providers on some systems give you a `ubuntu` user
> instead of `root`; the welcome email says which. Try
> `ssh ubuntu@203.0.113.45`.

## Step 5 — Install Docker

You are still connected to the server. Copy this line and press Enter:

```bash
curl -fsSL https://get.docker.com | sh
```

It prints a lot of lines and takes a minute. This is Docker's own installation
script; it sets up everything TroopConnect needs.

Check that it worked by running these two commands:

```bash
docker --version
docker compose version
```

You should get something like `Docker version 28.x.x` and
`Docker Compose version v2.x.x`. If you instead get
`docker: command not found`, the install did not finish — run the `curl` line
again and read the last few lines it printed.

## Step 6 — Install TroopConnect

Still on the server. First fetch the project files:

```bash
apt-get update && apt-get install -y git
git clone https://github.com/tdebruyn/TroopConnect.git
cd TroopConnect
```

Then create your settings file from the template:

```bash
cp .env.example .env
```

Now open it in a text editor. The only editor guaranteed to be on the server is
`nano`, and the only key you need to remember is `Ctrl+O` to save and `Ctrl+X`
to quit:

```bash
nano .env
```

Fill in the four lines at the top. **This is the only file you edit.**

```
SITE_DOMAIN=scoutsdelimal.be
EMAIL_URL=smtp+tls://inscriptions@scoutsdelimal.be:yourpassword@mail.example.org:587
DEFAULT_FROM_EMAIL=inscriptions@scoutsdelimal.be
ACME_EMAIL=your-own-address@example.org
```

| Line | What to put |
| --- | --- |
| `SITE_DOMAIN` | your domain name, exactly, with no `https://` and no trailing slash |
| `EMAIL_URL` | your mail provider's details — see below |
| `DEFAULT_FROM_EMAIL` | the address the site sends as, which must be one your mail provider lets you use |
| `ACME_EMAIL` | your own address; Let's Encrypt uses it to warn you if the certificate ever fails to renew |

Save (`Ctrl+O`, Enter) and quit (`Ctrl+X`).

### About that email line

TroopConnect sends registration confirmations, reminders and section emails —
it is a large part of what it does, so it needs a mail account it can send
through. Any provider works. You need four pieces, in this shape:

```
smtp+tls://USERNAME:PASSWORD@MAIL-SERVER:PORT
```

- `smtp+tls` — the right choice for almost every provider, on port `587`.
- `USERNAME` and `PASSWORD` — the mail account's login.
- `MAIL-SERVER` — from your provider's help pages, something like
  `smtp.gmail.com` or `mail.scoutsdelimal.be`.
- `PORT` — `587` with `smtp+tls`, or `465` with `smtp+ssl`.

Two traps worth knowing about:

- **If your password contains `@`, `:` or `/`,** replace it with `%40`, `%3A`
  and `%2F`. A password of `p@ss` is written `p%40ss` here.
- **Port 25 is blocked by nearly every hosting provider.** If your mail
  provider only offers port 25, find another port or use a different provider.
  The setup wizard will tell you if mail does not work, so you will find out
  immediately rather than through parents who never received anything.

If you do not have a mail account yet, TroopConnect can also send through
[MailerSend](https://www.mailersend.com) by setting `MAILERSEND_API_KEY`
instead of `EMAIL_URL`.

### Start it

```bash
docker compose up -d
```

The first time, it downloads the pieces and starts them. It prints a stream of
lines and then returns to the prompt. Wait about a minute, then look at the
log of the website container:

```bash
docker compose logs web | grep -i "setup code"
```

You should see a line like:

```
Setup code: K7QP-2M4T-9XWB-HR3F
```

**Write it down.** It is the key to the next step. If the line has scrolled
away or you lost it, ask for it again:

```bash
docker compose exec web python manage.py setup_code
```

## Step 7 — Answer the setup wizard

Open your domain in a browser: `https://scoutsdelimal.be`. Until you finish the
wizard, **every page leads there** — an instance with no administrator has
nothing worth showing yet.

> The screenshots below show the wizard **in English**. A brand-new instance
> starts **in French**, which is the default it ships with, whatever language
> your browser asks for. You get English at the Languages step (the fourth
> screen), and you can change the site's languages at any time afterwards
> under Site settings. So do not be surprised if your first screen is French.

Every answer can be changed later.

### The setup code

![The setup code screen](docs/images/getting-started/01-setup-1-code.png)

Type the code from the log. It is a gate, not a password: it exists so that
only someone who can read your server's log — you — can create the
administrator account.

### The administrator

![Creating the first administrator](docs/images/getting-started/02-setup-2-administrator.png)

This is the account **you** will log in with. Use an address you will still
have next year. The password needs to be a long one; it is the account that can
do everything.

### Your unit

![The unit's name and contact details](docs/images/getting-started/03-setup-3-unit.png)

The unit's name, and how the outside world reaches it. The name is used in the
header of the site and in the signature of every email, so make it the one your
families use. Contact details can be left empty and filled in later; the logo
and favicon too (TroopConnect shows the Les Scouts mark until you upload your
own).

### Languages

![Languages and country settings](docs/images/getting-started/04-setup-4-languages.png)

Which languages the site offers. You can enable French, Dutch and English in
any combination; visitors get a language switcher, and each of your families
gets emails in their own language. "Phone country" and "currency" only decide
how phone numbers and amounts are *displayed* — nothing is rewritten in the
database if you change them.

### Sections

![Editing the branches and sections](docs/images/getting-started/05-setup-5-sections.png)

Your branches and sections, starting from Les Scouts' own four. Rename a branch
in each language you enabled, change its ages, add and remove sections. Each
section is a group a child is enrolled in. You can change all of this later, in
the Django admin.

### The scout year

![The shape of the scout year](docs/images/getting-started/06-setup-6-scout-year.png)

When your year starts, when ages are counted, and the day the section passage
falls due. The defaults (year from 1 August, ages on 31 December, passage on
1 May) are Les Scouts' convention. "Section passage runs — Automatic" means
members are moved up on that day without anyone pressing a button.

### Modules

![Switching modules on and off](docs/images/getting-started/07-setup-7-modules.png)

Three parts of the site you can switch off if you do not want them: membership
fees, signature campaigns, and the section agenda. Switching one off hides it
completely (its pages return "not found") but **deletes nothing**, so you can
switch it back on later and find everything where you left it.

### The test email

![The test email step](docs/images/getting-started/08-setup-8-test-email.png)

The wizard sends one real message, *now*, and will not finish until it arrives.
This is deliberate: a wrong password or a blocked port is much better found out
about here, while you are looking at the screen, than through families who
never heard anything.

If it fails, the page shows your mail server's own words. The usual causes are
a wrong password, the wrong port (try 587), or `DEFAULT_FROM_EMAIL` being an
address your provider will not let you send as. Fix it in `.env`, then:

```bash
docker compose up -d
```

and try the step again.

### Done

![The wizard's last screen](docs/images/getting-started/09-setup-9-done.png)

Your site is live.

## Step 8 — After the wizard

### Log in

![The login page](docs/images/getting-started/10-site-1-login.png)

Log in with the administrator account you created. This is also where families
will register and log in.

### The site itself

![The homepage of a fresh instance](docs/images/getting-started/11-site-2-homepage.png)

The homepage starts with **placeholder text**, as in the screenshot above. It is
there to be replaced: press **Edit this page** and write your own welcome. Until
you do, that text is what the world sees.

### Settings

![The settings page](docs/images/getting-started/12-site-3-settings.png)

Everything you answered in the wizard is here, at **Site settings**, in four
groups: the unit, its languages, the calendar, and the modules. This is where
you change them later. Branches and sections are edited in the Django admin
(`/admin/`).

## Looking after it

### Backups

Your data lives in two Docker volumes: **`db_data`** (the database) and
**`media`** (uploaded files — logos, attachments, signed documents). To back
them up, from the `TroopConnect` directory on the server:

```bash
docker compose exec -T db pg_dump -U troopconnect troopconnect > backup-$(date +%F).sql
```

That writes a dated `.sql` file in your current directory, which you should
copy to your own computer — a backup on the same server is not a backup. For
the uploads, copy the `media` volume with:

```bash
docker run --rm -v troopconnect_media:/data -v "$PWD":/out alpine \
  tar czf /out/media-$(date +%F).tar.gz -C /data .
```

(The volume's name starts with the folder name — check it with
`docker volume ls` if the command complains.)

### Upgrading

Decide which version you want in `.env`:

```
TC_VERSION=0.4.2
```

Then:

```bash
docker compose pull
docker compose up -d
```

Migrations run by themselves, under a lock, so a restart is safe. **Back up
first.** TroopConnect is pre-1.0, and a release can change the database in ways
that cannot be undone.

### The four volumes you must not delete

| Volume | Holds | If you delete it |
| --- | --- | --- |
| `db_data` | the database | you lose every member, enrollment and payment |
| `media` | uploaded files | you lose logos, attachments and signed documents |
| `app_secrets` | the key that signs logins | everybody is logged out |
| `db_secrets` | the database password | the site can no longer open its own database |

Never delete `db_data` on its own: the password in `db_secrets` then points at
a database that does not exist. **Delete both, or neither.**

### When something is wrong

```bash
docker compose ps                       # what is running, and is it healthy
docker compose logs web                 # the website's own log
docker compose logs worker              # background jobs and email sending
docker compose exec web python manage.py check    # configuration problems, in plain words
curl -s https://scoutsdelimal.be/healthz          # is the database answering?
```

`/healthz` answers with a small JSON line naming whatever is broken — usually
`{"database": "ok", "cache": "ok"}`.

### Common problems

| What you see | What it usually means |
| --- | --- |
| `docker: command not found` | Docker is not installed, or you opened a new terminal before finishing step 5. Re-run the `curl` line. |
| `Permission denied` when connecting | wrong password, or the wrong username — some providers give you `ubuntu` rather than `root`. |
| The browser warns about the certificate | DNS has not spread yet, or ports 80/443 are closed. Wait, then check your provider's firewall. |
| `https://your-domain` shows a connection error | the containers are not running yet, or Caddy is still waiting for the certificate. Try `docker compose ps`. |
| Everything leads to a setup page you cannot leave | that is correct until you finish the wizard — see step 7. |
| The wizard says it cannot send email | wrong `EMAIL_URL`, usually the port or the password. See "the test email" above. |
| `port is already allocated` | something else on the server uses port 80 or 443 (often an older web server from the provider's image). |
| The setup code has scrolled away | `docker compose exec web python manage.py setup_code`. |

## Getting help

- The [README](README.md) explains what the project is and how it is put
  together.
- [INSTALL.md](INSTALL.md) is the same installation without the hand-holding,
  plus the community-maintained Ansible playbook.
- [docs/dev/CONTRACT.md](docs/dev/CONTRACT.md) documents every setting in
  `.env` and every field on the settings page.
- For a bug or a question, open an issue on
  [GitHub](https://github.com/tdebruyn/TroopConnect/issues). Say what you were
  doing, what you expected, and paste what the command printed — that is enough
  for someone to help.
