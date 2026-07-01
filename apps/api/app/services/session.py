"""DynamoDB session store for voice/chat conversations."""

from app.storage.dynamo import SessionDynamoStore

session_store = SessionDynamoStore()
