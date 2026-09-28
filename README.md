# Marorka Python connection test

A separate diagnostic app; does not modify existing apps. No actual credentials are included.

## Run locally on Windows
1. Extract this folder and open a terminal in it.
2. Run `py -m pip install -r requirements.txt`.
3. Run `py -m streamlit run app.py`.
4. In the browser, enter the Weather Routing API credentials, choose **Test authentication only**, and click **Run test**.
5. If login succeeds, run **Retrieve one vessel**, with a real seven-digit IMO.
6. For fleet retrieval, export your Excel Fleet table to a comma-separated UTF-8 CSV with `ShipName,IMONo` headers and upload it. Duplicate IMOs are requested once. Invalid IMOs appear as errors.

If `py` is unavailable but Python is installed, replace `py` with `python`.

## Streamlit Community Cloud / GitHub
Upload app.py, marorka_client.py and requirements.txt to a new repository or separate folder. Select app.py as the main file. The login form works without any credentials in the repository. Restrict access to your intended users.

Alternatively configure the following in Streamlit's Secrets settings (not in GitHub):

```toml
[marorka]
username = "YOUR_API_USERNAME"
password = "YOUR_API_PASSWORD"
```

With Secrets configured, the app uses those credentials instead of the form. All users allowed into that deployment can request data using that account. No automatic/scheduled refresh or permanent snapshot is implemented.

## Console alternative
`py test_connection.py` tests authentication only, with a hidden password prompt directly in the terminal.
`py test_connection.py --imo YOUR_IMO` retrieves one vessel.
`py test_connection.py --fleet fleet.csv` retrieves all listed vessels.
The console requires requests; install it with `py -m pip install requests` if you do not want Streamlit.

## Request contract, from supplied Marorka documentation
- POST https://am-api-gateway.northeu-prod-001.ascenzmarorka.com/api/auth/online/token
- JSON body: username and password. Read access_token from the response.
- GET /wrs/latestapprovedpassageplan?shipimo=SEVEN_DIGIT_IMO
- Authorization: Bearer TOKEN

Uses requests' JSON encoding and normal certificate verification. Redirects are not followed, so credentials are not replayed to a different location. A no-op explicit auth handler prevents local .netrc Basic credentials overriding the intended authentication, while preserving normal environment proxy support.

## Interpretation
- Token request 401: login rejected before any vessel request. Python alone does not guarantee a fix.
- Token succeeds, plan 403: investigate vessel/API permission.
- Plan 404: resource not found; no specific no-plan meaning is assumed.
- Empty response: reported separately, without inventing a reason.
- A 401 on a plan request triggers one token renewal and one retry. Continued 401, token-generation failure, or 429 stops remaining fleet requests and marks them Not attempted.

Raw JSON plans are preserved because the response schema is not yet available. No optimization submission endpoint is called. Login tokens/passwords are not exported or logged. Form values and tokens exist in server memory during a request; credentials in Streamlit Secrets are managed by the deployment. Results remain in the user's app session until replaced or the session ends; downloads persist wherever the user saves them. Do not share response downloads if they contain confidential voyage information.

The code was verified with simulated HTTP responses; live account access has not been tested. Send only the displayed error (with any account details removed) or a non-sensitive sample plan structure for the next step.
