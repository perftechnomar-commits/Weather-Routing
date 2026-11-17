# Login setup

In Streamlit Cloud, open Manage app → Settings → Secrets and add:

```toml
[passwords]
performance = "REPLACE_WITH_YOUR_STRONG_PASSWORD"
# Add more username/password entries if needed.
```

Use your own password, not the placeholder. Never commit real passwords to GitHub.
For local use, save this configuration in `.streamlit/secrets.toml`.
The app blocks access if login secrets are missing. Data loads only after sign-in.
Login lasts for the browser session; reloading may require signing in again.
This is a separate application login, not the Marorka API credentials.
Keep the repository private: bundled CSVs and the offline HTML contain data independently of the app login. Do not distribute the offline HTML as a protected dashboard.
