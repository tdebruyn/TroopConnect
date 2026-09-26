# Getting-started screenshots

These are real screenshots of a real instance, not mockups. They are used by
[GETTING-STARTED.md](../../../GETTING-STARTED.md); re-shoot them when the setup
wizard's markup or copy changes.

They were captured like this:

1. Bring up a **throwaway** instance — one that has never been set up, so the
   wizard is live — on a spare port, with its own compose project name so it
   neither touches a development database nor collides on ports:

   ```bash
   docker compose -f compose.yml -f compose.dev.yml --project-name guide up -d
   ```

   The instance needs a `.env` (any values: `SITE_DOMAIN=localhost`,
   `EMAIL_URL=console://`), and the dev overlay's published ports moved aside
   with a small override file if a dev stack is already running.

2. Read the setup code the entrypoint prints, and walk the wizard with
   Playwright — `/setup/<step>` addresses each step directly, and the steps
   save as they are answered, so a script can fill a step, screenshot it and
   press Next.

3. The shots are in **English**, which is not what a new instance shows: it
   starts in French, the language it ships with. Setting
   `TroopSettings.enabled_languages` to `fr, nl, en` and `default_language` to
   `en` before the walk is what makes them English. The guide says so where it
   shows them.

4. Delete the throwaway instance and its volumes (`down -v`) once they are
   captured. It holds the administrator account and password shown in the
   screenshots.
