"""
One-time setup script: creates the Databricks secret scope and stores API keys. 
So never commit the resulting secret value anywhere.
"""
from databricks.sdk import WorkspaceClient
from databricks.sdk.service import workspace
import getpass, secrets

w = WorkspaceClient()

w.secrets.create_scope(scope="geoapify")
w.secrets.put_secret(
    scope="geoapify",
    key="geoapify-key",
    string_value=getpass.getpass("Paste your geoapify API key: ")
)

w.secrets.create_scope(scope="ors")
w.secrets.put_secret(
    scope="ors",
    key="ors-key",
    string_value=getpass.getpass("Paste your OpenRouteServer API key: ")
)


# Shared secret between the Silver Spark job and the app's /silver/sync endpoint.
# It is is to prove the caller is the Spark job and not some random request hitting the endpoint.

w.secrets.put_secret(
    scope="geoapify",
    key="silver-sync-token",
    string_value=secrets.token_urlsafe(32)
)
 
print("Done. Secrets stored")

