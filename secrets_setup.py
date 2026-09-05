"""
One-time setup script: creates the Databricks secret scope and stores API keys. 
So never commit the resulting secret value anywhere.
"""
from databricks.sdk import WorkspaceClient
from databricks.sdk.service import workspace
import getpass

w = WorkspaceClient()

w.secrets.create_scope(scope="geoapify")
w.secrets.put_secret(
    scope="geoapify",
    key="geoapify-key",
    string_value=getpass.getpass("Paste your geoapify API key: ")
)
